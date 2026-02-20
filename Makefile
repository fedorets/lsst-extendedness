# ============================================================================
# LSST Extendedness Pipeline - Makefile
# Wraps PDM commands for convenience
# ============================================================================

.PHONY: help install dev-install test test-cov coverage coverage-report \
        lint lint-fix format typecheck check all-checks \
        db-init db-shell db-stats db-backup db-restore \
        ingest query process query-today query-minimoon query-recent \
        timer-install timer-uninstall timer-status timer-logs \
        shell profile-ingest generate-sample-data validate-config \
        setup-system bootstrap deploy health-check env-info clean \
        docs docs-serve docs-build

# Default configuration
CONFIG ?= config/default.toml
WINDOW ?= 15
DEPLOY_HOST ?= app-server
DEPLOY_USER ?= deploy
DEPLOY_PATH ?= /opt/services/lsst-extendedness

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m  # No Color

# ============================================================================
# HELP
# ============================================================================

help:
	@echo "$(BLUE)LSST Extendedness Pipeline$(NC)"
	@echo ""
	@echo "$(GREEN)Setup:$(NC)"
	@echo "  make install          Install production dependencies"
	@echo "  make dev-install      Install dev + test dependencies"
	@echo "  make bootstrap        Run bootstrap script (no sudo)"
	@echo "  make setup-system     Install system dependencies (requires sudo)"
	@echo ""
	@echo "$(GREEN)Development:$(NC)"
	@echo "  make test             Run pytest"
	@echo "  make test-cov         Run pytest with coverage report"
	@echo "  make coverage-report  Open HTML coverage report"
	@echo "  make lint             Run ruff linter"
	@echo "  make lint-fix         Run ruff with auto-fix"
	@echo "  make format           Format code with ruff"
	@echo "  make typecheck        Run mypy type checker"
	@echo "  make check            Run all checks (lint + format + typecheck + test)"
	@echo "  make shell            Interactive Python shell with package loaded"
	@echo ""
	@echo "$(GREEN)Database:$(NC)"
	@echo "  make db-init          Initialize SQLite database schema"
	@echo "  make db-shell         Open SQLite interactive shell"
	@echo "  make db-stats         Show database statistics"
	@echo "  make db-backup        Backup database"
	@echo "  make db-restore       Restore database from backup"
	@echo ""
	@echo "$(GREEN)Operations:$(NC)"
	@echo "  make ingest           Run daily ingestion (CONFIG=config/local.toml)"
	@echo "  make query            Interactive query shell"
	@echo "  make process          Run post-processing (WINDOW=15 days)"
	@echo "  make query-today      Quick: today's alerts"
	@echo "  make query-minimoon   Quick: minimoon candidates"
	@echo "  make query-recent     Quick: last 7 days"
	@echo ""
	@echo "$(GREEN)Systemd Timers:$(NC)"
	@echo "  make timer-install    Install + enable systemd timers"
	@echo "  make timer-uninstall  Stop + remove timers"
	@echo "  make timer-status     Check timer status"
	@echo "  make timer-logs       Tail timer logs"
	@echo ""
	@echo "$(GREEN)Documentation:$(NC)"
	@echo "  make docs             Build documentation"
	@echo "  make docs-serve       Serve docs locally (http://localhost:8000)"
	@echo ""
	@echo "$(GREEN)Utilities:$(NC)"
	@echo "  make env-info         Show environment information"
	@echo "  make health-check     Run system health check"
	@echo "  make clean            Clean build artifacts"

# ============================================================================
# SETUP
# ============================================================================

install:
	@echo "$(BLUE)Installing production dependencies...$(NC)"
	pdm install --prod

dev-install:
	@echo "$(BLUE)Installing development dependencies...$(NC)"
	pdm install -G dev
	pdm run pre-commit install

bootstrap:
	@echo "$(BLUE)Running bootstrap script...$(NC)"
	./scripts/bootstrap.sh

setup-system:
	@echo "$(BLUE)Installing system dependencies (requires sudo)...$(NC)"
	./scripts/setup-system.sh

# ============================================================================
# DEVELOPMENT
# ============================================================================

test:
	@echo "$(BLUE)Running tests...$(NC)"
	pdm run pytest tests/ -v

test-cov:
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	pdm run pytest tests/ -v --cov=lsst_extendedness --cov-report=term-missing --cov-report=html

coverage:
	@echo "$(BLUE)Generating coverage report...$(NC)"
	pdm run coverage report --show-missing

