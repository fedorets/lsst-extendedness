# LSST Alert Pipeline

A two-part pipeline for processing LSST alerts through the ANTARES broker.

## Architecture

```
LSST → ANTARES Broker → [Part 1: Filter] → Kafka Stream → [Part 2: Consumer] → CSV + Cutouts
```

## Part 1: ANTARES Level 2 Filter

The filter (`antares_extendedness_filter.py`) runs on the ANTARES broker and filters alerts based on:
1. DIASource extendedness values (Median, Min, Max)
2. Presence of SSSource schema attachment (solar system object association)

### Configuration

Edit the threshold values in `antares_extendedness_filter.py`:

```python
# Extendedness thresholds
EXTENDEDNESS_MEDIAN_MIN = 0.0  # Adjust for your science case
EXTENDEDNESS_MEDIAN_MAX = 1.0
EXTENDEDNESS_MIN_THRESHOLD = 0.0
EXTENDEDNESS_MAX_THRESHOLD = 1.0

# SSSource requirement
REQUIRE_SSSOURCE = True  # True = require SSSource, False = exclude SSSource
```

**SSSource Logic:**
- `REQUIRE_SSSOURCE = True`: Only pass alerts WITH SSSource schema attached (e.g., known asteroids)
- `REQUIRE_SSSOURCE = False`: Only pass alerts WITHOUT SSSource schema (e.g., extragalactic sources)

The filter checks for SSSource in multiple ways:
- Alert properties (`ssObjectId`, `ssObject` fields)
- Raw alert packet (`ssObject` field)
- ANTARES locus tags (solar system object classifications)

### Deployment to ANTARES

1. **Via ANTARES DevKit** (recommended for development):
   - Access the ANTARES DevKit at https://antares.noirlab.edu
   - Upload `antares_extendedness_filter.py` as a new filter
   - Test with historical data

2. **Via ANTARES API** (for production):
   - Contact ANTARES team for filter deployment
   - Provide the filter code and metadata
   - Configure output Kafka topic

### Filter Output

The filter outputs passing alerts to a Kafka topic (e.g., `lsst-extendedness-filtered`).

## Part 2: Kafka Consumer

The consumer (`lsst_alert_consumer.py`) runs on your VM and processes the filtered alert stream.

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# For Kafka client on Ubuntu/Debian
sudo apt-get install librdkafka-dev

# Install librdkafka for other systems:
# macOS: brew install librdkafka
# CentOS/RHEL: sudo yum install librdkafka-devel
```

### Configuration

Edit the Kafka configuration in `lsst_alert_consumer.py`:

```python
kafka_config = {
    'bootstrap.servers': 'your-kafka-broker:9092',
    'group.id': 'lsst-alert-consumer',
    'auto.offset.reset': 'earliest',
}

topic = 'lsst-extendedness-filtered'  # Your filtered stream topic
output_dir = '/path/to/output'
```

### Manual Run

```bash
python3 lsst_alert_consumer.py
```

### Cron Job Setup

1. Make the script executable:
   ```bash
   chmod +x run_lsst_consumer.sh
   ```

2. Edit crontab:
   ```bash
   crontab -e
   ```

3. Add daily job (e.g., 2 AM):
   ```
   0 2 * * * /path/to/run_lsst_consumer.sh >> /var/log/lsst_consumer.log 2>&1
   ```

4. Other scheduling examples:
   ```
   # Every 6 hours
   0 */6 * * * /path/to/run_lsst_consumer.sh >> /var/log/lsst_consumer.log 2>&1

   # Twice daily (2 AM and 2 PM)
   0 2,14 * * * /path/to/run_lsst_consumer.sh >> /var/log/lsst_consumer.log 2>&1
   ```

## Output Structure

```
lsst_alerts/
├── data/
│   ├── lsst_alerts_20260210.csv
│   ├── lsst_alerts_20260211.csv
│   └── ...
└── cutouts/
    ├── 1234567_science_20260210_020315.fits
    ├── 1234567_template_20260210_020315.fits
    ├── 1234567_difference_20260210_020315.fits
    └── ...
