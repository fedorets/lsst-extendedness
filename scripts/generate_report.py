#!/usr/bin/env python3
"""
LSST Alert Pipeline - Report Generation Script
Generates summary reports from processed data and statistics
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


class ReportGenerator:
    """Generates reports from LSST alert pipeline data."""

    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.csv_dir = self.data_dir / "processed" / "csv"
        self.summary_dir = self.data_dir / "processed" / "summary"
        self.cutout_dir = self.data_dir / "cutouts"

    def get_csv_files(self, start_date=None, end_date=None):
        """
        Get CSV files within date range.

        Parameters:
        -----------
        start_date : str or datetime
            Start date (inclusive)
        end_date : str or datetime
            End date (inclusive)

        Returns:
        --------
        list
            List of CSV file paths
        """
        csv_files = sorted(self.csv_dir.glob("**/*.csv"))

        if start_date or end_date:
            filtered_files = []
            for csv_file in csv_files:
                # Extract date from filename (format: lsst_alerts_YYYYMMDD.csv)
                filename = csv_file.name
                if filename.startswith("lsst_alerts_"):
                    date_str = filename.replace("lsst_alerts_", "").replace(".csv", "")
                    try:
                        file_date = datetime.strptime(date_str, "%Y%m%d")

                        if start_date and file_date < pd.to_datetime(start_date):
                            continue
                        if end_date and file_date > pd.to_datetime(end_date):
                            continue

                        filtered_files.append(csv_file)
                    except ValueError:
                        continue

            return filtered_files

        return csv_files

    def load_data(self, csv_files):
        """
        Load data from CSV files.

        Parameters:
        -----------
        csv_files : list
            List of CSV file paths

        Returns:
        --------
        DataFrame
            Combined data from all CSV files
        """
        if not csv_files:
            print("No CSV files found")
            return pd.DataFrame()

        print(f"Loading {len(csv_files)} CSV files...")

        dfs = []
        for csv_file in csv_files:
            try:
                df = pd.read_csv(csv_file)
                dfs.append(df)
            except Exception as e:
                print(f"Warning: Failed to load {csv_file}: {e}")

        if not dfs:
            return pd.DataFrame()

        combined_df = pd.concat(dfs, ignore_index=True)
        print(f"Loaded {len(combined_df)} records")

        return combined_df

    def generate_daily_report(self, date=None):
        """
        Generate daily report for a specific date.

        Parameters:
        -----------
        date : str or datetime
            Date for report (default: yesterday)

        Returns:
        --------
        dict
            Daily report statistics
        """
        if date is None:
            date = datetime.now() - timedelta(days=1)
        else:
            date = pd.to_datetime(date)

        date_str = date.strftime("%Y%m%d")
        print(f"\nGenerating daily report for {date_str}...")

        # Get CSV files for this date
        csv_files = self.get_csv_files(start_date=date, end_date=date)

        if not csv_files:
            print(f"No data found for {date_str}")
            return None

        # Load data
        df = self.load_data(csv_files)

        if df.empty:
            return None

        # Generate statistics
        report = {
            "date": date_str,
            "total_alerts": len(df),
            "unique_objects": df["diaObjectId"].nunique() if "diaObjectId" in df.columns else 0,
            "unique_sources": df["diaSourceId"].nunique() if "diaSourceId" in df.columns else 0,
        }

        # Filter statistics
        if "filterName" in df.columns:
            report["alerts_by_filter"] = df["filterName"].value_counts().to_dict()

        # SSSource statistics
        if "hasSSSource" in df.columns:
            report["with_sssource"] = int(df["hasSSSource"].sum())
            report["without_sssource"] = int((~df["hasSSSource"]).sum())

        # Extendedness statistics
        if "extendednessMedian" in df.columns:
            report["extendedness_stats"] = {
                "median_mean": float(df["extendednessMedian"].mean()),
                "median_std": float(df["extendednessMedian"].std()),
                "median_min": float(df["extendednessMedian"].min()),
                "median_max": float(df["extendednessMedian"].max()),
            }

        # Cutout statistics
        cutout_cols = [col for col in df.columns if "cutout_path" in col]
        if cutout_cols:
            report["cutouts"] = {}
            for col in cutout_cols:
                cutout_type = col.replace("_cutout_path", "")
                report["cutouts"][cutout_type] = int(df[col].notna().sum())

        # Sky coverage (RA/Dec ranges)
        if "ra" in df.columns and "dec" in df.columns:
            report["sky_coverage"] = {
                "ra_min": float(df["ra"].min()),
                "ra_max": float(df["ra"].max()),
                "dec_min": float(df["dec"].min()),
                "dec_max": float(df["dec"].max()),
                "area_sq_deg": self._estimate_sky_area(df),
            }

        # Flux statistics
        if "psFlux" in df.columns:
            report["flux_stats"] = {
                "mean": float(df["psFlux"].mean()),
                "median": float(df["psFlux"].median()),
                "std": float(df["psFlux"].std()),
            }

        # SNR statistics
        if "snr" in df.columns:
            report["snr_stats"] = {
                "mean": float(df["snr"].mean()),
                "median": float(df["snr"].median()),
                "above_5": int((df["snr"] > 5).sum()),
                "above_10": int((df["snr"] > 10).sum()),
            }

        return report

    def generate_monthly_report(self, year, month):
        """
        Generate monthly summary report.

        Parameters:
        -----------
        year : int
            Year
        month : int
            Month (1-12)

        Returns:
        --------
        dict
            Monthly report statistics
        """
        print(f"\nGenerating monthly report for {year}-{month:02d}...")

        # Get all CSV files for this month
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)

        csv_files = self.get_csv_files(start_date=start_date, end_date=end_date)

        if not csv_files:
            print(f"No data found for {year}-{month:02d}")
            return None

        # Load data
        df = self.load_data(csv_files)

        if df.empty:
            return None

        # Generate statistics
        report = {
            "year": year,
            "month": month,
            "total_alerts": len(df),
            "unique_objects": df["diaObjectId"].nunique() if "diaObjectId" in df.columns else 0,
            "days_with_data": len(csv_files),
            "avg_alerts_per_day": len(df) / len(csv_files) if csv_files else 0,
        }

        # Daily breakdown
        if "timestamp" in df.columns:
            df["date"] = pd.to_datetime(df["timestamp"]).dt.date
            daily_counts = df.groupby("date").size()
            report["daily_stats"] = {
                "max_alerts": int(daily_counts.max()),
                "min_alerts": int(daily_counts.min()),
                "avg_alerts": float(daily_counts.mean()),
            }

        # Similar statistics as daily report
        if "filterName" in df.columns:
            report["alerts_by_filter"] = df["filterName"].value_counts().to_dict()

        if "hasSSSource" in df.columns:
            report["with_sssource"] = int(df["hasSSSource"].sum())
            report["sso_fraction"] = float(df["hasSSSource"].mean())

        return report

    def _estimate_sky_area(self, df):
        """Rough estimate of sky area covered (in square degrees)."""
        if "ra" not in df.columns or "dec" not in df.columns:
            return 0.0

        ra_range = df["ra"].max() - df["ra"].min()
        dec_range = df["dec"].max() - df["dec"].min()

        # Simple rectangular approximation (not accurate for large areas)
        area = ra_range * dec_range * np.cos(np.radians(df["dec"].mean()))
        return float(area)

    def save_report(self, report, output_file):
        """Save report to JSON file."""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\nReport saved to: {output_path}")

    def print_report(self, report):
        """Print report to console."""
        print("\n" + "=" * 60)
        print("Report Summary")
        print("=" * 60)

        for key, value in report.items():
            if isinstance(value, dict):
                print(f"\n{key}:")
                for subkey, subvalue in value.items():
                    print(f"  {subkey}: {subvalue}")
            else:
                print(f"{key}: {value}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate reports from LSST alert pipeline data")
    parser.add_argument(
        "--base-dir",
        default=".",
        help="Base directory of LSST pipeline (default: current directory)",
    )
    parser.add_argument(
        "--type", choices=["daily", "monthly"], default="daily", help="Report type (default: daily)"
    )
    parser.add_argument("--date", help="Date for daily report (YYYY-MM-DD, default: yesterday)")
    parser.add_argument("--year", type=int, help="Year for monthly report")
    parser.add_argument("--month", type=int, help="Month for monthly report (1-12)")
    parser.add_argument("--output", help="Output file for report (JSON)")

    args = parser.parse_args()

    print("=" * 60)
    print("LSST Alert Pipeline - Report Generation")
    print("=" * 60)

    # Create report generator
    generator = ReportGenerator(args.base_dir)

    # Generate report
    if args.type == "daily":
        report = generator.generate_daily_report(date=args.date)
    elif args.type == "monthly":
        if not args.year or not args.month:
            print("Error: --year and --month required for monthly report")
            sys.exit(1)
        report = generator.generate_monthly_report(args.year, args.month)

    if report is None:
        print("\nNo data available for requested period")
        sys.exit(1)

    # Print report
    generator.print_report(report)

    # Save report if requested
    if args.output:
        generator.save_report(report, args.output)

    print("\n✓ Report generation completed")


if __name__ == "__main__":
    main()
