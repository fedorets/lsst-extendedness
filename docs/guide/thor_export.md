# Exporting to THOR

[THOR (Tracklet-less Heliocentric Orbit Recovery)](https://github.com/moeyensj/thor)
links solar system object detections across multiple nights without requiring
pre-formed tracklets. It accepts observations as `InputObservations`, a
table defined in the [adam_core](https://github.com/B612-Asteroid-Institute/adam_core)
library.

## Output Schema

The script writes a Parquet or CSV file with these columns:

| Column | Type | Description |
|--------|------|-------------|
| `id` | string | Unique observation identifier |
| `exposure_id` | string | Exposure identifier (defaults to `id` when unavailable) |
| `mjd_utc` | float64 | Observation time, MJD in UTC |
| `night` | Int64 | Observing night integer (`floor(mjd_utc - 0.5)`) |
| `ra` | float64 | Right ascension, J2000 apparent (degrees) |
| `dec` | float64 | Declination, J2000 apparent (degrees) |
| `ra_sigma` | float64 | RA positional 1-sigma uncertainty, east-west direction (degrees) |
| `dec_sigma` | float64 | Dec positional 1-sigma uncertainty, north-south direction (degrees) |
| `ra_dec_cov` | float64 | RA-Dec covariance (degrees²); NaN when unknown |
| `mag` | float64 | Apparent magnitude; NaN when unavailable |
| `mag_sigma` | float64 | Magnitude 1-sigma uncertainty; NaN when unavailable |
| `filter` | string | Photometric filter (e.g. `r`, `g`, `i`) |
| `observatory_code` | string | MPC 3-character observatory code |

!!! note "Uncertainty units"
    `ra_sigma` and `dec_sigma` are in **degrees**, consistent with THOR's
    `InputObservations` and the ADES `rmsRA`/`rmsDec` convention
    (east-west and north-south sky-plane uncertainties, already including the
    cos(dec) projection). Values derived from SNR are converted from arcseconds
    by dividing by 3600.

## Observing Night Convention

`night` uses the convention `floor(mjd_utc − 0.5)`, which rolls over at
noon UTC. Observations taken before and after midnight in the same astronomical
night therefore share the same `night` value.

## Input Formats

| Flag | Format | Observatory source | Magnitude |
|------|--------|--------------------|-----------|
| `--db` | Pipeline SQLite (`alerts_raw`) | `--observatory CODE` required | `psf_mag` column if present |
| `--csv` | Pipeline CSV export | `--observatory CODE` required | `psf_mag` column if present |
| `--mpc80` | MPC 80-column optical file | Embedded per observation (col 78-80) | Cols 66-70 / band col 71 |
| `--ades` | ADES PSV file | `stn` column | `mag` / `band` columns |

For `--mpc80` and `--ades`, observatory codes are passed through directly to
THOR — no coordinate lookup is performed. THOR resolves observer positions
internally using its own ephemeris data.

## Loading into THOR

```python
import pyarrow.parquet as pq
from adam_core.time import Timestamp
from thor.observations import InputObservations

table = pq.read_table("observations.parquet")

# Convert plain MJD float column to adam_core Timestamp
time = Timestamp.from_mjd(table.column("mjd_utc").to_pylist(), scale="utc")

obs = InputObservations.from_kwargs(
    id=table.column("id"),
    exposure_id=table.column("exposure_id"),
    time=time,
    ra=table.column("ra"),
    dec=table.column("dec"),
    ra_sigma=table.column("ra_sigma"),
    dec_sigma=table.column("dec_sigma"),
    ra_dec_cov=table.column("ra_dec_cov"),
    mag=table.column("mag"),
    mag_sigma=table.column("mag_sigma"),
    filter=table.column("filter"),
    observatory_code=table.column("observatory_code"),
)
```

## Usage Examples

### From the pipeline SQLite database

```bash
# All alerts, Rubin Observatory (X05)
python scripts/export_to_thor.py \
    --db data/alerts.db \
    --observatory X05 \
    -o observations.parquet

# SSO-associated alerts only, custom MJD window
python scripts/export_to_thor.py \
    --db data/alerts.db \
    --observatory X05 \
    --sso-only \
    --mjd-min 60500.0 --mjd-max 60510.0 \
    -o observations.parquet
```

### From a pipeline CSV export

```bash
python scripts/export_to_thor.py \
    --csv data/alerts_20260210.csv \
    --observatory X05 \
    -o observations.parquet
```

### From an MPC 80-column file

```bash
python scripts/export_to_thor.py \
    --mpc80 observations.mpc \
    -o observations.parquet
```

### From an ADES PSV file

```bash
python scripts/export_to_thor.py \
    --ades observations.psv \
    -o observations.parquet
```

### Output as CSV

```bash
python scripts/export_to_thor.py \
    --db data/alerts.db --observatory X05 \
    --format csv -o observations.csv
```

### Override PSF FWHM (non-LSST observatories)

```bash
# ZTF at 2.0 arcsec FWHM, Palomar (I41)
python scripts/export_to_thor.py \
    --db data/alerts.db \
    --observatory I41 \
    --psf-fwhm 2.0 \
    -o observations.parquet
```

## Astrometric Uncertainty Estimation

**`ra_sigma`** (RA positional uncertainty in degrees):

- SQLite / CSV with SNR: `ra_sigma = psf_fwhm / (snr × 3600)`
- MPC80 (no SNR): `ra_sigma = DEFAULT_POS_SIGMA_DEG` (override with `--default-sigma`)
- ADES PSV with `rmsRA`: `ra_sigma = rmsRA / 3600`
- Fallback: `DEFAULT_POS_SIGMA_DEG = 0.2 / 3600 ≈ 5.6 × 10⁻⁵ deg`

**`dec_sigma`** (Dec positional uncertainty in degrees):

Equal to `ra_sigma` for non-trailed detections. For trailed detections
(SQLite `trail_data.trailLength` present), the effective PSF is elongated:

```
dec_sigma = ra_sigma × sqrt(sqrt(psf_fwhm² + trail_length²) / psf_fwhm)
```

For ADES PSV: taken directly from `rmsDec / 3600` when available.

## CLI Reference

```
usage: export_to_thor.py [-h]
    [--db PATH | --csv PATH | --mpc80 PATH | --ades PATH]
    [-o PATH] [--format {parquet,csv}]
    [--observatory CODE]
    [--psf-fwhm ARCSEC] [--default-sigma ARCSEC]
    [--sso-only] [--filtered-only]
    [--mjd-min MJD] [--mjd-max MJD]
    [--default-filter FILTER]
```

| Flag | Description |
|------|-------------|
| `--db PATH` | Pipeline SQLite database |
| `--csv PATH` | Pipeline CSV export |
| `--mpc80 PATH` | MPC 80-column observation file |
| `--ades PATH` | ADES PSV observation file |
| `-o PATH` | Output file path (default: `thor_observations.parquet`) |
| `--format {parquet,csv}` | Output format (default: `parquet`) |
| `--observatory CODE` | MPC 3-char code for `--db` / `--csv` inputs |
| `--psf-fwhm ARCSEC` | PSF FWHM for SNR-based uncertainty (default: 1.0) |
| `--default-sigma ARCSEC` | Fallback positional uncertainty in arcseconds (default: 0.2) |
| `--sso-only` | Include only SSO-associated alerts (`--db` / `--csv`) |
| `--filtered-only` | Include only alerts in `alerts_filtered` table (`--db`) |
| `--mjd-min MJD` | Exclude observations before this MJD |
| `--mjd-max MJD` | Exclude observations after this MJD |
| `--default-filter FILTER` | Filter name when unavailable in source data (default: `r`) |

See [Export Format Comparison](export_comparison.md) for a side-by-side overview of the Pumalink and THOR export scripts.
