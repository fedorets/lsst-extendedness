"""
Tests for AVRO deserialization module.
"""

from __future__ import annotations

import struct
from unittest.mock import MagicMock, patch

import pytest

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_avro_dict():
    """Sample deserialized AVRO alert structure."""
    return {
        "alertId": 12345,
        "diaSource": {
            "diaSourceId": 123450001,
            "diaObjectId": 12345,
            "ra": 180.12345,
            "decl": 45.67890,
            "midPointTai": 60100.5,
            "filterName": "r",
            "psFlux": 1500.0,
            "psFluxErr": 15.0,
        },
        "ssObject": None,
    }


@pytest.fixture
def confluent_wire_format_data():
    """Create Confluent Wire Format message."""
    # Magic byte (0x00) + schema ID (4 bytes big-endian) + data
    schema_id = 12345
    magic_byte = b"\x00"
    schema_id_bytes = struct.pack(">I", schema_id)
    # Add some fake AVRO data after the header
    fake_avro_data = b"AVRO_DATA_HERE"
    return magic_byte + schema_id_bytes + fake_avro_data


@pytest.fixture
def raw_avro_data():
    """Create raw AVRO data (non-Confluent format)."""
    # Raw data that doesn't start with magic byte
    return b"\x01\x02\x03\x04\x05RAW_AVRO_DATA"


# ============================================================================
# EXTRACT SCHEMA ID TESTS
# ============================================================================


class TestExtractSchemaId:
    """Tests for extract_schema_id function."""

    def test_extract_from_confluent_format(self, confluent_wire_format_data):
        """Test extracting schema ID from Confluent format."""
        from lsst_extendedness.ingest.deserializer import extract_schema_id

        schema_id = extract_schema_id(confluent_wire_format_data)

        assert schema_id == 12345

    def test_extract_from_raw_avro(self, raw_avro_data):
        """Test that raw AVRO returns None."""
        from lsst_extendedness.ingest.deserializer import extract_schema_id

        schema_id = extract_schema_id(raw_avro_data)

        assert schema_id is None

    def test_extract_from_short_data(self):
        """Test with data too short for schema ID."""
        from lsst_extendedness.ingest.deserializer import extract_schema_id

        short_data = b"\x00\x01"  # Only 2 bytes

        schema_id = extract_schema_id(short_data)

        assert schema_id is None

    def test_extract_different_schema_ids(self):
        """Test extracting different schema IDs."""
        from lsst_extendedness.ingest.deserializer import extract_schema_id

        for expected_id in [0, 1, 100, 65535, 2**31 - 1]:
            data = b"\x00" + struct.pack(">I", expected_id) + b"data"
            result = extract_schema_id(data)
            assert result == expected_id


# ============================================================================
# AVRO TO ALERT TESTS
# ============================================================================


class TestAvroToAlert:
    """Tests for avro_to_alert function."""

    def test_convert_basic_alert(self, sample_avro_dict):
        """Test converting basic AVRO record to AlertRecord."""
        from lsst_extendedness.ingest.deserializer import avro_to_alert

        alert = avro_to_alert(sample_avro_dict)

        assert alert.alert_id == 12345
        assert alert.dia_source_id == 123450001
        assert alert.ra == 180.12345
        assert alert.dec == 45.67890

    def test_convert_with_ss_object(self):
        """Test converting alert with solar system object."""
        from lsst_extendedness.ingest.deserializer import avro_to_alert

        avro = {
            "alertId": 99999,
            "diaSource": {
                "diaSourceId": 999990001,
                "ra": 90.0,
                "decl": 30.0,
                "midPointTai": 60200.0,
            },
            "ssObject": {
                "ssObjectId": "SSO_2024_ABC",
            },
        }

        alert = avro_to_alert(avro)

        assert alert.has_ss_source is True
        assert alert.ss_object_id == "SSO_2024_ABC"


# ============================================================================
# ALERT DESERIALIZER CLASS TESTS
# ============================================================================


