"""
LSST Alert Kafka Consumer (v2.0)
Consumes filtered alerts from ANTARES broker with organized directory structure
"""

import io
import json
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import fastavro
import pandas as pd
from astropy.io import fits
from confluent_kafka import Consumer, KafkaError


# Setup logging
def setup_logging(log_dir):
    """Configure logging with rotation and separate error log."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")

    # Main log file
    log_file = log_dir / "consumer" / f"lsst_consumer_{today}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Error log file
    error_file = log_dir / "error" / f"errors_{today}.log"
    error_file.parent.mkdir(parents=True, exist_ok=True)

    # Configure root logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(console_formatter)

    # File handler (all logs)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
    )
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(file_formatter)

    # Error file handler (errors only)
    error_handler = RotatingFileHandler(
        error_file,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.addHandler(error_handler)

    # Create 'latest' symlink
    latest_link = log_dir / "consumer" / "latest.log"
    if latest_link.exists() or latest_link.is_symlink():
        latest_link.unlink()
    latest_link.symlink_to(log_file.name)

    return logger


class LSSTAlertConsumer:
    """
    Kafka consumer for LSST alerts with organized directory structure.
    """

    def __init__(self, kafka_config, base_dir="./lsst-pipeline"):
        """
        Initialize the LSST alert consumer.

        Parameters:
        -----------
        kafka_config : dict
            Kafka consumer configuration
        base_dir : str
            Base directory for the pipeline
        """
        self.kafka_config = kafka_config
        self.base_dir = Path(base_dir)

        # Setup directory structure
        self._setup_directories()

        # Setup logging
        self.logger = setup_logging(self.log_dir)
        self.logger.info(f"Initializing LSST Alert Consumer in {self.base_dir}")

        # Initialize consumer
        try:
            self.consumer = Consumer(kafka_config)
            self.logger.info("Kafka consumer initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Kafka consumer: {e}")
            raise

        # Alert record buffer
        self.alert_records = []

        # State tracking for reassociations
        self.state_file = self.temp_dir / "consumer_state.json"
        self.processed_sources = {}  # {diaSourceId: {'last_seen': mjd, 'ssObjectId': id, 'reassoc_time': mjd}}
        self._load_state()

        # Statistics
        self.stats = {
            "messages_processed": 0,
            "messages_failed": 0,
            "cutouts_saved": 0,
            "csv_rows_written": 0,
            "reassociations_detected": 0,
            "new_sources": 0,
            "start_time": datetime.now(),
        }

    def _setup_directories(self):
        """Create the directory structure."""
        # Main directories
        self.data_dir = self.base_dir / "data"
        self.log_dir = self.base_dir / "logs"
        self.temp_dir = self.base_dir / "temp"

        # Data subdirectories
        self.csv_dir = self.data_dir / "processed" / "csv"
        self.cutout_dir = self.data_dir / "cutouts"
        self.summary_dir = self.data_dir / "processed" / "summary"
        self.archive_dir = self.data_dir / "archive"

        # Temp subdirectories
        self.partial_csv_dir = self.temp_dir / "partial_csvs"
        self.processing_dir = self.temp_dir / "processing"
        self.failed_dir = self.temp_dir / "failed"

        # Create all directories
        for directory in [
            self.csv_dir,
            self.cutout_dir,
            self.summary_dir,
            self.archive_dir,
            self.log_dir,
            self.partial_csv_dir,
            self.processing_dir,
            self.failed_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    def _load_state(self):
        """Load previously processed sources state."""
        try:
            if self.state_file.exists():
                with open(self.state_file) as f:
                    state = json.load(f)
                    self.processed_sources = state.get("processed_sources", {})
                    self.logger.info(f"Loaded state: {len(self.processed_sources)} tracked sources")
            else:
                self.logger.info("No previous state found, starting fresh")
        except Exception as e:
            self.logger.error(f"Failed to load state: {e}")
            self.processed_sources = {}

    def _save_state(self):
        """Save processed sources state."""
        try:
            state = {
                "processed_sources": self.processed_sources,
                "last_updated": datetime.now().isoformat(),
            }

            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)

            self.logger.debug(f"Saved state: {len(self.processed_sources)} tracked sources")
        except Exception as e:
            self.logger.error(f"Failed to save state: {e}")

    def _get_date_path(self, date_format="%Y/%m"):
        """
        Get date-based subdirectory path.

        Parameters:
        -----------
        date_format : str
            strftime format for date subdirectories

        Returns:
        --------
        str
            Formatted date path
        """
        return datetime.now().strftime(date_format)

    def _get_csv_filepath(self):
        """
        Generate CSV filepath with date organization.

        Returns:
        --------
        Path
            Full path to today's CSV file
        """
        date_path = self._get_date_path("%Y/%m")
        csv_subdir = self.csv_dir / date_path
        csv_subdir.mkdir(parents=True, exist_ok=True)

        today = datetime.now().strftime("%Y%m%d")
        return csv_subdir / f"lsst_alerts_{today}.csv"

    def _get_cutout_filepath(self, dia_source_id, cutout_type):
        """
        Generate cutout filepath with date/type organization.

        Parameters:
        -----------
        dia_source_id : str
            DIASource identifier
        cutout_type : str
            Type of cutout (science/template/difference)

        Returns:
        --------
        Path
            Full path for cutout file
        """
        date_path = self._get_date_path("%Y/%m/%d")
        cutout_subdir = self.cutout_dir / date_path / cutout_type
        cutout_subdir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{dia_source_id}_{cutout_type}_{timestamp}.fits"

        return cutout_subdir / filename

    def extract_cutout(self, cutout_data, dia_source_id, cutout_type):
        """
        Extract and save a FITS cutout from alert data.

        Parameters:
        -----------
        cutout_data : bytes
            Binary FITS cutout data
        dia_source_id : str
            DIASource identifier for filename
        cutout_type : str
            Type of cutout (science/template/difference)

        Returns:
        --------
        str
            Relative path to saved cutout file
        """
        try:
            # Parse FITS data
            fits_data = fits.open(io.BytesIO(cutout_data))

            # Generate filepath
            filepath = self._get_cutout_filepath(dia_source_id, cutout_type)

            # Save FITS file
            fits_data.writeto(filepath, overwrite=True)
            fits_data.close()

            self.stats["cutouts_saved"] += 1
            self.logger.debug(f"Saved cutout: {filepath}")

            # Return relative path from base_dir for CSV storage
            return str(filepath.relative_to(self.base_dir))

        except Exception as e:
            self.logger.error(f"Error saving cutout for {dia_source_id} ({cutout_type}): {e}")
            return None

    def process_alert(self, alert):
        """
        Process a single alert: extract data and cutouts.
        Detects reassociations by comparing with previously processed sources.

        Parameters:
        -----------
        alert : dict
            Deserialized alert packet from Kafka

        Returns:
        --------
        dict
            Record for CSV with alert data and cutout paths
        """
        try:
            # Extract DIASource information
            dia_source = alert.get("diaSource", {})
            dia_source_id = dia_source.get("diaSourceId", "unknown")

            # Build the base record
            record = {
                "alertId": alert.get("alertId"),
                "diaSourceId": dia_source_id,
                "diaObjectId": dia_source.get("diaObjectId"),
                "ra": dia_source.get("ra"),
                "dec": dia_source.get("decl"),
                "mjd": dia_source.get("midPointTai"),
                "filterName": dia_source.get("filterName"),
                "psFlux": dia_source.get("psFlux"),
                "psFluxErr": dia_source.get("psFluxErr"),
                "snr": dia_source.get("snr"),
                "extendednessMedian": dia_source.get("extendednessMedian"),
                "extendednessMin": dia_source.get("extendednessMin"),
                "extendednessMax": dia_source.get("extendednessMax"),
                "timestamp": datetime.now().isoformat(),
            }

            # Check for SSSource and extract SSObject fields
            has_sssource = "ssObject" in alert and alert["ssObject"] is not None
            record["hasSSSource"] = has_sssource

            current_ss_object_id = None
            reassoc_time = None

            if has_sssource:
                ss_object = alert["ssObject"]
                current_ss_object_id = ss_object.get("ssObjectId")
                reassoc_time = ss_object.get("ssObjectReassocTimeMjdTai")
                record["ssObjectId"] = current_ss_object_id
                record["ssObjectReassocTimeMjdTai"] = reassoc_time
            else:
                record["ssObjectId"] = None
                record["ssObjectReassocTimeMjdTai"] = None

            # Check for reassociation
            is_reassociation = False
            reassoc_reason = None

            if str(dia_source_id) in self.processed_sources:
                # This source was seen before
                prev_state = self.processed_sources[str(dia_source_id)]
                prev_ss_id = prev_state.get("ssObjectId")
                prev_reassoc_time = prev_state.get("reassoc_time")

                # Detect reassociation scenarios:
                # 1. Previously had no SSObject, now has one
                if prev_ss_id is None and current_ss_object_id is not None:
                    is_reassociation = True
                    reassoc_reason = "new_association"
                    self.logger.info(
                        f"New SSObject association for DIASource {dia_source_id}: {current_ss_object_id}"
                    )

                # 2. SSObject ID changed
                elif (
                    prev_ss_id is not None
                    and current_ss_object_id is not None
                    and prev_ss_id != current_ss_object_id
                ):
                    is_reassociation = True
                    reassoc_reason = "changed_association"
                    self.logger.info(
                        f"SSObject changed for DIASource {dia_source_id}: {prev_ss_id} -> {current_ss_object_id}"
                    )

                # 3. Reassociation timestamp updated
                elif (
                    reassoc_time is not None
                    and prev_reassoc_time is not None
                    and reassoc_time != prev_reassoc_time
                ):
                    is_reassociation = True
                    reassoc_reason = "updated_reassociation"
                    self.logger.info(
                        f"Reassociation timestamp updated for DIASource {dia_source_id}"
                    )

                if is_reassociation:
                    self.stats["reassociations_detected"] += 1
            else:
                # First time seeing this source
                self.stats["new_sources"] += 1

            # Add reassociation flags to record
            record["isReassociation"] = is_reassociation
            record["reassociationReason"] = reassoc_reason

            # Update tracked state
            self.processed_sources[str(dia_source_id)] = {
                "last_seen": record["mjd"],
                "ssObjectId": current_ss_object_id,
                "reassoc_time": reassoc_time,
                "last_processed": datetime.now().isoformat(),
            }

            # Extract all trail* flags from DIASource
            for key, value in dia_source.items():
                if key.startswith("trail"):
                    record[key] = value

            # Extract all pixelFlags* fields from DIASource
            for key, value in dia_source.items():
                if key.startswith("pixelFlags"):
                    record[key] = value

            # Extract and save cutouts
            cutout_stamps = [
                alert.get("cutoutScience"),
                alert.get("cutoutTemplate"),
                alert.get("cutoutDifference"),
            ]
            cutout_types = ["science", "template", "difference"]

            for cutout_data, cutout_type in zip(cutout_stamps, cutout_types, strict=False):
                if cutout_data:
                    cutout_path = self.extract_cutout(cutout_data, str(dia_source_id), cutout_type)
                    record[f"{cutout_type}_cutout_path"] = cutout_path
                else:
                    record[f"{cutout_type}_cutout_path"] = None

            self.stats["messages_processed"] += 1
            return record

        except Exception as e:
            self.logger.error(f"Error processing alert: {e}", exc_info=True)
            self.stats["messages_failed"] += 1
            return None

    def save_to_csv(self):
        """Save accumulated alert records to CSV file."""
        if not self.alert_records:
            self.logger.warning("No records to save")
            return

        try:
            csv_filepath = self._get_csv_filepath()
            df = pd.DataFrame(self.alert_records)

            # Append to existing file or create new one
            if csv_filepath.exists():
                df.to_csv(csv_filepath, mode="a", header=False, index=False)
            else:
                df.to_csv(csv_filepath, index=False)

            rows_written = len(self.alert_records)
            self.stats["csv_rows_written"] += rows_written
            self.logger.info(f"Saved {rows_written} records to {csv_filepath}")

            # Clear the buffer
            self.alert_records = []

            # Save state periodically after CSV writes
            self._save_state()

        except Exception as e:
            self.logger.error(f"Error saving to CSV: {e}", exc_info=True)

            # Save to failed directory for manual recovery
            try:
                failed_file = (
                    self.failed_dir
                    / f"failed_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                )
                with open(failed_file, "w") as f:
                    json.dump(self.alert_records, f, indent=2)
                self.logger.warning(f"Saved failed batch to {failed_file}")
            except Exception as e2:
                self.logger.error(f"Failed to save recovery file: {e2}")

    def save_daily_summary(self):
        """Save daily statistics summary."""
        try:
            date_path = self._get_date_path("%Y/%m")
            summary_subdir = self.summary_dir / date_path
            summary_subdir.mkdir(parents=True, exist_ok=True)

            today = datetime.now().strftime("%Y%m%d")
            summary_file = summary_subdir / f"daily_stats_{today}.json"

            runtime = (datetime.now() - self.stats["start_time"]).total_seconds()

            summary = {
                "date": today,
                "messages_processed": self.stats["messages_processed"],
                "messages_failed": self.stats["messages_failed"],
                "cutouts_saved": self.stats["cutouts_saved"],
                "csv_rows_written": self.stats["csv_rows_written"],
                "new_sources": self.stats["new_sources"],
                "reassociations_detected": self.stats["reassociations_detected"],
                "total_tracked_sources": len(self.processed_sources),
                "runtime_seconds": runtime,
                "processing_rate": self.stats["messages_processed"] / runtime if runtime > 0 else 0,
                "timestamp": datetime.now().isoformat(),
            }

            with open(summary_file, "w") as f:
                json.dump(summary, f, indent=2)

            self.logger.info(f"Saved daily summary to {summary_file}")

        except Exception as e:
            self.logger.error(f"Error saving daily summary: {e}")

    def consume_alerts(self, topic, duration_seconds=None, max_messages=None):
        """
        Consume alerts from Kafka topic.

        Parameters:
        -----------
        topic : str
            Kafka topic name
        duration_seconds : int, optional
            How long to consume (None = indefinite)
        max_messages : int, optional
            Maximum number of messages to process (None = unlimited)
        """
        self.consumer.subscribe([topic])
        self.logger.info(f"Subscribed to topic: {topic}")

        message_count = 0
        start_time = datetime.now()

        try:
            while True:
                # Check duration limit
                if duration_seconds:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    if elapsed > duration_seconds:
                        self.logger.info(f"Reached duration limit: {duration_seconds}s")
                        break

                # Check message limit
                if max_messages and message_count >= max_messages:
                    self.logger.info(f"Reached message limit: {max_messages}")
                    break

                # Poll for messages
                msg = self.consumer.poll(timeout=1.0)

                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        self.logger.debug("Reached end of partition")
                    else:
                        self.logger.error(f"Kafka error: {msg.error()}")
                    continue

                # Deserialize Avro message
                try:
                    bytes_reader = io.BytesIO(msg.value())
                    alert = fastavro.schemaless_reader(bytes_reader, schema=None)

                    # Process the alert
                    record = self.process_alert(alert)

                    if record:
                        self.alert_records.append(record)
                        message_count += 1

                        # Periodic saves (every 100 records)
                        if len(self.alert_records) >= 100:
                            self.save_to_csv()

                        # Periodic logging
                        if message_count % 1000 == 0:
                            self.logger.info(f"Processed {message_count} messages")

                except Exception as e:
                    self.logger.error(f"Error deserializing/processing message: {e}")
                    self.stats["messages_failed"] += 1

        except KeyboardInterrupt:
            self.logger.info("Consumer interrupted by user")

        finally:
            # Save any remaining records
            if self.alert_records:
                self.save_to_csv()

            # Save final state
            self._save_state()

            # Save daily summary
            self.save_daily_summary()

            # Log final statistics
            self.logger.info(f"Final statistics: {self.stats}")

            self.consumer.close()
            self.logger.info(f"Consumer closed. Processed {message_count} messages total")


def main():
    """
    Main entry point - configure and run the consumer.
    """
    # Kafka configuration
    kafka_config = {
        "bootstrap.servers": "localhost:9092",
        "group.id": "lsst-alert-consumer",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": True,
    }

    # Base directory - UPDATE THIS FOR YOUR SYSTEM
    base_dir = "/home/ubuntu/lsst-extendedness"

    # Topic name - UPDATE THIS
    topic = "lsst-extendedness-filtered"

    # Create and run consumer
    consumer = LSSTAlertConsumer(kafka_config, base_dir)

    # Consume alerts
    consumer.consume_alerts(
        topic=topic,
        duration_seconds=3600,  # Run for 1 hour
        max_messages=10000,  # Or max 10k messages
    )


if __name__ == "__main__":
    main()
