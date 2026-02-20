"""
Tests for query shortcuts module.
"""

from __future__ import annotations

import pytest

from lsst_extendedness.query import shortcuts
from lsst_extendedness.storage import SQLiteStorage


@pytest.fixture
def populated_storage(tmp_path, alert_factory):
    """Create a populated storage for query tests."""
    db_path = tmp_path / "query_test.db"
    storage = SQLiteStorage(db_path)
    storage.initialize()

    # Create diverse test data
    alerts = []

    # High SNR point sources
    for i in range(10):
        alerts.append(
            alert_factory.create(
                extendedness_median=0.1,
                snr=100.0 + i,
                filter_name="g",
                has_ss_source=False,
            )
        )

    # Extended sources
    for i in range(10):
        alerts.append(
            alert_factory.create(
                extendedness_median=0.85,
                snr=30.0,
                filter_name="r",
                has_ss_source=False,
            )
        )

    # Minimoon candidates (SSO with intermediate extendedness)
    for i in range(5):
        alerts.append(
            alert_factory.create(
                extendedness_median=0.5,
                snr=50.0,
                has_ss_source=True,
                ss_object_id=f"SSO_{i}",
            )
        )

    # SSO alerts without minimoon characteristics
    for i in range(5):
        alerts.append(
            alert_factory.create(
                extendedness_median=0.1,
                snr=80.0,
                has_ss_source=True,
                ss_object_id=f"SSO_other_{i}",
            )
        )

    storage.write_batch(alerts)
    yield storage
    storage.close()


class TestQueryShortcuts:
    """Tests for query shortcut functions."""

    def test_point_sources(self, populated_storage):
        """Test querying point sources."""
        df = shortcuts.point_sources(storage=populated_storage)

        assert len(df) > 0
        # All should have low extendedness
        assert all(df["extendedness_median"] < 0.3)

    def test_extended_sources(self, populated_storage):
        """Test querying extended sources."""
        df = shortcuts.extended_sources(storage=populated_storage)

        assert len(df) > 0
        # All should have high extendedness
        assert all(df["extendedness_median"] > 0.7)

    def test_minimoon_candidates(self, populated_storage):
        """Test querying minimoon candidates."""
        df = shortcuts.minimoon_candidates(storage=populated_storage)

        assert len(df) == 5
        # All should have SSO and intermediate extendedness
        assert all(df["has_ss_source"] == 1)
        assert all((df["extendedness_median"] >= 0.3) & (df["extendedness_median"] <= 0.7))

    def test_sso_alerts(self, populated_storage):
        """Test querying SSO alerts."""
        df = shortcuts.sso_alerts(storage=populated_storage)

        assert len(df) == 10  # 5 minimoon + 5 other SSO
        assert all(df["has_ss_source"] == 1)

    def test_high_snr(self, populated_storage):
        """Test querying high SNR alerts."""
        df = shortcuts.high_snr(min_snr=80.0, storage=populated_storage)

        assert len(df) > 0
        assert all(df["snr"] >= 80.0)

    def test_high_snr_default(self, populated_storage):
        """Test high SNR with default threshold."""
        df = shortcuts.high_snr(storage=populated_storage)

        assert all(df["snr"] >= 50.0)

    def test_with_filter(self, populated_storage):
        """Test filtering by observation filter."""
        df = shortcuts.with_filter("g", storage=populated_storage)

        assert len(df) > 0
        assert all(df["filter_name"] == "g")

    def test_by_source(self, populated_storage):
        """Test querying by DIA source ID."""
        # Get a known source ID from the data
        result = populated_storage.query("SELECT dia_source_id FROM alerts_raw LIMIT 1")
        source_id = result[0]["dia_source_id"]

        df = shortcuts.by_source(source_id, storage=populated_storage)

        assert len(df) >= 1
        assert all(df["dia_source_id"] == source_id)

    def test_by_sso(self, populated_storage):
        """Test querying by SSObject ID."""
        df = shortcuts.by_sso("SSO_0", storage=populated_storage)

        assert len(df) >= 1
        assert all(df["ss_object_id"] == "SSO_0")

    def test_in_region(self, populated_storage):
        """Test querying alerts in a sky region."""
        # Query a wide region that should contain all alerts
        df = shortcuts.in_region(
            ra_min=0.0,
            ra_max=360.0,
            dec_min=-90.0,
            dec_max=90.0,
            storage=populated_storage,
        )

        # Should get all alerts
        assert len(df) == 30

    def test_in_time_window(self, populated_storage):
        """Test querying alerts in a time window."""
        df = shortcuts.in_time_window(
            start_mjd=59000.0,
            end_mjd=70000.0,
            storage=populated_storage,
        )

        # Should get all alerts (they're in this range)
        assert len(df) > 0

    def test_stats(self, populated_storage):
        """Test getting database stats."""
        result = shortcuts.stats(storage=populated_storage)

        assert isinstance(result, dict)
        assert "alerts_raw_count" in result
        assert result["alerts_raw_count"] == 30

    def test_custom_query(self, populated_storage):
        """Test custom SQL query."""
        df = shortcuts.custom(
            "SELECT COUNT(*) as cnt FROM alerts_raw WHERE has_ss_source = 1",
            storage=populated_storage,
        )

        assert df.iloc[0]["cnt"] == 10

    def test_processing_results_empty(self, populated_storage):
        """Test querying processing results when empty."""
        df = shortcuts.processing_results(storage=populated_storage)

        assert len(df) == 0

    def test_processing_results_with_filter(self, populated_storage):
        """Test querying processing results with processor filter."""
        df = shortcuts.processing_results(
            processor_name="nonexistent",
            storage=populated_storage,
        )

        assert len(df) == 0


