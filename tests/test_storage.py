"""
Tests for storage backends.

Tests the SQLiteStorage implementation for:
- Schema initialization
- Batch writes
- Queries
- State tracking
"""

from lsst_extendedness.models import IngestionRun, ProcessingResult
from lsst_extendedness.storage import SQLiteStorage


class TestSQLiteStorageInit:
    """Tests for SQLiteStorage initialization."""

    def test_create_new_database(self, temp_db):
        """Test creating a new database."""
        # temp_db fixture handles initialization
        assert temp_db.db_path.exists()

    def test_initialize_idempotent(self, temp_db):
        """Test that initialize() is safe to call multiple times."""
        # Should not raise
        temp_db.initialize()
        temp_db.initialize()

    def test_get_alert_count_empty(self, temp_db):
        """Test getting count from empty database."""
        assert temp_db.get_alert_count() == 0


class TestSQLiteStorageWrite:
    """Tests for write operations."""

    def test_write_batch_single(self, temp_db, alert_factory):
        """Test writing a single alert."""
        alert = alert_factory.create()

        count = temp_db.write_batch([alert])

        assert count == 1
        assert temp_db.get_alert_count() == 1

    def test_write_batch_multiple(self, temp_db, alert_factory):
        """Test writing multiple alerts."""
        alerts = alert_factory.create_batch(100)

        count = temp_db.write_batch(alerts)

        assert count == 100
        assert temp_db.get_alert_count() == 100

    def test_write_batch_empty(self, temp_db):
        """Test writing empty batch."""
        count = temp_db.write_batch([])

        assert count == 0

    def test_write_batch_duplicates_ignored(self, temp_db, alert_factory):
        """Test that duplicate alerts are ignored."""
        alert = alert_factory.create()

        temp_db.write_batch([alert])
        temp_db.write_batch([alert])  # Same alert again

        # Should only have one
        assert temp_db.get_alert_count() == 1

    def test_write_processing_result(self, temp_db):
        """Test writing a processing result."""
        result = ProcessingResult(
            processor_name="test_processor",
            processor_version="1.0.0",
            records=[{"id": 1}],
            summary="Test result",
        )

        result_id = temp_db.write_processing_result(result)

        assert result_id > 0

        # Query to verify
        rows = temp_db.query("SELECT * FROM processing_results WHERE id = ?", (result_id,))
        assert len(rows) == 1
        assert rows[0]["processor_name"] == "test_processor"

    def test_write_ingestion_run(self, temp_db):
        """Test writing an ingestion run."""
        run = IngestionRun(source_name="test")
        run.alerts_ingested = 50

        run_id = temp_db.write_ingestion_run(run)

        assert run_id > 0
        assert run.id == run_id

        # Query to verify
        rows = temp_db.query("SELECT * FROM ingestion_runs WHERE id = ?", (run_id,))
        assert len(rows) == 1
        assert rows[0]["alerts_ingested"] == 50

    def test_update_ingestion_run(self, temp_db):
        """Test updating an existing ingestion run."""
        run = IngestionRun(source_name="test")

        # Initial save
        temp_db.write_ingestion_run(run)
        original_id = run.id

        # Update
        run.alerts_ingested = 100
        run.complete()
        temp_db.write_ingestion_run(run)

        # Should have same ID
        assert run.id == original_id

        # Query to verify update
        rows = temp_db.query("SELECT * FROM ingestion_runs WHERE id = ?", (run.id,))
        assert rows[0]["alerts_ingested"] == 100
        assert rows[0]["status"] == "completed"


class TestSQLiteStorageQuery:
    """Tests for query operations."""

    def test_query_basic(self, populated_db):
        """Test basic query."""
        results = populated_db.query("SELECT * FROM alerts_raw LIMIT 10")

        assert len(results) == 10
        assert "alert_id" in results[0]

    def test_query_with_params(self, populated_db):
        """Test query with parameters."""
        results = populated_db.query("SELECT * FROM alerts_raw WHERE has_ss_source = ?", (1,))

        assert len(results) > 0
        for row in results:
            assert row["has_ss_source"] == 1

    def test_query_empty_result(self, temp_db):
        """Test query returning no results."""
        results = temp_db.query("SELECT * FROM alerts_raw WHERE alert_id = -1")

        assert results == []

    def test_execute(self, populated_db):
        """Test execute for non-query operations."""
        # Count before
        before = populated_db.get_alert_count()

        # Delete some alerts (use subquery instead of LIMIT on DELETE
        # which requires SQLITE_ENABLE_UPDATE_DELETE_LIMIT)
        populated_db.execute(
            "DELETE FROM alerts_raw WHERE rowid IN "
            "(SELECT rowid FROM alerts_raw WHERE has_ss_source = 0 LIMIT 5)"
        )

        # Should have deleted some
        after = populated_db.get_alert_count()
        assert after < before


