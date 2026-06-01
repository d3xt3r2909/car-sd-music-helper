# Nova Music Helper - Portable Setup

This setup has two parts:

1. Hosted page: `song_links.html`
2. Local helper: `link_helper_server.py` running on the computer/account that has the SD card

The hosted page can show the UI, but the local helper is required for:

- reading `/Volumes/Untitled`
- finding duplicates
- running `yt-dlp`
- clearing `songs.txt`
- moving downloaded MP3 files to the SD card
- keyboard accept/skip flow from the Chrome extension

## Disclaimer

This is a local workflow tool. It does not grant rights to download, copy, convert, or redistribute music. Each user is responsible for using it only with content they are allowed to access and for following the terms of the services they use.

Personal link files stay on the computer/account where the helper is installed:

```text
~/Desktop/nova/songs.txt
~/Desktop/nova/song_search_links.txt
```

Those files should not be uploaded to GitHub. The repo/bundle should include only `song_search_links.example.txt` as a format example.

## Install On Another macOS Account

Copy this folder to the other account, then run:

```bash
cd ~/Desktop/nova
./install_nova_helper.sh
```

Or double-click this file after copying/downloading the full project:

```text
install_nova_helper.command
```

If dependencies are missing:

```bash
brew install yt-dlp ffmpeg deno
```

After install, verify:

```bash
curl http://127.0.0.1:8765/health
curl http://127.0.0.1:8765/config
```

## SD Card Name

Default SD card path is:

```text
/Volumes/Untitled
```

If the card has another name, edit:

```text
~/Desktop/nova/nova_helper_config.json
```

Change:

```json
"sd_card": "/Volumes/Untitled"
```

Then restart:

```bash
launchctl kickstart -k gui/$(id -u)/com.nova.song-helper
```

## Hosted Page

Upload `song_links.html` wherever you want. It will call:

```text
http://127.0.0.1:8765
```

If you need another helper URL/port, open the page once with:

```text
https://your-page.example/song_links.html?helper=http://127.0.0.1:8765
```

The page stores that helper URL in browser localStorage.

The hosted page has a `First setup on this Mac` panel. It can check whether the helper is running and copy the install commands, but it cannot install the helper directly from the browser.

## Chrome Extension

The extension is included in this folder/repository:

```text
add-to-songs-extension/
```

For `Cmd+Shift+Y` and `Cmd+Shift+N` on YouTube:

1. Open `chrome://extensions`
2. Enable Developer mode
3. Load unpacked
4. Select:

```text
~/Desktop/nova/add-to-songs-extension
```

The extension expects the helper on:

```text
http://127.0.0.1:8765
```

## Files That Should Travel Together

Minimum useful bundle:

```text
song_links.html
link_helper_server.py
song_search_links.example.txt
install_nova_helper.sh
install_nova_helper.command
add-to-songs-extension/
README.md
README_PORTABLE.md
.gitignore
```

Local/generated files do not need to be uploaded:

```text
songs.txt
song_search_links.txt
song_links_done.json
song_links_pending.json
yt_dlp_download.log
yt_dlp_status.json
helper.stdout.log
helper.stderr.log
```
