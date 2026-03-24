"""
Configurable Filter Engine.

Provides flexible filtering of alerts based on configurable criteria.
Filters can be combined, saved as presets, and applied at query time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    import pandas as pd

    from ..storage.sqlite import SQLiteStorage

logger = structlog.get_logger(__name__)


class FilterOperator(Enum):
    """Comparison operators for filter conditions."""

    EQ = "="
    NE = "!="
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
    IN = "IN"
    NOT_IN = "NOT IN"
    LIKE = "LIKE"
    IS_NULL = "IS NULL"
    IS_NOT_NULL = "IS NOT NULL"
    BETWEEN = "BETWEEN"


@dataclass
class FilterCondition:
    """A single filter condition."""

    field: str
    operator: FilterOperator
    value: Any = None
    value2: Any = None  # For BETWEEN operator

    def to_sql(self) -> tuple[str, list[Any]]:
        """Convert to SQL clause and parameters.

        Returns:
            Tuple of (SQL string, list of parameters)
        """
        if self.operator == FilterOperator.IS_NULL:
            return f"{self.field} IS NULL", []
        elif self.operator == FilterOperator.IS_NOT_NULL:
            return f"{self.field} IS NOT NULL", []
        elif self.operator == FilterOperator.BETWEEN:
            return f"{self.field} BETWEEN ? AND ?", [self.value, self.value2]
        elif self.operator in (FilterOperator.IN, FilterOperator.NOT_IN):
            if not isinstance(self.value, list | tuple):
                raise ValueError(f"IN operator requires list, got {type(self.value)}")
            placeholders = ", ".join("?" * len(self.value))
            return f"{self.field} {self.operator.value} ({placeholders})", list(self.value)
        else:
            return f"{self.field} {self.operator.value} ?", [self.value]

    @classmethod
    def eq(cls, field: str, value: Any) -> FilterCondition:
        """Create equality condition."""
        return cls(field, FilterOperator.EQ, value)

    @classmethod
    def ne(cls, field: str, value: Any) -> FilterCondition:
        """Create not-equal condition."""
        return cls(field, FilterOperator.NE, value)

    @classmethod
    def lt(cls, field: str, value: Any) -> FilterCondition:
        """Create less-than condition."""
        return cls(field, FilterOperator.LT, value)

    @classmethod
    def le(cls, field: str, value: Any) -> FilterCondition:
        """Create less-than-or-equal condition."""
        return cls(field, FilterOperator.LE, value)

    @classmethod
    def gt(cls, field: str, value: Any) -> FilterCondition:
        """Create greater-than condition."""
        return cls(field, FilterOperator.GT, value)

    @classmethod
    def ge(cls, field: str, value: Any) -> FilterCondition:
        """Create greater-than-or-equal condition."""
        return cls(field, FilterOperator.GE, value)

    @classmethod
    def between(cls, field: str, low: Any, high: Any) -> FilterCondition:
        """Create between condition."""
        return cls(field, FilterOperator.BETWEEN, low, high)

    @classmethod
    def in_list(cls, field: str, values: list[Any]) -> FilterCondition:
        """Create IN condition."""
        return cls(field, FilterOperator.IN, values)

    @classmethod
    def is_null(cls, field: str) -> FilterCondition:
        """Create IS NULL condition."""
        return cls(field, FilterOperator.IS_NULL)

    @classmethod
    def is_not_null(cls, field: str) -> FilterCondition:
        """Create IS NOT NULL condition."""
        return cls(field, FilterOperator.IS_NOT_NULL)


@dataclass
class FilterConfig:
    """Configuration for a filter with multiple conditions."""

    name: str = "custom"
    description: str = ""
    conditions: list[FilterCondition] = field(default_factory=list)
    combine_with: str = "AND"  # AND or OR
    order_by: str | None = None
    order_desc: bool = True
    limit: int | None = None

    def add(self, condition: FilterCondition) -> FilterConfig:
        """Add a condition (fluent interface)."""
        self.conditions.append(condition)
        return self

    def to_sql(self, base_table: str = "alerts_raw") -> tuple[str, list[Any]]:
        """Generate SQL query from filter configuration.

        Args:
            base_table: Table to query

        Returns:
            Tuple of (SQL query, parameters)
        """
        params = []
        where_clauses = []

        for condition in self.conditions:
            clause, condition_params = condition.to_sql()
            where_clauses.append(clause)
            params.extend(condition_params)

        sql = f"SELECT * FROM {base_table}"

        if where_clauses:
            combiner = f" {self.combine_with} "
            sql += f" WHERE {combiner.join(where_clauses)}"

        if self.order_by:
            direction = "DESC" if self.order_desc else "ASC"
            sql += f" ORDER BY {self.order_by} {direction}"

        if self.limit:
            sql += f" LIMIT {self.limit}"

        return sql, params

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for storage."""
        return {
            "name": self.name,
            "description": self.description,
            "conditions": [
                {
                    "field": c.field,
                    "operator": c.operator.value,
                    "value": c.value,
                    "value2": c.value2,
                }
                for c in self.conditions
            ],
            "combine_with": self.combine_with,
            "order_by": self.order_by,
            "order_desc": self.order_desc,
            "limit": self.limit,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FilterConfig:
        """Deserialize from dictionary."""
        conditions = []
        for c in data.get("conditions", []):
            operator = FilterOperator(c["operator"])
            conditions.append(
                FilterCondition(
                    field=c["field"],
                    operator=operator,
                    value=c.get("value"),
                    value2=c.get("value2"),
                )
            )

        return cls(
            name=data.get("name", "custom"),
            description=data.get("description", ""),
            conditions=conditions,
            combine_with=data.get("combine_with", "AND"),
            order_by=data.get("order_by"),
            order_desc=data.get("order_desc", True),
            limit=data.get("limit"),
        )


class FilterEngine:
    """Engine for applying filters to alert data.

    Usage:
        engine = FilterEngine(storage)

        # Quick filter
        df = engine.filter(
            extendedness_min=0.3,
            extendedness_max=0.7,
            has_sso=True,
        )

        # Using FilterConfig
        config = FilterConfig(name="my_filter")
        config.add(FilterCondition.ge("snr", 10))
        config.add(FilterCondition.between("extendedness_median", 0.3, 0.7))
        df = engine.apply(config)

        # Save and reuse
        engine.save_filter(config)
        df = engine.apply_saved("my_filter")
    """

    def __init__(self, storage: SQLiteStorage):
        """Initialize filter engine.

        Args:
            storage: SQLiteStorage for data access
        """
        self.storage = storage
        self._ensure_filter_table()

    def _ensure_filter_table(self) -> None:
        """Ensure saved filters table exists."""
        self.storage.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_filters (
                name TEXT PRIMARY KEY,
                description TEXT,
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """
        )

    def filter(
        self,
        *,
        extendedness_min: float | None = None,
        extendedness_max: float | None = None,
        snr_min: float | None = None,
        has_sso: bool | None = None,
        is_reassociation: bool | None = None,
        filter_name: str | None = None,
        mjd_min: float | None = None,
        mjd_max: float | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """Apply quick filter with common parameters.

        Args:
            extendedness_min: Minimum extendedness
            extendedness_max: Maximum extendedness
            snr_min: Minimum SNR
            has_sso: Filter by SSO association
            is_reassociation: Filter by reassociation status
            filter_name: Photometric filter (g, r, i, etc.)
            mjd_min: Minimum MJD
            mjd_max: Maximum MJD
            limit: Maximum results

        Returns:
            Filtered DataFrame
        """
        config = FilterConfig(name="quick_filter", limit=limit)

        if extendedness_min is not None:
            config.add(FilterCondition.ge("extendedness_median", extendedness_min))
        if extendedness_max is not None:
            config.add(FilterCondition.le("extendedness_median", extendedness_max))
        if snr_min is not None:
            config.add(FilterCondition.ge("snr", snr_min))
        if has_sso is not None:
            config.add(FilterCondition.eq("has_ss_source", 1 if has_sso else 0))
        if is_reassociation is not None:
            config.add(FilterCondition.eq("is_reassociation", 1 if is_reassociation else 0))
        if filter_name is not None:
            config.add(FilterCondition.eq("filter_name", filter_name))
        if mjd_min is not None:
            config.add(FilterCondition.ge("mjd", mjd_min))
        if mjd_max is not None:
            config.add(FilterCondition.le("mjd", mjd_max))

        return self.apply(config)

    def apply(self, config: FilterConfig) -> pd.DataFrame:
        """Apply a filter configuration.

        Args:
            config: FilterConfig to apply

        Returns:
            Filtered DataFrame
        """
        import pandas as pd

        sql, params = config.to_sql()
        rows = self.storage.query(sql, tuple(params))

        logger.debug(
            "filter_applied",
            name=config.name,
            conditions=len(config.conditions),
            results=len(rows),
        )

        return pd.DataFrame(rows)

    def save_filter(self, config: FilterConfig) -> None:
        """Save a filter configuration for later use.

        Args:
            config: FilterConfig to save
        """
        import json
        from datetime import datetime

        now = datetime.utcnow().isoformat()
        config_json = json.dumps(config.to_dict())

        self.storage.execute(
            """
            INSERT INTO saved_filters (name, description, config_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (name) DO UPDATE SET
                description = ?,
                config_json = ?,
                updated_at = ?
            """,
            (
                config.name,
                config.description,
                config_json,
                now,
                now,
                config.description,
                config_json,
                now,
            ),
        )

        logger.info("filter_saved", name=config.name)

    def load_filter(self, name: str) -> FilterConfig | None:
        """Load a saved filter configuration.

        Args:
            name: Filter name

        Returns:
            FilterConfig or None if not found
        """
        import json

        rows = self.storage.query(
            "SELECT config_json FROM saved_filters WHERE name = ?",
            (name,),
        )

        if not rows:
            return None

        data = json.loads(rows[0]["config_json"])
        return FilterConfig.from_dict(data)

    def apply_saved(self, name: str) -> pd.DataFrame:
        """Apply a saved filter by name.

        Args:
            name: Saved filter name

        Returns:
            Filtered DataFrame

        Raises:
            ValueError: If filter not found
        """
        config = self.load_filter(name)
        if not config:
            raise ValueError(f"Filter not found: {name}")
        return self.apply(config)

    def list_saved(self) -> list[dict[str, Any]]:
        """List all saved filters.

        Returns:
            List of filter info dicts
        """
        return self.storage.query(
            "SELECT name, description, created_at, updated_at FROM saved_filters ORDER BY name"
        )

    def delete_filter(self, name: str) -> bool:
        """Delete a saved filter.

        Args:
            name: Filter name

        Returns:
            True if deleted, False if not found
        """
        rows_affected = self.storage.execute(
            "DELETE FROM saved_filters WHERE name = ?",
            (name,),
        )
        return rows_affected > 0

    def copy_to_filtered(self, config: FilterConfig) -> int:
        """Apply filter and copy results to alerts_filtered table.

        Args:
            config: Filter configuration

        Returns:
            Number of alerts copied
        """
        import hashlib
        import json
        from datetime import datetime

        # Generate config hash for tracking
        config_json = json.dumps(config.to_dict(), sort_keys=True)
        config_hash = hashlib.md5(config_json.encode()).hexdigest()[:16]

        # Get filtered alert IDs
        sql, params = config.to_sql()
        sql = sql.replace("SELECT *", "SELECT id")

        rows = self.storage.query(sql, tuple(params))
        alert_ids = [r["id"] for r in rows]

        if not alert_ids:
            return 0

        # Insert into alerts_filtered
        now = datetime.utcnow().isoformat()
        for alert_id in alert_ids:
            self.storage.execute(
                """
                INSERT OR IGNORE INTO alerts_filtered (raw_alert_id, filter_config_hash, filtered_at)
                VALUES (?, ?, ?)
                """,
                (alert_id, config_hash, now),
            )

        logger.info(
            "alerts_filtered",
            config=config.name,
            count=len(alert_ids),
            hash=config_hash,
        )

        return len(alert_ids)
