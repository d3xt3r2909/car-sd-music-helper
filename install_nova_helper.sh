#!/usr/bin/env bash
set -euo pipefail

NOVA_DIR="${NOVA_DIR:-$HOME/Desktop/nova}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.nova.song-helper.plist"
PYTHON_BIN="$(command -v python3)"

mkdir -p "$NOVA_DIR"
mkdir -p "$HOME/Library/LaunchAgents"

copy_if_needed() {
  local name="$1"
  local src="$SCRIPT_DIR/$name"
  local dst="$NOVA_DIR/$name"
  if [ ! -e "$src" ]; then
    return
  fi
  if [ "$src" = "$dst" ]; then
    return
  fi
  if [ -d "$src" ]; then
    rm -rf "$dst"
    cp -R "$src" "$dst"
  else
    cp "$src" "$dst"
  fi
}

copy_if_needed "link_helper_server.py"
copy_if_needed "song_links.html"
copy_if_needed "song_search_links.example.txt"
copy_if_needed "add-to-songs-extension"

if [ ! -f "$NOVA_DIR/song_search_links.txt" ]; then
  if [ -f "$NOVA_DIR/song_search_links.example.txt" ]; then
    cp "$NOVA_DIR/song_search_links.example.txt" "$NOVA_DIR/song_search_links.txt"
  else
    touch "$NOVA_DIR/song_search_links.txt"
  fi
fi

if [ ! -f "$NOVA_DIR/nova_helper_config.json" ]; then
  cat > "$NOVA_DIR/nova_helper_config.json" <<JSON
{
  "root": "$NOVA_DIR",
  "host": "127.0.0.1",
  "port": 8765,
  "songs_file": "$NOVA_DIR/songs.txt",
  "links_file": "$NOVA_DIR/song_search_links.txt",
  "done_file": "$NOVA_DIR/song_links_done.json",
  "pending_file": "$NOVA_DIR/song_links_pending.json",
  "download_log_file": "$NOVA_DIR/yt_dlp_download.log",
  "download_status_file": "$NOVA_DIR/yt_dlp_status.json",
  "sd_card": "/Volumes/Untitled",
  "auth": {
    "enabled": false,
    "username": "",
    "password": "",
    "api_token": ""
  }
}
JSON
fi

touch "$NOVA_DIR/songs.txt"

for tool in yt-dlp ffmpeg ffprobe deno; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing $tool. Install dependencies with:"
    echo "  brew install yt-dlp ffmpeg deno"
    exit 1
  fi
done

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.nova.song-helper</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>$NOVA_DIR/link_helper_server.py</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$NOVA_DIR/helper.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$NOVA_DIR/helper.stderr.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl kickstart -k "gui/$(id -u)/com.nova.song-helper"

echo "Nova helper installed."
echo "Directory: $NOVA_DIR"
echo "Config: $NOVA_DIR/nova_helper_config.json"
echo "Health: http://127.0.0.1:8765/health"
echo "Open local page: $NOVA_DIR/song_links.html"
