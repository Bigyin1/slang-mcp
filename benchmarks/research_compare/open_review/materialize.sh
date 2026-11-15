#!/bin/sh
set -eu
corpus_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
input_root=/private/tmp/slang-compare-open/inputs
for case_name in axi_review idma_review; do
  if [ -e "$input_root/$case_name" ]; then
    echo "Refusing existing destination: $input_root/$case_name" >&2
    exit 1
  fi
done
mkdir -p "$input_root"
for case_name in axi_review idma_review; do
  cp -R "$corpus_dir/cases/$case_name/workspace" "$input_root/$case_name"
  chmod -R a-w "$input_root/$case_name"
done
