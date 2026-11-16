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
cp docs/agent-instructions.md "$stage/AGENTS.md"
cp -R docs "$stage/"
mkdir -p "$stage/src"
cp src/contract.json "$stage/src/"
mkdir -p "$stage/licenses"
# The release embeds the GCC C++ runtime under its runtime library exception.
cp -R licenses/gcc "$stage/licenses/"
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
ldd "$stage/bin/slang_mcp" | tee build/package/ldd.txt
if grep -q 'not found' build/package/ldd.txt; then exit 1; fi
scripts/check-linux-abi.sh "$stage/bin/slang_mcp"
tar -C build/package -czf "dist/linux/$package.tar.gz" "$package"
(cd dist/linux && sha256sum "$package.tar.gz" > "$package.tar.gz.sha256")
(cd dist/linux && sha256sum -c "$package.tar.gz.sha256")
tar -tzf "dist/linux/$package.tar.gz" | grep -Fx "$package/bin/slang_mcp"
tar -tzf "dist/linux/$package.tar.gz" | grep -Fx "$package/AGENTS.md"
