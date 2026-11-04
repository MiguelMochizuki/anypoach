#!/bin/bash
set -euo pipefail

# Arguments: menu-bar source SVG and destination ICNS.
icon_tmp="$(mktemp -d)"
trap 'rm -rf "$icon_tmp"' EXIT
iconset="$icon_tmp/Poach.iconset"
mkdir "$iconset"
node --input-type=module - "$1" "$icon_tmp/master.svg" <<'JS'
import { readFileSync, writeFileSync } from "node:fs";
const [, , source, output] = process.argv;
const mark = readFileSync(source, "utf8").replace(/^[\s\S]*?<svg[^>]*>/, "").replace(/<\/svg>\s*$/, "").replaceAll("currentColor", "#fff8eb");
writeFileSync(output, `<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
<defs><linearGradient id="ink" x2=".85" y2="1"><stop stop-color="#4f508d"/><stop offset="1" stop-color="#181a31"/></linearGradient></defs>
<rect x="88" y="88" width="848" height="848" rx="192" fill="url(#ink)"/>
<g transform="translate(188 180) scale(36)" fill="none">${mark}</g>
</svg>`);
JS
sips -s format png "$icon_tmp/master.svg" --out "$icon_tmp/master.png" >/dev/null
for size in 16 32 128 256 512; do
  for scale in 1 2; do
    pixels=$((size * scale))
    suffix=""
    if [[ "$scale" == 2 ]]; then suffix="@2x"; fi
    sips -z "$pixels" "$pixels" "$icon_tmp/master.png" --out "$iconset/icon_${size}x${size}${suffix}.png" >/dev/null
  done
done
iconutil -c icns "$iconset" -o "$2"
