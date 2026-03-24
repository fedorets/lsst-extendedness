#!/bin/bash
#
# LSST Alert Pipeline - Environment Setup Script
# Run this once to set up the complete environment
#
# Usage: ./setup_environment.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Determine script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

log_info "======================================"
log_info "LSST Alert Pipeline - Setup"
log_info "======================================"
log_info "Base directory: $BASE_DIR"
log_info ""

# Check Python version
log_info "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    log_error "Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
log_info "Python version: $PYTHON_VERSION"

# Check if running in base directory
cd "$BASE_DIR"

# Create directory structure
log_info ""
log_info "Creating directory structure..."

directories=(
    "bin"
    "src"
    "src/utils"
    "config"
    "data/raw"
    "data/processed/csv"
    "data/processed/summary"
    "data/cutouts"
    "data/archive"
    "logs/consumer"
    "logs/cron"
    "logs/error"
    "logs/cleanup"
    "temp/partial_csvs"
    "temp/processing"
    "temp/failed"
    "scripts"
    "tests"
    "docs"
)

for dir in "${directories[@]}"; do
    mkdir -p "$dir"
    log_info "  Created: $dir"
done

# Create __init__.py files for Python packages
log_info ""
log_info "Creating Python package files..."
touch src/__init__.py
touch src/utils/__init__.py
touch tests/__init__.py
log_info "  Created __init__.py files"

# Create/update .gitignore
log_info ""
log_info "Creating .gitignore..."
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/

# IDE
.vscode/
.idea/
*.swp
*.swo

# Data files
data/raw/**/*.avro
data/processed/csv/**/*.csv
data/cutouts/**/*.fits
data/archive/**/*.tar.gz
temp/**/*

# Logs
logs/**/*.log

# Configuration (keep examples)
config/config.py
config/kafka_config.json

# OS
.DS_Store
Thumbs.db

# Temporary files
*.tmp
*.bak
*.pid
EOF
log_info "  Created .gitignore"

# Set up virtual environment (optional)
log_info ""
read -p "Create Python virtual environment? (recommended) [Y/n]: " create_venv
create_venv=${create_venv:-Y}

if [[ "$create_venv" =~ ^[Yy]$ ]]; then
    log_info "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    log_info "  Virtual environment created and activated"

    # Upgrade pip
    log_info "Upgrading pip..."
    pip install --upgrade pip

    # Install requirements if they exist
    if [ -f "requirements.txt" ]; then
        log_info "Installing Python dependencies..."
        pip install -r requirements.txt
        log_info "  Dependencies installed"
    else
        log_warn "requirements.txt not found. You'll need to install dependencies manually."
    fi
else
    log_warn "Skipping virtual environment creation"
fi

# Check for system dependencies
log_info ""
log_info "Checking system dependencies..."

# Check for librdkafka
if ldconfig -p | grep -q librdkafka; then
    log_info "  librdkafka: installed"
else
    log_warn "  librdkafka: NOT FOUND"
    log_info "  Install with:"
    log_info "    Ubuntu/Debian: sudo apt-get install librdkafka-dev"
    log_info "    CentOS/RHEL: sudo yum install librdkafka-devel"
    log_info "    macOS: brew install librdkafka"
fi

# Make scripts executable
log_info ""
log_info "Making scripts executable..."
chmod +x bin/*.sh 2>/dev/null || true
chmod +x scripts/*.sh 2>/dev/null || true
log_info "  Scripts are now executable"

# Create example configuration if needed
log_info ""
if [ ! -f "config/config.py" ] && [ -f "config/config_example.py" ]; then
    log_info "Creating config.py from example..."
    cp config/config_example.py config/config.py
    log_info "  Created config/config.py - PLEASE EDIT THIS FILE"
else
    log_warn "config/config.py already exists or example not found"
fi

# Set up permissions
log_info ""
log_info "Setting permissions..."
chmod 755 bin src scripts tests
chmod 775 data logs temp
log_info "  Permissions set"

# Summary
log_info ""
log_info "======================================"
log_info "Setup completed successfully!"
log_info "======================================"
log_info ""
log_info "Next steps:"
log_info "1. Edit config/config.py with your Kafka settings"
log_info "2. Test Kafka connection: python3 scripts/test_kafka_connection.py"
log_info "3. Run consumer manually: python3 src/lsst_alert_consumer.py"
log_info "4. Set up cron job: crontab -e"
log_info "   Add: 0 2 * * * $BASE_DIR/bin/run_lsst_consumer.sh"
log_info ""

if [[ "$create_venv" =~ ^[Yy]$ ]]; then
    log_info "Virtual environment is activated. To activate it later:"
    log_info "  source venv/bin/activate"
    log_info ""
fi

log_info "For more information, see docs/README.md"
log_info ""

exit 0
