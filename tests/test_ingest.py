"""
Tests for ingestion pipeline.
"""

from __future__ import annotations

import pytest

from lsst_extendedness.ingest.deserializer import (
    AlertDeserializer,
    extract_schema_id,
)
from lsst_extendedness.ingest.pipeline import (
    IngestionPipeline,
    PipelineOptions,
    PipelineStats,
)
from lsst_extendedness.ingest.state import StateTracker
from lsst_extendedness.sources.mock import MockSource
from lsst_extendedness.storage.sqlite import SQLiteStorage


class TestPipelineStats:
    """Tests for PipelineStats."""

    def test_empty_stats(self):
        """Test empty stats."""
        stats = PipelineStats()

        assert stats.alerts_received == 0
        assert stats.alerts_stored == 0
        assert stats.success_rate == 0.0
        assert stats.alerts_per_second == 0.0

    def test_success_rate(self):
        """Test success rate calculation."""
        stats = PipelineStats(
            alerts_received=100,
            alerts_stored=95,
            alerts_failed=5,
        )

        assert stats.success_rate == 95.0

    def test_alerts_per_second(self):
        """Test processing rate calculation."""
        stats = PipelineStats(
            alerts_stored=1000,
            elapsed_seconds=10.0,
        )

        assert stats.alerts_per_second == 100.0


class TestPipelineOptions:
    """Tests for PipelineOptions."""

    def test_default_options(self):
        """Test default options."""
        options = PipelineOptions()

        assert options.batch_size == 500
        assert options.max_alerts is None
        assert options.store_cutouts is True
        assert options.skip_duplicates is True
        assert options.track_state is True
        assert options.dry_run is False

    def test_custom_options(self):
        """Test custom options."""
        options = PipelineOptions(
            batch_size=100,
            max_alerts=1000,
            dry_run=True,
        )

        assert options.batch_size == 100
        assert options.max_alerts == 1000
        assert options.dry_run is True


class TestIngestionPipeline:
    """Tests for IngestionPipeline."""

    def test_pipeline_with_mock_source(self, temp_db):
        """Test pipeline with mock source."""
        source = MockSource(count=50, seed=42)

        options = PipelineOptions(
            batch_size=10,
            max_alerts=50,
            track_state=False,  # Disable state tracking for simpler test
        )

        pipeline = IngestionPipeline(source, temp_db, options)

        with pipeline:
            stats = pipeline.run()

        assert stats.alerts_received == 50
        assert stats.alerts_stored == 50
        assert stats.alerts_failed == 0
        assert stats.batches_written == 5  # 50 / 10

    def test_pipeline_dry_run(self, temp_db):
        """Test pipeline in dry run mode."""
        source = MockSource(count=20)

        options = PipelineOptions(dry_run=True, track_state=False)

        pipeline = IngestionPipeline(source, temp_db, options)

        with pipeline:
            stats = pipeline.run()

        # Should report success but not write
        assert stats.alerts_received == 20
        assert stats.alerts_stored == 20

        # Verify nothing written
        db_stats = temp_db.get_stats()
        assert db_stats.get("alerts_raw_count", 0) == 0

    def test_pipeline_max_alerts(self, temp_db):
        """Test pipeline with max_alerts limit."""
        source = MockSource(count=100)

        options = PipelineOptions(max_alerts=25, track_state=False)

        pipeline = IngestionPipeline(source, temp_db, options)

        with pipeline:
            stats = pipeline.run()

        assert stats.alerts_received == 25
        assert stats.alerts_stored == 25

    def test_run_ingestion_convenience(self, temp_db):
        """Test run_ingestion convenience function."""
        source = MockSource(count=30)

        # Use context manager approach
        source.connect()
        try:
            options = PipelineOptions(
                batch_size=10,
                max_alerts=30,
                track_state=False,
            )
            pipeline = IngestionPipeline(source, temp_db, options)
            temp_db.initialize()
            stats = pipeline.run()
        finally:
            source.close()

        assert stats.alerts_stored == 30


