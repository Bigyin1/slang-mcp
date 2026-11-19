#!/usr/bin/env bash
set -euo pipefail

build_directory=$(cd "${1:-build/linux-release}" && pwd)
mkdir -p "${2:-dist/linux}"
output_directory=$(cd "${2:-dist/linux}" && pwd)
version=$(sed -n 's/^project(slang_mcp VERSION \([^ ]*\) LANGUAGES CXX)$/\1/p' CMakeLists.txt)
test -n "$version"
if [[ -n "${RELEASE_TAG:-}" ]]; then test "$RELEASE_TAG" = "v$version"; fi
package="slang-mcp-${version}-linux-x86_64"
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
cp "$build_directory/slang_mcp" "$stage/slang_mcp"
guide=slang-mcp.md
cp docs/agent-instructions.md "$stage/$guide"
(cd "$stage" && tar -czf "$output_directory/$package.tar.gz" slang_mcp "$guide")
checksum=(sha256sum)
if ! command -v sha256sum >/dev/null; then checksum=(shasum -a 256); fi
(cd "$output_directory" && "${checksum[@]}" "$package.tar.gz" > "$package.tar.gz.sha256")
(cd "$output_directory" && "${checksum[@]}" -c "$package.tar.gz.sha256")
tar -tzf "$output_directory/$package.tar.gz" | grep -Fx slang_mcp
tar -tzf "$output_directory/$package.tar.gz" | grep -Fx "$guide"
tar -tzf "$output_directory/$package.tar.gz" | while IFS= read -r member; do
  if [[ "$member" != slang_mcp && "$member" != "$guide" ]]; then
    echo "Unexpected archive entry: $member" >&2
    exit 1
  fi
done
