#!/usr/bin/env python3
"""
Export astrometric detections to Pumalink TRD9 format.

Pumalink (https://github.com/atlas-ifa/puma) is a tracklet-linking tool for
solar system object detection. It ingests astrometric detections in TRD9
format: 9 whitespace-delimited fields per detection line.

TRD9 field order:
    MJD  RA  Dec  xerr  terr  lng  lat  elev  ID

Field definitions (from PUMA manual):
    MJD   - Modified Julian Date at exposure midpoint (days)
    RA    - Right ascension, J2000 apparent (degrees)
    Dec   - Declination, J2000 apparent (degrees)
    xerr  - Cross-track astrometric 1-sigma error (arcseconds)
    terr  - Along-track astrometric 1-sigma error (arcseconds)
              Estimated as xerr x sqrt(major_axis / minor_axis).
              Equals xerr when the PSF is circular (no trailing).
              Larger than xerr for trailed detections.
    lng   - Observatory longitude, WGS84 east-positive (degrees)
    lat   - Observatory geodetic latitude, WGS84 (degrees)
    elev  - Observatory elevation above WGS84 ellipsoid (meters)
    ID    - Unique detection identifier (max 31 chars, no spaces or commas)

Observatory coordinates:
    Loaded from a local copy of the MPC observatory codes file (ObsCodes.html
    or ObsCodes.dat), available from:
        https://www.minorplanetcenter.net/iau/lists/ObsCodes.html

    The MPC file stores positions as geocentric parallax constants
    (rho*cos(phi'), rho*sin(phi')). This script converts them to WGS84
    geodetic latitude and ellipsoidal elevation.

    For input formats that carry a per-observation observatory code (MPC80,
    ADES PSV), the observatory is resolved per observation from the loaded
    file. For pipeline formats (SQLite, CSV), a single observatory code is
    supplied via --observatory.

Input formats:
    --db    PATH   SQLite database (alerts_raw table from this pipeline)
    --csv   PATH   CSV file exported from this pipeline
    --mpc80 PATH   MPC 80-column optical observation file
    --ades  PATH   ADES PSV (pipe-separated values) file

Astrometric error estimation:
    For SQLite/CSV inputs (SNR available):
        xerr = PSF_FWHM / SNR   (if SNR > 0)
        xerr = DEFAULT_XERR     (fallback when SNR is NULL or zero)

    For MPC80 inputs (no SNR):
        xerr = DEFAULT_XERR (override with --default-xerr)

    For ADES PSV inputs:
        xerr and terr taken directly from rmsRA / rmsDec columns when present.
        Falls back to DEFAULT_XERR if those columns are absent.

    Along-track error (terr):
        If trail length is available (trailLength field in SQLite trail_data):
            terr = xerr x sqrt(sqrt(psf_fwhm^2 + trail_length^2) / psf_fwhm)
        Otherwise:
            terr = xerr  (symmetric PSF assumed)

Usage examples:
    # From SQLite database, all SSO alerts, Rubin Observatory
    python export_to_pumalink.py --db data/alerts.db --sso-only \\
        --obscode-file ObsCodes.html --observatory X05 -o detections.trd

    # From pipeline CSV export, Rubin Observatory
    python export_to_pumalink.py --csv data/lsst_alerts_20260210.csv \\
        --obscode-file ObsCodes.html --observatory X05 -o detections.trd

    # From MPC80 file (observatory codes embedded per observation)
    python export_to_pumalink.py --mpc80 observations.mpc \\
        --obscode-file ObsCodes.html -o detections.trd

    # From ADES PSV file (observatory codes embedded per observation)
    python export_to_pumalink.py --ades observations.psv \\
        --obscode-file ObsCodes.html -o detections.trd

    # Filter by MJD window
    python export_to_pumalink.py --db data/alerts.db \\
        --obscode-file ObsCodes.html --observatory X05 \\
        --mjd-min 60500.0 --mjd-max 60510.0 -o detections.trd

    # List all observatories in the loaded ObsCodes file
    python export_to_pumalink.py --obscode-file ObsCodes.html \\
        --list-observatories

    # Override PSF FWHM for error estimation (e.g., ZTF at 2.0 arcsec)
    python export_to_pumalink.py --db data/alerts.db \\
        --obscode-file ObsCodes.html --observatory I41 \\
        --psf-fwhm 2.0 -o detections.trd
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
import sys
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# WGS84 ellipsoid constants
# ---------------------------------------------------------------------------
_WGS84_A = 6378137.0  # equatorial radius, metres
_WGS84_F = 1.0 / 298.257223563  # flattening
_WGS84_B = _WGS84_A * (1.0 - _WGS84_F)  # polar radius, metres
_WGS84_E2 = 1.0 - (_WGS84_B / _WGS84_A) ** 2  # first eccentricity squared

# ---------------------------------------------------------------------------
# Astrometric error defaults
# ---------------------------------------------------------------------------
DEFAULT_XERR_ARCSEC = 0.2  # fallback when SNR / rmsRA unavailable
DEFAULT_PSF_FWHM_ARCSEC = 1.0  # conservative default; override with --psf-fwhm

# ---------------------------------------------------------------------------
# MPC ObsCodes file — local path and source URL
# ---------------------------------------------------------------------------
MPC_OBSCODE_URL = "https://www.minorplanetcenter.net/iau/lists/ObsCodes.html"

# Default local path: data/ObsCodes.dat relative to the repository root.
# Kept up to date by scripts/update_obscodes.sh (run daily via cron or systemd).
OBSCODE_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "ObsCodes.dat"


# ---------------------------------------------------------------------------
# Observatory
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Observatory:
    """WGS84 geodetic position of an observatory.

    Derived from MPC parallax constants (rho_cos_phi, rho_sin_phi) by
    conversion from geocentric to geodetic coordinates.
    """

    code: str  # MPC 3-character site code
    name: str  # human-readable name from ObsCodes file
    lng: float  # east longitude, degrees, WGS84
    lat: float  # geodetic latitude, degrees, WGS84
    elev: float  # elevation above WGS84 ellipsoid, metres


def _geocentric_to_geodetic(rho_cos_phi: float, rho_sin_phi: float) -> tuple[float, float]:
    """Convert MPC parallax constants to geodetic latitude and elevation.

    The MPC stores observatory positions as dimensionless parallax constants
    in units of Earth's equatorial radius:
        rho_cos_phi = (r/a) * cos(geocentric_latitude)
        rho_sin_phi = (r/a) * sin(geocentric_latitude)

    This function converts to WGS84 geodetic latitude (degrees) and
    ellipsoidal elevation (metres) using Bowring's iterative method.

    Args:
        rho_cos_phi: MPC parallax constant (dimensionless).
        rho_sin_phi: MPC parallax constant (dimensionless, signed).

    Returns:
        (geodetic_latitude_degrees, elevation_metres)
    """
    p = rho_cos_phi * _WGS84_A  # distance from rotation axis, metres
    z = rho_sin_phi * _WGS84_A  # signed z-coordinate, metres

    if p == 0.0 and z == 0.0:
        return 0.0, 0.0

    # Bowring's method: one iteration is typically sufficient
    theta = math.atan2(z * _WGS84_A, p * _WGS84_B)
    lat = math.atan2(
        z + (_WGS84_A**2 - _WGS84_B**2) / _WGS84_B * math.sin(theta) ** 3,
        p - _WGS84_E2 * _WGS84_A * math.cos(theta) ** 3,
    )

    sin_lat = math.sin(lat)
    cos_lat = math.cos(lat)
    N = _WGS84_A / math.sqrt(1.0 - _WGS84_E2 * sin_lat**2)

    if abs(cos_lat) > 1e-10:
        elev = p / cos_lat - N
    else:
        elev = abs(z) / abs(sin_lat) - N * (1.0 - _WGS84_E2)

    return math.degrees(lat), elev


# ---------------------------------------------------------------------------
# MPC ObsCodes file loading
# ---------------------------------------------------------------------------


def load_observatories(obscode_path: Path) -> dict[str, Observatory]:
    """Load observatory positions from a local MPC ObsCodes file.

    Supports both the plain-text (ObsCodes.dat) and HTML (ObsCodes.html)
    variants available from:
        https://www.minorplanetcenter.net/iau/lists/ObsCodes.html

    The MPC file format (fixed-width text):
        Col 0-2:   3-character site code
        Col 3-11:  east longitude, degrees (right-justified)
        Col 12-20: rho*cos(phi'), parallax constant
        Col 21-30: rho*sin(phi'), parallax constant (signed)
        Col 31+:   observatory name

    Entries with missing parallax constants (e.g., space-based or
    roving observers) are skipped — they cannot be represented in TRD9.

    Args:
        obscode_path: Path to the local MPC ObsCodes file.

    Returns:
        Dictionary mapping 3-character MPC code → Observatory.

    Raises:
        FileNotFoundError: If obscode_path does not exist.
    """
    if not obscode_path.exists():
        raise FileNotFoundError(
            f"ObsCodes file not found: {obscode_path}\n" f"Download from: {MPC_OBSCODE_URL}"
        )

    text = obscode_path.read_text(encoding="utf-8", errors="replace")

    # Strip HTML tags if this is the .html variant
    if "<" in text[:200]:
        text = re.sub(r"<[^>]+>", "", text)

    observatories: dict[str, Observatory] = {}

    for line in text.splitlines():
        # Skip header, blank lines, and lines shorter than 30 characters
        if len(line) < 30 or line.startswith("Code") or not line[0:3].strip():
            continue

        code = line[0:3].strip()
        lng_str = line[3:12].strip()
        cos_str = line[12:21].strip()
        sin_str = line[21:30].strip()
        name = line[30:].strip()

        # Skip entries with missing parallax constants
        if not cos_str or not sin_str:
            continue

        try:
            lng = float(lng_str)
            rho_cos_phi = float(cos_str)
            rho_sin_phi = float(sin_str)
        except ValueError:
            continue

        lat, elev = _geocentric_to_geodetic(rho_cos_phi, rho_sin_phi)

        # MPC longitudes are 0-360 deg East; convert to -180 to +180
        if lng > 180.0:
            lng -= 360.0

        observatories[code] = Observatory(
            code=code,
            name=name,
            lng=lng,
            lat=lat,
            elev=elev,
        )

    return observatories


def download_obscode_file(dest: Path) -> None:
    """Download the MPC ObsCodes file to a local path.

    Args:
        dest: Destination file path.
    """
    print(f"Downloading MPC ObsCodes from {MPC_OBSCODE_URL} → {dest}")
    urllib.request.urlretrieve(MPC_OBSCODE_URL, dest)
    print("Download complete.")


# ---------------------------------------------------------------------------
# Coordinate / time utilities
# ---------------------------------------------------------------------------


def _cal_to_mjd(year: int, month: int, day_fraction: float) -> float:
    """Convert calendar date (with fractional day) to MJD."""
    y, m = year, month
    if m <= 2:
        y -= 1
        m += 12
    A = int(y / 100)
    B = 2 - A + int(A / 4)
    d = int(day_fraction)
    frac = day_fraction - d
    jd = int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + B - 1524.5
    return jd - 2400000.5 + frac


def _ra_hms_to_deg(h: float, m: float, s: float) -> float:
    """Convert RA from hours/minutes/seconds to decimal degrees."""
    return (h + m / 60.0 + s / 3600.0) * 15.0


def _dec_dms_to_deg(sign: str, d: float, m: float, s: float) -> float:
    """Convert Dec from sign/degrees/arcminutes/arcseconds to decimal degrees."""
    val = d + m / 60.0 + s / 3600.0
    return -val if sign == "-" else val


def _iso_to_mjd(iso: str) -> float:
    """Convert an ISO 8601 timestamp string to MJD."""
    iso = iso.rstrip("Z").replace("T", " ")
    # Handle optional fractional seconds
    fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in iso else "%Y-%m-%d %H:%M:%S"
    dt = datetime.strptime(iso, fmt).replace(tzinfo=UTC)
    # MJD epoch: 1858-11-17 00:00:00 UTC = JD 2400000.5
    mjd_epoch = datetime(1858, 11, 17, tzinfo=UTC)
    return (dt - mjd_epoch).total_seconds() / 86400.0


# ---------------------------------------------------------------------------
# Astrometric error estimation
# ---------------------------------------------------------------------------


def _estimate_xerr(snr: float | None, psf_fwhm: float) -> float:
    """Estimate cross-track positional error in arcseconds.

    Args:
        snr: Signal-to-noise ratio, or None if unavailable.
        psf_fwhm: PSF FWHM in arcseconds for this observatory.

    Returns:
        1-sigma cross-track error in arcseconds.
    """
    if snr and snr > 0:
        return psf_fwhm / snr
    return DEFAULT_XERR_ARCSEC


def _estimate_terr(xerr: float, trail_length: float | None, psf_fwhm: float) -> float:
    """Estimate along-track positional error in arcseconds.

    For a non-trailed detection (trail_length is None or zero), the PSF is
    symmetric and terr equals xerr.

    For a trailed detection, the PSF is elongated. Following the PUMA manual
    ("xerr multiplied by the square root of the ratio of the detection's major
    to minor axis"):
        major_axis = sqrt(psf_fwhm^2 + trail_length^2)
        minor_axis = psf_fwhm
        terr = xerr x sqrt(major_axis / minor_axis)

    Args:
        xerr: Cross-track error in arcseconds.
        trail_length: Trail length in arcseconds from trailLength field,
                      or None if not available.
        psf_fwhm: PSF FWHM in arcseconds.

    Returns:
        1-sigma along-track error in arcseconds.
    """
    if trail_length and trail_length > 0 and psf_fwhm > 0:
        major = math.sqrt(psf_fwhm**2 + trail_length**2)
        return xerr * math.sqrt(major / psf_fwhm)
    return xerr


# ---------------------------------------------------------------------------
# SQLite reader (pipeline internal format)
# ---------------------------------------------------------------------------


def read_from_sqlite(
    db_path: Path,
    observatory: Observatory,
    psf_fwhm: float,
    *,
    sso_only: bool = False,
    filtered_only: bool = False,
    mjd_min: float | None = None,
    mjd_max: float | None = None,
) -> list[dict]:
    """Read detections from the pipeline SQLite database.

    Args:
        db_path: Path to the SQLite database.
        observatory: Observatory used for all detections in this database.
        psf_fwhm: PSF FWHM in arcseconds for error estimation.
        sso_only: Only return alerts with has_ss_source = 1.
        filtered_only: Only return alerts present in alerts_filtered.
        mjd_min: Exclude observations before this MJD.
        mjd_max: Exclude observations after this MJD.

    Returns:
        List of TRD9 row dicts ready for write_trd9().

    Raises:
        FileNotFoundError: If db_path does not exist.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        prefix = "r." if filtered_only else ""
        if filtered_only:
            base = (
                "SELECT r.dia_source_id, r.mjd, r.ra, r.dec, r.snr, r.trail_data "
                "FROM alerts_raw r "
                "INNER JOIN alerts_filtered f ON f.raw_alert_id = r.id"
            )
        else:
            base = "SELECT dia_source_id, mjd, ra, dec, snr, trail_data " "FROM alerts_raw"

        conditions, params = [], []
        if sso_only:
            conditions.append(f"{prefix}has_ss_source = 1")
        if mjd_min is not None:
            conditions.append(f"{prefix}mjd >= ?")
            params.append(mjd_min)
        if mjd_max is not None:
            conditions.append(f"{prefix}mjd <= ?")
            params.append(mjd_max)

        query = base
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += f" ORDER BY {prefix}mjd"

        rows = []
        for row in conn.execute(query, params).fetchall():
            trail_data = json.loads(row["trail_data"] or "{}")
            trail_length = trail_data.get("trailLength")

            xerr = _estimate_xerr(row["snr"], psf_fwhm)
            terr = _estimate_terr(xerr, trail_length, psf_fwhm)

            rows.append(
                {
                    "mjd": row["mjd"],
                    "ra": row["ra"],
                    "dec": row["dec"],
                    "xerr": xerr,
                    "terr": terr,
                    "lng": observatory.lng,
                    "lat": observatory.lat,
                    "elev": observatory.elev,
                    "id": str(row["dia_source_id"]),
                }
            )
        return rows
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CSV reader (pipeline export format)
# ---------------------------------------------------------------------------


def read_from_csv(
    csv_path: Path,
    observatory: Observatory,
    psf_fwhm: float,
    *,
    sso_only: bool = False,
    mjd_min: float | None = None,
    mjd_max: float | None = None,
) -> list[dict]:
    """Read detections from a pipeline CSV export file.

    Required columns: dia_source_id, mjd, ra, dec.
    Optional columns: snr, has_ss_source, trail_data.

    Args:
        csv_path: Path to the CSV file.
        observatory: Observatory used for all detections in this file.
        psf_fwhm: PSF FWHM in arcseconds for error estimation.
        sso_only: Only return rows where has_ss_source is truthy.
        mjd_min: Exclude observations before this MJD.
        mjd_max: Exclude observations after this MJD.

    Returns:
        List of TRD9 row dicts ready for write_trd9().

    Raises:
        FileNotFoundError: If csv_path does not exist.
        KeyError: If required columns are missing.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    required = {"dia_source_id", "mjd", "ra", "dec"}
    rows = []

    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        missing = required - set(reader.fieldnames)
        if missing:
            raise KeyError(f"CSV is missing required columns: {missing}")

        for row in reader:
            mjd = float(row["mjd"])
            if mjd_min is not None and mjd < mjd_min:
                continue
            if mjd_max is not None and mjd > mjd_max:
                continue

            has_ss = row.get("has_ss_source", "0")
            if sso_only and has_ss not in ("1", "True", "true", "yes"):
                continue

            snr = float(row["snr"]) if row.get("snr") else None
            trail_raw = row.get("trail_data") or "{}"
            trail_data = json.loads(trail_raw) if isinstance(trail_raw, str) else {}
            trail_length = trail_data.get("trailLength")

            xerr = _estimate_xerr(snr, psf_fwhm)
            terr = _estimate_terr(xerr, trail_length, psf_fwhm)

            rows.append(
                {
                    "mjd": mjd,
                    "ra": float(row["ra"]),
                    "dec": float(row["dec"]),
                    "xerr": xerr,
                    "terr": terr,
                    "lng": observatory.lng,
                    "lat": observatory.lat,
                    "elev": observatory.elev,
                    "id": str(int(row["dia_source_id"])),
                }
            )

    rows.sort(key=lambda r: r["mjd"])
    return rows


# ---------------------------------------------------------------------------
# MPC 80-column reader
# ---------------------------------------------------------------------------


def read_mpc80(
    path: Path,
    observatories: dict[str, Observatory],
    psf_fwhm: float,
    *,
    mjd_min: float | None = None,
    mjd_max: float | None = None,
) -> list[dict]:
    """Read detections from an MPC 80-column optical observation file.

    Column layout (1-indexed, inclusive):
        16-19  Year of observation
        21-22  Month of observation
        24-32  Day of observation (UT, with decimal fraction)
        33-34  RA hours
        36-37  RA minutes
        39-44  RA seconds
        45     Declination sign (+ or -)
        46-47  Declination degrees
        49-50  Declination arcminutes
        52-56  Declination arcseconds
        78-80  Observatory code

    Observatory coordinates are resolved per observation from the loaded
    MPC ObsCodes file. Observations whose observatory code is not found
    in the file are skipped with a warning.

    Args:
        path: Path to the MPC80 file.
        observatories: Observatory lookup dict from load_observatories().
        psf_fwhm: PSF FWHM in arcseconds for error estimation (default used,
                  no SNR available in MPC80 format).
        mjd_min: Exclude observations before this MJD.
        mjd_max: Exclude observations after this MJD.

    Returns:
        List of TRD9 row dicts ready for write_trd9().

    Raises:
        FileNotFoundError: If path does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"MPC80 file not found: {path}")

    rows = []
    skipped_codes: set[str] = set()
    seq = 0

    for _, line in enumerate(path.read_text().splitlines(), start=1):
        # Skip blank lines and comment lines
        if not line.strip() or line.startswith("#"):
            continue
        # Lines must be at least 80 characters; pad if needed
        line = line.ljust(80)

        try:
            # Python 0-indexed slices (MPC 1-indexed columns - 1)
            year = int(line[15:19])
            month = int(line[20:22])
            day_frac = float(line[23:32])
            ra_h = float(line[32:34])
            ra_m = float(line[35:37])
            ra_s = float(line[38:44])
            dec_sign = line[44]
            dec_d = float(line[45:47])
            dec_m = float(line[48:50])
            dec_s = float(line[51:56])
            obs_code = line[77:80].strip()
        except (ValueError, IndexError):
            continue  # malformed line

        obs = observatories.get(obs_code)
        if obs is None:
            skipped_codes.add(obs_code)
            continue

        mjd = _cal_to_mjd(year, month, day_frac)
        if mjd_min is not None and mjd < mjd_min:
            continue
        if mjd_max is not None and mjd > mjd_max:
            continue

        ra = _ra_hms_to_deg(ra_h, ra_m, ra_s)
        dec = _dec_dms_to_deg(dec_sign, dec_d, dec_m, dec_s)

        # No SNR in MPC80 format; use the default error
        xerr = DEFAULT_XERR_ARCSEC
        terr = xerr

        seq += 1
        rows.append(
            {
                "mjd": mjd,
                "ra": ra,
                "dec": dec,
                "xerr": xerr,
                "terr": terr,
                "lng": obs.lng,
                "lat": obs.lat,
                "elev": obs.elev,
                "id": f"mpc{seq:07d}",
            }
        )

    if skipped_codes:
        print(
            f"Warning: {len(skipped_codes)} unknown observatory code(s) skipped "
            f"(not in ObsCodes file): {', '.join(sorted(skipped_codes))}",
            file=sys.stderr,
        )

    rows.sort(key=lambda r: r["mjd"])
    return rows


# ---------------------------------------------------------------------------
# ADES PSV reader
# ---------------------------------------------------------------------------


def read_ades_psv(
    path: Path,
    observatories: dict[str, Observatory],
    psf_fwhm: float,
    *,
    mjd_min: float | None = None,
    mjd_max: float | None = None,
) -> list[dict]:
    """Read detections from an ADES PSV (pipe-separated values) file.

    Required ADES columns: stn, obsTime, ra, dec.
    Optional ADES columns: rmsRA, rmsDec (used directly as xerr/terr when present).

    Observatory coordinates are resolved per observation from the loaded
    MPC ObsCodes file using the `stn` column.

    Args:
        path: Path to the ADES PSV file.
        observatories: Observatory lookup dict from load_observatories().
        psf_fwhm: PSF FWHM in arcseconds (used only if rmsRA/rmsDec absent).
        mjd_min: Exclude observations before this MJD.
        mjd_max: Exclude observations after this MJD.

    Returns:
        List of TRD9 row dicts ready for write_trd9().

    Raises:
        FileNotFoundError: If path does not exist.
        KeyError: If required ADES columns are absent.
    """
    if not path.exists():
        raise FileNotFoundError(f"ADES PSV file not found: {path}")

    rows = []
    skipped_codes: set[str] = set()
    header: list[str] | None = None
    required = {"stn", "obsTime", "ra", "dec"}
    seq = 0

    for line in path.read_text().splitlines():
        stripped = line.strip()

        # Skip blank lines and metadata comments (# key value)
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue

        # Column header line: | col1 | col2 | ... |
        if header is None:
            if "|" in stripped:
                header = [c.strip() for c in stripped.strip("|").split("|")]
                missing = required - set(header)
                if missing:
                    raise KeyError(f"ADES PSV is missing required columns: {missing}")
            continue

        # Data line
        values = [c.strip() for c in stripped.strip("|").split("|")]
        if len(values) < len(header):
            values += [""] * (len(header) - len(values))
        record = dict(zip(header, values, strict=False))

        obs_code = record.get("stn", "").strip()
        obs = observatories.get(obs_code)
        if obs is None:
            skipped_codes.add(obs_code)
            continue

        try:
            mjd = _iso_to_mjd(record["obsTime"])
            ra = float(record["ra"])
            dec = float(record["dec"])
        except (ValueError, KeyError):
            continue

        if mjd_min is not None and mjd < mjd_min:
            continue
        if mjd_max is not None and mjd > mjd_max:
            continue

        # Use ADES rmsRA/rmsDec directly when available (they are in arcseconds)
        rms_ra = record.get("rmsRA", "").strip()
        rms_dec = record.get("rmsDec", "").strip()
        if rms_ra and rms_dec:
            try:
                xerr = float(rms_ra)
                terr = float(rms_dec)
            except ValueError:
                xerr = terr = DEFAULT_XERR_ARCSEC
        else:
            xerr = terr = DEFAULT_XERR_ARCSEC

        # Use obsID if present, otherwise generate a sequential ID
        obs_id = record.get("obsID", "").strip() or record.get("trkSub", "").strip()
        seq += 1
        det_id = obs_id if obs_id else f"ades{seq:07d}"

        rows.append(
            {
                "mjd": mjd,
                "ra": ra,
                "dec": dec,
                "xerr": xerr,
                "terr": terr,
                "lng": obs.lng,
                "lat": obs.lat,
                "elev": obs.elev,
                "id": det_id.replace(" ", "_").replace(",", "_")[:31],
            }
        )

    if skipped_codes:
        print(
            f"Warning: {len(skipped_codes)} unknown observatory code(s) skipped "
            f"(not in ObsCodes file): {', '.join(sorted(skipped_codes))}",
            file=sys.stderr,
        )

    if header is None:
        raise KeyError("No column header line found in ADES PSV file.")

    rows.sort(key=lambda r: r["mjd"])
    return rows


# ---------------------------------------------------------------------------
# TRD9 writer
# ---------------------------------------------------------------------------


def write_trd9(rows: list[dict], output_path: Path) -> int:
    """Write detection records to a Pumalink TRD9 file.

    Each output line contains 9 space-separated fields:
        MJD  RA  Dec  xerr  terr  lng  lat  elev  ID

    Args:
        rows: List of TRD9 row dicts (keys: mjd, ra, dec, xerr, terr,
              lng, lat, elev, id).
        output_path: Destination .trd file path.

    Returns:
        Number of detections written.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w") as f:
        f.write(
            "# Pumalink TRD9 export\n"
            "# Generated by export_to_pumalink.py (LSST Extendedness Pipeline)\n"
            "# Fields: MJD RA Dec xerr terr lng lat elev ID\n"
            "# Units:  days deg deg arcsec arcsec deg deg m string\n"
            "#\n"
        )
        for row in rows:
            f.write(
                f"{row['mjd']:.10f}  "
                f"{row['ra']:.6f}  "
                f"{row['dec']:.6f}  "
                f"{row['xerr']:.6f}  "
                f"{row['terr']:.6f}  "
                f"{row['lng']:.6f}  "
                f"{row['lat']:.6f}  "
                f"{row['elev']:.1f}  "
                f"{row['id']}\n"
            )

    return len(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export astrometric detections to Pumalink TRD9 format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Input (mutually exclusive)
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--db", metavar="PATH", type=Path, help="Pipeline SQLite database")
    src.add_argument("--csv", metavar="PATH", type=Path, help="Pipeline CSV export")
    src.add_argument("--mpc80", metavar="PATH", type=Path, help="MPC 80-column observation file")
    src.add_argument("--ades", metavar="PATH", type=Path, help="ADES PSV observation file")

    # Output
    parser.add_argument("-o", "--output", metavar="PATH", type=Path, help="Output .trd file")

    # ObsCodes
    obs_grp = parser.add_argument_group("observatory")
    obs_grp.add_argument(
        "--obscode-file",
        metavar="PATH",
        type=Path,
        default=OBSCODE_DEFAULT_PATH,
        help=(
            "Local MPC observatory codes file (ObsCodes.html or ObsCodes.dat). "
            f"Default: {OBSCODE_DEFAULT_PATH}. "
            "Kept current by scripts/update_obscodes.sh. "
            f"Source: {MPC_OBSCODE_URL}"
        ),
    )
    obs_grp.add_argument(
        "--download-obscodes",
        metavar="PATH",
        type=Path,
        help="Download MPC ObsCodes file to this path and exit.",
    )
    obs_grp.add_argument(
        "--observatory",
        metavar="CODE",
        help=(
            "MPC 3-character observatory code for pipeline input (--db / --csv). "
            "Not required for --mpc80 / --ades (code is read per observation)."
        ),
    )
    obs_grp.add_argument(
        "--list-observatories",
        action="store_true",
        help="Print all observatories from the ObsCodes file and exit.",
    )

    # Error estimation
    err_grp = parser.add_argument_group("error estimation")
    err_grp.add_argument(
        "--psf-fwhm",
        type=float,
        default=DEFAULT_PSF_FWHM_ARCSEC,
        metavar="ARCSEC",
        help=(
            f'PSF FWHM for xerr estimation (default: {DEFAULT_PSF_FWHM_ARCSEC}"). '
            'Typical values: Rubin 0.7", ZTF 2.0", ATLAS 2.0".'
        ),
    )
    err_grp.add_argument(
        "--default-xerr",
        type=float,
        default=DEFAULT_XERR_ARCSEC,
        metavar="ARCSEC",
        help=(f'Fallback xerr when SNR / rmsRA is unavailable (default: {DEFAULT_XERR_ARCSEC}").'),
    )

    # Filters (for pipeline inputs)
    flt_grp = parser.add_argument_group("filters (pipeline inputs only)")
    flt_grp.add_argument(
        "--sso-only",
        action="store_true",
        help="Only export alerts with SSSource association",
    )
    flt_grp.add_argument(
        "--filtered-only",
        action="store_true",
        help="Only export alerts in alerts_filtered table (--db only)",
    )
    flt_grp.add_argument(
        "--mjd-min",
        metavar="MJD",
        type=float,
        default=None,
        help="Exclude observations before this MJD",
    )
    flt_grp.add_argument(
        "--mjd-max",
        metavar="MJD",
        type=float,
        default=None,
        help="Exclude observations after this MJD",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # --download-obscodes
    if args.download_obscodes:
        download_obscode_file(args.download_obscodes)
        return 0

    # --list-observatories
    if args.list_observatories:
        if not args.obscode_file:
            parser.error("--list-observatories requires --obscode-file")
        try:
            obs = load_observatories(args.obscode_file)
        except FileNotFoundError as e:
            print(e, file=sys.stderr)
            return 1
        print(f"{'Code':<5}  {'Lng':>10}  {'Lat':>9}  {'Elev':>7}  Name")
        print("-" * 70)
        for o in obs.values():
            print(f"{o.code:<5}  {o.lng:>10.4f}  {o.lat:>9.4f}  {o.elev:>7.0f}  {o.name}")
        print(f"\n{len(obs)} observatories loaded.")
        return 0

    # Require input and output for actual export
    if all(x is None for x in [args.db, args.csv, args.mpc80, args.ades]):
        parser.error("one of --db, --csv, --mpc80, --ades is required")
    if args.output is None:
        parser.error("-o / --output is required")
    if args.obscode_file is None:
        parser.error(
            "--obscode-file is required\n"
            "  Download with: python export_to_pumalink.py --download-obscodes ObsCodes.html"
        )
    if args.filtered_only and args.csv:
        parser.error("--filtered-only requires --db (not available for CSV input)")
    if (args.db or args.csv) and not args.observatory:
        parser.error("--observatory is required when using --db or --csv")

    # Load observatories
    try:
        observatories = load_observatories(args.obscode_file)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"Loaded {len(observatories)} observatories from {args.obscode_file}")

    # Override default xerr if supplied
    global DEFAULT_XERR_ARCSEC
    DEFAULT_XERR_ARCSEC = args.default_xerr

    # Read input
    try:
        if args.db or args.csv:
            obs = observatories.get(args.observatory)
            if obs is None:
                print(
                    f"Observatory '{args.observatory}' not found in ObsCodes file.",
                    file=sys.stderr,
                )
                return 1
            print(f"Observatory: {obs.code}  {obs.name}")
            print(f"  lng={obs.lng:.4f}  lat={obs.lat:.4f}  elev={obs.elev:.0f} m")

            if args.db:
                print(f"Reading from SQLite: {args.db}")
                rows = read_from_sqlite(
                    args.db,
                    obs,
                    args.psf_fwhm,
                    sso_only=args.sso_only,
                    filtered_only=args.filtered_only,
                    mjd_min=args.mjd_min,
                    mjd_max=args.mjd_max,
                )
            else:
                print(f"Reading from CSV: {args.csv}")
                rows = read_from_csv(
                    args.csv,
                    obs,
                    args.psf_fwhm,
                    sso_only=args.sso_only,
                    mjd_min=args.mjd_min,
                    mjd_max=args.mjd_max,
                )

        elif args.mpc80:
            print(f"Reading from MPC80: {args.mpc80}")
            rows = read_mpc80(
                args.mpc80,
                observatories,
                args.psf_fwhm,
                mjd_min=args.mjd_min,
                mjd_max=args.mjd_max,
            )

        else:
            print(f"Reading from ADES PSV: {args.ades}")
            rows = read_ades_psv(
                args.ades,
                observatories,
                args.psf_fwhm,
                mjd_min=args.mjd_min,
                mjd_max=args.mjd_max,
            )

    except (FileNotFoundError, KeyError) as e:
        print(f"Error reading input: {e}", file=sys.stderr)
        return 1

    if not rows:
        print("No detections matched the specified filters — output file not written.")
        return 0

    print(f"Writing {len(rows)} detections to {args.output}")
    try:
        n = write_trd9(rows, args.output)
    except OSError as e:
        print(f"Error writing output: {e}", file=sys.stderr)
        return 1

    print(f"Done. {n} detections written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
