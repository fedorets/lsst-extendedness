# Quick Start

Get up and running in 5 minutes.

## 1. Initialize the Database

```bash
lsst-extendedness db-init
```

This creates the SQLite database with all required tables and views.

## 2. Test with Mock Data

```bash
# Ingest 1000 mock alerts
lsst-extendedness ingest --source mock --count 1000

# Check database stats
lsst-extendedness db-stats
```

## 3. Query Your Data

```bash
# Recent alerts (last 7 days)
lsst-extendedness query --recent 7

# Export to CSV
lsst-extendedness query --recent 7 --export alerts.csv
```

## 4. Interactive Python

```python
from lsst_extendedness.storage import SQLiteStorage
from lsst_extendedness.query import shortcuts

# Connect to database
storage = SQLiteStorage("data/lsst_extendedness.db")

# Get recent alerts as DataFrame
df = shortcuts.recent(storage, days=7)
print(f"Found {len(df)} alerts")

# Filter by extendedness
extended = df[df['extendedness_median'] > 0.7]
print(f"Extended sources: {len(extended)}")
```

## 5. Run with Real Data

### ANTARES Source

```bash
# Set credentials
export ANTARES_API_KEY="your-key"
export ANTARES_API_SECRET="your-secret"

# Ingest from ANTARES
lsst-extendedness ingest --source antares \
    --topics extragalactic_staging \
    --limit 1000
```

### Kafka Source

```bash
# Use Kafka profile from config
lsst-extendedness ingest --source kafka \
    --profile production \
    --duration 3600
```

### File Source

```bash
# Import from CSV
lsst-extendedness ingest --source file \
    --path data/alerts.csv

# Import from AVRO
lsst-extendedness ingest --source file \
    --path data/alerts.avro
```

## 6. Apply Filters

```bash
# Filter for point sources
lsst-extendedness filter --preset point_sources

# Filter for SSO candidates
lsst-extendedness filter --preset sso_candidates

# Custom filter
lsst-extendedness filter \
    --extendedness-min 0.3 \
    --extendedness-max 0.7 \
    --require-sso
```

## 7. Run Post-Processing

```bash
# Run all registered processors
lsst-extendedness process --window 15

# Run specific processor
lsst-extendedness process --processor example --window 7
```

## Next Steps

- [Configuration Guide](configuration.md) - Customize settings
- [Ingestion Pipeline](../guide/ingestion.md) - Detailed ingestion docs
- [Post-Processing](../guide/processing.md) - Create custom processors
