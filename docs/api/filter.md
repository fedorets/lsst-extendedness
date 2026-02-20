# Filter Engine API Reference

Configurable SQL-based filtering for alerts.

## FilterEngine

::: lsst_extendedness.filter.FilterEngine
    options:
      show_root_heading: true
      members:
        - __init__
        - apply_filter
        - create_filter
        - get_filter
        - list_filters

## FilterConfig

::: lsst_extendedness.filter.FilterConfig
    options:
      show_root_heading: true

## Presets

Built-in filter presets:

| Preset | Description |
|--------|-------------|
| `all` | No filtering, pass all alerts |
| `point_sources` | Extendedness < 0.3 |
| `extended_sources` | Extendedness > 0.7 |
| `sso_candidates` | Has SSObject association |
| `high_snr` | SNR > 100 |
| `minimoon_candidates` | SSO with intermediate extendedness |

## Usage Examples

### Using Presets

```python
from lsst_extendedness.filter import FilterEngine, presets

engine = FilterEngine(storage)

# Apply preset
results = engine.apply_filter(presets.POINT_SOURCES)

# Get preset config
config = presets.get_preset("sso_candidates")
print(config.to_sql())
```

### Custom Filters

```python
from lsst_extendedness.filter import FilterConfig

# Create custom filter
config = FilterConfig(
    name="my_filter",
    extendedness_min=0.4,
    extendedness_max=0.6,
    require_sso=True,
    min_snr=50.0,
    filters=["g", "r", "i"],
)

# Apply
results = engine.apply_filter(config)

# Save for reuse
engine.create_filter(config)
```

### SQL Generation

```python
config = FilterConfig(
    extendedness_min=0.3,
    min_snr=50.0,
)

sql, params = config.to_sql()
print(sql)
# SELECT * FROM alerts_raw WHERE extendedness_median >= ? AND snr >= ?
print(params)
# (0.3, 50.0)
```
