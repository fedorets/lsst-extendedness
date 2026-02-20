# LSST Extendedness Pipeline

A modern Python pipeline for processing LSST alerts with extendedness analysis, SQLite storage, and flexible post-processing.

## Features

- **Protocol-based architecture** - Swap sources (Kafka, ANTARES, File) without code changes
- **SQLite storage** - Simple, fast local database for 80GB+ of alerts
- **Pydantic models** - Type-safe data validation without ORM complexity
- **Configurable filtering** - SQL-based filter engine with presets
- **Post-processing framework** - Plugin architecture for custom analysis (minimoon detection, etc.)
- **Systemd integration** - Automated daily ingestion and processing

## Architecture

```mermaid
graph LR
    A[ANTARES Broker] --> B[Alert Source]
    B --> C[Ingestion Pipeline]
    C --> D[(SQLite Database)]
    D --> E[Filter Engine]
    E --> F[Post-Processors]
    F --> G[Results]
```

## Quick Start

```bash
# Install
pip install lsst-extendedness

# Or with PDM
pdm install

# Initialize database
lsst-extendedness db-init

# Run ingestion (mock source for testing)
lsst-extendedness ingest --source mock --count 1000

# Query recent alerts
lsst-extendedness query --recent 7
```

## Project Status

| Component | Status |
|-----------|--------|
| Core Models | ✅ Complete |
| Sources (Kafka, ANTARES, File, Mock) | ✅ Complete |
| SQLite Storage | ✅ Complete |
| Filter Engine | ✅ Complete |
| Post-Processing | ✅ Complete |
| CLI | ✅ Complete |
| Documentation | 🔄 In Progress |

## License

MIT License - See [LICENSE](https://github.com/westover/lsst-extendedness/blob/main/LICENSE) for details.
