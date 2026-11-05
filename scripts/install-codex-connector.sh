#!/bin/bash
set -euo pipefail

source_dir="$(cd "$(dirname "$0")" && pwd)"
market="$HOME/Library/Application Support/Poach/Codex/marketplace"
plugin="$market/plugins/poach"
for app in "/Applications/Poach.app" "$HOME/Applications/Poach.app"; do
  if [[ -x "$app/Contents/Resources/runtime/bin/node" ]]; then
    export PATH="$app/Contents/Resources/runtime/bin:$PATH"
    break
  fi
done
export PATH="$PATH:/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin:/Applications/Codex.app/Contents/Resources"
command -v codex >/dev/null || { echo "Open or install Codex first, then run this installer again." >&2; exit 1; }
mkdir -p "$market"
ditto "$source_dir/marketplace" "$market"
# plutil quotes the destination path correctly, including spaces and Unicode.
plutil -replace mcpServers.poach.args.0 -string "$plugin/launch-connector.sh" "$plugin/.mcp.json"
plutil -convert json "$plugin/.mcp.json"
codex plugin marketplace add "$market"
codex plugin add poach@poach-local
