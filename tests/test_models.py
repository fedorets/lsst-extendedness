"""
Tests for data models.

Tests the Pydantic models for:
- AlertRecord validation and conversion
- ProcessingResult handling
- IngestionRun lifecycle
"""

import pytest

from lsst_extendedness.models import AlertRecord, IngestionRun, ProcessingResult
from lsst_extendedness.models.runs import RunStatus


class TestAlertRecord:
    """Tests for AlertRecord model."""

    def test_create_minimal(self):
        """Test creating alert with minimal required fields."""
        alert = AlertRecord(
            alert_id=1,
            dia_source_id=1000,
            ra=180.0,
            dec=45.0,
            mjd=60000.0,
        )

        assert alert.alert_id == 1
        assert alert.dia_source_id == 1000
        assert alert.ra == 180.0
        assert alert.dec == 45.0
        assert alert.mjd == 60000.0

    def test_create_with_all_fields(self, alert_factory):
        """Test creating alert with all fields."""
        alert = alert_factory.create(
            filter_name="r",
            snr=150.0,
            has_ss_source=True,
            ss_object_id="SSO_123",
        )

        assert alert.filter_name == "r"
        assert alert.snr == 150.0
        assert alert.has_ss_source is True
        assert alert.ss_object_id == "SSO_123"

    def test_ra_validation(self):
        """Test RA must be 0-360."""
        with pytest.raises(ValueError):
            AlertRecord(
                alert_id=1,
                dia_source_id=1,
                ra=400.0,  # Invalid
                dec=45.0,
                mjd=60000.0,
            )

    def test_dec_validation(self):
        """Test Dec must be -90 to 90."""
        with pytest.raises(ValueError):
            AlertRecord(
                alert_id=1,
                dia_source_id=1,
                ra=180.0,
                dec=100.0,  # Invalid
                mjd=60000.0,
            )

    def test_extendedness_validation(self):
        """Test extendedness must be 0-1."""
        with pytest.raises(ValueError):
            AlertRecord(
                alert_id=1,
                dia_source_id=1,
                ra=180.0,
                dec=45.0,
                mjd=60000.0,
                extendedness_median=1.5,  # Invalid
            )

    def test_filter_name_normalization(self):
        """Test filter name is normalized to lowercase."""
        alert = AlertRecord(
            alert_id=1,
            dia_source_id=1,
            ra=180.0,
            dec=45.0,
            mjd=60000.0,
            filter_name="G",  # Uppercase
        )

        assert alert.filter_name == "g"

    def test_from_avro(self, sample_avro_record):
        """Test creating from AVRO record."""
        alert = AlertRecord.from_avro(sample_avro_record)

        assert alert.alert_id == 123456789
        assert alert.dia_source_id == 987654321
        assert alert.ra == 180.12345
        assert alert.dec == 45.67890
        assert alert.filter_name == "r"
        assert alert.has_ss_source is True
        assert alert.ss_object_id == "SSO_2024_AB123"

    def test_from_avro_no_sso(self, sample_avro_no_sso):
        """Test creating from AVRO record without SSObject."""
        alert = AlertRecord.from_avro(sample_avro_no_sso)

        assert alert.has_ss_source is False
        assert alert.ss_object_id is None

    def test_from_avro_extracts_trail_data(self, sample_avro_record):
        """Test that trail fields are extracted."""
        sample_avro_record["diaSource"]["trailLength"] = 15.5
        sample_avro_record["diaSource"]["trailAngle"] = 45.2

        alert = AlertRecord.from_avro(sample_avro_record)

        assert "trailLength" in alert.trail_data
        assert alert.trail_data["trailLength"] == 15.5

    def test_from_avro_extracts_pixel_flags(self, sample_avro_record):
        """Test that pixel flags are extracted."""
        sample_avro_record["diaSource"]["pixelFlagsCr"] = True

        alert = AlertRecord.from_avro(sample_avro_record)

        assert "pixelFlagsCr" in alert.pixel_flags
        assert alert.pixel_flags["pixelFlagsCr"] is True

    def test_to_db_dict(self, alert_factory):
        """Test conversion to database dictionary."""
        alert = alert_factory.create(
            trail_data={"trailLength": 10.0},
            pixel_flags={"pixelFlagsBad": False},
        )

        db_dict = alert.to_db_dict()

        assert isinstance(db_dict, dict)
        assert db_dict["alert_id"] == alert.alert_id
        # JSON fields should be strings
        assert isinstance(db_dict["trail_data"], str)
        assert isinstance(db_dict["pixel_flags"], str)

    def test_from_db_row(self, alert_factory):
        """Test round-trip through database format."""
        original = alert_factory.create(
            trail_data={"test": "value"},
            pixel_flags={"flag": True},
        )

        db_dict = original.to_db_dict()
        restored = AlertRecord.from_db_row(db_dict)

        assert restored.alert_id == original.alert_id
        assert restored.trail_data == original.trail_data
        assert restored.pixel_flags == original.pixel_flags


