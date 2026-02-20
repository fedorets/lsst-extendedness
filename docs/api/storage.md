# Storage API Reference

SQLite storage backend for alert data.

## SQLiteStorage

::: lsst_extendedness.storage.SQLiteStorage
    options:
      show_root_heading: true
      members:
        - __init__
        - initialize
        - write_batch
        - query
        - get_alert
        - get_alerts_by_filter
        - close

## Database Schema

### Core Tables

#### alerts_raw

All ingested alerts (never filtered, for reproducibility).

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| alert_id | INTEGER | LSST alert ID |
| dia_source_id | INTEGER | DIASource ID |
| ra | REAL | Right ascension (degrees) |
| dec | REAL | Declination (degrees) |
| mjd | REAL | Modified Julian Date |
| extendedness_median | REAL | Extendedness metric |
| has_ss_source | INTEGER | Has SSObject association |
| ingested_at | TEXT | Ingestion timestamp |

#### processed_sources

State tracking for reassociation detection.

| Column | Type | Description |
|--------|------|-------------|
| dia_source_id | INTEGER | Primary key |
| first_seen_mjd | REAL | First observation MJD |
| last_seen_mjd | REAL | Last observation MJD |
| ss_object_id | TEXT | Current SSObject ID |

#### processing_results

Post-processing output.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| processor_name | TEXT | Processor identifier |
| result_data | TEXT | JSON result data |
| processed_at | TEXT | Processing timestamp |

### Views

- `v_point_sources` - Alerts with extendedness < 0.3
- `v_extended_sources` - Alerts with extendedness > 0.7
- `v_sso_candidates` - Alerts with SSObject associations
- `v_recent_alerts` - Last 7 days of alerts

## Usage Examples

```python
from lsst_extendedness.storage import SQLiteStorage

# Initialize
storage = SQLiteStorage("data/alerts.db")
storage.initialize()

# Write alerts
alerts = [alert1, alert2, alert3]
count = storage.write_batch(alerts)
print(f"Wrote {count} alerts")

# Query
results = storage.query(
    "SELECT * FROM alerts_raw WHERE extendedness_median > ?",
    (0.5,)
)

# Use view
df = storage.query_df("SELECT * FROM v_sso_candidates")
```
