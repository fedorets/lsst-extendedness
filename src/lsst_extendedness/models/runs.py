"""
Run tracking models for the LSST Extendedness Pipeline.

This module defines models for tracking ingestion and processing runs:
- IngestionRun: Metadata about an ingestion run

Example:
    >>> from lsst_extendedness.models import IngestionRun
    >>>
    >>> run = IngestionRun(source_name="kafka")
    >>> run.alerts_ingested += 100
    >>> run.complete()
    >>> print(f"Ingested {run.alerts_ingested} alerts in {run.duration_seconds}s")
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field


class RunStatus(StrEnum):
    """Status of an ingestion or processing run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IngestionRun(BaseModel):
    """Metadata about an ingestion run.

    Tracks statistics and status for a single ingestion execution,
    providing an audit trail for data provenance.

    Attributes:
        id: Unique run identifier (set by database)
        source_name: Name of the source (kafka, file, mock, etc.)
        source_config: Configuration used for the source
        started_at: When the run started
        completed_at: When the run completed (None if still running)
        status: Current run status
        alerts_ingested: Number of alerts successfully ingested
        alerts_failed: Number of alerts that failed processing
        new_sources: Number of newly discovered DIASources
        reassociations_detected: Number of SSObject reassociations detected
        cutouts_saved: Number of cutout files saved
        error_message: Error message if run failed
        metadata: Additional run metadata

    Example:
        >>> run = IngestionRun(source_name="kafka")
        >>> run.status = RunStatus.RUNNING
        >>> # ... process alerts ...
        >>> run.alerts_ingested = 1000
        >>> run.complete()
    """

    model_config = ConfigDict(extra="ignore")

    id: int | None = Field(default=None, description="Unique run identifier (database-assigned)")
    source_name: str = Field(default="unknown", description="Source name (kafka, file, mock)")
    source_config: dict[str, Any] = Field(
        default_factory=dict, description="Source configuration used"
    )
    started_at: datetime = Field(default_factory=datetime.utcnow, description="Run start time")
    completed_at: datetime | None = Field(default=None, description="Run completion time")
    status: RunStatus = Field(default=RunStatus.RUNNING, description="Current run status")

    # Statistics
    alerts_ingested: int = Field(default=0, ge=0, description="Alerts successfully ingested")
    alerts_failed: int = Field(default=0, ge=0, description="Alerts that failed processing")
    new_sources: int = Field(default=0, ge=0, description="New DIASources discovered")
    reassociations_detected: int = Field(default=0, ge=0, description="Reassociations detected")
    cutouts_saved: int = Field(default=0, ge=0, description="Cutout files saved")

    # Error tracking
    error_message: str | None = Field(default=None, description="Error message if failed")

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional run metadata")

    @computed_field  # type: ignore[misc]
    @property
    def duration_seconds(self) -> float | None:
        """Calculate run duration in seconds.

        Returns:
            Duration in seconds, or None if run is not completed
        """
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    @computed_field  # type: ignore[misc]
    @property
    def processing_rate(self) -> float | None:
        """Calculate alerts processed per second.

        Returns:
            Rate in alerts/second, or None if not applicable
        """
        duration = self.duration_seconds
        if duration is None or duration == 0:
            return None
        return self.alerts_ingested / duration

    @computed_field  # type: ignore[misc]
    @property
    def success_rate(self) -> float:
        """Calculate success rate as a percentage.

        Returns:
            Success rate (0-100), or 100 if no alerts processed
        """
        total = self.alerts_ingested + self.alerts_failed
        if total == 0:
            return 100.0
        return (self.alerts_ingested / total) * 100

    @computed_field  # type: ignore[misc]
    @property
    def is_running(self) -> bool:
        """Check if the run is still in progress."""
        return self.status == RunStatus.RUNNING

    @computed_field  # type: ignore[misc]
    @property
    def is_complete(self) -> bool:
        """Check if the run completed successfully."""
        return self.status == RunStatus.COMPLETED

    def complete(self, error: str | None = None) -> None:
        """Mark the run as complete.

        Args:
            error: Optional error message if the run failed

        Example:
            >>> run.complete()  # Success
            >>> run.complete(error="Connection lost")  # Failure
        """
        self.completed_at = datetime.utcnow()
        if error:
            self.status = RunStatus.FAILED
            self.error_message = error
        else:
            self.status = RunStatus.COMPLETED

    def fail(self, error: str) -> None:
        """Mark the run as failed with an error message.

        Args:
            error: Error message describing the failure
        """
        self.complete(error=error)

    def cancel(self) -> None:
        """Mark the run as cancelled."""
        self.completed_at = datetime.utcnow()
        self.status = RunStatus.CANCELLED

    def to_db_dict(self) -> dict[str, Any]:
        """Convert to dictionary for SQLite insertion."""
        import json

        data = self.model_dump(mode="json", exclude={"id"})

        # Convert enum to string
        data["status"] = self.status.value

        # Serialize nested dicts
        data["source_config"] = json.dumps(data["source_config"])
        data["metadata"] = json.dumps(data["metadata"])

        return data

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> IngestionRun:
        """Create IngestionRun from a database row."""
        import json

        data = dict(row)

        # Parse JSON fields
        if isinstance(data.get("source_config"), str):
            data["source_config"] = json.loads(data["source_config"])
        if isinstance(data.get("metadata"), str):
            data["metadata"] = json.loads(data["metadata"])

        # Convert status string to enum
        if isinstance(data.get("status"), str):
            data["status"] = RunStatus(data["status"])

        return cls(**data)

    def summary_dict(self) -> dict[str, Any]:
        """Get a summary dictionary for logging/reporting.

        Returns:
            Dictionary with key run statistics
        """
        return {
            "id": self.id,
            "source": self.source_name,
            "status": self.status.value,
            "alerts_ingested": self.alerts_ingested,
            "alerts_failed": self.alerts_failed,
            "new_sources": self.new_sources,
            "reassociations": self.reassociations_detected,
            "duration_seconds": self.duration_seconds,
            "processing_rate": self.processing_rate,
            "success_rate": round(self.success_rate, 2),
        }
