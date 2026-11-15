.PHONY: configure build format format-check lint complexity test test-unit test-integration test-realworld check check-all check-benchmarks

export UV_CACHE_DIR ?= $(CURDIR)/build/uv-cache
export MPLCONFIGDIR ?= $(CURDIR)/.matplotlib

configure:
	cmake --preset dev

build:
	cmake --build --preset dev --parallel 6

format:
	cmake --build build/cpp --target format

format-check:
	cmake --build build/cpp --target format-check

lint:
	cmake --build build/cpp --target lint

complexity:
	cmake --build build/cpp --target complexity

test: build
	cmake --build build/cpp --target slang_mcp_tests --parallel 6
	ctest --preset dev

test-unit test-integration: test

check: build format-check lint complexity test

check-benchmarks:
	uv run --project benchmarks --locked ruff format --check benchmarks
	uv run --project benchmarks --locked ruff check benchmarks
	uv run --project benchmarks --locked pylint --rcfile=benchmarks/pyproject.toml benchmarks
	uv run --project benchmarks --locked mypy --config-file=benchmarks/pyproject.toml benchmarks
	uv run --project benchmarks --locked xenon --max-absolute B --max-modules B --max-average A benchmarks
	uv run --project benchmarks --locked pytest -c benchmarks/pyproject.toml benchmarks/tests benchmarks/research_compare/tests

test-realworld: build
	uv run --project benchmarks --locked python -m benchmarks validate --builds

check-all: check check-benchmarks test-realworld
