"""Project per-song lifecycle from verified library files and read-only MP/qB facts."""

import math
import unicodedata
from collections import Counter
from pathlib import PurePosixPath


def _progress(value):
    return max(0, min(1, value)) if isinstance(value, (int, float)) and math.isfinite(value) else None


def _title(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def _path(value):
    return str(PurePosixPath(str(value).replace("\\", "/"))) if value else ""


def _state(status, label, message="", progress=None, tone="muted"):
    return {"status": status, "status_label": label, "status_message": message,
            "progress": progress, "status_tone": tone}


def _track_progress(entry, filename, task):
    expected = {_path(filename)}
    root = _path(entry.get("source_root"))
    if root and root not in {_path(path) for path in entry.get("fullpaths", [])}:
        expected.add(str(PurePosixPath(PurePosixPath(root).name) / filename))
    matches = [row for row in task.get("file_priorities", []) if _path(row.get("name")) in expected]
    if len(matches) != 1 or not matches[0].get("priority", 0) > 0:
        return None
    return _progress(matches[0].get("progress"))


def song_lifecycle(state, registry, tasks, transfers, *, library_files=None, file_exists):
    """Keep subscription bookkeeping intact; one completed file never completes its album."""
    tracks = {mid: item for mid, item in state.get("tracks", {}).items() if item.get("present")}
    confirmed = {}
    for mid, item in tracks.items():
        hit = (library_files or {}).get(mid)
        if hit and file_exists(hit.get("path"), hit.get("storage")):
            confirmed[mid] = dict(hit)
        elif item.get("status") == "library" and file_exists(item.get("library_path"), "local"):
            confirmed[mid] = {"path": item["library_path"], "storage": "local"}

    by_file = {}
    for row in transfers:
        key = (str(row.get("download_hash") or "").lower(), _path(row.get("src")))
        if key[0] and key[1] and row.get("id", 0) >= by_file.get(key, {}).get("id", 0):
            by_file[key] = row
        source = str(row.get("media_source") or "")
        raw_mid = str(row.get("media_id") or "") if source == "qqmusic" else f"{source}:{row.get('media_id') or ''}"
        mid = state.get("identity_aliases", {}).get(raw_mid, raw_mid)
        # Standalone downloads can predate the selected-files registry.
        if (mid in tracks and source in ("qqmusic", "netease")
                and row.get("music_type") == "recording" and row.get("status") is True
                and _title(row.get("title")) == _title(tracks[mid]["song"].get("title"))
                and file_exists(row.get("dest"), row.get("dest_storage"))):
            confirmed[mid] = {"path": row["dest"], "storage": row.get("dest_storage") or "local"}

    states = {}
    for mid, item in tracks.items():
        if mid in confirmed:
            states[mid] = _state("library", "已入库", "已确认音乐库中的歌曲文件", tone="green")
        elif item.get("status") == "pending":
            states[mid] = _state("pending", "待订阅", "等待创建 MP 单曲订阅")
        elif item.get("status") == "failed":
            states[mid] = _state("failed", "等待重试", "订阅创建未完成，将按计划重试", tone="warn")
        elif item.get("status") == "library":
            states[mid] = _state("unknown", "状态待确认", "原入库文件暂未找到，请检查音乐目录")
        else:
            states[mid] = _state("searching", "待搜索", "等待 MP 搜索和匹配可用资源")

    rank = {"searching": 0, "pending": 0, "failed": 0, "unknown": 1,
            "transfer_failed": 2, "downloading": 3, "downloaded": 4, "library": 5}
    for torrent_hash, entry in registry.items():
        sources = dict(zip(entry.get("files", []), entry.get("fullpaths", [])))
        task = tasks.get(torrent_hash) or {}
        for mid, filename in entry.get("matches", {}).items():
            if mid not in tracks or states[mid]["status"] == "library":
                continue
            transfer = by_file.get((torrent_hash.lower(), _path(sources.get(filename))))
            if transfer and transfer.get("status") is True and file_exists(transfer.get("dest"), transfer.get("dest_storage")):
                confirmed[mid] = {"path": transfer["dest"], "storage": transfer.get("dest_storage") or "local"}
                candidate = _state("library", "已入库", "MP 已成功整理，已确认入库文件", tone="green")
            elif transfer and transfer.get("status") is False and (not task.get("success") or task.get("state") == "missing"):
                candidate = _state("transfer_failed", "整理失败", "MP 整理未成功，请查看整理记录", tone="warn")
            elif not task.get("success"):
                candidate = _state("unknown", "状态待确认", "暂时无法读取下载器状态")
            elif task.get("state") == "missing":
                candidate = _state("unknown", "任务未找到", "下载器中没有此任务，暂未确认入库文件", tone="warn")
            else:
                progress = _track_progress(entry, filename, task)
                qstate = str(task.get("state") or "").casefold()
                if progress is None:
                    candidate = _state("unknown", "状态待确认", "尚未核对该音轨的勾选与进度")
                elif "checking" in qstate:
                    candidate = _state("downloading", "校验中", "下载器正在校验文件", progress, "purple")
                elif qstate in ("error", "missingfiles", "unknown"):
                    candidate = _state("downloading", "下载异常", "请检查下载器中的任务", progress, "warn")
                elif progress >= 1:
                    if transfer and transfer.get("status") is False:
                        candidate = _state("transfer_failed", "整理失败", "下载已完成，MP 整理未成功，请查看整理记录", 1, "warn")
                    else:
                        candidate = _state("downloaded", "待入库", "该音轨下载完成，等待 MP 成功整理入库", 1, "purple")
                elif "paused" in qstate or "stopped" in qstate:
                    candidate = _state("downloading", "下载已暂停", "歌曲尚未下载完成", progress, "warn")
                elif "queued" in qstate:
                    candidate = _state("downloading", "等待下载", "歌曲已进入下载器队列", progress, "purple")
                else:
                    candidate = _state("downloading", "下载中", "歌曲音轨的实际下载进度", progress, "purple")
            if rank[candidate["status"]] > rank[states[mid]["status"]]:
                states[mid] = candidate
    return {"states": states, "counts": dict(Counter(item["status"] for item in states.values())),
            "library_files": confirmed}
