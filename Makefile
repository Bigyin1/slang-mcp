.PHONY: format format-check lint typecheck complexity test-unit test-integration test-realworld check check-all

PYTHON := .venv/bin/python
RUFF := .venv/bin/ruff
PYLINT := .venv/bin/pylint
MYPY := .venv/bin/mypy
PYTEST := .venv/bin/pytest
XENON := .venv/bin/xenon

format:
	$(RUFF) format src tests benchmarks
	$(RUFF) check --fix src tests benchmarks

format-check:
	$(RUFF) format --check src tests benchmarks

lint:
	$(RUFF) check src tests benchmarks
	$(PYLINT) src tests benchmarks

typecheck:
	$(MYPY) src tests benchmarks

complexity:
	$(XENON) --max-absolute B --max-modules B --max-average A src benchmarks

test-unit:
	$(PYTEST) tests/unit

test-integration:
	$(PYTEST) tests/integration

test-realworld:
	SLANG_MCP_REALWORLD=1 $(PYTEST) -m realworld tests/realworld

check: format-check lint typecheck complexity test-unit test-integration

check-all: check test-realworld
