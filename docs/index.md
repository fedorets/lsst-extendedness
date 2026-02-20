# LSST Extendedness Pipeline

Pipeline for detecting **minimoon candidates** in the LSST alert stream through extendedness analysis and orbit determination.

## What It Does

1. **Ingests** alerts from ANTARES broker, Fink, or other sources
2. **Filters** by extendedness, SNR, and solar system object association
3. **Stores** everything in SQLite with full audit trail
4. **Post-processes** for minimoon detection and custom analysis

## Quick Start

```bash
git clone https://github.com/westover/lsst-extendedness.git
cd lsst-extendedness
pdm install
pdm run lsst-extendedness db-init
pdm run lsst-extendedness ingest --source mock --count 100
```

:material-arrow-right: [Full Quick Start Guide](getting-started/quickstart.md)

## Documentation Index

### Getting Started

- [**Quick Start**](getting-started/quickstart.md) - Install, first run, Python API examples
- [**Configuration**](getting-started/configuration.md) - TOML config, environment variables, CLI flags

### User Guide

- [**Ingestion**](guide/ingestion.md) - Ingest alerts from any source
- [**Filtering**](guide/filtering.md) - Filter presets and custom SQL filters
- [**Post-Processing**](guide/processing.md) - Run analysis, create custom processors
- [**Querying**](guide/querying.md) - Query data and export results

### API Reference

- [**Models**](api/models.md) - `AlertRecord`, `ProcessingResult`, `IngestionRun`
- [**Sources**](api/sources.md) - All alert sources + how to build your own
- [**Storage**](api/storage.md) - `SQLiteStorage`, database schema, views
- [**Filter Engine**](api/filter.md) - `FilterEngine`, presets, SQL generation
- [**Processing**](api/processing.md) - `BaseProcessor`, registry, plugin system

### Deployment & Operations

- [**Systemd Timers**](deployment/systemd.md) - Automated daily ingestion/processing
- [**OpenStack VM**](deployment/openstack.md) - Production deployment guide

### Contributing

- [**Contributing Guide**](contributing.md) - Development workflow, code quality, PR process

## Alert Sources

| Source | Use Case | Credentials | Docs |
|--------|----------|-------------|------|
| ANTARESSource | Production LSST alerts | API key | [API](api/sources.md#antaressource) |
| FinkSource | Real ZTF data for testing | None | [API](api/sources.md#finksource) |
| SpaceRocksSource | Known asteroid orbits (JPL) | None | [API](api/sources.md#spacerockssource) |
| KafkaSource | Direct Kafka streaming | Broker config | [API](api/sources.md#kafkasource) |
| FileSource | AVRO/CSV file import | None | [API](api/sources.md#filesource) |
| MockSource | Synthetic test data | None | [API](api/sources.md#mocksource) |

## Extending the Pipeline

### Add a New Source

```python
from lsst_extendedness.sources import register_source

@register_source("my_source")
class MySource:
    source_name = "my_source"
    def connect(self): ...
    def fetch_alerts(self, limit=None): ...
    def close(self): ...
```

:material-arrow-right: [Full guide](api/sources.md#creating-a-custom-source)

### Add a Post-Processor

```python
from lsst_extendedness.processing import BaseProcessor, register_processor

@register_processor("orbit_check")
class OrbitCheckProcessor(BaseProcessor):
    name = "orbit_check"
    version = "1.0.0"
    def process(self, df): ...
```

:material-arrow-right: [Full guide](api/processing.md#creating-a-custom-processor)

## Project Status

| Component | Tests | Coverage |
|-----------|-------|----------|
| Models | 50+ | 98% |
| Sources (6 implementations) | 200+ | 96% |
| Storage | 40+ | 95% |
| Filter Engine | 60+ | 97% |
| Processing | 50+ | 96% |
| **Total** | **586** | **96%+** |
