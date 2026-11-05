#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash scripts/build-macos-app.sh
release="outputs/beta"
mkdir -p "$release"
ditto -c -k --keepParent outputs/Poach.app "$release/Poach-$(uname -m).zip"
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
mkdir "$stage/Poach Codex"
ditto outputs/connectors/marketplace "$stage/Poach Codex/marketplace"
cp scripts/install-codex-connector.sh "$stage/Poach Codex/Install Codex.command"
ditto -c -k --keepParent "$stage/Poach Codex" "$release/Poach-Codex.zip"
cp outputs/connectors/Poach.mcpb "$release/"
