"""Read-only projections for the plugin page; no subscription or download writes."""

import math
from collections import Counter
from pathlib import PurePosixPath


def download_cards(registry, tracks, read_download=None):
    cards = []
    for torrent_hash, entry in sorted(registry.items(), key=lambda pair: pair[1].get("at", 0), reverse=True)[:6]:
        songs = [tracks[mid].get("song", {}) for mid in entry.get("matches", {}) if mid in tracks]
        albums = list(dict.fromkeys(song.get("album") for song in songs if song.get("album")))
        artists = list(dict.fromkeys(artist for song in songs for artist in song.get("artists", [])))
        card = {
            "id": torrent_hash, "title": albums[0] if len(albums) == 1 else "歌单选曲",
            "artists": artists, "resource": entry.get("title", ""),
            "files": [PurePosixPath(name).name for name in entry.get("files", [])],
            "selected": len(entry.get("files", [])), "total": entry.get("audio_count"),
            "phase": entry.get("phase", ""), "error": entry.get("error", ""),
            "at": entry.get("at"), "state": None, "progress": None, "live_error": "",
        }
        if read_download:
            try:
                live = read_download(torrent_hash)
                if not live.get("success"):
                    raise ValueError("download unavailable")
                card["state"] = live.get("state")
                progress = live.get("progress")
                if isinstance(progress, (int, float)) and math.isfinite(progress):
                    card["progress"] = max(0, min(1, progress))
            except Exception:
                card["live_error"] = "暂时无法读取下载器进度，可稍后刷新"
        cards.append(card)
    return cards


def page_projection(state, overview, config, settings, registry, checks, adapter_error="", lifecycle=None):
    songs = []
    for mid, item in state.get("tracks", {}).items():
        if not item.get("present"):
            continue
        song = item.get("song", {})
        base_status = {"subscribed": "searching", "library": "unknown"}.get(item.get("status"), item.get("status", "pending"))
        songs.append({"id": mid, "title": song.get("title", ""), "artists": list(song.get("artists", [])),
                      "album": song.get("album", ""), "subscription_status": item.get("status", "pending"),
                      "status": base_status, "playlist_ids": list(item.get("playlist_ids", [])),
                      **(lifecycle or {}).get("states", {}).get(mid, {})})
    playlists = [{key: entry.get(key) for key in ("id", "title", "source", "cover_url", "total", "last_fetch", "last_error")}
                 for entry in overview.get("playlists", [])]
    return {
        "success": True,
        "overview": {key: overview.get(key, 0) for key in
                     ("tracked", "subscribed", "library", "pending", "failed", "last_sync", "last_fetch", "last_error")},
        "enabled": bool(config.get("enabled")), "dry_run": bool(config.get("dry_run")),
        "interval_minutes": config.get("interval", 60), "immediate_search": bool(config.get("immediate_search")),
        "adapter_error": adapter_error, "playlists": playlists, "songs": songs,
        "status_counts": dict(Counter(song["status"] for song in songs)),
        "status_updated_at": None, "status_warning": "",
        "unavailable": len(overview.get("playlist", {}).get("unavailable", [])),
        "settings": {key: settings.get(key) for key in
                     ("downloader", "save_path", "library_path", "follow_mp", "error")},
        "downloads": download_cards(registry, state.get("tracks", {})),
        "checks": [{key: check.get(key) for key in ("at", "title", "allowed", "reason")}
                   for check in checks if check.get("version")][-8:][::-1],
    }
