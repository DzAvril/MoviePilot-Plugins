"""QB/TR 文件核验与 MP 3.1.6 窄范围运行时适配；不修改宿主磁盘源码。"""

import inspect
import time
from dataclasses import replace
from functools import wraps
from pathlib import PurePosixPath


class SelectionError(ValueError):
    pass


PAUSED_STATES = {"paused", "pauseddl", "pausedup", "stopped", "stoppeddl", "stoppedup"}


def task_info(server, torrent_hash):
    rows, error = server.get_torrents(ids=[torrent_hash])
    if error:
        raise SelectionError("无法读取下载任务，未启动")
    return next((dict(row) for row in rows or [] if str(row.get("hash", "")).lower() == torrent_hash), None)


def ensure_paused(server, torrent_hash):
    if not server.stop_torrents(ids=[torrent_hash]):
        raise SelectionError("无法暂停任务，未执行选曲")
    for attempt in range(8):
        row = task_info(server, torrent_hash)
        if row and str(row.get("state", "")).casefold() in PAUSED_STATES:
            return row
        if attempt < 7:
            time.sleep(0.25)
    raise SelectionError("未确认任务暂停，未执行选曲")


def choose_files(server, torrent_hash, folder_name, files, wanted):
    """必须先暂停；用名称映射真实文件 ID，设置后回读核验才允许调用者启动。"""
    expected = {str(PurePosixPath(name)) for name in files}
    wanted = set(wanted)
    if not wanted or not wanted.issubset(expected):
        raise SelectionError("选曲清单无效，任务保持暂停")

    def index(rows):
        mapped = {}
        for row in rows or []:
            name = str(PurePosixPath(str(row.get("name", "")).replace("\\", "/")))
            if name not in expected and folder_name and name.startswith(folder_name + "/"):
                name = name[len(folder_name) + 1:]
            file_id = row.get("index", row.get("id"))
            if name not in expected or name in mapped or not isinstance(file_id, int):
                raise SelectionError("下载器文件清单与种子不一致，任务保持暂停")
            mapped[name] = (file_id, int(row.get("priority", -1)))
        if set(mapped) != expected or len({v[0] for v in mapped.values()}) != len(mapped):
            raise SelectionError("下载器文件清单不完整，任务保持暂停")
        return mapped

    mapped = index(server.get_files(torrent_hash, retry=4, interval=0.5))
    all_ids = [value[0] for value in mapped.values()]
    wanted_ids = [mapped[name][0] for name in wanted]
    if not server.set_files(torrent_hash=torrent_hash, file_ids=all_ids, priority=0):
        raise SelectionError("取消非目标文件失败，任务保持暂停")
    if not server.set_files(torrent_hash=torrent_hash, file_ids=wanted_ids, priority=1):
        raise SelectionError("勾选歌曲失败，任务保持暂停")
    actual = index(server.get_files(torrent_hash, retry=3, interval=0.25))
    if {name for name, (_, priority) in actual.items() if priority > 0} != wanted:
        raise SelectionError("文件勾选回读不一致，任务保持暂停")
    return [name for name in files if name in wanted]


class RuntimeAdapter:
    """宿主缺少歌曲选文件契约，只适配已核对的三个调用边界。"""

    def __init__(self, plugin):
        self.plugin = plugin
        self.bindings = []

    def install(self):
        from app.chain.download.submission import DownloadSubmissionOwner
        from app.chain.search.music import SearchMusicOwner
        from app.chain.search import result as search_result
        from app.domain.music import MusicMatch

        # 升级宿主后若签名不兼容，保留下载事件拦截，绝不回退成整专下载。
        submit = DownloadSubmissionOwner._submit_prepared_download
        if not {"prepared", "context", "governance"}.issubset(inspect.signature(submit).parameters):
            raise SelectionError("当前 MP 下载契约不兼容，QQ 单曲下载已保护性暂停")
        if "include_candidates" not in inspect.signature(search_result._match_torrents).parameters:
            raise SelectionError("当前 MP 搜索契约不兼容，QQ 单曲下载已保护性暂停")

        original_keywords = self._original(SearchMusicOwner._music_keywords)
        original_matches = self._original(search_result._match_torrents)
        original_submit = self._original(submit)
        plugin = self.plugin

        @wraps(original_keywords)
        def keywords(mediainfo, keyword, include_candidates):
            if not plugin._owns_media(mediainfo) or keyword:
                return original_keywords(mediainfo, keyword, include_candidates)
            values = original_keywords(mediainfo, keyword, True)
            # 把专辑放在第二项，仍服从 MP 配置的名称搜索次数和站点预算。
            if mediainfo.album and mediainfo.album != mediainfo.title:
                artist = (mediainfo.artists or [mediainfo.album_artist or ""])[0]
                values = [mediainfo.title, f"{artist} {mediainfo.album}".strip(), *values]
            return list(dict.fromkeys(values))

        @wraps(original_matches)
        def matches(*args, **kwargs):
            # 宿主 3.1.6 使用全关键字调用；其它调用方式保持原行为。
            media = kwargs.get("mediainfo")
            if not plugin._owns_media(media):
                return original_matches(*args, **kwargs)
            include = kwargs.get("include_candidates", False)
            candidates = original_matches(*args, **{**kwargs, "include_candidates": True})
            result = []
            for candidate in candidates:
                match = candidate.music_match
                if match and match.status == "album" and match.reason == "related_album":
                    # 原生歌手/版本/订阅过滤通过后，文件实证通过才能成为自动下载候选。
                    plan = plugin._inspect_plan(media, candidate.torrent)
                    if plan["allowed"]:
                        candidate = replace(candidate, music_match=MusicMatch("exact", "qqmusic_split_track_verified"))
                    elif not include:
                        continue
                elif match and match.status != "exact" and not include:
                    continue
                result.append(candidate)
            return result

        @wraps(original_submit)
        def submit_selected(owner, **kwargs):
            if not plugin._owns_media(kwargs["context"].media_info):
                return original_submit(owner, **kwargs)
            if plugin._stop.is_set():
                return None, "插件正在停止，QQ 选曲任务未启动"
            return plugin._submit_selected(owner, **kwargs)

        self._bind(SearchMusicOwner, "_music_keywords", keywords, static=True)
        self._bind(search_result, "_match_torrents", matches)
        self._bind(DownloadSubmissionOwner, "_submit_prepared_download", submit_selected)

    @staticmethod
    def _original(func):
        return getattr(func, "_qqmusic_original", func)

    def _bind(self, target, name, func, static=False):
        previous = getattr(target, name)
        func._qqmusic_original = self._original(previous)
        setattr(target, name, staticmethod(func) if static else func)
        self.bindings.append((target, name, func, static))

    def uninstall(self):
        for target, name, func, static in reversed(self.bindings):
            # 旧实例停止时不能覆盖已经热重载的新实例。
            if getattr(target, name) is func:
                original = func._qqmusic_original
                setattr(target, name, staticmethod(original) if static else original)
        self.bindings.clear()
