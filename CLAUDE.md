# LSST Extendedness Pipeline

## What This Is

Pipeline for detecting **minimoon candidates** in the LSST alert stream from Vera C. Rubin Observatory. Ingests alerts from brokers (ANTARES, Fink), filters by extendedness/SSO association, stores in SQLite, and runs post-processing for orbit determination.

## Commands

```bash
pdm install                                    # Install deps
pdm install -G dev                             # With dev tools
pdm run pytest tests/ -v                       # Run tests
pdm run pytest tests/ --cov=lsst_extendedness  # Coverage
pdm run ruff check src/ tests/                 # Lint
pdm run ruff format src/ tests/                # Format
pdm run mypy src/lsst_extendedness/            # Type check
pdm run mkdocs serve                           # Docs at localhost:8000
pdm run lsst-extendedness db-init              # Init database
pdm run lsst-extendedness ingest --source mock --count 100
pdm run lsst-extendedness ingest --source fink
pdm run lsst-extendedness db-stats
```

## Project Layout

```
src/lsst_extendedness/
├── models/alerts.py       # AlertRecord (Pydantic) - core data model
├── sources/               # Alert sources (all implement AlertSource protocol)
│   ├── protocol.py        # AlertSource protocol + source registry
│   ├── antares.py         # ANTARES broker (production)
│   ├── fink.py            # Fink broker (real ZTF fixtures, no creds needed)
│   ├── spacerocks.py      # JPL Horizons asteroid orbits (optional dep)
│   ├── kafka.py           # Direct Kafka streaming
│   ├── file.py            # AVRO/CSV file import
│   └── mock.py            # Synthetic test data
├── storage/
│   ├── sqlite.py          # SQLiteStorage - all DB operations
│   └── schema.py          # SQL schema, views, migrations
├── filter/                # Configurable alert filtering
├── processing/            # Post-processors (minimoon detection)
├── ingest/                # Pipeline orchestration
├── query/                 # Query helpers and export
├── cli.py                 # Click CLI
└── config.py              # Settings (TOML-based)
tests/
├── conftest.py            # Fixtures: alert_factory, temp_db, mock_source
├── test_sources.py        # Source tests
├── test_storage.py        # Storage tests
├── test_quickstart_docs.py # Validates docs code examples work
└── ...                    # 586 tests, 96%+ coverage
```

## Alert Sources

| Source | Import | Credentials | Use Case |
|--------|--------|-------------|----------|
| `ANTARESSource` | always | API key+secret | Production LSST alerts |
| `FinkSource` | always | none | Real ZTF data via fixtures |
| `SpaceRocksSource` | optional | none | Known asteroid orbits (JPL Horizons) |
| `KafkaSource` | always | broker config | Direct Kafka streaming |
| `FileSource` | always | none | AVRO/CSV import |
| `MockSource` | always | none | Synthetic test data |

## Adding a New Source

1. Create `src/lsst_extendedness/sources/mysource.py`
2. Implement connect/fetch_alerts/close + `@register_source("name")`
3. Export from `sources/__init__.py`
4. Add tests

```python
@register_source("mysource")
class MySource:
    source_name = "mysource"
    def connect(self) -> None: ...
    def fetch_alerts(self, limit=None) -> Iterator[AlertRecord]: ...
    def close(self) -> None: ...
```

## Science Context

**Minimoons** = temporarily captured natural satellites of Earth.

Key detection criteria:
- **SSO association**: `has_ss_source=True`
- **Point-like**: Low extendedness (asteroid, not galaxy)
- **Orbit**: Heliocentric → not captured yet; geocentric → minimoon

Important AlertRecord fields: `extendedness_median`, `has_ss_source`, `ss_object_id`, `trail_data` (orbital elements)

## CI

- Lint + type check (ruff, mypy) on every push/PR
- Tests on Python 3.12 and 3.13
- Coverage gate at 85%
- Dependabot with auto-merge for minor/patch
- Docker fresh install test (weekly + on dependency changes)
