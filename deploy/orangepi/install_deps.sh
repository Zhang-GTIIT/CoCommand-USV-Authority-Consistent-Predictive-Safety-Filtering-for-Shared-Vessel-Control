#!/usr/bin/env sh
set -eu

# Run explicitly on a Debian/Ubuntu-class ARM64 board. This does not alter kernels,
# GPIO, serial settings, or boot firmware.
sudo apt-get update
sudo apt-get install -y --no-install-recommends cmake ninja-build g++ python3 python3-venv

