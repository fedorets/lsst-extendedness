"""
Tests for filter engine module.
"""

from __future__ import annotations

import pytest

from lsst_extendedness.filter.engine import (
    FilterCondition,
    FilterConfig,
    FilterEngine,
    FilterOperator,
)

# ============================================================================
# FILTER OPERATOR TESTS
# ============================================================================


class TestFilterOperator:
    """Tests for FilterOperator enum."""

    def test_operator_values(self):
        """Test operator SQL values."""
        assert FilterOperator.EQ.value == "="
        assert FilterOperator.NE.value == "!="
        assert FilterOperator.LT.value == "<"
        assert FilterOperator.LE.value == "<="
        assert FilterOperator.GT.value == ">"
        assert FilterOperator.GE.value == ">="
        assert FilterOperator.IN.value == "IN"
        assert FilterOperator.NOT_IN.value == "NOT IN"
        assert FilterOperator.LIKE.value == "LIKE"
        assert FilterOperator.IS_NULL.value == "IS NULL"
        assert FilterOperator.IS_NOT_NULL.value == "IS NOT NULL"
        assert FilterOperator.BETWEEN.value == "BETWEEN"


# ============================================================================
# FILTER CONDITION TESTS
# ============================================================================


class TestFilterCondition:
    """Tests for FilterCondition dataclass."""

    def test_eq_condition(self):
        """Test equality condition."""
        condition = FilterCondition.eq("field", "value")

        assert condition.field == "field"
        assert condition.operator == FilterOperator.EQ
        assert condition.value == "value"

    def test_ne_condition(self):
        """Test not-equal condition."""
        condition = FilterCondition.ne("status", "closed")

        assert condition.operator == FilterOperator.NE
        assert condition.value == "closed"

    def test_lt_condition(self):
        """Test less-than condition."""
        condition = FilterCondition.lt("count", 100)

        assert condition.operator == FilterOperator.LT
        assert condition.value == 100

    def test_le_condition(self):
        """Test less-than-or-equal condition."""
        condition = FilterCondition.le("mjd", 60000.0)

        assert condition.operator == FilterOperator.LE

    def test_gt_condition(self):
        """Test greater-than condition."""
        condition = FilterCondition.gt("snr", 5.0)

        assert condition.operator == FilterOperator.GT

    def test_ge_condition(self):
        """Test greater-than-or-equal condition."""
        condition = FilterCondition.ge("extendedness", 0.3)

        assert condition.operator == FilterOperator.GE

    def test_between_condition(self):
        """Test between condition."""
        condition = FilterCondition.between("mjd", 60000, 60100)

        assert condition.operator == FilterOperator.BETWEEN
        assert condition.value == 60000
        assert condition.value2 == 60100

    def test_in_list_condition(self):
        """Test IN condition."""
        condition = FilterCondition.in_list("filter_name", ["g", "r", "i"])

        assert condition.operator == FilterOperator.IN
        assert condition.value == ["g", "r", "i"]

    def test_is_null_condition(self):
        """Test IS NULL condition."""
        condition = FilterCondition.is_null("ss_object_id")

        assert condition.operator == FilterOperator.IS_NULL

    def test_is_not_null_condition(self):
        """Test IS NOT NULL condition."""
        condition = FilterCondition.is_not_null("extendedness")

        assert condition.operator == FilterOperator.IS_NOT_NULL

    # SQL generation tests

    def test_to_sql_eq(self):
        """Test SQL generation for equality."""
        condition = FilterCondition.eq("field", "value")
        sql, params = condition.to_sql()

        assert sql == "field = ?"
        assert params == ["value"]

    def test_to_sql_between(self):
        """Test SQL generation for BETWEEN."""
        condition = FilterCondition.between("mjd", 60000, 60100)
        sql, params = condition.to_sql()

        assert sql == "mjd BETWEEN ? AND ?"
        assert params == [60000, 60100]

    def test_to_sql_in(self):
        """Test SQL generation for IN."""
        condition = FilterCondition.in_list("filter", ["g", "r"])
        sql, params = condition.to_sql()

        assert sql == "filter IN (?, ?)"
        assert params == ["g", "r"]

    def test_to_sql_is_null(self):
        """Test SQL generation for IS NULL."""
        condition = FilterCondition.is_null("field")
        sql, params = condition.to_sql()

        assert sql == "field IS NULL"
        assert params == []

    def test_to_sql_is_not_null(self):
        """Test SQL generation for IS NOT NULL."""
        condition = FilterCondition.is_not_null("field")
        sql, params = condition.to_sql()

        assert sql == "field IS NOT NULL"
        assert params == []

    def test_to_sql_in_requires_list(self):
        """Test that IN operator requires list."""
        condition = FilterCondition("field", FilterOperator.IN, "not_a_list")

        with pytest.raises(ValueError, match="requires list"):
            condition.to_sql()


