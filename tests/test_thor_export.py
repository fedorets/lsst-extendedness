"""
Tests for scripts/export_to_thor.py.

Covers utility functions, file format readers, the Parquet/CSV writer, and
THOR-specific features: night calculation, magnitude/filter columns,
ra_sigma/dec_sigma in degrees, and output schema correctness.
"""

from __future__ import annotations

import importlib.util
import math
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Import the standalone script via importlib (not in src/)
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "export_to_thor.py"
_spec = importlib.util.spec_from_file_location("export_to_thor", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules["export_to_thor"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

DEFAULT_POS_SIGMA_ARCSEC = _mod.DEFAULT_POS_SIGMA_ARCSEC
DEFAULT_POS_SIGMA_DEG = _mod.DEFAULT_POS_SIGMA_DEG
DEFAULT_FILTER = _mod.DEFAULT_FILTER
_ARCSEC_TO_DEG = _mod._ARCSEC_TO_DEG
_THOR_COLUMNS = _mod._THOR_COLUMNS

_cal_to_mjd = _mod._cal_to_mjd
_ra_hms_to_deg = _mod._ra_hms_to_deg
_dec_dms_to_deg = _mod._dec_dms_to_deg
_iso_to_mjd = _mod._iso_to_mjd
_mjd_to_night = _mod._mjd_to_night
_estimate_pos_sigma_arcsec = _mod._estimate_pos_sigma_arcsec
_estimate_trail_sigma_arcsec = _mod._estimate_trail_sigma_arcsec
read_from_sqlite = _mod.read_from_sqlite
read_from_csv = _mod.read_from_csv
read_mpc80 = _mod.read_mpc80
read_ades_psv = _mod.read_ades_psv
write_thor_observations = _mod.write_thor_observations

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

# Pipeline CSV with optional mag and filter columns
_CSV_CONTENT = (
    "dia_source_id,mjd,ra,dec,snr,has_ss_source,trail_data,psf_mag,filter\n"
    '1,60000.0,150.0,10.0,20.0,1,"{}",18.5,r\n'
    '2,60001.0,151.0,11.0,50.0,0,"{}",19.2,g\n'
    '3,60002.0,152.0,12.0,,1,"{}","",""\n'  # no SNR, no mag, no filter
    '4,60003.0,153.0,13.0,30.0,1,"{""trailLength"": 3.0}",20.1,i\n'
)

# MPC 80-column line (80 chars) including magnitude and filter:
#   year=2024, month=01, day=15.500000 → MJD 60324.5
#   RA=10h23m45.670s, Dec=+12°34'56.70", mag=12.34, filter=r, obs=X05
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
    "         "  # [56:65] blank (9 chars)
    "12.34"  # [65:70] magnitude (5 chars)
    "r"  # [70]    filter band
    "      "  # [71:77] blank (6 chars)
    "X05"  # [77:80] obs code
)
assert len(_MPC80_LINE) == 80

_MPC80_EXPECTED_MJD = 60324.5
_MPC80_EXPECTED_RA = (10 + 23 / 60 + 45.670 / 3600) * 15
_MPC80_EXPECTED_DEC = 12 + 34 / 60 + 56.70 / 3600

# ADES PSV with full optional columns
_ADES_FULL = (
    "# version ADES 2017\n"
    "| stn | obsTime | ra | dec | rmsRA | rmsDec | mag | rmsMag | band | obsID |\n"
    "| X05 | 2024-01-15T12:00:00Z | 155.940 | 12.582 | 0.15 | 0.20 | 18.5 | 0.05 | r | obs001 |\n"
    "| I41 | 2024-01-15T18:00:00Z | 210.500 | -5.300 | 0.18 | 0.25 | 19.1 | 0.07 | g | obs002 |\n"
)

# ADES PSV without optional error/photometry columns
_ADES_MINIMAL = (
    "# version ADES 2017\n"
    "| stn | obsTime | ra | dec |\n"
    "| X05 | 2024-01-15T12:00:00Z | 155.940 | 12.582 |\n"
)


@pytest.fixture
def csv_file(tmp_path: Path) -> Path:
    p = tmp_path / "alerts.csv"
    p.write_text(_CSV_CONTENT)
    return p


@pytest.fixture
def mpc80_file(tmp_path: Path) -> Path:
    p = tmp_path / "obs.mpc"
    p.write_text(_MPC80_LINE + "\n")
    return p


@pytest.fixture
def ades_full(tmp_path: Path) -> Path:
    p = tmp_path / "obs_full.psv"
    p.write_text(_ADES_FULL)
    return p


@pytest.fixture
def ades_minimal(tmp_path: Path) -> Path:
    p = tmp_path / "obs_minimal.psv"
    p.write_text(_ADES_MINIMAL)
    return p


@pytest.fixture
def sqlite_db(tmp_path: Path) -> Path:
    """Pipeline SQLite database with psf_mag and filter columns."""
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
            has_ss_source INTEGER DEFAULT 0,
            psf_mag REAL,
            filter TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO alerts_raw VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (1, "det001", 60000.0, 150.0, 10.0, 20.0, "{}", 1, 18.5, "r"),
            (2, "det002", 60001.0, 151.0, 11.0, 50.0, '{"trailLength": 3.0}', 0, 19.2, "g"),
            (3, "det003", 60002.0, 152.0, 12.0, None, "{}", 1, None, None),
        ],
    )
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def sqlite_db_no_phot(tmp_path: Path) -> Path:
    """Pipeline SQLite database without psf_mag / filter columns."""
    db = tmp_path / "test_nophot.db"
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
    conn.execute(
        "INSERT INTO alerts_raw VALUES (?,?,?,?,?,?,?,?)",
        (1, "det001", 60000.0, 150.0, 10.0, 20.0, "{}", 1),
    )
    conn.commit()
    conn.close()
    return db


