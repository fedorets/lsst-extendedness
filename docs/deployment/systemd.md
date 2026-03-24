# Systemd Timers

Automated daily ingestion and processing using systemd timers.

## Installation

```bash
# Install timer units
make timer-install

# Or manually
sudo cp systemd/*.service systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lsst-update-obscodes.timer
sudo systemctl enable --now lsst-ingest.timer
sudo systemctl enable --now lsst-process.timer
```

## Service Units

### lsst-update-obscodes.service

Downloads the MPC observatory codes file (`data/ObsCodes.dat`) and replaces
it only if the content has changed (SHA-256 comparison). Runs daily at 01:00,
one hour before ingestion, so the Pumalink export always uses current data.

```ini
[Unit]
Description=LSST Extendedness Pipeline - Update MPC ObsCodes
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=%h/lsst-extendedness
ExecStart=/bin/bash %h/lsst-extendedness/scripts/update_obscodes.sh
StandardOutput=journal
StandardError=journal
SyslogIdentifier=lsst-update-obscodes
TimeoutStartSec=120

[Install]
WantedBy=default.target
```

Timer: runs daily at 01:00 (`lsst-update-obscodes.timer`).

Logs: `logs/obscodes/obscodes_YYYYMMDD.log`

Also called by `bin/run_lsst_consumer.sh` at the start of each cron run,
so the file stays current regardless of which scheduling method is used.

---

### lsst-ingest.service

Runs daily ingestion from configured source.

```ini
[Unit]
Description=LSST Extendedness Alert Ingestion
After=network-online.target

[Service]
Type=oneshot
User=lsst
WorkingDirectory=/opt/lsst-extendedness
ExecStart=/opt/lsst-extendedness/.venv/bin/lsst-extendedness ingest
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### lsst-process.service

Runs post-processing on accumulated alerts.

```ini
[Unit]
Description=LSST Extendedness Post-Processing
After=network-online.target

[Service]
Type=oneshot
User=lsst
WorkingDirectory=/opt/lsst-extendedness
ExecStart=/opt/lsst-extendedness/.venv/bin/lsst-extendedness process --window 15
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## Timer Units

### lsst-ingest.timer

Runs ingestion daily at 2 AM.

```ini
[Unit]
Description=Daily LSST Alert Ingestion

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
```

### lsst-process.timer

Runs processing daily at 4 AM.

```ini
[Unit]
Description=Daily LSST Post-Processing

[Timer]
OnCalendar=*-*-* 04:00:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
```

## Management Commands

```bash
# Check timer status
make timer-status
# or
systemctl list-timers lsst-*

# View logs
make timer-logs
# or
journalctl -u lsst-ingest -u lsst-process -f

# Manual run
sudo systemctl start lsst-ingest.service

# Disable timers
make timer-uninstall
```

## Monitoring

### Check Last Run

```bash
systemctl status lsst-ingest.service
systemctl status lsst-process.service
```

### View Statistics

```bash
lsst-extendedness db-stats
```

### Log Analysis

```bash
# Recent errors
journalctl -u lsst-ingest --since "1 day ago" -p err

# Full log for last run
journalctl -u lsst-ingest -n 100 --no-pager
```
