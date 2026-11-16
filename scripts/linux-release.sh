#!/usr/bin/env bash
set -euo pipefail

# Run in the pinned manylinux_2_28 container with portable-linux-toolchain.
test "$(uname -m)" = x86_64
test "$(getconf GNU_LIBC_VERSION)" = 'glibc 2.28'
export CI=true CC=clang CXX=clang++
cmake -S . -B build/linux-release -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON \
  -DPython_EXECUTABLE=/opt/python/cp310-cp310/bin/python3 \
  -DCMAKE_EXE_LINKER_FLAGS='-fuse-ld=lld -static-libstdc++ -static-libgcc'
cmake --build build/linux-release --parallel 2
ctest --test-dir build/linux-release --output-on-failure

mkdir -p build/package
ldd build/linux-release/slang_mcp | tee build/package/ldd.txt
if grep -q 'not found' build/package/ldd.txt; then exit 1; fi
scripts/check-linux-abi.sh build/linux-release/slang_mcp
scripts/package-linux.sh
