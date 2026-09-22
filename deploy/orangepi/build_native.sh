#!/usr/bin/env sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
build_dir=${COCOMMAND_BUILD_DIR:-"$repo_dir/build-arm64-native"}
install_prefix=${COCOMMAND_INSTALL_PREFIX:-"$repo_dir/install-arm64-native"}

cmake -S "$repo_dir" -B "$build_dir" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCOCOMMAND_BUILD_TESTS=ON \
  -DCOCOMMAND_BUILD_PYBIND=OFF \
  -DCMAKE_INSTALL_PREFIX="$install_prefix"
cmake --build "$build_dir" --parallel 2
ctest --test-dir "$build_dir" --output-on-failure
cmake --install "$build_dir"

printf '%s\n' "Native ARM64 application installed at $install_prefix"

