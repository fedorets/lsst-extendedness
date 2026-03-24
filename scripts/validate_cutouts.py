#!/usr/bin/env python3
"""
LSST Alert Pipeline - Cutout Validation Script
Validates integrity and metadata of FITS cutout files
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from astropy.io import fits


class CutoutValidator:
    """Validates FITS cutout files."""

    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.cutout_dir = self.base_dir / "data" / "cutouts"

        self.stats = {
            "total_files": 0,
            "valid_files": 0,
            "invalid_files": 0,
            "corrupted_files": 0,
            "empty_files": 0,
            "errors": [],
        }

    def validate_fits_file(self, filepath):
        """
        Validate a single FITS file.

        Returns:
        --------
        dict
            Validation results
        """
        result = {"filepath": str(filepath), "valid": False, "error": None, "metadata": {}}

        try:
            # Check file exists and is not empty
            if not filepath.exists():
                result["error"] = "File not found"
                return result

            if filepath.stat().st_size == 0:
                result["error"] = "Empty file"
                self.stats["empty_files"] += 1
                return result

            # Try to open FITS file
            with fits.open(filepath) as hdul:
                # Check if file has at least one HDU
                if len(hdul) == 0:
                    result["error"] = "No HDUs found"
                    return result

                # Get primary HDU
                primary_hdu = hdul[0]

                # Check if data exists
                if primary_hdu.data is None:
                    result["error"] = "No data in primary HDU"
                    return result

                # Extract metadata
                result["metadata"] = {
                    "shape": primary_hdu.data.shape,
                    "dtype": str(primary_hdu.data.dtype),
                    "n_hdus": len(hdul),
                    "file_size_kb": filepath.stat().st_size / 1024,
                }

                # Basic data statistics
                data = primary_hdu.data
                result["metadata"]["data_stats"] = {
                    "min": float(np.min(data)),
                    "max": float(np.max(data)),
                    "mean": float(np.mean(data)),
                    "median": float(np.median(data)),
                    "std": float(np.std(data)),
                    "has_nan": bool(np.any(np.isnan(data))),
                    "has_inf": bool(np.any(np.isinf(data))),
                }

                # Check header for expected keywords
                header = primary_hdu.header
                result["metadata"]["header_keys"] = len(header)

                # Extract some common LSST keywords if present
                lsst_keywords = ["FILTER", "EXPTIME", "MJD-OBS", "RA", "DEC"]
                for keyword in lsst_keywords:
                    if keyword in header:
                        result["metadata"][keyword.lower()] = header[keyword]

                result["valid"] = True
                self.stats["valid_files"] += 1

        except (OSError, fits.verify.VerifyError) as e:
            result["error"] = f"Corrupted FITS file: {e!s}"
            self.stats["corrupted_files"] += 1
        except Exception as e:
            result["error"] = f"Unexpected error: {e!s}"
            self.stats["invalid_files"] += 1

        if result["error"]:
            self.stats["errors"].append(
                {"file": str(filepath.relative_to(self.base_dir)), "error": result["error"]}
            )

        return result

    def validate_directory(self, directory=None, recursive=True, sample_rate=1.0):
        """
        Validate all FITS files in a directory.

        Parameters:
        -----------
        directory : Path, optional
            Directory to validate (default: cutout_dir)
        recursive : bool
            Whether to recursively validate subdirectories
        sample_rate : float
            Fraction of files to validate (0.0-1.0)

        Returns:
        --------
        dict
            Validation statistics
        """
        if directory is None:
            directory = self.cutout_dir
        else:
            directory = Path(directory)

        if not directory.exists():
            print(f"Directory not found: {directory}")
            return self.stats

        # Find all FITS files
        pattern = "**/*.fits" if recursive else "*.fits"
        fits_files = list(directory.glob(pattern))

        print(f"Found {len(fits_files)} FITS files in {directory}")

        if sample_rate < 1.0:
            # Random sampling
            import random

            n_sample = int(len(fits_files) * sample_rate)
            fits_files = random.sample(fits_files, n_sample)
            print(f"Validating {n_sample} files (sample rate: {sample_rate:.1%})")

        # Validate each file
        self.stats["total_files"] = len(fits_files)

        for i, filepath in enumerate(fits_files, 1):
            if i % 100 == 0:
                print(f"Progress: {i}/{len(fits_files)} files validated...")

            result = self.validate_fits_file(filepath)

            # Print errors immediately
            if result["error"]:
                print(f"ERROR: {filepath.name} - {result['error']}")

        return self.stats

    def print_summary(self):
        """Print validation summary."""
        print("\n" + "=" * 60)
        print("Validation Summary")
        print("=" * 60)

        print(f"\nTotal files checked: {self.stats['total_files']}")
        print(f"Valid files: {self.stats['valid_files']}")
        print(f"Invalid files: {self.stats['invalid_files']}")
        print(f"Corrupted files: {self.stats['corrupted_files']}")
        print(f"Empty files: {self.stats['empty_files']}")

        if self.stats["total_files"] > 0:
            valid_pct = 100 * self.stats["valid_files"] / self.stats["total_files"]
            print(f"\nSuccess rate: {valid_pct:.1f}%")

        if self.stats["errors"]:
            print(f"\nErrors found: {len(self.stats['errors'])}")
            print("\nFirst 10 errors:")
            for error in self.stats["errors"][:10]:
                print(f"  - {error['file']}: {error['error']}")

            if len(self.stats["errors"]) > 10:
                print(f"  ... and {len(self.stats['errors']) - 10} more")

    def save_report(self, output_file):
        """Save validation report to JSON file."""
        report = {
            "timestamp": datetime.now().isoformat(),
            "cutout_directory": str(self.cutout_dir),
            "statistics": self.stats,
        }

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\nValidation report saved to: {output_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate LSST alert cutout FITS files")
    parser.add_argument(
        "--base-dir",
        default=".",
        help="Base directory of LSST pipeline (default: current directory)",
    )
    parser.add_argument(
        "--directory", help="Specific directory to validate (default: data/cutouts)"
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        default=True,
        help="Recursively validate subdirectories (default: True)",
    )
    parser.add_argument(
        "--sample-rate",
        type=float,
        default=1.0,
        help="Fraction of files to validate (0.0-1.0, default: 1.0)",
    )
    parser.add_argument("--report", help="Output file for validation report (JSON)")

    args = parser.parse_args()

    print("=" * 60)
    print("LSST Alert Pipeline - Cutout Validation")
    print("=" * 60)
    print(f"\nBase directory: {args.base_dir}")

    # Create validator
    validator = CutoutValidator(args.base_dir)

    # Run validation
    print("\nStarting validation...")
    validator.validate_directory(
        directory=args.directory, recursive=args.recursive, sample_rate=args.sample_rate
    )

    # Print summary
    validator.print_summary()

    # Save report if requested
    if args.report:
        validator.save_report(args.report)

    # Exit with error code if there were invalid files
    if validator.stats["invalid_files"] > 0 or validator.stats["corrupted_files"] > 0:
        print("\n⚠ Validation completed with errors")
        sys.exit(1)
    else:
        print("\n✓ All files validated successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()
