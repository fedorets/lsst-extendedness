"""
LSST Alert Pipeline - Source Package
Main package for LSST alert processing components
"""

__version__ = "2.0.0"
__author__ = "LSST Alert Pipeline"

# Import main consumer class for easy access
from .lsst_alert_consumer import LSSTAlertConsumer

__all__ = ["LSSTAlertConsumer"]