# ---------------------------------------------------------------------------
# _mjd_to_night
# ---------------------------------------------------------------------------


class TestMjdToNight:
    def test_noon_utc_starts_new_night(self):
        # floor(mjd - 0.5): midnight = 0.0 fraction, noon = 0.5 fraction
        # Night rolls over at noon UTC — same night before and after midnight
        night_before_midnight = _mjd_to_night(60000.9)  # 21:36 UTC
        night_after_midnight = _mjd_to_night(60001.1)  # 02:24 UTC next day
        assert night_before_midnight == night_after_midnight

    def test_noon_rollover(self):
        # Just before noon and just after noon are different nights
        just_before_noon = _mjd_to_night(60000.499)
        just_after_noon = _mjd_to_night(60000.501)
        assert just_after_noon == just_before_noon + 1

    def test_returns_integer(self):
        assert isinstance(_mjd_to_night(60000.0), int)

    def test_monotone(self):
        nights = [_mjd_to_night(60000.0 + i) for i in range(5)]
        assert nights == sorted(nights)
        assert len(set(nights)) == 5  # each day is a different night


# ---------------------------------------------------------------------------
# _estimate_pos_sigma_arcsec
# ---------------------------------------------------------------------------


class TestEstimatePosSigmaArcsec:
    def test_with_snr(self):
        assert _estimate_pos_sigma_arcsec(snr=10.0, psf_fwhm=1.0) == pytest.approx(0.1)

    def test_fallback_none_snr(self):
        assert _estimate_pos_sigma_arcsec(None, 1.0) == DEFAULT_POS_SIGMA_ARCSEC

    def test_fallback_zero_snr(self):
        assert _estimate_pos_sigma_arcsec(0.0, 1.0) == DEFAULT_POS_SIGMA_ARCSEC

    def test_scales_with_fwhm(self):
        assert _estimate_pos_sigma_arcsec(10.0, 2.0) == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# _estimate_trail_sigma_arcsec
# ---------------------------------------------------------------------------


