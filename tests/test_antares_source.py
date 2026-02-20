"""Tests for ANTARESSource adapter."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from lsst_extendedness.models import AlertRecord
from lsst_extendedness.sources.antares import ANTARESSource


class MockAlert:
    """Mock ANTARES Alert object."""

    def __init__(
        self,
        alert_id: str = "12345",
        mjd: float = 60000.5,
        properties: dict[str, Any] | None = None,
        packet: dict[str, Any] | None = None,
    ):
        self.alert_id = alert_id
        self.mjd = mjd
        self.properties = properties or {
            "diaSourceId": 67890,
            "diaObjectId": 11111,
            "ra": 180.5,
            "decl": 45.25,
            "midPointTai": 60000.5,
            "filterName": "r",
            "psFlux": 1500.0,
            "psFluxErr": 15.0,
            "snr": 100.0,
            "extendednessMedian": 0.42,
            "extendednessMin": 0.38,
            "extendednessMax": 0.48,
            "trailLength": 0.0,
            "pixelFlagsBad": False,
        }
        self.packet = packet


class MockLocus:
    """Mock ANTARES Locus object."""

    def __init__(
        self,
        locus_id: str = "LOCUS_001",
        ra: float = 180.5,
        dec: float = 45.25,
        alerts: list[MockAlert] | None = None,
        tags: list[str] | None = None,
    ):
        self.locus_id = locus_id
        self.ra = ra
        self.dec = dec
        self.alerts = alerts if alerts is not None else [MockAlert()]
        self.tags = tags or []


class MockStreamingClient:
    """Mock ANTARES StreamingClient."""

    def __init__(
        self,
        topics: list[str],
        api_key: str,
        api_secret: str,
        loci: list[tuple[str, MockLocus]] | None = None,
    ):
        self.topics = topics
        self.api_key = api_key
        self.api_secret = api_secret
        self._loci = loci or [("test_topic", MockLocus())]
        self._index = 0
        self._closed = False

    def iter(self):
        """Iterate over mock loci."""
        yield from self._loci

    def close(self):
        """Close the mock client."""
        self._closed = True


class TestANTARESSourceInit:
    """Tests for ANTARESSource initialization."""

    def test_init_with_required_params(self):
        """Test initialization with required parameters."""
        source = ANTARESSource(
            topics=["test_topic"],
            api_key="test_key",
            api_secret="test_secret",
        )
        assert source.topics == ["test_topic"]
        assert source.api_key == "test_key"
        assert source.api_secret == "test_secret"
        assert source.source_name == "antares"
        assert source.poll_timeout == 10.0
        assert source.include_locus_history is False

    def test_init_with_optional_params(self):
        """Test initialization with optional parameters."""
        source = ANTARESSource(
            topics=["topic1", "topic2"],
            api_key="key",
            api_secret="secret",
            poll_timeout=30.0,
            include_locus_history=True,
        )
        assert source.poll_timeout == 30.0
        assert source.include_locus_history is True

    def test_repr(self):
        """Test string representation."""
        source = ANTARESSource(
            topics=["extragalactic_staging"],
            api_key="key",
            api_secret="secret",
        )
        assert "ANTARESSource" in repr(source)
        assert "extragalactic_staging" in repr(source)


class TestANTARESSourceConnection:
    """Tests for ANTARESSource connection handling."""

    @patch("lsst_extendedness.sources.antares._import_antares_client")
    def test_connect_creates_client(self, mock_import):
        """Test that connect() creates StreamingClient."""
        mock_module = MagicMock()
        mock_module.StreamingClient = MockStreamingClient
        mock_import.return_value = mock_module

        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )
        source.connect()

        assert source._connected is True
        assert source._client is not None

    @patch("lsst_extendedness.sources.antares._import_antares_client")
    def test_connect_raises_on_failure(self, mock_import):
        """Test that connect() raises ConnectionError on failure."""
        mock_module = MagicMock()
        mock_module.StreamingClient.side_effect = Exception("Connection failed")
        mock_import.return_value = mock_module

        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )

        with pytest.raises(ConnectionError, match="Failed to connect"):
            source.connect()

    @patch("lsst_extendedness.sources.antares._import_antares_client")
    def test_close(self, mock_import):
        """Test that close() cleans up resources."""
        mock_module = MagicMock()
        mock_module.StreamingClient = MockStreamingClient
        mock_import.return_value = mock_module

        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )
        source.connect()
        source.close()

        assert source._connected is False
        assert source._client is None

    @patch("lsst_extendedness.sources.antares._import_antares_client")
    def test_context_manager(self, mock_import):
        """Test context manager usage."""
        mock_module = MagicMock()
        mock_module.StreamingClient = MockStreamingClient
        mock_import.return_value = mock_module

        with ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        ) as source:
            assert source._connected is True

        assert source._connected is False


class TestANTARESSourceFetch:
    """Tests for ANTARESSource.fetch_alerts()."""

    @patch("lsst_extendedness.sources.antares._import_antares_client")
    def test_fetch_requires_connection(self, mock_import):
        """Test that fetch_alerts() requires connection."""
        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )

        with pytest.raises(RuntimeError, match="not connected"):
            list(source.fetch_alerts())

    @patch("lsst_extendedness.sources.antares._import_antares_client")
    def test_fetch_yields_alert_records(self, mock_import):
        """Test that fetch_alerts() yields AlertRecord instances."""
        mock_locus = MockLocus()
        mock_client = MockStreamingClient(
            topics=["test"],
            api_key="key",
            api_secret="secret",
            loci=[("test_topic", mock_locus)],
        )

        mock_module = MagicMock()
        mock_module.StreamingClient.return_value = mock_client
        mock_import.return_value = mock_module

        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )
        source.connect()
        source._client = mock_client

        alerts = list(source.fetch_alerts())

        assert len(alerts) == 1
        assert isinstance(alerts[0], AlertRecord)
        assert alerts[0].ra == 180.5
        assert alerts[0].dec == 45.25

    @patch("lsst_extendedness.sources.antares._import_antares_client")
    def test_fetch_with_limit(self, mock_import):
        """Test fetch_alerts() respects limit parameter."""
        loci = [("topic", MockLocus(locus_id=f"LOCUS_{i}")) for i in range(10)]
        mock_client = MockStreamingClient(
            topics=["test"],
            api_key="key",
            api_secret="secret",
            loci=loci,
        )

        mock_module = MagicMock()
        mock_module.StreamingClient.return_value = mock_client
        mock_import.return_value = mock_module

        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )
        source.connect()
        source._client = mock_client

        alerts = list(source.fetch_alerts(limit=3))

        assert len(alerts) == 3


class TestANTARESSourceConversion:
    """Tests for ANTARES locus to AlertRecord conversion."""

    def test_convert_basic_locus(self):
        """Test basic locus conversion."""
        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )

        locus = MockLocus()
        result = source._convert_locus(locus)

        assert result is not None
        assert isinstance(result, AlertRecord)
        assert result.dia_source_id == 67890
        assert result.ra == 180.5
        assert result.dec == 45.25
        assert result.mjd == 60000.5
        assert result.filter_name == "r"
        assert result.extendedness_median == 0.42

    def test_convert_locus_with_empty_alerts(self):
        """Test that empty alerts list returns None."""
        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )

        locus = MockLocus(alerts=[])
        result = source._convert_locus(locus)

        assert result is None

    def test_convert_locus_with_ss_object(self):
        """Test conversion with solar system object."""
        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )

        alert = MockAlert(
            properties={
                "diaSourceId": 1000,
                "ra": 100.0,
                "decl": 30.0,
                "midPointTai": 60000.0,
                "extendednessMedian": 0.5,
                "ssObjectId": "SSO_2024_AB1",
                "ssObjectReassocTimeMjdTai": 60000.0,
            }
        )
        locus = MockLocus(alerts=[alert])
        result = source._convert_locus(locus)

        assert result is not None
        assert result.has_ss_source is True
        assert result.ss_object_id == "SSO_2024_AB1"
        assert result.is_reassociation is True

    def test_convert_locus_with_sso_tag(self):
        """Test SSO detection via locus tags."""
        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )

        alert = MockAlert(
            properties={
                "diaSourceId": 1000,
                "ra": 100.0,
                "decl": 30.0,
                "midPointTai": 60000.0,
                "extendednessMedian": 0.5,
            }
        )
        locus = MockLocus(alerts=[alert], tags=["solar_system", "neo"])
        result = source._convert_locus(locus)

        assert result is not None
        assert result.has_ss_source is True

    def test_convert_locus_with_trail_data(self):
        """Test trail data extraction."""
        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )

        alert = MockAlert(
            properties={
                "diaSourceId": 1000,
                "ra": 100.0,
                "decl": 30.0,
                "midPointTai": 60000.0,
                "trailLength": 5.5,
                "trailAngle": 45.0,
                "trailFlux": 1000.0,
            }
        )
        locus = MockLocus(alerts=[alert])
        result = source._convert_locus(locus)

        assert result is not None
        assert result.trail_data["trailLength"] == 5.5
        assert result.trail_data["trailAngle"] == 45.0

    def test_convert_locus_with_pixel_flags(self):
        """Test pixel flags extraction."""
        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )

        alert = MockAlert(
            properties={
                "diaSourceId": 1000,
                "ra": 100.0,
                "decl": 30.0,
                "midPointTai": 60000.0,
                "pixelFlagsBad": False,
                "pixelFlagsCr": True,
                "pixelFlagsEdge": False,
            }
        )
        locus = MockLocus(alerts=[alert])
        result = source._convert_locus(locus)

        assert result is not None
        assert result.pixel_flags["pixelFlagsCr"] is True

    def test_convert_locus_history(self):
        """Test conversion of full locus history."""
        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
            include_locus_history=True,
        )

        alerts = [MockAlert(alert_id=str(i), mjd=60000.0 + i) for i in range(3)]
        locus = MockLocus(alerts=alerts)

        results = list(source._convert_locus_history(locus))

        assert len(results) == 3


class TestANTARESSourceSSExtraction:
    """Tests for SSObject information extraction."""

    def test_extract_ss_from_properties(self):
        """Test SSObject extraction from alert properties."""
        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )

        alert = MockAlert(
            properties={
                "ssObjectId": "SSO_123",
                "ssObjectReassocTimeMjdTai": 60000.5,
            }
        )
        locus = MockLocus()

        has_ss, ss_id, reassoc_time = source._extract_ss_info(locus, alert, alert.properties)

        assert has_ss is True
        assert ss_id == "SSO_123"
        assert reassoc_time == 60000.5

    def test_extract_ss_from_packet(self):
        """Test SSObject extraction from raw packet."""
        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )

        alert = MockAlert(
            properties={},
            packet={
                "ssObject": {
                    "ssObjectId": "SSO_456",
                    "ssObjectReassocTimeMjdTai": 60001.0,
                }
            },
        )
        locus = MockLocus()

        has_ss, ss_id, reassoc_time = source._extract_ss_info(locus, alert, alert.properties)

        assert has_ss is True
        assert ss_id == "SSO_456"
        assert reassoc_time == 60001.0

    def test_extract_ss_from_tags(self):
        """Test SSObject detection from locus tags."""
        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )

        alert = MockAlert(properties={})
        locus = MockLocus(tags=["asteroid", "mba"])

        has_ss, ss_id, _reassoc_time = source._extract_ss_info(locus, alert, alert.properties)

        assert has_ss is True
        assert ss_id is None  # ID not available from tags

    def test_extract_ss_no_sso(self):
        """Test when there's no SSObject."""
        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )

        alert = MockAlert(properties={"ra": 100.0})
        locus = MockLocus(tags=[])

        has_ss, ss_id, reassoc_time = source._extract_ss_info(locus, alert, alert.properties)

        assert has_ss is False
        assert ss_id is None
        assert reassoc_time is None


