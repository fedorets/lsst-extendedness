# Installation

## Requirements

- Python 3.12 or 3.13
- System dependencies: `librdkafka-dev` (for Kafka connectivity)

## Using PDM (Recommended)

[PDM](https://pdm-project.org/) is the recommended package manager for this project.

```bash
# Clone the repository
git clone https://github.com/westover/lsst-extendedness.git
cd lsst-extendedness

# Install PDM if needed
pip install pdm

# Install dependencies
pdm install

# Install with dev tools
pdm install -G dev
```

## Using pip

```bash
pip install lsst-extendedness
```

## System Dependencies

=== "Ubuntu/Debian"

    ```bash
    sudo apt-get update
    sudo apt-get install -y librdkafka-dev libopenblas-dev
    ```

=== "macOS"

    ```bash
    brew install librdkafka openblas
    ```

=== "RHEL/CentOS"

    ```bash
    sudo yum install -y librdkafka-devel openblas-devel
    ```

## Bootstrap Script

For a quick automated setup:

```bash
./scripts/bootstrap.sh
```

This script:

1. Checks Python version (3.12+ required)
2. Installs PDM if needed
3. Installs all dependencies
4. Initializes the database
5. Runs verification tests

## Verify Installation

```bash
# Check CLI is available
lsst-extendedness --version

# Run tests
pdm run pytest tests/ -v

# Initialize database
lsst-extendedness db-init
```

## Optional Dependencies

### Thumbnails

For generating PNG thumbnails from FITS cutouts:

```bash
pdm install -G thumbnails
# or
pip install lsst-extendedness[thumbnails]
```

### Development Tools

For contributing to the project:

```bash
pdm install -G dev
```

This includes:

- pytest, pytest-cov (testing)
- ruff (linting/formatting)
- mypy (type checking)
- pre-commit (git hooks)
