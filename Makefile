.PHONY: help install test lint format demo clean

help:
	@echo "Route.it Developer Commands:"
	@echo "  make install  - Install package in editable mode with dev dependencies"
	@echo "  make test     - Run pytest suite"
	@echo "  make demo     - Run Vadodara 30-stop CVRPTW optimization demo (offline-safe)"
	@echo "  make lint     - Check code formatting and style with ruff & black"
	@echo "  make format   - Automatically format code with ruff & black"
	@echo "  make clean    - Remove build artifacts and temporary caches"

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

demo:
	python -m benchmarks.demo_vadodara --mock

lint:
	ruff check .
	black --check .

format:
	ruff check --fix .
	black .

clean:
	python -c "import shutil, glob, os; [shutil.rmtree(p, ignore_errors=True) for p in glob.glob('**/__pycache__', recursive=True) + glob.glob('*.egg-info') + ['.pytest_cache', '.ruff_cache', 'build', 'dist']]"
