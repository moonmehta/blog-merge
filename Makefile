# feed-mixer
# Convenient commands for development and usage.

.PHONY: help setup install run clean clean_venv clean_cache clean_all
.DEFAULT_GOAL := help

PYTHON := python3
VENV_DIR := venv
VENV_PYTHON := $(VENV_DIR)/bin/python
VENV_PIP := $(VENV_DIR)/bin/pip

help:
	@echo "feed-mixer"
	@echo "=========="
	@echo ""
	@echo "Available commands:"
	@echo "  make setup        - Set up virtual environment and install dependencies"
	@echo "  make install      - Install dependencies (assumes venv exists)"
	@echo "  make run          - Fetch feeds and write the mixed Atom feed"
	@echo "                      (add CACHE_FALLBACK=true to use cache on fetch failure)"
	@echo "  make clean        - Remove generated output"
	@echo "  make clean_venv   - Remove the virtual environment"
	@echo "  make clean_cache  - Remove the feed cache"
	@echo "  make clean_all    - Remove output, cache, and virtual environment"
	@echo "  make help         - Show this help message"

setup: $(VENV_DIR)/bin/activate
	@echo "Setup complete. To activate: source $(VENV_DIR)/bin/activate"

$(VENV_DIR)/bin/activate: requirements.txt
	@echo "Creating virtual environment..."
	$(PYTHON) -m venv $(VENV_DIR)
	@echo "Installing dependencies..."
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -r requirements.txt
	@touch $(VENV_DIR)/bin/activate

install:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	$(VENV_PIP) install --upgrade pip
	$(VENV_PIP) install -r requirements.txt

run: setup
	$(VENV_PYTHON) src/mixer.py $(if $(VERBOSE),--verbose) $(if $(CACHE),--cache) $(if $(CACHE_FALLBACK),--cache-fallback)

clean:
	@echo "Cleaning output..."
	rm -rf _site
	rm -rf src/__pycache__ __pycache__

clean_venv:
	rm -rf $(VENV_DIR)

clean_cache:
	rm -rf .cache

clean_all: clean clean_venv clean_cache
