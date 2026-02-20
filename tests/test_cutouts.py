"""
Tests for FITS cutout processor.
"""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from lsst_extendedness.cutouts.processor import (
    CutoutConfig,
    CutoutPaths,
    CutoutProcessor,
    extract_cutout_stamps,
)
from lsst_extendedness.models import AlertRecord

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_alert():
    """Create a sample alert for testing."""
    return AlertRecord(
        alert_id=12345,
        dia_source_id=123450001,
        dia_object_id=12345,
        ra=180.0,
        dec=45.0,
        mjd=60000.5,
        filter_name="g",
    )


@pytest.fixture
def valid_fits_data():
    """Create valid FITS header data."""
    # Minimal valid FITS header (2880 bytes minimum block)
    header = b"SIMPLE  =                    T / file conforms to FITS standard"
    header += b" " * (80 - len(header))  # Pad to 80 chars
    header += b"BITPIX  =                    8 / bits per data value"
    header += b" " * (80 - 52)
    header += b"NAXIS   =                    0 / number of axes"
    header += b" " * (80 - 47)
    header += b"END" + b" " * 77
    # Pad to 2880 bytes (FITS block size)
    header += b" " * (2880 - len(header))
    return header


@pytest.fixture
def gzipped_fits_data(valid_fits_data):
    """Create gzipped FITS data."""
    return gzip.compress(valid_fits_data)


@pytest.fixture
def sample_avro_record(valid_fits_data, gzipped_fits_data):
    """Create sample AVRO record with cutouts."""
    return {
        "alertId": 12345,
        "cutoutScience": gzipped_fits_data,
        "cutoutTemplate": valid_fits_data,  # Test non-gzipped
        "cutoutDifference": gzipped_fits_data,
    }


@pytest.fixture
def cutout_config(tmp_path):
    """Create cutout config with temp directory."""
    return CutoutConfig(
        output_dir=tmp_path / "cutouts",
        save_science=True,
        save_template=True,
        save_difference=True,
        compress=False,
        organize_by_date=True,
        organize_by_object=False,
    )


@pytest.fixture
def cutout_processor(cutout_config):
    """Create cutout processor."""
    return CutoutProcessor(cutout_config)


# ============================================================================
# CUTOUT PATHS TESTS
# ============================================================================


class TestCutoutPaths:
    """Tests for CutoutPaths dataclass."""

    def test_default_values(self):
        """Test default None values."""
        paths = CutoutPaths()

        assert paths.science is None
        assert paths.template is None
        assert paths.difference is None

    def test_with_values(self, tmp_path):
        """Test with actual paths."""
        science = tmp_path / "science.fits"
        template = tmp_path / "template.fits"

        paths = CutoutPaths(science=science, template=template)

        assert paths.science == science
        assert paths.template == template
        assert paths.difference is None

    def test_to_dict_empty(self):
        """Test to_dict with no paths."""
        paths = CutoutPaths()
        result = paths.to_dict()

        assert result["science_cutout_path"] is None
        assert result["template_cutout_path"] is None
        assert result["difference_cutout_path"] is None

    def test_to_dict_with_paths(self, tmp_path):
        """Test to_dict with paths."""
        science = tmp_path / "science.fits"
        paths = CutoutPaths(science=science)
        result = paths.to_dict()

        assert result["science_cutout_path"] == str(science)
        assert result["template_cutout_path"] is None


# ============================================================================
# CUTOUT CONFIG TESTS
# ============================================================================


class TestCutoutConfig:
    """Tests for CutoutConfig dataclass."""

    def test_default_values(self):
        """Test default configuration."""
        config = CutoutConfig()

        assert config.output_dir == Path("data/cutouts")
        assert config.save_science is True
        assert config.save_template is True
        assert config.save_difference is True
        assert config.compress is False
        assert config.organize_by_date is True
        assert config.organize_by_object is False

    def test_custom_values(self, tmp_path):
        """Test custom configuration."""
        config = CutoutConfig(
            output_dir=tmp_path,
            save_science=True,
            save_template=False,
            save_difference=False,
            compress=True,
            organize_by_date=False,
            organize_by_object=True,
        )

        assert config.output_dir == tmp_path
        assert config.save_template is False
        assert config.compress is True
        assert config.organize_by_object is True


