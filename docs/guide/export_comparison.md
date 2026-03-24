# Export Format Comparison

Side-by-side overview of the two export scripts for tracklet-linking tools.

## At a Glance

| Property | Pumalink (TRD9) | THOR (InputObservations) |
|----------|-----------------|--------------------------|
| Script | `scripts/export_to_pumalink.py` | `scripts/export_to_thor.py` |
| Output format | Whitespace-delimited text (`.trd`) | Parquet or CSV |
| Uncertainty units | arcseconds | degrees |
| Observatory handling | WGS84 coords looked up from MPC ObsCodes | 3-char code passed through |
| ObsCodes file required | Yes (for `--db` / `--csv` / `--mpc80`) | No |
| Magnitude support | No | Yes (`mag`, `mag_sigma`, `filter`) |
| Trailed detection handling | Enlarged `terr` along-track | Enlarged `dec_sigma` |
| Default output file | stdout / `-o` path | `thor_observations.parquet` |
| Output flag | `-o PATH` | `-o PATH` + `--format {parquet,csv}` |

## Input Format Support

| Flag | Pumalink | THOR |
|------|----------|------|
| `--db` | SQLite pipeline database | SQLite pipeline database |
| `--csv` | Pipeline CSV export | Pipeline CSV export |
| `--mpc80` | MPC 80-column file | MPC 80-column file |
| `--ades` | ADES PSV file | ADES PSV file |

## Uncertainty Estimation

| Source | Pumalink `xerr` | THOR `ra_sigma` / `dec_sigma` |
|--------|-----------------|-------------------------------|
| SQLite / CSV with SNR | `psf_fwhm / snr` (arcsec) | `psf_fwhm / (snr × 3600)` (deg) |
| MPC80 (no SNR) | `--default-xerr` (default 0.2 arcsec) | `--default-sigma` (default 0.2 arcsec → converted to deg) |
| ADES PSV with `rmsRA` | Taken directly (arcsec) | `rmsRA / 3600` (deg) |
| Trailed detection | `terr = xerr × sqrt(major_axis / psf_fwhm)` | `dec_sigma = ra_sigma × sqrt(sqrt(psf_fwhm² + L²) / psf_fwhm)` |

## Shared CLI Flags

Both scripts accept these flags:

| Flag | Description |
|------|-------------|
| `--db PATH` | Pipeline SQLite database |
| `--csv PATH` | Pipeline CSV export |
| `--mpc80 PATH` | MPC 80-column observation file |
| `--ades PATH` | ADES PSV observation file |
| `--observatory CODE` | MPC 3-char code (required for `--db` / `--csv`) |
| `--psf-fwhm ARCSEC` | PSF FWHM for SNR-based uncertainty (default: 1.0) |
| `--sso-only` | Include only SSO-associated alerts |
| `--filtered-only` | Include only alerts in `alerts_filtered` table |
| `--mjd-min MJD` | Exclude observations before this MJD |
| `--mjd-max MJD` | Exclude observations after this MJD |

## Pumalink-Only Flags

| Flag | Description |
|------|-------------|
| `--obscode-file PATH` | Local MPC ObsCodes file (default: `data/ObsCodes.dat`) |
| `--download-obscodes PATH` | Download ObsCodes to path and exit |
| `--list-observatories` | Print all loaded observatories and exit |
| `--default-xerr ARCSEC` | Fallback cross-track error (default: 0.2) |

## THOR-Only Flags

| Flag | Description |
|------|-------------|
| `--format {parquet,csv}` | Output format (default: `parquet`) |
| `--default-sigma ARCSEC` | Fallback positional uncertainty (default: 0.2) |
| `--default-filter FILTER` | Filter name when unavailable in source data (default: `r`) |

## When to Use Which

- **Pumalink**: when running [PUMA](https://github.com/atlas-ifa/puma) for tracklet linking; requires a local MPC ObsCodes file for WGS84 observatory positions.
- **THOR**: when running [THOR](https://github.com/moeyensj/thor) for tracklet-less heliocentric orbit recovery; outputs a structured Parquet file loadable directly as `adam_core` `InputObservations`.