coverage-report:
	@echo "$(BLUE)Opening coverage report...$(NC)"
	pdm run coverage html
	@if command -v open >/dev/null 2>&1; then \
		open htmlcov/index.html; \
	elif command -v xdg-open >/dev/null 2>&1; then \
		xdg-open htmlcov/index.html; \
	else \
		echo "Coverage report generated at htmlcov/index.html"; \
	fi

lint:
	@echo "$(BLUE)Running linter...$(NC)"
	pdm run ruff check src/ tests/

lint-fix:
	@echo "$(BLUE)Running linter with auto-fix...$(NC)"
	pdm run ruff check src/ tests/ --fix

format:
	@echo "$(BLUE)Formatting code...$(NC)"
	pdm run ruff format src/ tests/

typecheck:
	@echo "$(BLUE)Running type checker...$(NC)"
	pdm run mypy src/

check: lint format typecheck test
	@echo "$(GREEN)All checks passed!$(NC)"

all-checks: check

# ============================================================================
# DATABASE
# ============================================================================

db-init:
	@echo "$(BLUE)Initializing database...$(NC)"
	pdm run python -m lsst_extendedness.cli db-init --config $(CONFIG)

db-shell:
	@echo "$(BLUE)Opening SQLite shell...$(NC)"
	@DB_PATH=$$(pdm run python -c "from lsst_extendedness.config import get_settings; print(get_settings().database_path)" 2>/dev/null || echo "data/lsst_extendedness.db"); \
	sqlite3 "$$DB_PATH"

db-stats:
	@echo "$(BLUE)Database statistics:$(NC)"
	pdm run python -m lsst_extendedness.cli db-stats --config $(CONFIG)

db-backup:
	@echo "$(BLUE)Backing up database...$(NC)"
	@TIMESTAMP=$$(date +%Y%m%d_%H%M%S); \
	DB_PATH=$$(pdm run python -c "from lsst_extendedness.config import get_settings; print(get_settings().database_path)" 2>/dev/null || echo "data/lsst_extendedness.db"); \
	cp "$$DB_PATH" "data/backups/lsst_extendedness_$$TIMESTAMP.db"; \
	echo "$(GREEN)Backup created: data/backups/lsst_extendedness_$$TIMESTAMP.db$(NC)"

db-restore:
	@echo "$(YELLOW)Restoring database from: $(BACKUP)$(NC)"
	@if [ -z "$(BACKUP)" ]; then \
		echo "$(RED)Error: Specify BACKUP=path/to/backup.db$(NC)"; \
		exit 1; \
	fi
	@DB_PATH=$$(pdm run python -c "from lsst_extendedness.config import get_settings; print(get_settings().database_path)" 2>/dev/null || echo "data/lsst_extendedness.db"); \
	cp "$(BACKUP)" "$$DB_PATH"; \
	echo "$(GREEN)Database restored from $(BACKUP)$(NC)"

# ============================================================================
# OPERATIONS
# ============================================================================

ingest:
	@echo "$(BLUE)Running ingestion...$(NC)"
	pdm run python -m lsst_extendedness.cli ingest --config $(CONFIG)

query:
	@echo "$(BLUE)Starting query shell...$(NC)"
	pdm run python -m lsst_extendedness.cli query --config $(CONFIG)

process:
	@echo "$(BLUE)Running post-processing (window=$(WINDOW) days)...$(NC)"
	pdm run python -m lsst_extendedness.cli process --config $(CONFIG) --window $(WINDOW)

query-today:
	@echo "$(BLUE)Today's alerts:$(NC)"
	pdm run python -c "from lsst_extendedness.query.shortcuts import today; print(today().to_string())"

query-minimoon:
	@echo "$(BLUE)Minimoon candidates:$(NC)"
	pdm run python -c "from lsst_extendedness.query.shortcuts import minimoon_candidates; print(minimoon_candidates().to_string())"

query-recent:
	@echo "$(BLUE)Recent alerts (7 days):$(NC)"
	pdm run python -c "from lsst_extendedness.query.shortcuts import recent; print(recent(days=7).to_string())"

# ============================================================================
# SYSTEMD TIMERS
# ============================================================================

timer-install:
	@echo "$(BLUE)Installing systemd timers...$(NC)"
	mkdir -p ~/.config/systemd/user
	cp systemd/lsst-ingest.service ~/.config/systemd/user/
	cp systemd/lsst-ingest.timer ~/.config/systemd/user/
	cp systemd/lsst-process.service ~/.config/systemd/user/
	cp systemd/lsst-process.timer ~/.config/systemd/user/
	systemctl --user daemon-reload
	systemctl --user enable lsst-ingest.timer lsst-process.timer
	systemctl --user start lsst-ingest.timer lsst-process.timer
	@echo "$(GREEN)Timers installed and enabled$(NC)"