class TestANTARESSourceErrorHandling:
    """Tests for ANTARESSource error handling."""

    @patch("lsst_extendedness.sources.antares._import_antares_client")
    def test_fetch_with_locus_conversion_error(self, mock_import):
        """Test that conversion errors are handled gracefully."""
        # Create a locus with an alert that will raise an exception
        bad_alert = MagicMock()
        bad_alert.alert_id = "bad"
        bad_alert.mjd = 60000.0
        bad_alert.properties = None  # Will cause AttributeError

        bad_locus = MagicMock()
        bad_locus.locus_id = "BAD_LOCUS"
        bad_locus.alerts = [bad_alert]

        good_alert = MockAlert()
        good_locus = MockLocus(locus_id="GOOD_LOCUS", alerts=[good_alert])

        mock_client = MagicMock()
        mock_client.iter.return_value = [("topic", bad_locus), ("topic", good_locus)]

        mock_module = MagicMock()
        mock_module.StreamingClient.return_value = mock_client
        mock_import.return_value = mock_module

        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )
        source.connect()
        source._client = mock_client

        # Should skip bad locus and return good one
        alerts = list(source.fetch_alerts())
        assert len(alerts) == 1

    @patch("lsst_extendedness.sources.antares._import_antares_client")
    def test_fetch_with_keyboard_interrupt(self, mock_import):
        """Test that KeyboardInterrupt is handled gracefully."""
        mock_client = MagicMock()

        def raise_keyboard_interrupt():
            raise KeyboardInterrupt()

        mock_client.iter.side_effect = raise_keyboard_interrupt

        mock_module = MagicMock()
        mock_module.StreamingClient.return_value = mock_client
        mock_import.return_value = mock_module

        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )
        source.connect()
        source._client = mock_client

        # Should not raise, just stop iterating
        alerts = list(source.fetch_alerts())
        assert len(alerts) == 0

    @patch("lsst_extendedness.sources.antares._import_antares_client")
    def test_fetch_with_generic_exception(self, mock_import):
        """Test that generic exceptions are re-raised."""
        mock_client = MagicMock()
        mock_client.iter.side_effect = RuntimeError("Network error")

        mock_module = MagicMock()
        mock_module.StreamingClient.return_value = mock_client
        mock_import.return_value = mock_module

        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )
        source.connect()
        source._client = mock_client

        with pytest.raises(RuntimeError, match="Network error"):
            list(source.fetch_alerts())

    @patch("lsst_extendedness.sources.antares._import_antares_client")
    def test_close_handles_exception(self, mock_import):
        """Test that close() handles exceptions gracefully."""
        mock_client = MagicMock()
        mock_client.close.side_effect = Exception("Close failed")

        mock_module = MagicMock()
        mock_module.StreamingClient.return_value = mock_client
        mock_import.return_value = mock_module

        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )
        source.connect()
        source._client = mock_client

        # Should not raise
        source.close()
        assert source._connected is False
        assert source._client is None

    @patch("lsst_extendedness.sources.antares._import_antares_client")
    def test_fetch_locus_history_with_limit(self, mock_import):
        """Test fetch with locus history and limit."""
        # Create locus with multiple alerts
        alerts = [MockAlert(alert_id=str(i), mjd=60000.0 + i) for i in range(5)]
        locus = MockLocus(alerts=alerts)

        mock_client = MagicMock()
        mock_client.iter.return_value = [("topic", locus)]

        mock_module = MagicMock()
        mock_module.StreamingClient.return_value = mock_client
        mock_import.return_value = mock_module

        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
            include_locus_history=True,
        )
        source.connect()
        source._client = mock_client

        # Fetch with limit less than alerts in history
        result = list(source.fetch_alerts(limit=3))
        assert len(result) == 3

    def test_convert_locus_history_empty_alerts(self):
        """Test _convert_locus_history with empty alerts."""
        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )

        locus = MockLocus(alerts=[])
        results = list(source._convert_locus_history(locus))
        assert len(results) == 0

    def test_create_alert_record_exception(self):
        """Test _create_alert_record handles exceptions."""
        source = ANTARESSource(
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )

        # Create mock with broken data that will cause exception
        bad_locus = MagicMock()
        bad_locus.ra = "not a number"  # Will fail validation
        bad_locus.dec = "also bad"

        bad_alert = MagicMock()
        bad_alert.alert_id = "test"
        bad_alert.mjd = "not a float"

        bad_props = {"ra": "invalid", "decl": "invalid", "midPointTai": "bad"}

        result = source._create_alert_record(bad_locus, bad_alert, bad_props)
        assert result is None


