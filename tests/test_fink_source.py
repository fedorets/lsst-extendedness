"""Tests for FinkSource."""

from __future__ import annotations

from pathlib import Path

import pytest

from lsst_extendedness.models import AlertRecord
from lsst_extendedness.sources.fink import FinkSource, _jd_to_mjd, _mag_to_flux, _object_id_to_int

# Fixture directory
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "fink"


class TestFinkSourceHelpers:
    """Tests for helper functions."""

    def test_jd_to_mjd(self):
        """Test Julian Date to MJD conversion."""
        # JD 2459537.0520833 should be around MJD 59536.5520833
        jd = 2459537.0520833
        mjd = _jd_to_mjd(jd)
        assert mjd == pytest.approx(59536.5520833, rel=1e-6)

    def test_mag_to_flux(self):
        """Test magnitude to flux conversion."""
        # mag=0 should give flux=1
        flux, _ = _mag_to_flux(0.0)
        assert flux == pytest.approx(1.0, rel=1e-6)

        # mag=5 should give flux=0.01 (5 mag = 100x dimmer)
        flux, _ = _mag_to_flux(5.0)
        assert flux == pytest.approx(0.01, rel=1e-6)

    def test_mag_to_flux_with_error(self):
        """Test magnitude to flux conversion with error."""
        flux, flux_err = _mag_to_flux(20.0, 0.1)
        assert flux > 0
        assert flux_err is not None
        assert flux_err > 0

    def test_object_id_to_int(self):
        """Test object ID string to int conversion."""
        # Same ID should give same result
        id1 = _object_id_to_int("ZTF21aaxtctv")
        id2 = _object_id_to_int("ZTF21aaxtctv")
        assert id1 == id2

        # Different IDs should give different results
        id3 = _object_id_to_int("ZTF20acvfraq")
        assert id3 != id1


class TestFinkSourceInit:
    """Tests for FinkSource initialization."""

    def test_init_default(self):
        """Test default initialization."""
        source = FinkSource()
        assert source.use_fixtures is True
        assert source.include_sso is True
        assert source.source_name == "fink"

    def test_init_custom_fixtures_dir(self, tmp_path):
        """Test initialization with custom fixtures directory."""
        source = FinkSource(fixtures_dir=tmp_path)
        assert source.fixtures_dir == tmp_path

    def test_init_no_sso(self):
        """Test initialization without SSO alerts."""
        source = FinkSource(include_sso=False)
        assert source.include_sso is False

    def test_repr(self):
        """Test string representation."""
        source = FinkSource()
        assert "FinkSource" in repr(source)
        assert "use_fixtures=True" in repr(source)


@pytest.mark.skipif(
    not (FIXTURES_DIR / "objects.json").exists(),
    reason="Fink fixtures not downloaded",
)
class TestFinkSourceWithFixtures:
    """Tests for FinkSource with real fixtures."""

    def test_connect_loads_fixtures(self):
        """Test that connect loads fixture files."""
        source = FinkSource()
        source.connect()

        assert source._connected is True
        assert len(source._alerts) > 0
        source.close()

    def test_fetch_alerts_yields_alert_records(self):
        """Test that fetch_alerts yields AlertRecord instances."""
        source = FinkSource()
        source.connect()

        alerts = list(source.fetch_alerts(limit=5))

        assert len(alerts) == 5
        for alert in alerts:
            assert isinstance(alert, AlertRecord)
            assert alert.ra is not None
            assert alert.dec is not None
            assert alert.mjd is not None

        source.close()

    def test_fetch_alerts_with_limit(self):
        """Test fetch_alerts respects limit parameter."""
        source = FinkSource()
        source.connect()

        alerts = list(source.fetch_alerts(limit=3))
        assert len(alerts) == 3

        source.close()

    def test_fetch_alerts_all(self):
        """Test fetching all alerts without limit."""
        source = FinkSource()
        source.connect()

        alerts = list(source.fetch_alerts())
        assert len(alerts) == len(source._alerts)

        source.close()

    def test_alert_has_expected_fields(self):
        """Test that converted alerts have expected fields."""
        source = FinkSource()
        source.connect()

        alert = next(source.fetch_alerts(limit=1))

        # Check required fields
        assert alert.alert_id > 0
        assert alert.dia_source_id > 0
        assert 0 <= alert.ra <= 360
        assert -90 <= alert.dec <= 90
        assert alert.mjd > 50000  # Sanity check for MJD

        # Check optional fields are present (may be None)
        assert hasattr(alert, "filter_name")
        assert hasattr(alert, "extendedness_median")
        assert hasattr(alert, "has_ss_source")

        source.close()

    def test_sso_alerts_have_ss_fields(self):
        """Test that SSO alerts have Solar System fields populated."""
        source = FinkSource(include_sso=True)
        source.connect()

        # Find an SSO alert
        sso_alerts = [a for a in source.fetch_alerts() if a.has_ss_source]

        assert len(sso_alerts) > 0, "Expected some SSO alerts in fixtures"

        # Check SSO fields
        sso = sso_alerts[0]
        assert sso.has_ss_source is True
        # ss_object_id may or may not be present depending on data
        assert hasattr(sso, "ss_object_id")

        source.close()

    def test_without_sso(self):
        """Test loading without SSO alerts."""
        source = FinkSource(include_sso=False)
        source.connect()

        # Should have fewer alerts than with SSO
        count_without = len(source._alerts)

        source2 = FinkSource(include_sso=True)
        source2.connect()
        count_with = len(source2._alerts)

        assert count_without < count_with

        source.close()
        source2.close()

    def test_context_manager(self):
        """Test using FinkSource as context manager."""
        with FinkSource() as source:
            assert source._connected is True
            alerts = list(source.fetch_alerts(limit=2))
            assert len(alerts) == 2

        assert source._connected is False

    def test_close_clears_state(self):
        """Test that close() clears internal state."""
        source = FinkSource()
        source.connect()
        assert len(source._alerts) > 0

        source.close()

        assert source._connected is False
        assert len(source._alerts) == 0


