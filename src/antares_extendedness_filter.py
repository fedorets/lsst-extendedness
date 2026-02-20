"""
ANTARES Level 2 Filter for LSST Alerts
Filters based on DIASource extendedness values and SSSource presence/reassociation

This filter captures:
1. New DIASources that match extendedness criteria and SSSource requirements
2. DIASources that were recently reassociated with an SSObject (even if previously seen)

The reassociation detection works by checking if ssObjectReassocTimeMjdTai is recent
relative to the observation time, indicating a fresh association update.

NOTE: This filter only determines which alerts PASS through to the output Kafka topic.
It does NOT modify or control which fields are included in the alert packets.
All fields in the original LSST alert packet (including ssObjectId, ssObjectReassocTimeMjdTai,
trail* flags, and pixelFlags* fields) are automatically included in alerts that pass the filter.

The downstream consumer (lsst_alert_consumer.py) is responsible for extracting
these fields from the alert packets and storing them in CSV files.
"""


def extendedness_filter(locus):
    """
    ANTARES filter function that filters alerts based on extendedness criteria,
    SSSource presence, and recent reassociations.

    This filter checks:
    1. extendednessMedian, extendednessMin, and extendednessMax from DIASource table
    2. Presence of SSSource schema (regardless of values)
    3. Recent SSObject reassociation (ssObjectReassocTimeMjdTai close to observation time)

    You'll need to configure the threshold values based on your science case.

    Parameters:
    -----------
    locus : antares.devkit.locus.Locus
        ANTARES locus object containing alert information

    Returns:
    --------
    bool
        True if the alert passes the filter, False otherwise
    """

    # Configuration - adjust these values for your science case
    EXTENDEDNESS_MEDIAN_MIN = 0.0  # Minimum median extendedness
    EXTENDEDNESS_MEDIAN_MAX = 1.0  # Maximum median extendedness
    EXTENDEDNESS_MIN_THRESHOLD = 0.0  # Minimum value threshold
    EXTENDEDNESS_MAX_THRESHOLD = 1.0  # Maximum value threshold

    # SSSource requirement: True to require SSSource, False to exclude SSSource
    REQUIRE_SSSOURCE = True

    # Reassociation detection window (days)
    # If ssObjectReassocTimeMjdTai is within this many days of the observation,
    # consider it a recent reassociation and pass the alert through
    REASSOC_WINDOW_DAYS = 1.0  # Default: 1 day

    # Get the most recent alert
    if not locus.alerts:
        return False

    latest_alert = locus.alerts[-1]

    # Extract extendedness properties from the alert
    # These come from the DIASource table fields
    try:
        extendedness_median = latest_alert.properties.get("extendednessMedian")
        extendedness_min = latest_alert.properties.get("extendednessMin")
        extendedness_max = latest_alert.properties.get("extendednessMax")

        # Check if all required fields are present
        if None in [extendedness_median, extendedness_min, extendedness_max]:
            return False

        # Apply extendedness filter criteria
        passes_median = EXTENDEDNESS_MEDIAN_MIN <= extendedness_median <= EXTENDEDNESS_MEDIAN_MAX
        passes_min = extendedness_min >= EXTENDEDNESS_MIN_THRESHOLD
        passes_max = extendedness_max <= EXTENDEDNESS_MAX_THRESHOLD

        passes_extendedness = passes_median and passes_min and passes_max

        # Check for SSSource schema attachment
        # The SSSource data is typically in the alert packet's ssObject field
        # We're just checking if it exists, not validating its contents
        has_sssource = False
        ssobject_reassoc_time = None

        # Method 1: Check via alert properties (if ANTARES exposes it this way)
        if hasattr(latest_alert, "properties"):
            # Check for any SSSource-related fields
            sssource_fields = ["ssObjectId", "ssObject"]
            has_sssource = any(
                latest_alert.properties.get(field) is not None for field in sssource_fields
            )

            # Get reassociation timestamp if available
            ssobject_reassoc_time = latest_alert.properties.get("ssObjectReassocTimeMjdTai")

        # Method 2: Check via raw alert packet (if available)
        # The ssObject field in LSST alert packets indicates SSSource attachment
        if (
            not has_sssource
            and hasattr(latest_alert, "packet")
            and "ssObject" in latest_alert.packet
            and latest_alert.packet["ssObject"] is not None
        ):
            has_sssource = True
            if ssobject_reassoc_time is None:
                ssobject_reassoc_time = latest_alert.packet["ssObject"].get(
                    "ssObjectReassocTimeMjdTai"
                )

        # Method 3: Check via locus tags (ANTARES may tag SSO associations)
        if not has_sssource and hasattr(locus, "tags"):
            # Check for solar system object tags
            sso_tags = ["solar_system", "sso", "asteroid", "comet"]
            has_sssource = any(tag in locus.tags for tag in sso_tags)

        # Check for recent reassociation
        is_recent_reassoc = False
        if has_sssource and ssobject_reassoc_time is not None:
            # Get observation time
            obs_time = latest_alert.properties.get("midPointTai")

            if obs_time is not None:
                # Check if reassociation is recent (within window of observation)
                time_diff = abs(ssobject_reassoc_time - obs_time)
                is_recent_reassoc = time_diff <= REASSOC_WINDOW_DAYS

        # Apply SSSource filter with reassociation logic
        if REQUIRE_SSSOURCE:
            # Pass if:
            # 1. Has SSSource AND meets extendedness criteria, OR
            # 2. Has recent reassociation (even if previously seen)
            passes_sssource = has_sssource and (passes_extendedness or is_recent_reassoc)
        else:
            # Exclude SSSource objects
            passes_sssource = not has_sssource and passes_extendedness

        # Return True if criteria are met
        # For REQUIRE_SSSOURCE=True: pass if has SSSource AND (good extendedness OR recent reassoc)
        # For REQUIRE_SSSOURCE=False: pass if no SSSource AND good extendedness
        return passes_sssource

    except (AttributeError, KeyError):
        # Log the error if needed (ANTARES provides logging)
        return False


# ANTARES filter metadata (required)
filter_name = "extendedness_sssource_reassoc_filter"
filter_version = "2.0.0"
filter_description = "Filters LSST alerts based on DIASource extendedness, SSSource presence, and recent SSObject reassociations"

# Tags for categorizing this filter
tags = [
    "extended_sources",
    "morphology",
    "galaxies",
    "solar_system_objects",
    "sso",
    "reassociation",
]

# This is the main entry point that ANTARES will call
run = extendedness_filter