# ============================================================================
# CUTOUT PROCESSOR TESTS
# ============================================================================


class TestCutoutProcessor:
    """Tests for CutoutProcessor."""

    def test_init_default_config(self, tmp_path):
        """Test initialization with default config."""
        processor = CutoutProcessor()

        assert processor.config is not None
        assert processor.config.output_dir == Path("data/cutouts")

    def test_init_custom_config(self, cutout_config):
        """Test initialization with custom config."""
        processor = CutoutProcessor(cutout_config)

        assert processor.config == cutout_config

    def test_ensure_output_dir(self, cutout_config):
        """Test output directory creation."""
        processor = CutoutProcessor(cutout_config)

        assert cutout_config.output_dir.exists()

    def test_get_output_path_basic(self, cutout_processor, sample_alert):
        """Test output path generation."""
        path = cutout_processor._get_output_path(sample_alert, "science")

        assert path.parent.exists()
        assert "science" in path.name
        assert str(sample_alert.dia_source_id) in path.name

    def test_get_output_path_organize_by_date(self, cutout_config, sample_alert):
        """Test path with date organization."""
        cutout_config.organize_by_date = True
        processor = CutoutProcessor(cutout_config)

        path = processor._get_output_path(sample_alert, "science")

        # Should include date directories (YYYY/MM/DD)
        assert len(path.relative_to(cutout_config.output_dir).parts) >= 3

    def test_get_output_path_organize_by_object(self, cutout_config, sample_alert):
        """Test path with object organization."""
        cutout_config.organize_by_date = False
        cutout_config.organize_by_object = True
        processor = CutoutProcessor(cutout_config)

        path = processor._get_output_path(sample_alert, "science")

        assert f"obj_{sample_alert.dia_object_id}" in str(path)

    def test_get_output_path_compressed(self, cutout_config, sample_alert):
        """Test path with compression enabled."""
        cutout_config.compress = True
        processor = CutoutProcessor(cutout_config)

        path = processor._get_output_path(sample_alert, "science")

        assert path.suffix == ".gz"

    def test_extract_cutout_empty_data(self, cutout_processor, tmp_path):
        """Test extraction with no data."""
        output_path = tmp_path / "test.fits"

        result = cutout_processor._extract_cutout(None, output_path)

        assert result is False
        assert not output_path.exists()

    def test_extract_cutout_valid_fits(self, cutout_processor, valid_fits_data, tmp_path):
        """Test extraction with valid FITS data."""
        output_path = tmp_path / "test.fits"

        result = cutout_processor._extract_cutout(valid_fits_data, output_path)

        assert result is True
        assert output_path.exists()
        # Verify content
        assert output_path.read_bytes().startswith(b"SIMPLE")

    def test_extract_cutout_gzipped_input(self, cutout_processor, gzipped_fits_data, tmp_path):
        """Test extraction with gzipped input."""
        output_path = tmp_path / "test.fits"

        result = cutout_processor._extract_cutout(gzipped_fits_data, output_path)

        assert result is True
        assert output_path.exists()
        # Should be decompressed
        assert output_path.read_bytes().startswith(b"SIMPLE")

    def test_extract_cutout_with_compression(self, cutout_config, valid_fits_data, tmp_path):
        """Test extraction with output compression."""
        cutout_config.compress = True
        processor = CutoutProcessor(cutout_config)
        output_path = tmp_path / "test.fits.gz"

        result = processor._extract_cutout(valid_fits_data, output_path)

        assert result is True
        assert output_path.exists()
        # Should be gzipped
        assert output_path.read_bytes()[:2] == b"\x1f\x8b"

    def test_extract_cutout_invalid_fits(self, cutout_processor, tmp_path):
        """Test extraction with invalid FITS header."""
        output_path = tmp_path / "test.fits"
        invalid_data = b"NOT A FITS FILE"

        result = cutout_processor._extract_cutout(invalid_data, output_path)

        assert result is False

    def test_process_alert(self, cutout_processor, sample_alert, sample_avro_record):
        """Test processing a single alert."""
        paths = cutout_processor.process_alert(sample_alert, sample_avro_record)

        assert paths.science is not None
        assert paths.template is not None
        assert paths.difference is not None
        assert paths.science.exists()
        assert paths.template.exists()
        assert paths.difference.exists()

    def test_process_alert_missing_cutouts(self, cutout_processor, sample_alert):
        """Test processing alert without cutout data."""
        avro = {"alertId": 12345}  # No cutout fields

        paths = cutout_processor.process_alert(sample_alert, avro)

        assert paths.science is None
        assert paths.template is None
        assert paths.difference is None

    def test_process_alert_selective_save(self, cutout_config, sample_alert, sample_avro_record):
        """Test processing with selective save options."""
        cutout_config.save_science = True
        cutout_config.save_template = False
        cutout_config.save_difference = False
        processor = CutoutProcessor(cutout_config)

        paths = processor.process_alert(sample_alert, sample_avro_record)

        assert paths.science is not None
        assert paths.template is None
        assert paths.difference is None

    def test_process_batch(self, cutout_processor, sample_alert, sample_avro_record):
        """Test batch processing."""
        # Create multiple alerts
        alerts_with_avro = [(sample_alert, sample_avro_record)] * 3

        results = cutout_processor.process_batch(alerts_with_avro)

        assert len(results) == 3
        for paths in results:
            assert paths.science is not None

    def test_cleanup_old_cutouts(self, cutout_config, sample_alert, sample_avro_record):
        """Test cleanup of old cutouts."""
        import os
        import time

        processor = CutoutProcessor(cutout_config)

        # Create some cutouts
        paths = processor.process_alert(sample_alert, sample_avro_record)

        # Make files appear old
        old_time = time.time() - (60 * 86400)  # 60 days ago
        if paths.science:
            os.utime(paths.science, (old_time, old_time))

        # Run cleanup (30 days)
        removed = processor.cleanup_old_cutouts(days=30)

        assert removed >= 1

    def test_get_stats_empty(self, cutout_processor):
        """Test stats on empty directory."""
        stats = cutout_processor.get_stats()

        assert stats["total_files"] == 0
        assert stats["total_size_mb"] == 0
        assert stats["by_type"]["science"] == 0

    def test_get_stats_with_files(self, cutout_processor, sample_alert, sample_avro_record):
        """Test stats after processing."""
        cutout_processor.process_alert(sample_alert, sample_avro_record)

        stats = cutout_processor.get_stats()

        assert stats["total_files"] >= 3
        assert stats["by_type"]["science"] >= 1
        assert stats["by_type"]["template"] >= 1
        assert stats["by_type"]["difference"] >= 1


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================


