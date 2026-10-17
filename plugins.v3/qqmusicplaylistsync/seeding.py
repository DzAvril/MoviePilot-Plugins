"""Full-torrent seeding and opt-in removal of unimported audio only."""

import math
import stat
import time
from pathlib import Path, PurePosixPath

from .selected import PAUSED_STATES, SelectionError, choose_files, ensure_paused, task_info

DAY = 86400
TAG = "QQ歌单选曲"


def retention_days(value):
    try:
        parsed = int(value or 0)
        if isinstance(value, bool) or isinstance(value, float) and value != parsed:
            return 0
        return max(0, min(3650, parsed))
    except (ValueError, TypeError, OverflowError):
        return 0


def relative_name(value):
    name = PurePosixPath(value)
    if not value or "\\" in value or "\x00" in value or name.is_absolute() or ".." in name.parts or str(name) != value:
        raise SelectionError("种子文件路径无法安全核验，保留文件")
    return value


def checked_inventory(entry, row, rows, normalize):
    """Recover old registries from qB, checking both task ownership and original layout."""
    root = Path(entry["source_root"])
    selected = entry.get("files") or []
    if (not root.is_absolute() or ".." in root.parts or not selected
            or str(row.get("hash", "")).lower() != entry["hash"].lower()
            or TAG not in {tag.strip() for tag in str(row.get("tags") or "").split(",")}):
        raise SelectionError("任务归属无法核验，保留文件")
    single = str(root) in entry.get("fullpaths", [])
    folder = "" if single else root.name
    directory = root.parent
    if str(row.get("save_path") or "") != normalize(str(directory)) or str(row.get("content_path") or "") != normalize(str(root)):
        raise SelectionError("下载任务目录已变化，保留文件")
    names = []
    for file in rows or []:
        name = str(file.get("name") or "")
        if folder and name.startswith(folder + "/"):
            name = name[len(folder) + 1:]
        names.append(relative_name(name))
    expected_paths = [str((directory if single else root) / relative_name(name)) for name in selected]
    if (not names or len(set(names)) != len(names) or not set(selected).issubset(names)
            or expected_paths != entry.get("fullpaths") or single and names != selected
            or entry.get("download_files") and set(entry["download_files"]) != set(names)):
        raise SelectionError("下载器文件清单与已登记文件不一致，保留文件")
    return {"download_files": names, "folder_name": folder, "download_dir": str(directory),
            "qb_save_path": str(row["save_path"]), "download_mode": "full_album"}


def complete(row, rows):
    state = str(row.get("state") or "").casefold()
    return (bool(rows) and not any(part in state for part in ("checking", "error", "missing", "unknown"))
            and row.get("progress") == 1 and all(file.get("priority", 0) > 0 and file.get("progress") == 1 for file in rows))


def library_confirmed(entry, transfers, settings):
    """Every selected source needs its own successful transfer and a real local destination."""
    root = Path(settings.get("library_path") or ".")
    source_root = Path(entry["source_root"])
    if not root.is_absolute() or (settings.get("library_storage") or "local") != "local":
        return False
    latest = {}
    for row in transfers:
        if str(row.get("download_hash") or "").lower() == entry["hash"].lower():
            if row.get("id", 0) >= latest.get(row.get("src"), {}).get("id", 0):
                latest[row.get("src")] = row
    for src in entry["fullpaths"]:
        record = latest.get(src, {})
        dest = Path(record.get("dest") or ".")
        if (record.get("status") is not True or (record.get("dest_storage") or "local") != "local"
                or not dest.is_absolute() or ".." in dest.parts or not dest.is_relative_to(root)
                or dest.is_relative_to(source_root) or dest.is_symlink()
                or not dest.is_file() or dest.stat().st_size <= 0):
            return False
    return True


def deletion_plan(entry, settings, audio_extensions):
    """No traversal or recursive removal; keep selected sources and all library files."""
    root = Path(entry["source_root"])
    library = Path(settings.get("library_path") or ".")
    if (not root.is_dir() or root.resolve() != root or not library.is_absolute()
            or root.is_relative_to(library) or library.is_relative_to(root)):
        raise SelectionError("下载目录与音乐库边界无法核验，保留文件")
    wanted = set(entry["files"])
    plan = []
    for name in entry["download_files"]:
        relative_name(name)
        path = root / name
        if name in wanted or path.suffix.casefold() not in audio_extensions:
            continue
        if path.resolve() != path or path.is_symlink():
            raise SelectionError("未入库文件存在链接或路径变化，保留文件")
        if not path.exists():
            continue
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise SelectionError("未入库文件类型变化，保留文件")
        plan.append({"name": name, "signature": [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]})
    return plan


def shared_content(server, entry):
    rows, error = server.get_torrents()
    if error:
        raise SelectionError("无法核对其他下载任务，保留文件")
    root = PurePosixPath(entry["qb_save_path"]) / entry["folder_name"]
    for row in rows or []:
        if str(row.get("hash") or "").lower() == entry["hash"].lower():
            continue
        other = PurePosixPath(str(row.get("content_path") or row.get("save_path") or "/"))
        if other.is_relative_to(root) or root.is_relative_to(other):
            raise SelectionError("其他下载任务仍使用该目录，保留文件")