timer-uninstall:
	@echo "$(YELLOW)Removing systemd timers...$(NC)"
	-systemctl --user stop lsst-ingest.timer lsst-process.timer
	-systemctl --user disable lsst-ingest.timer lsst-process.timer
	rm -f ~/.config/systemd/user/lsst-ingest.{service,timer}
	rm -f ~/.config/systemd/user/lsst-process.{service,timer}
	systemctl --user daemon-reload
	@echo "$(GREEN)Timers removed$(NC)"

timer-status:
	@echo "$(BLUE)Timer status:$(NC)"
	systemctl --user list-timers lsst-*
	@echo ""
	@echo "$(BLUE)Service status:$(NC)"
	-systemctl --user status lsst-ingest.service --no-pager
	-systemctl --user status lsst-process.service --no-pager

timer-logs:
	@echo "$(BLUE)Timer logs (press Ctrl+C to exit):$(NC)"
	journalctl --user -u lsst-ingest -u lsst-process -f

# ============================================================================
# DOCUMENTATION
# ============================================================================

docs: docs-build
	@echo "$(GREEN)Documentation built in site/$(NC)"

docs-build:
	@echo "$(BLUE)Building documentation...$(NC)"
	pdm run mkdocs build

docs-serve:
	@echo "$(BLUE)Serving documentation at http://localhost:8000$(NC)"
	pdm run mkdocs serve

# ============================================================================
# UTILITIES
# ============================================================================

shell:
	@echo "$(BLUE)Starting interactive Python shell...$(NC)"
	pdm run python -c "from lsst_extendedness import *; import code; code.interact(banner='LSST Extendedness Pipeline Shell', local=locals())"

profile-ingest:
	@echo "$(BLUE)Profiling ingestion...$(NC)"
	pdm run python -m cProfile -o profile.stats -m lsst_extendedness.cli ingest --config $(CONFIG) --source mock --count 1000
	pdm run python -c "import pstats; p=pstats.Stats('profile.stats'); p.sort_stats('cumtime').print_stats(20)"

generate-sample-data:
	@echo "$(BLUE)Generating sample data...$(NC)"
	pdm run python -m lsst_extendedness.cli generate-mock --count 1000 --output data/sample.db

validate-config:
	@echo "$(BLUE)Validating configuration: $(CONFIG)$(NC)"
	pdm run python -m lsst_extendedness.config.validate $(CONFIG)

env-info:
	@echo "$(BLUE)Environment Information$(NC)"
	@echo "========================"
	@echo "Python:   $$(python3 --version 2>&1)"
	@echo "PDM:      $$(pdm --version 2>&1 || echo 'not installed')"
	@echo "Platform: $$(uname -s) $$(uname -m)"
	@echo ""
	@echo "$(BLUE)NumPy BLAS Configuration:$(NC)"
	@pdm run python -c "import numpy; numpy.show_config()" 2>/dev/null | grep -i blas || echo "NumPy not installed"
	@echo ""
	@echo "$(BLUE)Database:$(NC)"
	@pdm run python -c "from lsst_extendedness.config import get_settings; print(get_settings().database_path)" 2>/dev/null || echo "Not configured"

health-check:
	@echo "$(BLUE)Running health check...$(NC)"
	pdm run python -m lsst_extendedness.cli health-check --config $(CONFIG)

clean:
	@echo "$(YELLOW)Cleaning build artifacts...$(NC)"
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .eggs/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf profile.stats
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.py[cod]" -delete
	@echo "$(GREEN)Clean complete$(NC)"

# ============================================================================
# DEPLOYMENT (for reference - typically use GitHub Actions)
# ============================================================================

deploy:
	@echo "$(BLUE)Deploying to $(DEPLOY_HOST)...$(NC)"
	rsync -avz --exclude='.venv' --exclude='data/*.db' --exclude='.git' \
		--exclude='htmlcov' --exclude='.pytest_cache' --exclude='__pycache__' \
		./ $(DEPLOY_USER)@$(DEPLOY_HOST):$(DEPLOY_PATH)/
	ssh $(DEPLOY_USER)@$(DEPLOY_HOST) "cd $(DEPLOY_PATH) && make install && make db-init"
	@echo "$(GREEN)Deployment complete$(NC)"
