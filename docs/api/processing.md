# Processing API Reference

Post-processing framework for custom alert analysis.

## BaseProcessor

Base class for all post-processors:

::: lsst_extendedness.processing.BaseProcessor
    options:
      show_root_heading: true
      members:
        - name
        - version
        - process
        - pre_filter_sql

## ProcessingRunner

Orchestrates processor execution:

::: lsst_extendedness.processing.ProcessingRunner
    options:
      show_root_heading: true
      members:
        - __init__
        - run_all
        - run_processor

## Registry

Auto-discovery and registration:

::: lsst_extendedness.processing.registry
    options:
      show_root_heading: true
      members:
        - register_processor
        - get_processor
        - list_processors

## Creating a Custom Processor

```python
from lsst_extendedness.processing import BaseProcessor, register_processor
from lsst_extendedness.models import ProcessingResult
import pandas as pd

@register_processor("minimoon_detector")
class MiniMoonDetector(BaseProcessor):
    """Detect minimoon candidates from accumulated alerts."""

    name = "minimoon_detector"
    version = "1.0.0"

    def __init__(self, min_observations: int = 3):
        self.min_observations = min_observations

    @property
    def pre_filter_sql(self) -> str:
        """SQL to pre-filter data before processing."""
        return """
            SELECT * FROM alerts_raw
            WHERE has_ss_source = 1
            AND extendedness_median BETWEEN 0.3 AND 0.7
            AND mjd > ?
        """

    def process(self, df: pd.DataFrame) -> ProcessingResult:
        """
        Analyze alerts for minimoon candidates.

        Args:
            df: Pre-filtered DataFrame of alerts

        Returns:
            ProcessingResult with detected candidates
        """
        candidates = []

        # Group by SSObject
        for ss_id, group in df.groupby("ss_object_id"):
            if len(group) >= self.min_observations:
                # Check for arc consistency
                if self._check_arc(group):
                    candidates.append({
                        "ss_object_id": ss_id,
                        "num_observations": len(group),
                        "mean_extendedness": group["extendedness_median"].mean(),
                        "first_seen": group["mjd"].min(),
                        "last_seen": group["mjd"].max(),
                    })

        return ProcessingResult(
            processor_name=self.name,
            processor_version=self.version,
            records=candidates,
            summary=f"Found {len(candidates)} minimoon candidates",
        )

    def _check_arc(self, group: pd.DataFrame) -> bool:
        """Check if observations form consistent arc."""
        # Implementation here
        return True
```

## Plugin Directory

Place custom processors in `plugins/` directory for auto-discovery:

```
plugins/
├── __init__.py
├── minimoon_detector.py
└── transient_classifier.py
```

They will be automatically loaded on startup.

## Running Processors

### CLI

```bash
# Run all processors
lsst-extendedness process --window 15

# Run specific processor
lsst-extendedness process --processor minimoon_detector --window 30
```

### Python

```python
from lsst_extendedness.processing import ProcessingRunner
from lsst_extendedness.storage import SQLiteStorage

storage = SQLiteStorage("data/alerts.db")
runner = ProcessingRunner(storage)

# Run all
results = runner.run_all(window_days=15)

# Run specific
result = runner.run_processor("minimoon_detector", window_days=30)
print(result.summary)
```
