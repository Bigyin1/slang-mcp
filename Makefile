.PHONY: configure build format format-check lint complexity test test-unit test-integration check

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
