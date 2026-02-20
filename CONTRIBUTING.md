# Contributing to LSST Extendedness Pipeline

Thank you for your interest in contributing! This guide covers the development workflow, code quality tools, and CI/CD pipeline.

## Quick Start

### Prerequisites

- Python 3.12 or 3.13
- [PDM](https://pdm-project.org/) package manager
- Git

### Setup

```bash
# Clone the repository
git clone https://github.com/westover/lsst-extendedness.git
cd lsst-extendedness

# Install PDM if you don't have it
pip install pdm

# Install all dependencies (including dev tools)
pdm install -G dev

# Install pre-commit hooks
pdm run pre-commit install
pdm run pre-commit install --hook-type commit-msg
```

## Code Quality Tools

We use several tools to maintain code quality. All are configured in `pyproject.toml`.

### Ruff (Linting & Formatting)

[Ruff](https://docs.astral.sh/ruff/) handles both linting and formatting in one fast tool.

```bash
# Check for linting issues
pdm run ruff check src/ tests/

# Auto-fix linting issues where possible
pdm run ruff check src/ tests/ --fix

# Check formatting
pdm run ruff format src/ tests/ --check

# Apply formatting
pdm run ruff format src/ tests/
```

**Rules enabled:**
- `E`, `W` - pycodestyle errors and warnings
- `F` - Pyflakes
- `I` - isort (import sorting)
- `B` - flake8-bugbear
- `C4` - flake8-comprehensions
- `UP` - pyupgrade
- `ARG` - flake8-unused-arguments
- `SIM` - flake8-simplify
- `PTH` - flake8-use-pathlib
- `RUF` - Ruff-specific rules

**Line length:** 100 characters

### Mypy (Type Checking)

We use strict type checking with [mypy](https://mypy.readthedocs.io/).

```bash
# Run type checker
pdm run mypy src/lsst_extendedness/
```

**Configuration highlights:**
- `strict = true` - All strict checks enabled
- `disallow_untyped_defs = true` - All functions must have type hints
- Test files have relaxed typing requirements

**Type stubs provided for:**
- `pandas-stubs` - pandas type hints
- `types-requests` - requests type hints

### Pre-commit Hooks

Pre-commit runs automatically on `git commit`. Hooks include:

| Hook | Purpose |
|------|---------|
| `check-added-large-files` | Prevent files > 1MB |
| `check-case-conflict` | Detect case-insensitive conflicts |
| `end-of-file-fixer` | Ensure files end with newline |
| `trailing-whitespace` | Remove trailing whitespace |
| `check-yaml`, `check-toml`, `check-json` | Validate config files |
| `check-merge-conflict` | Detect conflict markers |
| `debug-statements` | Prevent debugger imports |
| `detect-private-key` | Prevent accidental key commits |
| `ruff` | Linting with auto-fix |
| `ruff-format` | Code formatting |
| `mypy` | Type checking |
| `bandit` | Security checks |
| `pytest` | Run tests |
| `commitizen` | Validate commit messages |

**Manual run:**
```bash
# Run all hooks on all files
pdm run pre-commit run --all-files

# Run specific hook
pdm run pre-commit run ruff --all-files
```

## Testing

We use [pytest](https://docs.pytest.org/) with coverage tracking.

### Running Tests

```bash
# Run all tests
pdm run pytest tests/

# Run with verbose output
pdm run pytest tests/ -v

# Run with coverage report
pdm run pytest tests/ -v --cov=lsst_extendedness --cov-report=term-missing

# Run with HTML coverage report
pdm run pytest tests/ -v --cov=lsst_extendedness --cov-report=html
# Then open htmlcov/index.html

# Run specific test file
pdm run pytest tests/test_models.py -v

# Run tests matching a pattern
pdm run pytest tests/ -k "test_alert" -v
```

### Test Markers

```bash
# Skip slow tests
pdm run pytest tests/ -m "not slow"

# Run only integration tests
pdm run pytest tests/ -m integration

# Run only unit tests
pdm run pytest tests/ -m unit
```

### Coverage Requirements

- **Minimum coverage:** 85%
- **Branch coverage:** Enabled
- **Excluded from coverage:**
  - `cli.py` (tested via integration)
  - `__main__.py`

### Writing Tests

```python
import pytest
from lsst_extendedness.models import AlertRecord

class TestAlertRecord:
    """Tests for AlertRecord model."""

    def test_create_valid_alert(self):
        """Test creating an alert with valid data."""
        alert = AlertRecord(
            alert_id=1,
            dia_source_id=1000,
            ra=180.0,
            dec=45.0,
            mjd=60000.0,
        )
        assert alert.alert_id == 1

    def test_invalid_ra_raises(self):
        """Test that invalid RA raises ValidationError."""
        with pytest.raises(ValueError):
            AlertRecord(
                alert_id=1,
                dia_source_id=1000,
                ra=400.0,  # Invalid: must be 0-360
                dec=45.0,
                mjd=60000.0,
            )

    @pytest.mark.slow
    def test_large_batch_processing(self):
        """Test processing many alerts (slow)."""
        # ... slow test code
```

## PDM Scripts

Convenient shortcuts defined in `pyproject.toml`:

```bash
# Testing
pdm run test              # pytest tests/ -v
pdm run test-cov          # pytest with coverage + HTML report

# Linting & Formatting
pdm run lint              # ruff check src/ tests/
pdm run lint-fix          # ruff check --fix
pdm run format            # ruff format src/ tests/
pdm run format-check      # ruff format --check
pdm run typecheck         # mypy src/

# All checks at once
pdm run check             # lint + format-check + typecheck + test

# Database operations
pdm run db-init           # Initialize SQLite schema
pdm run db-shell          # Open SQLite shell
pdm run db-stats          # Show database statistics

# Pipeline operations
pdm run ingest            # Run ingestion
pdm run query             # Run queries
pdm run process           # Run post-processing
```

## CI/CD Pipeline

GitHub Actions runs on every push and pull request to `main`.

### Workflow Jobs

| Job | Description | Python Versions |
|-----|-------------|-----------------|
| `lint` | Ruff linting, formatting check, mypy | 3.13 |
| `test` | pytest with coverage | 3.12, 3.13 |
| `coverage` | Enforce 85% coverage threshold | 3.13 |
| `all-checks` | Gate job - all must pass | - |

### CI Configuration

The workflow is defined in `.github/workflows/ci.yml`.

**Key features:**
- Caches PDM dependencies for faster builds
- Installs system dependencies (`librdkafka-dev`, `libopenblas-dev`)
- Uploads coverage to Codecov
- Fails if any check doesn't pass

### Running CI Locally

You can simulate CI locally before pushing:

```bash
# Run all the same checks CI runs
pdm run check

# Or individually:
pdm run ruff check src/lsst_extendedness/ tests/
pdm run ruff format src/lsst_extendedness/ tests/ --check
pdm run mypy src/lsst_extendedness/
pdm run pytest tests/ -v --cov=lsst_extendedness --cov-fail-under=85
```

## Commit Messages

We use [Conventional Commits](https://www.conventionalcommits.org/) with [Commitizen](https://commitizen-tools.github.io/commitizen/).

### Format

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Types

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, no code change |
| `refactor` | Code change that neither fixes nor adds |
| `perf` | Performance improvement |
| `test` | Adding or correcting tests |
| `chore` | Maintenance tasks |
| `ci` | CI/CD changes |

### Examples

```bash
feat(ingest): add ANTARES source adapter
fix(filter): correct SNR threshold validation
docs(readme): update installation instructions
test(models): add AlertRecord validation tests
ci(actions): add Python 3.13 to test matrix
```

## Project Structure

```
lsst-extendedness/
├── src/lsst_extendedness/     # Main package
│   ├── models/                # Pydantic data models
│   ├── sources/               # Alert source adapters (Kafka, File, Mock)
│   ├── storage/               # SQLite storage backend
│   ├── ingest/                # Ingestion pipeline
│   ├── filter/                # Configurable alert filtering
│   ├── processing/            # Post-processing framework
│   ├── query/                 # Query shortcuts and export
│   ├── cutouts/               # FITS cutout extraction
│   └── cli.py                 # Command-line interface
├── tests/                     # Test suite
│   ├── conftest.py            # Shared fixtures
│   ├── fixtures/              # Test data factories
│   └── test_*.py              # Test modules
├── config/                    # Configuration files
├── pyproject.toml             # Project configuration
└── .github/workflows/         # CI/CD workflows
```

## Adding New Features

### 1. Create a Branch

```bash
git checkout -b feat/my-new-feature
```

### 2. Write Tests First

Add tests in `tests/test_*.py` before implementing.

### 3. Implement the Feature

Add code in `src/lsst_extendedness/`.

### 4. Run Quality Checks

```bash
pdm run check
```

### 5. Commit with Conventional Message

```bash
git add .
git commit -m "feat(module): add new feature"
```

### 6. Push and Create PR

```bash
git push origin feat/my-new-feature
```

Then create a pull request on GitHub.

## Implementing Alert Sources

To add a new alert source, implement the `AlertSource` protocol:

```python
from typing import Iterator
from lsst_extendedness.sources.protocol import AlertSource
from lsst_extendedness.models import AlertRecord

class MyCustomSource(AlertSource):
    """Custom alert source implementation."""

    source_name: str = "my_source"

    def connect(self) -> None:
        """Establish connection to the data source."""
        self._client = MyAPIClient(self.config.api_url)

    def fetch_alerts(self, limit: int | None = None) -> Iterator[AlertRecord]:
        """Yield alerts from the source."""
        for raw_alert in self._client.get_alerts(limit=limit):
            yield AlertRecord.from_dict(raw_alert)

    def close(self) -> None:
        """Clean up resources."""
        if hasattr(self, '_client'):
            self._client.disconnect()
```

## ANTARES Integration

This pipeline is designed to work with the [ANTARES broker](https://antares.noirlab.edu/), which filters and distributes LSST alerts. Understanding the ANTARES data model is essential for working with this codebase.

### ANTARES Filter Example

ANTARES uses Level 2 filters to determine which alerts pass through to downstream consumers. Here's a reference implementation showing how to access alert data:

```python
"""
ANTARES Level 2 Filter for LSST Alerts
Filters based on DIASource extendedness and SSSource presence
"""

def extendedness_filter(locus):
    """
    ANTARES filter function.

    Parameters
    ----------
    locus : antares.devkit.locus.Locus
        ANTARES locus object containing alert information.
        A locus represents a unique sky position with associated alerts.

    Returns
    -------
    bool
        True if the alert passes the filter
    """
    # Configuration thresholds
    EXTENDEDNESS_MEDIAN_MIN = 0.0
    EXTENDEDNESS_MEDIAN_MAX = 1.0
    REQUIRE_SSSOURCE = True
    REASSOC_WINDOW_DAYS = 1.0

    # Get the most recent alert from the locus
    if not locus.alerts:
        return False

    latest_alert = locus.alerts[-1]

    # ==== Access DIASource properties ====
    # Properties come from the DIASource table
    extendedness_median = latest_alert.properties.get('extendednessMedian')
    extendedness_min = latest_alert.properties.get('extendednessMin')
    extendedness_max = latest_alert.properties.get('extendednessMax')
    obs_time = latest_alert.properties.get('midPointTai')

    # Check if all required fields are present
    if None in [extendedness_median, extendedness_min, extendedness_max]:
        return False

    # ==== Check for SSSource (Solar System association) ====
    has_sssource = False
    ssobject_reassoc_time = None

    # Method 1: Check via alert properties
    if hasattr(latest_alert, 'properties'):
        sssource_fields = ['ssObjectId', 'ssObject']
        has_sssource = any(
            latest_alert.properties.get(field) is not None
            for field in sssource_fields
        )
        ssobject_reassoc_time = latest_alert.properties.get('ssObjectReassocTimeMjdTai')

    # Method 2: Check via raw alert packet (if available)
    if not has_sssource and hasattr(latest_alert, 'packet'):
        if 'ssObject' in latest_alert.packet and latest_alert.packet['ssObject'] is not None:
            has_sssource = True
            if ssobject_reassoc_time is None:
                ssobject_reassoc_time = latest_alert.packet['ssObject'].get(
                    'ssObjectReassocTimeMjdTai'
                )

    # Method 3: Check via locus tags
    if not has_sssource and hasattr(locus, 'tags'):
        sso_tags = ['solar_system', 'sso', 'asteroid', 'comet']
        has_sssource = any(tag in locus.tags for tag in sso_tags)

    # ==== Apply filter logic ====
    passes_extendedness = (
        EXTENDEDNESS_MEDIAN_MIN <= extendedness_median <= EXTENDEDNESS_MEDIAN_MAX
        and extendedness_min >= 0.0
        and extendedness_max <= 1.0
    )

    # Check for recent reassociation
    is_recent_reassoc = False
    if has_sssource and ssobject_reassoc_time is not None and obs_time is not None:
        time_diff = abs(ssobject_reassoc_time - obs_time)
        is_recent_reassoc = time_diff <= REASSOC_WINDOW_DAYS

    if REQUIRE_SSSOURCE:
        # Pass if has SSSource AND (good extendedness OR recent reassociation)
        return has_sssource and (passes_extendedness or is_recent_reassoc)
    else:
        # Pass if NO SSSource AND good extendedness
        return not has_sssource and passes_extendedness


# ANTARES metadata (required by broker)
filter_name = "extendedness_sssource_reassoc_filter"
filter_version = "2.0.0"
filter_description = "Filters based on extendedness, SSSource presence, and reassociations"
tags = ["extended_sources", "morphology", "solar_system_objects", "reassociation"]

# Entry point called by ANTARES
run = extendedness_filter
```

### Key LSST Alert Fields

Understanding the LSST alert schema is critical. Here are the key fields:

| Field | Table | Type | Description |
|-------|-------|------|-------------|
| `alertId` | Alert | int | Unique alert identifier |
| `diaSourceId` | DIASource | int | Unique detection identifier |
| `diaObjectId` | DIASource | int | Associated variable object |
| `ra`, `decl` | DIASource | float | Sky coordinates (degrees) |
| `midPointTai` | DIASource | float | Observation time (MJD) |
| `filterName` | DIASource | str | Filter band (u/g/r/i/z/y) |
| `psFlux` | DIASource | float | Point source flux |
| `psFluxErr` | DIASource | float | Flux uncertainty |
| `snr` | DIASource | float | Signal-to-noise ratio |
| `extendednessMedian` | DIASource | float | Extendedness metric (0=point, 1=extended) |
| `extendednessMin` | DIASource | float | Minimum extendedness |
| `extendednessMax` | DIASource | float | Maximum extendedness |
| `ssObjectId` | SSObject | str | Solar system object ID |
| `ssObjectReassocTimeMjdTai` | SSObject | float | Last reassociation time |
| `trailLength` | DIASource | float | Trail length (arcsec) |
| `trailAngle` | DIASource | float | Trail position angle |
| `pixelFlags*` | DIASource | bool | Various pixel quality flags |

### Alert Packet Structure

LSST alerts come as AVRO-encoded packets with this structure:

```python
{
    "alertId": 12345,
    "diaSource": {
        "diaSourceId": 123450001,
        "diaObjectId": 12345,
        "ra": 180.12345,
        "decl": 45.67890,
        "midPointTai": 60100.5,
        "filterName": "r",
        "psFlux": 1500.0,
        "psFluxErr": 15.0,
        "snr": 100.0,
        "extendednessMedian": 0.42,
        "extendednessMin": 0.38,
        "extendednessMax": 0.48,
        "trailLength": 0.0,
        "trailAngle": 0.0,
        "pixelFlagsBad": False,
        "pixelFlagsCr": False,
        # ... more fields
    },
    "ssObject": {  # Null if not associated with solar system object
        "ssObjectId": "SSO_2024_AB123",
        "ssObjectReassocTimeMjdTai": 60099.5,
        # ... more fields
    },
    "prvDiaSources": [  # Previous detections of this object
        # Array of DIASource records
    ],
    "prvDiaForcedSources": [  # Forced photometry
        # Array of forced source records
    ],
    "cutoutScience": b"...",    # FITS image data
    "cutoutTemplate": b"...",   # Template image data
    "cutoutDifference": b"...", # Difference image data
}
```

### Reassociation Detection

A key science case is detecting when a DIASource gets reassociated with a different SSObject (solar system object). This happens when:

1. **New association**: Source had no SSObject, now has one
2. **Changed association**: Source moved from one SSObject to another
3. **Updated reassociation**: `ssObjectReassocTimeMjdTai` timestamp changed

```python
# Track state across alerts
if str(dia_source_id) in self.processed_sources:
    prev_state = self.processed_sources[str(dia_source_id)]
    prev_ss_id = prev_state.get('ssObjectId')
    prev_reassoc_time = prev_state.get('reassoc_time')

    # Detect reassociation scenarios
    if prev_ss_id is None and current_ss_object_id is not None:
        is_reassociation = True
        reassoc_reason = 'new_association'

    elif prev_ss_id != current_ss_object_id:
        is_reassociation = True
        reassoc_reason = 'changed_association'

    elif reassoc_time != prev_reassoc_time:
        is_reassociation = True
        reassoc_reason = 'updated_reassociation'
```

### Using antares-client

The `antares-client` Python package provides access to the ANTARES API:

```python
from antares_client import StreamingClient

# Create client with credentials
client = StreamingClient(
    topics=['extendedness-filtered'],
    api_key='your-api-key',
    api_secret='your-api-secret',
)

# Consume alerts
for locus, alert in client.iter():
    # Process each alert
    process_alert(locus, alert)
```

**Note:** The `antares-client` package depends on `bson-modern` (a maintained fork of `bson`) for BSON serialization. This is handled automatically via PDM's dependency resolution.

## Getting Help

- **Issues:** [GitHub Issues](https://github.com/westover/lsst-extendedness/issues)
- **Discussions:** Open an issue for questions

## License

MIT License - see [LICENSE](LICENSE) for details.
