"""
ANTARES alert source for the LSST Extendedness Pipeline.

This module provides an ANTARESSource that uses the antares-client library
to consume alerts from ANTARES broker topics.

ANTARES (Arizona-NOAO Temporal Analysis and Response to Events System) is
an alert broker that provides filtered and enriched alerts from LSST.

Example:
    >>> from lsst_extendedness.sources import ANTARESSource
    >>>
    >>> source = ANTARESSource(
    ...     topics=["extragalactic_staging"],
    ...     api_key="YOUR_API_KEY",
    ...     api_secret="YOUR_API_SECRET",
    ... )
    >>> source.connect()
    >>> for alert in source.fetch_alerts(limit=100):
    ...     print(f"Alert {alert.alert_id} at RA={alert.ra}")
    >>> source.close()

See Also:
    - ANTARES Client documentation: https://nsf-noirlab.gitlab.io/csdc/antares/client/
    - ANTARES Streaming: https://nsf-noirlab.gitlab.io/csdc/antares/client/tutorial/streaming.html
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from lsst_extendedness.models.alerts import AlertRecord
from lsst_extendedness.sources.protocol import register_source

if TYPE_CHECKING:
    from antares_client import StreamingClient
    from antares_client.models import Locus

logger = logging.getLogger(__name__)

# Lazy import for antares_client
_antares_client = None


def _import_antares_client() -> Any:
    """Lazy import of antares-client."""
    global _antares_client
    if _antares_client is None:
        try:
            import antares_client

            _antares_client = antares_client
        except ImportError as e:
            raise ImportError(
                "antares-client is required for ANTARESSource. "
                "Install with: pip install antares-client"
            ) from e
    return _antares_client


@register_source("antares")
class ANTARESSource:
    """ANTARES source for consuming alerts via the antares-client library.

    This source provides a high-level interface to ANTARES broker,
    converting ANTARES Locus objects to AlertRecord instances.

    ANTARES provides filtered and enriched alerts with:
    - Alert history (multiple observations per locus)
    - Catalog cross-matches
    - User-defined tags
    - Gravitational wave associations

    Attributes:
        source_name: Always "antares"
        topics: List of ANTARES topic names to subscribe to
        api_key: ANTARES API key for authentication
        api_secret: ANTARES API secret for authentication

    Example:
        >>> source = ANTARESSource(
        ...     topics=["extragalactic_staging", "nuclear_transient_staging"],
        ...     api_key="your_key",
        ...     api_secret="your_secret",
        ... )
        >>> source.connect()
        >>> for alert in source.fetch_alerts(limit=1000):
        ...     if alert.has_ss_source:
        ...         print(f"SSO Alert: {alert.ss_object_id}")
        >>> source.close()

    See Also:
        - KafkaSource: For direct Kafka access with AVRO deserialization
        - FileSource: For importing from AVRO/CSV files
    """

    source_name = "antares"

    def __init__(
        self,
        topics: list[str],
        api_key: str,
        api_secret: str,
        *,
        poll_timeout: float = 10.0,
        include_locus_history: bool = False,
    ):
        """Initialize ANTARES source.

        Args:
            topics: List of ANTARES topic names to subscribe to.
                Common topics include:
                - "extragalactic_staging": Extragalactic transients
                - "nuclear_transient_staging": Nuclear transients
                - "solar_system_staging": Solar system objects
            api_key: ANTARES API key for authentication.
                Get credentials at: https://antares.noirlab.edu/
            api_secret: ANTARES API secret for authentication.
            poll_timeout: Timeout for polling messages (seconds).
                Default is 10 seconds.
            include_locus_history: If True, include all alerts in the locus
                history (multiple AlertRecords per locus). If False, only
                yield the most recent alert. Default is False.
        """
        self.topics = topics
        self.api_key = api_key
        self.api_secret = api_secret
        self.poll_timeout = poll_timeout
        self.include_locus_history = include_locus_history

        self._client: StreamingClient | None = None
        self._connected = False

    def connect(self) -> None:
        """Connect to ANTARES broker.

        Raises:
            ImportError: If antares-client is not installed.
            ConnectionError: If connection to ANTARES fails.
        """
        antares = _import_antares_client()

        try:
            self._client = antares.StreamingClient(
                topics=self.topics,
                api_key=self.api_key,
                api_secret=self.api_secret,
            )
            self._connected = True
            logger.info(
                "Connected to ANTARES broker",
                extra={"topics": self.topics},
            )
        except Exception as e:
            raise ConnectionError(f"Failed to connect to ANTARES: {e}") from e

    def fetch_alerts(self, limit: int | None = None) -> Iterator[AlertRecord]:
        """Fetch and yield alerts from ANTARES.

        Polls ANTARES for locus objects and converts them to AlertRecord
        instances. By default, only the most recent alert from each locus
        is yielded.

        Args:
            limit: Maximum number of alerts to fetch (None = unlimited).

        Yields:
            AlertRecord instances with fields populated from ANTARES locus data.

        Raises:
            RuntimeError: If not connected to ANTARES.

        Example:
            >>> for alert in source.fetch_alerts(limit=100):
            ...     print(f"Alert {alert.alert_id}: extendedness={alert.extendedness_median}")
        """
        if not self._connected or self._client is None:
            raise RuntimeError("Source not connected. Call connect() first.")

        count = 0

        try:
            for _topic, locus in self._client.iter():
                if limit is not None and count >= limit:
                    break

                try:
                    if self.include_locus_history:
                        # Yield all alerts from locus history
                        for alert_record in self._convert_locus_history(locus):
                            count += 1
                            yield alert_record
                            if limit is not None and count >= limit:
                                break
                    else:
                        # Only yield most recent alert
                        result = self._convert_locus(locus)
                        if result is not None:
                            count += 1
                            yield result

                except Exception as e:
                    logger.error(
                        "Error converting ANTARES locus to AlertRecord",
                        extra={"locus_id": getattr(locus, "locus_id", "unknown"), "error": str(e)},
                        exc_info=True,
                    )
                    continue

        except KeyboardInterrupt:
            logger.info("Interrupted by user, stopping alert fetch")
        except Exception as e:
            logger.error(f"Error fetching alerts from ANTARES: {e}", exc_info=True)
            raise

        logger.info(f"Fetched {count} alerts from ANTARES")

    def _convert_locus(self, locus: Locus) -> AlertRecord | None:
        """Convert an ANTARES Locus to an AlertRecord.

        Extracts the most recent alert from the locus and maps
        ANTARES properties to AlertRecord fields.

        Args:
            locus: ANTARES Locus object

        Returns:
            AlertRecord if conversion succeeds, None otherwise
        """
        if not locus.alerts:
            logger.debug(f"Locus {locus.locus_id} has no alerts")
            return None

        # Get the most recent alert
        latest_alert = locus.alerts[-1]
        props = latest_alert.properties

        return self._create_alert_record(locus, latest_alert, props)

    def _convert_locus_history(self, locus: Locus) -> Iterator[AlertRecord]:
        """Convert all alerts in a locus history to AlertRecords.

        Args:
            locus: ANTARES Locus object

        Yields:
            AlertRecord for each alert in the locus history
        """
        if not locus.alerts:
            return

        for alert in locus.alerts:
            props = alert.properties
            record = self._create_alert_record(locus, alert, props)
            if record is not None:
                yield record

    def _create_alert_record(
        self,
        locus: Locus,
        alert: Any,
        props: dict[str, Any],
    ) -> AlertRecord | None:
        """Create an AlertRecord from ANTARES locus/alert data.

        Args:
            locus: ANTARES Locus object
            alert: ANTARES Alert object
            props: Alert properties dictionary

        Returns:
            AlertRecord or None if required fields are missing
        """
        try:
            # Extract SSObject information from multiple sources
            has_ss_source, ss_object_id, ss_reassoc_time = self._extract_ss_info(
                locus, alert, props
            )

            # Determine if this is a recent reassociation
            is_reassociation = False
            reassociation_reason = None
            if has_ss_source and ss_reassoc_time is not None:
                obs_time = props.get("midPointTai") or alert.mjd
                if obs_time is not None:
                    time_diff = abs(ss_reassoc_time - obs_time)
                    if time_diff <= 1.0:  # Within 1 day
                        is_reassociation = True
                        reassociation_reason = (
                            f"Recent SSObject reassociation (dt={time_diff:.3f} days)"
                        )

            # Extract trail data
            trail_data = {
                key: value
                for key, value in props.items()
                if key.startswith("trail") and value is not None
            }

            # Extract pixel flags
            pixel_flags = {
                key: value
                for key, value in props.items()
                if key.startswith("pixelFlags") and value is not None
            }

            # Build AlertRecord
            return AlertRecord(
                alert_id=int(alert.alert_id) if hasattr(alert, "alert_id") else 0,
                dia_source_id=props.get("diaSourceId", 0),
                dia_object_id=props.get("diaObjectId"),
                ra=props.get("ra") or locus.ra,
                dec=props.get("decl") or locus.dec,
                mjd=props.get("midPointTai") or alert.mjd,
                filter_name=props.get("filterName"),
                ps_flux=props.get("psFlux"),
                ps_flux_err=props.get("psFluxErr"),
                snr=props.get("snr"),
                extendedness_median=props.get("extendednessMedian"),
                extendedness_min=props.get("extendednessMin"),
                extendedness_max=props.get("extendednessMax"),
                has_ss_source=has_ss_source,
                ss_object_id=ss_object_id,
                ss_object_reassoc_time_mjd=ss_reassoc_time,
                is_reassociation=is_reassociation,
                reassociation_reason=reassociation_reason,
                trail_data=trail_data,
                pixel_flags=pixel_flags,
            )

        except Exception as e:
            logger.warning(f"Failed to create AlertRecord: {e}")
            return None

    def _extract_ss_info(
        self,
        locus: Locus,
        alert: Any,
        props: dict[str, Any],
    ) -> tuple[bool, str | None, float | None]:
        """Extract Solar System Object information from multiple sources.

        ANTARES may provide SSObject data in different ways:
        1. Via alert properties (ssObjectId)
        2. Via raw alert packet (ssObject dict)
        3. Via locus tags (solar_system, sso, etc.)

        Args:
            locus: ANTARES Locus object
            alert: ANTARES Alert object
            props: Alert properties dictionary

        Returns:
            Tuple of (has_ss_source, ss_object_id, reassoc_time_mjd)
        """
        has_ss_source = False
        ss_object_id = None
        ss_reassoc_time = None

        # Method 1: Check alert properties
        ss_object_id = props.get("ssObjectId")
        if ss_object_id is not None:
            has_ss_source = True
            ss_reassoc_time = props.get("ssObjectReassocTimeMjdTai")

        # Method 2: Check raw alert packet if available
        if not has_ss_source and hasattr(alert, "packet"):
            packet = getattr(alert, "packet", {}) or {}
            ss_object = packet.get("ssObject")
            if ss_object is not None and len(ss_object) > 0:
                has_ss_source = True
                ss_object_id = ss_object.get("ssObjectId")
                if ss_reassoc_time is None:
                    ss_reassoc_time = ss_object.get("ssObjectReassocTimeMjdTai")

        # Method 3: Check locus tags
        if not has_ss_source and hasattr(locus, "tags"):
            tags = getattr(locus, "tags", []) or []
            sso_tags = {"solar_system", "sso", "asteroid", "comet", "neo", "mba"}
            if any(tag.lower() in sso_tags for tag in tags):
                has_ss_source = True

        return has_ss_source, ss_object_id, ss_reassoc_time

    def close(self) -> None:
        """Close ANTARES connection.

        Safe to call multiple times.
        """
        if self._client is not None:
            try:
                self._client.close()
            except Exception as e:
                logger.warning(f"Error closing ANTARES client: {e}")
            finally:
                self._client = None
        self._connected = False

    def __enter__(self) -> ANTARESSource:
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def __repr__(self) -> str:
        """String representation."""
        return f"ANTARESSource(topics={self.topics!r})"
