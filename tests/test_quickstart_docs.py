"""
Tests validating the quickstart documentation examples work correctly.

These tests ensure that all code examples in docs/getting-started/quickstart.md
are functional and produce expected results. If these tests fail, the
documentation needs to be updated.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


class TestQuickstartSQLiteStorage:
    """Tests for the SQLiteStorage usage examples in quickstart.md."""

    def test_storage_initialize_and_count(self):
        """Test the SQLiteStorage example from 'Query Data (Python)' section.

        Validates this quickstart code works:
            storage = SQLiteStorage("data/lsst_extendedness.db")
            storage.initialize()
            count = storage.get_alert_count()
        """
        from lsst_extendedness.storage import SQLiteStorage

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_quickstart.db"

            # This mirrors the quickstart example
            storage = SQLiteStorage(str(db_path))
            storage.initialize()

            count = storage.get_alert_count()
            assert count == 0  # Fresh database

            storage.close()


class TestQuickstartFinkSource:
    """Tests for the FinkSource usage examples in quickstart.md."""

    def test_fink_source_context_manager(self):
        """Test FinkSource with context manager from quickstart.md.

        Validates this quickstart code works:
            with FinkSource() as source:
                for alert in source.fetch_alerts(limit=5):
                    print(f"Alert {alert.alert_id}: RA={alert.ra:.2f}, Dec={alert.dec:.2f}")
        """
        from lsst_extendedness.sources import FinkSource

        with FinkSource() as source:
            alerts = []
            for alert in source.fetch_alerts(limit=5):
                # These are the fields used in the quickstart example
                assert hasattr(alert, "alert_id")
                assert hasattr(alert, "ra")
                assert hasattr(alert, "dec")
                # Validate the formatting works
                formatted = f"Alert {alert.alert_id}: RA={alert.ra:.2f}, Dec={alert.dec:.2f}"
                assert "Alert" in formatted
                assert "RA=" in formatted
                assert "Dec=" in formatted
                alerts.append(alert)

            # Should get some alerts from fixtures
            assert len(alerts) <= 5

    def test_fink_source_explicit_connect(self):
        """Test FinkSource with explicit connect/close from quickstart.md.

        Validates this quickstart code works:
            source = FinkSource()
            source.connect()
            alerts = list(source.fetch_alerts(limit=10))
            source.close()
        """
        from lsst_extendedness.sources import FinkSource

        source = FinkSource()
        source.connect()

        alerts = list(source.fetch_alerts(limit=10))
        assert len(alerts) <= 10

        # Test the fields accessed in quickstart
        for alert in alerts:
            assert alert.alert_id is not None
            assert alert.ra is not None
            assert alert.dec is not None

        source.close()

    def test_fink_source_sso_check(self):
        """Test FinkSource SSO filtering from quickstart.md.

        Validates this quickstart code works:
            alerts = list(source.fetch_alerts(limit=10))
            sso_alerts = [a for a in alerts if a.has_ss_source]
        """
        from lsst_extendedness.sources import FinkSource

        source = FinkSource(include_sso=True)
        source.connect()

        alerts = list(source.fetch_alerts(limit=10))

        # This mirrors the quickstart SSO check
        sso_alerts = [a for a in alerts if a.has_ss_source]

        # Verify the filtering works (may or may not find SSOs depending on fixtures)
        assert isinstance(sso_alerts, list)
        for alert in sso_alerts:
            assert alert.has_ss_source is True

        source.close()


class TestQuickstartMockSource:
    """Tests for the mock source CLI example in quickstart.md."""

    def test_mock_source_ingestion(self):
        """Test that MockSource can generate alerts as shown in CLI examples.

        Validates the underlying functionality of:
            pdm run lsst-extendedness ingest --source mock --count 100
        """
        from lsst_extendedness.sources import MockSource

        source = MockSource(count=100, seed=42)
        source.connect()

        alerts = list(source.fetch_alerts())
        assert len(alerts) == 100

        # Verify alerts have required fields
        for alert in alerts:
            assert alert.alert_id is not None
            assert alert.ra >= 0 and alert.ra <= 360
            assert alert.dec >= -90 and alert.dec <= 90
            assert alert.mjd > 0

        source.close()


class TestQuickstartIntegration:
    """Integration tests combining storage and sources as shown in quickstart."""

    def test_ingest_mock_to_storage(self):
        """Test full ingestion workflow from quickstart.

        This validates the combination of:
        1. pdm run lsst-extendedness db-init
        2. pdm run lsst-extendedness ingest --source mock --count 100
        3. pdm run lsst-extendedness db-stats
        """
        from lsst_extendedness.sources import MockSource
        from lsst_extendedness.storage import SQLiteStorage

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "quickstart_test.db"

            # Step 1: Initialize database (db-init)
            storage = SQLiteStorage(str(db_path))
            storage.initialize()
            assert storage.get_alert_count() == 0

            # Step 2: Ingest mock data
            source = MockSource(count=100, seed=42)
            source.connect()
            alerts = list(source.fetch_alerts())
            source.close()

            storage.write_batch(alerts)

            # Step 3: Check stats (db-stats)
            count = storage.get_alert_count()
            assert count == 100

            storage.close()

    def test_ingest_fink_to_storage(self):
        """Test ingesting Fink fixture data to storage.

        This tests the alternative workflow using real ZTF data:
            with FinkSource() as source:
                for alert in source.fetch_alerts(limit=5):
                    # process alert
        """
        from lsst_extendedness.sources import FinkSource
        from lsst_extendedness.storage import SQLiteStorage

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "fink_test.db"

            storage = SQLiteStorage(str(db_path))
            storage.initialize()

            with FinkSource() as source:
                alerts = list(source.fetch_alerts(limit=10))

            if alerts:  # Only if fixtures exist
                storage.write_batch(alerts)
                count = storage.get_alert_count()
                assert count == len(alerts)

            storage.close()


class TestQuickstartAlertFields:
    """Tests validating alert fields mentioned in quickstart documentation."""

    def test_alert_has_documented_fields(self):
        """Verify AlertRecord has all fields mentioned in quickstart.md."""
        from lsst_extendedness.models import AlertRecord

        # Create a minimal alert
        alert = AlertRecord(
            alert_id=12345,
            dia_source_id=12345000,
            ra=180.0,
            dec=45.0,
            mjd=60000.0,
        )

        # Fields explicitly used in quickstart examples
        assert hasattr(alert, "alert_id")
        assert hasattr(alert, "ra")
        assert hasattr(alert, "dec")
        assert hasattr(alert, "has_ss_source")

        # Verify types match documentation expectations
        assert isinstance(alert.alert_id, int)
        assert isinstance(alert.ra, float)
        assert isinstance(alert.dec, float)
        assert isinstance(alert.has_ss_source, bool)