class TestFinkSourceErrors:
    """Tests for FinkSource error handling."""

    def test_fetch_without_connect_raises(self):
        """Test that fetch_alerts without connect raises RuntimeError."""
        source = FinkSource()

        with pytest.raises(RuntimeError, match="not connected"):
            list(source.fetch_alerts())

    def test_missing_fixtures_raises(self, tmp_path):
        """Test that missing fixtures raise FileNotFoundError."""
        source = FinkSource(fixtures_dir=tmp_path)

        with pytest.raises(FileNotFoundError, match="No fixture files found"):
            source.connect()

    def test_live_api_not_implemented(self):
        """Test that live API mode raises NotImplementedError."""
        source = FinkSource(use_fixtures=False)

        with pytest.raises(NotImplementedError, match="Live API"):
            source.connect()


class TestFinkSourceConversionEdgeCases:
    """Tests for edge cases in alert conversion."""

    def test_convert_alert_missing_required_field(self, tmp_path):
        """Test that alerts missing required fields return None."""
        source = FinkSource(fixtures_dir=tmp_path)

        # Create a fixture with missing required field
        incomplete_alert = {
            "i:candid": 12345,
            "i:objectId": "ZTF21test",
            # Missing i:ra, i:dec, i:jd
        }

        # Manually set the alerts list
        source._alerts = [incomplete_alert]
        source._connected = True

        alerts = list(source.fetch_alerts())

        # Should get 0 alerts since required fields are missing
        assert len(alerts) == 0

    def test_convert_alert_with_sso_name_fallback(self, tmp_path):
        """Test that sso_name is used when ssnamenr is not present."""
        source = FinkSource(fixtures_dir=tmp_path)

        # Create alert with sso_name but no ssnamenr
        alert_with_sso_name = {
            "i:candid": 12345,
            "i:objectId": "ZTF21test",
            "i:ra": 180.0,
            "i:dec": 45.0,
            "i:jd": 2459537.0520833,
            "d:roid": 3,  # Indicates SSO
            "sso_name": "2024 AB123",  # SSO name fallback
        }

        source._alerts = [alert_with_sso_name]
        source._connected = True

        alerts = list(source.fetch_alerts())

        assert len(alerts) == 1
        assert alerts[0].ss_object_id == "2024 AB123"
        assert alerts[0].has_ss_source is True

    def test_convert_alert_exception_is_logged(self, tmp_path, caplog):
        """Test that conversion exceptions are logged and skipped."""
        import logging

        source = FinkSource(fixtures_dir=tmp_path)

        # Create an alert that will cause an exception during conversion
        # (e.g., candid is a string that can't be converted to int)
        bad_alert = {
            "i:candid": "not-an-int",  # This will fail int() conversion
            "i:objectId": "ZTF21test",
            "i:ra": 180.0,
            "i:dec": 45.0,
            "i:jd": 2459537.0520833,
        }

        good_alert = {
            "i:candid": 12345,
            "i:objectId": "ZTF21good",
            "i:ra": 181.0,
            "i:dec": 46.0,
            "i:jd": 2459538.0,
        }

        source._alerts = [bad_alert, good_alert]
        source._connected = True

        with caplog.at_level(logging.WARNING):
            alerts = list(source.fetch_alerts())

        # Should get only the good alert
        assert len(alerts) == 1
        assert alerts[0].alert_id == 12345


class TestFinkSourceRegistration:
    """Tests for source registration."""

    def test_fink_source_registered(self):
        """Test that FinkSource is registered."""
        from lsst_extendedness.sources.protocol import is_source_registered

        assert is_source_registered("fink")

    def test_get_fink_source(self):
        """Test getting FinkSource from registry."""
        from lsst_extendedness.sources.protocol import get_source

        source = get_source("fink")
        assert isinstance(source, FinkSource)