# ============================================================================
# FILTER CONFIG TESTS
# ============================================================================


class TestFilterConfig:
    """Tests for FilterConfig dataclass."""

    def test_default_values(self):
        """Test default configuration."""
        config = FilterConfig()

        assert config.name == "custom"
        assert config.description == ""
        assert config.conditions == []
        assert config.combine_with == "AND"
        assert config.order_by is None
        assert config.order_desc is True
        assert config.limit is None

    def test_add_condition(self):
        """Test adding conditions (fluent interface)."""
        config = FilterConfig()
        result = config.add(FilterCondition.eq("field", "value"))

        assert result is config  # Returns self
        assert len(config.conditions) == 1

    def test_add_multiple_conditions(self):
        """Test adding multiple conditions."""
        config = (
            FilterConfig()
            .add(FilterCondition.ge("snr", 10))
            .add(FilterCondition.le("extendedness", 0.5))
        )

        assert len(config.conditions) == 2

    def test_to_sql_no_conditions(self):
        """Test SQL generation with no conditions."""
        config = FilterConfig()
        sql, params = config.to_sql()

        assert sql == "SELECT * FROM alerts_raw"
        assert params == []

    def test_to_sql_single_condition(self):
        """Test SQL generation with single condition."""
        config = FilterConfig()
        config.add(FilterCondition.ge("snr", 10))
        sql, params = config.to_sql()

        assert "WHERE snr >= ?" in sql
        assert params == [10]

    def test_to_sql_multiple_conditions_and(self):
        """Test SQL generation with AND combination."""
        config = FilterConfig(combine_with="AND")
        config.add(FilterCondition.ge("snr", 10))
        config.add(FilterCondition.le("extendedness", 0.5))
        sql, params = config.to_sql()

        assert "WHERE snr >= ? AND extendedness" in sql
        assert params == [10, 0.5]

    def test_to_sql_multiple_conditions_or(self):
        """Test SQL generation with OR combination."""
        config = FilterConfig(combine_with="OR")
        config.add(FilterCondition.eq("filter_name", "g"))
        config.add(FilterCondition.eq("filter_name", "r"))
        sql, params = config.to_sql()

        assert " OR " in sql
        assert params == ["g", "r"]

    def test_to_sql_with_order_by(self):
        """Test SQL generation with ORDER BY."""
        config = FilterConfig(order_by="mjd", order_desc=True)
        sql, _params = config.to_sql()

        assert "ORDER BY mjd DESC" in sql

    def test_to_sql_with_order_asc(self):
        """Test SQL generation with ORDER BY ASC."""
        config = FilterConfig(order_by="snr", order_desc=False)
        sql, _params = config.to_sql()

        assert "ORDER BY snr ASC" in sql

    def test_to_sql_with_limit(self):
        """Test SQL generation with LIMIT."""
        config = FilterConfig(limit=100)
        sql, _params = config.to_sql()

        assert "LIMIT 100" in sql

    def test_to_sql_custom_table(self):
        """Test SQL generation with custom table."""
        config = FilterConfig()
        sql, _params = config.to_sql(base_table="alerts_filtered")

        assert "FROM alerts_filtered" in sql

    def test_to_dict(self):
        """Test serialization to dictionary."""
        config = FilterConfig(
            name="test_filter",
            description="Test description",
            limit=50,
        )
        config.add(FilterCondition.ge("snr", 10))

        result = config.to_dict()

        assert result["name"] == "test_filter"
        assert result["description"] == "Test description"
        assert result["limit"] == 50
        assert len(result["conditions"]) == 1
        assert result["conditions"][0]["field"] == "snr"
        assert result["conditions"][0]["operator"] == ">="

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "name": "loaded_filter",
            "description": "Loaded from dict",
            "conditions": [
                {"field": "snr", "operator": ">=", "value": 10},
                {"field": "mjd", "operator": "BETWEEN", "value": 60000, "value2": 60100},
            ],
            "combine_with": "AND",
            "order_by": "mjd",
            "order_desc": True,
            "limit": 100,
        }

        config = FilterConfig.from_dict(data)

        assert config.name == "loaded_filter"
        assert len(config.conditions) == 2
        assert config.conditions[0].operator == FilterOperator.GE
        assert config.conditions[1].operator == FilterOperator.BETWEEN
        assert config.limit == 100

    def test_roundtrip_serialization(self):
        """Test to_dict/from_dict roundtrip."""
        original = FilterConfig(
            name="roundtrip",
            description="Test roundtrip",
            limit=25,
        )
        original.add(FilterCondition.ge("snr", 5))
        original.add(FilterCondition.between("mjd", 60000, 60100))

        data = original.to_dict()
        restored = FilterConfig.from_dict(data)

        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.limit == original.limit
        assert len(restored.conditions) == len(original.conditions)


