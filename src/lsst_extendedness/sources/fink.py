"""
Fink broker source for the LSST Extendedness Pipeline.

This module provides a FinkSource that loads alerts from Fink broker data,
either from local fixture files or from the public Fink REST API.

Fink is one of the seven community brokers selected to receive the full
LSST alert stream. Currently it processes ZTF alerts, which have a similar
structure to expected LSST alerts.

Example:
    >>> from lsst_extendedness.sources import FinkSource
    >>>
    >>> # Load from fixtures (default, no network required)
    >>> source = FinkSource()
    >>> source.connect()
    >>> for alert in source.fetch_alerts(limit=10):
    ...     print(f"Alert {alert.alert_id} at RA={alert.ra}")
    >>> source.close()

See Also:
    - Fink Science Portal: https://fink-portal.org
    - Fink API: https://api.fink-portal.org
    - Fink Documentation: https://fink-broker.readthedocs.io
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from lsst_extendedness.models.alerts import AlertRecord
from lsst_extendedness.sources.protocol import register_source

logger = logging.getLogger(__name__)

# ZTF filter mapping
ZTF_FILTERS = {1: "g", 2: "r", 3: "i"}

# Default fixtures path
FIXTURES_DIR = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "fink"


def _jd_to_mjd(jd: float) -> float:
    """Convert Julian Date to Modified Julian Date."""
    return jd - 2400000.5


def _mag_to_flux(mag: float, mag_err: float | None = None) -> tuple[float, float | None]:
    """Convert magnitude to flux (arbitrary units).

    Uses the formula: flux = 10^(-0.4 * mag)
    """
    import math

    flux = math.pow(10, -0.4 * mag)
    flux_err = None
    if mag_err is not None and mag_err > 0:
        # Error propagation: d(flux)/d(mag) = -0.4 * ln(10) * flux
        flux_err = 0.4 * math.log(10) * flux * mag_err
    return flux, flux_err


def _object_id_to_int(object_id: str) -> int:
    """Convert ZTF object ID string to integer hash."""
    # Use first 15 digits of MD5 hash to get a stable integer
    hash_hex = hashlib.md5(object_id.encode()).hexdigest()[:15]
    return int(hash_hex, 16)


@register_source("fink")
class FinkSource:
    """Fink broker source for ZTF/LSST-like alerts.

    Loads alerts from Fink broker data. By default, uses local fixture
    files for reproducible testing. Can optionally fetch live data from
    the Fink public API.

    The Fink data structure maps to LSST alerts as follows:
    - i:candid → alert_id
    - i:objectId → dia_object_id (hashed to int)
    - i:ra, i:dec → coordinates
    - i:jd → mjd (converted)
    - i:fid → filter_name (1=g, 2=r, 3=i)
    - i:classtar → extendedness (inverted: 1-classtar)
    - d:roid → has_ss_source (>0 means SSO)
    - i:ssnamenr → ss_object_id

    Attributes:
        source_name: Always "fink"
        use_fixtures: If True, load from local fixtures (default)
        fixtures_dir: Path to fixture files
        include_sso: If True, also load SSO alerts from fixtures

    Example:
        >>> source = FinkSource()
        >>> source.connect()
        >>> alerts = list(source.fetch_alerts(limit=5))
        >>> print(f"Got {len(alerts)} alerts")
        >>> source.close()
    """

    source_name = "fink"

    def __init__(
        self,
        *,
        use_fixtures: bool = True,
        fixtures_dir: Path | str | None = None,
        include_sso: bool = True,
    ):
        """Initialize Fink source.

        Args:
            use_fixtures: If True, load from local fixture files (default).
                This is recommended for testing as it's reproducible and
                doesn't require network access.
            fixtures_dir: Path to fixture files. Defaults to
                tests/fixtures/fink/ in the package directory.
            include_sso: If True, also load SSO (Solar System Object)
                alerts from fixtures. Default is True.
        """
        self.use_fixtures = use_fixtures
        self.fixtures_dir = Path(fixtures_dir) if fixtures_dir else FIXTURES_DIR
        self.include_sso = include_sso

        self._alerts: list[dict[str, Any]] = []
        self._connected = False
        self._index = 0

    def connect(self) -> None:
        """Load alerts from fixtures or API.

        Raises:
            FileNotFoundError: If fixtures are requested but not found.
            ConnectionError: If API fetch fails.
        """
        if self.use_fixtures:
            self._load_fixtures()
        else:
            raise NotImplementedError("Live API fetch not yet implemented. Use fixtures for now.")

        self._connected = True
        self._index = 0
        logger.info(
            f"Connected to Fink source with {len(self._alerts)} alerts",
            extra={"source": "fink", "alert_count": len(self._alerts)},
        )

    def _load_fixtures(self) -> None:
        """Load alerts from fixture files."""
        self._alerts = []

        # Load object alerts
        objects_file = self.fixtures_dir / "objects.json"
        if objects_file.exists():
            with open(objects_file) as f:
                self._alerts.extend(json.load(f))
            logger.debug(f"Loaded {len(self._alerts)} object alerts from fixtures")
        else:
            logger.warning(f"Objects fixture not found: {objects_file}")

        # Load SSO alerts
        if self.include_sso:
            sso_file = self.fixtures_dir / "sso.json"
            if sso_file.exists():
                with open(sso_file) as f:
                    sso_alerts = json.load(f)
                    self._alerts.extend(sso_alerts)
                logger.debug(f"Loaded {len(sso_alerts)} SSO alerts from fixtures")

        if not self._alerts:
            raise FileNotFoundError(
                f"No fixture files found in {self.fixtures_dir}. "
                "Run 'python scripts/download_fink_fixtures.py' to generate them."
            )

    def fetch_alerts(self, limit: int | None = None) -> Iterator[AlertRecord]:
        """Fetch and yield alerts as AlertRecord instances.

        Args:
            limit: Maximum number of alerts to yield (None = all).

        Yields:
            AlertRecord instances converted from Fink format.

        Raises:
            RuntimeError: If not connected.
        """
        if not self._connected:
            raise RuntimeError("Source not connected. Call connect() first.")

        count = 0
        for raw_alert in self._alerts:
            if limit is not None and count >= limit:
                break

            try:
                alert_record = self._convert_alert(raw_alert)
                if alert_record is not None:
                    count += 1
                    yield alert_record
            except Exception as e:
                logger.warning(
                    f"Error converting Fink alert: {e}",
                    extra={"error": str(e)},
                )
                continue

        logger.info(f"Fetched {count} alerts from Fink source")

    def _convert_alert(self, raw: dict[str, Any]) -> AlertRecord | None:
        """Convert a Fink alert to AlertRecord.

        Args:
            raw: Raw Fink alert dictionary.

        Returns:
            AlertRecord or None if conversion fails.
        """
        # Required fields
        candid = raw.get("i:candid")
        object_id = raw.get("i:objectId")
        ra = raw.get("i:ra")
        dec = raw.get("i:dec")
        jd = raw.get("i:jd")

        if not all([candid, object_id, ra is not None, dec is not None, jd]):
            logger.debug(f"Missing required fields in alert: {raw.get('i:objectId')}")
            return None

        # Type narrowing for mypy - these are guaranteed non-None after the check above
        candid_val = int(cast(int, candid))
        object_id_str = str(cast(str, object_id))
        ra_val = float(cast(float, ra))
        dec_val = float(cast(float, dec))
        jd_val = float(cast(float, jd))

        # Convert JD to MJD
        mjd = _jd_to_mjd(jd_val)

        # Filter name
        fid = raw.get("i:fid", 0)
        filter_name = ZTF_FILTERS.get(fid, "unknown")

        # Magnitude to flux
        magpsf = raw.get("i:magpsf")
        sigmapsf = raw.get("i:sigmapsf")
        ps_flux, ps_flux_err = None, None
        if magpsf is not None:
            ps_flux, ps_flux_err = _mag_to_flux(magpsf, sigmapsf)

        # SNR from magnitude error (rough approximation)
        snr = None
        if sigmapsf is not None and sigmapsf > 0:
            snr = 1.0 / sigmapsf  # Rough SNR approximation

        # Extendedness from classtar (star/galaxy classifier)
        # classtar = 1 means star-like, 0 means extended
        # We invert it so extendedness = 1 means extended
        classtar = raw.get("i:classtar")
        extendedness = None
        if classtar is not None:
            extendedness = 1.0 - classtar

        # Solar System Object detection
        roid = raw.get("d:roid", 0)
        has_ss_source = roid is not None and roid > 0
        ss_object_id = None
        ssnamenr = raw.get("i:ssnamenr")
        if ssnamenr is not None and ssnamenr != "null":
            ss_object_id = str(ssnamenr)
        # Also check sso_name field (present in SSO queries)
        if not ss_object_id:
            sso_name = raw.get("sso_name")
            if sso_name:
                ss_object_id = str(sso_name)

        # Build AlertRecord
        return AlertRecord(
            alert_id=candid_val,
            dia_source_id=candid_val,  # Use candid as source ID too
            dia_object_id=_object_id_to_int(object_id_str),
            ra=ra_val,
            dec=dec_val,
            mjd=mjd,
            filter_name=filter_name,
            ps_flux=ps_flux,
            ps_flux_err=ps_flux_err,
            snr=snr,
            extendedness_median=extendedness,
            extendedness_min=extendedness,  # ZTF only has one value
            extendedness_max=extendedness,
            has_ss_source=has_ss_source,
            ss_object_id=ss_object_id,
        )

    def close(self) -> None:
        """Close the source and release resources."""
        self._alerts = []
        self._connected = False
        self._index = 0

    def __enter__(self) -> FinkSource:
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def __repr__(self) -> str:
        """String representation."""
        return f"FinkSource(use_fixtures={self.use_fixtures}, alerts={len(self._alerts)})"
