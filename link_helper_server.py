#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
import html
import json
import os
import re
import shutil
import subprocess
import threading
import time
import unicodedata

DEFAULT_ROOT = Path(os.environ.get("NOVA_ROOT", "~/Desktop/nova")).expanduser()
CONFIG_FILE = Path(os.environ.get("NOVA_CONFIG", DEFAULT_ROOT / "nova_helper_config.json")).expanduser()


def load_config() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


CONFIG = load_config()
ROOT = Path(CONFIG.get("root", DEFAULT_ROOT)).expanduser()
HOST = CONFIG.get("host", "127.0.0.1")
PORT = int(CONFIG.get("port", os.environ.get("NOVA_PORT", 8765)))
SONGS_FILE = Path(CONFIG.get("songs_file", ROOT / "songs.txt")).expanduser()
LINKS_FILE = Path(CONFIG.get("links_file", ROOT / "song_search_links.txt")).expanduser()
DONE_FILE = Path(CONFIG.get("done_file", ROOT / "song_links_done.json")).expanduser()
PENDING_FILE = Path(CONFIG.get("pending_file", ROOT / "song_links_pending.json")).expanduser()
DOWNLOAD_LOG_FILE = Path(CONFIG.get("download_log_file", ROOT / "yt_dlp_download.log")).expanduser()
DOWNLOAD_STATUS_FILE = Path(CONFIG.get("download_status_file", ROOT / "yt_dlp_status.json")).expanduser()
SD_CARD = Path(CONFIG.get("sd_card", "/Volumes/Untitled")).expanduser()
REMOVED_DIR_NAME = "_Removed_By_Helper"
LOCAL_DUPLICATES_DIR_NAME = "_Already_On_Card"
PENDING_MAX_AGE_SECONDS = 60 * 60
DOWNLOAD_PROCESS = None

REMOVE_WORDS = {
    "official",
    "audio",
    "video",
    "lyrics",
    "lyric",
    "tekst",
    "text",
    "hd",
    "hq",
    "4k",
    "stage",
    "performance",
    "album",
    "live",
    "spot",
}


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback.copy() if isinstance(fallback, dict) else fallback


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def clean_title(value: str) -> str:
    value = re.sub(r"\s*-\s*YouTube\s*$", "", value or "", flags=re.I)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:180] or "Added from YouTube"


def fold_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode("ascii")
    return value.lower()


