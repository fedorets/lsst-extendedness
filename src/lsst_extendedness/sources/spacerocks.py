"""
SpaceRocks source for the LSST Extendedness Pipeline.

This module provides a SpaceRocksSource that generates alerts from known
asteroid orbital data using the spacerocks package. Useful for:
- Testing with real asteroid orbits from JPL Horizons
- Generating synthetic observation data
- Validating orbit determination algorithms

Requires the optional `space-rocks` package:
    pip install space-rocks

Example:
    >>> from lsst_extendedness.sources import SpaceRocksSource
    >>>
    >>> # Fetch known NEO data
    >>> source = SpaceRocksSource(objects=["Apophis", "Bennu", "Ryugu"])
    >>> source.connect()
    >>> for alert in source.fetch_alerts():
    ...     print(f"Object {alert.ss_object_id}: a={alert.trail_data.get('a'):.3f} AU")
    >>> source.close()

See Also:
    - SpaceRocks docs: https://spacerocks.readthedocs.io
    - JPL Horizons: https://ssd.jpl.nasa.gov/horizons/
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from typing import Any, ClassVar

from lsst_extendedness.models.alerts import AlertRecord
from lsst_extendedness.sources.protocol import register_source

logger = logging.getLogger(__name__)

# Check for spacerocks availability
try:
    from spacerocks import SpaceRock
    from spacerocks.time import Time

    SPACEROCKS_AVAILABLE = True
except ImportError:
    SPACEROCKS_AVAILABLE = False
    SpaceRock = None
    Time = None


def _name_to_id(name: str) -> int:
    """Convert object name to a stable integer ID."""
    hash_hex = hashlib.md5(name.encode()).hexdigest()[:15]
    return int(hash_hex, 16)


def _jd_to_mjd(jd: float) -> float:
    """Convert Julian Date to Modified Julian Date."""
    return jd - 2400000.5


@register_source("spacerocks")
class SpaceRocksSource:
    """Source for generating alerts from known asteroid orbits.

    Uses the spacerocks package to fetch orbital data from JPL Horizons
    and generate AlertRecord instances. This is useful for:

    1. **Testing orbit determination**: Generate observations of known
       objects to validate orbit fitting algorithms.

    2. **Synthetic data**: Create realistic alert streams based on
       real asteroid populations.

    3. **Cross-matching**: Compare detected objects against known
       asteroid catalogs.

    The generated AlertRecords include orbital elements in `trail_data`:
    - a: semi-major axis (AU)
    - e: eccentricity
    - inc: inclination (degrees)
    - arg: argument of perihelion (degrees)
    - node: longitude of ascending node (degrees)
    - true_anomaly: true anomaly (degrees)

    Attributes:
        source_name: Always "spacerocks"
        objects: List of object names to fetch
        epoch: Observation epoch (default: now)

    Example:
        >>> source = SpaceRocksSource(
        ...     objects=["Apophis", "Bennu"],
        ...     epoch="2025-01-01"
        ... )
        >>> source.connect()
        >>> alerts = list(source.fetch_alerts())
        >>> print(f"Generated {len(alerts)} alerts")
    """

    source_name = "spacerocks"

    # Default NEOs for testing
    DEFAULT_OBJECTS: ClassVar[list[str]] = [
        "Apophis",
        "Bennu",
        "Ryugu",
        "Didymos",
        "Eros",
        "Itokawa",
        "2024 PT5",  # Recent minimoon candidate
    ]

    def __init__(
        self,
        *,
        objects: list[str] | None = None,
        epoch: str | None = None,
        reference_plane: str = "ECLIPJ2000",
        origin: str = "SSB",
    ):
        """Initialize SpaceRocks source.

        Args:
            objects: List of asteroid/comet names to fetch from JPL Horizons.
                Can use provisional designations (e.g., "2024 PT5") or
                names (e.g., "Apophis"). Default: common NEOs.
            epoch: Observation epoch as ISO date string (e.g., "2025-01-01").
                Default: current time.
            reference_plane: Orbital reference plane. Default: "ECLIPJ2000".
            origin: Coordinate origin. Default: "SSB" (Solar System Barycenter).

        Raises:
            ImportError: If spacerocks package is not installed.
        """
        if not SPACEROCKS_AVAILABLE:
            raise ImportError(
                "spacerocks package not installed. Install with: pip install space-rocks"
            )

        self.objects = objects or self.DEFAULT_OBJECTS
        self.epoch_str = epoch
        self.reference_plane = reference_plane
        self.origin = origin

        self._rocks: list[Any] = []
        self._connected = False
        self._epoch: Any = None

    def connect(self) -> None:
        """Fetch orbital data from JPL Horizons.

        Queries JPL Horizons for each object and stores the orbital
        elements. Failed queries are logged but don't stop processing.

        Raises:
            ConnectionError: If no objects could be fetched.
        """
        if self.epoch_str:
            self._epoch = Time.from_iso(self.epoch_str)
        else:
            self._epoch = Time.now()

        self._rocks = []
        failed = []

        for name in self.objects:
            try:
                rock = SpaceRock.from_horizons(
                    name=name,
                    epoch=self._epoch,
                    reference_plane=self.reference_plane,
                    origin=self.origin.lower(),
                )
                self._rocks.append(rock)
                logger.debug(f"Fetched orbital data for {name}")
            except Exception as e:
                logger.warning(f"Failed to fetch {name} from Horizons: {e}")
                failed.append(name)

        if not self._rocks:
            raise ConnectionError(f"Could not fetch any objects from Horizons. Failed: {failed}")

        self._connected = True
        logger.info(
            f"Connected to SpaceRocks source with {len(self._rocks)} objects",
            extra={"source": "spacerocks", "object_count": len(self._rocks)},
        )

    def fetch_alerts(self, limit: int | None = None) -> Iterator[AlertRecord]:
        """Generate AlertRecords from orbital data.

        Each object produces one AlertRecord with orbital elements
        stored in the `trail_data` field.

        Args:
            limit: Maximum number of alerts to yield (None = all).

        Yields:
            AlertRecord instances with orbital data.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connected:
            raise RuntimeError("Source not connected. Call connect() first.")

        count = 0
        for rock in self._rocks:
            if limit is not None and count >= limit:
                break

            try:
                alert = self._convert_rock(rock)
                if alert is not None:
                    count += 1
                    yield alert
            except Exception as e:
                logger.warning(f"Error converting rock {rock.name}: {e}")
                continue

        logger.info(f"Generated {count} alerts from SpaceRocks source")

    def _convert_rock(self, rock: Any) -> AlertRecord | None:
        """Convert a SpaceRock to AlertRecord.

        Args:
            rock: SpaceRock instance with orbital data.

        Returns:
            AlertRecord or None if conversion fails.
        """
        name = rock.name
        object_id = _name_to_id(name)

        # Get position for RA/Dec
        # SpaceRock stores position in AU, we need to convert to sky coords
        # For now, use orbital elements to approximate
        try:
            ra = float(rock.node)  # Approximate using node
            dec = float(rock.inc) - 90  # Approximate using inclination
            # Clamp to valid ranges
            ra = ra % 360
            dec = max(-90, min(90, dec))
        except (AttributeError, TypeError):
            ra = 0.0
            dec = 0.0

        # Get epoch as MJD
        try:
            mjd = _jd_to_mjd(float(rock.epoch.jd))
        except (AttributeError, TypeError):
            mjd = _jd_to_mjd(float(self._epoch.jd))

        # Store orbital elements in trail_data
        trail_data: dict[str, Any] = {}
        for attr in ["a", "e", "inc", "arg", "node", "true_anomaly", "q", "Q"]:
            try:
                val = getattr(rock, attr, None)
                if val is not None:
                    trail_data[attr] = float(val)
            except (TypeError, ValueError):
                pass

        # Add metadata
        trail_data["name"] = name
        trail_data["reference_plane"] = self.reference_plane
        trail_data["origin"] = self.origin
        trail_data["source"] = "jpl_horizons"

        return AlertRecord(
            alert_id=object_id,
            dia_source_id=object_id * 1000,
            dia_object_id=object_id,
            ra=ra,
            dec=dec,
            mjd=mjd,
            filter_name="spacerocks",
            # Mark as SSO
            has_ss_source=True,
            ss_object_id=name,
            # Store orbital elements
            trail_data=trail_data,
            # Set extendedness based on typical asteroid values
            extendedness_median=0.1,  # Point-like
            extendedness_min=0.0,
            extendedness_max=0.2,
        )

    def close(self) -> None:
        """Release resources."""
        self._rocks = []
        self._connected = False
        self._epoch = None

    def __enter__(self) -> SpaceRocksSource:
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def __repr__(self) -> str:
        """String representation."""
        return f"SpaceRocksSource(objects={len(self.objects)}, connected={self._connected})"
