"""
LSST Extendedness Pipeline - Test Suite

Unit and integration tests for the alert processing pipeline.

Test Organization:
- test_models.py: Pydantic model validation and conversion
- test_sources.py: Alert source implementations
- test_storage.py: SQLite storage backend
- test_ingest.py: Ingestion pipeline integration
- test_filter.py: Filter engine tests
- test_processing.py: Post-processor framework

Fixtures are in tests/fixtures/:
- factories.py: AlertFactory for generating test data
- avro_samples.py: Sample AVRO records

Run tests:
    $ make test          # Quick test run
    $ make test-cov      # With coverage
    $ pdm run pytest tests/ -v
"""

from pathlib import Path

__version__ = "2.0.0"


def get_test_data_dir() -> Path:
    """Get path to test data directory."""
    return Path(__file__).parent / "test_data"


def get_mock_alert() -> dict:
    """
    Create a mock LSST alert for testing.

    Returns a mock alert packet with DIASource, SSObject, and cutouts
    that matches the LSST alert schema.

    Returns:
        dict: Mock alert packet
    """
    return {
        "alertId": 123456789,
        "diaSource": {
            "diaSourceId": 987654321,
            "diaObjectId": 111222333,
            "ra": 180.0,
            "decl": 45.0,
            "midPointTai": 59945.123456,
            "filterName": "g",
            "psFlux": 1000.5,
            "psFluxErr": 10.2,
            "snr": 98.1,
            "extendednessMedian": 0.85,
            "extendednessMin": 0.80,
            "extendednessMax": 0.90,
            "trailLength": 15.5,
            "trailAngle": 45.2,
            "pixelFlagsBad": False,
            "pixelFlagsCr": True,
            "pixelFlagsEdge": False,
        },
        "ssObject": {
            "ssObjectId": "SSO123456",
            "ssObjectReassocTimeMjdTai": 59945.120000,
        },
        "cutoutScience": b"\x00" * 100,  # Mock FITS data
        "cutoutTemplate": b"\x00" * 100,
        "cutoutDifference": b"\x00" * 100,
    }


def get_mock_alert_no_sso() -> dict:
    """
    Create a mock alert without SSObject association.

    Returns:
        dict: Mock alert without SSObject
    """
    alert = get_mock_alert()
    alert["ssObject"] = None
    return alert


def get_mock_alert_extended() -> dict:
    """
    Create a mock alert for an extended source (galaxy).

    Returns:
        dict: Mock alert with high extendedness values
    """
    alert = get_mock_alert()
    alert["alertId"] = 123456790
    alert["diaSource"]["diaSourceId"] = 987654322
    alert["diaSource"]["extendednessMedian"] = 0.92
    alert["diaSource"]["extendednessMin"] = 0.88
    alert["diaSource"]["extendednessMax"] = 0.96
    alert["diaSource"]["snr"] = 25.0  # Lower SNR typical for galaxies
    alert["ssObject"] = None
    return alert


def get_mock_alert_point_source() -> dict:
    """
    Create a mock alert for a point source (star).

    Returns:
        dict: Mock alert with low extendedness values
    """
    alert = get_mock_alert()
    alert["alertId"] = 123456791
    alert["diaSource"]["diaSourceId"] = 987654323
    alert["diaSource"]["extendednessMedian"] = 0.08
    alert["diaSource"]["extendednessMin"] = 0.05
    alert["diaSource"]["extendednessMax"] = 0.12
    alert["diaSource"]["snr"] = 150.0  # High SNR typical for stars
    alert["diaSource"]["trailLength"] = 0.0
    alert["diaSource"]["trailAngle"] = 0.0
    alert["ssObject"] = None
    return alert


def get_mock_alert_with_trail() -> dict:
    """
    Create a mock alert with a significant trail (potential asteroid).

    Returns:
        dict: Mock alert with trail data
    """
    alert = get_mock_alert()
    alert["alertId"] = 123456792
    alert["diaSource"]["diaSourceId"] = 987654324
    alert["diaSource"]["extendednessMedian"] = 0.55
    alert["diaSource"]["extendednessMin"] = 0.45
    alert["diaSource"]["extendednessMax"] = 0.65
    alert["diaSource"]["trailLength"] = 25.3
    alert["diaSource"]["trailAngle"] = 78.5
    alert["diaSource"]["trailWidth"] = 3.2
    alert["ssObject"] = {
        "ssObjectId": "SSO_ASTEROID_001",
        "ssObjectReassocTimeMjdTai": 59945.123000,
    }
    return alert


__all__ = [
    "get_mock_alert",
    "get_mock_alert_extended",
    "get_mock_alert_no_sso",
    "get_mock_alert_point_source",
    "get_mock_alert_with_trail",
    "get_test_data_dir",
]
