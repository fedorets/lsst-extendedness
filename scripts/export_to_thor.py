#!/usr/bin/env python3
"""
Export astrometric detections to THOR InputObservations format.

THOR (Tracklet-less Heliocentric Orbit Recovery) is a pipeline for linking
solar system object detections across multiple nights without requiring
pre-formed tracklets. Source: https://github.com/moeyensj/thor

This script exports detections from the LSST Extendedness pipeline (or from
standard astrometric file formats) to a Parquet or CSV file containing the
THOR InputObservations columns.

Output columns:
    id               - unique observation identifier (string)
    exposure_id      - exposure identifier; defaults to id when unavailable
    mjd_utc          - observation time, Modified Julian Date in UTC (float)
    night            - observing night (int, defined as floor(mjd_utc - 0.5))
    ra               - right ascension, J2000 apparent (degrees)
    dec              - declination, J2000 apparent (degrees)
    ra_sigma         - RA 1-sigma uncertainty in the RA direction (degrees)
    dec_sigma        - Dec 1-sigma uncertainty (degrees)
    ra_dec_cov       - RA-Dec covariance (degrees^2); set to NaN when unknown
    mag              - apparent magnitude; NaN when unavailable
    mag_sigma        - magnitude 1-sigma uncertainty; NaN when unavailable
    filter           - photometric filter name (e.g., "r", "g", "i")
    observatory_code - MPC 3-character observatory code

Notes on uncertainty units:
    THOR uses degrees for ra_sigma and dec_sigma (not arcseconds).
    ra_sigma is the sky-plane positional uncertainty in the east-west direction
    (consistent with the ADES rmsRA convention: already includes the cos(dec)
    projection). dec_sigma is the positional uncertainty in the north-south
    direction. Both are derived from the PSF-based SNR estimate in arcseconds
    and converted to degrees by dividing by 3600.

Loading the output in THOR:
    import pyarrow.parquet as pq
    from adam_core.time import Timestamp
    from thor.observations import InputObservations

    table = pq.read_table("detections.parquet")

    # Convert plain MJD float column to adam_core Timestamp
    import pyarrow as pa
    mjd = table.column("mjd_utc").to_pylist()
    time = Timestamp.from_mjd(mjd, scale="utc")

    obs = InputObservations.from_kwargs(
        id=table.column("id"),
        exposure_id=table.column("exposure_id"),
        time=time,
        ra=table.column("ra"),
        dec=table.column("dec"),
        ra_sigma=table.column("ra_sigma"),
        dec_sigma=table.column("dec_sigma"),
        ra_dec_cov=table.column("ra_dec_cov"),
        mag=table.column("mag"),
        mag_sigma=table.column("mag_sigma"),
        filter=table.column("filter"),
        observatory_code=table.column("observatory_code"),
    )

Input formats:
    --db    PATH   SQLite database (alerts_raw table from this pipeline)
    --csv   PATH   CSV file exported from this pipeline
    --mpc80 PATH   MPC 80-column optical observation file
    --ades  PATH   ADES PSV (pipe-separated values) file

Astrometric uncertainty estimation:
    For SQLite/CSV inputs:
        ra_sigma = psf_fwhm / (snr * 3600)             [degrees]
        dec_sigma = ra_sigma, enlarged for trailed detections
        Fallback to DEFAULT_POS_SIGMA_DEG when SNR is NULL or zero.

    For MPC80 inputs:
        ra_sigma = dec_sigma = DEFAULT_POS_SIGMA_DEG (override with --default-sigma)

    For ADES PSV inputs:
        ra_sigma = rmsRA / 3600    (when rmsRA column present, arcsec -> deg)
        dec_sigma = rmsDec / 3600  (when rmsDec column present)
        Fallback to DEFAULT_POS_SIGMA_DEG when rmsRA/rmsDec absent.

Usage examples:
    # From SQLite database, Rubin Observatory (X05)
    python export_to_thor.py --db data/alerts.db \\
        --observatory X05 -o observations.parquet

    # SSO-associated alerts only, MJD window
    python export_to_thor.py --db data/alerts.db --observatory X05 \\
        --sso-only --mjd-min 60500.0 --mjd-max 60510.0 -o obs.parquet

    # From pipeline CSV export
    python export_to_thor.py --csv data/alerts_20260210.csv \\
        --observatory X05 -o observations.parquet

    # From MPC 80-column file (per-observation observatory codes)
    python export_to_thor.py --mpc80 observations.mpc -o observations.parquet

    # From ADES PSV file (per-observation observatory codes)
    python export_to_thor.py --ades observations.psv -o observations.parquet

    # Output as CSV instead of Parquet
    python export_to_thor.py --db data/alerts.db --observatory X05 \\
        --format csv -o observations.csv

    # Override PSF FWHM (e.g., ZTF at 2.0 arcsec FWHM)
    python export_to_thor.py --db data/alerts.db --observatory I41 \\
        --psf-fwhm 2.0 -o observations.parquet
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Astrometric error defaults
# ---------------------------------------------------------------------------
_ARCSEC_TO_DEG = 1.0 / 3600.0

DEFAULT_POS_SIGMA_ARCSEC = 0.2  # fallback positional uncertainty when SNR / rmsRA unavailable
DEFAULT_POS_SIGMA_DEG = DEFAULT_POS_SIGMA_ARCSEC * _ARCSEC_TO_DEG
DEFAULT_PSF_FWHM_ARCSEC = 1.0  # conservative default; override with --psf-fwhm

# Default filter when none available from the data
DEFAULT_FILTER = "r"

# ---------------------------------------------------------------------------
# Time utilities
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
    fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in iso else "%Y-%m-%d %H:%M:%S"
    dt = datetime.strptime(iso, fmt).replace(tzinfo=UTC)
    mjd_epoch = datetime(1858, 11, 17, tzinfo=UTC)
    return (dt - mjd_epoch).total_seconds() / 86400.0


def _mjd_to_night(mjd: float) -> int:
    """Convert MJD to observing night integer.

    Uses the convention floor(mjd - 0.5), which rolls over at noon UTC so
    that observations taken in the same astronomical night (before and after
    midnight) share the same night number.

    Args:
        mjd: Modified Julian Date.

    Returns:
        Integer night identifier.
    """
    return int(math.floor(mjd - 0.5))


# ---------------------------------------------------------------------------
# Astrometric uncertainty estimation
# ---------------------------------------------------------------------------


def _estimate_pos_sigma_arcsec(snr: float | None, psf_fwhm: float) -> float:
    """Estimate astrometric positional uncertainty in arcseconds.

    Used for ra_sigma when no ADES rmsRA is available.

    Args:
        snr: Signal-to-noise ratio, or None if unavailable.
        psf_fwhm: PSF FWHM in arcseconds.

    Returns:
        1-sigma positional uncertainty in arcseconds.
    """
    if snr and snr > 0:
        return psf_fwhm / snr
    return DEFAULT_POS_SIGMA_ARCSEC


def _estimate_trail_sigma_arcsec(
    pos_sigma: float, trail_length: float | None, psf_fwhm: float
) -> float:
    """Estimate dec_sigma for a trailed detection in arcseconds.

    For a trailed detection the effective PSF is elongated in the direction
    of trailing. The dec_sigma (along the trail, assuming trailing is roughly
    in the RA direction) is larger than the symmetric ra_sigma:
        major_axis = sqrt(psf_fwhm^2 + trail_length^2)
        dec_sigma = pos_sigma x sqrt(major_axis / psf_fwhm)

    For non-trailed (or unknown trail) detections dec_sigma = pos_sigma.

    Args:
        pos_sigma: Symmetric positional uncertainty in arcseconds (= ra_sigma).
        trail_length: Trail length in arcseconds, or None.
        psf_fwhm: PSF FWHM in arcseconds.

    Returns:
        1-sigma dec_sigma in arcseconds.
    """
    if trail_length and trail_length > 0 and psf_fwhm > 0:
        major = math.sqrt(psf_fwhm**2 + trail_length**2)
        return pos_sigma * math.sqrt(major / psf_fwhm)
    return pos_sigma


# ---------------------------------------------------------------------------
# SQLite reader (pipeline internal format)
# ---------------------------------------------------------------------------


def read_from_sqlite(
    db_path: Path,
    observatory_code: str,
    psf_fwhm: float,
    default_filter: str,
    *,
    sso_only: bool = False,
    filtered_only: bool = False,
    mjd_min: float | None = None,
    mjd_max: float | None = None,
) -> list[dict]:
    """Read detections from the pipeline SQLite database.

    Args:
        db_path: Path to the SQLite database.
        observatory_code: MPC 3-character code for all detections in this DB.
        psf_fwhm: PSF FWHM in arcseconds for error estimation.
        default_filter: Filter name to use when psf_filter column is absent.
        sso_only: Only return alerts with has_ss_source = 1.
        filtered_only: Only return alerts in alerts_filtered.
        mjd_min: Exclude observations before this MJD.
        mjd_max: Exclude observations after this MJD.

    Returns:
        List of observation dicts ready for write_thor_observations().

    Raises:
        FileNotFoundError: If db_path does not exist.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Discover available columns
        cols = {row[1] for row in conn.execute("PRAGMA table_info(alerts_raw)").fetchall()}
        has_mag = "psf_mag" in cols
        has_filter = "filter" in cols

        select_cols = "dia_source_id, mjd, ra, dec, snr, trail_data, has_ss_source"
        if has_mag:
            select_cols += ", psf_mag"
        if has_filter:
            select_cols += ", filter"

        prefix = "r." if filtered_only else ""
        if filtered_only:
            base = (
                f"SELECT {', '.join(f'r.{c}' for c in select_cols.split(', '))} "
                "FROM alerts_raw r "
                "INNER JOIN alerts_filtered f ON f.raw_alert_id = r.id"
            )
        else:
            base = f"SELECT {select_cols} FROM alerts_raw"

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

            pos_sigma = _estimate_pos_sigma_arcsec(row["snr"], psf_fwhm)
            trail_sigma = _estimate_trail_sigma_arcsec(pos_sigma, trail_length, psf_fwhm)

            mag = float(row["psf_mag"]) if has_mag and row["psf_mag"] is not None else float("nan")
            filt = (
                str(row["filter"]) if has_filter and row["filter"] is not None else default_filter
            )

            det_id = str(row["dia_source_id"])
            rows.append(
                {
                    "id": det_id,
                    "exposure_id": det_id,
                    "mjd_utc": row["mjd"],
                    "night": _mjd_to_night(row["mjd"]),
                    "ra": row["ra"],
                    "dec": row["dec"],
                    "ra_sigma": pos_sigma * _ARCSEC_TO_DEG,
                    "dec_sigma": trail_sigma * _ARCSEC_TO_DEG,
                    "ra_dec_cov": float("nan"),
                    "mag": mag,
                    "mag_sigma": float("nan"),
                    "filter": filt,
                    "observatory_code": observatory_code,
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
    observatory_code: str,
    psf_fwhm: float,
    default_filter: str,
    *,
    sso_only: bool = False,
    mjd_min: float | None = None,
    mjd_max: float | None = None,
) -> list[dict]:
    """Read detections from a pipeline CSV export file.

    Required columns: dia_source_id, mjd, ra, dec.
    Optional columns: snr, has_ss_source, trail_data, psf_mag, filter.

    Args:
        csv_path: Path to the CSV file.
        observatory_code: MPC 3-character code for all detections in this file.
        psf_fwhm: PSF FWHM in arcseconds for error estimation.
        default_filter: Filter name to use when filter column is absent or empty.
        sso_only: Only return rows where has_ss_source is truthy.
        mjd_min: Exclude observations before this MJD.
        mjd_max: Exclude observations after this MJD.

    Returns:
        List of observation dicts ready for write_thor_observations().

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

            pos_sigma = _estimate_pos_sigma_arcsec(snr, psf_fwhm)
            trail_sigma = _estimate_trail_sigma_arcsec(pos_sigma, trail_length, psf_fwhm)

            mag_raw = row.get("psf_mag", "")
            mag = float(mag_raw) if mag_raw else float("nan")

            filt = row.get("filter", "").strip() or default_filter

            det_id = str(int(float(row["dia_source_id"])))
            rows.append(
                {
                    "id": det_id,
                    "exposure_id": det_id,
                    "mjd_utc": mjd,
                    "night": _mjd_to_night(mjd),
                    "ra": float(row["ra"]),
                    "dec": float(row["dec"]),
                    "ra_sigma": pos_sigma * _ARCSEC_TO_DEG,
                    "dec_sigma": trail_sigma * _ARCSEC_TO_DEG,
                    "ra_dec_cov": float("nan"),
                    "mag": mag,
                    "mag_sigma": float("nan"),
                    "filter": filt,
                    "observatory_code": observatory_code,
                }
            )

    rows.sort(key=lambda r: r["mjd_utc"])
    return rows


# ---------------------------------------------------------------------------
# MPC 80-column reader
# ---------------------------------------------------------------------------


def read_mpc80(
    path: Path,
    psf_fwhm: float,
    default_filter: str,
    *,
    mjd_min: float | None = None,
    mjd_max: float | None = None,
) -> list[dict]:
    """Read detections from an MPC 80-column optical observation file.

    Column layout (0-indexed Python slices):
        [15:19]  Year of observation
        [20:22]  Month of observation
        [23:32]  Day of observation (UT, decimal fraction)
        [32:34]  RA hours
        [35:37]  RA minutes
        [38:44]  RA seconds
        [44]     Declination sign (+/-)
        [45:47]  Declination degrees
        [48:50]  Declination arcminutes
        [51:56]  Declination arcseconds
        [65:70]  Magnitude (optional, may be blank)
        [70]     Filter band character (optional)
        [77:80]  Observatory code

    Observatory codes are passed through directly to THOR as the
    observatory_code column; THOR resolves observer positions internally.
    Observations with a blank observatory code are skipped.

    Args:
        path: Path to the MPC80 file.
        psf_fwhm: PSF FWHM in arcseconds (no SNR in MPC80; used only
                  for documentation of the assumed uncertainty).
        default_filter: Filter to use when the band column is blank.
        mjd_min: Exclude observations before this MJD.
        mjd_max: Exclude observations after this MJD.

    Returns:
        List of observation dicts ready for write_thor_observations().

    Raises:
        FileNotFoundError: If path does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"MPC80 file not found: {path}")

    rows = []
    seq = 0

    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        line = line.ljust(80)

        try:
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

        if not obs_code:
            continue  # no observatory code — cannot assign to a site

        mjd = _cal_to_mjd(year, month, day_frac)
        if mjd_min is not None and mjd < mjd_min:
            continue
        if mjd_max is not None and mjd > mjd_max:
            continue

        ra = _ra_hms_to_deg(ra_h, ra_m, ra_s)
        dec = _dec_dms_to_deg(dec_sign, dec_d, dec_m, dec_s)

        # Magnitude and filter (columns 65-70 and 70, optional)
        mag_str = line[65:70].strip()
        band = line[70].strip()
        mag = float(mag_str) if mag_str else float("nan")
        filt = band if band else default_filter

        seq += 1
        rows.append(
            {
                "id": f"mpc{seq:07d}",
                "exposure_id": f"mpc{seq:07d}",
                "mjd_utc": mjd,
                "night": _mjd_to_night(mjd),
                "ra": ra,
                "dec": dec,
                "ra_sigma": DEFAULT_POS_SIGMA_DEG,
                "dec_sigma": DEFAULT_POS_SIGMA_DEG,
                "ra_dec_cov": float("nan"),
                "mag": mag,
                "mag_sigma": float("nan"),
                "filter": filt,
                "observatory_code": obs_code,
            }
        )

    rows.sort(key=lambda r: r["mjd_utc"])
    return rows