class TestAlertDeserializer:
    """Tests for AlertDeserializer class."""

    def test_init_default(self):
        """Test default initialization."""
        from lsst_extendedness.ingest.deserializer import AlertDeserializer

        deserializer = AlertDeserializer()

        assert deserializer.schema_registry_url is None
        assert deserializer._schema_cache == {}
        assert deserializer._default_schema is None

    def test_init_with_registry_url(self):
        """Test initialization with schema registry URL."""
        from lsst_extendedness.ingest.deserializer import AlertDeserializer

        deserializer = AlertDeserializer(schema_registry_url="http://schema-registry:8081")

        assert deserializer.schema_registry_url == "http://schema-registry:8081"

    def test_set_default_schema(self):
        """Test setting default schema."""
        from lsst_extendedness.ingest.deserializer import AlertDeserializer

        deserializer = AlertDeserializer()
        schema = {"type": "record", "name": "Alert", "fields": []}

        deserializer.set_default_schema(schema)

        assert deserializer._default_schema == schema

    def test_get_schema_from_cache(self):
        """Test getting schema from cache."""
        from lsst_extendedness.ingest.deserializer import AlertDeserializer

        deserializer = AlertDeserializer()
        schema = {"type": "record", "name": "Alert"}
        deserializer._schema_cache[123] = schema

        result = deserializer.get_schema(123)

        assert result == schema

    def test_get_schema_no_registry_url(self):
        """Test getting schema without registry URL."""
        from lsst_extendedness.ingest.deserializer import AlertDeserializer

        deserializer = AlertDeserializer()

        result = deserializer.get_schema(123)

        assert result is None

    @patch("httpx.get")
    def test_get_schema_from_registry(self, mock_get):
        """Test fetching schema from registry."""
        from lsst_extendedness.ingest.deserializer import AlertDeserializer

        deserializer = AlertDeserializer(schema_registry_url="http://schema-registry:8081")

        # Mock successful registry response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"schema": '{"type": "record", "name": "Alert"}'}
        mock_get.return_value = mock_response

        result = deserializer.get_schema(456)

        assert result == {"type": "record", "name": "Alert"}
        assert 456 in deserializer._schema_cache

    @patch("httpx.get")
    def test_get_schema_registry_failure(self, mock_get):
        """Test handling registry fetch failure."""
        from lsst_extendedness.ingest.deserializer import AlertDeserializer

        deserializer = AlertDeserializer(schema_registry_url="http://schema-registry:8081")

        # Mock failed response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = deserializer.get_schema(789)

        assert result is None

    @patch("httpx.get")
    def test_get_schema_registry_exception(self, mock_get):
        """Test handling registry connection error."""
        from lsst_extendedness.ingest.deserializer import AlertDeserializer

        deserializer = AlertDeserializer(schema_registry_url="http://schema-registry:8081")

        # Mock connection error
        mock_get.side_effect = Exception("Connection refused")

        result = deserializer.get_schema(999)

        assert result is None

    def test_deserialize_batch_empty(self):
        """Test deserializing empty batch."""
        from lsst_extendedness.ingest.deserializer import AlertDeserializer

        deserializer = AlertDeserializer()

        result = deserializer.deserialize_batch([])

        assert result == []

    @patch("lsst_extendedness.ingest.deserializer.deserialize_alert")
    def test_deserialize_batch_with_failures(self, mock_deserialize):
        """Test batch deserialization skips failures."""
        from lsst_extendedness.ingest.deserializer import AlertDeserializer
        from lsst_extendedness.models import AlertRecord

        deserializer = AlertDeserializer()

        # Create a mock alert
        mock_alert = MagicMock(spec=AlertRecord)

        # First succeeds, second fails, third succeeds
        mock_deserialize.side_effect = [
            mock_alert,
            ValueError("Invalid data"),
            mock_alert,
        ]

        result = deserializer.deserialize_batch([b"1", b"2", b"3"])

        assert len(result) == 2  # Only successful deserializations


# ============================================================================
# DESERIALIZE AVRO TESTS (with mocked fastavro)
# ============================================================================


