#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
destination="$repo_root/outputs/Poach.app"
node_path="$(command -v node || true)"
signing_identity="${POACH_CODESIGN_IDENTITY:--}"
if [[ -z "${POACH_CODESIGN_IDENTITY:-}" ]] && security find-identity -v -p codesigning | grep -q '"Poach Local Development"'; then
  signing_identity="Poach Local Development"
fi

if [[ -z "$node_path" ]]; then
  echo "Node.js 20 or newer is required to build the Poach app." >&2
  exit 1
fi

pnpm --filter @poach/core build
pnpm --filter @poach/mcp-server build
swift build --package-path "$repo_root/apps/macos" --configuration release
mkdir -p "$repo_root/outputs"
stage_dir="$(mktemp -d "$repo_root/outputs/.poach-build.XXXXXX")"
trap 'rm -rf "$stage_dir"' EXIT
app_path="$stage_dir/Poach.app"
mkdir -p "$app_path/Contents/MacOS"
engine_path="$app_path/Contents/Resources/core"
mkdir -p "$engine_path/dist"
bash "$repo_root/scripts/build-app-icon.sh" "$repo_root/apps/macos/Assets/PoachMenuBar.svg" "$app_path/Contents/Resources/Poach.icns"
cp "$repo_root/packages/core/dist/"*.js "$engine_path/dist/"
cp "$repo_root/packages/core/package.json" "$engine_path/package.json"
cp "$repo_root/apps/macos/.build/release/Poach" "$app_path/Contents/MacOS/Poach"
cp "$repo_root/apps/macos/Info.plist" "$app_path/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :POACHNodePath string $node_path" "$app_path/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :POACHMCPServerPath string $repo_root/packages/mcp-server/dist/index.js" "$app_path/Contents/Info.plist"
if [[ "$signing_identity" == "-" ]]; then
  codesign --force --sign - "$app_path"
  echo "Development build: ad-hoc signing can invalidate Screen Recording approval after rebuilding. Set POACH_CODESIGN_IDENTITY to a stable code-signing identity." >&2
elif [[ "$signing_identity" == "Poach Local Development" ]]; then
  codesign --force --options runtime --timestamp=none --sign "$signing_identity" "$app_path"
else
  codesign --force --options runtime --timestamp --sign "$signing_identity" "$app_path"
fi
codesign --verify --strict "$app_path"

# Replacing signed executable pages in place can terminate a running Poach.
if [[ -d "$destination" ]]; then
  swift - "$app_path" "$destination" <<'SWIFT'
import Darwin
let arguments = CommandLine.arguments
if renamex_np(arguments[1], arguments[2], UInt32(RENAME_SWAP)) != 0 {
    perror("Could not exchange app bundles")
    exit(1)
}
SWIFT
else
  mv "$app_path" "$destination"
fi
echo "Built $destination"