# ---------------------------------------------------------------------------
# ADES PSV reader
# ---------------------------------------------------------------------------


def read_ades_psv(
    path: Path,
    psf_fwhm: float,
    default_filter: str,
    *,
    mjd_min: float | None = None,
    mjd_max: float | None = None,
) -> list[dict]:
    """Read detections from an ADES PSV (pipe-separated values) file.

    Required ADES columns: stn, obsTime, ra, dec.
    Optional ADES columns: rmsRA, rmsDec, mag, rmsMag, band, obsID, trkSub.

    Args:
        path: Path to the ADES PSV file.
        psf_fwhm: PSF FWHM in arcseconds (used only when rmsRA/rmsDec absent).
        default_filter: Filter to use when band column is absent or blank.
        mjd_min: Exclude observations before this MJD.
        mjd_max: Exclude observations after this MJD.

    Returns:
        List of observation dicts ready for write_thor_observations().

    Raises:
        FileNotFoundError: If path does not exist.
        KeyError: If required ADES columns are absent.
    """
    if not path.exists():
        raise FileNotFoundError(f"ADES PSV file not found: {path}")

    rows = []
    header: list[str] | None = None
    required = {"stn", "obsTime", "ra", "dec"}
    seq = 0

    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
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
        if not obs_code:
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

        # Positional uncertainties: use ADES rmsRA/rmsDec directly (arcsec->deg)
        rms_ra = record.get("rmsRA", "").strip()
        rms_dec = record.get("rmsDec", "").strip()
        if rms_ra and rms_dec:
            try:
                ra_sigma = float(rms_ra) * _ARCSEC_TO_DEG
                dec_sigma = float(rms_dec) * _ARCSEC_TO_DEG
            except ValueError:
                ra_sigma = dec_sigma = DEFAULT_POS_SIGMA_DEG
        else:
            ra_sigma = dec_sigma = DEFAULT_POS_SIGMA_DEG

        # Magnitude
        mag_str = record.get("mag", "").strip()
        rms_mag_str = record.get("rmsMag", "").strip()
        mag = float(mag_str) if mag_str else float("nan")
        mag_sigma = float(rms_mag_str) if rms_mag_str else float("nan")

        # Filter
        band = record.get("band", "").strip()
        filt = band if band else default_filter

        # Observation ID
        obs_id = (record.get("obsID") or record.get("trkSub") or "").strip()
        seq += 1
        det_id = obs_id if obs_id else f"ades{seq:07d}"
        det_id = det_id.replace(" ", "_").replace(",", "_")[:31]

        rows.append(
            {
                "id": det_id,
                "exposure_id": det_id,
                "mjd_utc": mjd,
                "night": _mjd_to_night(mjd),
                "ra": ra,
                "dec": dec,
                "ra_sigma": ra_sigma,
                "dec_sigma": dec_sigma,
                "ra_dec_cov": float("nan"),
                "mag": mag,
                "mag_sigma": mag_sigma,
                "filter": filt,
                "observatory_code": obs_code,
            }
        )

    if header is None:
        raise KeyError("No column header line found in ADES PSV file.")

    rows.sort(key=lambda r: r["mjd_utc"])
    return rows


