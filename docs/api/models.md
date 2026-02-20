# Models API Reference

Data models for the LSST Extendedness Pipeline using Pydantic.

## AlertRecord

The core data model for LSST alerts.

::: lsst_extendedness.models.AlertRecord
    options:
      show_root_heading: true
      members:
        - alert_id
        - dia_source_id
        - ra
        - dec
        - mjd
        - extendedness_median
        - has_ss_source
        - from_avro
        - to_db_dict

## ProcessingResult

Results from post-processors.

::: lsst_extendedness.models.ProcessingResult
    options:
      show_root_heading: true

## IngestionRun

Metadata about an ingestion run.

::: lsst_extendedness.models.IngestionRun
    options:
      show_root_heading: true

## Usage Examples

### Creating an AlertRecord

```python
from lsst_extendedness.models import AlertRecord

# From keyword arguments
alert = AlertRecord(
    alert_id=123456,
    dia_source_id=987654,
    ra=180.0,
    dec=45.0,
    mjd=60100.5,
    extendedness_median=0.42,
)

# From AVRO record
avro_data = {...}  # Deserialized from Kafka
alert = AlertRecord.from_avro(avro_data)

# To dictionary for database
db_dict = alert.to_db_dict()
```

### Validation

Pydantic validates all fields automatically:

```python
from pydantic import ValidationError

try:
    alert = AlertRecord(
        alert_id=123456,
        ra=400.0,  # Invalid: must be 0-360
        dec=45.0,
        mjd=60100.5,
    )
except ValidationError as e:
    print(e)
    # ra: Input should be less than or equal to 360
```
