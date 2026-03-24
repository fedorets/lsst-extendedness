"""
FITS Cutout Processor.

Extracts and saves FITS cutout images from alert packets.
"""

from __future__ import annotations

import gzip
import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import structlog

if TYPE_CHECKING:
    from ..models.alerts import AlertRecord

logger = structlog.get_logger(__name__)


@dataclass
class CutoutPaths:
    """Paths to extracted cutout files."""

    science: Path | None = None
    template: Path | None = None
    difference: Path | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Convert to dictionary for storage."""
        return {
            "science_cutout_path": str(self.science) if self.science else None,
            "template_cutout_path": str(self.template) if self.template else None,
            "difference_cutout_path": str(self.difference) if self.difference else None,
        }


@dataclass
class CutoutConfig:
    """Configuration for cutout processing."""

    output_dir: Path = Path("data/cutouts")
    save_science: bool = True
    save_template: bool = True
    save_difference: bool = True
    compress: bool = False
    organize_by_date: bool = True
    organize_by_object: bool = False


class CutoutProcessor:
    """Extracts and saves FITS cutouts from alert packets.

    Usage:
        processor = CutoutProcessor(config)

        # Process single alert
        paths = processor.process_alert(alert, avro_record)

        # Batch process
        for alert, avro in alerts_with_avro:
            paths = processor.process_alert(alert, avro)
            # paths.science, paths.template, paths.difference
    """

    def __init__(self, config: CutoutConfig | None = None):
        """Initialize cutout processor.

        Args:
            config: Cutout configuration
        """
        self.config = config or CutoutConfig()
        self._ensure_output_dir()

    def _ensure_output_dir(self) -> None:
        """Create output directory if needed."""
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_output_path(
        self,
        alert: AlertRecord,
        cutout_type: str,
    ) -> Path:
        """Generate output path for a cutout.

        Args:
            alert: AlertRecord
            cutout_type: 'science', 'template', or 'difference'

        Returns:
            Output file path
        """
        base_dir = self.config.output_dir

        # Organize by date
        if self.config.organize_by_date:
            from ..utils.time import mjd_to_datetime

            dt = mjd_to_datetime(alert.mjd)
            date_str = dt.strftime("%Y/%m/%d")
            base_dir = base_dir / date_str

        # Organize by object
        if self.config.organize_by_object and alert.dia_object_id:
            base_dir = base_dir / f"obj_{alert.dia_object_id}"

        base_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{alert.dia_source_id}_{cutout_type}_{timestamp}.fits"

        if self.config.compress:
            filename += ".gz"

        return base_dir / filename

    def _extract_cutout(
        self,
        data: bytes | None,
        output_path: Path,
    ) -> bool:
        """Extract and save a single cutout.

        Args:
            data: Raw cutout bytes (may be gzipped)
            output_path: Path to save to

        Returns:
            True if successful
        """
        if not data:
            return False

        try:
            # Check if gzipped
            if data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)

            # Validate FITS header
            if not data.startswith(b"SIMPLE"):
                logger.warning(
                    "invalid_fits_header",
                    path=str(output_path),
                )
                return False

            # Compress if configured
            if self.config.compress:
                data = gzip.compress(data)

            # Write file
            output_path.write_bytes(data)

            logger.debug("cutout_saved", path=str(output_path), size=len(data))
            return True

        except Exception as e:
            logger.error(
                "cutout_extraction_failed",
                path=str(output_path),
                error=str(e),
            )
            return False

    def process_alert(
        self,
        alert: AlertRecord,
        avro_record: dict[str, Any],
    ) -> CutoutPaths:
        """Extract cutouts from an alert.

        Args:
            alert: AlertRecord
            avro_record: Raw AVRO record with cutout bytes

        Returns:
            CutoutPaths with saved file locations
        """
        paths = CutoutPaths()

        # Extract science cutout
        if self.config.save_science:
            science_data = avro_record.get("cutoutScience")
            if science_data:
                path = self._get_output_path(alert, "science")
                if self._extract_cutout(science_data, path):
                    paths.science = path

        # Extract template cutout
        if self.config.save_template:
            template_data = avro_record.get("cutoutTemplate")
            if template_data:
                path = self._get_output_path(alert, "template")
                if self._extract_cutout(template_data, path):
                    paths.template = path

        # Extract difference cutout
        if self.config.save_difference:
            difference_data = avro_record.get("cutoutDifference")
            if difference_data:
                path = self._get_output_path(alert, "difference")
                if self._extract_cutout(difference_data, path):
                    paths.difference = path

        return paths

    def process_batch(
        self,
        alerts_with_avro: list[tuple[AlertRecord, dict[str, Any]]],
    ) -> list[CutoutPaths]:
        """Process a batch of alerts.

        Args:
            alerts_with_avro: List of (AlertRecord, avro_record) tuples

        Returns:
            List of CutoutPaths
        """
        results = []
        for alert, avro in alerts_with_avro:
            paths = self.process_alert(alert, avro)
            results.append(paths)
        return results

    def cleanup_old_cutouts(self, days: int = 30) -> int:
        """Remove cutouts older than specified days.

        Args:
            days: Age threshold in days

        Returns:
            Number of files removed
        """
        import time

        threshold = time.time() - (days * 86400)
        removed = 0

        for fits_file in self.config.output_dir.rglob("*.fits*"):
            if fits_file.stat().st_mtime < threshold:
                fits_file.unlink()
                removed += 1

        # Clean up empty directories
        for dir_path in sorted(
            self.config.output_dir.rglob("*"),
            key=lambda p: len(p.parts),
            reverse=True,
        ):
            if dir_path.is_dir() and not any(dir_path.iterdir()):
                dir_path.rmdir()

        logger.info("cutouts_cleaned", removed=removed, days=days)
        return removed

    def get_stats(self) -> dict[str, Any]:
        """Get cutout storage statistics.

        Returns:
            Dict with storage stats
        """
        total_files = 0
        total_size = 0
        by_type = {"science": 0, "template": 0, "difference": 0}

        for fits_file in self.config.output_dir.rglob("*.fits*"):
            total_files += 1
            total_size += fits_file.stat().st_size

            name = fits_file.name
            if "_science_" in name:
                by_type["science"] += 1
            elif "_template_" in name:
                by_type["template"] += 1
            elif "_difference_" in name:
                by_type["difference"] += 1

        return {
            "total_files": total_files,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "by_type": by_type,
            "output_dir": str(self.config.output_dir),
        }


def extract_cutout_stamps(
    avro_record: dict[str, Any],
) -> dict[str, bytes | None]:
    """Extract raw cutout stamps from AVRO record.

    Useful for in-memory processing without saving to disk.

    Args:
        avro_record: Raw AVRO record

    Returns:
        Dict with decompressed cutout bytes
    """
    stamps = {}

    for key in ("cutoutScience", "cutoutTemplate", "cutoutDifference"):
        data = avro_record.get(key)
        if data:
            # Decompress if gzipped
            if data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            stamps[key] = data
        else:
            stamps[key] = None

    return stamps


def load_cutout_as_array(
    path: Path | str,
) -> np.ndarray[tuple[int, ...], np.dtype[np.floating[Any]]]:
    """Load a FITS cutout as numpy array.

    Args:
        path: Path to FITS file

    Returns:
        Image data as numpy array
    """
    try:
        from astropy.io import fits
    except ImportError as e:
        raise ImportError("astropy required for FITS loading. Install with: pdm add astropy") from e

    path = Path(path)

    # Handle gzipped files
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as f:
            data = f.read()
        with fits.open(io.BytesIO(data)) as hdul:
            return cast("np.ndarray[tuple[Any, ...], np.dtype[Any]]", hdul[0].data)
    else:
        with fits.open(path) as hdul:
            return cast("np.ndarray[tuple[Any, ...], np.dtype[Any]]", hdul[0].data)
