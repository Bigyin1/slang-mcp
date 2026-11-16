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
for document in README.md docs/*.md; do
  name=$(basename "$document")
  if [[ "$name" == agent-instructions.md ]]; then name=AGENTS.md; fi
  sed -e 's#](docs/#](#g' \
    -e 's#](agent-instructions.md)#](AGENTS.md)#g' \
    -e 's#](LICENSE)#](LICENSES.md)#g' \
    -e "s#](../src/contract.json)#](https://github.com/Bigyin1/slang-mcp/blob/v${version}/src/contract.json)#g" \
    "$document" > "$stage/$name"
done
append_license() {
  printf '\n## %s\n\n````text\n' "$1"
  cat "$2"
  printf '\n````\n'
}
printf '# Licenses\n' > "$stage/LICENSES.md"
append_license slang-mcp LICENSE >> "$stage/LICENSES.md"
for license in licenses/gcc/*; do
  append_license "GCC runtime: $(basename "$license")" "$license" >> "$stage/LICENSES.md"
done
for dependency in slang mcp_sdk fmt json tomlplusplus boost_regex mimalloc; do
  directory="$build_directory/_deps/${dependency}-src"
  for license in LICENSE LICENSE.txt LICENSE.MIT LICENSE_1_0.txt COPYING; do
    if [[ -f "$directory/$license" ]]; then
      append_license "$dependency" "$directory/$license" >> "$stage/LICENSES.md"
      break
    fi
  done
done
(cd "$stage" && tar -czf "$output_directory/$package.tar.gz" slang_mcp *.md)
checksum=(sha256sum)
if ! command -v sha256sum >/dev/null; then checksum=(shasum -a 256); fi
(cd "$output_directory" && "${checksum[@]}" "$package.tar.gz" > "$package.tar.gz.sha256")
(cd "$output_directory" && "${checksum[@]}" -c "$package.tar.gz.sha256")
tar -tzf "$output_directory/$package.tar.gz" | grep -Fx slang_mcp
tar -tzf "$output_directory/$package.tar.gz" | grep -Fx AGENTS.md
tar -tzf "$output_directory/$package.tar.gz" | while IFS= read -r member; do
  if [[ "$member" == */* || ( "$member" != slang_mcp && "$member" != *.md ) ]]; then
    echo "Unexpected archive entry: $member" >&2
    exit 1
  fi
done
