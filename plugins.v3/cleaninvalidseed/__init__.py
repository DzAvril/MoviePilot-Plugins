"""MoviePilot V3 invalid seeding review, guarded task actions and reversible source cleanup."""

import fcntl
import threading
import time
import uuid
from collections import Counter
from collections.abc import Sequence
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from apscheduler.triggers.cron import CronTrigger
from app.sdk.logging import logger
from app.sdk.plugin import _PluginBase
from app.sdk.services import DownloaderHelper
from app.core.config import settings
from app.schemas import NotificationType

from .core import (DEFAULTS, TRANSIENT, classify, config_values, digest, lines, observe,
                   parse_mappings, safe_message, task_record, value)
from .files import TRASH, inspect_sources, move_to_trash, reconcile_entry, restore_entry

OPERATION_LOCK = threading.Lock()
CONFIRMATIONS = {"tag": "标记选中任务", "remove": "移除任务并保留文件", "quarantine": "移入回收区"}


class BusyError(ValueError):
    pass


class CleanInvalidSeed(_PluginBase):
    plugin_name = "清理无效做种"
    plugin_desc = "复核失效种子、保护跨下载器做种，源文件清理可预览、可恢复。"
    plugin_icon = "https://raw.githubusercontent.com/DzAvril/MoviePilot-Plugins/a06b2f2a7916a9e492fdf5b0a25e30a38ca28127/icons/CleanInvalidSeed-3.0.2.png"
    plugin_version = "3.0.3"
    plugin_author = "DzAvril"
    author_url = "https://github.com/DzAvril"
    plugin_config_prefix = "cleaninvalidseed"
    plugin_order = 1
    auth_level = 1
    DATA_KEY = "review_state_v3"

    def init_plugin(self, config=None):
        if hasattr(self, "_stop"):
            self._stop.set()
        self._stop = threading.Event()
        self._state_lock = threading.RLock()
        self._busy = False
        self._error = ""
        try:
            self._config = config_values(config)
            if self._config["cron"]:
                CronTrigger.from_crontab(self._config["cron"], timezone=settings.TZ)
        except (ValueError, TypeError):
            self._config = {**DEFAULTS, **{k: v for k, v in (config or {}).items() if k in DEFAULTS}}
            self._error = "配置无效，请检查运行周期、数值和目录映射后重新保存"
        self._state = self.get_data(self.DATA_KEY) or {"observations": {}, "history": [], "trash": {}}
        self._state.setdefault("trash", {})
        self._state.setdefault("history", [])
        if any(entry.get("status") == "intent" for entry in self._state["trash"].values()):
            try:
                with self._operation():
                    self._reconcile_trash()
            except BusyError:
                pass
        if self._config.get("onlyonce"):
            self._config["onlyonce"] = False
            self.update_config(self._config)
            self.start_scan()

    def get_state(self):
        return bool(self._config.get("enabled")) and not self._error

    def get_service(self):
        if self.get_state() and self._config.get("cron"):
            return [{"id": "CleanInvalidSeed", "name": "复核无效做种",
                     "trigger": CronTrigger.from_crontab(self._config["cron"], timezone=settings.TZ),
                     "func": self.clean_invalid_seed, "kwargs": {"max_instances": 1, "coalesce": True}}]
        return []

    def stop_service(self):
        if hasattr(self, "_stop"):
            self._stop.set()

    @contextmanager
    def _operation(self):
        if not OPERATION_LOCK.acquire(blocking=False):
            raise BusyError("已有检测或清理正在进行，请稍后查看结果")
        try:
            folder = self.get_data_path()
            folder.mkdir(parents=True, exist_ok=True)
            with (folder / "operation.lock").open("a") as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise BusyError("其他进程正在检测，请稍后重试") from None
                yield self._stop
        finally:
            OPERATION_LOCK.release()

    def _persist(self):
        self.save_data(self.DATA_KEY, deepcopy(self._state))

    def _inventory(self, config, stop):
        helper = DownloaderHelper()
        configs = helper.get_configs(include_disabled=True)
        services = helper.get_services()
        requested = set(config["downloaders"])
        if not requested:
            raise ValueError("请先选择需要检测的下载器")
        if not requested.issubset(services):
            raise ValueError("所选下载器不存在、已停用或不可用，保留所有任务和源文件")
        names = set(requested)
        if config["detect_invalid_files"]:
            # A disabled client can still own files. Do not mistake its absence for an empty inventory.
            names.update(configs)
        tasks, available = [], {}
        for name in sorted(names):
            if stop.is_set():
                raise ValueError("检测已停止")
            service = services.get(name)
            if not service or service.type not in ("qbittorrent", "transmission"):
                raise ValueError(f"{name} 无法完整核对，保留所有任务和源文件")
            client = service.instance
            try:
                if service.type == "transmission":
                    arguments = list(dict.fromkeys([*client._trarg, "secondsSeeding", "files", "priorities", "wanted"]))
                    torrents = client.trc.get_torrents(arguments=arguments)
                else:
                    torrents, error = client.get_torrents()
                    if error:
                        raise ValueError()
                if torrents is None:
                    raise ValueError()
                for torrent in torrents:
                    if stop.is_set():
                        raise ValueError("检测已停止")
                    files = torrent.get_files() if service.type == "transmission" else None
                    trackers = None
                    if service.type == "qbittorrent":
                        # TorrentDictionary is a dict, but .trackers performs a separate RPC.
                        trackers = getattr(torrent, "trackers", value(torrent, "trackers", default=[]))
                        if not isinstance(trackers, Sequence) or isinstance(trackers, (str, bytes, bytearray)):
                            raise ValueError("Tracker 清单读取不完整")
                        trackers = list(trackers)
                    tasks.append(task_record(torrent, service.type, name, files=files, trackers=trackers))
                available[name] = {"name": name, "type": service.type, "count": len(torrents)}
            except Exception:
                # Native client errors may contain tracker passkeys and service credentials.
                raise ValueError(f"{name} 清单读取不完整，本轮不执行任何清理") from None
        return tasks, available, services

    def _evaluate(self, config, stop):
        tasks, available, services = self._inventory(config, stop)
        rows = classify(tasks, config)
        warnings = []
        if config["detect_invalid_files"]:
            try:
                mappings = parse_mappings(config["download_dirs"])
            except ValueError as error:
                warnings.append(str(error))
                mappings = []
            if not mappings:
                if not warnings:
                    warnings.append("未配置目录映射，本轮仅检测种子任务")
            else:
                files, warnings = inspect_sources(mappings, tasks, config, time.time(), stop.is_set)
                rows.extend(files)
        if stop.is_set():
            raise ValueError("配置已变更或检测已停止，请重新检测")
        return rows, warnings, available, services

    def _review(self, config, stop):
        rows, warnings, available, _ = self._evaluate(config, stop)
        self._state["observations"] = observe(rows, self._state.get("observations", {}), config, time.time())
        if any(TRANSIENT.search(msg) for msg in lines(config["custom_error_msg"])):
            warnings.insert(0, "已忽略自定义规则中的网络、账号或权限错误；这些错误不能证明站点已删种")
        report = {"scan_id": uuid.uuid4().hex, "at": time.time(), "config_digest": digest(config),
                  "rows": [{k: v for k, v in row.items() if k != "paths"} for row in rows],
                  "warnings": warnings, "services": list(available.values()), "error": ""}
        self._state["report"] = report
        self._persist()
        return report

    def clean_invalid_seed(self, preview=False):
        try:
            with self._operation() as stop:
                if self._error:
                    raise ValueError(self._error)
                config = deepcopy(self._config)
                report = self._review(config, stop)
                if not preview and config["action"] != "preview":
                    ids = [row["id"] for row in report["rows"] if row["kind"] == "torrent" and row["ready"]][:config["max_actions"]]
                    if ids:
                        self._execute(report, ids, config["action"], config, stop)
                if config["notify"] and not preview:
                    counts = Counter(row["status"] for row in report["rows"])
                    if counts["candidate"] or counts["warning"] or report["warnings"] or config["notify_all"]:
                        self.post_message(mtype=NotificationType.SiteMessage, title="清理无效做种 · 复核完成",
                                          text=f"候选 {counts['candidate']}，需检查 {counts['warning']}，受保护 {counts['protected']}。请在插件数据页查看原因和操作记录。")
                return {"success": True, "scan_id": report["scan_id"]}
        except BusyError as error:
            return {"success": False, "message": str(error)}
        except Exception as error:
            message = str(error) if isinstance(error, ValueError) else "检测未完成，已停止本轮操作，请稍后重试"
            # Failed observations never age toward deletion while a client is offline.
            with self._state_lock:
                self._state["observations"] = {}
                self._state["last_error"] = {"at": time.time(), "message": safe_message(message)}
                self._persist()
            logger.warning(f"[CleanInvalidSeed] {safe_message(message)}")
            return {"success": False, "message": safe_message(message)}

    def start_scan(self):
        with self._state_lock:
            if self._busy:
                return {"success": False, "message": "检测正在进行"}
            self._busy = True
        def work():
            try:
                self.clean_invalid_seed(preview=True)
            finally:
                with self._state_lock:
                    self._busy = False
        threading.Thread(target=work, name="CleanInvalidSeed-review", daemon=True).start()
        return {"success": True, "message": "检测已开始，结果会自动更新"}

    def _audit(self, row, action, status, message="", entry_id=None):
        event = {"id": entry_id or uuid.uuid4().hex, "at": time.time(), "row_id": row["id"],
                 "name": row["name"], "service": row.get("service", "源文件"), "action": action,
                 "status": status, "message": safe_message(message)}
        self._state["history"] = [event, *[item for item in self._state["history"] if item["id"] != event["id"]]][:200]
        self._persist()
        return event

    def _reconcile_trash(self):
        resolved = {}
        for entry_id, entry in list(self._state["trash"].items()):
            if entry.get("status") != "intent":
                continue
            outcome = reconcile_entry(entry)
            if outcome == "unmoved":
                del self._state["trash"][entry_id]
                resolved[entry_id] = self._audit(entry, "quarantine", "skipped", "确认源文件仍在原位，已清理未执行的回收记录", entry_id)
            elif outcome == "quarantined":
                entry["status"] = "quarantined"
                resolved[entry_id] = self._audit(entry, "quarantine", "success", "已核对文件位于回收区，可恢复原位", entry_id)
        return resolved

    def _execute(self, report, ids, action, config, stop):
        if not ids or len(ids) > config["max_actions"]:
            raise ValueError(f"每批请选择 1–{config['max_actions']} 项")
        if action == "quarantine":
            self._reconcile_trash()
        old = {row["id"]: row for row in report["rows"]}
        outcomes = []
        for row_id in dict.fromkeys(ids):
            row = old.get(row_id)
            if not row or not row.get("ready") or stop.is_set():
                raise ValueError("所选项目未满足观察条件或操作已停止，请重新检测")
            if (row["kind"] == "file") != (action == "quarantine"):
                raise ValueError("所选项目与处理方式不匹配")
            # Read ALL relevant clients again for each action, including manual batches.
            fresh_rows, _, _, services = self._evaluate(config, stop)
            fresh = next((item for item in fresh_rows if item["id"] == row_id), None)
            if not fresh or fresh["status"] != "candidate" or fresh["signature"] != row["signature"]:
                outcomes.append(self._audit(row, action, "skipped", "最新状态已变化，保留并等待重新检测"))
                continue
            entry_id = uuid.uuid4().hex
            self._audit(row, action, "intent", "正在复核执行结果", entry_id)
            try:
                if stop.is_set():
                    raise ValueError("配置已变更或操作已停止")
                if action == "quarantine":
                    if len(self._state["trash"]) >= 1000:
                        raise ValueError("回收区记录已达上限，请先处理已有条目")
                    entry = {**row, "id": entry_id, "at": time.time(), "status": "intent",
                             "trash_path": str(Path(row["root"]) / TRASH / entry_id)}
                    def persist_intent():
                        self._state["trash"][entry_id] = entry
                        self._persist()
                    move_to_trash(row, entry_id, stopped=stop.is_set, before_move=persist_intent)
                    entry["status"] = "quarantined"
                else:
                    client = services[row["service"]].instance
                    if action == "remove":
                        if client.delete_torrents(delete_file=False, ids=row["hash"]) is not True:
                            raise ValueError("下载器未确认移除，文件保留")
                    elif row["client"] == "qbittorrent":
                        client.set_torrents_tag(ids=row["hash"], tags=[config["label"]])
                    else:
                        if client.set_torrent_tag(ids=row["hash"], tags=list(dict.fromkeys([*row["tags"], config["label"]]))) is not True:
                            raise ValueError("下载器未确认标记")
                    check, error = client.get_torrents(ids=[row["hash"]])
                    if error or check is None:
                        raise ValueError("操作后状态无法回读，请检查下载器")
                    if action == "remove" and check:
                        raise ValueError("任务仍在下载器中，未确认移除")
                    if action == "tag":
                        if len(check) != 1:
                            raise ValueError("无法回读任务标签")
                        actual = task_record(check[0], row["client"], row["service"])
                        if config["label"] not in actual["tags"]:
                            raise ValueError("标签回读不一致，未确认标记")
                row.update(status="processed", ready=False, reason=CONFIRMATIONS[action])
                outcomes.append(self._audit(row, action, "success", CONFIRMATIONS[action], entry_id))
            except Exception as error:
                message = str(error) if isinstance(error, ValueError) else "操作结果待核对，保留源文件；请查看下载器或回收区"
                status = "uncertain"
                if action == "quarantine" and entry_id not in self._state["trash"]:
                    status, message = "skipped", "未执行移动，请检查源目录及回收区后重试"
                event = self._audit(row, action, status, message, entry_id)
                if action == "quarantine":
                    event = self._reconcile_trash().get(entry_id, event)
                outcomes.append(event)
        return {"success": True, "results": outcomes}

    def execute(self, payload: dict):
        try:
            with self._operation() as stop:
                report = self._state.get("report", {})
                config = deepcopy(self._config)
                action = payload.get("action")
                if action not in CONFIRMATIONS or payload.get("confirmation") != CONFIRMATIONS[action]:
                    raise ValueError("请输入页面提示的确认文字")
                if self._error or payload.get("scan_id") != report.get("scan_id") or report.get("config_digest") != digest(config) or time.time() - report.get("at", 0) > 600 or self._state.get("last_error", {}).get("at", 0) > report.get("at", 0):
                    raise ValueError("检测结果已失效或配置已变更，请重新检测")
                ids = payload.get("ids")
                if not isinstance(ids, list) or any(not isinstance(item, str) for item in ids):
                    raise ValueError("请选择需要处理的项目")
                return self._execute(report, ids, action, config, stop)
        except Exception as error:
            return {"success": False, "message": safe_message(error) if isinstance(error, ValueError) else "操作未完成，请重新检测后查看记录"}

    def restore(self, payload: dict):
        try:
            with self._operation() as stop:
                entry = self._state["trash"].get(payload.get("id"))
                if not entry or entry["status"] not in ("quarantined", "intent"):
                    raise ValueError("未找到可恢复的回收区条目")
                if entry["status"] == "intent":
                    self._reconcile_trash()
                    if entry["id"] not in self._state["trash"]:
                        return {"success": True, "message": "源文件仍在原位，已清理未执行的回收记录"}
                restore_entry(entry, stopped=stop.is_set)
                entry["status"] = "restored"
                self._audit(entry, "restore", "success", "已恢复到原位置")
                # Active quarantine entries are durable, restored entries need only their audit event.
                del self._state["trash"][entry["id"]]
                self._persist()
                return {"success": True, "message": "已恢复到原位置"}
        except Exception as error:
            return {"success": False, "message": safe_message(error) if isinstance(error, ValueError) else "恢复未完成，回收区内容保留，请检查原位置是否已有同名文件"}

    def page_data(self, revision: str = ""):
        with self._state_lock:
            current_revision = digest([self._state.get("report", {}).get("scan_id"),
                                       self._state.get("last_error"), self._state["history"][:1],
                                       len(self._state["trash"]), self._config, self._error])
            busy = self._busy or OPERATION_LOCK.locked()
            if revision == current_revision:
                return {"success": True, "unchanged": True, "revision": current_revision, "busy": busy}
            report = deepcopy(self._state.get("report", {}))
            rows = report.pop("rows", [])
            # paths/hashes are retained only in the server's execution plan.
            public_rows = [{k: v for k, v in row.items() if k not in ("hash", "paths", "signature", "inode", "root_inode", "device")} for row in rows]
            for row in public_rows:
                if "trackers" in row:
                    row["trackers"] = [{key: item[key] for key in ("host", "healthy", "failed", "detail")} for item in row["trackers"]]
            trash = [{k: item.get(k) for k in ("id", "name", "path", "trash_path", "at", "size", "status")} for item in self._state["trash"].values()]
            try:
                choices = [{"name": name, "type": config.type, "enabled": config.enabled} for name, config in DownloaderHelper().get_configs(include_disabled=True).items()]
            except Exception:
                choices = []
            plan_current = not self._error and report.get("config_digest") == digest(self._config)
            return {"success": True, "revision": current_revision, "busy": busy, "config_error": self._error,
                    "plan_current": plan_current,
                    "config": self._config, "report": {**report, "rows": public_rows},
                    "last_error": self._state.get("last_error", {}), "history": deepcopy(self._state["history"]),
                    "trash": sorted(trash, key=lambda x: x["at"], reverse=True), "downloaders": choices,
                    "counts": dict(Counter(row["status"] for row in rows))}

    def get_api(self):
        endpoints = [("status", self.page_data, ["GET"]), ("scan", self.start_scan, ["POST"]),
                     ("execute", self.execute, ["POST"]), ("restore", self.restore, ["POST"])]
        return [{"path": f"/{prefix}{name}", "endpoint": endpoint, "methods": methods, "auth": auth,
                 "summary": f"清理无效做种 {name}"} for prefix, auth in (("", "apikey"), ("page_", "bear")) for name, endpoint, methods in endpoints]

    def get_render_mode(self):
        return "vue", "dist/assets"

    def get_page(self):
        return [{"component": "VAlert", "props": {"type": "info", "variant": "tonal"}, "text": "请打开复核工作台查看检测结果。"}]

    def get_form(self):
        fields = [("VSwitch", "enabled", "启用定时复核"), ("VTextField", "cron", "定时周期"),
                  ("VSwitch", "onlyonce", "保存后只读检测一次"), ("VSwitch", "notify", "结果通知"),
                  ("VSwitch", "notify_all", "正常轮次也通知"), ("VTextField", "label", "失效标记标签"),
                  ("VTextField", "confirmations", "至少观察次数（2–20）"), ("VTextField", "grace_hours", "持续观察小时（1–720）"),
                  ("VTextField", "min_seeding_days", "最少累计做种天数（0–3650）"), ("VTextField", "max_actions", "每批处理上限（1–100）"),
                  ("VSwitch", "detect_invalid_files", "检测源文件，移动操作在工作台确认"),
                  ("VTextField", "file_min_age_days", "源文件静置天数（1–3650）"),
                  ("VTextarea", "download_dirs", "目录映射：MP目录:下载器目录1,下载器目录2"),
                  ("VTextarea", "exclude_keywords", "排除名称关键词，每行一个"),
                  ("VTextarea", "exclude_categories", "排除分类，每行一个"),
                  ("VTextarea", "exclude_labels", "排除标签，每行一个"),
                  ("VTextarea", "custom_error_msg", "自定义完整删种错误，每行一个")]
        try:
            names = list(DownloaderHelper().get_configs())
        except Exception:
            names = self._config.get("downloaders", [])
        content = [{"component": "VSelect", "props": {"model": "downloaders", "label": "检测下载器", "items": names, "multiple": True}},
                   {"component": "VSelect", "props": {"model": "action", "label": "定时处理方式", "items": [
                       {"title": "只预览", "value": "preview"}, {"title": "标记任务", "value": "tag"},
                       {"title": "移除任务并保留文件", "value": "remove"}]}}]
        content.extend({"component": component, "props": {"model": key, "label": label}} for component, key, label in fields)
        return [{"component": "VForm", "content": content}], deepcopy(self._config)
