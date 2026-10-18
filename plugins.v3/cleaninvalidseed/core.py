"""Deterministic, conservative classification. This module never changes a client or file."""

import hashlib
import json
import math
import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit

PERMANENT_ERRORS = {
    "torrent not registered with this tracker", "torrent banned", "err torrent banned",
    "torrent not exists", "unregistered torrent", "torrent not found",
}
# These responses describe an account, a service or transport, never a deleted torrent.
TRANSIENT = re.compile(
    r"connect|time.?out|timed out|resolv|unreachable|gateway|unavailable|maintenance|disabled|"
    r"unauthori[sz]ed|passkey|permission|rate.?limit|too many|\b50[234]\b|\b40[13]\b|"
    r"account|access denied|认证|维护|连接|账号|帐户|超时", re.I,
)
DEFAULTS = {
    "enabled": False, "cron": "0 3 * * *", "action": "preview", "downloaders": [],
    "notify": False, "notify_all": False, "label": "无效做种", "confirmations": 2,
    "grace_hours": 24, "min_seeding_days": 10, "max_actions": 10,
    "detect_invalid_files": False, "download_dirs": "", "file_min_age_days": 10,
    "exclude_keywords": "", "exclude_categories": "", "exclude_labels": "",
    "custom_error_msg": "", "onlyonce": False,
}


def lines(value):
    return list(dict.fromkeys(x.strip() for x in str(value or "").splitlines() if x.strip()))


def normalized(value):
    return " ".join(str(value or "").strip().split()).casefold().rstrip(".!。")


def config_values(config):
    old = config or {}
    result = {**DEFAULTS, **{k: v for k, v in old.items() if k in DEFAULTS and v is not None}}
    if "action" not in old:
        # Upgrading never inherits a destructive legacy switch.
        result["action"] = "preview"
    if result["action"] not in ("preview", "tag", "remove"):
        raise ValueError("处理模式无效")
    for key, low, high in (("confirmations", 2, 20), ("grace_hours", 1, 720),
                           ("min_seeding_days", 0, 3650), ("file_min_age_days", 1, 3650),
                           ("max_actions", 1, 100)):
        value = result[key]
        try:
            number = float(value)
            if isinstance(value, bool) or not math.isfinite(number) or number != int(number) or not low <= number <= high:
                raise ValueError()
            result[key] = int(number)
        except (ValueError, TypeError, OverflowError):
            raise ValueError(f"{key} 需为 {low}–{high} 的整数") from None
    if not isinstance(result["downloaders"], list) or any(not isinstance(x, str) for x in result["downloaders"]):
        raise ValueError("请选择需要检测的下载器")
    result["downloaders"] = list(dict.fromkeys(result["downloaders"]))
    if "file_min_age_days" not in old:
        result["file_min_age_days"] = max(1, result["min_seeding_days"])
    for key in ("label", "download_dirs", "exclude_keywords", "exclude_categories", "exclude_labels", "custom_error_msg", "cron"):
        result[key] = str(result[key] or "").strip()
    result["label"] = result["label"] or "无效做种"
    if any(x in result["label"] for x in (",", "\n", "\r")) or len(result["label"]) > 100:
        raise ValueError("标记标签需为单个标签，最多 100 字符")
    for key in ("enabled", "notify", "notify_all", "detect_invalid_files", "onlyonce"):
        if not isinstance(result[key], bool):
            raise ValueError(f"{key} 需为开关值")
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def value(obj, *keys, default=None):
    """Downloaded RPC records are local values; no threads or implicit network lookups."""
    for key in keys:
        try:
            item = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
        except (AttributeError, KeyError):
            continue
        if item is not None:
            return item
    return default


def number(obj, *keys, default=None):
    item = value(obj, *keys, default=default)
    if hasattr(item, "total_seconds"):
        item = item.total_seconds()
    try:
        result = float(item)
        return result if math.isfinite(result) and result >= 0 else default
    except (ValueError, TypeError):
        return default


def safe_message(message):
    text = re.sub(r"(?:https?|udp)://\S+", "[Tracker]", str(message or ""))
    text = re.sub(r"(?i)(passkey|token|password|authkey|apikey|api_key)\s*[=:]\s*[^\s&,;]+", r"\1=[隐藏]", text)
    return re.sub(r"\b[a-fA-F0-9]{24,}\b", "[隐藏]", text)[:300]


