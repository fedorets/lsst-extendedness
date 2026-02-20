# Post-Processing

Run custom analysis on accumulated alerts.

## Overview

The processing framework allows you to:

- Run analysis on time windows of data
- Pre-filter data with SQL for efficiency
- Store results in the database
- Create custom processor plugins

## Running Processors

### CLI

```bash
# Run all processors (15-day window)
lsst-extendedness process --window 15

# Run specific processor
lsst-extendedness process --processor example --window 30

# Dry run (show what would be processed)
lsst-extendedness process --dry-run
```

### Python

```python
from lsst_extendedness.processing import ProcessingRunner

runner = ProcessingRunner(storage)

# Run all
results = runner.run_all(window_days=15)
for result in results:
    print(f"{result.processor_name}: {result.summary}")

# Run specific
result = runner.run_processor("example", window_days=30)
```

## Built-in Processors

### Example Processor

A template showing the processor structure:

```python
from lsst_extendedness.processing.builtin import ExampleProcessor

processor = ExampleProcessor()
result = processor.process(df)
```

## Creating Custom Processors

### Basic Structure

```python
from lsst_extendedness.processing import BaseProcessor, register_processor
from lsst_extendedness.models import ProcessingResult
import pandas as pd

@register_processor("my_processor")
class MyProcessor(BaseProcessor):
    name = "my_processor"
    version = "1.0.0"

    def process(self, df: pd.DataFrame) -> ProcessingResult:
        # Your analysis here
        records = []

        for _, row in df.iterrows():
            if self._is_interesting(row):
                records.append({
                    "alert_id": row["alert_id"],
                    "score": self._compute_score(row),
                })

        return ProcessingResult(
            processor_name=self.name,
            processor_version=self.version,
            records=records,
            summary=f"Found {len(records)} interesting alerts",
        )
```

### Pre-filtering

Add SQL pre-filtering for efficiency:

```python
@register_processor("sso_analyzer")
class SSOAnalyzer(BaseProcessor):
    name = "sso_analyzer"
    version = "1.0.0"

    @property
    def pre_filter_sql(self) -> str:
        return """
            SELECT * FROM alerts_raw
            WHERE has_ss_source = 1
            AND mjd > ?
            ORDER BY ss_object_id, mjd
        """

    def process(self, df: pd.DataFrame) -> ProcessingResult:
        # df is already filtered to SSO alerts
        ...
```

### Plugin Directory

Place processors in `plugins/` for auto-discovery:

```
plugins/
├── __init__.py
├── minimoon_detector.py
└── transient_classifier.py
```

## Viewing Results

```python
# Query processing results
results = storage.query("""
    SELECT * FROM processing_results
    WHERE processor_name = 'my_processor'
    ORDER BY processed_at DESC
""")

# Get latest result
latest = storage.query("""
    SELECT result_data FROM processing_results
    WHERE processor_name = 'my_processor'
    ORDER BY processed_at DESC
    LIMIT 1
""")
```

## Scheduling

Processors run automatically via systemd timer:

```bash
# Check timer status
systemctl status lsst-process.timer

# View logs
journalctl -u lsst-process -f
```
