"""
Kafka helper utilities for LSST alert consumer
"""

import logging

from confluent_kafka import Consumer
from confluent_kafka.admin import AdminClient

logger = logging.getLogger(__name__)


def create_consumer(config):
    """
    Create and configure a Kafka consumer.

    Parameters:
    -----------
    config : dict
        Kafka consumer configuration

    Returns:
    --------
    Consumer
        Configured Kafka consumer
    """
    try:
        consumer = Consumer(config)
        logger.info("Kafka consumer created successfully")
        return consumer
    except Exception as e:
        logger.error(f"Failed to create Kafka consumer: {e}")
        raise


def test_connection(config):
    """
    Test connection to Kafka broker.

    Parameters:
    -----------
    config : dict
        Kafka configuration

    Returns:
    --------
    bool
        True if connection successful
    """
    try:
        admin_client = AdminClient({"bootstrap.servers": config["bootstrap.servers"]})

        metadata = admin_client.list_topics(timeout=10)
        logger.info(f"Connected to Kafka cluster: {metadata.cluster_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to connect to Kafka: {e}")
        return False


def list_topics(config):
    """
    List available Kafka topics.

    Parameters:
    -----------
    config : dict
        Kafka configuration

    Returns:
    --------
    list
        List of topic names
    """
    try:
        admin_client = AdminClient({"bootstrap.servers": config["bootstrap.servers"]})

        metadata = admin_client.list_topics(timeout=10)
        topics = [
            topic for topic in metadata.topics if not topic.startswith("_")
        ]  # Exclude internal topics

        return sorted(topics)
    except Exception as e:
        logger.error(f"Failed to list topics: {e}")
        return []


def get_topic_info(config, topic_name):
    """
    Get information about a specific topic.

    Parameters:
    -----------
    config : dict
        Kafka configuration
    topic_name : str
        Name of the topic

    Returns:
    --------
    dict
        Topic information (partitions, replicas, etc.)
    """
    try:
        admin_client = AdminClient({"bootstrap.servers": config["bootstrap.servers"]})

        metadata = admin_client.list_topics(timeout=10)

        if topic_name not in metadata.topics:
            logger.warning(f"Topic '{topic_name}' not found")
            return None

        topic_metadata = metadata.topics[topic_name]

        info = {
            "name": topic_name,
            "partitions": len(topic_metadata.partitions),
            "partition_details": [],
        }

        for partition_id, partition_metadata in topic_metadata.partitions.items():
            info["partition_details"].append(
                {
                    "id": partition_id,
                    "leader": partition_metadata.leader,
                    "replicas": partition_metadata.replicas,
                    "isrs": partition_metadata.isrs,
                }
            )

        return info
    except Exception as e:
        logger.error(f"Failed to get topic info: {e}")
        return None


def get_consumer_lag(consumer, topic, partitions=None):
    """
    Get consumer lag for a topic.

    Parameters:
    -----------
    consumer : Consumer
        Kafka consumer
    topic : str
        Topic name
    partitions : list, optional
        List of partition IDs to check (default: all)

    Returns:
    --------
    dict
        Consumer lag per partition
    """
    try:
        # Get current assignment
        assignment = consumer.assignment()

        if not assignment:
            logger.warning("Consumer has no partition assignment")
            return {}

        lag_info = {}

        for tp in assignment:
            if topic and tp.topic != topic:
                continue

            # Get committed offset
            committed = consumer.committed([tp])[0]
            committed_offset = committed.offset if committed else -1

            # Get high water mark
            _low, high = consumer.get_watermark_offsets(tp, timeout=5.0)

            lag = high - committed_offset if committed_offset >= 0 else high

            lag_info[tp.partition] = {
                "committed_offset": committed_offset,
                "high_water_mark": high,
                "lag": lag,
            }

        return lag_info
    except Exception as e:
        logger.error(f"Failed to get consumer lag: {e}")
        return {}


def seek_to_beginning(consumer, topic):
    """
    Seek consumer to beginning of topic.

    Parameters:
    -----------
    consumer : Consumer
        Kafka consumer
    topic : str
        Topic name
    """
    try:
        from confluent_kafka import TopicPartition

        # Get topic partitions
        metadata = consumer.list_topics(topic, timeout=10)

        if topic not in metadata.topics:
            logger.error(f"Topic '{topic}' not found")
            return

        partitions = metadata.topics[topic].partitions

        # Create TopicPartition objects for seeking
        tps = [TopicPartition(topic, partition_id, 0) for partition_id in partitions]

        # Seek to beginning
        consumer.seek(tps[0])  # Seek first partition as example

        logger.info(f"Seeking to beginning of topic '{topic}'")
    except Exception as e:
        logger.error(f"Failed to seek to beginning: {e}")


def get_message_count_estimate(config, topic):
    """
    Get rough estimate of message count in topic.

    Parameters:
    -----------
    config : dict
        Kafka configuration
    topic : str
        Topic name

    Returns:
    --------
    int
        Estimated message count
    """
    try:
        from confluent_kafka import TopicPartition

        consumer = Consumer({**config, "group.id": "temp-counter", "enable.auto.commit": False})

        # Get topic metadata
        metadata = consumer.list_topics(topic, timeout=10)

        if topic not in metadata.topics:
            logger.error(f"Topic '{topic}' not found")
            consumer.close()
            return 0

        partitions = metadata.topics[topic].partitions

        total_messages = 0

        for partition_id in partitions:
            tp = TopicPartition(topic, partition_id)
            low, high = consumer.get_watermark_offsets(tp, timeout=5.0)
            total_messages += high - low

        consumer.close()

        return total_messages
    except Exception as e:
        logger.error(f"Failed to estimate message count: {e}")
        return 0