def tracker_records(torrent, kind, trackers=None):
    records = []
    raw = trackers if trackers is not None else (value(torrent, "trackers", default=[]) if kind == "qbittorrent" else value(torrent, "tracker_stats", "trackerStats", default=[]))
    for tracker in raw or []:
        url = value(tracker, "url", "announce", default="")
        try:
            host = urlsplit(url).hostname
        except (ValueError, TypeError):
            host = None
        if not host or value(tracker, "tier", default=0) == -1:
            continue
        if kind == "qbittorrent":
            status = value(tracker, "status")
            healthy = status == 2
            failed = status == 4
            message = value(tracker, "msg", default="")
        else:
            announced = value(tracker, "has_announced", "hasAnnounced", default=False)
            succeeded = value(tracker, "last_announce_succeeded", "lastAnnounceSucceeded")
            healthy = announced is True and succeeded is True
            failed = announced is True and succeeded is False
            message = value(tracker, "last_announce_result", "lastAnnounceResult", default="")
        records.append({"host": host.casefold(), "healthy": healthy, "failed": failed,
                        "message": normalized(message), "detail": safe_message(message)})
    return records


def task_record(torrent, kind, service, *, files=None, trackers=None):
    tags = value(torrent, "tags", default="") if kind == "qbittorrent" else value(torrent, "labels", default=[])
    tags = [s.strip() for s in tags.split(",")] if isinstance(tags, str) else list(tags or [])
    state = str(value(torrent, "state", "status", default="unknown"))
    key = str(value(torrent, "hash", "hash_string", "hashString", default=""))
    paths = []
    if kind == "qbittorrent":
        content = value(torrent, "content_path")
        if content:
            paths.append(str(content))
    else:
        directory = value(torrent, "download_dir", "downloadDir")
        # Use actual renamed file paths, not downloadDir + torrent.name.
        if directory and files:
            for entry in files:
                filename = value(entry, "name", default="")
                if not filename or PurePosixPath(filename).is_absolute() or ".." in PurePosixPath(filename).parts:
                    raise ValueError("下载器返回了无效的文件路径")
                paths.append(str(PurePosixPath(directory) / filename))
    for path in paths:
        if not PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
            raise ValueError("下载器返回了无效的内容路径")
    return {"id": digest([service, key]), "hash": key, "name": str(value(torrent, "name", default="未命名")),
            "service": service, "kind": "torrent", "client": kind, "state": state,
            "size": number(torrent, "size", "total_size", "totalSize", default=0),
            "progress": number(torrent, "progress") if kind == "qbittorrent" else number(torrent, "percent_done", "percentDone"),
            "seed_seconds": number(torrent, "seeding_time", "seconds_seeding", "secondsSeeding"),
            "tags": tags, "category": str(value(torrent, "category", default="")),
            "local_error": kind == "transmission" and value(torrent, "error", default=0) == 3,
            "added": str(value(torrent, "added_on", "added_date", "addedDate", default="")),
            "paths": paths, "trackers": tracker_records(torrent, kind, trackers)}


def classify(tasks, config):
    """A healthy peer on the same Tracker is additional evidence, never a replacement for exact errors."""
    healthy_hosts = {t["host"] for task in tasks for t in task["trackers"] if t["healthy"]}
    errors = PERMANENT_ERRORS | {normalized(x) for x in lines(config["custom_error_msg"]) if not TRANSIENT.search(x)}
    results = []
    for task in tasks:
        if task["service"] not in config["downloaders"]:
            continue
        item = {**task, "status": "healthy", "reason": "Tracker 工作正常", "eligible": False}
        trackers = task["trackers"]
        invalid = bool(trackers) and all(t["failed"] and t["message"] in errors and not TRANSIENT.search(t["message"]) for t in trackers)
        if not trackers:
            item.update(status="unknown", reason="未取得可验证的 Tracker 信息，保留任务")
        elif any(t["healthy"] for t in trackers):
            pass
        elif not invalid:
            item.update(status="warning", reason="临时故障或证据不足，保留任务")
        elif not all(t["host"] in healthy_hosts for t in trackers):
            item.update(status="warning", reason="同一 Tracker 暂无成功做种作为佐证，保留任务")
        else:
            item.update(status="candidate", reason="所有 Tracker 均明确返回删种错误")
            if task["category"] in lines(config["exclude_categories"]):
                item.update(status="protected", reason="命中排除分类")
            elif set(task["tags"]) & set(lines(config["exclude_labels"])):
                item.update(status="protected", reason="命中排除标签")
            elif any(x.casefold() in task["name"].casefold() for x in lines(config["exclude_keywords"])):
                item.update(status="protected", reason="命中排除关键词")
            elif not task["hash"] or not task["added"] or not task["paths"]:
                item.update(status="protected", reason="缺少种子身份，保留任务")
            elif task["local_error"]:
                item.update(status="protected", reason="本地数据错误，需先检查磁盘与路径")
            elif task["progress"] != 1:
                item.update(status="protected", reason="下载未完成或完成状态未知")
            elif re.search(r"paused|stopped|checking|check |queued|moving|metadata", task["state"], re.I):
                item.update(status="protected", reason="暂停、排队、校验或移动中的任务受保护")
            elif config["min_seeding_days"] and (task["seed_seconds"] is None or task["seed_seconds"] < config["min_seeding_days"] * 86400):
                item.update(status="protected", reason="累计做种时长不足或不可验证")
        item["signature"] = digest([task["hash"], task["paths"], task["added"], [(t["host"], t["message"]) for t in trackers], task["category"], sorted(task["tags"])])
        results.append(item)
    return results