def remove_unimported(entry, server, *, normalize, settings, transfers, save, audio_extensions, stopped=lambda: False, check_other_clients=lambda: None):
    """A persisted removal intent permits retry after a crash between qB removal and unlink."""
    cleanup = entry["cleanup"]
    if not library_confirmed(entry, transfers(), settings):
        raise SelectionError("入库文件未全部确认，保留下载文件")
    shared_content(server, entry)
    check_other_clients()
    # Recheck directory/symlink safety, but retain original inode signatures on retries.
    current = {item["name"]: item for item in deletion_plan(entry, settings, audio_extensions)}
    for item in cleanup["plan"]:
        if item["name"] in current and current[item["name"]]["signature"] != item["signature"]:
            raise SelectionError("下载文件已被替换，保留文件")
    row = task_info(server, entry["hash"])
    if row:
        if stopped():
            raise SelectionError("插件已停止维护，保留文件")
        if (cleanup["state"] != "removing" or not cleanup.get("task_added_on")
                or row.get("added_on") != cleanup["task_added_on"]
                or str(row.get("state") or "").casefold() not in PAUSED_STATES
                or str(row.get("save_path") or "") != entry["qb_save_path"]
                or TAG not in {tag.strip() for tag in str(row.get("tags") or "").split(",")}):
            raise SelectionError("相同种子已重新添加，保留文件")
        rows = server.get_files(entry["hash"]) or []
        checked_inventory(entry, row, rows, normalize)
        if not complete(row, rows):
            raise SelectionError("完整下载状态已变化，保留文件")
        if not server.delete_torrents(delete_file=False, ids=[entry["hash"]]):
            raise SelectionError("移除做种任务失败，保留文件")
        for attempt in range(8):
            if task_info(server, entry["hash"]) is None:
                break
            if attempt == 7:
                raise SelectionError("尚未确认做种任务移除，保留文件")
            time.sleep(0.25)
    cleanup["state"] = "removed"
    save()
    for item in cleanup["plan"]:
        if stopped():
            raise SelectionError("插件已停止维护，保留文件")
        if item["name"] not in current:
            continue
        # Recheck the leaf immediately before unlink; unlink never follows a symlink.
        path = Path(entry["source_root"]) / item["name"]
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns] != item["signature"]:
            raise SelectionError("下载文件已变化，保留文件")
        path.unlink()
        cleanup["deleted"] = cleanup.get("deleted", 0) + 1
        save()
    cleanup.update(state="done", finished_at=time.time(), error="")
    cleanup.pop("plan", None)
    save()


def maintain_entry(entry, server, *, normalize, settings, days, now, transfers, save, audio_extensions, pending_selection=False, stopped=lambda: False, check_other_clients=lambda: None):
    """Called by scheduled/manual maintenance, never by read-only page refreshes."""
    cleanup = entry.setdefault("cleanup", {})
    if stopped():
        return
    if cleanup.get("state") == "done":
        return
    row = task_info(server, entry["hash"])
    if cleanup.get("state") in {"removing", "removed"}:
        if days and not pending_selection:
            remove_unimported(entry, server, normalize=normalize, settings=settings, transfers=transfers, save=save, audio_extensions=audio_extensions, stopped=stopped, check_other_clients=check_other_clients)
        return
    if not row or entry.get("phase") != "started" or entry.get("error"):
        return
    rows = server.get_files(entry["hash"]) or []
    entry.update(checked_inventory(entry, row, rows, normalize))
    if any(file.get("priority", 0) <= 0 for file in rows):
        was_paused = str(row.get("state") or "").casefold() in PAUSED_STATES
        ensure_paused(server, entry["hash"])
        if stopped():
            raise SelectionError("插件已停止维护，保留文件")
        choose_files(server, entry["hash"], entry["folder_name"], entry["download_files"], entry["download_files"])
        cleanup.clear()
        save()
        if not was_paused and not server.start_torrents(ids=[entry["hash"]]):
            raise SelectionError("整专文件已勾选，启动失败，任务保持暂停")
        row, rows = task_info(server, entry["hash"]), server.get_files(entry["hash"])
    cleanup.pop("error", None)
    if not days:
        cleanup.clear()
        cleanup.update(state="disabled")
        save()
        return
    if not any(name not in entry["files"] and Path(name).suffix.casefold() in audio_extensions for name in entry["download_files"]):
        cleanup.update(state="not_needed")
        save()
        return
    if not complete(row, rows):
        cleanup.clear()
        cleanup.update(state="waiting_download")
    elif pending_selection or not library_confirmed(entry, transfers(), settings):
        cleanup.clear()
        cleanup.update(state="waiting_library")
    else:
        seconds = row.get("seeding_time")
        if seconds is None and callable(getattr(server, "seeding_seconds", None)):
            seconds = server.seeding_seconds(entry["hash"])
        if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
            raise SelectionError("做种时长无法核验，保留文件")
        if not cleanup.get("ready_at") or seconds < cleanup.get("seed_seconds_at_ready", 0):
            cleanup.update(ready_at=now, seed_seconds_at_ready=seconds)
        cleanup.update(state="retaining", due_at=cleanup["ready_at"] + days * DAY,
                       seed_seconds=max(0, seconds - cleanup["seed_seconds_at_ready"]))
        if now >= cleanup["due_at"] and cleanup["seed_seconds"] >= days * DAY:
            shared_content(server, entry)
            check_other_clients()
            plan = deletion_plan(entry, settings, audio_extensions)
            if not plan:
                cleanup.update(state="not_needed")
            else:
                paused = ensure_paused(server, entry["hash"])
                rows = server.get_files(entry["hash"]) or []
                checked_inventory(entry, paused, rows, normalize)
                if not complete(paused, rows):
                    raise SelectionError("完整下载状态已变化，保留文件")
                if not isinstance(paused.get("added_on"), (int, float)) or paused["added_on"] <= 0:
                    raise SelectionError("下载任务创建时间无法核验，保留文件")
                cleanup.update(state="removing", plan=plan, task_added_on=paused["added_on"])
                save()
                remove_unimported(entry, server, normalize=normalize, settings=settings, transfers=transfers, save=save, audio_extensions=audio_extensions, stopped=stopped, check_other_clients=check_other_clients)
    save()
