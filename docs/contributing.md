# Contributing

Thank you for your interest in contributing to the LSST Extendedness Pipeline!

For detailed contribution guidelines, see the [CONTRIBUTING.md](https://github.com/westover/lsst-extendedness/blob/main/CONTRIBUTING.md) file in the repository.

## Quick Start

```bash
# Clone and install
git clone https://github.com/westover/lsst-extendedness.git
cd lsst-extendedness
pdm install -G dev

# Run tests
pdm run test

# Run all checks
pdm run check
```

## Code Quality

| Tool | Command | Purpose |
|------|---------|---------|
| Ruff | `pdm run lint` | Linting |
| Ruff | `pdm run format` | Formatting |
| mypy | `pdm run typecheck` | Type checking |
| pytest | `pdm run test` | Testing |

## Test Coverage

- Minimum required: **85%**
- Run with coverage: `pdm run test-cov`

## Pull Request Process

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run `pdm run check`
5. Submit PR

## Creating Processors

See the [Processing Guide](guide/processing.md) for creating custom post-processors.

## Adding Sources

See the [Sources API](api/sources.md) for implementing new alert sources.