class TestExtractCutoutStamps:
    """Tests for extract_cutout_stamps function."""

    def test_extract_all_stamps(self, valid_fits_data, gzipped_fits_data):
        """Test extracting all stamps."""
        avro = {
            "cutoutScience": gzipped_fits_data,
            "cutoutTemplate": valid_fits_data,
            "cutoutDifference": gzipped_fits_data,
        }

        stamps = extract_cutout_stamps(avro)

        assert stamps["cutoutScience"] is not None
        assert stamps["cutoutTemplate"] is not None
        assert stamps["cutoutDifference"] is not None
        # Gzipped should be decompressed
        assert stamps["cutoutScience"].startswith(b"SIMPLE")

    def test_extract_missing_stamps(self):
        """Test with missing stamps."""
        avro = {"alertId": 12345}

        stamps = extract_cutout_stamps(avro)

        assert stamps["cutoutScience"] is None
        assert stamps["cutoutTemplate"] is None
        assert stamps["cutoutDifference"] is None

    def test_extract_partial_stamps(self, valid_fits_data):
        """Test with some stamps missing."""
        avro = {"cutoutScience": valid_fits_data}

        stamps = extract_cutout_stamps(avro)

        assert stamps["cutoutScience"] is not None
        assert stamps["cutoutTemplate"] is None
        assert stamps["cutoutDifference"] is None


