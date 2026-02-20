"""
LSST Alert Pipeline - Utilities Package
Helper functions and utilities for alert processing
"""

# Import utility modules for easy access
from . import csv_writer, cutout_processor, kafka_helpers
from .csv_writer import (
    CSVWriter,
    DynamicCSVWriter,
    append_to_csv,
    convert_csv_to_json,
    csv_stats,
    filter_csv,
    merge_csv_files,
    split_csv_by_column,
    write_csv_with_metadata,
)

# Import commonly used classes/functions
from .cutout_processor import CutoutProcessor, extract_all_cutouts
from .kafka_helpers import (
    create_consumer,
    get_consumer_lag,
    get_message_count_estimate,
    get_topic_info,
    list_topics,
    test_connection,
)

__all__ = [
    "CSVWriter",
    # Classes
    "CutoutProcessor",
    "DynamicCSVWriter",
    "append_to_csv",
    "convert_csv_to_json",
    # Functions - Kafka
    "create_consumer",
    "csv_stats",
    "csv_writer",
    "cutout_processor",
    # Functions - Cutouts
    "extract_all_cutouts",
    "filter_csv",
    "get_consumer_lag",
    "get_message_count_estimate",
    "get_topic_info",
    # Modules
    "kafka_helpers",
    "list_topics",
    "merge_csv_files",
    "split_csv_by_column",
    "test_connection",
    # Functions - CSV
    "write_csv_with_metadata",
]