class TestStateTracker:
    """Tests for StateTracker."""

    def test_source_state_tracking(self, temp_db):
        """Test tracking source state."""
        tracker = StateTracker(temp_db)

        # Initially no state
        state = tracker.get_source_state(12345)
        assert state is None

        # Update state
        tracker.update_source_state(
            dia_source_id=12345,
            mjd=60000.0,
            _alert_id=1001,
            ss_object_id="SSO_123",
        )

        # Retrieve state
        state = tracker.get_source_state(12345)
        assert state is not None
        assert state.dia_source_id == 12345
        assert state.first_seen_mjd == 60000.0
        assert state.ss_object_id == "SSO_123"

    def test_kafka_offset_tracking(self, temp_db):
        """Test Kafka offset tracking."""
        tracker = StateTracker(temp_db)

        # Initially no offset
        offset = tracker.get_kafka_offset("test-topic", 0)
        assert offset is None

        # Save offset
        tracker.save_kafka_offset("test-topic", 0, 1000)

        # Retrieve offset
        offset = tracker.get_kafka_offset("test-topic", 0)
        assert offset == 1000

        # Update offset
        tracker.save_kafka_offset("test-topic", 0, 2000)
        offset = tracker.get_kafka_offset("test-topic", 0)
        assert offset == 2000

    def test_source_state_update(self, temp_db):
        """Test updating source state multiple times."""
        tracker = StateTracker(temp_db)

        # First observation
        tracker.update_source_state(
            dia_source_id=99999,
            mjd=60000.0,
            _alert_id=1,
        )

        state = tracker.get_source_state(99999)
        assert state.first_seen_mjd == 60000.0
        assert state.last_seen_mjd == 60000.0

        # Second observation (later)
        tracker.update_source_state(
            dia_source_id=99999,
            mjd=60001.0,
            _alert_id=2,
        )

        state = tracker.get_source_state(99999)
        assert state.first_seen_mjd == 60000.0  # Should stay same
        assert state.last_seen_mjd == 60001.0  # Should update


class TestDeserializer:
    """Tests for AVRO deserialization."""

    def test_extract_schema_id_confluent(self):
        """Test extracting schema ID from Confluent format."""
        # Confluent wire format: [0x00] [4-byte schema ID] [data]
        data = b"\x00\x00\x00\x00\x42rest_of_data"

        schema_id = extract_schema_id(data)
        assert schema_id == 66  # 0x42

    def test_extract_schema_id_non_confluent(self):
        """Test with non-Confluent format."""
        data = b"SIMPLE  = T"  # Regular FITS-like data

        schema_id = extract_schema_id(data)
        assert schema_id is None

    def test_alert_deserializer_batch(self):
        """Test batch deserialization."""
        deserializer = AlertDeserializer()

        # With no schema, batch should return empty (can't deserialize)
        # This tests the error handling path
        messages = [b"invalid1", b"invalid2"]
        alerts = deserializer.deserialize_batch(messages)

        # Should handle errors gracefully
        assert alerts == []


class TestPipelineDuplicateHandling:
    """Tests for duplicate detection and handling."""

    def test_skip_duplicates_enabled(self, temp_db):
        """Test that duplicates are skipped when enabled."""
        source = MockSource(count=20, seed=42)

        # First run
        options = PipelineOptions(batch_size=10, track_state=True)
        pipeline = IngestionPipeline(source, temp_db, options)

        with pipeline:
            stats1 = pipeline.run()

        assert stats1.alerts_stored == 20

        # Second run with same source (same seed = same alert_ids)
        source2 = MockSource(count=20, seed=42)
        pipeline2 = IngestionPipeline(source2, temp_db, options)

        with pipeline2:
            stats2 = pipeline2.run()

        # All should be skipped as duplicates
        assert stats2.alerts_received == 20
        assert stats2.alerts_stored == 0

    def test_pipeline_writes_new_alerts(self, temp_db):
        """Test that different alerts are written successfully.

        Note: The MockSource generates alert_ids based on index (1000000 + index),
        not on seed. Different seeds only affect random values like coordinates.
        """
        source = MockSource(count=10, seed=42)

        # First run
        options = PipelineOptions(batch_size=10, skip_duplicates=False, track_state=False)
        pipeline = IngestionPipeline(source, temp_db, options)

        with pipeline:
            stats = pipeline.run()

        # Should store all alerts
        assert stats.alerts_stored == 10

        # Verify in DB
        db_stats = temp_db.get_stats()
        assert db_stats.get("alerts_raw_count", 0) == 10


