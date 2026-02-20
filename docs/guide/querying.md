# Querying Data

Access and analyze stored alerts.

## Query Shortcuts

Common queries made easy:

```python
from lsst_extendedness.query import shortcuts

# Recent alerts
df = shortcuts.recent(storage, days=7)

# Today's alerts
df = shortcuts.today(storage)

# SSO candidates
df = shortcuts.sso_candidates(storage)

# By extendedness range
df = shortcuts.by_extendedness(storage, min_val=0.3, max_val=0.7)
```

## CLI Queries

```bash
# Recent alerts
lsst-extendedness query --recent 7

# Count by filter
lsst-extendedness query --group-by filter_name

# Database statistics
lsst-extendedness db-stats

# Interactive SQL shell
lsst-extendedness db-shell
```

## SQL Queries

### Direct SQL

```python
# Raw query
results = storage.query(
    "SELECT * FROM alerts_raw WHERE snr > ? LIMIT 100",
    (50.0,)
)

# As DataFrame
df = storage.query_df("""
    SELECT
        filter_name,
        COUNT(*) as count,
        AVG(extendedness_median) as avg_ext
    FROM alerts_raw
    GROUP BY filter_name
""")
```

### Using Views

```sql
-- Point sources
SELECT * FROM v_point_sources LIMIT 100;

-- Extended sources
SELECT * FROM v_extended_sources LIMIT 100;

-- SSO candidates
SELECT * FROM v_sso_candidates;

-- Recent (last 7 days)
SELECT * FROM v_recent_alerts;
```

## Export

### CSV

```python
from lsst_extendedness.query import export

# Export query results
export.to_csv(df, "output.csv")

# CLI
lsst-extendedness query --recent 7 --export alerts.csv
```

### Parquet

```python
export.to_parquet(df, "output.parquet")

# CLI
lsst-extendedness query --recent 7 --export alerts.parquet
```

### Excel

```python
export.to_excel(df, "output.xlsx")
```

## Common Queries

### Alerts by Date

```sql
SELECT
    DATE(ingested_at) as date,
    COUNT(*) as count
FROM alerts_raw
GROUP BY DATE(ingested_at)
ORDER BY date DESC;
```

### Extendedness Distribution

```sql
SELECT
    CASE
        WHEN extendedness_median < 0.3 THEN 'point'
        WHEN extendedness_median > 0.7 THEN 'extended'
        ELSE 'intermediate'
    END as type,
    COUNT(*) as count
FROM alerts_raw
GROUP BY type;
```

### SSO Reassociations

```sql
SELECT *
FROM alerts_raw
WHERE is_reassociation = 1
ORDER BY mjd DESC;
```

### High SNR Sources

```sql
SELECT *
FROM alerts_raw
WHERE snr > 100
ORDER BY snr DESC
LIMIT 100;
```

## Performance Tips

1. **Use views** for common filters
2. **Add indexes** for frequent queries
3. **Limit results** with LIMIT clause
4. **Use pre-filtering** in processors