# ============================================================================
# FILTER ENGINE TESTS
# ============================================================================


class TestFilterEngine:
    """Tests for FilterEngine class."""

    def test_init(self, temp_db):
        """Test engine initialization."""
        engine = FilterEngine(temp_db)

        assert engine.storage is temp_db
        # saved_filters table should be created
        tables = temp_db.query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='saved_filters'"
        )
        assert len(tables) == 1

    def test_filter_no_conditions(self, temp_db, alert_factory):
        """Test filter with no conditions returns all alerts."""
        # Add some alerts
        alerts = alert_factory.create_batch(5)
        temp_db.write_batch(alerts)

        engine = FilterEngine(temp_db)
        df = engine.filter()

        assert len(df) == 5

    def test_filter_extendedness_range(self, temp_db, alert_factory):
        """Test filtering by extendedness range."""
        # Create alerts with different extendedness values
        alerts = [
            alert_factory.create(extendedness_median=0.1),  # Below range
            alert_factory.create(extendedness_median=0.4),  # In range
            alert_factory.create(extendedness_median=0.5),  # In range
            alert_factory.create(extendedness_median=0.9),  # Above range
        ]
        temp_db.write_batch(alerts)

        engine = FilterEngine(temp_db)
        df = engine.filter(extendedness_min=0.3, extendedness_max=0.7)

        assert len(df) == 2

    def test_filter_snr_min(self, temp_db, alert_factory):
        """Test filtering by minimum SNR."""
        alerts = [
            alert_factory.create(snr=5.0),
            alert_factory.create(snr=15.0),
            alert_factory.create(snr=25.0),
        ]
        temp_db.write_batch(alerts)

        engine = FilterEngine(temp_db)
        df = engine.filter(snr_min=10.0)

        assert len(df) == 2

    def test_filter_has_sso(self, temp_db, alert_factory):
        """Test filtering by SSO association."""
        alerts = [
            alert_factory.create(has_ss_source=True),
            alert_factory.create(has_ss_source=False),
            alert_factory.create(has_ss_source=True),
        ]
        temp_db.write_batch(alerts)

        engine = FilterEngine(temp_db)
        df = engine.filter(has_sso=True)

        assert len(df) == 2

    def test_filter_by_filter_name(self, temp_db, alert_factory):
        """Test filtering by photometric filter."""
        alerts = [
            alert_factory.create(filter_name="g"),
            alert_factory.create(filter_name="r"),
            alert_factory.create(filter_name="g"),
        ]
        temp_db.write_batch(alerts)

        engine = FilterEngine(temp_db)
        df = engine.filter(filter_name="g")

        assert len(df) == 2

    def test_filter_mjd_range(self, temp_db, alert_factory):
        """Test filtering by MJD range."""
        alerts = [
            alert_factory.create(mjd=59999.0),  # Before range
            alert_factory.create(mjd=60050.0),  # In range
            alert_factory.create(mjd=60101.0),  # After range
        ]
        temp_db.write_batch(alerts)

        engine = FilterEngine(temp_db)
        df = engine.filter(mjd_min=60000.0, mjd_max=60100.0)

        assert len(df) == 1

    def test_filter_with_limit(self, temp_db, alert_factory):
        """Test filter with limit."""
        alerts = alert_factory.create_batch(10)
        temp_db.write_batch(alerts)

        engine = FilterEngine(temp_db)
        df = engine.filter(limit=3)

        assert len(df) == 3

    def test_apply_config(self, temp_db, alert_factory):
        """Test applying FilterConfig."""
        alerts = alert_factory.create_batch(5)
        temp_db.write_batch(alerts)

        engine = FilterEngine(temp_db)
        config = FilterConfig(name="test", limit=2)
        df = engine.apply(config)

        assert len(df) == 2

    def test_save_and_load_filter(self, temp_db):
        """Test saving and loading filter."""
        engine = FilterEngine(temp_db)

        config = FilterConfig(
            name="saved_test",
            description="Test saved filter",
        )
        config.add(FilterCondition.ge("snr", 10))

        engine.save_filter(config)
        loaded = engine.load_filter("saved_test")

        assert loaded is not None
        assert loaded.name == "saved_test"
        assert len(loaded.conditions) == 1

    def test_load_filter_not_found(self, temp_db):
        """Test loading non-existent filter."""
        engine = FilterEngine(temp_db)

        result = engine.load_filter("nonexistent")

        assert result is None

    def test_apply_saved(self, temp_db, alert_factory):
        """Test applying saved filter."""
        alerts = alert_factory.create_batch(5)
        temp_db.write_batch(alerts)

        engine = FilterEngine(temp_db)
        config = FilterConfig(name="apply_test", limit=3)
        engine.save_filter(config)

        df = engine.apply_saved("apply_test")

        assert len(df) == 3

    def test_apply_saved_not_found(self, temp_db):
        """Test applying non-existent saved filter."""
        engine = FilterEngine(temp_db)

        with pytest.raises(ValueError, match="Filter not found"):
            engine.apply_saved("nonexistent")

    def test_list_saved(self, temp_db):
        """Test listing saved filters."""
        engine = FilterEngine(temp_db)

        engine.save_filter(FilterConfig(name="filter_a", description="A"))
        engine.save_filter(FilterConfig(name="filter_b", description="B"))

        saved = engine.list_saved()

        assert len(saved) == 2
        names = [f["name"] for f in saved]
        assert "filter_a" in names
        assert "filter_b" in names

    def test_delete_filter(self, temp_db):
        """Test deleting saved filter."""
        engine = FilterEngine(temp_db)
        engine.save_filter(FilterConfig(name="to_delete"))

        result = engine.delete_filter("to_delete")

        assert result is True
        assert engine.load_filter("to_delete") is None

    def test_delete_filter_not_found(self, temp_db):
        """Test deleting non-existent filter."""
        engine = FilterEngine(temp_db)

        result = engine.delete_filter("nonexistent")

        assert result is False

    def test_save_filter_update(self, temp_db):
        """Test updating existing saved filter."""
        engine = FilterEngine(temp_db)

        # Save initial filter
        config1 = FilterConfig(name="update_test", description="Original")
        engine.save_filter(config1)

        # Save updated filter with same name
        config2 = FilterConfig(name="update_test", description="Updated")
        config2.add(FilterCondition.ge("snr", 20))
        engine.save_filter(config2)

        loaded = engine.load_filter("update_test")

        assert loaded.description == "Updated"
        assert len(loaded.conditions) == 1

    def test_copy_to_filtered(self, temp_db, alert_factory):
        """Test copying filtered alerts to alerts_filtered table."""
        # Ensure alerts_filtered table exists
        temp_db.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts_filtered (
                id INTEGER PRIMARY KEY,
                raw_alert_id INTEGER NOT NULL,
                filter_config_hash TEXT NOT NULL,
                filtered_at TEXT NOT NULL,
                UNIQUE(raw_alert_id, filter_config_hash)
            )
        """
        )

        alerts = alert_factory.create_batch(5)
        temp_db.write_batch(alerts)

        engine = FilterEngine(temp_db)
        config = FilterConfig(name="copy_test", limit=3)

        count = engine.copy_to_filtered(config)

        assert count == 3

        # Verify records in alerts_filtered
        rows = temp_db.query("SELECT * FROM alerts_filtered")
        assert len(rows) == 3

    def test_copy_to_filtered_empty(self, temp_db):
        """Test copy with no matching alerts."""
        temp_db.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts_filtered (
                id INTEGER PRIMARY KEY,
                raw_alert_id INTEGER NOT NULL,
                filter_config_hash TEXT NOT NULL,
                filtered_at TEXT NOT NULL,
                UNIQUE(raw_alert_id, filter_config_hash)
            )
        """
        )

        engine = FilterEngine(temp_db)
        config = FilterConfig(name="empty_test")
        config.add(FilterCondition.eq("snr", 999999))  # No match

        count = engine.copy_to_filtered(config)

        assert count == 0


