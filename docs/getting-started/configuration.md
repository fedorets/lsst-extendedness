# Configuration

## Configuration Files

Configuration is loaded from TOML files in the `config/` directory.

### Default Configuration

`config/default.toml` contains all default settings:

```toml
[database]
path = "data/lsst_extendedness.db"
backup_dir = "data/backups"
backup_retention_days = 30

[ingestion]
batch_size = 100
save_cutouts = true
cutout_dir = "data/cutouts"

[filter]
default_preset = "all"

[processing]
default_window_days = 15
plugin_dir = "plugins"

[logging]
level = "INFO"
format = "structured"
```

### Kafka Profiles

`config/kafka_profiles.toml` defines Kafka connection profiles:

```toml
[profiles.local]
bootstrap_servers = "localhost:9092"
group_id = "lsst-extendedness-local"
auto_offset_reset = "earliest"

[profiles.production]
bootstrap_servers = "kafka.antares.noirlab.edu:9092"
group_id = "lsst-extendedness-prod"
auto_offset_reset = "latest"
security_protocol = "SASL_SSL"
sasl_mechanism = "PLAIN"
```

## Environment Variables

Environment variables override config file settings:

| Variable | Description | Default |
|----------|-------------|---------|
| `LSST_DB_PATH` | Database file path | `data/lsst_extendedness.db` |
| `LSST_LOG_LEVEL` | Logging level | `INFO` |
| `ANTARES_API_KEY` | ANTARES API key | - |
| `ANTARES_API_SECRET` | ANTARES API secret | - |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka brokers | - |

## Loading Configuration

```python
from lsst_extendedness.config import Settings

# Load default config
settings = Settings()

# Load with overrides
settings = Settings(
    database_path="custom/path.db",
    log_level="DEBUG",
)

# Access settings
print(settings.database.path)
print(settings.ingestion.batch_size)
```

## CLI Configuration

Override settings via CLI flags:

```bash
# Custom database
lsst-extendedness --db-path /custom/path.db db-stats

# Custom config file
lsst-extendedness --config config/production.toml ingest

# Verbose logging
lsst-extendedness --log-level DEBUG ingest --source mock
```

## Filter Presets

Define custom filter presets in your config:

```toml
[filter.presets.my_custom_filter]
extendedness_min = 0.4
extendedness_max = 0.6
require_sso = true
min_snr = 50.0
```

Then use with:

```bash
lsst-extendedness filter --preset my_custom_filter
```

## Processor Configuration

Configure post-processors:

```toml
[processing.processors.minimoon_detector]
enabled = true
window_days = 15
min_observations = 3

[processing.processors.example]
enabled = true
```