# ---------------------------------------------------------------------------
# THOR InputObservations writer
# ---------------------------------------------------------------------------

_THOR_COLUMNS = [
    "id",
    "exposure_id",
    "mjd_utc",
    "night",
    "ra",
    "dec",
    "ra_sigma",
    "dec_sigma",
    "ra_dec_cov",
    "mag",
    "mag_sigma",
    "filter",
    "observatory_code",
]

_THOR_DTYPES: dict[str, str] = {
    "id": "string",
    "exposure_id": "string",
    "mjd_utc": "float64",
    "night": "Int64",  # nullable integer
    "ra": "float64",
    "dec": "float64",
    "ra_sigma": "float64",
    "dec_sigma": "float64",
    "ra_dec_cov": "float64",
    "mag": "float64",
    "mag_sigma": "float64",
    "filter": "string",
    "observatory_code": "string",
}


def write_thor_observations(rows: list[dict], output_path: Path, fmt: str = "parquet") -> int:
    """Write observation records to a THOR InputObservations-compatible file.

    Args:
        rows: List of observation dicts (keys: id, exposure_id, mjd_utc, night,
              ra, dec, ra_sigma, dec_sigma, ra_dec_cov, mag, mag_sigma,
              filter, observatory_code).
        output_path: Destination file path.
        fmt: Output format — "parquet" (default) or "csv".

    Returns:
        Number of observations written.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(rows, columns=_THOR_COLUMNS)
    df = df.astype(_THOR_DTYPES)

    if fmt == "parquet":
        df.to_parquet(output_path, index=False)
    elif fmt == "csv":
        df.to_csv(output_path, index=False)
    else:
        raise ValueError(f"Unsupported output format: {fmt!r}. Use 'parquet' or 'csv'.")

    return len(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export astrometric detections to THOR InputObservations format.",
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
    parser.add_argument("-o", "--output", metavar="PATH", type=Path, help="Output file path")
    parser.add_argument(
        "--format",
        choices=["parquet", "csv"],
        default="parquet",
        help="Output format (default: parquet)",
    )

    # Observatory
    obs_grp = parser.add_argument_group("observatory")
    obs_grp.add_argument(
        "--observatory",
        metavar="CODE",
        help=(
            "MPC 3-character observatory code for pipeline input (--db / --csv). "
            "Not needed for --mpc80 / --ades (codes embedded per observation)."
        ),
    )

    # Error estimation
    err_grp = parser.add_argument_group("astrometric errors")
    err_grp.add_argument(
        "--psf-fwhm",
        metavar="ARCSEC",
        type=float,
        default=DEFAULT_PSF_FWHM_ARCSEC,
        help=f"PSF FWHM in arcseconds for SNR-based error estimation (default: {DEFAULT_PSF_FWHM_ARCSEC})",
    )
    err_grp.add_argument(
        "--default-sigma",
        metavar="ARCSEC",
        type=float,
        default=DEFAULT_POS_SIGMA_ARCSEC,
        help=f"Fallback positional uncertainty in arcseconds when SNR and rmsRA are unavailable (default: {DEFAULT_POS_SIGMA_ARCSEC})",
    )

    # Filters (pipeline inputs only)
    filt_grp = parser.add_argument_group("filters (pipeline inputs only)")
    filt_grp.add_argument(
        "--sso-only",
        action="store_true",
        help="Include only SSO-associated alerts (has_ss_source = 1)",
    )
    filt_grp.add_argument(
        "--filtered-only",
        action="store_true",
        help="Include only alerts present in alerts_filtered table (--db only)",
    )
    filt_grp.add_argument(
        "--mjd-min",
        metavar="MJD",
        type=float,
        help="Exclude observations before this MJD",
    )
    filt_grp.add_argument(
        "--mjd-max",
        metavar="MJD",
        type=float,
        help="Exclude observations after this MJD",
    )

    # Photometry
    phot_grp = parser.add_argument_group("photometry")
    phot_grp.add_argument(
        "--default-filter",
        metavar="FILTER",
        default=DEFAULT_FILTER,
        help=f"Filter name to use when unavailable in the source data (default: {DEFAULT_FILTER!r})",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Determine effective defaults for errors
    default_sigma_deg = args.default_sigma * _ARCSEC_TO_DEG

    # Validate: pipeline inputs require --observatory
    if (args.db or args.csv) and not args.observatory:
        parser.error("--observatory CODE is required when using --db or --csv")

    # Determine output path and format
    output = args.output
    if output is None:
        stem = "thor_observations"
        ext = ".parquet" if args.format == "parquet" else ".csv"
        output = Path(stem + ext)

    # Read observations
    rows: list[dict]
    if args.db:
        rows = read_from_sqlite(
            args.db,
            args.observatory,
            args.psf_fwhm,
            args.default_filter,
            sso_only=args.sso_only,
            filtered_only=args.filtered_only,
            mjd_min=args.mjd_min,
            mjd_max=args.mjd_max,
        )
    elif args.csv:
        rows = read_from_csv(
            args.csv,
            args.observatory,
            args.psf_fwhm,
            args.default_filter,
            sso_only=args.sso_only,
            mjd_min=args.mjd_min,
            mjd_max=args.mjd_max,
        )
    elif args.mpc80:
        rows = read_mpc80(
            args.mpc80,
            args.psf_fwhm,
            args.default_filter,
            mjd_min=args.mjd_min,
            mjd_max=args.mjd_max,
        )
    elif args.ades:
        rows = read_ades_psv(
            args.ades,
            args.psf_fwhm,
            args.default_filter,
            mjd_min=args.mjd_min,
            mjd_max=args.mjd_max,
        )
    else:
        parser.error("Specify an input source: --db, --csv, --mpc80, or --ades")

    # Apply custom --default-sigma override (replaces the compiled-in default
    # wherever it was used as a fallback)
    if args.default_sigma != DEFAULT_POS_SIGMA_ARCSEC:
        for row in rows:
            if row["ra_sigma"] == DEFAULT_POS_SIGMA_DEG:
                row["ra_sigma"] = default_sigma_deg
            if row["dec_sigma"] == DEFAULT_POS_SIGMA_DEG:
                row["dec_sigma"] = default_sigma_deg

    n = write_thor_observations(rows, output, fmt=args.format)
    print(f"Wrote {n} observations to {output} ({args.format})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
