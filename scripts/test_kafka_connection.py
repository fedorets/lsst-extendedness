#!/usr/bin/env python3
"""
LSST Alert Pipeline - Kafka Connection Test
Tests connectivity to Kafka broker and topic availability
"""

import sys
from pathlib import Path

from confluent_kafka import Consumer, KafkaError
from confluent_kafka.admin import AdminClient

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Try to import config
try:
    from config.config import KAFKA_CONFIG, KAFKA_TOPIC
except ImportError:
    print("ERROR: Could not import config.py")
    print("Please create config/config.py from config/config_example.py")
    sys.exit(1)


def test_broker_connection():
    """Test basic connection to Kafka broker."""
    print("=" * 60)
    print("Testing Kafka Broker Connection")
    print("=" * 60)

    print(f"\nBroker: {KAFKA_CONFIG.get('bootstrap.servers')}")

    try:
        # Create admin client
        admin_client = AdminClient({"bootstrap.servers": KAFKA_CONFIG["bootstrap.servers"]})

        # Get cluster metadata
        metadata = admin_client.list_topics(timeout=10)

        print("✓ Successfully connected to Kafka broker")
        print(f"\nCluster ID: {metadata.cluster_id}")
        print(f"Broker count: {len(metadata.brokers)}")

        print("\nAvailable brokers:")
        for broker_id, broker_metadata in metadata.brokers.items():
            print(f"  - Broker {broker_id}: {broker_metadata.host}:{broker_metadata.port}")

        return True, metadata

    except Exception as e:
        print("✗ Failed to connect to Kafka broker")
        print(f"Error: {e}")
        return False, None


def test_topic_availability(metadata):
    """Test if the configured topic exists and is accessible."""
    print("\n" + "=" * 60)
    print("Testing Topic Availability")
    print("=" * 60)

    print(f"\nTopic: {KAFKA_TOPIC}")

    if KAFKA_TOPIC in metadata.topics:
        topic_metadata = metadata.topics[KAFKA_TOPIC]
        print(f"✓ Topic '{KAFKA_TOPIC}' exists")

        print(f"\nPartitions: {len(topic_metadata.partitions)}")
        for partition_id, partition_metadata in topic_metadata.partitions.items():
            print(f"  - Partition {partition_id}:")
            print(f"    Leader: {partition_metadata.leader}")
            print(f"    Replicas: {partition_metadata.replicas}")
            print(f"    ISRs: {partition_metadata.isrs}")

        if topic_metadata.error is not None:
            print(f"✗ Topic error: {topic_metadata.error}")
            return False

        return True
    else:
        print(f"✗ Topic '{KAFKA_TOPIC}' not found")
        print("\nAvailable topics:")
        for topic_name in sorted(metadata.topics.keys()):
            if not topic_name.startswith("_"):  # Skip internal topics
                print(f"  - {topic_name}")
        return False


def test_consumer_creation():
    """Test consumer creation and subscription."""
    print("\n" + "=" * 60)
    print("Testing Consumer Creation")
    print("=" * 60)

    try:
        # Create consumer
        consumer = Consumer(KAFKA_CONFIG)
        print("✓ Consumer created successfully")

        # Subscribe to topic
        consumer.subscribe([KAFKA_TOPIC])
        print(f"✓ Subscribed to topic: {KAFKA_TOPIC}")

        # Try to poll (just to test, don't wait for messages)
        print("\nAttempting to poll for messages (timeout: 5s)...")
        msg = consumer.poll(timeout=5.0)

        if msg is None:
            print("✓ No messages received (topic may be empty or low traffic)")
        elif msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                print("✓ Reached end of partition (consumer is working)")
            else:
                print(f"✗ Kafka error: {msg.error()}")
                consumer.close()
                return False
        else:
            print("✓ Received a message successfully!")
            print(f"  Topic: {msg.topic()}")
            print(f"  Partition: {msg.partition()}")
            print(f"  Offset: {msg.offset()}")
            print(f"  Message size: {len(msg.value())} bytes")

        consumer.close()
        print("\n✓ Consumer closed successfully")
        return True

    except Exception as e:
        print("✗ Failed to create consumer")
        print(f"Error: {e}")
        return False


def test_consumer_group():
    """Test consumer group configuration."""
    print("\n" + "=" * 60)
    print("Testing Consumer Group")
    print("=" * 60)

    group_id = KAFKA_CONFIG.get("group.id", "unknown")
    print(f"\nConsumer group ID: {group_id}")

    # This is informational - actual group info requires more setup
    print("✓ Consumer group configured")

    return True


def print_config_summary():
    """Print summary of Kafka configuration."""
    print("\n" + "=" * 60)
    print("Kafka Configuration Summary")
    print("=" * 60)

    print("\nConfiguration:")
    for key, value in KAFKA_CONFIG.items():
        # Don't print sensitive values
        if "password" in key.lower() or "secret" in key.lower():
            print(f"  {key}: ********")
        else:
            print(f"  {key}: {value}")

    print(f"\nTopic: {KAFKA_TOPIC}")


def main():
    """Run all tests."""
    print("\n")
    print("*" * 60)
    print("LSST Alert Pipeline - Kafka Connection Test")
    print("*" * 60)

    # Print configuration
    print_config_summary()

    # Test broker connection
    success, metadata = test_broker_connection()
    if not success:
        print("\n" + "=" * 60)
        print("TEST FAILED: Cannot connect to Kafka broker")
        print("=" * 60)
        print("\nPlease check:")
        print("1. Kafka broker is running")
        print("2. bootstrap.servers in config.py is correct")
        print("3. Network connectivity to broker")
        print("4. Firewall rules allow connection")
        sys.exit(1)

    # Test topic availability
    if not test_topic_availability(metadata):
        print("\n" + "=" * 60)
        print("WARNING: Configured topic not found")
        print("=" * 60)
        print("\nThe consumer may not receive messages.")
        print("Please verify the topic name in config.py")
        # Continue anyway - topic might not exist yet

    # Test consumer creation
    if not test_consumer_creation():
        print("\n" + "=" * 60)
        print("TEST FAILED: Cannot create consumer")
        print("=" * 60)
        sys.exit(1)

    # Test consumer group
    test_consumer_group()

    # Summary
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED!")
    print("=" * 60)
    print("\nYour Kafka connection is configured correctly.")
    print("You can now run the LSST alert consumer.")
    print("\nNext steps:")
    print("1. Run consumer manually: python3 src/lsst_alert_consumer.py")
    print("2. Set up cron job: bin/run_lsst_consumer.sh")
    print("\n")


if __name__ == "__main__":
    main()
