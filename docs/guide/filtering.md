# Filtering Alerts

Apply configurable filters to select alerts of interest.

## Filter Presets

Built-in presets for common use cases:

```bash
# Point sources (stars)
lsst-extendedness filter --preset point_sources

# Extended sources (galaxies)
lsst-extendedness filter --preset extended_sources

# Solar system object candidates
lsst-extendedness filter --preset sso_candidates

# High signal-to-noise
lsst-extendedness filter --preset high_snr
```

## Custom Filters

### CLI

```bash
# Extendedness range
lsst-extendedness filter \
    --extendedness-min 0.3 \
    --extendedness-max 0.7

# With SSO requirement
lsst-extendedness filter \
    --require-sso \
    --min-snr 50

# Specific filters
lsst-extendedness filter \
    --filters g,r,i

# Time range
lsst-extendedness filter \
    --since 2024-01-01 \
    --until 2024-12-31
```

### Python

```python
from lsst_extendedness.filter import FilterEngine, FilterConfig

engine = FilterEngine(storage)

# Create filter config
config = FilterConfig(
    name="my_filter",
    extendedness_min=0.3,
    extendedness_max=0.7,
    require_sso=True,
    min_snr=50.0,
    filters=["g", "r", "i"],
    mjd_min=60000.0,
)

# Apply filter
results = engine.apply_filter(config)
print(f"Found {len(results)} matching alerts")
```

## Filter Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `extendedness_min` | float | Minimum extendedness (0-1) |
| `extendedness_max` | float | Maximum extendedness (0-1) |
| `require_sso` | bool | Require SSObject association |
| `exclude_sso` | bool | Exclude SSObject associations |
| `min_snr` | float | Minimum signal-to-noise |
| `max_snr` | float | Maximum signal-to-noise |
| `filters` | list | Filter bands (u,g,r,i,z,y) |
| `mjd_min` | float | Minimum MJD |
| `mjd_max` | float | Maximum MJD |
| `ra_min/ra_max` | float | RA range (degrees) |
| `dec_min/dec_max` | float | Dec range (degrees) |

## Saving Filters

```python
# Save filter for reuse
engine.create_filter(config)

# List saved filters
filters = engine.list_filters()

# Load saved filter
config = engine.get_filter("my_filter")

# Delete filter
engine.delete_filter("my_filter")
```

## Filter Views

The database includes pre-defined views:

```sql
-- Point sources
SELECT * FROM v_point_sources;

-- Extended sources
SELECT * FROM v_extended_sources;

-- SSO candidates
SELECT * FROM v_sso_candidates;
```

## Export Filtered Results

```bash
# Export to CSV
lsst-extendedness filter --preset sso_candidates --export results.csv

# Export to Parquet
lsst-extendedness filter --preset sso_candidates --export results.parquet
```