class TestEstimateTrailSigmaArcsec:
    def test_no_trail_returns_pos_sigma(self):
        assert _estimate_trail_sigma_arcsec(0.2, None, 1.0) == pytest.approx(0.2)

    def test_zero_trail_returns_pos_sigma(self):
        assert _estimate_trail_sigma_arcsec(0.2, 0.0, 1.0) == pytest.approx(0.2)

    def test_trail_gives_larger_dec_sigma(self):
        dec_sigma = _estimate_trail_sigma_arcsec(0.2, 3.0, 1.0)
        assert dec_sigma > 0.2

    def test_trail_formula(self):
        pos_sigma, trail, fwhm = 0.2, 3.0, 1.0
        major = math.sqrt(fwhm**2 + trail**2)
        expected = pos_sigma * math.sqrt(major / fwhm)
        assert _estimate_trail_sigma_arcsec(pos_sigma, trail, fwhm) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# read_from_sqlite
# ---------------------------------------------------------------------------


class TestReadFromSqlite:
    def test_row_count(self, sqlite_db):
        rows = read_from_sqlite(sqlite_db, "X05", psf_fwhm=1.0, default_filter="r")
        assert len(rows) == 3

    def test_thor_columns_present(self, sqlite_db):
        rows = read_from_sqlite(sqlite_db, "X05", psf_fwhm=1.0, default_filter="r")
        for row in rows:
            for col in _THOR_COLUMNS:
                assert col in row

    def test_observatory_code_set(self, sqlite_db):
        rows = read_from_sqlite(sqlite_db, "X05", psf_fwhm=1.0, default_filter="r")
        assert all(r["observatory_code"] == "X05" for r in rows)

    def test_ra_sigma_in_degrees(self, sqlite_db):
        rows = read_from_sqlite(sqlite_db, "X05", psf_fwhm=1.0, default_filter="r")
        # ra_sigma must be in degrees (< 0.01 deg = 36 arcsec for reasonable SNR)
        assert all(r["ra_sigma"] < 0.01 for r in rows)

    def test_mag_column_populated(self, sqlite_db):
        rows = read_from_sqlite(sqlite_db, "X05", psf_fwhm=1.0, default_filter="r")
        row_with_mag = next(r for r in rows if r["mjd_utc"] == 60000.0)
        assert row_with_mag["mag"] == pytest.approx(18.5)

    def test_filter_column_populated(self, sqlite_db):
        rows = read_from_sqlite(sqlite_db, "X05", psf_fwhm=1.0, default_filter="r")
        row = next(r for r in rows if r["mjd_utc"] == 60000.0)
        assert row["filter"] == "r"

    def test_null_mag_becomes_nan(self, sqlite_db):
        rows = read_from_sqlite(sqlite_db, "X05", psf_fwhm=1.0, default_filter="r")
        row = next(r for r in rows if r["mjd_utc"] == 60002.0)
        assert math.isnan(row["mag"])

    def test_null_filter_uses_default(self, sqlite_db):
        rows = read_from_sqlite(sqlite_db, "X05", psf_fwhm=1.0, default_filter="z")
        row = next(r for r in rows if r["mjd_utc"] == 60002.0)
        assert row["filter"] == "z"

    def test_no_phot_columns_graceful(self, sqlite_db_no_phot):
        rows = read_from_sqlite(sqlite_db_no_phot, "X05", psf_fwhm=1.0, default_filter="r")
        assert len(rows) == 1
        assert math.isnan(rows[0]["mag"])
        assert rows[0]["filter"] == "r"

    def test_night_column(self, sqlite_db):
        rows = read_from_sqlite(sqlite_db, "X05", psf_fwhm=1.0, default_filter="r")
        for row in rows:
            assert row["night"] == _mjd_to_night(row["mjd_utc"])

    def test_trail_increases_dec_sigma(self, sqlite_db):
        rows = read_from_sqlite(sqlite_db, "X05", psf_fwhm=1.0, default_filter="r")
        trailed = next(r for r in rows if r["mjd_utc"] == 60001.0)
        assert trailed["dec_sigma"] > trailed["ra_sigma"]

    def test_sso_only_filter(self, sqlite_db):
        rows = read_from_sqlite(sqlite_db, "X05", psf_fwhm=1.0, default_filter="r", sso_only=True)
        assert len(rows) == 2

    def test_mjd_min_filter(self, sqlite_db):
        rows = read_from_sqlite(sqlite_db, "X05", psf_fwhm=1.0, default_filter="r", mjd_min=60001.0)
        assert all(r["mjd_utc"] >= 60001.0 for r in rows)

    def test_missing_db_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_from_sqlite(tmp_path / "missing.db", "X05", psf_fwhm=1.0, default_filter="r")

    def test_sorted_by_mjd(self, sqlite_db):
        rows = read_from_sqlite(sqlite_db, "X05", psf_fwhm=1.0, default_filter="r")
        mjds = [r["mjd_utc"] for r in rows]
        assert mjds == sorted(mjds)


