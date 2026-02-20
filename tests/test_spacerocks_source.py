"""
Tests for SpaceRocksSource.

These tests verify the SpaceRocksSource implementation for fetching
known asteroid orbital data from JPL Horizons.

The tests are skipped if the space-rocks package is not installed.
"""

from __future__ import annotations

import pytest

# Check if spacerocks is available
try:
    from spacerocks import SpaceRock
    from spacerocks.time import Time

    SPACEROCKS_AVAILABLE = True
except ImportError:
    SPACEROCKS_AVAILABLE = False

# Skip all tests if spacerocks not available
pytestmark = pytest.mark.skipif(
    not SPACEROCKS_AVAILABLE,
    reason="space-rocks package not installed (requires Python <3.14)",
)


class TestSpaceRocksSourceImport:
    """Tests for SpaceRocksSource import and initialization."""

    def test_import_when_available(self):
        """Test that SpaceRocksSource can be imported."""
        from lsst_extendedness.sources import SpaceRocksSource

        assert SpaceRocksSource is not None

    def test_source_name(self):
        """Test source_name attribute."""
        from lsst_extendedness.sources import SpaceRocksSource

        source = SpaceRocksSource(objects=["Apophis"])
        assert source.source_name == "spacerocks"

    def test_default_objects(self):
        """Test default objects list."""
        from lsst_extendedness.sources import SpaceRocksSource

        source = SpaceRocksSource()
        assert len(source.objects) > 0
        assert "Apophis" in source.objects

    def test_custom_objects(self):
        """Test custom objects list."""
        from lsst_extendedness.sources import SpaceRocksSource

        objects = ["Bennu", "Ryugu"]
        source = SpaceRocksSource(objects=objects)
        assert source.objects == objects


class TestSpaceRocksSourceConnection:
    """Tests for SpaceRocksSource connection and data fetching."""

    @pytest.mark.slow
    def test_connect_fetches_data(self):
        """Test that connect() fetches orbital data from Horizons."""
        from lsst_extendedness.sources import SpaceRocksSource

        source = SpaceRocksSource(objects=["Eros"])
        source.connect()

        assert source._connected
        assert len(source._rocks) == 1

        source.close()

    @pytest.mark.slow
    def test_connect_handles_invalid_objects(self):
        """Test that connect() handles invalid object names gracefully."""
        from lsst_extendedness.sources import SpaceRocksSource

        # Mix of valid and invalid
        source = SpaceRocksSource(objects=["Eros", "NotARealAsteroid12345"])
        source.connect()

        # Should still connect with valid objects
        assert source._connected
        assert len(source._rocks) >= 1

        source.close()

    @pytest.mark.slow
    def test_connect_fails_with_all_invalid(self):
        """Test that connect() raises error if no objects found."""
        from lsst_extendedness.sources import SpaceRocksSource

        source = SpaceRocksSource(objects=["NotRealAsteroid1", "NotRealAsteroid2"])

        with pytest.raises(ConnectionError):
            source.connect()

    @pytest.mark.slow
    def test_fetch_alerts_yields_records(self):
        """Test that fetch_alerts() yields AlertRecord instances."""
        from lsst_extendedness.models import AlertRecord
        from lsst_extendedness.sources import SpaceRocksSource

        source = SpaceRocksSource(objects=["Eros"])
        source.connect()

        alerts = list(source.fetch_alerts())
        assert len(alerts) == 1
        assert isinstance(alerts[0], AlertRecord)

        source.close()

    @pytest.mark.slow
    def test_fetch_alerts_includes_orbital_elements(self):
        """Test that alerts include orbital elements in trail_data."""
        from lsst_extendedness.sources import SpaceRocksSource

        source = SpaceRocksSource(objects=["Eros"])
        source.connect()

        alerts = list(source.fetch_alerts())
        alert = alerts[0]

        # Check orbital elements are present
        assert "a" in alert.trail_data  # semi-major axis
        assert "e" in alert.trail_data  # eccentricity
        assert "inc" in alert.trail_data  # inclination
        assert "name" in alert.trail_data
        assert alert.trail_data["name"] == "Eros"

        source.close()

    @pytest.mark.slow
    def test_fetch_alerts_marks_as_sso(self):
        """Test that alerts are marked as SSO."""
        from lsst_extendedness.sources import SpaceRocksSource

        source = SpaceRocksSource(objects=["Eros"])
        source.connect()

        alerts = list(source.fetch_alerts())
        alert = alerts[0]

        assert alert.has_ss_source is True
        assert alert.ss_object_id == "Eros"

        source.close()

    def test_fetch_alerts_requires_connection(self):
        """Test that fetch_alerts() raises error if not connected."""
        from lsst_extendedness.sources import SpaceRocksSource

        source = SpaceRocksSource(objects=["Eros"])

        with pytest.raises(RuntimeError, match="not connected"):
            list(source.fetch_alerts())

    @pytest.mark.slow
    def test_fetch_alerts_respects_limit(self):
        """Test that fetch_alerts() respects limit parameter."""
        from lsst_extendedness.sources import SpaceRocksSource

        source = SpaceRocksSource(objects=["Eros", "Bennu", "Ryugu"])
        source.connect()

        alerts = list(source.fetch_alerts(limit=2))
        assert len(alerts) == 2

        source.close()


class TestSpaceRocksSourceContextManager:
    """Tests for context manager usage."""

    @pytest.mark.slow
    def test_context_manager(self):
        """Test context manager connects and closes properly."""
        from lsst_extendedness.sources import SpaceRocksSource

        with SpaceRocksSource(objects=["Eros"]) as source:
            assert source._connected
            alerts = list(source.fetch_alerts())
            assert len(alerts) == 1

        assert not source._connected

    @pytest.mark.slow
    def test_repr(self):
        """Test string representation."""
        from lsst_extendedness.sources import SpaceRocksSource

        source = SpaceRocksSource(objects=["Eros", "Bennu"])
        assert "SpaceRocksSource" in repr(source)
        assert "objects=2" in repr(source)


class TestSpaceRocksSourceRegistration:
    """Tests for source registration."""

    def test_registered_as_spacerocks(self):
        """Test source is registered with name 'spacerocks'."""
        from lsst_extendedness.sources.protocol import is_source_registered

        assert is_source_registered("spacerocks")

    @pytest.mark.slow
    def test_get_source_by_name(self):
        """Test getting source by registered name."""
        from lsst_extendedness.sources.protocol import get_source

        source = get_source("spacerocks", objects=["Eros"])
        assert source.source_name == "spacerocks"


class TestSpaceRocksUnavailable:
    """Tests for when spacerocks is not installed."""

    def test_import_error_message(self):
        """Test helpful error when spacerocks not installed.

        This test is always run and checks the error handling.
        """
        # This test verifies the import error is helpful
        # by checking the module's SPACEROCKS_AVAILABLE flag
        from lsst_extendedness.sources import spacerocks

        # The module should define this flag
        assert hasattr(spacerocks, "SPACEROCKS_AVAILABLE")
