"""Retention of plugin bookkeeping; never delete music or native MP records."""

import math
from pathlib import Path, PurePosixPath

RETENTION_DAYS = 90
CLEANUP_INTERVAL = 86400


def expired(timestamp, now):
    return (isinstance(timestamp, (int, float)) and math.isfinite(timestamp)
            and 0 < timestamp <= now - RETENTION_DAYS * 86400)


def cleanup_due(state, now):
    last = state.get("last_cleanup", {}).get("at", 0)
    return not isinstance(last, (int, float)) or not math.isfinite(last) or now - last >= CLEANUP_INTERVAL or now < last


def local_source_absent(path):
    try:
        Path(path).lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def retired_download(entry, task, transfers, *, now, source_absent, file_exists):
    """Drop a guard only after its task and source are gone and every file is in library."""
    root = entry.get("source_root")
    paths = entry.get("fullpaths") or []
    if (entry.get("phase") != "started" or entry.get("error") or not expired(entry.get("at"), now)
            or not task.get("success") or task.get("state") != "missing"
            or not root or not PurePosixPath(root).is_absolute() or ".." in PurePosixPath(root).parts
            or not paths or len(paths) != len(entry.get("files", []))
            or any(".." in PurePosixPath(path).parts or not PurePosixPath(path).is_relative_to(root) for path in paths)
            or not source_absent(root)):
        return False
    latest = {}
    for row in transfers:
        if str(row.get("download_hash") or "").lower() != str(entry.get("hash") or "").lower():
            continue
        path = row.get("src")
        if row.get("id", 0) >= latest.get(path, {}).get("id", 0):
            latest[path] = row
    return all(path in latest and latest[path].get("status") is True
               and file_exists(latest[path].get("dest"), latest[path].get("dest_storage")) for path in paths)


def prune_history(state, registry, *, now, active_subscriptions):
    """Keep all current songs and all records needed by subscriptions or selection guards."""
    tracks = state.setdefault("tracks", {})
    protected = set(active_subscriptions)
    for entry in registry.values():
        protected.update(entry.get("matches", {}))
    removed = {mid for mid, item in tracks.items()
               if not item.get("present") and mid not in protected and expired(item.get("inactive_since"), now)}
    for mid in removed:
        del tracks[mid]
    aliases = state.get("identity_aliases", {})
    retired_aliases = [alias for alias, mid in aliases.items() if mid in removed]
    for alias in retired_aliases:
        del aliases[alias]
    playlists = state.get("playlists", {})
    retired_playlists = [pid for pid, entry in playlists.items()
                         if not entry.get("enabled") and expired(entry.get("disabled_since"), now)]
    for pid in retired_playlists:
        del playlists[pid]
    for entry in playlists.values():
        entry["mids"] = [mid for mid in entry.get("mids", []) if mid not in removed]
    return {"tracks": len(removed), "aliases": len(retired_aliases), "playlists": len(retired_playlists)}