# ---------------------------------------------------------------------------
# read_from_csv
# ---------------------------------------------------------------------------


class TestReadFromCsv:
    def test_row_count(self, csv_file):
        rows = read_from_csv(csv_file, "X05", psf_fwhm=1.0, default_filter="r")
        assert len(rows) == 4

    def test_thor_columns_present(self, csv_file):
        rows = read_from_csv(csv_file, "X05", psf_fwhm=1.0, default_filter="r")
        for row in rows:
            for col in _THOR_COLUMNS:
                assert col in row

    def test_mag_from_csv(self, csv_file):
        rows = read_from_csv(csv_file, "X05", psf_fwhm=1.0, default_filter="r")
        row = next(r for r in rows if r["mjd_utc"] == 60000.0)
        assert row["mag"] == pytest.approx(18.5)

    def test_filter_from_csv(self, csv_file):
        rows = read_from_csv(csv_file, "X05", psf_fwhm=1.0, default_filter="r")
        row = next(r for r in rows if r["mjd_utc"] == 60001.0)
        assert row["filter"] == "g"

    def test_missing_mag_becomes_nan(self, csv_file):
        rows = read_from_csv(csv_file, "X05", psf_fwhm=1.0, default_filter="r")
        row = next(r for r in rows if r["mjd_utc"] == 60002.0)
        assert math.isnan(row["mag"])

    def test_missing_filter_uses_default(self, csv_file):
        rows = read_from_csv(csv_file, "X05", psf_fwhm=1.0, default_filter="z")
        row = next(r for r in rows if r["mjd_utc"] == 60002.0)
        assert row["filter"] == "z"

    def test_ra_sigma_in_degrees(self, csv_file):
        rows = read_from_csv(csv_file, "X05", psf_fwhm=1.0, default_filter="r")
        assert all(r["ra_sigma"] < 0.01 for r in rows)

    def test_night_column(self, csv_file):
        rows = read_from_csv(csv_file, "X05", psf_fwhm=1.0, default_filter="r")
        for row in rows:
            assert row["night"] == _mjd_to_night(row["mjd_utc"])

    def test_sso_only(self, csv_file):
        rows = read_from_csv(csv_file, "X05", psf_fwhm=1.0, default_filter="r", sso_only=True)
        assert len(rows) == 3

    def test_mjd_min_filter(self, csv_file):
        rows = read_from_csv(csv_file, "X05", psf_fwhm=1.0, default_filter="r", mjd_min=60001.0)
        assert len(rows) == 3

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_from_csv(tmp_path / "missing.csv", "X05", psf_fwhm=1.0, default_filter="r")

    def test_missing_columns_raises(self, tmp_path):
        bad = tmp_path / "bad.csv"
        bad.write_text("col_a,col_b\n1,2\n")
        with pytest.raises(KeyError, match="required columns"):
            read_from_csv(bad, "X05", psf_fwhm=1.0, default_filter="r")

    def test_sorted_by_mjd(self, csv_file):
        rows = read_from_csv(csv_file, "X05", psf_fwhm=1.0, default_filter="r")
        mjds = [r["mjd_utc"] for r in rows]
        assert mjds == sorted(mjds)


# ---------------------------------------------------------------------------
# read_mpc80
# ---------------------------------------------------------------------------