def observe(rows, previous, config, now):
    current = {}
    for row in rows:
        row["ready"] = False
        if row["status"] != "candidate":
            continue
        old = previous.get(row["id"], {})
        # A scan gap beyond the observation window breaks continuous evidence.
        if old.get("signature") != row["signature"] or now - old.get("last", 0) > max(172800, config["grace_hours"] * 7200):
            old = {}
        first = old.get("first", now)
        count = old.get("count", 0)
        last = old.get("last", 0)
        if not old or now - last >= 3600:
            count += 1
            last = now
        current[row["id"]] = {"signature": row["signature"], "first": first, "last": last, "count": count}
        row.update(observations=count, first_seen=first, ready_at=first + config["grace_hours"] * 3600)
        row["ready"] = count >= config["confirmations"] and now >= row["ready_at"]
        if not row["ready"]:
            row["reason"] += f"；观察 {count}/{config['confirmations']} 次，等待观察期结束"
    if len(current) > 5000:
        raise ValueError("候选项超过 5000，已停止本轮操作，请缩小检测范围")
    return current


def parse_mappings(text):
    mappings = []
    for line in lines(text):
        root, separator, aliases = line.partition(":")
        if not separator:
            raise ValueError("目录映射需为 MP目录:下载器目录，可用逗号填写多个下载器目录")
        paths = [root.strip(), *[x.strip() for x in aliases.split(",")]]
        for path in paths:
            p = PurePosixPath(path)
            if not p.is_absolute() or ".." in p.parts or len(p.parts) < 3:
                raise ValueError("目录需使用具体的绝对路径，不能使用根目录、上级路径或磁盘根目录")
        root = str(PurePosixPath(paths[0]))
        if any(overlaps(root, other["root"]) for other in mappings):
            raise ValueError("MP 目录不能重复或互相嵌套，请将多个下载器目录写在同一行")
        for path in paths[1:]:
            for other in mappings:
                for alias in other["aliases"]:
                    if overlaps(path, alias):
                        raise ValueError(f"下载器目录 {path} 与 {alias} 重叠且对应不同 MP 目录，源文件复核已暂停")
        mappings.append({"root": root, "aliases": list(dict.fromkeys(str(PurePosixPath(p)) for p in paths[1:]))})
    return mappings


def overlaps(left, right):
    a, b = PurePosixPath(left), PurePosixPath(right)
    return a == b or a in b.parents or b in a.parents


def mapped_paths(mapping, tasks):
    paths = set()
    for task in tasks:
        if not task["paths"]:
            raise ValueError(f"{task['service']} 有任务的内容路径无法验证，已停止源文件检测")
        for path in task["paths"]:
            p = PurePosixPath(path)
            for alias in [mapping["root"], *mapping["aliases"]]:
                base = PurePosixPath(alias)
                if p == base or base in p.parents:
                    paths.add(str(PurePosixPath(mapping["root"]) / p.relative_to(base)))
                elif p in base.parents:
                    # A task can own the parent of a mapped disc/subdirectory.
                    paths.add(mapping["root"])
    if not paths:
        raise ValueError("目录映射没有对应到任何在用任务，无法证明映射正确，已停止源文件检测")
    return paths
