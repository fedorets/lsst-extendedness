"""
Configuration file for LSST Alert Pipeline
Copy this to config.py and customize for your setup
"""

# ============================================================================
# PART 1: ANTARES FILTER CONFIGURATION
# ============================================================================

# Extendedness filter thresholds
# These values filter on DIASource extendedness measurements
EXTENDEDNESS_FILTER = {
    # Median extendedness range
    "median_min": 0.0,
    "median_max": 1.0,
    # Min/max value thresholds
    "min_threshold": 0.0,
    "max_threshold": 1.0,
}

# SSSource schema filter
# Set to True to REQUIRE SSSource attachment, False to EXCLUDE alerts with SSSource
SSSOURCE_FILTER = {
    "require_sssource": True,  # True = only alerts WITH SSSource, False = only alerts WITHOUT SSSource
}

# ANTARES filter metadata
FILTER_METADATA = {
    "name": "extendedness_sssource_filter",
    "version": "1.1.0",
    "description": "Filters LSST alerts based on DIASource extendedness values and SSSource schema presence",
    "tags": ["extended_sources", "morphology", "galaxies", "solar_system_objects", "sso"],
}


# ============================================================================
# PART 2: KAFKA CONSUMER CONFIGURATION
# ============================================================================

# Kafka broker configuration
KAFKA_CONFIG = {
    # Kafka broker address(es)
    "bootstrap.servers": "localhost:9092",
    # Consumer group ID
    "group.id": "lsst-alert-consumer",
    # Where to start reading (earliest/latest)
    "auto.offset.reset": "earliest",
    # Auto-commit offsets
    "enable.auto.commit": True,
    "auto.commit.interval.ms": 5000,
    # Optional: Schema registry for Confluent Wire Format
    # 'schema.registry.url': 'http://localhost:8081',
}

# Topic configuration
KAFKA_TOPIC = "lsst-extendedness-filtered"

# Output configuration
OUTPUT_CONFIG = {
    # Base directory for all outputs
    "base_dir": "./lsst_alerts",
    # Data subdirectories
    "data_dir": "data",
    "cutout_dir": "cutouts",
    # CSV batch size (save every N records)
    "csv_batch_size": 100,
    # Data retention (days)
    "retention_days": 30,
}

# Consumer runtime configuration
CONSUMER_CONFIG = {
    # Maximum runtime per execution (seconds)
    # Set to None for indefinite
    "duration_seconds": 3600,  # 1 hour
    # Maximum messages to process per run
    # Set to None for unlimited
    "max_messages": 10000,
    # Kafka poll timeout (seconds)
    "poll_timeout": 1.0,
}

# Logging configuration
LOGGING_CONFIG = {
    "level": "INFO",  # DEBUG, INFO, WARNING, ERROR
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "log_file": None,  # Set to path for file logging
}


# ============================================================================
# ALERT PROCESSING CONFIGURATION
# ============================================================================

# Fields to extract from DIASource
DIASOURCE_FIELDS = [
    "diaSourceId",
    "diaObjectId",
    "ra",
    "decl",
    "midPointTai",
    "filterName",
    "psFlux",
    "psFluxErr",
    "extendednessMedian",
    "extendednessMin",
    "extendednessMax",
    "snr",
    "chi",
]

# Cutout types to save
CUTOUT_TYPES = ["science", "template", "difference"]

# Additional alert metadata to extract
ADDITIONAL_FIELDS = {
    "include_prvDiaSources": True,  # Include previous detections
    "include_diaObject": True,  # Include associated object info
    "include_ssObject": False,  # Include solar system object info
}
