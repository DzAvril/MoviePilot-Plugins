"""Reuse verified tracks from registered download caches without changing qB tasks."""

from pathlib import Path

from .core import track_file_selection
from .seeding import checked_inventory, library_confirmed
from .selected import SelectionError


def cache_candidates(state, registry):
    tracks = state.get("tracks", {})
    songs = [item["song"] for item in tracks.values() if item.get("present")]
    result = {}
    for key, entry in registry.items():
        if (entry.get("download_mode") != "full_album" or entry.get("phase") != "started"
                or entry.get("error") or entry.get("cleanup", {}).get("state") in ("removing", "removed", "done")):
            continue
        target = next((tracks[mid]["song"] for mid in entry.get("matches", {}) if mid in tracks), None)
        if not target:
            continue
        plan = track_file_selection(target, entry.get("download_files", []), songs)
        if plan["allowed"]:
            result[key] = {mid: name for mid, name in plan["matches"].items() if mid in tracks and tracks[mid].get("present")}
    return result


def source_path(entry, filename):
    root = Path(entry["source_root"])
    return root if str(root) in entry.get("fullpaths", []) else root / filename


def cached_destination(entry, filename, transfers, settings):
    source = str(source_path(entry, filename))
    # 同一文件可能由辅种任务共用；原生整理记录按源文件去重，hash 不一定属于本次任务。
    rows = [row for row in transfers if row.get("src") == source
            and (row.get("src_storage") or "local") == "local"]
    if not rows:
        return None
    latest = max(rows, key=lambda row: row.get("id", 0))
    check = {**entry, "hash": str(latest.get("download_hash") or ""), "fullpaths": [source]}
    return latest["dest"] if library_confirmed(check, [latest], settings) else None


def completed_cached_file(entry, filename, row, rows, normalize):
    checked = checked_inventory(entry, row, rows, normalize)
    if any(part in str(row.get("state") or "").casefold() for part in ("checking", "error", "missing", "unknown")):
        raise SelectionError("缓存正在校验或下载异常，等待下次确认")
    files = dict(zip(checked["download_files"], rows))
    file = files.get(filename)
    path = source_path(entry, filename)
    if (not file or file.get("priority", 0) <= 0 or file.get("progress") != 1
            or not path.is_absolute() or path.resolve() != path or not path.is_file()
            or path.is_symlink() or path.stat().st_size <= 0 or path.stat().st_size != file.get("size")):
        raise SelectionError("缓存音轨尚未完整或文件已变化，保留订阅等待")
    return path


def cache_source_exists(item):
    try:
        path = Path(item.get("cache_source") or ".")
        return (path.is_absolute() and not path.is_symlink() and path.resolve() == path and path.is_file()
                and [path.stat().st_size, path.stat().st_mtime_ns] == item.get("cache_signature"))
    except OSError:
        return False


def allow_cached_track(entry, mid, filename):
    """Extend only the import whitelist; full download priorities remain untouched."""
    if filename not in entry["files"]:
        entry["files"].append(filename)
        entry["fullpaths"].append(str(source_path(entry, filename)))
        entry["cleanup"] = {}
    entry.setdefault("matches", {})[mid] = filename
