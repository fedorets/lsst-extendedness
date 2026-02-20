"""
Alert source implementations for the LSST Extendedness Pipeline.

This module provides flexible input sources that implement the AlertSource protocol:

- ANTARESSource: High-level ANTARES broker client (recommended for LSST)
- KafkaSource: Direct Kafka streaming with AVRO deserialization
- FileSource: Import from AVRO/CSV files (for backfill or testing)
- FinkSource: Fink broker data (real ZTF alerts, no credentials needed)
- SpaceRocksSource: Known asteroid orbits from JPL Horizons (optional)
- MockSource: Generate synthetic alerts (for testing)

Example - Using different sources:
    >>> from lsst_extendedness.sources import ANTARESSource, MockSource, FinkSource
    >>>
    >>> # Production: ANTARES broker (recommended)
    >>> source = ANTARESSource(
    ...     topics=["extragalactic_staging"],
    ...     api_key="your_key",
    ...     api_secret="your_secret",
    ... )
    >>> source.connect()
    >>> for alert in source.fetch_alerts():
    ...     process(alert)
    >>>
    >>> # Testing with real data: Fink fixtures (no credentials)
    >>> source = FinkSource()
    >>> source.connect()
    >>> for alert in source.fetch_alerts():
    ...     process(alert)
    >>>
    >>> # Known asteroids from JPL Horizons (requires space-rocks)
    >>> from lsst_extendedness.sources import SpaceRocksSource
    >>> source = SpaceRocksSource(objects=["Apophis", "Bennu"])
    >>> source.connect()
    >>> for alert in source.fetch_alerts():
    ...     print(alert.trail_data)  # Contains orbital elements
    >>>
    >>> # Testing: Mock
    >>> source = MockSource(count=100)
    >>> for alert in source.fetch_alerts():
    ...     process(alert)

To implement a custom source, see `sources/protocol.py` for the interface.
"""

from lsst_extendedness.sources.antares import ANTARESSource
from lsst_extendedness.sources.file import FileSource
from lsst_extendedness.sources.fink import FinkSource
from lsst_extendedness.sources.kafka import KafkaSource
from lsst_extendedness.sources.mock import MockSource
from lsst_extendedness.sources.protocol import AlertSource, register_source

# SpaceRocksSource is optional - requires space-rocks package
try:
    from lsst_extendedness.sources.spacerocks import SpaceRocksSource

    _SPACEROCKS_AVAILABLE = True
except ImportError:
    SpaceRocksSource = None  # type: ignore
    _SPACEROCKS_AVAILABLE = False

__all__ = [
    "ANTARESSource",
    "AlertSource",
    "FileSource",
    "FinkSource",
    "KafkaSource",
    "MockSource",
    "SpaceRocksSource",
    "register_source",
]