class TestANTARESImportError:
    """Tests for antares-client import error handling."""

    def test_import_error_when_not_installed(self):
        """Test ImportError when antares-client is not installed."""
        import builtins
        import sys

        import lsst_extendedness.sources.antares as antares_module

        # Store original
        original = antares_module._antares_client
        original_import = builtins.__import__

        # Reset to None to force re-import
        antares_module._antares_client = None

        # Remove from sys.modules if present
        if "antares_client" in sys.modules:
            del sys.modules["antares_client"]

        def mock_import(name, *args, **kwargs):
            if name == "antares_client":
                raise ImportError("No module named 'antares_client'")
            return original_import(name, *args, **kwargs)

        builtins.__import__ = mock_import

        try:
            # Create fresh source
            source = ANTARESSource(
                topics=["test"],
                api_key="key",
                api_secret="secret",
            )

            # Connect should fail with ImportError
            with pytest.raises(ImportError, match="antares-client is required"):
                source.connect()
        finally:
            # Restore
            builtins.__import__ = original_import
            antares_module._antares_client = original


class TestANTARESSourceRegistration:
    """Tests for source registration."""

    def test_antares_source_registered(self):
        """Test that ANTARESSource is registered."""
        from lsst_extendedness.sources.protocol import is_source_registered

        assert is_source_registered("antares")

    def test_get_antares_source(self):
        """Test getting ANTARESSource from registry."""
        from lsst_extendedness.sources.protocol import get_source

        source = get_source(
            "antares",
            topics=["test"],
            api_key="key",
            api_secret="secret",
        )
        assert isinstance(source, ANTARESSource)
