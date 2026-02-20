"""
CSV writing utilities for LSST alerts
Handles efficient CSV writing with varying column sets and batch processing
"""

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class CSVWriter:
    """
    Handles writing LSST alert records to CSV files.
    Supports dynamic columns (trail*, pixelFlags*) and efficient batch writing.
    """

    def __init__(self, output_dir, batch_size=100):
        """
        Initialize CSV writer.

        Parameters:
        -----------
        output_dir : str or Path
            Directory to write CSV files
        batch_size : int
            Number of records to accumulate before writing
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.batch_size = batch_size

        self.record_buffer = []
        self.rows_written = 0

    def add_record(self, record):
        """
        Add a record to the buffer.

        Parameters:
        -----------
        record : dict
            Alert record to add

        Returns:
        --------
        bool
            True if buffer was flushed
        """
        self.record_buffer.append(record)

        if len(self.record_buffer) >= self.batch_size:
            self.flush()
            return True

        return False

    def flush(self, filepath=None):
        """
        Write buffered records to CSV file.

        Parameters:
        -----------
        filepath : str or Path, optional
            Output file path (default: auto-generated)

        Returns:
        --------
        int
            Number of rows written
        """
        if not self.record_buffer:
            logger.debug("No records to flush")
            return 0

        if filepath is None:
            filepath = self._get_default_filepath()

        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        try:
            df = pd.DataFrame(self.record_buffer)

            # Write to CSV
            if filepath.exists():
                # Append without header
                df.to_csv(filepath, mode="a", header=False, index=False)
            else:
                # Create new file with header
                df.to_csv(filepath, index=False)

            rows = len(self.record_buffer)
            self.rows_written += rows
            logger.info(f"Wrote {rows} records to {filepath}")

            # Clear buffer
            self.record_buffer = []

            return rows

        except Exception as e:
            logger.error(f"Error writing CSV: {e}", exc_info=True)
            return 0

    def _get_default_filepath(self):
        """Generate default filepath based on current date."""
        today = datetime.now().strftime("%Y%m%d")
        return self.output_dir / f"lsst_alerts_{today}.csv"

    def get_buffer_size(self):
        """Return number of records in buffer."""
        return len(self.record_buffer)

    def clear_buffer(self):
        """Clear the record buffer without writing."""
        count = len(self.record_buffer)
        self.record_buffer = []
        logger.debug(f"Cleared {count} records from buffer")
        return count


class DynamicCSVWriter:
    """
    CSV writer that handles dynamic columns across multiple files.
    Useful when alert schemas evolve or different alerts have different fields.
    """

    def __init__(self, output_dir):
        """
        Initialize dynamic CSV writer.

        Parameters:
        -----------
        output_dir : str or Path
            Directory to write CSV files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Track all columns seen
        self.all_columns = set()
        self.record_buffer = []

    def add_record(self, record):
        """
        Add a record and track its columns.

        Parameters:
        -----------
        record : dict
            Alert record to add
        """
        # Track new columns
        self.all_columns.update(record.keys())
        self.record_buffer.append(record)

    def flush(self, filepath):
        """
        Write all records with unified column set.

        Parameters:
        -----------
        filepath : str or Path
            Output file path
        """
        if not self.record_buffer:
            return 0

        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Create DataFrame with all columns
            df = pd.DataFrame(self.record_buffer)

            # Ensure all tracked columns are present
            for col in self.all_columns:
                if col not in df.columns:
                    df[col] = None

            # Sort columns for consistency
            df = df[sorted(df.columns)]

            # Write
            if filepath.exists():
                # When appending, we may need to handle column mismatches
                existing_df = pd.read_csv(filepath, nrows=0)  # Just get columns
                existing_cols = set(existing_df.columns)

                # If columns differ, need to rewrite entire file
                if existing_cols != set(df.columns):
                    logger.warning(f"Column mismatch in {filepath}, rewriting file")
                    existing_df = pd.read_csv(filepath)

                    # Merge column sets
                    all_cols = sorted(set(existing_df.columns) | set(df.columns))

                    # Ensure all columns present in both
                    for col in all_cols:
                        if col not in existing_df.columns:
                            existing_df[col] = None
                        if col not in df.columns:
                            df[col] = None

                    # Combine and write
                    combined_df = pd.concat([existing_df, df], ignore_index=True)
                    combined_df[all_cols].to_csv(filepath, index=False)
                else:
                    # Columns match, safe to append
                    df.to_csv(filepath, mode="a", header=False, index=False)
            else:
                # New file
                df.to_csv(filepath, index=False)

            rows = len(self.record_buffer)
            logger.info(f"Wrote {rows} records to {filepath}")

            # Clear buffer
            self.record_buffer = []

            return rows

        except Exception as e:
            logger.error(f"Error writing dynamic CSV: {e}", exc_info=True)
            return 0

    def get_column_list(self):
        """Return list of all columns seen."""
        return sorted(self.all_columns)