class TestReadMpc80:
    def test_basic(self, mpc80_file):
        rows = read_mpc80(mpc80_file, psf_fwhm=1.0, default_filter="r")
        assert len(rows) == 1

    def test_coordinates(self, mpc80_file):
        rows = read_mpc80(mpc80_file, psf_fwhm=1.0, default_filter="r")
        row = rows[0]
        assert row["ra"] == pytest.approx(_MPC80_EXPECTED_RA, abs=0.001)
        assert row["dec"] == pytest.approx(_MPC80_EXPECTED_DEC, abs=0.001)

    def test_mjd(self, mpc80_file):
        rows = read_mpc80(mpc80_file, psf_fwhm=1.0, default_filter="r")
        assert rows[0]["mjd_utc"] == pytest.approx(_MPC80_EXPECTED_MJD)

    def test_observatory_code_from_file(self, mpc80_file):
        rows = read_mpc80(mpc80_file, psf_fwhm=1.0, default_filter="r")
        assert rows[0]["observatory_code"] == "X05"

    def test_mag_from_file(self, mpc80_file):
        rows = read_mpc80(mpc80_file, psf_fwhm=1.0, default_filter="r")
        assert rows[0]["mag"] == pytest.approx(12.34)

    def test_filter_from_file(self, mpc80_file):
        rows = read_mpc80(mpc80_file, psf_fwhm=1.0, default_filter="V")
        # "r" is in the file at position [70], should take precedence over default
        assert rows[0]["filter"] == "r"

    def test_default_filter_when_blank(self, tmp_path):
        # Build a line with blank mag and filter fields
        line_no_phot = _MPC80_LINE[:65] + "     " + " " + _MPC80_LINE[71:]
        p = tmp_path / "no_phot.mpc"
        p.write_text(line_no_phot + "\n")
        rows = read_mpc80(p, psf_fwhm=1.0, default_filter="V")
        assert math.isnan(rows[0]["mag"])
        assert rows[0]["filter"] == "V"

    def test_default_pos_sigma_used(self, mpc80_file):
        rows = read_mpc80(mpc80_file, psf_fwhm=1.0, default_filter="r")
        assert rows[0]["ra_sigma"] == pytest.approx(DEFAULT_POS_SIGMA_DEG)
        assert rows[0]["dec_sigma"] == pytest.approx(DEFAULT_POS_SIGMA_DEG)

    def test_ra_sigma_in_degrees(self, mpc80_file):
        rows = read_mpc80(mpc80_file, psf_fwhm=1.0, default_filter="r")
        assert rows[0]["ra_sigma"] < 0.01  # degrees, not arcseconds

    def test_night_column(self, mpc80_file):
        rows = read_mpc80(mpc80_file, psf_fwhm=1.0, default_filter="r")
        assert rows[0]["night"] == _mjd_to_night(_MPC80_EXPECTED_MJD)

    def test_blank_obs_code_skipped(self, tmp_path):
        line_no_code = _MPC80_LINE[:77] + "   "
        p = tmp_path / "no_code.mpc"
        p.write_text(line_no_code + "\n")
        rows = read_mpc80(p, psf_fwhm=1.0, default_filter="r")
        assert rows == []

    def test_comment_and_blank_lines_skipped(self, tmp_path):
        p = tmp_path / "with_comments.mpc"
        p.write_text("# comment\n\n" + _MPC80_LINE + "\n")
        rows = read_mpc80(p, psf_fwhm=1.0, default_filter="r")
        assert len(rows) == 1

    def test_mjd_filter(self, mpc80_file):
        rows = read_mpc80(
            mpc80_file, psf_fwhm=1.0, default_filter="r", mjd_min=_MPC80_EXPECTED_MJD + 1
        )
        assert rows == []

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_mpc80(tmp_path / "missing.mpc", psf_fwhm=1.0, default_filter="r")

    def test_thor_columns_present(self, mpc80_file):
        rows = read_mpc80(mpc80_file, psf_fwhm=1.0, default_filter="r")
        for col in _THOR_COLUMNS:
            assert col in rows[0]


# ---------------------------------------------------------------------------
# read_ades_psv
# ---------------------------------------------------------------------------