class TestSQLiteStorageState:
    """Tests for state tracking operations."""

    def test_get_processed_source_not_found(self, temp_db):
        """Test getting non-existent processed source."""
        result = temp_db.get_processed_source(999999)

        assert result is None

    def test_update_processed_source_insert(self, temp_db):
        """Test inserting new processed source."""
        temp_db.update_processed_source(
            dia_source_id=12345,
            last_seen_mjd=60000.0,
            ss_object_id="SSO_123",
            reassoc_time=59999.0,
        )

        result = temp_db.get_processed_source(12345)

        assert result is not None
        assert result["dia_source_id"] == 12345
        assert result["last_seen_mjd"] == 60000.0
        assert result["ss_object_id"] == "SSO_123"
        assert result["observation_count"] == 1

    def test_update_processed_source_update(self, temp_db):
        """Test updating existing processed source."""
        # Insert
        temp_db.update_processed_source(
            dia_source_id=12345,
            last_seen_mjd=60000.0,
            ss_object_id="SSO_123",
            reassoc_time=59999.0,
        )

        # Update
        temp_db.update_processed_source(
            dia_source_id=12345,
            last_seen_mjd=60001.0,
            ss_object_id="SSO_123",
            reassoc_time=59999.0,
        )

        result = temp_db.get_processed_source(12345)

        assert result["last_seen_mjd"] == 60001.0
        assert result["observation_count"] == 2


class TestSQLiteStorageStats:
    """Tests for statistics operations."""

    def test_get_stats_empty(self, temp_db):
        """Test getting stats from empty database."""
        stats = temp_db.get_stats()

        assert stats["alerts_raw_count"] == 0
        assert "file_size_bytes" in stats

    def test_get_stats_populated(self, populated_db):
        """Test getting stats from populated database."""
        stats = populated_db.get_stats()

        assert stats["alerts_raw_count"] == 50
        assert stats["file_size_bytes"] > 0  # Use bytes for small test DBs


class TestSQLiteStorageViews:
    """Tests for database views."""

    def test_view_point_sources(self, populated_db):
        """Test point sources view."""
        results = populated_db.query("SELECT * FROM v_point_sources")

        for row in results:
            assert row["extendedness_median"] < 0.3

    def test_view_extended_sources(self, populated_db):
        """Test extended sources view."""
        results = populated_db.query("SELECT * FROM v_extended_sources")

        for row in results:
            assert row["extendedness_median"] > 0.7

    def test_view_minimoon_candidates(self, populated_db):
        """Test minimoon candidates view."""
        results = populated_db.query("SELECT * FROM v_minimoon_candidates")

        for row in results:
            assert row["has_ss_source"] == 1
            assert 0.3 <= row["extendedness_median"] <= 0.7

    def test_view_sso_alerts(self, populated_db):
        """Test SSO alerts view."""
        results = populated_db.query("SELECT * FROM v_sso_alerts")

        for row in results:
            assert row["has_ss_source"] == 1


class TestSQLiteStorageProcessing:
    """Tests for processing-related operations."""

    def test_get_alerts_for_processing(self, populated_db):
        """Test getting alerts for processing."""
        alerts = populated_db.get_alerts_for_processing(window_days=30)

        # Should return some alerts
        assert len(alerts) > 0
        # All should be dicts
        for alert in alerts:
            assert isinstance(alert, dict)
            assert "alert_id" in alert or "id" in alert

    def test_get_alerts_for_processing_with_limit(self, populated_db):
        """Test getting alerts for processing with limit."""
        alerts = populated_db.get_alerts_for_processing(window_days=30, limit=5)

        assert len(alerts) <= 5

    def test_vacuum(self, populated_db):
        """Test vacuum optimization."""
        # Just verify it doesn't error
        populated_db.vacuum()

        # Verify database still works after vacuum
        count = populated_db.get_alert_count()
        assert count == 50


