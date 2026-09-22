#!/usr/bin/env sh
set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
export PYTHONPATH="$repo_dir/python${PYTHONPATH:+:$PYTHONPATH}"
export COCOMMAND_NATIVE_LIB=${COCOMMAND_NATIVE_LIB:-"$repo_dir/build-arm64-native/libcocommand_c.so"}
python3 -m cocommand replay \
  --input "$repo_dir/examples/replay_fixture.jsonl" \
  --controller enhanced_steering \
  --output "$repo_dir/runs/arm64_replay_output.jsonl"

