#!/usr/bin/env sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_dir=${1:-"$repo_dir/build"}
log_dir="$repo_dir/artifacts/test-logs"
mkdir -p "$log_dir"
log="$log_dir/test-$(date -u +%Y%m%dT%H%M%SZ).log"

cmake --build "$build_dir" --parallel 2 2>&1 | tee "$log"
ctest --test-dir "$build_dir" --output-on-failure 2>&1 | tee -a "$log"
PYTHONPATH="$repo_dir/python" COCOMMAND_NATIVE_LIB="$build_dir/libcocommand_c.so" \
  python3 -m unittest discover -s "$repo_dir/tests/python" -v 2>&1 | tee -a "$log"