# ============================================================================
# FILTER PRESETS TESTS
# ============================================================================


class TestFilterPresets:
    """Tests for filter preset functions."""

    def test_point_sources(self):
        """Test point_sources preset."""
        from lsst_extendedness.filter.presets import point_sources

        config = point_sources()

        assert config.name == "point_sources"
        assert len(config.conditions) == 2
        assert config.order_by == "snr"

    def test_point_sources_with_limit(self):
        """Test point_sources with limit."""
        from lsst_extendedness.filter.presets import point_sources

        config = point_sources(limit=50)

        assert config.limit == 50

    def test_extended_sources(self):
        """Test extended_sources preset."""
        from lsst_extendedness.filter.presets import extended_sources

        config = extended_sources()

        assert config.name == "extended_sources"
        assert len(config.conditions) == 1

    def test_minimoon_candidates(self):
        """Test minimoon_candidates preset."""
        from lsst_extendedness.filter.presets import minimoon_candidates

        config = minimoon_candidates()

        assert config.name == "minimoon_candidates"
        assert len(config.conditions) == 3  # has_sso, ext_min, ext_max

    def test_sso_alerts(self):
        """Test sso_alerts preset."""
        from lsst_extendedness.filter.presets import sso_alerts

        config = sso_alerts()

        assert config.name == "sso_alerts"
        assert len(config.conditions) == 1

    def test_reassociations(self):
        """Test reassociations preset."""
        from lsst_extendedness.filter.presets import reassociations

        config = reassociations()

        assert config.name == "reassociations"

    def test_high_snr_default(self):
        """Test high_snr preset with default SNR."""
        from lsst_extendedness.filter.presets import high_snr

        config = high_snr()

        assert config.name == "high_snr"
        assert "50" in config.description

    def test_high_snr_custom(self):
        """Test high_snr preset with custom SNR."""
        from lsst_extendedness.filter.presets import high_snr

        config = high_snr(min_snr=100.0, limit=25)

        assert "100" in config.description
        assert config.limit == 25

    def test_recent_days_default(self):
        """Test recent_days preset with default days."""
        from lsst_extendedness.filter.presets import recent_days

        config = recent_days()

        assert config.name == "recent_7d"

    def test_recent_days_custom(self):
        """Test recent_days preset with custom days."""
        from lsst_extendedness.filter.presets import recent_days

        config = recent_days(days=14)

        assert config.name == "recent_14d"
        assert "14" in config.description

    def test_by_filter_band(self):
        """Test by_filter_band preset."""
        from lsst_extendedness.filter.presets import by_filter_band

        config = by_filter_band("g")

        assert config.name == "band_g"
        assert "g" in config.description

    def test_sky_region(self):
        """Test sky_region preset."""
        from lsst_extendedness.filter.presets import sky_region

        config = sky_region(ra_min=180.0, ra_max=190.0, dec_min=-10.0, dec_max=10.0)

        assert config.name == "sky_region"
        assert len(config.conditions) == 4  # ra_min, ra_max, dec_min, dec_max
        assert "180" in config.description

    def test_time_window(self):
        """Test time_window preset."""
        from lsst_extendedness.filter.presets import time_window

        config = time_window(start_mjd=60000.0, end_mjd=60100.0)

        assert config.name == "time_window"
        assert config.order_desc is False  # Chronological order

    def test_extendedness_range(self):
        """Test extendedness_range preset."""
        from lsst_extendedness.filter.presets import extendedness_range

        config = extendedness_range(ext_min=0.3, ext_max=0.7)

        assert config.name == "extendedness_range"
        assert "0.30" in config.description
        assert "0.70" in config.description

    def test_non_sso(self):
        """Test non_sso preset."""
        from lsst_extendedness.filter.presets import non_sso

        config = non_sso()

        assert config.name == "non_sso"
        assert len(config.conditions) == 1

    def test_unprocessed(self):
        """Test unprocessed preset."""
        from lsst_extendedness.filter.presets import unprocessed

        config = unprocessed()

        assert config.name == "unprocessed"


class TestGetPreset:
    """Tests for get_preset function."""

    def test_get_preset_exists(self):
        """Test getting an existing preset."""
        from lsst_extendedness.filter.presets import get_preset

        config = get_preset("point_sources")

        assert config.name == "point_sources"

    def test_get_preset_with_kwargs(self):
        """Test getting preset with keyword arguments."""
        from lsst_extendedness.filter.presets import get_preset

        config = get_preset("high_snr", min_snr=75.0, limit=10)

        assert config.limit == 10

    def test_get_preset_not_found(self):
        """Test getting non-existent preset."""
        from lsst_extendedness.filter.presets import get_preset

        with pytest.raises(ValueError, match="Unknown preset"):
            get_preset("nonexistent")


class TestListPresets:
    """Tests for list_presets function."""

    def test_list_presets(self):
        """Test listing all presets."""
        from lsst_extendedness.filter.presets import list_presets

        presets = list_presets()

        assert len(presets) >= 7  # At least 7 presets defined
        names = [p["name"] for p in presets]
        assert "point_sources" in names
        assert "minimoon_candidates" in names