def write_csv_with_metadata(records, filepath, metadata=None):
    """
    Write CSV with optional metadata header.

    Parameters:
    -----------
    records : list of dict
        Records to write
    filepath : str or Path
        Output file path
    metadata : dict, optional
        Metadata to write as comments at top of file

    Returns:
    --------
    int
        Number of rows written
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Convert to DataFrame
        df = pd.DataFrame(records)

        # Write metadata as comments
        with open(filepath, "w") as f:
            if metadata:
                f.write("# LSST Alert Data\n")
                for key, value in metadata.items():
                    f.write(f"# {key}: {value}\n")
                f.write("#\n")

            # Write CSV data
            df.to_csv(f, index=False)

        logger.info(f"Wrote {len(records)} records with metadata to {filepath}")
        return len(records)

    except Exception as e:
        logger.error(f"Error writing CSV with metadata: {e}")
        return 0


def append_to_csv(records, filepath, create_if_missing=True):
    """
    Append records to existing CSV file.

    Parameters:
    -----------
    records : list of dict
        Records to append
    filepath : str or Path
        CSV file path
    create_if_missing : bool
        Create file if it doesn't exist

    Returns:
    --------
    int
        Number of rows written
    """
    filepath = Path(filepath)

    if not filepath.exists():
        if not create_if_missing:
            logger.error(f"File does not exist: {filepath}")
            return 0
        else:
            # Create new file
            filepath.parent.mkdir(parents=True, exist_ok=True)
            df = pd.DataFrame(records)
            df.to_csv(filepath, index=False)
            return len(records)

    try:
        df = pd.DataFrame(records)
        df.to_csv(filepath, mode="a", header=False, index=False)

        logger.debug(f"Appended {len(records)} records to {filepath}")
        return len(records)

    except Exception as e:
        logger.error(f"Error appending to CSV: {e}")
        return 0


def merge_csv_files(
    input_files, output_file, remove_duplicates=False, sort_by=None, dedupe_column=None
):
    """
    Merge multiple CSV files into one.

    Parameters:
    -----------
    input_files : list of str/Path
        CSV files to merge
    output_file : str or Path
        Output file path
    remove_duplicates : bool
        Remove duplicate rows
    sort_by : str or list, optional
        Column(s) to sort by
    dedupe_column : str, optional
        Column to use for deduplication (keeps first occurrence)

    Returns:
    --------
    int
        Number of rows in merged file
    """
    try:
        dfs = []
        for filepath in input_files:
            filepath = Path(filepath)
            if filepath.exists():
                df = pd.read_csv(filepath)
                dfs.append(df)
            else:
                logger.warning(f"File not found: {filepath}")

        if not dfs:
            logger.error("No valid input files")
            return 0

        # Merge
        merged_df = pd.concat(dfs, ignore_index=True)

        # Deduplicate by specific column
        if dedupe_column and dedupe_column in merged_df.columns:
            before = len(merged_df)
            merged_df = merged_df.drop_duplicates(subset=[dedupe_column], keep="first")
            after = len(merged_df)
            logger.info(f"Removed {before - after} duplicates based on {dedupe_column}")

        # Remove complete duplicate rows
        elif remove_duplicates:
            before = len(merged_df)
            merged_df = merged_df.drop_duplicates()
            after = len(merged_df)
            logger.info(f"Removed {before - after} duplicate rows")

        # Sort
        if sort_by:
            merged_df = merged_df.sort_values(by=sort_by)

        # Write output
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        merged_df.to_csv(output_file, index=False)

        logger.info(f"Merged {len(input_files)} files into {output_file} ({len(merged_df)} rows)")
        return len(merged_df)

    except Exception as e:
        logger.error(f"Error merging CSV files: {e}")
        return 0


def split_csv_by_column(input_file, output_dir, split_column, prefix="split"):
    """
    Split CSV file into multiple files based on column value.

    Parameters:
    -----------
    input_file : str or Path
        Input CSV file
    output_dir : str or Path
        Output directory
    split_column : str
        Column to split by
    prefix : str
        Prefix for output files

    Returns:
    --------
    dict
        Mapping of split values to output files
    """
    try:
        df = pd.read_csv(input_file)

        if split_column not in df.columns:
            logger.error(f"Column '{split_column}' not found in {input_file}")
            return {}

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        output_files = {}

        # Group by split column
        for value, group_df in df.groupby(split_column):
            # Create output filename
            safe_value = str(value).replace("/", "_").replace(" ", "_")
            output_file = output_dir / f"{prefix}_{safe_value}.csv"

            # Write group
            group_df.to_csv(output_file, index=False)
            output_files[value] = output_file

            logger.info(f"Wrote {len(group_df)} rows to {output_file}")

        return output_files

    except Exception as e:
        logger.error(f"Error splitting CSV: {e}")
        return {}


def csv_stats(csv_file):
    """
    Get statistics about a CSV file.

    Parameters:
    -----------
    csv_file : str or Path
        CSV file to analyze

    Returns:
    --------
    dict
        Statistics about the CSV file
    """
    try:
        df = pd.read_csv(csv_file)

        stats = {
            "filepath": str(csv_file),
            "rows": len(df),
            "columns": len(df.columns),
            "column_names": list(df.columns),
            "file_size_kb": Path(csv_file).stat().st_size / 1024,
            "memory_usage_mb": df.memory_usage(deep=True).sum() / (1024 * 1024),
        }

        # Identify dynamic columns
        trail_cols = [col for col in df.columns if col.startswith("trail")]
        pixel_cols = [col for col in df.columns if col.startswith("pixelFlags")]

        if trail_cols:
            stats["trail_columns"] = trail_cols
        if pixel_cols:
            stats["pixel_flag_columns"] = pixel_cols

        # Check for reassociations
        if "isReassociation" in df.columns:
            stats["reassociations"] = int(df["isReassociation"].sum())
            stats["reassociation_rate"] = float(df["isReassociation"].mean())

        # Check for SSObjects
        if "hasSSSource" in df.columns:
            stats["with_ssobject"] = int(df["hasSSSource"].sum())
            stats["ssobject_rate"] = float(df["hasSSSource"].mean())

        return stats

    except Exception as e:
        logger.error(f"Error getting CSV stats: {e}")
        return {"error": str(e)}


def convert_csv_to_json(csv_file, json_file, orient="records", indent=2):
    """
    Convert CSV to JSON format.

    Parameters:
    -----------
    csv_file : str or Path
        Input CSV file
    json_file : str or Path
        Output JSON file
    orient : str
        JSON orientation ('records', 'index', 'columns', etc.)
    indent : int
        JSON indentation

    Returns:
    --------
    int
        Number of records written
    """
    try:
        df = pd.read_csv(csv_file)

        json_file = Path(json_file)
        json_file.parent.mkdir(parents=True, exist_ok=True)

        df.to_json(json_file, orient=orient, indent=indent)

        logger.info(f"Converted {csv_file} to {json_file} ({len(df)} records)")
        return len(df)

    except Exception as e:
        logger.error(f"Error converting CSV to JSON: {e}")
        return 0


def filter_csv(input_file, output_file, filter_func):
    """
    Filter CSV file based on custom function.

    Parameters:
    -----------
    input_file : str or Path
        Input CSV file
    output_file : str or Path
        Output CSV file
    filter_func : callable
        Function that takes a row (dict) and returns True/False

    Returns:
    --------
    int
        Number of rows in filtered file
    """
    try:
        df = pd.read_csv(input_file)

        # Apply filter
        mask = df.apply(lambda row: filter_func(row.to_dict()), axis=1)
        filtered_df = df[mask]

        # Write output
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        filtered_df.to_csv(output_file, index=False)

        logger.info(f"Filtered {len(df)} rows to {len(filtered_df)} rows")
        return len(filtered_df)

    except Exception as e:
        logger.error(f"Error filtering CSV: {e}")
        return 0
