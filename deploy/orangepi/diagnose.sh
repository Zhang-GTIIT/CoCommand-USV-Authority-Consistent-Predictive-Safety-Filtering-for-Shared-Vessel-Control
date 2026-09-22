#!/usr/bin/env sh
set -eu

printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'kernel=%s\n' "$(uname -a)"
printf 'machine=%s\n' "$(uname -m)"
printf 'python=%s\n' "$(python3 --version 2>&1 || true)"
printf 'cmake=%s\n' "$(cmake --version 2>/dev/null | head -n 1 || true)"
if command -v lscpu >/dev/null 2>&1; then lscpu; fi
if command -v free >/dev/null 2>&1; then free -h; fi
for zone in /sys/class/thermal/thermal_zone*/temp; do
  if [ -r "$zone" ]; then printf 'temperature_raw %s=' "$zone"; cat "$zone"; fi
done
printf '%s\n' 'hardware_validation=not_performed_by_this_script'

