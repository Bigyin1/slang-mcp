.PHONY: format format-check lint typecheck complexity test-unit test-integration test-realworld check check-all

PYTHON := .venv/bin/python
RUFF := .venv/bin/ruff
PYLINT := .venv/bin/pylint
MYPY := .venv/bin/mypy
PYTEST := .venv/bin/pytest
XENON := .venv/bin/xenon

format:
	$(RUFF) format src tests
	$(RUFF) check --fix src tests

format-check:
	$(RUFF) format --check src tests

lint:
	$(RUFF) check src tests
	$(PYLINT) src tests

typecheck:
	$(MYPY) src tests

complexity:
	$(XENON) --max-absolute B --max-modules B --max-average A src

test-unit:
	$(PYTEST) tests/unit

test-integration:
	$(PYTEST) tests/integration

test-realworld:
	SLANG_MCP_REALWORLD=1 $(PYTEST) -m realworld tests/realworld

check: format-check lint typecheck complexity test-unit test-integration

check-all: check test-realworld
