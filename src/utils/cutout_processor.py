"""
Cutout processing utilities for LSST alerts
"""

import io
import logging
from pathlib import Path

import numpy as np
from astropy.io import fits

logger = logging.getLogger(__name__)


class CutoutProcessor:
    """Handles extraction and processing of FITS cutouts from alerts."""

    def __init__(self, output_dir):
        """
        Initialize cutout processor.

        Parameters:
        -----------
        output_dir : str or Path
            Directory to save cutouts
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def extract_cutout(self, cutout_data, output_path):
        """
        Extract cutout from alert and save to file.

        Parameters:
        -----------
        cutout_data : bytes
            Binary FITS cutout data
        output_path : str or Path
            Path to save cutout

        Returns:
        --------
        bool
            True if successful
        """
        try:
            # Parse FITS data
            fits_data = fits.open(io.BytesIO(cutout_data))

            # Ensure output directory exists
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Save FITS file
            fits_data.writeto(output_path, overwrite=True)
            fits_data.close()

            logger.debug(f"Saved cutout: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Error extracting cutout: {e}")
            return False

    def get_cutout_statistics(self, cutout_path):
        """
        Get statistics from a cutout FITS file.

        Parameters:
        -----------
        cutout_path : str or Path
            Path to FITS cutout

        Returns:
        --------
        dict
            Statistics about the cutout
        """
        try:
            with fits.open(cutout_path) as hdul:
                data = hdul[0].data

                if data is None:
                    return None

                stats = {
                    "shape": data.shape,
                    "dtype": str(data.dtype),
                    "min": float(np.min(data)),
                    "max": float(np.max(data)),
                    "mean": float(np.mean(data)),
                    "median": float(np.median(data)),
                    "std": float(np.std(data)),
                    "has_nan": bool(np.any(np.isnan(data))),
                }

                return stats

        except Exception as e:
            logger.error(f"Error getting cutout statistics: {e}")
            return None

    def validate_cutout(self, cutout_path):
        """
        Validate a cutout FITS file.

        Parameters:
        -----------
        cutout_path : str or Path
            Path to FITS cutout

        Returns:
        --------
        tuple
            (is_valid, error_message)
        """
        try:
            cutout_path = Path(cutout_path)

            # Check file exists
            if not cutout_path.exists():
                return False, "File does not exist"

            # Check file size
            if cutout_path.stat().st_size == 0:
                return False, "File is empty"

            # Try to open FITS file
            with fits.open(cutout_path) as hdul:
                # Check for data
                if len(hdul) == 0:
                    return False, "No HDUs found"

                if hdul[0].data is None:
                    return False, "No data in primary HDU"

            return True, None

        except Exception as e:
            return False, str(e)

    def create_thumbnail(self, cutout_path, thumbnail_path, size=(100, 100)):
        """
        Create a thumbnail image from a cutout.

        Parameters:
        -----------
        cutout_path : str or Path
            Path to FITS cutout
        thumbnail_path : str or Path
            Path to save thumbnail (PNG)
        size : tuple
            Thumbnail size (width, height)

        Returns:
        --------
        bool
            True if successful
        """
        try:
            from PIL import Image

            with fits.open(cutout_path) as hdul:
                data = hdul[0].data

                if data is None:
                    return False

                # Normalize data to 0-255
                data_min = np.nanmin(data)
                data_max = np.nanmax(data)

                if data_max > data_min:
                    normalized = 255 * (data - data_min) / (data_max - data_min)
                else:
                    normalized = np.zeros_like(data)

                normalized = normalized.astype(np.uint8)

                # Create image
                img = Image.fromarray(normalized)
                img = img.resize(size, Image.LANCZOS)

                # Save thumbnail
                thumbnail_path = Path(thumbnail_path)
                thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
                img.save(thumbnail_path)

                logger.debug(f"Created thumbnail: {thumbnail_path}")
                return True

        except ImportError:
            logger.warning("PIL not installed, cannot create thumbnails")
            return False
        except Exception as e:
            logger.error(f"Error creating thumbnail: {e}")
            return False

    def compare_cutouts(self, science_path, template_path, difference_path):
        """
        Compare science, template, and difference cutouts.

        Parameters:
        -----------
        science_path : str or Path
            Path to science cutout
        template_path : str or Path
            Path to template cutout
        difference_path : str or Path
            Path to difference cutout

        Returns:
        --------
        dict
            Comparison results
        """
        try:
            results = {}

            with (
                fits.open(science_path) as sci_hdul,
                fits.open(template_path) as tmp_hdul,
                fits.open(difference_path) as diff_hdul,
            ):
                sci_data = sci_hdul[0].data
                tmp_data = tmp_hdul[0].data
                diff_data = diff_hdul[0].data

                # Check shapes match
                if sci_data.shape != tmp_data.shape != diff_data.shape:
                    results["shape_match"] = False
                    return results

                results["shape_match"] = True
                results["shape"] = sci_data.shape

                # Calculate residual (should be ~0 if difference is correct)
                residual = sci_data - tmp_data - diff_data
                results["residual_rms"] = float(np.sqrt(np.mean(residual**2)))

                # Peak signal in difference image
                results["diff_peak"] = float(np.max(np.abs(diff_data)))
                results["diff_snr"] = float(np.max(diff_data) / np.std(diff_data))

                return results

        except Exception as e:
            logger.error(f"Error comparing cutouts: {e}")
            return {"error": str(e)}


def extract_all_cutouts(alert, output_dir, dia_source_id):
    """
    Extract all cutouts from an alert packet.

    Parameters:
    -----------
    alert : dict
        Alert packet
    output_dir : str or Path
        Directory to save cutouts
    dia_source_id : str
        DIASource ID for filenames

    Returns:
    --------
    dict
        Paths to saved cutouts
    """
    processor = CutoutProcessor(output_dir)

    cutouts = {
        "science": alert.get("cutoutScience"),
        "template": alert.get("cutoutTemplate"),
        "difference": alert.get("cutoutDifference"),
    }

    paths = {}

    for cutout_type, cutout_data in cutouts.items():
        if cutout_data:
            output_path = Path(output_dir) / f"{dia_source_id}_{cutout_type}.fits"

            if processor.extract_cutout(cutout_data, output_path):
                paths[cutout_type] = str(output_path)
            else:
                paths[cutout_type] = None
        else:
            paths[cutout_type] = None

    return paths
