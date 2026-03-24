"""
Tests for scripts/export_to_pumalink.py.

Covers utility functions, file format readers, TRD9 writer, and
the observatory loader using synthetic fixture data.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the standalone script via importlib (not in src/)
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "export_to_pumalink.py"
_spec = importlib.util.spec_from_file_location("export_to_pumalink", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
# Must register in sys.modules before exec so dataclasses can resolve __module__
sys.modules["export_to_pumalink"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

Observatory = _mod.Observatory
DEFAULT_XERR_ARCSEC = _mod.DEFAULT_XERR_ARCSEC
_WGS84_A = _mod._WGS84_A

_geocentric_to_geodetic = _mod._geocentric_to_geodetic
_cal_to_mjd = _mod._cal_to_mjd
_ra_hms_to_deg = _mod._ra_hms_to_deg
_dec_dms_to_deg = _mod._dec_dms_to_deg
_iso_to_mjd = _mod._iso_to_mjd
_estimate_xerr = _mod._estimate_xerr
_estimate_terr = _mod._estimate_terr
load_observatories = _mod.load_observatories
read_from_csv = _mod.read_from_csv
read_from_sqlite = _mod.read_from_sqlite
read_mpc80 = _mod.read_mpc80
read_ades_psv = _mod.read_ades_psv
write_trd9 = _mod.write_trd9

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

# Minimal MPC ObsCodes in fixed-width format.
# Column layout (0-indexed): [0:3]=code, [3:12]=lng, [12:21]=cos, [21:30]=sin, [30:]=name
_OBSCODES_TEXT = (
    "Code  Long.   cos      sin    Name\n"
    "X05 289.267  0.864749-0.500892Cerro Pachon\n"
    "I41 243.141  0.836800+0.545819Palomar Mountain\n"
    # Space-based: cos/sin blank → should be skipped
    "XSP   0.000                   Space telescope\n"
)

# MPC 80-column observation line (exactly 80 chars):
#   year=2024, month=01, day=15.500000  → MJD 60324.5
#   RA=10h23m45.670s, Dec=+12°34'56.70", obs=X05
_MPC80_LINE = (
    "               "  # [0:15]  designation / blank
    "2024"  # [15:19] year
    " "  # [19]
    "01"  # [20:22] month
    " "  # [22]
    "15.500000"  # [23:32] day fraction (9 chars)
    "10"  # [32:34] RA h
    " "  # [34]
    "23"  # [35:37] RA m
    " "  # [37]
    "45.670"  # [38:44] RA s (6 chars)
    "+"  # [44]    dec sign
    "12"  # [45:47] dec d
    " "  # [47]
    "34"  # [48:50] dec m
    " "  # [50]
    "56.70"  # [51:56] dec s (5 chars)
    "                     "  # [56:77] mag / filter / blank (21 chars)
    "X05"  # [77:80] obs code
)
assert len(_MPC80_LINE) == 80

# Expected values for the MPC80 line above
_MPC80_EXPECTED_MJD = 60324.5
_MPC80_EXPECTED_RA = (10 + 23 / 60 + 45.670 / 3600) * 15  # ≈ 155.940°
_MPC80_EXPECTED_DEC = 12 + 34 / 60 + 56.70 / 3600  # ≈ 12.582°

# ADES PSV with rmsRA/rmsDec columns
_ADES_WITH_RMS = (
    "# version ADES 2017\n"
    "| stn | obsTime | ra | dec | rmsRA | rmsDec | obsID |\n"
    "| X05 | 2024-01-15T12:00:00Z | 155.940 | 12.582 | 0.15 | 0.20 | test001 |\n"
    "| I41 | 2024-01-15T18:00:00Z | 210.500 | -5.300 | 0.18 | 0.25 | test002 |\n"
    "| ZZZ | 2024-01-15T20:00:00Z | 100.000 | 10.000 | 0.20 | 0.20 | skip001 |\n"
)

# ADES PSV without rmsRA/rmsDec (fallback to DEFAULT_XERR)
_ADES_NO_RMS = (
    "# version ADES 2017\n"
    "| stn | obsTime | ra | dec |\n"
    "| X05 | 2024-01-15T12:00:00Z | 155.940 | 12.582 |\n"
)

# Pipeline CSV (columns: dia_source_id, mjd, ra, dec, snr, has_ss_source, trail_data)
_CSV_CONTENT = (
    "dia_source_id,mjd,ra,dec,snr,has_ss_source,trail_data\n"
    '1,60000.0,150.0,10.0,20.0,1,"{}"\n'
    '2,60001.0,151.0,11.0,50.0,0,"{}"\n'
    '3,60002.0,152.0,12.0,,1,"{}"\n'  # no SNR → DEFAULT_XERR
    '4,60003.0,153.0,13.0,30.0,1,"{""trailLength"": 3.0}"\n'
)


@pytest.fixture
def obscode_file(tmp_path: Path) -> Path:
    p = tmp_path / "ObsCodes.dat"
    p.write_text(_OBSCODES_TEXT)
    return p


@pytest.fixture
def observatories(obscode_file: Path) -> dict:
    return load_observatories(obscode_file)


@pytest.fixture
def x05(observatories: dict) -> Observatory:
    return observatories["X05"]


@pytest.fixture
def mpc80_file(tmp_path: Path) -> Path:
    p = tmp_path / "obs.mpc"
    p.write_text(_MPC80_LINE + "\n")
    return p


@pytest.fixture
def ades_file_with_rms(tmp_path: Path) -> Path:
    p = tmp_path / "obs.psv"
    p.write_text(_ADES_WITH_RMS)
    return p


@pytest.fixture
def ades_file_no_rms(tmp_path: Path) -> Path:
    p = tmp_path / "obs_norms.psv"
    p.write_text(_ADES_NO_RMS)
    return p


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    p = tmp_path / "alerts.csv"
    p.write_text(_CSV_CONTENT)
    return p


@pytest.fixture
def sqlite_db(tmp_path: Path) -> Path:
    """Minimal SQLite DB matching the pipeline alerts_raw schema."""
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE alerts_raw (
            id INTEGER PRIMARY KEY,
            dia_source_id TEXT,
            mjd REAL,
            ra REAL,
            dec REAL,
            snr REAL,
            trail_data TEXT,
            has_ss_source INTEGER DEFAULT 0
        )
        """
    )
    rows = [
        (1, "det001", 60000.0, 150.0, 10.0, 20.0, "{}", 1),
        (2, "det002", 60001.0, 151.0, 11.0, 50.0, '{"trailLength": 3.0}', 0),
        (3, "det003", 60002.0, 152.0, 12.0, None, "{}", 1),
    ]
    conn.executemany("INSERT INTO alerts_raw VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    return db


# ---------------------------------------------------------------------------
# _geocentric_to_geodetic
# ---------------------------------------------------------------------------


class TestGeocentricToGeodetic:
    def test_equatorial_point(self):
        lat, elev = _geocentric_to_geodetic(1.0, 0.0)
        assert lat == pytest.approx(0.0, abs=1e-6)
        assert elev == pytest.approx(0.0, abs=1.0)  # within 1 m

    def test_both_zero(self):
        lat, elev = _geocentric_to_geodetic(0.0, 0.0)
        assert lat == 0.0
        assert elev == 0.0

    def test_southern_hemisphere(self):
        # Cerro Pachon is southern → negative geodetic lat
        lat, elev = _geocentric_to_geodetic(0.864749, -0.500892)
        assert lat < 0
        assert -35 < lat < -25  # southern Chile, roughly
        assert 1000 < elev < 5000  # high-altitude site

    def test_northern_hemisphere(self):
        # Palomar is northern → positive geodetic lat
        lat, elev = _geocentric_to_geodetic(0.836800, 0.545819)
        assert lat > 0
        assert 30 < lat < 40  # southern California
        assert 0 < elev < 3000


# ---------------------------------------------------------------------------
# _cal_to_mjd
# ---------------------------------------------------------------------------


class TestCalToMjd:
    def test_j2000(self):
        # J2000.0: 2000-01-01T12:00:00 UTC = MJD 51544.5
        assert _cal_to_mjd(2000, 1, 1.5) == pytest.approx(51544.5)

    def test_recent_date(self):
        # 2024-01-15 noon = MJD 60324.5 (verified via standard converter)
        assert _cal_to_mjd(2024, 1, 15.5) == pytest.approx(60324.5)

    def test_fractional_day(self):
        # Day fraction should add directly to MJD
        mjd_noon = _cal_to_mjd(2024, 6, 15.5)
        mjd_midnight = _cal_to_mjd(2024, 6, 15.0)
        assert mjd_noon - mjd_midnight == pytest.approx(0.5)

    def test_month_boundary(self):
        # Months ≤ 2 trigger year rollback in the algorithm
        mjd_jan = _cal_to_mjd(2024, 1, 1.0)
        mjd_feb = _cal_to_mjd(2024, 2, 1.0)
        mjd_mar = _cal_to_mjd(2024, 3, 1.0)
        assert mjd_feb > mjd_jan
        assert mjd_mar > mjd_feb


# ---------------------------------------------------------------------------
# _ra_hms_to_deg
# ---------------------------------------------------------------------------


class TestRaHmsToDeg:
    def test_zero(self):
        assert _ra_hms_to_deg(0, 0, 0) == pytest.approx(0.0)

    def test_12_hours(self):
        assert _ra_hms_to_deg(12, 0, 0) == pytest.approx(180.0)

    def test_one_hour(self):
        assert _ra_hms_to_deg(1, 0, 0) == pytest.approx(15.0)

    def test_fractional(self):
        # 10h 23m 45.670s
        expected = (10 + 23 / 60 + 45.670 / 3600) * 15
        assert _ra_hms_to_deg(10, 23, 45.670) == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------------------
# _dec_dms_to_deg
# ---------------------------------------------------------------------------


class TestDecDmsToDeg:
    def test_positive(self):
        assert _dec_dms_to_deg("+", 90, 0, 0) == pytest.approx(90.0)

    def test_negative(self):
        assert _dec_dms_to_deg("-", 90, 0, 0) == pytest.approx(-90.0)

    def test_zero(self):
        assert _dec_dms_to_deg("+", 0, 0, 0) == pytest.approx(0.0)

    def test_mixed(self):
        # +12° 34' 56.70"
        expected = 12 + 34 / 60 + 56.70 / 3600
        assert _dec_dms_to_deg("+", 12, 34, 56.70) == pytest.approx(expected, rel=1e-6)

    def test_negative_mixed(self):
        expected = -(12 + 34 / 60 + 56.70 / 3600)
        assert _dec_dms_to_deg("-", 12, 34, 56.70) == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------------------
# _iso_to_mjd
# ---------------------------------------------------------------------------


class TestIsoToMjd:
    def test_j2000(self):
        # J2000.0: 2000-01-01T12:00:00Z = MJD 51544.5
        assert _iso_to_mjd("2000-01-01T12:00:00Z") == pytest.approx(51544.5)

    def test_no_z_suffix(self):
        assert _iso_to_mjd("2000-01-01T12:00:00") == pytest.approx(51544.5)

    def test_fractional_seconds(self):
        assert _iso_to_mjd("2000-01-01T12:00:00.000Z") == pytest.approx(51544.5)

    def test_agrees_with_cal_to_mjd(self):
        # 2024-01-15 noon should agree between both conversion functions
        mjd_cal = _cal_to_mjd(2024, 1, 15.5)
        mjd_iso = _iso_to_mjd("2024-01-15T12:00:00Z")
        assert mjd_cal == pytest.approx(mjd_iso, abs=1e-6)


# ---------------------------------------------------------------------------
# _estimate_xerr
# ---------------------------------------------------------------------------


class TestEstimateXerr:
    def test_with_snr(self):
        xerr = _estimate_xerr(snr=10.0, psf_fwhm=1.0)
        assert xerr == pytest.approx(0.1)

    def test_fallback_none_snr(self):
        assert _estimate_xerr(snr=None, psf_fwhm=1.0) == DEFAULT_XERR_ARCSEC

    def test_fallback_zero_snr(self):
        assert _estimate_xerr(snr=0.0, psf_fwhm=1.0) == DEFAULT_XERR_ARCSEC

    def test_larger_fwhm(self):
        xerr = _estimate_xerr(snr=10.0, psf_fwhm=2.0)
        assert xerr == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# _estimate_terr
# ---------------------------------------------------------------------------


class TestEstimateTerr:
    def test_no_trail(self):
        # Symmetric PSF: terr == xerr
        assert _estimate_terr(0.2, trail_length=None, psf_fwhm=1.0) == pytest.approx(0.2)

    def test_zero_trail(self):
        assert _estimate_terr(0.2, trail_length=0.0, psf_fwhm=1.0) == pytest.approx(0.2)

    def test_with_trail(self):
        # terr > xerr for trailed detection
        terr = _estimate_terr(0.2, trail_length=3.0, psf_fwhm=1.0)
        assert terr > 0.2

    def test_trail_formula(self):
        # terr = xerr * sqrt(sqrt(fwhm^2 + trail^2) / fwhm)
        import math

        xerr, trail, fwhm = 0.2, 3.0, 1.0
        major = math.sqrt(fwhm**2 + trail**2)
        expected = xerr * math.sqrt(major / fwhm)
        assert _estimate_terr(xerr, trail, fwhm) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# load_observatories
# ---------------------------------------------------------------------------


class TestLoadObservatories:
    def test_loads_known_codes(self, obscode_file):
        obs = load_observatories(obscode_file)
        assert "X05" in obs
        assert "I41" in obs

    def test_skips_space_based(self, obscode_file):
        # XSP has blank cos/sin → skipped
        obs = load_observatories(obscode_file)
        assert "XSP" not in obs

    def test_observatory_fields(self, obscode_file):
        obs = load_observatories(obscode_file)
        x05 = obs["X05"]
        assert x05.code == "X05"
        assert x05.name == "Cerro Pachon"
        # Longitude 289.267° East → converted to -70.733°
        assert x05.lng == pytest.approx(-70.733, abs=0.01)
        # Southern hemisphere
        assert x05.lat < 0

    def test_northern_observatory(self, obscode_file):
        obs = load_observatories(obscode_file)
        i41 = obs["I41"]
        assert i41.lat > 0  # northern hemisphere

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_observatories(tmp_path / "nonexistent.dat")

    def test_html_variant_parsed(self, tmp_path):
        # HTML tags are stripped before parsing
        html = (
            "<html><pre>\n"
            "Code  Long.   cos      sin    Name\n"
            "X05 289.267  0.864749-0.500892Cerro Pachon\n"
            "</pre></html>\n"
        )
        p = tmp_path / "ObsCodes.html"
        p.write_text(html)
        obs = load_observatories(p)
        assert "X05" in obs

    def test_skips_header_line(self, obscode_file):
        obs = load_observatories(obscode_file)
        # "Code" is the header → should not appear as an observatory code
        assert "Cod" not in obs


# ---------------------------------------------------------------------------
# read_from_csv
# ---------------------------------------------------------------------------


class TestReadFromCsv:
    def test_basic(self, csv_file, x05):
        rows = read_from_csv(csv_file, x05, psf_fwhm=1.0)
        assert len(rows) == 4

    def test_required_fields_present(self, csv_file, x05):
        rows = read_from_csv(csv_file, x05, psf_fwhm=1.0)
        for row in rows:
            for field in ("mjd", "ra", "dec", "xerr", "terr", "lng", "lat", "elev", "id"):
                assert field in row

    def test_observatory_coordinates_used(self, csv_file, x05):
        rows = read_from_csv(csv_file, x05, psf_fwhm=1.0)
        for row in rows:
            assert row["lng"] == x05.lng
            assert row["lat"] == x05.lat
            assert row["elev"] == x05.elev

    def test_sso_only_filter(self, csv_file, x05):
        all_rows = read_from_csv(csv_file, x05, psf_fwhm=1.0)
        sso_rows = read_from_csv(csv_file, x05, psf_fwhm=1.0, sso_only=True)
        assert len(sso_rows) < len(all_rows)
        assert len(sso_rows) == 3  # rows 1, 3, 4 have has_ss_source=1

    def test_mjd_min_filter(self, csv_file, x05):
        rows = read_from_csv(csv_file, x05, psf_fwhm=1.0, mjd_min=60001.0)
        assert all(r["mjd"] >= 60001.0 for r in rows)
        assert len(rows) == 3

    def test_mjd_max_filter(self, csv_file, x05):
        rows = read_from_csv(csv_file, x05, psf_fwhm=1.0, mjd_max=60001.0)
        assert all(r["mjd"] <= 60001.0 for r in rows)
        assert len(rows) == 2

    def test_missing_file_raises(self, tmp_path, x05):
        with pytest.raises(FileNotFoundError):
            read_from_csv(tmp_path / "missing.csv", x05, psf_fwhm=1.0)

    def test_missing_columns_raises(self, tmp_path, x05):
        bad = tmp_path / "bad.csv"
        bad.write_text("col_a,col_b\n1,2\n")
        with pytest.raises(KeyError, match="required columns"):
            read_from_csv(bad, x05, psf_fwhm=1.0)

    def test_fallback_xerr_when_no_snr(self, csv_file, x05):
        rows = read_from_csv(csv_file, x05, psf_fwhm=1.0)
        # Row 3 has no SNR → should use DEFAULT_XERR
        no_snr_row = next(r for r in rows if r["mjd"] == 60002.0)
        assert no_snr_row["xerr"] == pytest.approx(DEFAULT_XERR_ARCSEC)

    def test_sorted_by_mjd(self, csv_file, x05):
        rows = read_from_csv(csv_file, x05, psf_fwhm=1.0)
        mjds = [r["mjd"] for r in rows]
        assert mjds == sorted(mjds)


# ---------------------------------------------------------------------------
# read_mpc80
# ---------------------------------------------------------------------------


class TestReadMpc80:
    def test_basic(self, mpc80_file, observatories):
        rows = read_mpc80(mpc80_file, observatories, psf_fwhm=1.0)
        assert len(rows) == 1

    def test_coordinates(self, mpc80_file, observatories):
        rows = read_mpc80(mpc80_file, observatories, psf_fwhm=1.0)
        row = rows[0]
        assert row["ra"] == pytest.approx(_MPC80_EXPECTED_RA, abs=0.001)
        assert row["dec"] == pytest.approx(_MPC80_EXPECTED_DEC, abs=0.001)

    def test_mjd(self, mpc80_file, observatories):
        rows = read_mpc80(mpc80_file, observatories, psf_fwhm=1.0)
        assert rows[0]["mjd"] == pytest.approx(_MPC80_EXPECTED_MJD)

    def test_default_xerr(self, mpc80_file, observatories):
        # MPC80 has no SNR → default error
        rows = read_mpc80(mpc80_file, observatories, psf_fwhm=1.0)
        assert rows[0]["xerr"] == pytest.approx(DEFAULT_XERR_ARCSEC)
        assert rows[0]["terr"] == pytest.approx(DEFAULT_XERR_ARCSEC)

    def test_unknown_obs_code_skipped(self, tmp_path, observatories):
        # Replace obs code with unknown "ZZZ"
        bad_line = _MPC80_LINE[:77] + "ZZZ"
        p = tmp_path / "unknown.mpc"
        p.write_text(bad_line + "\n")
        rows = read_mpc80(p, observatories, psf_fwhm=1.0)
        assert rows == []

    def test_blank_and_comment_lines_skipped(self, tmp_path, observatories):
        p = tmp_path / "commented.mpc"
        p.write_text("# comment\n\n" + _MPC80_LINE + "\n")
        rows = read_mpc80(p, observatories, psf_fwhm=1.0)
        assert len(rows) == 1

    def test_mjd_min_filter(self, tmp_path, observatories):
        p = tmp_path / "obs.mpc"
        p.write_text(_MPC80_LINE + "\n")
        rows = read_mpc80(p, observatories, psf_fwhm=1.0, mjd_min=_MPC80_EXPECTED_MJD + 1)
        assert rows == []

    def test_missing_file_raises(self, tmp_path, observatories):
        with pytest.raises(FileNotFoundError):
            read_mpc80(tmp_path / "missing.mpc", observatories, psf_fwhm=1.0)

    def test_sequential_ids(self, tmp_path, observatories):
        # Two observations → IDs mpc0000001 and mpc0000002
        p = tmp_path / "two.mpc"
        p.write_text(_MPC80_LINE + "\n" + _MPC80_LINE + "\n")
        rows = read_mpc80(p, observatories, psf_fwhm=1.0)
        assert len(rows) == 2
        ids = {r["id"] for r in rows}
        assert len(ids) == 2  # distinct IDs


# ---------------------------------------------------------------------------
# read_ades_psv
# ---------------------------------------------------------------------------


class TestReadAdesPsv:
    def test_basic(self, ades_file_with_rms, observatories):
        rows = read_ades_psv(ades_file_with_rms, observatories, psf_fwhm=1.0)
        # ZZZ is unknown → 2 valid rows
        assert len(rows) == 2

    def test_rms_fields_used(self, ades_file_with_rms, observatories):
        rows = read_ades_psv(ades_file_with_rms, observatories, psf_fwhm=1.0)
        x05_row = next(r for r in rows if r["lng"] == pytest.approx(observatories["X05"].lng))
        assert x05_row["xerr"] == pytest.approx(0.15)
        assert x05_row["terr"] == pytest.approx(0.20)

    def test_obs_id_used_as_id(self, ades_file_with_rms, observatories):
        rows = read_ades_psv(ades_file_with_rms, observatories, psf_fwhm=1.0)
        ids = {r["id"] for r in rows}
        assert "test001" in ids
        assert "test002" in ids

    def test_fallback_default_xerr_when_no_rms(self, ades_file_no_rms, observatories):
        rows = read_ades_psv(ades_file_no_rms, observatories, psf_fwhm=1.0)
        assert len(rows) == 1
        assert rows[0]["xerr"] == pytest.approx(DEFAULT_XERR_ARCSEC)
        assert rows[0]["terr"] == pytest.approx(DEFAULT_XERR_ARCSEC)

    def test_mjd_filter(self, ades_file_with_rms, observatories):
        rows = read_ades_psv(
            ades_file_with_rms,
            observatories,
            psf_fwhm=1.0,
            mjd_max=_iso_to_mjd("2024-01-15T12:00:00Z"),
        )
        assert len(rows) == 1

    def test_missing_file_raises(self, tmp_path, observatories):
        with pytest.raises(FileNotFoundError):
            read_ades_psv(tmp_path / "missing.psv", observatories, psf_fwhm=1.0)

    def test_missing_required_columns_raises(self, tmp_path, observatories):
        bad = tmp_path / "bad.psv"
        bad.write_text("| stn | ra |\n| X05 | 10.0 |\n")
        with pytest.raises(KeyError, match="required columns"):
            read_ades_psv(bad, observatories, psf_fwhm=1.0)

    def test_no_header_raises(self, tmp_path, observatories):
        # Only comment lines, no header → KeyError
        no_header = tmp_path / "noheader.psv"
        no_header.write_text("# comment\n")
        with pytest.raises(KeyError):
            read_ades_psv(no_header, observatories, psf_fwhm=1.0)


# ---------------------------------------------------------------------------
# read_from_sqlite
# ---------------------------------------------------------------------------


class TestReadFromSqlite:
    def test_basic(self, sqlite_db, x05):
        rows = read_from_sqlite(sqlite_db, x05, psf_fwhm=1.0)
        assert len(rows) == 3

    def test_required_fields_present(self, sqlite_db, x05):
        rows = read_from_sqlite(sqlite_db, x05, psf_fwhm=1.0)
        for row in rows:
            for field in ("mjd", "ra", "dec", "xerr", "terr", "lng", "lat", "elev", "id"):
                assert field in row

    def test_sso_only(self, sqlite_db, x05):
        rows = read_from_sqlite(sqlite_db, x05, psf_fwhm=1.0, sso_only=True)
        # rows 1 and 3 have has_ss_source=1
        assert len(rows) == 2

    def test_mjd_min_filter(self, sqlite_db, x05):
        rows = read_from_sqlite(sqlite_db, x05, psf_fwhm=1.0, mjd_min=60001.0)
        assert all(r["mjd"] >= 60001.0 for r in rows)
        assert len(rows) == 2

    def test_trail_data_increases_terr(self, sqlite_db, x05):
        rows = read_from_sqlite(sqlite_db, x05, psf_fwhm=1.0)
        # Row 2 has trailLength=3.0 → terr should exceed xerr for that row
        trailed = next(r for r in rows if r["mjd"] == 60001.0)
        assert trailed["terr"] > trailed["xerr"]

    def test_null_snr_uses_default(self, sqlite_db, x05):
        rows = read_from_sqlite(sqlite_db, x05, psf_fwhm=1.0)
        no_snr = next(r for r in rows if r["mjd"] == 60002.0)
        assert no_snr["xerr"] == pytest.approx(DEFAULT_XERR_ARCSEC)

    def test_missing_db_raises(self, tmp_path, x05):
        with pytest.raises(FileNotFoundError):
            read_from_sqlite(tmp_path / "missing.db", x05, psf_fwhm=1.0)

    def test_sorted_by_mjd(self, sqlite_db, x05):
        rows = read_from_sqlite(sqlite_db, x05, psf_fwhm=1.0)
        mjds = [r["mjd"] for r in rows]
        assert mjds == sorted(mjds)


# ---------------------------------------------------------------------------
# write_trd9
# ---------------------------------------------------------------------------


class TestWriteTrd9:
    def _make_row(self, mjd=60000.0, ra=150.0, dec=-30.0, obs_code="X05") -> dict:
        return {
            "mjd": mjd,
            "ra": ra,
            "dec": dec,
            "xerr": 0.2,
            "terr": 0.2,
            "lng": -70.73,
            "lat": -30.24,
            "elev": 2662.0,
            "id": obs_code + "det001",
        }

    def test_returns_count(self, tmp_path):
        rows = [self._make_row(60000.0 + i) for i in range(5)]
        n = write_trd9(rows, tmp_path / "out.trd")
        assert n == 5

    def test_creates_file(self, tmp_path):
        rows = [self._make_row()]
        write_trd9(rows, tmp_path / "out.trd")
        assert (tmp_path / "out.trd").exists()

    def test_creates_parent_dirs(self, tmp_path):
        rows = [self._make_row()]
        out = tmp_path / "nested" / "dir" / "out.trd"
        write_trd9(rows, out)
        assert out.exists()

    def test_header_comment(self, tmp_path):
        rows = [self._make_row()]
        out = tmp_path / "out.trd"
        write_trd9(rows, out)
        text = out.read_text()
        assert text.startswith("#")

    def test_nine_fields_per_data_line(self, tmp_path):
        rows = [self._make_row()]
        out = tmp_path / "out.trd"
        write_trd9(rows, out)
        data_lines = [ln for ln in out.read_text().splitlines() if not ln.startswith("#")]
        assert len(data_lines) == 1
        fields = data_lines[0].split()
        assert len(fields) == 9

    def test_field_order_and_values(self, tmp_path):
        row = self._make_row(mjd=60000.5, ra=150.123456, dec=-30.654321)
        out = tmp_path / "out.trd"
        write_trd9([row], out)
        data_lines = [ln for ln in out.read_text().splitlines() if not ln.startswith("#")]
        fields = data_lines[0].split()
        assert float(fields[0]) == pytest.approx(60000.5)
        assert float(fields[1]) == pytest.approx(150.123456)
        assert float(fields[2]) == pytest.approx(-30.654321)
        assert float(fields[3]) == pytest.approx(0.2)
        assert float(fields[4]) == pytest.approx(0.2)

    def test_empty_rows(self, tmp_path):
        out = tmp_path / "out.trd"
        n = write_trd9([], out)
        assert n == 0
        assert out.exists()
        data_lines = [ln for ln in out.read_text().splitlines() if not ln.startswith("#")]
        assert data_lines == []

    def test_id_preserved(self, tmp_path):
        row = self._make_row()
        row["id"] = "mydet_12345"
        out = tmp_path / "out.trd"
        write_trd9([row], out)
        data_lines = [ln for ln in out.read_text().splitlines() if not ln.startswith("#")]
        assert data_lines[0].split()[-1] == "mydet_12345"
