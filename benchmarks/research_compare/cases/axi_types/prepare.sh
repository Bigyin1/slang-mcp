#!/bin/sh
set -eu
case_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_root=${1:-$case_dir/rtl}
destination=${2:-/private/tmp/slang-compare/axi_types/rtl}
(cd "$source_root" && shasum -a 256 -c "$case_dir/sources.sha256")
while read -r checksum relative; do
  mkdir -p "$destination/$(dirname -- "$relative")"
  cp "$source_root/$relative" "$destination/$relative"
done < "$case_dir/sources.sha256"
cp "$case_dir/integration.sv" "$destination/integration.sv"
cp "$case_dir/compile_config.json" "$destination/compile_config.json"
cp "$case_dir/provenance.json" "$destination/provenance.json"
cp "$case_dir/README.txt" "$destination/README.txt"