class TestPipelineReassociations:
    """Tests for reassociation tracking."""

    def test_reassociation_counting(self, temp_db, mocker):
        """Test that reassociations are counted."""
        # Create mock source that yields alerts with reassociations
        source = MockSource(count=10, seed=42)
        source.connect()

        # Patch the alerts to have some reassociations
        original_fetch = source.fetch_alerts

        def patched_fetch(limit=None):
            for i, alert in enumerate(original_fetch(limit)):
                if i < 3:  # First 3 alerts are reassociations
                    alert.is_reassociation = True
                    alert.reassociation_reason = "test"
                yield alert

        mocker.patch.object(source, "fetch_alerts", patched_fetch)

        options = PipelineOptions(batch_size=10, track_state=False)
        pipeline = IngestionPipeline(source, temp_db, options)
        temp_db.initialize()

        stats = pipeline.run()

        assert stats.reassociations == 3
        source.close()


class TestPipelineErrorHandling:
    """Tests for pipeline error handling."""

    def test_batch_write_error(self, temp_db, mocker):
        """Test handling of batch write errors."""
        source = MockSource(count=10, seed=42)

        # Patch storage to fail on write
        mocker.patch.object(temp_db, "write_batch", side_effect=Exception("Database error"))

        options = PipelineOptions(batch_size=5, track_state=False)
        pipeline = IngestionPipeline(source, temp_db, options)

        with pipeline:
            stats = pipeline.run()

        # Should have processed but failed to write
        assert stats.alerts_received == 10
        assert stats.alerts_stored == 0
        assert stats.alerts_failed == 10  # 2 batches of 5

    def test_pipeline_exception_records_failure(self, temp_db, mocker):
        """Test that pipeline exceptions are recorded."""
        source = MockSource(count=10, seed=42)

        # Patch to raise exception during fetch
        mocker.patch.object(source, "fetch_alerts", side_effect=Exception("Connection lost"))

        options = PipelineOptions(track_state=False)
        pipeline = IngestionPipeline(source, temp_db, options)

        with pytest.raises(Exception, match="Connection lost"), pipeline:
            pipeline.run()


class TestPipelineStateTracking:
    """Tests for state tracking integration."""

    def test_state_tracker_integration(self, temp_db):
        """Test that state tracker is used during pipeline run."""
        source = MockSource(count=5, seed=42)

        options = PipelineOptions(batch_size=5, track_state=True)
        pipeline = IngestionPipeline(source, temp_db, options)

        with pipeline:
            stats = pipeline.run()

        # Should have stored alerts
        assert stats.alerts_stored == 5

        # Either all new or all updated depending on prior state
        total_tracked = stats.new_sources + stats.updated_sources
        assert total_tracked == 5

    def test_state_tracker_disabled(self, temp_db):
        """Test pipeline runs correctly without state tracking."""
        source = MockSource(count=5, seed=42)

        options = PipelineOptions(batch_size=5, track_state=False)
        pipeline = IngestionPipeline(source, temp_db, options)

        with pipeline:
            stats = pipeline.run()

        # Should store alerts
        assert stats.alerts_stored == 5

        # No state tracking means no new/updated counts
        assert stats.new_sources == 0
        assert stats.updated_sources == 0


