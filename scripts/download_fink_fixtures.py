#!/usr/bin/env python3
"""
Download test fixtures from Fink public API.

This script fetches real ZTF alert data from Fink's public REST API
and saves it as JSON fixtures for testing. Run this once to populate
the fixtures, then commit them to the repository.

The fixtures provide realistic astronomical data without requiring
network access during tests.

Usage:
    python scripts/download_fink_fixtures.py

Output:
    tests/fixtures/fink/
        objects.json      - Multiple alerts from known ZTF objects
        sso.json          - Solar System Object alerts
        metadata.json     - Info about when fixtures were generated
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime
from pathlib import Path

# Fink public API base URL
FINK_API = "https://api.fink-portal.org/api/v1"

# Output directory
FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "fink"

# Known ZTF objects to fetch (chosen for variety and stability)
KNOWN_OBJECTS = [
    "ZTF21aaxtctv",  # Transient
    "ZTF18aaqjovh",  # Known supernova candidate
    "ZTF19aarioci",  # Variable star
    "ZTF20acvfraq",  # Another transient
    "ZTF21abfmbix",  # Recent object
]

# Known Solar System Objects (asteroid numbers)
KNOWN_SSO = [
    "8467",  # Asteroid
    "1620",  # Asteroid (Geographos)
    "433",  # Asteroid (Eros)
]


def fetch_json(url: str) -> list[dict] | dict:
    """Fetch JSON from URL."""
    print(f"  Fetching: {url}")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "lsst-extendedness-fixtures/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def download_objects() -> list[dict]:
    """Download alerts for known objects."""
    all_alerts = []

    for obj_id in KNOWN_OBJECTS:
        url = f"{FINK_API}/objects?objectId={obj_id}&output-format=json"
        try:
            alerts = fetch_json(url)
            if isinstance(alerts, list) and alerts:
                # Take up to 5 alerts per object to keep fixtures small
                all_alerts.extend(alerts[:5])
                print(f"    Got {min(len(alerts), 5)} alerts for {obj_id}")
            else:
                print(f"    No alerts for {obj_id}")
        except Exception as e:
            print(f"    Error fetching {obj_id}: {e}")

    return all_alerts


def download_sso() -> list[dict]:
    """Download Solar System Object alerts."""
    all_sso = []

    for sso_id in KNOWN_SSO:
        url = f"{FINK_API}/sso?n_or_d={sso_id}&output-format=json"
        try:
            alerts = fetch_json(url)
            if isinstance(alerts, list) and alerts:
                # Take up to 5 alerts per SSO
                all_sso.extend(alerts[:5])
                print(f"    Got {min(len(alerts), 5)} alerts for SSO {sso_id}")
            else:
                print(f"    No alerts for SSO {sso_id}")
        except Exception as e:
            print(f"    Error fetching SSO {sso_id}: {e}")

    return all_sso


def main():
    """Download all fixtures."""
    print("Downloading Fink fixtures...")
    print(f"Output directory: {FIXTURES_DIR}")

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    # Download object alerts
    print("\n1. Downloading object alerts...")
    objects = download_objects()
    objects_file = FIXTURES_DIR / "objects.json"
    with open(objects_file, "w") as f:
        json.dump(objects, f, indent=2)
    print(f"   Saved {len(objects)} alerts to {objects_file.name}")

    # Download SSO alerts
    print("\n2. Downloading SSO alerts...")
    sso = download_sso()
    sso_file = FIXTURES_DIR / "sso.json"
    with open(sso_file, "w") as f:
        json.dump(sso, f, indent=2)
    print(f"   Saved {len(sso)} alerts to {sso_file.name}")

    # Write metadata
    metadata = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source": "Fink Public API (api.fink-portal.org)",
        "objects_queried": KNOWN_OBJECTS,
        "sso_queried": KNOWN_SSO,
        "total_object_alerts": len(objects),
        "total_sso_alerts": len(sso),
        "notes": [
            "These are real ZTF alerts from the Fink broker",
            "Data structure is similar to expected LSST alerts",
            "Regenerate with: python scripts/download_fink_fixtures.py",
        ],
    }
    metadata_file = FIXTURES_DIR / "metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"\n3. Saved metadata to {metadata_file.name}")

    print("\nDone! Fixtures ready for testing.")
    print(f"Total alerts: {len(objects) + len(sso)}")


if __name__ == "__main__":
    main()
