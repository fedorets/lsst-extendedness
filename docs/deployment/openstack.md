# OpenStack VM Deployment

Deploy the LSST Extendedness Pipeline to an OpenStack VM.

## VM Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| vCPUs | 2 | 4 |
| RAM | 4 GB | 8 GB |
| Disk | 100 GB | 500 GB |
| OS | Ubuntu 22.04 | Ubuntu 24.04 |

!!! note "Storage Sizing"
    Plan ~80 GB for the SQLite database plus ~20 GB per month for FITS cutouts.

## Cloud-Init Script

Use this cloud-init script when launching the VM:

```yaml
#cloud-config
package_update: true
package_upgrade: true

packages:
  - python3.12
  - python3.12-venv
  - python3.12-dev
  - librdkafka-dev
  - libopenblas-dev
  - git
  - htop
  - tmux

users:
  - name: lsst
    groups: sudo
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL

write_files:
  - path: /opt/lsst-extendedness/setup.sh
    permissions: '0755'
    content: |
      #!/bin/bash
      set -e
      cd /opt/lsst-extendedness

      # Install PDM
      pip install pdm

      # Install dependencies
      pdm config venv.in_project true
      pdm install

      # Initialize database
      pdm run lsst-extendedness db-init

      # Install systemd timers
      sudo cp systemd/*.service systemd/*.timer /etc/systemd/system/
      sudo systemctl daemon-reload
      sudo systemctl enable lsst-ingest.timer lsst-process.timer
      sudo systemctl start lsst-ingest.timer lsst-process.timer

      echo "Setup complete!"

runcmd:
  - git clone https://github.com/westover/lsst-extendedness.git /opt/lsst-extendedness
  - chown -R lsst:lsst /opt/lsst-extendedness
  - su - lsst -c "/opt/lsst-extendedness/setup.sh"
```

## Manual Installation

### 1. Create VM

```bash
# Using OpenStack CLI
openstack server create \
  --flavor m1.medium \
  --image ubuntu-24.04 \
  --network private \
  --key-name my-key \
  --security-group default \
  lsst-extendedness
```

### 2. SSH and Install

```bash
ssh ubuntu@<vm-ip>

# Install system dependencies
sudo apt-get update
sudo apt-get install -y \
  python3.12 python3.12-venv python3.12-dev \
  librdkafka-dev libopenblas-dev git

# Clone repository
sudo mkdir -p /opt/lsst-extendedness
sudo chown $USER:$USER /opt/lsst-extendedness
git clone https://github.com/westover/lsst-extendedness.git /opt/lsst-extendedness

# Run bootstrap
cd /opt/lsst-extendedness
./scripts/bootstrap.sh
```

### 3. Configure ANTARES Credentials

```bash
# Create environment file
sudo tee /opt/lsst-extendedness/.env << EOF
ANTARES_API_KEY=your-api-key
ANTARES_API_SECRET=your-api-secret
EOF

sudo chmod 600 /opt/lsst-extendedness/.env
```

### 4. Install Systemd Timers

```bash
cd /opt/lsst-extendedness
make timer-install
```

## Persistent Storage

### Attach Volume

```bash
# Create volume
openstack volume create --size 500 lsst-data

# Attach to VM
openstack server add volume lsst-extendedness lsst-data

# On the VM, format and mount
sudo mkfs.ext4 /dev/vdb
sudo mkdir -p /data
sudo mount /dev/vdb /data

# Add to fstab
echo '/dev/vdb /data ext4 defaults 0 2' | sudo tee -a /etc/fstab

# Link data directory
ln -s /data /opt/lsst-extendedness/data
```

## Firewall Rules

Minimal ports needed:

| Port | Protocol | Purpose |
|------|----------|---------|
| 22 | TCP | SSH access |
| 9092 | TCP | Kafka (outbound only) |

```bash
# Security group (outbound Kafka)
openstack security group rule create \
  --protocol tcp \
  --dst-port 9092 \
  --egress \
  default
```

## Monitoring

### Health Check Script

```bash
#!/bin/bash
# /opt/lsst-extendedness/healthcheck.sh

cd /opt/lsst-extendedness

# Check database
if pdm run lsst-extendedness db-stats > /dev/null 2>&1; then
    echo "Database: OK"
else
    echo "Database: FAIL"
    exit 1
fi

# Check timers
if systemctl is-active lsst-ingest.timer > /dev/null; then
    echo "Ingest Timer: OK"
else
    echo "Ingest Timer: FAIL"
    exit 1
fi

# Check disk space
USAGE=$(df /data | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$USAGE" -lt 90 ]; then
    echo "Disk: OK ($USAGE% used)"
else
    echo "Disk: WARNING ($USAGE% used)"
fi

echo "All checks passed"
```

### Cron for Alerts

```bash
# Add to crontab
0 6 * * * /opt/lsst-extendedness/healthcheck.sh | mail -s "LSST Health Check" admin@example.com
```

## Backup Strategy

### Daily Database Backup

```bash
#!/bin/bash
# /opt/lsst-extendedness/backup.sh

DATE=$(date +%Y%m%d)
BACKUP_DIR=/data/backups

mkdir -p $BACKUP_DIR

# Backup database
sqlite3 /opt/lsst-extendedness/data/lsst_extendedness.db ".backup '$BACKUP_DIR/lsst_$DATE.db'"

# Compress
gzip $BACKUP_DIR/lsst_$DATE.db

# Keep 30 days
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete

# Optional: Upload to object storage
# openstack object create backups $BACKUP_DIR/lsst_$DATE.db.gz
```

Add to crontab:
```bash
0 5 * * * /opt/lsst-extendedness/backup.sh
```

## Troubleshooting

### Check Service Logs

```bash
journalctl -u lsst-ingest -f
journalctl -u lsst-process -f
```

### Database Issues

```bash
# Check database integrity
sqlite3 /opt/lsst-extendedness/data/lsst_extendedness.db "PRAGMA integrity_check"

# Vacuum to reclaim space
sqlite3 /opt/lsst-extendedness/data/lsst_extendedness.db "VACUUM"
```

### Network Issues

```bash
# Test Kafka connectivity
nc -zv kafka.antares.noirlab.edu 9092

# Test ANTARES API
curl -I https://api.antares.noirlab.edu/v1/
```
