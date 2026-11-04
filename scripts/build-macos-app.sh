#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
app_path="$repo_root/outputs/Poach.app"
node_path="$(command -v node || true)"
signing_identity="${POACH_CODESIGN_IDENTITY:--}"

if [[ -z "$node_path" ]]; then
  echo "Node.js 20 or newer is required to build the Poach app." >&2
  exit 1
fi

pnpm --filter @poach/core build
swift build --package-path "$repo_root/apps/macos" --configuration release
mkdir -p "$app_path/Contents/MacOS"
engine_path="$app_path/Contents/Resources/core"
mkdir -p "$engine_path/dist"
cp "$repo_root/packages/core/dist/"*.js "$engine_path/dist/"
cp "$repo_root/packages/core/package.json" "$engine_path/package.json"
cp "$repo_root/apps/macos/.build/release/Poach" "$app_path/Contents/MacOS/Poach"
cp "$repo_root/apps/macos/Info.plist" "$app_path/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Add :POACHNodePath string $node_path" "$app_path/Contents/Info.plist"
if [[ "$signing_identity" == "-" ]]; then
  codesign --force --sign - "$app_path"
  echo "Development build: ad-hoc signing can invalidate Screen Recording approval after rebuilding. Set POACH_CODESIGN_IDENTITY to a stable code-signing identity." >&2
else
  codesign --force --options runtime --timestamp --sign "$signing_identity" "$app_path"
fi
codesign --verify --strict "$app_path"

echo "Built $app_path"