class TestProcessingResult:
    """Tests for ProcessingResult model."""

    def test_create_minimal(self):
        """Test creating with minimal fields."""
        result = ProcessingResult(
            processor_name="test",
            processor_version="1.0.0",
        )

        assert result.processor_name == "test"
        assert result.processor_version == "1.0.0"
        assert result.records == []
        assert result.summary == ""

    def test_create_with_records(self):
        """Test creating with result records."""
        records = [
            {"candidate_id": 1, "score": 0.95},
            {"candidate_id": 2, "score": 0.87},
        ]

        result = ProcessingResult(
            processor_name="detector",
            processor_version="2.0.0",
            records=records,
            summary="Found 2 candidates",
        )

        assert len(result.records) == 2
        assert result.records[0]["score"] == 0.95
        assert result.summary == "Found 2 candidates"

    def test_to_db_dict(self):
        """Test conversion to database dictionary."""
        result = ProcessingResult(
            processor_name="test",
            processor_version="1.0.0",
            records=[{"key": "value"}],
            metadata={"run_id": "abc123"},
        )

        db_dict = result.to_db_dict()

        assert isinstance(db_dict["records"], str)
        assert isinstance(db_dict["metadata"], str)

    def test_from_db_row(self):
        """Test round-trip through database format."""
        original = ProcessingResult(
            processor_name="test",
            processor_version="1.0.0",
            records=[{"a": 1}],
            metadata={"b": 2},
        )

        db_dict = original.to_db_dict()
        restored = ProcessingResult.from_db_row(db_dict)

        assert restored.records == original.records
        assert restored.metadata == original.metadata


class TestIngestionRun:
    """Tests for IngestionRun model."""

    def test_create_default(self):
        """Test creating with defaults."""
        run = IngestionRun(source_name="kafka")

        assert run.source_name == "kafka"
        assert run.status == RunStatus.RUNNING
        assert run.alerts_ingested == 0
        assert run.is_running is True

    def test_complete_success(self):
        """Test completing a run successfully."""
        run = IngestionRun(source_name="kafka")
        run.alerts_ingested = 100

        run.complete()

        assert run.status == RunStatus.COMPLETED
        assert run.is_complete is True
        assert run.completed_at is not None

    def test_complete_failure(self):
        """Test completing a run with failure."""
        run = IngestionRun(source_name="kafka")

        run.complete(error="Connection lost")

        assert run.status == RunStatus.FAILED
        assert run.error_message == "Connection lost"

    def test_fail_helper(self):
        """Test fail() helper method."""
        run = IngestionRun(source_name="kafka")

        run.fail("Something went wrong")

        assert run.status == RunStatus.FAILED
        assert run.error_message == "Something went wrong"

    def test_cancel(self):
        """Test cancelling a run."""
        run = IngestionRun(source_name="kafka")

        run.cancel()

        assert run.status == RunStatus.CANCELLED

    def test_duration_seconds(self):
        """Test duration calculation."""
        run = IngestionRun(source_name="kafka")

        # Not complete yet
        assert run.duration_seconds is None

        run.complete()

        # Should have some duration
        assert run.duration_seconds is not None
        assert run.duration_seconds >= 0

    def test_processing_rate(self):
        """Test processing rate calculation."""
        run = IngestionRun(source_name="kafka")
        run.alerts_ingested = 1000

        run.complete()

        if run.duration_seconds and run.duration_seconds > 0:
            assert run.processing_rate is not None
            assert run.processing_rate > 0

    def test_success_rate(self):
        """Test success rate calculation."""
        run = IngestionRun(source_name="kafka")
        run.alerts_ingested = 90
        run.alerts_failed = 10

        assert run.success_rate == 90.0

    def test_success_rate_no_alerts(self):
        """Test success rate with no alerts."""
        run = IngestionRun(source_name="kafka")

        assert run.success_rate == 100.0

    def test_summary_dict(self):
        """Test summary dictionary generation."""
        run = IngestionRun(source_name="kafka")
        run.alerts_ingested = 100
        run.new_sources = 50
        run.complete()

        summary = run.summary_dict()

        assert summary["source"] == "kafka"
        assert summary["alerts_ingested"] == 100
        assert summary["new_sources"] == 50
        assert summary["status"] == "completed"

    def test_to_db_dict(self):
        """Test conversion to database dictionary."""
        run = IngestionRun(
            source_name="kafka",
            source_config={"topic": "test"},
            metadata={"version": "2.0.0"},
        )

        db_dict = run.to_db_dict()

        assert isinstance(db_dict["source_config"], str)
        assert isinstance(db_dict["metadata"], str)
        assert "id" not in db_dict  # ID excluded

    def test_from_db_row(self):
        """Test creating IngestionRun from database row."""
        from lsst_extendedness.models.runs import RunStatus

        # Create original with various fields
        original = IngestionRun(
            source_name="kafka",
            source_config={"topic": "alerts", "group_id": "test"},
            metadata={"version": "1.0.0", "host": "server1"},
        )
        original.id = 42
        original.alerts_ingested = 1000
        original.alerts_failed = 5
        original.new_sources = 500
        original.reassociations_detected = 10
        original.cutouts_saved = 100
        original.complete()

        # Convert to DB dict and back
        db_dict = original.to_db_dict()
        db_dict["id"] = 42  # ID would come from DB

        restored = IngestionRun.from_db_row(db_dict)

        assert restored.id == 42
        assert restored.source_name == "kafka"
        assert restored.source_config == {"topic": "alerts", "group_id": "test"}
        assert restored.metadata == {"version": "1.0.0", "host": "server1"}
        assert restored.alerts_ingested == 1000
        assert restored.alerts_failed == 5
        assert restored.status == RunStatus.COMPLETED

    def test_from_db_row_with_dict_already_parsed(self):
        """Test from_db_row when JSON fields are already dicts."""
        db_dict = {
            "id": 1,
            "source_name": "file",
            "source_config": {"path": "/data"},  # Already a dict
            "metadata": {"key": "value"},  # Already a dict
            "status": "running",
            "alerts_ingested": 50,
            "alerts_failed": 0,
            "new_sources": 25,
            "reassociations_detected": 0,
            "cutouts_saved": 0,
        }

        restored = IngestionRun.from_db_row(db_dict)

        assert restored.source_config == {"path": "/data"}
        assert restored.metadata == {"key": "value"}
