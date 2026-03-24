# Exporting to Pumalink

[Pumalink (PUMA)](https://github.com/atlas-ifa/puma) is a tracklet-linking tool
for solar system object detection. It ingests astrometric detections in **TRD9**
format: nine whitespace-delimited fields per detection line.

## TRD9 Format

```
MJD  RA  Dec  xerr  terr  lng  lat  elev  ID
```

| Field  | Unit       | Description                                       |
|--------|------------|---------------------------------------------------|
| `MJD`  | days       | Modified Julian Date at exposure midpoint         |
| `RA`   | degrees    | Right ascension, J2000 apparent                   |
| `Dec`  | degrees    | Declination, J2000 apparent                       |
| `xerr` | arcseconds | Cross-track astrometric 1-sigma error             |
| `terr` | arcseconds | Along-track astrometric 1-sigma error             |
| `lng`  | degrees    | Observatory longitude, WGS84 east-positive        |
| `lat`  | degrees    | Observatory geodetic latitude, WGS84              |
| `elev` | metres     | Observatory elevation above WGS84 ellipsoid       |
| `ID`   | string     | Unique detection identifier (≤31 chars, no spaces or commas) |

## Observatory Data

Observatory positions are loaded from a local copy of the
[MPC ObsCodes file](https://www.minorplanetcenter.net/iau/lists/ObsCodes.html).
The default path is `data/ObsCodes.dat`, kept current by `scripts/update_obscodes.sh`
(see [Systemd Timers](../deployment/systemd.md) for automated daily updates).

Both the plain-text (`.dat`) and HTML (`.html`) variants from MPC are accepted.

## Input Formats

| Flag       | Format                                                   | Observatory |
|------------|----------------------------------------------------------|-------------|
| `--db`     | Pipeline SQLite database (`alerts_raw` table)            | `--observatory CODE` required |
| `--csv`    | Pipeline CSV export                                      | `--observatory CODE` required |
| `--mpc80`  | MPC 80-column optical observation file                   | Per-observation from ObsCodes |
| `--ades`   | ADES PSV (pipe-separated values) file                    | Per-observation from ObsCodes |

## Prerequisites

Download or update the MPC ObsCodes file:

```bash
# Download once manually
python scripts/export_to_pumalink.py --download-obscodes data/ObsCodes.dat

# Or run the update script (also checks for changes)
bash scripts/update_obscodes.sh
```

The `update_obscodes.sh` script runs automatically every day via
[systemd timer](../deployment/systemd.md) or the cron job in `bin/run_lsst_consumer.sh`.

## Usage Examples

### From the pipeline SQLite database

```bash
# All alerts, Rubin Observatory (X05)
python scripts/export_to_pumalink.py \
    --db data/alerts.db \
    --observatory X05 \
    -o detections.trd

# SSO-associated alerts only, custom MJD window
python scripts/export_to_pumalink.py \
    --db data/alerts.db \
    --observatory X05 \
    --sso-only \
    --mjd-min 60500.0 --mjd-max 60510.0 \
    -o detections.trd
```

### From a pipeline CSV export

```bash
python scripts/export_to_pumalink.py \
    --csv data/lsst_alerts_20260210.csv \
    --observatory X05 \
    -o detections.trd
```

### From an MPC 80-column file

```bash
python scripts/export_to_pumalink.py \
    --mpc80 observations.mpc \
    -o detections.trd
```

### From an ADES PSV file

```bash
python scripts/export_to_pumalink.py \
    --ades observations.psv \
    -o detections.trd
```

### Override PSF FWHM (for non-LSST observatories)

```bash
# ZTF at 2.0 arcsec FWHM, Palomar (I41)
python scripts/export_to_pumalink.py \
    --db data/alerts.db \
    --observatory I41 \
    --psf-fwhm 2.0 \
    -o detections.trd
```

### List available observatories

```bash
python scripts/export_to_pumalink.py --list-observatories
```

## Astrometric Error Estimation

**Cross-track error (`xerr`):**

- SQLite / CSV with SNR: `xerr = PSF_FWHM / SNR`
- MPC80 (no SNR): `xerr = DEFAULT_XERR` (0.2 arcsec; override with `--default-xerr`)
- ADES PSV with `rmsRA` / `rmsDec`: taken directly from those columns
- Fallback: `DEFAULT_XERR = 0.2 arcsec`

**Along-track error (`terr`):**

For non-trailed detections `terr = xerr`. For trailed detections (trail length
available in SQLite `trail_data`):

```
major_axis = sqrt(psf_fwhm^2 + trail_length^2)
terr = xerr x sqrt(major_axis / psf_fwhm)
```

## CLI Reference

```
usage: export_to_pumalink.py [-h]
    [--db PATH | --csv PATH | --mpc80 PATH | --ades PATH]
    [-o PATH]
    [--obscode-file PATH] [--download-obscodes PATH]
    [--observatory CODE] [--list-observatories]
    [--psf-fwhm ARCSEC] [--default-xerr ARCSEC]
    [--sso-only] [--filtered-only]
    [--mjd-min MJD] [--mjd-max MJD]
```

| Flag                     | Description                                                   |
|--------------------------|---------------------------------------------------------------|
| `--db PATH`              | SQLite database (pipeline format)                             |
| `--csv PATH`             | Pipeline CSV export                                           |
| `--mpc80 PATH`           | MPC 80-column observation file                                |
| `--ades PATH`            | ADES PSV observation file                                     |
| `-o PATH`                | Output `.trd` file path                                       |
| `--obscode-file PATH`    | Local MPC ObsCodes file (default: `data/ObsCodes.dat`)        |
| `--download-obscodes PATH` | Download ObsCodes to path and exit                          |
| `--observatory CODE`     | MPC 3-char code for `--db` / `--csv` inputs                  |
| `--list-observatories`   | Print all loaded observatories and exit                       |
| `--psf-fwhm ARCSEC`      | PSF FWHM for error estimation (default: 1.0)                  |
| `--default-xerr ARCSEC`  | Fallback positional error (default: 0.2)                      |
| `--sso-only`             | Include only SSO-associated alerts (`--db` / `--csv`)         |
| `--filtered-only`        | Include only alerts in `alerts_filtered` table (`--db`)       |
| `--mjd-min MJD`          | Exclude observations before this MJD                          |
| `--mjd-max MJD`          | Exclude observations after this MJD                           |
