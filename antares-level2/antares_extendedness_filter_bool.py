"""
ANTARES Level 2 Filter for LSST Alerts (boolean return variant)
Filters based on DIASource extendedness values and SSSource presence

NOTE: This filter only determines which alerts PASS through to the output Kafka topic.
It does NOT modify or control which fields are included in the alert packets.
All fields in the original LSST alert packet (including ssObjectId, ssObjectReassocTimeMjdTai,
trail* flags, and pixelFlags* fields) are automatically included in alerts that pass the filter.

The downstream consumer (lsst_alert_consumer.py) is responsible for extracting
these fields from the alert packets and storing them in CSV files.

--- IMPLEMENTATION NOTE: run() return convention ---
This version implements run() -> bool, returning True for passing alerts and False
otherwise. This follows the function-based ANTARES filter API convention, and is
consistent with all existing examples in this repository.

The primary version (antares_extendedness_filter_.py) instead uses run() -> None and
calls locus.tag(), following the class-based ANTARES DevKit API as documented online.

Use this file if the ANTARES team confirms that the class-based API accepts a boolean
return rather than locus.tag().
"""

from __future__ import annotations

from typing import ClassVar


class ExtendednessFilter:
    """
    ANTARES Level 2 filter that filters alerts based on extendedness criteria
    and the presence of SSSource schema attachment.

    This filter checks:
    1. extendednessMedian, extendednessMin, and extendednessMax from DIASource table
    2. Presence of SSSource schema (regardless of values)

    Adjust the threshold class attributes for your science case.
    """

    NAME = "extendedness_sssource_filter"
    VERSION = "1.1.0"
    DESCRIPTION = (
        "Filters LSST alerts based on DIASource extendedness values and SSSource schema presence"
    )
    TAGS: ClassVar[list[str]] = [
        "extended_sources",
        "morphology",
        "galaxies",
        "solar_system_objects",
        "sso",
    ]

    # Declares the tags this filter may apply to passing loci via locus.tag().
    # TODO: confirm tag names and descriptions with the ANTARES team before deployment.
    OUTPUT_TAGS: ClassVar[list[dict[str, str]]] = [
        {
            "name": "extendedness_sso_candidate",
            "description": (
                "Alert passes extendedness thresholds and has an SSSource attachment, "
                "marking it as a candidate solar system object for minimoon follow-up."
            ),
        },
    ]

    # Extendedness thresholds - adjust these values for your science case.
    # Values will be adjusted after taking a closer look at the images.
    EXTENDEDNESS_MEDIAN_MIN = 0.25  # Minimum median extendedness
    EXTENDEDNESS_MEDIAN_MAX = 1.0  # Maximum median extendedness
    EXTENDEDNESS_MIN_THRESHOLD = 0.25  # Minimum value threshold
    EXTENDEDNESS_MAX_THRESHOLD = 1.0  # Maximum value threshold

    # SSSource requirement: True to require SSSource, False to exclude SSSource.
    # Initially, the filter will include only the objects with attached SSSources,
    # that is, already attached to a small Solar System object. It will be later removed
    # when new discoveries will be also required.
    REQUIRE_SSSOURCE = True

    SLACK_CHANNEL = "#lsst-extendedness"

    def run(self, locus) -> bool:
        """
        Main filter entry point called by ANTARES for each locus.

        Parameters
        ----------
        locus : antares.devkit.locus.Locus
            ANTARES locus object containing alert information

        Returns
        -------
        bool
            True if the alert passes the filter, False otherwise.
        """
        if not locus.alerts:
            return False

        latest_alert = locus.alerts[-1]

        try:
            passes_extendedness = self._check_extendedness(latest_alert)
            has_sssource = self._check_sssource(locus, latest_alert)

            if self.REQUIRE_SSSOURCE:
                passes_sssource = has_sssource
            else:
                passes_sssource = not has_sssource

            return passes_extendedness and passes_sssource

        except (AttributeError, KeyError):
            return False

    def _check_extendedness(self, alert):
        """
        Check whether the alert passes extendedness thresholds.

        Parameters
        ----------
        alert : antares.devkit.alert.Alert
            The most recent alert from the locus

        Returns
        -------
        bool
            True if all extendedness criteria are met
        """
        extendedness_median = alert.properties.get("extendednessMedian")
        extendedness_min = alert.properties.get("extendednessMin")
        extendedness_max = alert.properties.get("extendednessMax")

        if None in [extendedness_median, extendedness_min, extendedness_max]:
            return False

        passes_median = (
            self.EXTENDEDNESS_MEDIAN_MIN <= extendedness_median <= self.EXTENDEDNESS_MEDIAN_MAX
        )
        passes_min = extendedness_min >= self.EXTENDEDNESS_MIN_THRESHOLD
        passes_max = extendedness_max <= self.EXTENDEDNESS_MAX_THRESHOLD

        return passes_median and passes_min and passes_max

    def _check_sssource(self, locus, alert):
        """
        Check whether the alert has an SSSource attachment.

        Tries three methods in order:
        1. Alert properties (ssObjectId / ssObject fields)
        2. Raw alert packet (ssObject field)
        3. ANTARES locus tags (solar system object classifications)

        Parameters
        ----------
        locus : antares.devkit.locus.Locus
            ANTARES locus object
        alert : antares.devkit.alert.Alert
            The most recent alert from the locus

        Returns
        -------
        bool
            True if an SSSource attachment is detected
        """
        # Method 1: Check via alert properties
        if hasattr(alert, "properties"):
            sssource_fields = ["ssObjectId", "ssObject"]
            if any(alert.properties.get(field) is not None for field in sssource_fields):
                return True

        # Method 2: Check via raw alert packet
        if (
            hasattr(alert, "packet")
            and "ssObject" in alert.packet
            and alert.packet["ssObject"] is not None
        ):
            return True

        # Method 3: Check via locus tags
        if hasattr(locus, "tags"):
            sso_tags = ["solar_system", "sso", "asteroid", "comet"]
            if any(tag in locus.tags for tag in sso_tags):
                return True

        return False
