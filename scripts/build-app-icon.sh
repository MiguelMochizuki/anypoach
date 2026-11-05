#!/bin/bash
set -euo pipefail

# Arguments: app icon master PNG and destination ICNS.
icon_tmp="$(mktemp -d)"
trap 'rm -rf "$icon_tmp"' EXIT
iconset="$icon_tmp/Poach.iconset"
mkdir "$iconset"
for size in 16 32 128 256 512; do
  for scale in 1 2; do
    pixels=$((size * scale))
    suffix=""
    if [[ "$scale" == 2 ]]; then suffix="@2x"; fi
    sips -z "$pixels" "$pixels" "$1" --out "$iconset/icon_${size}x${size}${suffix}.png" >/dev/null
  done
done
iconutil -c icns "$iconset" -o "$2"
