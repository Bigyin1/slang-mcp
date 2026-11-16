#!/usr/bin/env bash
set -euo pipefail

binary=${1:?Usage: check-linux-abi.sh ELF_BINARY}
maximum=2.28
readelf_tool=${READELF:-readelf}
versions=$("$readelf_tool" --version-info --wide "$binary" |
  grep -oE 'GLIBC_[A-Za-z0-9_.]+' | sort -u)
test -n "$versions"
for symbol in $versions; do
  if [[ ! "$symbol" =~ ^GLIBC_[0-9]+(\.[0-9]+)*$ ]]; then
    echo "Unsupported glibc ABI requirement: $symbol" >&2
    exit 1
  fi
  required=${symbol#GLIBC_}
  highest=$(printf '%s\n' "$required" "$maximum" | sort -V | tail -1)
  if [[ "$highest" != "$maximum" ]]; then
    echo "Requires $symbol; release baseline is GLIBC_$maximum" >&2
    exit 1
  fi
done
dependencies=$("$readelf_tool" --dynamic --wide "$binary")
if [[ "$dependencies" =~ \[(libstdc\+\+|libgcc_s|libasan|libubsan)\.so ]]; then
  echo 'Release must not depend on shared C++ or sanitizer runtimes' >&2
  exit 1
fi
printf 'ELF glibc requirements verified: <= %s; C++ runtimes are static\n' "$maximum"
