"""
LSST Alert Pipeline Configuration
Edit this file with your specific settings
"""

from pathlib import Path

# ============================================================================
# BASE DIRECTORIES
# ============================================================================

# Base directory for the pipeline
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

# ============================================================================
# KAFKA CONFIGURATION
# ============================================================================

KAFKA_CONFIG = {
    # Kafka broker(s)
    "bootstrap.servers": "localhost:9092",  # UPDATE THIS
    # Consumer group ID
    "group.id": "lsst-alert-consumer",
    # Where to start reading
    "auto.offset.reset": "earliest",  # or 'latest'
    # Auto-commit settings
    "enable.auto.commit": True,
    "auto.commit.interval.ms": 5000,
    # Performance tuning
    "max.poll.interval.ms": 300000,  # 5 minutes
    "session.timeout.ms": 30000,  # 30 seconds
    # Optional: Schema registry (uncomment if using)
    # 'schema.registry.url': 'http://localhost:8081',
    # Optional: SSL/TLS settings (uncomment if needed)
    # 'security.protocol': 'SSL',
    # 'ssl.ca.location': '/path/to/ca-cert',
    # 'ssl.certificate.location': '/path/to/client-cert',
    # 'ssl.key.location': '/path/to/client-key',
    # Optional: SASL authentication (uncomment if needed)
    # 'security.protocol': 'SASL_SSL',
    # 'sasl.mechanisms': 'PLAIN',
    # 'sasl.username': 'your-username',
    # 'sasl.password': 'your-password',
}

# Kafka topic to consume from
KAFKA_TOPIC = "lsst-extendedness-filtered"  # UPDATE THIS

# ============================================================================
# CONSUMER RUNTIME CONFIGURATION
# ============================================================================

CONSUMER_CONFIG = {
    # Maximum runtime per execution (seconds)
    # Set to None for indefinite
    "duration_seconds": 3600,  # 1 hour
    # Maximum messages to process per run
    # Set to None for unlimited
    "max_messages": 10000,
    # Kafka poll timeout (seconds)
    "poll_timeout": 1.0,
    # CSV batch size (save every N records)
    "csv_batch_size": 100,
}

# ============================================================================
# DATA STORAGE CONFIGURATION
# ============================================================================

OUTPUT_CONFIG = {
    # CSV retention (days)
    "csv_retention_days": 90,
    # Cutout retention (days)
    "cutout_retention_days": 30,
    # Log retention (days)
    "log_retention_days": 60,
    # Archive before deletion
    "archive_before_delete": True,
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
    "snr",
    "extendednessMedian",
    "extendednessMin",
    "extendednessMax",
    # All fields starting with 'trail' are automatically extracted
    # All fields starting with 'pixelFlags' are automatically extracted
]

# Fields to extract from SSObject (when present)
SSOBJECT_FIELDS = [
    "ssObjectId",
    "ssObjectReassocTimeMjdTai",
]

# Cutout types to save
CUTOUT_TYPES = ["science", "template", "difference"]

# Additional features
FEATURES = {
    "save_raw_messages": False,  # Save raw Avro messages
    "create_thumbnails": False,  # Create PNG thumbnails (requires PIL)
    "validate_cutouts": False,  # Validate cutouts after saving
    "track_sssource": True,  # Track SSSource associations
}

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

LOGGING_CONFIG = {
    "level": "INFO",  # DEBUG, INFO, WARNING, ERROR
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    # Rotating file handler settings
    "max_bytes": 10 * 1024 * 1024,  # 10MB
    "backup_count": 5,
    # Log to console
    "console": True,
    # Separate error log
    "error_log": True,
}

# ============================================================================
# ANTARES FILTER CONFIGURATION (for reference)
# ============================================================================

# These settings are used in the ANTARES filter
# They're here for documentation purposes
ANTARES_FILTER_CONFIG = {
    # Extendedness thresholds
    "extendedness_median_min": 0.0,
    "extendedness_median_max": 1.0,
    "extendedness_min_threshold": 0.0,
    "extendedness_max_threshold": 1.0,
    # SSSource requirement
    "require_sssource": True,  # True = require, False = exclude
    # Reassociation detection window (days)
    # If ssObjectReassocTimeMjdTai is within this many days of observation,
    # consider it a recent reassociation
    "reassoc_window_days": 1.0,
}

# ============================================================================
# REASSOCIATION TRACKING
# ============================================================================

# The consumer tracks previously seen DIASources to detect reassociations
# State is saved in: temp/consumer_state.json
# This enables detection of:
# - New SSObject associations
# - Changed SSObject associations
# - Updated reassociation timestamps
