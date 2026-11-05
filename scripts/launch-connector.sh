#!/bin/bash
set -eu
for app in "/Applications/Poach.app" "$HOME/Applications/Poach.app"; do
  resources="$app/Contents/Resources"
  bin="$resources/runtime/bin"
  if [[ -x "$bin/node" && -x "$bin/ffmpeg" && -x "$bin/ffprobe" && -r "$resources/server.mjs" ]]; then
    export PATH="$bin:/usr/bin:/bin"
    exec "$bin/node" "$resources/server.mjs"
  fi
done
echo "Install Poach Beta 2 or later in Applications before connecting your assistant." >&2
exit 1
