# Nova Music Helper

Local helper and browser UI for building an MP3 collection for a car SD card.

This project is macOS-only. The web page can be hosted anywhere, but file access and downloads are handled by a small local helper server running on the Mac that has the SD card mounted.

## Disclaimer

This project is only a local helper for managing music files and user-provided links on the computer where it is installed. Use it only with content you are allowed to access, download, copy, or convert, and follow the terms of the services you use.

The repository intentionally does not include a copyrighted song-link catalog. Personal queues such as `songs.txt` and `song_search_links.txt` are local-only files on each user's computer and are ignored by git.

## What It Does

- Shows music already on the SD card, grouped by folder
- Searches/filter songs on the card
- Finds likely duplicate MP3 files
- Moves removed files into `_Removed_By_Helper` instead of deleting them
- Shows song suggestions that are not already on the SD card
- Adds accepted YouTube links to `songs.txt`
- Runs `yt-dlp` to download `songs.txt` into `~/Desktop/nova`
- Clears `songs.txt` after a successful download
- Shows newly downloaded MP3s and moves them to a selected SD card folder
- Supports a Chrome extension shortcut flow:
  - `Cmd+Shift+Y` accepts the current YouTube video
  - `Cmd+Shift+N` skips it

## Architecture

There are two parts:

1. `song_links.html`
   - The browser UI
   - Can be opened locally or hosted on GitHub Pages/any static host

2. `link_helper_server.py`
   - Local server at `http://127.0.0.1:8765`
   - Reads the SD card
   - Runs `yt-dlp`
   - Moves files
   - Writes `songs.txt`
   - Reads local-only suggestions from `song_search_links.txt`

The hosted page cannot do those local filesystem operations by itself because browsers sandbox file access. The local helper is required on every computer/account where you want this workflow to work.

## Requirements

macOS only, with:

```bash
brew install yt-dlp ffmpeg deno
```

Python 3 is also required and is usually already available on macOS.

## Install

Copy or clone this project into:

```text
~/Desktop/nova
```

Run:

```bash
cd ~/Desktop/nova
./install_nova_helper.sh
```

You can also double-click this file from Finder after cloning/downloading the full project:

```text
install_nova_helper.command
```

Verify:

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/config
```

The installer creates a LaunchAgent:

```text
~/Library/LaunchAgents/com.nova.song-helper.plist
```

## Configuration

Config file:

```text
~/Desktop/nova/nova_helper_config.json
```

Default SD card path:

```json
"sd_card": "/Volumes/Untitled"
```

If your SD card has another name, change that value, then restart:

```bash
launchctl kickstart -k gui/$(id -u)/com.nova.song-helper
```

## Browser Page

Open locally:

```text
~/Desktop/nova/song_links.html
```

Or upload `song_links.html` to a static host.

GitHub Pages URL for this repo:

```text
https://d3xt3r2909.github.io/car-sd-music-helper/
```

By default, the page talks to:

```text
http://127.0.0.1:8765
```

To override the helper URL:

```text
https://your-site.example/song_links.html?helper=http://127.0.0.1:8765
```

The page stores the helper URL in browser localStorage.

The hosted page includes a setup panel with helper status, copyable setup commands, and project download links. It can check `http://127.0.0.1:8765`, but it cannot install the helper by itself because browsers cannot write LaunchAgents or access the local filesystem.

## Page Visits

GitHub Pages is static hosting, so this project does not count visits by itself.

Options:

- Use GitHub repository `Insights` -> `Traffic` for basic repository traffic.
- Add an external analytics snippet to `song_links.html` for real page views, for example Cloudflare Web Analytics, GoatCounter, Plausible, or Umami.

Keep analytics snippets public-safe: do not put private API keys or secrets into the HTML.

## Chrome Extension

The Chrome extension is included in this repository at `add-to-songs-extension/`. It stores only the local helper URL in browser extension storage.

Install the extension for the YouTube shortcut flow:

1. Open `chrome://extensions`
2. Enable Developer mode
3. Click `Load unpacked`
4. Select:

```text
~/Desktop/nova/add-to-songs-extension
```

Shortcuts:

- `Cmd+Shift+Y`: accept current YouTube video and open next suggestion
- `Cmd+Shift+N`: skip current suggestion and open next suggestion

If shortcuts do not work, open:

```text
chrome://extensions/shortcuts
```

and confirm they are assigned.

## Normal Workflow

1. Open `song_links.html`
2. Use the `Songs` section to find suggestions missing from the SD card
3. Click `Search`
4. Open the right YouTube result
5. Press `Cmd+Shift+Y` to accept it
6. Repeat until `songs.txt` has the links you want
7. Click `Download songs.txt`
8. Use `Downloaded music` to move MP3s to the right SD card folder

## Generated/Local Files

These files are local state and usually should not be committed:

```text
songs.txt
song_search_links.txt
song_links_done.json
song_links_pending.json
yt_dlp_download.log
yt_dlp_status.json
helper.stdout.log
helper.stderr.log
nova_helper_config.json
_Already_On_Card/
```

## Troubleshooting

### The page does nothing

Check that the helper is running:

```bash
curl http://127.0.0.1:8765/health
```

Restart:

```bash
launchctl kickstart -k gui/$(id -u)/com.nova.song-helper
```

### SD card is empty or unavailable

Check the card path:

```bash
ls /Volumes
```

Then update `sd_card` in:

```text
~/Desktop/nova/nova_helper_config.json
```

### Download fails with ffmpeg missing

Install dependencies:

```bash
brew install yt-dlp ffmpeg deno
```

The helper passes explicit paths for Homebrew tools when possible.

### Hosted page cannot reach localhost

The helper includes CORS and Private Network Access headers. If the browser still blocks it, open the local page directly or use:

```text
?helper=http://127.0.0.1:8765
```

## Safety Notes

- `Remove` does not permanently delete SD card files. It moves them to `_Removed_By_Helper`.
- Successful downloads clear `songs.txt`; failed downloads keep it for retry.
- Duplicate local downloads are moved to `_Already_On_Card` when `Skip duplicates` is enabled.