class TestReadAdesPsv:
    def test_basic(self, ades_full):
        rows = read_ades_psv(ades_full, psf_fwhm=1.0, default_filter="r")
        assert len(rows) == 2

    def test_observatory_code_from_file(self, ades_full):
        rows = read_ades_psv(ades_full, psf_fwhm=1.0, default_filter="r")
        codes = {r["observatory_code"] for r in rows}
        assert codes == {"X05", "I41"}

    def test_rms_fields_used_and_in_degrees(self, ades_full):
        rows = read_ades_psv(ades_full, psf_fwhm=1.0, default_filter="r")
        x05 = next(r for r in rows if r["observatory_code"] == "X05")
        assert x05["ra_sigma"] == pytest.approx(0.15 * _ARCSEC_TO_DEG)
        assert x05["dec_sigma"] == pytest.approx(0.20 * _ARCSEC_TO_DEG)

    def test_mag_from_file(self, ades_full):
        rows = read_ades_psv(ades_full, psf_fwhm=1.0, default_filter="r")
        x05 = next(r for r in rows if r["observatory_code"] == "X05")
        assert x05["mag"] == pytest.approx(18.5)

    def test_mag_sigma_from_file(self, ades_full):
        rows = read_ades_psv(ades_full, psf_fwhm=1.0, default_filter="r")
        x05 = next(r for r in rows if r["observatory_code"] == "X05")
        assert x05["mag_sigma"] == pytest.approx(0.05)

    def test_filter_from_band_column(self, ades_full):
        rows = read_ades_psv(ades_full, psf_fwhm=1.0, default_filter="V")
        x05 = next(r for r in rows if r["observatory_code"] == "X05")
        assert x05["filter"] == "r"

    def test_obs_id_used(self, ades_full):
        rows = read_ades_psv(ades_full, psf_fwhm=1.0, default_filter="r")
        ids = {r["id"] for r in rows}
        assert "obs001" in ids
        assert "obs002" in ids

    def test_fallback_default_sigma_when_no_rms(self, ades_minimal):
        rows = read_ades_psv(ades_minimal, psf_fwhm=1.0, default_filter="r")
        assert len(rows) == 1
        assert rows[0]["ra_sigma"] == pytest.approx(DEFAULT_POS_SIGMA_DEG)
        assert rows[0]["dec_sigma"] == pytest.approx(DEFAULT_POS_SIGMA_DEG)

    def test_missing_mag_becomes_nan(self, ades_minimal):
        rows = read_ades_psv(ades_minimal, psf_fwhm=1.0, default_filter="r")
        assert math.isnan(rows[0]["mag"])
        assert math.isnan(rows[0]["mag_sigma"])

    def test_default_filter_when_no_band(self, ades_minimal):
        rows = read_ades_psv(ades_minimal, psf_fwhm=1.0, default_filter="z")
        assert rows[0]["filter"] == "z"

    def test_night_column(self, ades_full):
        rows = read_ades_psv(ades_full, psf_fwhm=1.0, default_filter="r")
        for row in rows:
            assert row["night"] == _mjd_to_night(row["mjd_utc"])

    def test_mjd_filter(self, ades_full):
        rows = read_ades_psv(
            ades_full, psf_fwhm=1.0, default_filter="r", mjd_max=_iso_to_mjd("2024-01-15T12:00:00Z")
        )
        assert len(rows) == 1

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_ades_psv(tmp_path / "missing.psv", psf_fwhm=1.0, default_filter="r")

    def test_missing_required_columns_raises(self, tmp_path):
        bad = tmp_path / "bad.psv"
        bad.write_text("| stn | ra |\n| X05 | 10.0 |\n")
        with pytest.raises(KeyError, match="required columns"):
            read_ades_psv(bad, psf_fwhm=1.0, default_filter="r")

    def test_no_header_raises(self, tmp_path):
        p = tmp_path / "noheader.psv"
        p.write_text("# comment only\n")
        with pytest.raises(KeyError):
            read_ades_psv(p, psf_fwhm=1.0, default_filter="r")

    def test_thor_columns_present(self, ades_full):
        rows = read_ades_psv(ades_full, psf_fwhm=1.0, default_filter="r")
        for row in rows:
            for col in _THOR_COLUMNS:
                assert col in row