def normalize_song_key(value: str) -> str:
    value = Path(value).stem
    value = re.sub(r"\[[A-Za-z0-9_-]{8,}\]\s*$", "", value)
    value = re.sub(r"\([^)]*(official|audio|video|lyric|lyrics|tekst|text|hd|hq|4k|tv|live|album|20\d{2}|19\d{2})[^)]*\)", " ", value, flags=re.I)
    value = re.sub(r"\[[^\]]*(official|audio|video|lyric|lyrics|tekst|text|hd|hq|4k|tv|live|album|20\d{2}|19\d{2})[^\]]*\]", " ", value, flags=re.I)
    value = fold_text(value)
    value = re.sub(r"\b(20\d{2}|19\d{2})\b", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    words = [word for word in value.split() if word not in REMOVE_WORDS]
    return " ".join(words)


def possible_song_keys(value: str) -> set[str]:
    value = Path(value).stem
    keys = {normalize_song_key(value)}
    if " - " in value:
        keys.add(normalize_song_key(value.split(" - ", 1)[1]))
    return {key for key in keys if key}


def is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def unique_target(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    index = 2
    while True:
        candidate = path.with_name(f"{stem} ({index}){suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def scan_music_library() -> dict:
    if not SD_CARD.exists():
        return {
            "ok": False,
            "mounted": False,
            "root": str(SD_CARD),
            "total": 0,
            "folders": [],
        }

    grouped: dict[str, list[dict]] = {}
    for path in sorted(SD_CARD.rglob("*.mp3")):
        if path.name.startswith("._"):
            continue

        try:
            relative = path.relative_to(SD_CARD)
        except ValueError:
            continue

        if REMOVED_DIR_NAME in relative.parts:
            continue

        folder = relative.parts[0] if len(relative.parts) > 1 else "(root)"
        try:
            stat = path.stat()
            size = stat.st_size
            updated_at = int(stat.st_mtime)
        except OSError:
            size = 0
            updated_at = 0

        grouped.setdefault(folder, []).append(
            {
                "name": path.name,
                "title": path.stem,
                "folder": folder,
                "path": str(path),
                "relativePath": str(relative),
                "size": size,
                "updatedAt": updated_at,
                "key": normalize_song_key(path.name),
            }
        )

    folders = [
        {
            "name": folder,
            "count": len(items),
            "songs": sorted(items, key=lambda item: fold_text(item["name"])),
        }
        for folder, items in sorted(grouped.items(), key=lambda item: fold_text(item[0]))
    ]

    return {
        "ok": True,
        "mounted": True,
        "root": str(SD_CARD),
        "total": sum(folder["count"] for folder in folders),
        "folders": folders,
    }


def duplicate_groups() -> dict:
    library = scan_music_library()
    if not library.get("ok"):
        return {**library, "duplicates": []}

    grouped: dict[str, list[dict]] = {}
    for folder in library["folders"]:
        for song in folder["songs"]:
            key = song["key"]
            if key:
                grouped.setdefault(key, []).append(song)

    duplicates = [
        {
            "key": key,
            "count": len(items),
            "songs": sorted(items, key=lambda item: (fold_text(item["folder"]), fold_text(item["name"]))),
        }
        for key, items in grouped.items()
        if len(items) > 1
    ]
    duplicates.sort(key=lambda item: (-item["count"], item["key"]))

    return {
        "ok": True,
        "mounted": True,
        "root": str(SD_CARD),
        "groups": len(duplicates),
        "duplicateSongs": sum(item["count"] for item in duplicates),
        "duplicates": duplicates,
    }


def recommendation_items(limit: int = 120) -> dict:
    library = scan_music_library()
    if not library.get("ok"):
        return {**library, "items": []}

    library_keys = set()
    for folder in library["folders"]:
        for song in folder["songs"]:
            library_keys.update(possible_song_keys(song["name"]))
    done = read_json(DONE_FILE, {})
    seen_titles: set[str] = set()
    items = []

    for item in parse_song_links():
        keys = possible_song_keys(item["title"])
        key = sorted(keys, key=len, reverse=True)[0] if keys else ""
        if not key or keys.intersection(library_keys) or item["sourceId"] in done or key in seen_titles:
            continue
        seen_titles.add(key)
        items.append(
            {
                "sourceId": item["sourceId"],
                "title": item["title"],
                "url": item["url"],
                "section": item["section"],
                "reason": "Nije pronađeno na kartici",
            }
        )
        if len(items) >= limit:
            break

    return {
        "ok": True,
        "mounted": True,
        "root": str(SD_CARD),
        "count": len(items),
        "items": items,
    }


def remove_song(path_value: str) -> dict:
    source = Path(path_value)
    if not source.exists():
        raise ValueError("File does not exist.")
    if source.name.startswith("._") or source.suffix.lower() != ".mp3":
        raise ValueError("Only visible MP3 files can be removed.")
    if not is_inside(source, SD_CARD):
        raise ValueError("File is not on the SD card.")

    relative = source.resolve().relative_to(SD_CARD.resolve())
    if REMOVED_DIR_NAME in relative.parts:
        raise ValueError("File is already in removed folder.")

    removed_dir = SD_CARD / REMOVED_DIR_NAME / relative.parent
    removed_dir.mkdir(parents=True, exist_ok=True)
    target = unique_target(removed_dir / source.name)
    shutil.move(str(source), str(target))

    sidecar_source = source.with_name("._" + source.name)
    sidecar_target = None
    if sidecar_source.exists():
        sidecar_target = unique_target(removed_dir / sidecar_source.name)
        shutil.move(str(sidecar_source), str(sidecar_target))

    return {
        "ok": True,
        "removedTo": str(target),
        "sidecarRemovedTo": str(sidecar_target) if sidecar_target else "",
    }


def sd_card_folder_names() -> list[str]:
    if not SD_CARD.exists():
        return []
    return sorted(
        [
            path.name
            for path in SD_CARD.iterdir()
            if path.is_dir()
            and not path.name.startswith(".")
            and path.name != REMOVED_DIR_NAME
        ],
        key=fold_text,
    )


def existing_sd_keys() -> set[str]:
    keys = set()
    if not SD_CARD.exists():
        return keys
    for path in SD_CARD.rglob("*.mp3"):
        if path.name.startswith("._"):
            continue
        try:
            relative = path.relative_to(SD_CARD)
        except ValueError:
            continue
        if REMOVED_DIR_NAME in relative.parts:
            continue
        keys.update(possible_song_keys(path.name))
    return keys


def guess_folder_for_download(name: str) -> str:
    value = fold_text(name)
    rules = [
        ("02_BiH_Reprezentacija", ["bosna", "bih", "zmajevi", "reprezentacija", "world cup"]),
        ("04_Sevdah_Duhovnjak", ["safet isovic", "amira medunjanin", "sevdah"]),
        (
            "05_Yugo_Rock",
            [
                "bijelo dugme",
                "crvena jabuka",
                "azra",
                "ekv",
                "ekatarina",
                "bajaga",
                "parni valjak",
                "prljavo kazaliste",
                "plavi orkestar",
                "zabranjeno pusenje",
                "riblja corba",
                "yu grupa",
                "indexi",
            ],
        ),
        (
            "06_Pop_Rock",
            [
                "dino merlin",
                "merlin",
                "zdravko colic",
                "zeljko joksimovic",
                "tose proeski",
                "hari mata hari",
                "oliver",
                "gibonni",
                "magazin",
                "severina",
                "jelena rozga",
                "danijela",
                "marija serifovic",
                "al dino",
                "emina",
                "dzejla",
                "kaliopi",
            ],
        ),
        (
            "08_Party_Udri",
            [
                "milica",
                "aleksandra prijovic",
                "senidah",
                "voyage",
                "nucci",
                "tea tairovic",
                "teodora",
                "sara jo",
                "nikolija",
                "maya berovic",
                "buba",
                "jala",
                "hurricane",
                "colonia",
                "grse",
                "rasta",
                "devito",
                "breskvica",
                "edit",
            ],
        ),
        (
            "11_Moderni_Folk_Pop",
            [
                "mirza selimovic",
                "dzenan loncarevic",
                "lexington",
                "aco pejovic",
                "sasa matic",
                "amar gile",
                "tropico",
                "amadeus",
                "pedja",
                "zeljko samardzic",
                "dejan matic",
                "dado polumenta",
            ],
        ),
        (
            "03_Narodnjaci",
            [
                "halid beslic",
                "hanka paldum",
                "saban saulic",
                "toma zdravkovic",
                "sinan sakic",
                "ana bekuta",
                "lepa brena",
                "dragana mirkovic",
                "vesna zmijanac",
                "nada topcagic",
                "zorica brunclik",
            ],
        ),
    ]
    for folder, patterns in rules:
        if any(pattern in value for pattern in patterns):
            return folder
    return "10_Mix"


def downloaded_music() -> dict:
    folders = sd_card_folder_names()
    keys = existing_sd_keys()
    songs = []
    for path in sorted(SONGS_FILE.parent.glob("*.mp3"), key=lambda item: fold_text(item.name)):
        if path.name.startswith("._"):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        song_keys = possible_song_keys(path.name)
        songs.append(
            {
                "name": path.name,
                "title": path.stem,
                "path": str(path),
                "size": stat.st_size,
                "updatedAt": int(stat.st_mtime),
                "suggestedFolder": guess_folder_for_download(path.name),
                "alreadyOnCard": bool(song_keys.intersection(keys)),
            }
        )
    return {
        "ok": True,
        "downloadDir": str(SONGS_FILE.parent),
        "count": len(songs),
        "folders": folders,
        "songs": songs,
    }


def move_downloaded_song(path_value: str, folder: str, skip_duplicate: bool = True) -> dict:
    source = Path(path_value)
    download_root = SONGS_FILE.parent.resolve()
    if not source.exists():
        raise ValueError("Downloaded file does not exist.")
    if source.name.startswith("._") or source.suffix.lower() != ".mp3":
        raise ValueError("Only visible MP3 files can be moved.")
    if not is_inside(source, download_root):
        raise ValueError("File is not inside ~/Desktop/nova.")

    folders = set(sd_card_folder_names())
    if folder not in folders:
        raise ValueError("Target folder does not exist on SD card.")

    song_keys = possible_song_keys(source.name)
    if skip_duplicate and song_keys.intersection(existing_sd_keys()):
        duplicate_dir = SONGS_FILE.parent / LOCAL_DUPLICATES_DIR_NAME
        duplicate_dir.mkdir(parents=True, exist_ok=True)
        target = unique_target(duplicate_dir / source.name)
        shutil.move(str(source), str(target))
        return {
            "ok": True,
            "skippedDuplicate": True,
            "movedTo": str(target),
            "message": "Already on SD card. Moved local copy to _Already_On_Card.",
        }

    target = unique_target(SD_CARD / folder / source.name)
    shutil.move(str(source), str(target))

    sidecar_source = source.with_name("._" + source.name)
    if sidecar_source.exists():
        shutil.move(str(sidecar_source), str(unique_target(target.with_name("._" + target.name))))

    return {
        "ok": True,
        "skippedDuplicate": False,
        "movedTo": str(target),
        "message": f"Moved to {folder}.",
    }


def ytdlp_binary() -> str:
    for value in ["/opt/homebrew/bin/yt-dlp", "/usr/local/bin/yt-dlp"]:
        if Path(value).exists():
            return value

    found = shutil.which("yt-dlp")
    if found:
        return found

    raise ValueError("yt-dlp nije pronađen.")


def ffmpeg_location_args() -> list[str]:
    for directory in ["/opt/homebrew/bin", "/usr/local/bin"]:
        if (Path(directory) / "ffmpeg").exists() and (Path(directory) / "ffprobe").exists():
            return ["--ffmpeg-location", directory]
    return []


def js_runtime_args() -> list[str]:
    for value in ["/opt/homebrew/bin/deno", "/usr/local/bin/deno"]:
        if Path(value).exists():
            return ["--js-runtimes", f"deno:{value}"]
    return []


def songs_txt_url_count() -> int:
    if not SONGS_FILE.exists():
        return 0
    return sum(
        1
        for line in SONGS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("http")
    )


def download_command() -> list[str]:
    return [
        ytdlp_binary(),
        *js_runtime_args(),
        *ffmpeg_location_args(),
        "-x",
        "--audio-format",
        "mp3",
        "-P",
        str(SONGS_FILE.parent),
        "-a",
        str(SONGS_FILE),
    ]


def current_download_status() -> dict:
    status = read_json(DOWNLOAD_STATUS_FILE, {})
    global DOWNLOAD_PROCESS
    if DOWNLOAD_PROCESS and DOWNLOAD_PROCESS.poll() is None:
        status["running"] = True
        status["pid"] = DOWNLOAD_PROCESS.pid
    elif status.get("running"):
        status["running"] = False

    status.setdefault("running", False)
    status.setdefault("log", str(DOWNLOAD_LOG_FILE))
    status.setdefault("songsFile", str(SONGS_FILE))
    status.setdefault("urlCount", songs_txt_url_count())
    status["tail"] = download_log_tail()
    return status


def download_log_tail(lines: int = 80) -> str:
    if not DOWNLOAD_LOG_FILE.exists():
        return ""
    try:
        return "\n".join(DOWNLOAD_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except Exception:
        return ""


def monitor_download(process: subprocess.Popen) -> None:
    exit_code = process.wait()
    cleared_songs_file = False
    if exit_code == 0:
        SONGS_FILE.write_text("", encoding="utf-8")
        cleared_songs_file = True

    status = read_json(DOWNLOAD_STATUS_FILE, {})
    status.update(
        {
            "ok": exit_code == 0,
            "running": False,
            "exitCode": exit_code,
            "finishedAt": int(time.time()),
            "urlCount": songs_txt_url_count(),
            "clearedSongsFile": cleared_songs_file,
        }
    )
    write_json(DOWNLOAD_STATUS_FILE, status)


def start_download() -> dict:
    global DOWNLOAD_PROCESS
    if DOWNLOAD_PROCESS and DOWNLOAD_PROCESS.poll() is None:
        return current_download_status()

    url_count = songs_txt_url_count()
    if url_count == 0:
        raise ValueError("songs.txt nema nijedan URL za download.")

    command = download_command()
    DOWNLOAD_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DOWNLOAD_LOG_FILE.open("a", encoding="utf-8") as log:
        log.write("\n\n")
        log.write(f"=== {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        log.write(" ".join(command) + "\n")
        log.flush()
        DOWNLOAD_PROCESS = subprocess.Popen(
            command,
            cwd=str(SONGS_FILE.parent),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )

    status = {
        "ok": True,
        "running": True,
        "pid": DOWNLOAD_PROCESS.pid,
        "startedAt": int(time.time()),
        "command": " ".join(command),
        "log": str(DOWNLOAD_LOG_FILE),
        "songsFile": str(SONGS_FILE),
        "urlCount": url_count,
    }
    write_json(DOWNLOAD_STATUS_FILE, status)
    threading.Thread(target=monitor_download, args=(DOWNLOAD_PROCESS,), daemon=True).start()
    status["tail"] = download_log_tail()
    return status


def parse_song_links() -> list[dict]:
    if not LINKS_FILE.exists():
        return []

    items = []
    section = "Songs"
    pending_title = ""

    for raw in LINKS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.lower().startswith("batch "):
            section = line
            pending_title = ""
        elif line.startswith("http"):
            if pending_title:
                index = len(items) + 1
                items.append(
                    {
                        "sourceId": f"song-{index}",
                        "title": pending_title,
                        "url": line,
                        "section": section,
                    }
                )
                pending_title = ""
        else:
            pending_title = line

    return items


def next_unresolved(after_source_id: str = "") -> dict:
    done = read_json(DONE_FILE, {})
    items = parse_song_links()
    start_index = 0

    if after_source_id:
        for index, item in enumerate(items):
            if item["sourceId"] == after_source_id:
                start_index = index + 1
                break

    ordered_items = items[start_index:] + items[:start_index]
    for item in ordered_items:
        if item["sourceId"] not in done:
            set_pending(item["sourceId"], item["title"])
            return item
    return {}


def canonicalize_youtube_url(value: str) -> str:
    parsed = urlparse(value.strip())
    host = parsed.netloc.lower().removeprefix("www.")

    video_id = ""
    if host in {"youtube.com", "m.youtube.com", "music.youtube.com"} and parsed.path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    elif host == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0]
    elif host in {"youtube.com", "m.youtube.com"} and parsed.path.startswith("/shorts/"):
        video_id = parsed.path.split("/")[2]

    if not video_id:
        raise ValueError("Open a YouTube video page first.")

    return f"https://www.youtube.com/watch?{urlencode({'v': video_id})}"


def append_song(title: str, url: str) -> tuple[bool, str]:
    SONGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = SONGS_FILE.read_text(encoding="utf-8") if SONGS_FILE.exists() else ""

    if url in existing:
        return False, "Already exists in songs.txt"

    prefix = "" if existing.endswith("\n\n") or not existing else "\n"
    with SONGS_FILE.open("a", encoding="utf-8") as file:
        file.write(f"{prefix}# {title}\n{url}\n\n")

    return True, "Added to songs.txt"


def mark_done(source_id: str, title: str, url: str = "", done: bool = True) -> None:
    if not source_id:
        return

    values = read_json(DONE_FILE, {})
    if done:
        values[source_id] = {
            "title": title,
            "url": url,
            "updatedAt": int(time.time()),
        }
    else:
        values.pop(source_id, None)
    write_json(DONE_FILE, values)


def mark_pending_done(url: str = "", skipped: bool = False) -> dict:
    pending = read_json(PENDING_FILE, {})
    created_at = int(pending.get("createdAt", 0) or 0)

    if pending and time.time() - created_at <= PENDING_MAX_AGE_SECONDS:
        source_id = str(pending.get("sourceId", ""))
        title = str(pending.get("title", ""))
        mark_done(source_id, title, url, done=True)

        values = read_json(DONE_FILE, {})
        if source_id in values:
            values[source_id]["skipped"] = skipped
            write_json(DONE_FILE, values)

        try:
            PENDING_FILE.unlink()
        except FileNotFoundError:
            pass
        return pending

    return {}


def set_pending(source_id: str, title: str) -> None:
    write_json(
        PENDING_FILE,
        {
            "sourceId": source_id,
            "title": title,
            "createdAt": int(time.time()),
        },
    )


def consume_pending(url: str) -> dict:
    return mark_pending_done(url, skipped=False)


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self.respond_text("ok")
            return

        if parsed.path == "/config":
            self.respond_json(
                {
                    "ok": True,
                    "root": str(ROOT),
                    "configFile": str(CONFIG_FILE),
                    "songsFile": str(SONGS_FILE),
                    "linksFile": str(LINKS_FILE),
                    "downloadDir": str(SONGS_FILE.parent),
                    "sdCard": str(SD_CARD),
                    "host": HOST,
                    "port": PORT,
                }
            )
            return

        if parsed.path == "/done":
            self.respond_json(read_json(DONE_FILE, {}))
            return

        if parsed.path == "/clear-done":
            write_json(DONE_FILE, {})
            self.respond_json({"ok": True})
            return

        if parsed.path == "/library":
            self.respond_json(scan_music_library())
            return

        if parsed.path == "/duplicates":
            self.respond_json(duplicate_groups())
            return

        if parsed.path == "/recommendations":
            params = parse_qs(parsed.query)
            try:
                limit = int(params.get("limit", ["120"])[0])
            except ValueError:
                limit = 120
            self.respond_json(recommendation_items(max(1, min(limit, 500))))
            return

        if parsed.path == "/remove-song":
            params = parse_qs(parsed.query)
            try:
                result = remove_song(params.get("path", [""])[0])
                self.respond_json(result)
            except Exception as error:
                self.respond_json({"ok": False, "error": str(error)}, status=400)
            return

        if parsed.path == "/download-songs":
            try:
                self.respond_json(start_download())
            except Exception as error:
                self.respond_json({"ok": False, "error": str(error), **current_download_status()}, status=400)
            return

        if parsed.path == "/download-status":
            self.respond_json(current_download_status())
            return

        if parsed.path == "/downloaded-music":
            self.respond_json(downloaded_music())
            return

        if parsed.path == "/move-downloaded":
            params = parse_qs(parsed.query)
            try:
                skip_duplicate = params.get("skipDuplicate", ["true"])[0].lower() not in {"0", "false", "no"}
                result = move_downloaded_song(
                    params.get("path", [""])[0],
                    params.get("folder", [""])[0],
                    skip_duplicate=skip_duplicate,
                )
                self.respond_json(result)
            except Exception as error:
                self.respond_json({"ok": False, "error": str(error)}, status=400)
            return

        if parsed.path == "/pending":
            params = parse_qs(parsed.query)
            source_id = params.get("sourceId", [""])[0]
            title = clean_title(params.get("title", [""])[0])
            set_pending(source_id, title)
            self.respond_json({"ok": True, "sourceId": source_id, "title": title})
            return

        if parsed.path == "/next":
            item = next_unresolved()
            self.respond_json({"ok": bool(item), "next": item})
            return

        if parsed.path == "/skip":
            pending = mark_pending_done(skipped=True)
            item = next_unresolved(str(pending.get("sourceId", "")))
            self.respond_json(
                {
                    "ok": True,
                    "skipped": bool(pending),
                    "pending": pending,
                    "next": item,
                }
            )
            return

        if parsed.path == "/mark":
            params = parse_qs(parsed.query)
            source_id = params.get("sourceId", [""])[0]
            title = clean_title(params.get("title", [""])[0])
            is_done = params.get("done", ["true"])[0].lower() not in {"0", "false", "no"}
            mark_done(source_id, title, done=is_done)
            self.respond_json({"ok": True, "sourceId": source_id, "done": is_done})
            return

        if parsed.path not in {"/add", "/accept"}:
            self.respond_text("Use /add?url=...&title=...", status=404)
            return

        params = parse_qs(parsed.query)
        raw_url = params.get("url", [""])[0]
        title = clean_title(params.get("title", [""])[0])

        try:
            url = canonicalize_youtube_url(raw_url)
            added, message = append_song(title, url)
            pending = consume_pending(url)
            status = "OK" if added else "SKIP"
            if pending:
                message = f"{message}. Marked source card done."
            item = next_unresolved(str(pending.get("sourceId", ""))) if parsed.path == "/accept" else {}
            if parsed.path == "/accept":
                self.respond_json(
                    {
                        "ok": True,
                        "status": status,
                        "message": message,
                        "title": title,
                        "url": url,
                        "pending": pending,
                        "next": item,
                    }
                )
            else:
                body = self.page(status, message, title, url)
                self.respond_html(body)
        except Exception as error:
            body = self.page("ERROR", str(error), title, raw_url)
            self.respond_html(body, status=400)

    def page(self, status: str, message: str, title: str, url: str) -> str:
        return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(status)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; margin: 32px; line-height: 1.4; }}
    code {{ overflow-wrap: anywhere; }}
    button {{ padding: 8px 12px; }}
  </style>
</head>
<body>
  <h1>{html.escape(status)}</h1>
  <p>{html.escape(message)}</p>
  <p><strong>{html.escape(title)}</strong></p>
  <p><code>{html.escape(url)}</code></p>
  <button onclick="window.close()">Close</button>
</body>
</html>"""

    def respond_text(self, body: str, status: int = 200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def respond_html(self, body: str, status: int = 200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def respond_json(self, body, status: int = 200):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print(fmt % args)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Listening on http://{HOST}:{PORT}")
    print(f"Appending to {SONGS_FILE}")
    server.serve_forever()


if __name__ == "__main__":
    main()
