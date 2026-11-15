#!/usr/bin/env bash
set -euo pipefail

# Run on Ubuntu 24.04 x86-64 with the toolchain in linux-toolchain/action.yml.
test "$(uname -m)" = x86_64
export CC=clang-23 CXX=clang++-23
cmake -S . -B build/linux-release -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON \
  -DCMAKE_EXE_LINKER_FLAGS=-fuse-ld=lld-23
cmake --build build/linux-release --parallel 2
ctest --test-dir build/linux-release --output-on-failure

version=$(sed -n 's/^project(slang_mcp VERSION \([^ ]*\) LANGUAGES CXX)$/\1/p' CMakeLists.txt)
test -n "$version"
if [[ -n "${RELEASE_TAG:-}" ]]; then
  test "$RELEASE_TAG" = "v$version"
fi
package="slang-mcp-${version}-linux-x86_64"
stage="build/package/$package"
mkdir -p "$stage/bin" dist/linux
cmake --install build/linux-release --prefix "$stage"
cp LICENSE README.md "$stage/"
mkdir -p "$stage/licenses"
for dependency in slang mcp_sdk fmt json tomlplusplus boost_regex mimalloc; do
  directory="build/linux-release/_deps/${dependency}-src"
  for license in LICENSE LICENSE.txt LICENSE.MIT LICENSE_1_0.txt COPYING; do
    if [[ -f "$directory/$license" ]]; then
      cp "$directory/$license" "$stage/licenses/${dependency}-${license}"
      break
    fi
  done
done
# Fail if the resulting executable has unresolved shared-library dependencies.
ldd "$stage/bin/slang-mcp" | tee build/package/ldd.txt
if grep -q 'not found' build/package/ldd.txt; then exit 1; fi
tar -C build/package -czf "dist/linux/$package.tar.gz" "$package"
(cd dist/linux && sha256sum "$package.tar.gz" > "$package.tar.gz.sha256")
(cd dist/linux && sha256sum -c "$package.tar.gz.sha256")
tar -tzf "dist/linux/$package.tar.gz" | grep -Fx "$package/bin/slang-mcp"