# ---------------------------------------------------------------------------
# write_thor_observations
# ---------------------------------------------------------------------------


def _make_row(mjd=60000.0, obs="X05", mag=18.5, filt="r") -> dict:
    return {
        "id": f"{obs}_{mjd:.0f}",
        "exposure_id": f"{obs}_{mjd:.0f}",
        "mjd_utc": mjd,
        "night": _mjd_to_night(mjd),
        "ra": 150.0,
        "dec": -30.0,
        "ra_sigma": 0.0001,
        "dec_sigma": 0.0001,
        "ra_dec_cov": float("nan"),
        "mag": mag,
        "mag_sigma": 0.05,
        "filter": filt,
        "observatory_code": obs,
    }


class TestWriteThorObservations:
    def test_returns_count(self, tmp_path):
        rows = [_make_row(60000.0 + i) for i in range(5)]
        assert write_thor_observations(rows, tmp_path / "out.parquet") == 5

    def test_creates_parquet_file(self, tmp_path):
        write_thor_observations([_make_row()], tmp_path / "out.parquet")
        assert (tmp_path / "out.parquet").exists()

    def test_creates_csv_file(self, tmp_path):
        write_thor_observations([_make_row()], tmp_path / "out.csv", fmt="csv")
        assert (tmp_path / "out.csv").exists()

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "nested" / "dir" / "out.parquet"
        write_thor_observations([_make_row()], out)
        assert out.exists()

    def test_parquet_columns_match_schema(self, tmp_path):
        out = tmp_path / "out.parquet"
        write_thor_observations([_make_row()], out)
        df = pd.read_parquet(out)
        assert list(df.columns) == _THOR_COLUMNS

    def test_csv_columns_match_schema(self, tmp_path):
        out = tmp_path / "out.csv"
        write_thor_observations([_make_row()], out, fmt="csv")
        df = pd.read_csv(out)
        assert list(df.columns) == _THOR_COLUMNS

    def test_parquet_values_round_trip(self, tmp_path):
        row = _make_row(mjd=60324.5, obs="X05", mag=18.5, filt="r")
        out = tmp_path / "out.parquet"
        write_thor_observations([row], out)
        df = pd.read_parquet(out)
        assert df["mjd_utc"].iloc[0] == pytest.approx(60324.5)
        assert df["ra"].iloc[0] == pytest.approx(150.0)
        assert df["mag"].iloc[0] == pytest.approx(18.5)
        assert df["filter"].iloc[0] == "r"
        assert df["observatory_code"].iloc[0] == "X05"

    def test_night_dtype_is_integer(self, tmp_path):
        out = tmp_path / "out.parquet"
        write_thor_observations([_make_row()], out)
        df = pd.read_parquet(out)
        assert pd.api.types.is_integer_dtype(df["night"])

    def test_empty_rows_writes_header_only(self, tmp_path):
        out = tmp_path / "out.parquet"
        n = write_thor_observations([], out)
        assert n == 0
        df = pd.read_parquet(out)
        assert len(df) == 0
        assert list(df.columns) == _THOR_COLUMNS

    def test_invalid_format_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unsupported output format"):
            write_thor_observations([_make_row()], tmp_path / "out.trd", fmt="trd")

    def test_multiple_rows_preserved(self, tmp_path):
        rows = [_make_row(60000.0 + i, obs="X05") for i in range(10)]
        out = tmp_path / "out.parquet"
        write_thor_observations(rows, out)
        df = pd.read_parquet(out)
        assert len(df) == 10

    def test_nan_mag_round_trips(self, tmp_path):
        row = _make_row()
        row["mag"] = float("nan")
        out = tmp_path / "out.parquet"
        write_thor_observations([row], out)
        df = pd.read_parquet(out)
        assert math.isnan(df["mag"].iloc[0])