```

### CSV Format

The CSV files contain:

| Column | Description |
|--------|-------------|
| alertId | Unique alert identifier |
| diaSourceId | DIASource identifier |
| diaObjectId | DIAObject identifier |
| ra | Right ascension (degrees) |
| dec | Declination (degrees) |
| mjd | Modified Julian Date |
| filterName | Photometric filter |
| psFlux | Point source flux |
| psFluxErr | Flux error |
| extendednessMedian | Median extendedness |
| extendednessMin | Minimum extendedness |
| extendednessMax | Maximum extendedness |
| science_cutout_path | Path to science image cutout |
| template_cutout_path | Path to template image cutout |
| difference_cutout_path | Path to difference image cutout |
| timestamp | Processing timestamp |

## Monitoring

### Check Logs

```bash
# Cron job logs
tail -f /var/log/lsst_consumer.log

# Check last run
grep "LSST Alert Consumer" /var/log/lsst_consumer.log | tail -5
```

### Verify Output

```bash
# Count today's alerts
wc -l lsst_alerts/data/lsst_alerts_$(date +%Y%m%d).csv

# Check cutout storage
du -sh lsst_alerts/cutouts/
ls -lh lsst_alerts/cutouts/ | head -10
```

## Data Management

The cron script automatically cleans up old data (>30 days). Adjust retention in `run_lsst_consumer.sh`:

```bash
# Keep last 60 days instead
find ./lsst_alerts/data -name "lsst_alerts_*.csv" -mtime +60 -delete
find ./lsst_alerts/cutouts -name "*.fits" -mtime +60 -delete
```

## Troubleshooting

### Kafka Connection Issues

1. Check Kafka broker is accessible:
   ```bash
   telnet your-kafka-broker 9092
   ```

2. Test with kafka-console-consumer:
   ```bash
   kafka-console-consumer --bootstrap-server your-kafka-broker:9092 \
                          --topic lsst-extendedness-filtered \
                          --from-beginning
   ```

### Schema Registry Issues

If using Confluent Wire Format, ensure schema registry is accessible:

```python
# Add to kafka_config
kafka_config['schema.registry.url'] = 'http://your-schema-registry:8081'
```

### Missing Dependencies

```bash
# If fastavro fails
pip install --upgrade fastavro

# If confluent-kafka fails
pip install --no-binary :all: confluent-kafka
```

### ANTARES Filter Issues

- Check ANTARES DevKit logs for filter errors
- Verify DIASource field names match schema: https://sdm-schemas.lsst.io/apdb.html
- Test filter with sample alerts before production deployment

## Advanced Configuration

### Custom Alert Processing

Extend `process_alert()` method to extract additional fields:

```python
def process_alert(self, alert):
    # Add more DIASource fields
    record['snr'] = dia_source.get('snr')
    record['chi'] = dia_source.get('chi')
    # Add previous detections
    record['prv_candidates'] = len(alert.get('prvDiaSources', []))
    return record
```

### Parallel Processing

For high-throughput scenarios:

```python
from concurrent.futures import ThreadPoolExecutor

def consume_alerts(self, topic, workers=4):
    with ThreadPoolExecutor(max_workers=workers) as executor:
        # Process alerts in parallel
        futures = []
        # ... implementation
```

## Resources

- ANTARES Documentation: https://antares.noirlab.edu
- LSST Alert Schema: https://github.com/lsst/alert_packet
- APDB Schema: https://sdm-schemas.lsst.io/apdb.html
- Kafka Consumer: https://docs.confluent.io/kafka-clients/python/current/overview.html

## Support

For issues with:
- ANTARES broker: Contact ANTARES team via https://antares.noirlab.edu
- LSST alerts: Rubin Observatory Community Forum at https://community.lsst.org
- This pipeline: Check logs and documentation above

## License

This code is provided as-is for astronomical research purposes.