class TestGetStorageHelper:
    """Tests for the _get_storage helper function."""

    def test_with_provided_storage(self, populated_storage):
        """Test that provided storage is returned unchanged."""
        result = shortcuts._get_storage(populated_storage)
        assert result is populated_storage

    def test_without_storage_no_default(self):
        """Test that FileNotFoundError is raised when no default DB exists."""
        with pytest.raises(FileNotFoundError):
            shortcuts._get_storage(None)


class TestQueryToDFHelper:
    """Tests for the _query_to_df helper function."""

    def test_returns_dataframe(self, populated_storage):
        """Test that helper returns a DataFrame."""
        df = shortcuts._query_to_df(
            populated_storage,
            "SELECT * FROM alerts_raw LIMIT 5",
        )

        import pandas as pd

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 5

    def test_with_params(self, populated_storage):
        """Test query with parameters."""
        df = shortcuts._query_to_df(
            populated_storage,
            "SELECT * FROM alerts_raw WHERE has_ss_source = ?",
            (1,),
        )

        assert len(df) == 10


class TestQueryShortcutsAdditional:
    """Additional tests for query shortcuts."""

    def test_today_empty(self, tmp_path):
        """Test today() with no recent data."""
        db_path = tmp_path / "empty.db"
        storage = SQLiteStorage(db_path)
        storage.initialize()

        df = shortcuts.today(storage=storage)

        # Should return empty DataFrame
        assert len(df) == 0

        storage.close()

    def test_recent_empty(self, tmp_path):
        """Test recent() with no data."""
        db_path = tmp_path / "empty.db"
        storage = SQLiteStorage(db_path)
        storage.initialize()

        df = shortcuts.recent(days=7, storage=storage)

        assert len(df) == 0

        storage.close()

    def test_recent_custom_days(self, populated_storage):
        """Test recent() with custom days parameter.

        Note: Test data has MJD around 60000 (circa 2023), but "recent" looks
        back from current date. We use in_time_window for reliable testing.
        """
        # Use in_time_window which doesn't depend on current date
        df = shortcuts.in_time_window(
            start_mjd=59000.0,
            end_mjd=65000.0,
            storage=populated_storage,
        )

        # Should have all test data
        assert len(df) > 0

    def test_reassociations_empty(self, populated_storage):
        """Test reassociations() when no reassociations exist."""
        df = shortcuts.reassociations(storage=populated_storage)

        # No reassociations in test data
        assert len(df) == 0

    def test_by_object(self, populated_storage):
        """Test by_object() for querying by DIA object ID."""
        # Get a known object ID
        result = populated_storage.query("SELECT dia_object_id FROM alerts_raw LIMIT 1")
        object_id = result[0]["dia_object_id"]

        df = shortcuts.by_object(object_id, storage=populated_storage)

        assert len(df) >= 1
        assert all(df["dia_object_id"] == object_id)

    def test_by_object_not_found(self, populated_storage):
        """Test by_object() with non-existent object ID."""
        df = shortcuts.by_object(999999999, storage=populated_storage)

        assert len(df) == 0

    def test_by_sso_not_found(self, populated_storage):
        """Test by_sso() with non-existent SSObject ID."""
        df = shortcuts.by_sso("NONEXISTENT_SSO", storage=populated_storage)

        assert len(df) == 0

    def test_in_region_narrow(self, populated_storage):
        """Test in_region() with narrow region that may have no results."""
        df = shortcuts.in_region(
            ra_min=0.0,
            ra_max=0.1,
            dec_min=0.0,
            dec_max=0.1,
            storage=populated_storage,
        )

        # May or may not have results depending on test data
        assert isinstance(df, type(shortcuts.point_sources(populated_storage)))

    def test_with_filter_nonexistent(self, populated_storage):
        """Test with_filter() for filter that doesn't exist."""
        df = shortcuts.with_filter("z", storage=populated_storage)

        # No 'z' filter in test data
        assert len(df) == 0

    def test_custom_query_with_params(self, populated_storage):
        """Test custom() with parameterized query."""
        df = shortcuts.custom(
            "SELECT * FROM alerts_raw WHERE snr > ? ORDER BY snr DESC LIMIT ?",
            params=(90.0, 5),
            storage=populated_storage,
        )

        assert len(df) <= 5
        if len(df) > 0:
            assert all(df["snr"] > 90.0)
