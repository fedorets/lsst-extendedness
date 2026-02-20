# Quick Start

Get the LSST Extendedness Pipeline running in 5 minutes.

## Prerequisites

| Requirement | Version | Install |
|-------------|---------|---------|
| Python | 3.12+ | [pyenv](https://github.com/pyenv/pyenv) |
| PDM | 2.0+ | `pip install pdm` |
| librdkafka | latest | See below |

### System Dependencies

=== "macOS"

    ```bash
    brew install librdkafka
    ```

=== "Ubuntu/Debian"

    ```bash
    sudo apt-get install -y librdkafka-dev
    ```

=== "RHEL/CentOS"

    ```bash
    sudo yum install -y librdkafka-devel
    ```

## Install

```bash
# Clone and install
git clone https://github.com/westover/lsst-extendedness.git
cd lsst-extendedness
pdm install

# Verify
pdm run pytest tests/ -x -q
```

## First Run

```bash
# 1. Initialize database
pdm run lsst-extendedness db-init

# 2. Ingest test data
pdm run lsst-extendedness ingest --source mock --count 100

# 3. Check it worked
pdm run lsst-extendedness db-stats
```

## Python API

### Query with SQLiteStorage

```python
from lsst_extendedness.storage import SQLiteStorage

storage = SQLiteStorage("data/lsst_extendedness.db")
storage.initialize()

count = storage.get_alert_count()
print(f"Total alerts: {count}")
```

### Load Real ZTF Data (No Credentials)

```python
from lsst_extendedness.sources import FinkSource

# FinkSource includes real ZTF alert fixtures
with FinkSource() as source:
    for alert in source.fetch_alerts(limit=5):
        print(f"Alert {alert.alert_id}: RA={alert.ra:.2f}, Dec={alert.dec:.2f}")

# Check for Solar System Objects
with FinkSource() as source:
    alerts = list(source.fetch_alerts(limit=10))
    sso_alerts = [a for a in alerts if a.has_ss_source]
    print(f"SSO alerts: {len(sso_alerts)}")
```

### Production: ANTARES Broker

For real-time LSST alerts (requires credentials):

```bash
export ANTARES_API_KEY="your-key"
export ANTARES_API_SECRET="your-secret"

pdm run lsst-extendedness ingest \
    --source antares \
    --topics extragalactic_staging \
    --limit 1000
```

## Command Reference

| Command | Description |
|---------|-------------|
| `pdm run lsst-extendedness db-init` | Initialize database |
| `pdm run lsst-extendedness db-stats` | Show statistics |
| `pdm run lsst-extendedness ingest --source mock --count N` | Ingest N mock alerts |
| `pdm run lsst-extendedness ingest --source fink` | Ingest from Fink fixtures |
| `pdm run lsst-extendedness query --recent 7` | Query last 7 days |
| `pdm run pytest tests/ -v` | Run tests |

## Troubleshooting

### LSST RSP Environment

If installing in an existing LSST RSP environment with dependency conflicts:

```bash
# Create isolated venv
pdm venv create
pdm use .venv/bin/python
pdm install
```

### httpx Conflict

If you see `lsst-rsp requires httpx<0.28` errors, the package already pins `httpx<0.28` for compatibility.

## Next Steps

- [Configuration](configuration.md) - Customize settings
- [Ingestion Guide](../guide/ingestion.md) - Detailed ingestion docs
- [API Reference](../api/sources.md) - Source implementations
