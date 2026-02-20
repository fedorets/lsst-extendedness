# LSST Extendedness Pipeline

[![CI](https://github.com/westover/lsst-extendedness/actions/workflows/ci.yml/badge.svg)](https://github.com/westover/lsst-extendedness/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-96%25-brightgreen)](https://github.com/westover/lsst-extendedness)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://python.org)

Pipeline for detecting **minimoon candidates** in the LSST alert stream from the Vera C. Rubin Observatory through extendedness analysis and orbit determination.

## Quick Start

```bash
git clone https://github.com/westover/lsst-extendedness.git
cd lsst-extendedness
pdm install
pdm run lsst-extendedness db-init
pdm run lsst-extendedness ingest --source mock --count 100
pdm run lsst-extendedness db-stats
```

See the full [Quick Start Guide](docs/getting-started/quickstart.md) for details.

## Architecture

```
Alert Sources ──> Ingestion Pipeline ──> SQLite Storage ──> Post-Processing
                                                │
  ANTARES (production)                    alerts_raw
  Fink    (real ZTF fixtures)             alerts_filtered
  SpaceRocks (JPL Horizons)               processing_results
  Mock    (testing)
```

## Alert Sources

| Source | Use Case | Credentials |
|--------|----------|-------------|
| [ANTARESSource](docs/api/sources.md) | Production LSST alerts | API key |
| [FinkSource](docs/api/sources.md) | Real ZTF data for testing | None |
| [SpaceRocksSource](docs/api/sources.md) | Known asteroid orbits | None |
| [KafkaSource](docs/api/sources.md) | Direct Kafka streaming | Broker config |
| [FileSource](docs/api/sources.md) | AVRO/CSV import | None |
| [MockSource](docs/api/sources.md) | Synthetic test data | None |

## Documentation

| Section | Description |
|---------|-------------|
| [Quick Start](docs/getting-started/quickstart.md) | Install and first run |
| [Configuration](docs/getting-started/configuration.md) | TOML config, env vars, CLI flags |
| **User Guide** | |
| [Ingestion](docs/guide/ingestion.md) | Ingest from any source |
| [Filtering](docs/guide/filtering.md) | Filter presets and custom filters |
| [Post-Processing](docs/guide/processing.md) | Run analysis, create processors |
| [Querying](docs/guide/querying.md) | Query and export data |
| **API Reference** | |
| [Models](docs/api/models.md) | AlertRecord, ProcessingResult, IngestionRun |
| [Sources](docs/api/sources.md) | All sources + how to add your own |
| [Storage](docs/api/storage.md) | SQLiteStorage, schema, views |
| [Filter Engine](docs/api/filter.md) | FilterEngine, presets, SQL generation |
| [Processing](docs/api/processing.md) | BaseProcessor, registry, plugin system |
| **Operations** | |
| [Systemd Timers](docs/deployment/systemd.md) | Automated scheduling |
| [OpenStack VM](docs/deployment/openstack.md) | Deployment guide |
| [Contributing](CONTRIBUTING.md) | Development workflow |

## Extending the Pipeline

### Add a New Source

Implement the `AlertSource` protocol and register it:

```python
from lsst_extendedness.sources import register_source

@register_source("my_source")
class MySource:
    source_name = "my_source"
    def connect(self): ...
    def fetch_alerts(self, limit=None): ...
    def close(self): ...
```

Full guide: [Sources API](docs/api/sources.md#creating-a-custom-source)

### Add a Post-Processor

Subclass `BaseProcessor` and register it:

```python
from lsst_extendedness.processing import BaseProcessor, register_processor

@register_processor("orbit_check")
class OrbitCheckProcessor(BaseProcessor):
    name = "orbit_check"
    version = "1.0.0"
    def process(self, df): ...
```

Full guide: [Processing API](docs/api/processing.md#creating-a-custom-processor)

## Development

```bash
pdm install -G dev                             # Dev dependencies
pdm run pytest tests/ -v                       # Tests (586 passing)
pdm run pytest tests/ --cov=lsst_extendedness  # Coverage (96%+)
pdm run ruff check src/ tests/                 # Lint
pdm run mypy src/lsst_extendedness/            # Type check
pdm run mkdocs serve                           # Docs at localhost:8000
```

## CI/CD

- Lint + type check on every push/PR
- Tests on Python 3.12 and 3.13
- Coverage gate at 85%
- Dependabot with auto-merge for minor/patch
- Docker fresh install test (weekly)

## License

MIT
