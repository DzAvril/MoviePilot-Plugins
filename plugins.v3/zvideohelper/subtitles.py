"""Search-only NAS adapter. Credentials and refresh stay owned by the native CLI."""

import hashlib
from html import unescape
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time


class SubtitleError(Exception):
    pass


def query_plan(keyword="", imdb_id=""):
    keyword, imdb_id = str(keyword or "").strip(), str(imdb_id or "").strip()
    if any(len(value) > 200 or any(ord(char) < 32 for char in value) for value in (keyword, imdb_id)):
        raise SubtitleError("搜索词需为 1–200 个字符")
    if imdb_id and not re.fullmatch(r"tt\d{6,12}", imdb_id):
        raise SubtitleError("IMDb ID 格式应为 tt 开头的数字")
    queries = list(dict.fromkeys(value for value in (imdb_id, keyword) if value))
    if not queries:
        raise SubtitleError("请输入片名或 IMDb ID")
    return queries


def project_candidates(data):
    """Do not send provider download locators to the browser or plugin history."""
    groups = data.get("subs", []) if isinstance(data, dict) else []
    if not isinstance(groups, list):
        raise SubtitleError("字幕服务返回结构异常，请稍后重试")
    candidates, seen = [], set()
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("subs"), list):
            continue
        for item in group["subs"]:
            if not isinstance(item, dict) or not isinstance(item.get("sub_title"), str) or not item["sub_title"].strip():
                continue
            subtitle_id = str(item.get("sub_id") or "")
            if not subtitle_id:
                continue
            title = unescape(item["sub_title"])
            key = hashlib.sha256((subtitle_id + "\0" + title).encode()).hexdigest()[:20]
            if key in seen:
                continue
            seen.add(key)
            suffix = Path(title).suffix.lower().lstrip(".")
            candidates.append({"id": key, "subtitle_id": subtitle_id, "title": title,
                "movie": str(group.get("name") or ""), "imdb_id": str(group.get("imdb") or ""),
                "size": str(item.get("size") or ""),
                "format": suffix.upper() if suffix in {"ass", "ssa", "srt", "vtt", "zip", "rar", "7z", "sup", "idx", "sub"} else "未标注",
                "download_available": bool(item.get("download_url"))})
    return candidates


class SubtitleService:
    def __init__(self, root, run=None):
        self.root = Path(root)
        self._run_override = run
        self._lock = threading.Lock()
        self._cache = {}

    def _run(self, args, timeout=150):
        if self._run_override:
            return self._run_override(args)
        native = self.root / "zspace-cli"
        if not native.is_file() or not os.access(native, os.X_OK):
            raise SubtitleError("NAS 字幕授权工具尚未安装，请先完成插件初始化")
        env = dict(os.environ, ZSPACE_CLI_HOME=str(self.root / "profile"))
        try:
            result = subprocess.run(args, capture_output=True, timeout=timeout, env=env)
            document = json.loads(result.stdout if result.returncode == 0 else result.stderr)
        except subprocess.TimeoutExpired:
            raise SubtitleError("字幕搜索超时，请稍后重试") from None
        except (OSError, ValueError):
            raise SubtitleError("字幕授权工具暂不可用，请检查 NAS 授权状态") from None
        if not isinstance(document, dict) or result.returncode or not document.get("ok"):
            code = document.get("error", {}).get("code", "") if isinstance(document, dict) else ""
            if code in {"E_NOT_LOGGED_IN", "E_OAUTH", "E_CREDENTIAL"}:
                raise SubtitleError("请先在 NAS 终端完成极空间授权，再刷新授权状态")
            raise SubtitleError("字幕服务请求失败，请检查 NAS 授权和网络连接后重试")
        return document

    def status(self):
        native = self.root / "zspace-cli"
        if not self._run_override and (not native.is_file() or not os.access(native, os.X_OK)):
            return {"installed": False, "authorized": False, "message": "NAS 字幕授权工具尚未安装"}
        try:
            result = self._run([str(native), "--profile", "zvideohelper", "status"], timeout=20)
            authorized = bool(result.get("data", {}).get("logged_in"))
            return {"installed": True, "authorized": authorized,
                    "message": "NAS 已授权，可搜索字幕" if authorized else "首次使用请先在 NAS 终端完成极空间授权"}
        except SubtitleError as error:
            return {"installed": True, "authorized": False, "message": str(error)}

    def search(self, keyword="", imdb_id=""):
        try:
            queries = query_plan(keyword, imdb_id)
        except SubtitleError as error:
            return {"success": False, "message": str(error)}
        cache_key = tuple(queries)
        cached = self._cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < 300:
            return {**cached[1], "cached": True}
        if not self._lock.acquire(blocking=False):
            return {"success": False, "message": "已有字幕搜索正在进行，请稍后重试"}
        try:
            attempts, candidates = [], []
            for query in queries:
                result = self._run([sys.executable, str(Path(__file__).with_name("subtitle_cli.py")),
                    "--original-bin", str(self.root / "zspace-cli"), "--profile", "zvideohelper", "--timeout", "25",
                    "media", "subtitle-search", "--dedicated-profile", "--params", json.dumps({"q": query}, ensure_ascii=False)])
                attempts.append(query)
                candidates = project_candidates(result.get("data", {}))
                if candidates:
                    break
            response = {"success": True, "count": len(candidates), "candidates": candidates,
                        "queries": attempts, "cached": False,
                        "message": "" if candidates else "未找到字幕，可尝试中文片名、原名或 IMDb ID"}
            if len(self._cache) >= 8:
                self._cache.clear()
            self._cache[cache_key] = (time.monotonic(), response)
            return response
        except SubtitleError as error:
            return {"success": False, "message": str(error)}
        finally:
            self._lock.release()