class TestDeserializeAvro:
    """Tests for deserialize_avro function."""

    @patch("fastavro.reader")
    def test_deserialize_raw_avro(self, mock_reader, sample_avro_dict):
        """Test deserializing raw AVRO data."""
        from lsst_extendedness.ingest.deserializer import deserialize_avro

        mock_reader.return_value = iter([sample_avro_dict])

        result = deserialize_avro(b"RAW_AVRO_DATA")

        assert result == sample_avro_dict

    @patch("fastavro.reader")
    def test_deserialize_empty_avro(self, mock_reader):
        """Test deserializing AVRO with no records."""
        from lsst_extendedness.ingest.deserializer import deserialize_avro

        mock_reader.return_value = iter([])

        with pytest.raises(ValueError, match="No records found"):
            deserialize_avro(b"EMPTY_AVRO")

    @patch("fastavro.schemaless_reader")
    @patch("fastavro.parse_schema")
    def test_deserialize_with_schema(self, mock_parse, mock_schemaless_reader, sample_avro_dict):
        """Test deserializing with provided schema."""
        from lsst_extendedness.ingest.deserializer import deserialize_avro

        mock_parse.return_value = {"parsed": "schema"}
        mock_schemaless_reader.return_value = sample_avro_dict

        schema = {"type": "record", "name": "Alert"}
        result = deserialize_avro(b"DATA", schema=schema)

        assert result == sample_avro_dict
        mock_parse.assert_called_once()

    @patch("fastavro.reader")
    def test_deserialize_strips_confluent_header(
        self, mock_reader, sample_avro_dict, confluent_wire_format_data
    ):
        """Test that Confluent Wire Format header is stripped."""
        from lsst_extendedness.ingest.deserializer import deserialize_avro

        mock_reader.return_value = iter([sample_avro_dict])

        result = deserialize_avro(confluent_wire_format_data)

        # Should have stripped 5-byte header
        assert result == sample_avro_dict


class TestDeserializeAlert:
    """Tests for deserialize_alert convenience function."""

    @patch("lsst_extendedness.ingest.deserializer.deserialize_avro")
    def test_deserialize_alert_convenience(self, mock_deserialize, sample_avro_dict):
        """Test the convenience function."""
        from lsst_extendedness.ingest.deserializer import deserialize_alert

        mock_deserialize.return_value = sample_avro_dict

        alert = deserialize_alert(b"DATA")

        assert alert.alert_id == 12345
        mock_deserialize.assert_called_once_with(b"DATA", None)

    @patch("lsst_extendedness.ingest.deserializer.deserialize_avro")
    def test_deserialize_alert_with_schema(self, mock_deserialize, sample_avro_dict):
        """Test convenience function with schema."""
        from lsst_extendedness.ingest.deserializer import deserialize_alert

        mock_deserialize.return_value = sample_avro_dict
        schema = {"type": "record"}

        alert = deserialize_alert(b"DATA", schema=schema)

        assert alert.alert_id == 12345
        mock_deserialize.assert_called_once_with(b"DATA", schema)


class TestDeserializeAvroImportError:
    """Tests for fastavro import error handling."""

    def test_fastavro_import_error(self):
        """Test that ImportError is raised when fastavro is not installed."""
        import builtins
        import sys

        # Force reload of module with fastavro mocked out
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "fastavro":
                raise ImportError("No module named 'fastavro'")
            return original_import(name, *args, **kwargs)

        try:
            builtins.__import__ = mock_import
            # Clear cached import
            if "fastavro" in sys.modules:
                del sys.modules["fastavro"]

            # Import the function fresh
            from importlib import reload

            import lsst_extendedness.ingest.deserializer as deserializer_module

            # This should raise ImportError when called
            with pytest.raises(ImportError, match="fastavro is required"):
                deserializer_module.deserialize_avro(b"test_data")
        finally:
            builtins.__import__ = original_import


class TestDeserializeAvroTypeValidation:
    """Tests for type validation in deserialization."""

    def test_deserialize_non_dict_raises(self, mocker):
        """Test that non-dict deserialization result raises ValueError."""
        from lsst_extendedness.ingest.deserializer import deserialize_avro

        # Mock fastavro module
        mock_fastavro = mocker.MagicMock()
        # Return a list instead of dict
        mock_fastavro.reader.return_value = iter([[1, 2, 3]])
        mocker.patch.dict("sys.modules", {"fastavro": mock_fastavro})

        with pytest.raises(ValueError, match="Expected dict"):
            deserialize_avro(b"DATA")

    def test_deserialize_string_raises(self, mocker):
        """Test that string deserialization result raises ValueError."""
        from lsst_extendedness.ingest.deserializer import deserialize_avro

        # Mock fastavro module
        mock_fastavro = mocker.MagicMock()
        mock_fastavro.reader.return_value = iter(["not a dict"])
        mocker.patch.dict("sys.modules", {"fastavro": mock_fastavro})

        with pytest.raises(ValueError, match="Expected dict"):
            deserialize_avro(b"DATA")