class TestStateTrackerAdvanced:
    """Additional tests for StateTracker functionality."""

    def test_get_all_kafka_state(self, temp_db):
        """Test getting all Kafka state entries."""
        tracker = StateTracker(temp_db)

        # Save multiple offsets
        tracker.save_kafka_offset("topic1", 0, 100)
        tracker.save_kafka_offset("topic1", 1, 200)
        tracker.save_kafka_offset("topic2", 0, 300)

        states = tracker.get_all_kafka_state()

        assert len(states) == 3
        # Verify each state has expected attributes
        offsets = {(s.topic, s.partition): s.offset for s in states}
        assert offsets[("topic1", 0)] == 100
        assert offsets[("topic1", 1)] == 200
        assert offsets[("topic2", 0)] == 300

    def test_get_sources_in_window(self, temp_db):
        """Test getting sources within a time window."""
        tracker = StateTracker(temp_db)

        # Create sources with different observation times
        tracker.update_source_state(dia_source_id=1, mjd=60000.0, _alert_id=1)
        tracker.update_source_state(dia_source_id=2, mjd=60005.0, _alert_id=2)
        tracker.update_source_state(dia_source_id=3, mjd=60010.0, _alert_id=3)
        tracker.update_source_state(dia_source_id=4, mjd=60015.0, _alert_id=4)

        # Query a window that should include sources 2 and 3
        sources = tracker.get_sources_in_window(60003.0, 60012.0)

        # Should get sources with last_seen_mjd >= 60003 and first_seen_mjd <= 60012
        source_ids = [s.dia_source_id for s in sources]
        assert 2 in source_ids
        assert 3 in source_ids

    def test_cleanup_old_state(self, temp_db, mocker):
        """Test cleanup of old state entries."""
        tracker = StateTracker(temp_db)

        # Create sources with different ages
        tracker.update_source_state(dia_source_id=1, mjd=60000.0, _alert_id=1)  # Old
        tracker.update_source_state(dia_source_id=2, mjd=60003.0, _alert_id=2)  # Old
        tracker.update_source_state(dia_source_id=3, mjd=60010.0, _alert_id=3)  # Recent

        # Mock the days_ago_mjd at the utils level where it's imported from
        mocker.patch(
            "lsst_extendedness.utils.time.days_ago_mjd",
            return_value=60005.0,
        )

        # Cleanup entries older than threshold
        removed = tracker.cleanup_old_state(days=90)

        # Should have removed 2 entries (sources 1 and 2)
        assert removed == 2

        # Verify source 3 still exists
        state = tracker.get_source_state(3)
        assert state is not None
        assert state.dia_source_id == 3


class TestRunIngestionFunction:
    """Tests for run_ingestion convenience function."""

    def test_run_ingestion(self, temp_db):
        """Test the run_ingestion convenience function."""
        from lsst_extendedness.ingest.pipeline import run_ingestion

        source = MockSource(count=15, seed=42)

        stats = run_ingestion(
            source,
            temp_db,
            batch_size=5,
            max_alerts=15,
            dry_run=False,
        )

        assert stats.alerts_received == 15
        assert stats.alerts_stored == 15

    def test_run_ingestion_dry_run(self, temp_db):
        """Test run_ingestion in dry run mode."""
        from lsst_extendedness.ingest.pipeline import run_ingestion

        source = MockSource(count=10, seed=42)

        stats = run_ingestion(
            source,
            temp_db,
            dry_run=True,
        )

        assert stats.alerts_stored == 10

        # Verify nothing written
        db_stats = temp_db.get_stats()
        assert db_stats.get("alerts_raw_count", 0) == 0


# Fixtures


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database for testing."""
    db_path = tmp_path / "test.db"
    storage = SQLiteStorage(db_path)
    storage.initialize()
    yield storage
    storage.close()
