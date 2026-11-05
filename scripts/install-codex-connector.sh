#!/bin/bash
set -euo pipefail

source_dir="$(cd "$(dirname "$0")" && pwd)"
market="$HOME/Library/Application Support/Poach/Codex/marketplace"
plugin="$market/plugins/poach"
command -v codex >/dev/null || { echo "Install the Codex CLI first." >&2; exit 1; }
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
command -v node >/dev/null || { echo "Install Node.js 20.19 or later first." >&2; exit 1; }

mkdir -p "$market"
ditto "$source_dir/marketplace" "$market"
node --input-type=module - "$plugin" <<'JS'
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
const directory = process.argv[2];
const manifest = join(directory, '.mcp.json');
const configuration = JSON.parse(readFileSync(manifest, 'utf8'));
configuration.mcpServers.poach.command = process.execPath;
configuration.mcpServers.poach.args = [join(directory, 'server.mjs')];
writeFileSync(manifest, JSON.stringify(configuration, null, 2) + '\n');
JS
codex plugin marketplace add "$market"
codex plugin add poach@poach-local
