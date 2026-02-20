# Sources API Reference

Alert source implementations for different data inputs.

## AlertSource Protocol

All sources implement this protocol:

::: lsst_extendedness.sources.protocol.AlertSource
    options:
      show_root_heading: true

## Available Sources

### KafkaSource

Direct Kafka consumer with AVRO deserialization.

::: lsst_extendedness.sources.KafkaSource
    options:
      show_root_heading: true
      members:
        - __init__
        - connect
        - fetch_alerts
        - close

### ANTARESSource

ANTARES broker client using antares-client library.

::: lsst_extendedness.sources.ANTARESSource
    options:
      show_root_heading: true
      members:
        - __init__
        - connect
        - fetch_alerts
        - close

### FileSource

Import from CSV or AVRO files.

::: lsst_extendedness.sources.FileSource
    options:
      show_root_heading: true
      members:
        - __init__
        - connect
        - fetch_alerts
        - close

### FinkSource

Real ZTF alert data from the Fink broker. Uses bundled fixtures - no credentials needed.

::: lsst_extendedness.sources.FinkSource
    options:
      show_root_heading: true
      members:
        - __init__
        - connect
        - fetch_alerts
        - close

### SpaceRocksSource

Known asteroid orbital data from JPL Horizons (optional dependency).

::: lsst_extendedness.sources.spacerocks.SpaceRocksSource
    options:
      show_root_heading: true
      members:
        - __init__
        - connect
        - fetch_alerts
        - close

!!! note "Optional Dependency"
    Requires the `space-rocks` package: `pdm install -G spacerocks`

### MockSource

Generate synthetic alerts for testing.

::: lsst_extendedness.sources.MockSource
    options:
      show_root_heading: true
      members:
        - __init__
        - connect
        - fetch_alerts
        - close

## Creating a Custom Source

Implement the `AlertSource` protocol:

```python
from typing import Iterator
from lsst_extendedness.sources import AlertSource, register_source
from lsst_extendedness.models import AlertRecord

@register_source("my_source")
class MyCustomSource:
    """Custom alert source."""

    source_name = "my_source"

    def __init__(self, api_url: str):
        self.api_url = api_url
        self._client = None

    def connect(self) -> None:
        self._client = MyAPIClient(self.api_url)

    def fetch_alerts(self, limit: int | None = None) -> Iterator[AlertRecord]:
        for raw in self._client.get_alerts(limit=limit):
            yield AlertRecord.from_dict(raw)

    def close(self) -> None:
        if self._client:
            self._client.disconnect()
```

Then use it:

```bash
lsst-extendedness ingest --source my_source --api-url https://...
```