class TestSQLiteStorageBackup:
    """Tests for backup operations."""

    def test_backup(self, populated_db, tmp_path):
        """Test creating a backup."""
        backup_path = tmp_path / "backup.db"

        populated_db.backup(backup_path)

        assert backup_path.exists()

        # Verify backup is valid
        backup_storage = SQLiteStorage(backup_path)
        backup_storage.initialize()
        assert backup_storage.get_alert_count() == populated_db.get_alert_count()
        backup_storage.close()


class TestSQLiteStorageContextManager:
    """Tests for context manager usage."""

    def test_context_manager(self, tmp_path):
        """Test using storage as context manager."""
        db_path = tmp_path / "test.db"

        with SQLiteStorage(db_path) as storage:
            storage.initialize()
            assert storage.get_alert_count() == 0

        # Connection should be closed
        assert storage._connection is None


class TestSchemaFunctions:
    """Tests for schema module functions."""

    def test_get_schema_sql(self):
        """Test getting complete schema SQL."""
        from lsst_extendedness.storage.schema import SCHEMA_VERSION, get_schema_sql

        sql = get_schema_sql()

        assert isinstance(sql, str)
        assert "CREATE TABLE" in sql
        assert "CREATE INDEX" in sql
        assert "CREATE VIEW" in sql
        assert "CREATE TRIGGER" in sql
        assert str(SCHEMA_VERSION) in sql

    def test_create_schema_without_triggers(self, tmp_path):
        """Test create_schema with triggers disabled."""
        import sqlite3

        from lsst_extendedness.storage.schema import create_schema

        db_path = tmp_path / "no_triggers.db"
        conn = sqlite3.connect(db_path)

        # Create without triggers
        create_schema(conn, include_triggers=False)

        # Tables should exist
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        assert "alerts_raw" in tables
        assert "processing_results" in tables

        # Trigger should not exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        triggers = [row[0] for row in cursor.fetchall()]
        assert len(triggers) == 0

        conn.close()

    def test_get_schema_version(self, tmp_path):
        """Test getting schema version."""
        import sqlite3

        from lsst_extendedness.storage.schema import (
            SCHEMA_VERSION,
            create_schema,
            get_schema_version,
        )

        db_path = tmp_path / "versioned.db"
        conn = sqlite3.connect(db_path)

        # Before schema creation, version should be None
        assert get_schema_version(conn) is None

        # Create schema
        create_schema(conn)

        # Version should be current
        version = get_schema_version(conn)
        assert version == SCHEMA_VERSION

        conn.close()

    def test_needs_migration_fresh_db(self, tmp_path):
        """Test needs_migration with fresh database."""
        import sqlite3

        from lsst_extendedness.storage.schema import needs_migration

        db_path = tmp_path / "fresh.db"
        conn = sqlite3.connect(db_path)

        # Fresh DB needs migration (no schema)
        assert needs_migration(conn) is True

        conn.close()

    def test_needs_migration_current(self, tmp_path):
        """Test needs_migration with current schema."""
        import sqlite3

        from lsst_extendedness.storage.schema import create_schema, needs_migration

        db_path = tmp_path / "current.db"
        conn = sqlite3.connect(db_path)

        # Create current schema
        create_schema(conn)

        # Should not need migration
        assert needs_migration(conn) is False

        conn.close()

    def test_migrate_fresh_db(self, tmp_path):
        """Test migrate on fresh database."""
        import sqlite3

        from lsst_extendedness.storage.schema import (
            SCHEMA_VERSION,
            get_schema_version,
            migrate,
        )

        db_path = tmp_path / "to_migrate.db"
        conn = sqlite3.connect(db_path)

        # Should create schema on fresh DB
        migrate(conn)

        # Schema should be at current version
        assert get_schema_version(conn) == SCHEMA_VERSION

        conn.close()

    def test_migrate_old_version(self, tmp_path):
        """Test migrate from older schema version."""
        import sqlite3

        from lsst_extendedness.storage.schema import (
            SCHEMA_VERSION,
            create_schema,
            get_schema_version,
            migrate,
        )

        db_path = tmp_path / "old.db"
        conn = sqlite3.connect(db_path)

        # Create current schema first
        create_schema(conn)

        # Manually set to old version
        conn.execute("UPDATE schema_info SET value = '0' WHERE key = 'version'")
        conn.commit()

        assert get_schema_version(conn) == 0

        # Migrate should update to current version
        migrate(conn)

        assert get_schema_version(conn) == SCHEMA_VERSION

        conn.close()