class TestLoadCutoutAsArray:
    """Tests for load_cutout_as_array function."""

    def test_load_requires_astropy(self, tmp_path):
        """Test that astropy import error is raised properly."""
        import builtins
        import sys

        from lsst_extendedness.cutouts import processor

        # Force reload of module with astropy mocked out
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "astropy.io" or name.startswith("astropy"):
                raise ImportError("No module named 'astropy'")
            return original_import(name, *args, **kwargs)

        # Create a dummy file
        test_file = tmp_path / "test.fits"
        test_file.write_bytes(b"SIMPLE  =                    T")

        try:
            builtins.__import__ = mock_import
            # Clear cached import
            if "astropy.io.fits" in sys.modules:
                del sys.modules["astropy.io.fits"]
            if "astropy.io" in sys.modules:
                del sys.modules["astropy.io"]
            if "astropy" in sys.modules:
                del sys.modules["astropy"]

            with pytest.raises(ImportError, match="astropy required"):
                processor.load_cutout_as_array(test_file)
        finally:
            builtins.__import__ = original_import

    def test_load_regular_fits(self, tmp_path):
        """Test loading regular FITS file as array."""
        pytest.importorskip("astropy")
        import numpy as np

        # Create a minimal valid FITS file with image data
        from astropy.io import fits

        from lsst_extendedness.cutouts.processor import load_cutout_as_array

        # Create simple image data
        data = np.zeros((10, 10), dtype=np.float32)
        data[5, 5] = 1.0

        test_file = tmp_path / "test.fits"
        hdu = fits.PrimaryHDU(data)
        hdu.writeto(test_file)

        # Load and verify
        result = load_cutout_as_array(test_file)

        assert result.shape == (10, 10)
        assert result[5, 5] == 1.0

    def test_load_gzipped_fits(self, tmp_path):
        """Test loading gzipped FITS file as array."""
        pytest.importorskip("astropy")
        import gzip
        import io

        import numpy as np
        from astropy.io import fits

        from lsst_extendedness.cutouts.processor import load_cutout_as_array

        # Create simple image data
        data = np.ones((8, 8), dtype=np.float32) * 42.0

        # Write to bytes
        buffer = io.BytesIO()
        hdu = fits.PrimaryHDU(data)
        hdu.writeto(buffer)
        buffer.seek(0)

        # Gzip it
        test_file = tmp_path / "test.fits.gz"
        with gzip.open(test_file, "wb") as f:
            f.write(buffer.read())

        # Load and verify
        result = load_cutout_as_array(test_file)

        assert result.shape == (8, 8)
        assert result[0, 0] == pytest.approx(42.0)


class TestCutoutExtractionErrors:
    """Tests for error handling in cutout extraction."""

    def test_extract_cutout_write_error(self, cutout_config, valid_fits_data, tmp_path):
        """Test extraction failure when write fails."""
        from unittest.mock import MagicMock, patch

        processor = CutoutProcessor(cutout_config)

        # Create a path that will fail on write
        output_path = tmp_path / "test.fits"

        # Mock write_bytes to raise an exception
        with patch.object(Path, "write_bytes", side_effect=PermissionError("Permission denied")):
            result = processor._extract_cutout(valid_fits_data, output_path)

        # Should return False due to exception
        assert result is False

    def test_extract_cutout_decompression_error(self, cutout_processor, tmp_path):
        """Test extraction with corrupted gzip data."""
        output_path = tmp_path / "test.fits"
        # Looks like gzip (magic bytes) but is corrupted
        corrupted_gzip = b"\x1f\x8b\x08\x00" + b"corrupted data here"

        result = cutout_processor._extract_cutout(corrupted_gzip, output_path)

        # Should return False due to decompression error
        assert result is False
