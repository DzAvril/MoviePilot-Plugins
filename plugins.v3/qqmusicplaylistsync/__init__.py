"""QQ、网易云公开歌单持续同步，下载仍由 MP 的原生音乐订阅负责。"""

import fcntl
import json
import os
import threading
import time
from datetime import datetime
from dataclasses import replace
from copy import deepcopy
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlsplit

from mutagen import File as AudioFile, MutagenError

from app.chain.subscribe import SubscribeChain
from app.chain.download import DownloadChain
from app.schemas.types import ChainEventType, MediaSource, MediaType
from app.sdk.events import eventmanager
from app.sdk.logging import logger
from app.sdk.media import MusicInfo
from app.sdk.network import RequestUtils, SecurityUtils
from app.sdk.plugin import _PluginBase
from app.sdk.queries import list_subscriptions, list_subscription_history, list_transfer_history
from app.sdk.scheduler import add_plugin_once_job

from .core import (PlaylistError, MUSIC_SOURCES, fetch_playlist, fetch_netease_playlist, merge_playlists,
                   playlist_id, playlist_ids, netease_playlist_id, process_pending, track_file_selection,
                   summary, text_key, media_key, track_key)
from .selected import RuntimeAdapter, SelectionError, choose_files, ensure_paused, task_info
from .page import download_cards, page_projection
from .lifecycle import song_lifecycle
from .library import LibraryIndexCache
from .history import RETENTION_DAYS, cleanup_due, expired, local_source_absent, retired_download, prune_history


class QQMusicPlaylistSync(_PluginBase):
    """同步公开歌单并通过原生单曲订阅安全下载所需音轨。"""
    plugin_name = "音乐歌单同步"
    plugin_desc = "持续同步 QQ 与网易云歌单，保持单曲订阅，从分轨专辑只下载歌单歌曲，跳过 CUE。"
    plugin_icon = "https://raw.githubusercontent.com/DzAvril/MoviePilot-Plugins/main/icons/MusicPlaylistSync-1.7.1.png"
    plugin_version = "1.8.2"
    plugin_author = "DzAvril"
    author_url = "https://github.com/DzAvril"
    plugin_config_prefix = "qqmusicplaylistsync_"
    plugin_order = 70
    auth_level = 1

    SOURCE = "qqmusic"
    STATE_KEY = "sync_state_v1"
    AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".wav", ".aac", ".ape", ".dsf", ".aiff", ".ogg", ".opus", ".wma"}

    def init_plugin(self, config=None):
        """初始化配置、持久账本、下载保护与状态缓存。"""
        self._stop = threading.Event()
        self._config = {
            "enabled": False,
            "playlist_urls": "",
            "netease_playlist_urls": "",
            "interval": 60,
            "subscribe_workers": 4,
            "immediate_search": True,
            "save_path": "",
            "library_path": "",
            "downloader": "",
            "dry_run": True,
            **(config or {}),
        }
        self._config["interval"] = max(1, min(1440, int(self._config.get("interval") or 60)))
        self._config["subscribe_workers"] = max(1, min(8, int(self._config.get("subscribe_workers") or 4)))
        for key in ("downloader", "save_path", "library_path"):
            self._config[key] = str(self._config.get(key) or "").strip()
        if "playlist_urls" not in (config or {}):
            self._config["playlist_urls"] = (config or {}).get("playlist_url", "")
        self._state = self.get_data(self.STATE_KEY) or {"version": 1, "tracks": {}}
        self._guard_lock = threading.Lock()
        self._guard_cache = {}
        self._playlist_aliases = {}
        self._selection_lock = threading.RLock()
        self._status_lock = threading.Lock()
        self._status_library_files = {}
        self._status_index = LibraryIndexCache()
        self._adapter = RuntimeAdapter(self)
        self._adapter_error = ""
        try:
            self._adapter.install()
        except Exception:
            self._adapter_error = "MP 选曲接口不兼容，歌单歌曲下载已保护性暂停"
            logger.error(self._adapter_error)

    def _owns_media(self, media):
        """仅匹配本插件已追踪的 QQ 或网易云原生单曲。"""
        return bool(media and str(media.media_source or "") in MUSIC_SOURCES
                    and media.music_type == "recording"
                    and track_key(self._state, media.media_source, media.media_id) in self._state.get("tracks", {}))

    def _file_plan(self, media, files):
        """为目标歌曲及同专辑歌单歌曲生成精确选曲计划。"""
        song = self._state["tracks"][track_key(self._state, media.media_source, media.media_id)]["song"]
        related = [item["song"] for item in self._state["tracks"].values() if item.get("present")]
        return track_file_selection(song, files, related)

    def _inspect_plan(self, media, torrent):
        reason = "无法确认种子文件内容，保留单曲订阅等待可验证资源"
        try:
            if self._adapter_error:
                return {"allowed": False, "reason": self._adapter_error}
            if torrent and not str(torrent.enclosure or "").startswith("magnet:"):
                key = (str(torrent.site), str(torrent.enclosure))
                with self._guard_lock:
                    cached = self._guard_cache.get(key)
                if not cached or time.time() - cached[0] >= 300:
                    content, folder, files = DownloadChain().download_torrent(torrent)
                    if not isinstance(content, bytes) or not files:
                        return {"allowed": False, "reason": reason}
                    cached = (time.time(), files)
                    with self._guard_lock:
                        if len(self._guard_cache) >= 256:
                            self._guard_cache.pop(next(iter(self._guard_cache)))
                        self._guard_cache[key] = cached
                # 缓存仅存文件清单；每次按当前歌单重新选曲，新收藏不会被旧计划遗漏。
                return self._file_plan(media, cached[1])
        except Exception:
            reason = "种子文件检查失败，保留单曲订阅等待下次重试"
        return {"allowed": False, "reason": reason}

    def _qb_service(self, downloader):
        """解析支持分轨选择的原生 qBittorrent 服务。"""
        from app.sdk.services import DownloaderHelper
        service = DownloaderHelper().get_service(name=downloader, type_filter="qbittorrent")
        if not service:
            raise SelectionError("选曲下载需要已配置的 qBittorrent，任务未启动")
        return service

    def _download_options(self):
        """每次读取当前 MP 音乐订阅默认值，空字段不固化成安装时路径。"""
        from app.application.configuration import get_configured_system_config
        from app.schemas.types import SystemConfigKey
        defaults = get_configured_system_config().get(SystemConfigKey.DefaultMusicSubscribeConfig) or {}
        return {key: self._config.get(key) or str(defaults.get(key) or "").strip() or None
                for key in ("downloader", "save_path")}

    def _default_downloader(self):
        from app.sdk.services import DownloaderHelper
        configs = list(DownloaderHelper().get_configs().values())
        default = next((config for config in configs if config.default), None)
        return (default or (configs[0] if configs else None)).name if configs else None

    def _resolved_settings(self):
        """与原生下载使用同一音乐目录匹配规则，音乐库查重读取配对目录。"""
        from app.application.directory import DirectoryHelper
        options = self._download_options()
        media = MusicInfo(title="音乐", music_type="recording", artists=[])
        storage, path, error = DownloadChain()._resolve_media_download_dir(
            media_info=media, save_path=options["save_path"])
        helper = DirectoryHelper()
        directory = helper.get_download_dir_by_task_path(media=media, task_path=str(path)) if path else None
        directory = directory or helper.get_dir(media, include_unsorted=True, storage=storage)
        library = self._config["library_path"] or (directory.library_path if directory else None)
        library_storage = "local" if self._config["library_path"] else (directory.library_storage if directory else None)
        return {"downloader": options["downloader"] or self._default_downloader(),
                "save_path": str(path) if path else None, "download_storage": storage,
                "library_path": library, "library_storage": library_storage,
                "follow_mp": {key: not bool(self._config[key]) for key in ("downloader", "save_path", "library_path")},
                "error": error or ("MP 尚未配置匹配的音乐库目录" if not library else "")}

    def _submit_selected(self, owner, *, prepared, context, episodes, channel, source, downloader,
                         userid, username, label, custom_words, governance):
        """在原生副作用边界内选曲；原生结算仍负责下载记录、通知和订阅完成。"""
        from app.application.torrent.download import TorrentHelper
        from app.sdk.config import settings

        torrent_hash = None
        server = None
        entry = None
        managed = False
        actual_downloader = None
        try:
            # 本插件配置优先；留空时按当前 MP 音乐默认值、站点和系统默认解析。
            # 旧订阅里曾写入的固定下载器不阻止后续跟随 MP 设置。
            actual_downloader = self._download_options()["downloader"] or prepared.site_downloader or self._default_downloader()
            if self._adapter_error or owner._subscription_download_cancelled(governance):
                raise SelectionError("QQ 选曲下载已取消，任务未启动")
            # 原生准备阶段已解析目录、分类子目录并校验保存位置，沿用该结果。
            if not Path(prepared.download_dir).is_absolute() or ".." in Path(prepared.download_dir).parts:
                raise SelectionError("QQ 选曲下载需要本地绝对目录，任务未启动")
            if not isinstance(prepared.torrent_content, bytes):
                raise SelectionError("无法核验磁力文件清单，任务未启动")
            plan = self._file_plan(context.media_info, prepared.file_list)
            if not plan["allowed"]:
                raise SelectionError(plan["reason"])
            torrent_hash = TorrentHelper.get_torrent_hash(prepared.torrent_content)
            if not torrent_hash:
                raise SelectionError("无法核验种子身份，任务未启动")
            service = self._qb_service(actual_downloader)
            server, module = service.instance, service.module
            normalized_dir = module.normalize_path(prepared.download_dir, actual_downloader)
            # 串行保护同一专辑并发命中，避免歌曲 A 与 B 的勾选结果互相覆盖。
            with self._selection_lock:
                registry = self.get_data("selected_downloads") or {}
                entry = registry.get(torrent_hash)
                existing = task_info(server, torrent_hash)
                if existing:
                    history = owner.download_history_repository.get_by_hash(torrent_hash)
                    owned = bool(entry and entry.get("downloader") == actual_downloader) or bool(
                        history and str(history.media_source or "") in MUSIC_SOURCES
                        and history.music_type == "recording"
                        and track_key(self._state, history.media_source, history.media_id) in self._state["tracks"])
                    if not owned:
                        raise SelectionError("相同种子已有其它用途的任务，未改变该任务")
                    if Path(existing.get("save_path") or "") != Path(normalized_dir):
                        raise SelectionError("已有任务目录不同，未改变该任务")
                source_dir = Path(prepared.download_dir) / prepared.folder_name
                source_root = source_dir if prepared.folder_name else source_dir / prepared.file_list[0]
                entry = entry or {"hash": torrent_hash, "downloader": actual_downloader,
                                  "title": prepared.torrent.title, "files": [], "matches": {},
                                  "source_root": str(source_root), "fullpaths": [], "phase": "preparing"}
                registry[torrent_hash] = entry
                self.save_data("selected_downloads", registry)
                managed = True
                if governance and governance.mark_started:
                    governance.mark_started()
                if not existing:
                    tag = str(getattr(settings, "TORRENT_TAG", "") or "")
                    server.add_torrent(content=prepared.torrent_content, download_dir=normalized_dir,
                                       is_paused=True, tag=[t for t in (tag, "QQ歌单选曲") if t],
                                       cookie=prepared.torrent.site_cookie, category=prepared.media.category,
                                       ignore_category_check=False, content_layout="Original")
                paused = ensure_paused(server, torrent_hash)
                if Path(paused.get("save_path") or "") != Path(normalized_dir):
                    raise SelectionError("下载器实际保存目录不同，任务保持暂停")
                if prepared.folder_name and Path(paused.get("content_path") or "") != Path(normalized_dir) / prepared.folder_name:
                    raise SelectionError("下载器文件布局无法确认，任务保持暂停")
                # 历史下载文件保留；后续新收藏只扩充本插件已核验的选择集合。
                previous = set(entry.get("files", [])) if entry else set()
                if not previous.issubset(set(prepared.file_list)):
                    raise SelectionError("已保存的选曲清单与种子不一致，任务保持暂停")
                wanted = previous.union(plan["files"])
                selected = choose_files(server, torrent_hash, prepared.folder_name, prepared.file_list, wanted)
                layout = "Original"
                # 明确登记选中文件，避免把未选音轨记为已下载。
                entry = {"hash": torrent_hash, "downloader": actual_downloader, "title": prepared.torrent.title,
                         "files": selected, "audio_count": plan["audio_count"],
                         "matches": {**(entry or {}).get("matches", {}), **plan["matches"]},
                         "source_root": str(source_root), "fullpaths": [str(source_dir / file) for file in selected],
                         "at": time.time(), "phase": "verified", "error": ""}
                registry[torrent_hash] = entry
                self.save_data("selected_downloads", registry)
                owner._settle_accepted_download(
                    prepared=replace(prepared, file_list=selected), context=context, episodes=episodes,
                    channel=channel, source=source, userid=userid, username=username, custom_words=custom_words,
                    actual_downloader=actual_downloader, download_hash=torrent_hash, layout=layout,
                )
                if self._stop.is_set() or owner._subscription_download_cancelled(governance):
                    raise SelectionError("任务已暂停，选曲后下载被取消")
                # 同一专辑后续补曲时，允许原生下载器监控再次整理新完成的文件。
                tag = str(getattr(settings, "TORRENT_TAG", "") or "")
                server.remove_torrents_tag(ids=[torrent_hash], tag=["已整理"])
                server.set_torrents_tag(ids=[torrent_hash], tags=[t for t in (tag, "QQ歌单选曲") if t])
                # 原生结算可能发布事件；启动前再次确认其它处理器未扩大勾选范围。
                paused = ensure_paused(server, torrent_hash)
                tags = {part.strip() for part in str(paused.get("tags") or "").split(",")}
                if "已整理" in tags or (tag and tag not in tags) or "QQ歌单选曲" not in tags:
                    raise SelectionError("下载器整理标签回读失败，任务保持暂停")
                choose_files(server, torrent_hash, prepared.folder_name, prepared.file_list, wanted)
                if not server.start_torrents(ids=[torrent_hash]):
                    raise SelectionError("选曲已保存，但启动失败，任务保持暂停")
                entry.update(phase="started", error="")
                self.save_data("selected_downloads", registry)
                logger.info(f"QQ 歌单选曲下载：{context.media_info.title}，只选 {len(selected)}/{plan['audio_count']} 首")
                return torrent_hash, None
        except Exception as error:
            # 只有已经核验归属并进入暂停/新建阶段的任务才允许回收暂停。
            message = str(error) if isinstance(error, SelectionError) else "选曲下载失败，任务保持暂停等待重试"
            if managed and server and torrent_hash and entry:
                server.stop_torrents(ids=[torrent_hash])
                with self._selection_lock:
                    registry = self.get_data("selected_downloads") or {}
                    entry.update(phase="paused", error=message)
                    registry[torrent_hash] = entry
                    self.save_data("selected_downloads", registry)
            logger.warning(f"QQ 歌单选曲未启动：{message}")
            return None, message

    @eventmanager.register(ChainEventType.TransferIntercept)
    def guard_selected_transfer(self, event):
        """防止旧整专任务已经存在的非选中音频被顺带整理；不删除任何文件。"""
        if not event or not event.event_data or event.event_data.cancel:
            return event
        data = event.event_data
        item = data.fileitem
        if not item or item.storage not in (None, "local"):
            return event
        path = Path(item.path)
        for entry in (self.get_data("selected_downloads") or {}).values():
            root = Path(entry["source_root"])
            if path.is_relative_to(root) and str(path) not in entry.get("fullpaths", []):
                data.cancel, data.source, data.reason = True, self.plugin_name, "QQ 歌单未选中的文件不整理"
                break
        return event

    def selection_details(self, torrent_hash: str = ""):
        entry = (self.get_data("selected_downloads") or {}).get(torrent_hash)
        if not entry:
            return {"success": False, "message": "没有本插件管理的选曲任务"}
        server = self._qb_service(entry["downloader"]).instance
        row = task_info(server, torrent_hash)
        files = server.get_files(torrent_hash) if row else []
        return {"success": True, **entry, "state": row.get("state") if row else "missing",
                "progress": row.get("progress") if row else None,
                "tags": row.get("tags") if row else None,
                "file_priorities": [{k: file.get(k) for k in ("index", "id", "name", "priority", "progress", "size")}
                                    for file in files or []]}

    def _resolve_playlist_id(self, value):
        """解析 QQ 官方短分享链接；限制跳转域和次数，避免任意 URL 请求。"""
        if value in self._playlist_aliases:
            return self._playlist_aliases[value]
        try:
            return playlist_id(value)
        except PlaylistError:
            parsed = urlsplit(value)
            if parsed.scheme != "https" or parsed.hostname != "c6.y.qq.com" or parsed.path != "/base/fcgi-bin/u":
                raise
        url = value
        for _ in range(5):
            response = RequestUtils(timeout=15, headers={"User-Agent": "Mozilla/5.0"}).get_res(
                url, allow_redirects=False,
            )
            if response is None or response.status_code not in (301, 302, 303, 307, 308):
                raise PlaylistError("QQ 短链接无法解析，请使用完整歌单链接或 ID")
            url = urljoin(url, response.headers.get("Location", ""))
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not ((parsed.hostname or "").endswith(".qq.com") or parsed.hostname == "qq.com"):
                raise PlaylistError("QQ 短链接跳转到了不支持的地址")
            try:
                pid = playlist_id(url)
            except PlaylistError:
                continue
            self._playlist_aliases[value] = pid
            return pid
        raise PlaylistError("QQ 短链接跳转次数过多，请使用歌单 ID")

    def _fetch_playlists(self, pids):
        snapshots, errors = {}, {}
        def read(pid):
            if pid.startswith("netease:"):
                return fetch_netease_playlist(self._netease_request, pid.split(":", 1)[1])
            return fetch_playlist(self._request_page, pid, fetch_filtered=self._fetch_filtered)
        with ThreadPoolExecutor(max_workers=min(4, len(pids)), thread_name_prefix="qq-playlist") as executor:
            futures = {executor.submit(read, pid): pid for pid in pids}
            for future in as_completed(futures):
                pid = futures[future]
                try:
                    snapshots[pid] = future.result()
                except Exception as error:
                    errors[pid] = str(error)[:250]
        return snapshots, errors

    @eventmanager.register(ChainEventType.ResourceDownload)
    def guard_single_track(self, event):
        """在下载器提交前核验真实种子清单，仅约束本插件单曲身份。"""
        if not event or not event.event_data:
            return event
        data = event.event_data
        context = data.context
        media = context.media_info if context else None
        if not self._owns_media(media):
            return event
        item = self._state.get("tracks", {}).get(track_key(self._state, media.media_source, media.media_id))
        if not item or data.cancel:
            return event
        # 同步开关暂停后，已生成的原生订阅仍必须遵守单曲边界。
        torrent = context.torrent_info
        reason = "无法确认种子文件内容，保留单曲订阅等待可验证资源"
        plan = self._inspect_plan(media, torrent)
        accepted, reason = plan["allowed"], plan["reason"]
        if accepted:
            try:
                # 留空明确回到原生音乐目录解析，也覆盖旧订阅曾保存的固定路径。
                data.options = {**(getattr(data, "options", None) or {}),
                                "save_path": self._download_options()["save_path"]}
            except Exception:
                accepted, reason = False, "MP 默认目录读取失败，保留订阅等待重试"
        if not accepted:
            data.cancel = True
            data.source = self.plugin_name
            data.reason = reason
        record = {"at": time.time(), "title": item["song"]["title"],
                  "resource": torrent.title if torrent else "", "allowed": accepted, "reason": reason,
                  "version": self.plugin_version}
        with self._guard_lock:
            records = self.get_data("single_track_checks") or []
            self.save_data("single_track_checks", (records + [record])[-30:])
        logger.info(f"QQ 单曲检查：{record['title']}，{'放行' if accepted else '拦截'}，{reason}")
        return event

    def get_state(self):
        """返回持续同步开关。"""
        return bool(self._config.get("enabled"))

    def get_service(self):
        """声明由宿主统一调度的歌单检查任务。"""
        if not self.get_state():
            return []
        return [{
            "id": "QQMusicPlaylistSync",
            "name": "音乐歌单同步",
            "trigger": "interval",
            "func": self.sync,
            "kwargs": {"minutes": self._config["interval"], "max_instances": 1, "coalesce": True},
        }]

    def stop_service(self):
        """停止同步并撤销本插件的运行时包装。"""
        if hasattr(self, "_stop"):
            self._stop.set()
        if hasattr(self, "_adapter"):
            self._adapter.uninstall()

    def get_media_source(self):
        """向宿主声明 QQ 与网易云音乐来源。"""
        return [{"name": title, "media_source": source, "media_types": [MediaType.MUSIC.value]}
                for source, title in ((self.SOURCE, "QQ音乐歌单"), ("netease", "网易云音乐歌单"))]

    def get_module(self):
        """提供宿主媒体识别与音乐识别模块入口。"""
        return {
            "recognize_media": self.recognize_media,
            "async_recognize_media": self.async_recognize_media,
            "recognize_music": self.recognize_music,
            "async_recognize_music": self.async_recognize_music,
        }

    def recognize_media(self, meta=None, mtype=None, media_source=None, media_id=None, **kwargs):
        """只接管本插件已追踪的 QQ 与网易云单曲身份。"""
        if str(media_source or "") not in MUSIC_SOURCES or kwargs.get("music_type") not in (None, "recording"):
            return None
        item = self._state.get("tracks", {}).get(track_key(self._state, media_source, media_id))
        if not item:
            return None
        song = item["song"]
        album_mid = song.get("album_mid", "")
        song_source = song.get("source", self.SOURCE)
        native_source, song_id = str(media_source), str(media_id)
        cover = song.get("cover_url") if song_source == "netease" else (
            f"https://y.gtimg.cn/music/photo_new/T002R500x500M000{album_mid}.jpg" if album_mid.isalnum() else None)
        return MusicInfo(
            media_source=MediaSource(native_source), media_id=song_id,
            music_type="recording", title=song["title"], artists=song["artists"],
            album=song.get("album"), album_artist=song["artists"][0],
            year=song.get("year"), release_date=song.get("release_date") or None,
            track_number=song.get("track_number"), duration=song.get("duration") or None,
            cover_url=cover, title_aliases=[song["title"]], artist_aliases=song["artists"],
            detail_link=(f"https://music.163.com/song?id={song_id}" if native_source == "netease"
                         else f"https://y.qq.com/n/ryqq_v2/songDetail/{song_id}"),
        )

    async def async_recognize_media(self, **kwargs):
        """为异步调用提供相同的单曲元数据合同。"""
        return self.recognize_media(**kwargs)

    def recognize_music(self, media_source, media_id, music_type=None, **kwargs):
        """按完整来源身份识别账本中的单曲。"""
        return self.recognize_media(media_source=media_source, media_id=media_id, music_type=music_type)

    async def async_recognize_music(self, media_source, media_id, music_type=None, **kwargs):
        """异步音乐入口复用同一身份识别逻辑。"""
        return self.recognize_music(media_source, media_id, music_type)

    def _request_page(self, pid, offset, count):
        """读取指定 QQ 歌单分页的公开元数据。"""
        return self._qq_request("music.srfDissInfo.DissInfo", "CgiGetDiss", {
            "disstid": int(pid), "song_begin": offset, "song_num": count,
        })

    def _netease_request(self, route, query):
        """Read public metadata through the endpoints used by the installed sync tool."""
        if self._stop.is_set():
            raise PlaylistError("插件已停止，本次不更新网易云快照")
        if route == "/playlist/detail":
            path, data = "/api/v6/playlist/detail", {"id": str(query["id"]), "n": 100000, "s": 0}
        elif route == "/song/detail":
            ids = [int(sid) for sid in query["ids"].split(",")]
            path, data = "/api/v3/song/detail", {"c": json.dumps([{"id": sid} for sid in ids]), "ids": json.dumps(ids)}
        else:
            raise PlaylistError("不支持的网易云元数据请求")
        response = RequestUtils(timeout=25, headers={"Referer": "https://music.163.com/",
                                                    "User-Agent": "Mozilla/5.0"}).post_res(
            "https://music.163.com" + path, data=data, allow_redirects=False)
        if response is None or response.status_code != 200:
            raise PlaylistError("网易云歌单暂时无法读取，下个周期自动重试")
        try:
            return response.json()
        except ValueError as error:
            raise PlaylistError("网易云返回了无效的元数据响应") from error

    def _qq_request(self, module, method, param):
        """带停止检查和超时访问 QQ 官方元数据接口。"""
        if self._stop.is_set():
            raise PlaylistError("插件已停止，本次不更新歌单快照")
        body = {
            "comm": {"ct": 24, "cv": 0},
            "req_0": {"module": module, "method": method, "param": param},
        }
        response = RequestUtils(timeout=25, headers={
            "Referer": "https://y.qq.com/", "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
        }).post_res("https://u.y.qq.com/cgi-bin/musicu.fcg", json=body)
        if response is None or response.status_code != 200:
            raise PlaylistError("QQ 歌单暂时无法读取，下个周期自动重试")
        return response.json()

    def _fetch_filtered(self, items):
        """QQ 歌单中的特殊类型条目通过公开详情接口补齐；仍不可读的留待下轮。"""
        tracks = []
        for start in range(0, len(items), 50):
            batch = items[start:start + 50]
            try:
                response = self._qq_request("music.trackInfo.UniformRuleCtrl", "CgiGetTrackInfo", {
                    "ids": [int(x["songid"]) for x in batch],
                    "types": [int(x.get("songtype") or 0) for x in batch],
                    "ctx": 0, "client": 1, "modify_stamp": [0] * len(batch),
                })
                result = response.get("req_0") or {}
                if response.get("code") == 0 and result.get("code") == 0:
                    tracks.extend((result.get("data") or {}).get("tracks") or [])
            except (PlaylistError, ValueError, KeyError):
                continue
        return tracks

    def _save(self, state):
        """通过宿主插件存储持久化同步账本。"""
        self.save_data(self.STATE_KEY, state)

    def _existing(self):
        """同时检查活动订阅和完成历史，覆盖提交成功但账本还没写入的重启窗口。"""
        existing = {}
        filters = {"media_types": [MediaType.MUSIC]}
        for query in (list_subscriptions, list_subscription_history):
            page = 1
            while True:
                result = query(filters, {"page": page, "count": 100})
                for item in result.items:
                    if str(item.media_source or "") in MUSIC_SOURCES:
                        existing[track_key(self._state, item.media_source, item.media_id)] = item.id
                if not result.has_next:
                    break
                page += 1
        return existing

    def _library_index(self, wanted=None, tag_cache=None, settings=None):
        """按标签匹配本地已有歌曲；状态查询复用未变化文件的标签。"""
        if wanted is None:
            wanted = {text_key(x["song"]["title"]) for x in self._state["tracks"].values()
                      if x.get("present") and x["status"] in ("pending", "failed")}
        index = {}
        if not wanted:
            return index
        settings = settings or self._resolved_settings()
        if not settings["library_path"] or settings["library_storage"] not in (None, "local"):
            return index
        root = Path(settings["library_path"])
        if not root.is_dir():
            return index
        seen = set()
        for folder, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if not d.startswith((".", "@", "#"))]
            if self._stop.is_set():
                break
            for name in files:
                path = Path(folder) / name
                if path.suffix.lower() not in self.AUDIO_EXTENSIONS or path.is_symlink():
                    continue
                try:
                    stat = path.stat()
                    if not stat.st_size:
                        continue
                    key = str(path)
                    seen.add(key)
                    signature = (stat.st_mtime_ns, stat.st_size)
                    cached = tag_cache.get(key) if tag_cache is not None else None
                    if cached and cached[0] == signature:
                        _, title, artists = cached
                    else:
                        if tag_cache is not None:
                            tag_cache[key] = (signature, "", ())
                        audio = AudioFile(path, easy=True)
                        if not audio or not audio.tags:
                            continue
                        title = text_key((audio.get("title") or [""])[0])
                        artists = tuple(text_key(artist) for artist in audio.get("artist") or [])
                        if tag_cache is not None:
                            tag_cache[key] = (signature, title, artists)
                    if title not in wanted:
                        continue
                    for artist in artists:
                        index[(title, artist)] = key
                except (MutagenError, OSError, ValueError, KeyError):
                    continue
        if tag_cache is not None and not self._stop.is_set():
            for path in set(tag_cache) - seen:
                tag_cache.pop(path, None)
        return index

    def _subscribe(self, song):
        """按平台原生身份创建单曲订阅，目录沿用宿主默认解析。"""
        return SubscribeChain().add(
            title=song["title"], year=str(song.get("year") or ""), mtype=MediaType.MUSIC,
            media_source=MediaSource(song.get("source", self.SOURCE)), media_id=song.get("source_id", song["mid"]), music_type="recording",
            username=self.plugin_name, message=False, exist_ok=True,
            source="QQMusicPlaylistSync:" + ",".join(self._state["tracks"][song["mid"]].get("playlist_ids", [])),
            downloader=self._config["downloader"] or None, save_path=self._config["save_path"] or None,
            audio_quality="hires|lossless", best_version=0,
        )

    def _queue_search(self):
        """等同手动搜索：只提交歌单订阅，立即提升已有新订阅任务，不重复创建任务。"""
        chain = SubscribeChain()
        targets = []
        items = []
        for item in self._state["tracks"].values():
            if not item.get("present") or item["status"] != "subscribed":
                continue
            if not item.get("search_pending", not item.get("search_requested_at")):
                continue
            sid = item.get("subscription_id")
            native = chain.subscription_repository.get(sid) if sid else None
            if (native and str(native.media_source) in MUSIC_SOURCES
                    and track_key(self._state, native.media_source, native.media_id) == item["song"]["mid"]):
                targets.append(sid)
            items.append(item)
        queued = None
        if targets:
            # 使用宿主原生持久队列，与 MP 手动搜索采用相同来源、优先级和去重语义。
            # 不在同步线程内等待整批站点搜索，否则会阻塞新收藏检查。
            queued = chain.subscription_search_repository.enqueue(
                subscription_ids=tuple(dict.fromkeys(targets)), source="manual", priority=100,
                available_at_by_subscription=None,
            )
        requested_at = time.time()
        for item in items:
            item.update(search_pending=False, search_requested_at=requested_at)
        if queued:
            self._state["last_search"] = {
                "requested_at": requested_at, "targets": len(targets),
                "created": queued.created_count, "coalesced": queued.coalesced_count,
                "batch_id": str(queued.batch.batch_id),
            }
        self._save(self._state)
        if targets:
            started = add_plugin_once_job(
                self.__class__.__name__, "immediate_search", chain.resume_search_queue,
                "QQ歌单立即搜索下载", delay_seconds=0,
                func_kwargs={"limit": max(50, len(targets))},
            )
            logger.info(f"QQ 歌单立即搜索：{len(targets)} 个订阅已进入原生手动搜索队列，立即唤醒={started}")
        return len(targets)

    def sync(self):
        """完整获取快照后增量同步；跨进程文件锁防止手动、定时和重载同时执行。"""
        if not self.get_state() or self._stop.is_set():
            return {"success": False, "message": "插件未启用"}
        directory = self.get_data_path()
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "sync.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"success": False, "message": "已有同步任务运行中"}
            # 重新读取持久化数据，不能用重载前的旧内存覆盖另一轮的成功账本。
            self._state = self.get_data(self.STATE_KEY) or {"version": 1, "tracks": {}}
            try:
                if self._state.get("version", 1) < 2 and self._state.get("tracks") and not self.get_data("state_before_multilist"):
                    self.save_data("state_before_multilist", self._state)
                started = time.perf_counter()
                now = time.time()
                pids = []
                if self._config.get("playlist_urls", "").strip():
                    pids.extend(playlist_ids(self._config["playlist_urls"], self._resolve_playlist_id))
                if self._config.get("netease_playlist_urls", "").strip():
                    if self._state.get("tracks") and not self.get_data("state_before_netease_v1"):
                        self.save_data("state_before_netease_v1", deepcopy(self._state))
                    pids.extend(media_key("netease", pid) for pid in playlist_ids(self._config["netease_playlist_urls"], netease_playlist_id))
                if not pids:
                    raise PlaylistError("请至少填写一个 QQ 或网易云音乐歌单")
                snapshots, playlist_errors = self._fetch_playlists(pids)
                fetched = time.perf_counter()
                if self._stop.is_set():
                    raise PlaylistError("插件已停止，保留各歌单上次完整快照")
                self._state = merge_playlists(self._state, snapshots, playlist_errors, pids, now)
                self._save(self._state)
                if not snapshots:
                    return {"success": False, **summary(self._state)}
                if self._config.get("dry_run"):
                    return {"success": True, "dry_run": True, "partial_success": bool(playlist_errors), **summary(self._state)}
                needs_creation = any(item.get("present") and item["status"] in ("pending", "failed")
                                     and item.get("retry_at", 0) <= now for item in self._state["tracks"].values())
                existing = self._existing() if needs_creation else {}
                library = self._library_index()
                indexed = time.perf_counter()

                def in_library(song):
                    return next((library[(text_key(song["title"]), text_key(artist))]
                                 for artist in song["artists"]
                                 if (text_key(song["title"]), text_key(artist)) in library), None)

                created = process_pending(
                    self._state, now=now, limit=0, existing=existing,
                    in_library=in_library, subscribe=self._subscribe, save=self._save,
                    stopped=self._stop.is_set, workers=self._config["subscribe_workers"],
                )
                subscribed = time.perf_counter()
                search_queued = 0
                if self._config["immediate_search"] and not self._stop.is_set():
                    search_queued = self._queue_search()
                self._cleanup_history(now)
                self._state["last_metrics"] = {
                    "fetch_seconds": round(fetched - started, 3),
                    "index_seconds": round(indexed - fetched, 3),
                    "subscribe_seconds": round(subscribed - indexed, 3),
                    "total_seconds": round(time.perf_counter() - started, 3),
                    "created": created, "search_queued": search_queued,
                }
                self._state["last_sync"] = time.time()
                self._save(self._state)
                logger.info(f"音乐歌单同步完成：{len(snapshots)}/{len(pids)} 个歌单成功，去重 {summary(self._state)['tracked']} 首，新增订阅 {created}，待处理 {summary(self._state)['pending']}")
                return {"success": True, "created": created, "search_queued": search_queued, "partial_success": bool(playlist_errors),
                        "metrics": self._state["last_metrics"], **summary(self._state)}
            except Exception as error:
                # 不记录响应体、Cookie 或认证数据；出错也保留已提交成功的账本。
                self._state["last_error"] = str(error)[:250]
                self._save(self._state)
                logger.error(f"音乐歌单同步失败：{str(error)[:250]}")
                return {"success": False, **summary(self._state)}

    def status(self):
        """返回同步概要、有效目录与下载保护状态。"""
        state = self.get_data(self.STATE_KEY) or {"tracks": {}}
        try:
            resolved = self._resolved_settings()
        except Exception:
            resolved = {"error": "MP 默认下载器或音乐目录暂时无法读取"}
        return {"success": True, "enabled": self.get_state(), "dry_run": self._config.get("dry_run"),
                "resolved_settings": resolved,
                "interval_minutes": self._config["interval"], "subscribe_workers": self._config["subscribe_workers"],
                "maintenance": {"library_scan_interval_seconds": self._status_index.ttl,
                                "library_index": self._status_index.snapshot(),
                                "history_retention_days": RETENTION_DAYS,
                                "last_cleanup": state.get("last_cleanup", {})},
                "immediate_search": self._config["immediate_search"], "metrics": state.get("last_metrics", {}),
                "last_search": state.get("last_search", {}), "single_track_only": True,
                "split_album_selection": True, "skip_cue": True, "adapter_error": self._adapter_error,
                "selected_downloads": list((self.get_data("selected_downloads") or {}).values())[-10:],
                "recent_file_checks": self.get_data("single_track_checks") or [], **summary(state)}

    def get_api(self):
        """声明受宿主认证保护的同步、状态及页面接口。"""
        return [
            {"path": "/sync", "endpoint": self.sync, "methods": ["POST"], "auth": "apikey", "summary": "立即同步 QQ 歌单"},
            {"path": "/status", "endpoint": self.status, "methods": ["GET"], "auth": "apikey", "summary": "QQ 歌单同步状态"},
            {"path": "/selection", "endpoint": self.selection_details, "methods": ["GET"], "auth": "apikey", "summary": "读取歌单选曲任务的真实文件优先级"},
            {"path": "/page_data", "endpoint": self.page_data, "methods": ["GET"], "auth": "bear", "summary": "歌单页面数据"},
            {"path": "/page_downloads", "endpoint": self.page_downloads, "methods": ["GET"], "auth": "bear", "summary": "歌单页面实时下载进度"},
            {"path": "/page_sync", "endpoint": self.sync, "methods": ["POST"], "auth": "bear", "summary": "从歌单页面立即同步"},
        ]

    def page_data(self):
        """投影供交互页面使用的歌单与歌曲数据。"""
        state = self.get_data(self.STATE_KEY) or {"tracks": {}}
        try:
            settings = self._resolved_settings()
        except Exception:
            settings = {"error": "MP 默认下载器或音乐目录暂时无法读取"}
        registry = self.get_data("selected_downloads") or {}
        with self._status_lock:
            lifecycle = song_lifecycle(state, registry, {}, [], library_files=self._status_library_files,
                                       file_exists=lambda path, storage: self._status_file_exists(path, storage, settings))
        return page_projection(state, summary(state), self._config, settings, registry,
                               self.get_data("single_track_checks") or [], self._adapter_error, lifecycle,
                               image_url=SecurityUtils.sign_url)

    def _status_file_exists(self, path, storage, settings):
        root = settings.get("library_path")
        if not path or not root or ".." in Path(path).parts or not Path(path).is_relative_to(Path(root)):
            return False
        storage = storage or "local"
        if storage != (settings.get("library_storage") or "local"):
            return False
        # Remote destinations use MP's successful transfer record; never scan them as local paths.
        if storage != "local":
            return True
        if not Path(path).is_absolute() or not Path(root).is_absolute():
            return False
        try:
            return Path(path).is_file() and Path(path).stat().st_size > 0
        except OSError:
            return False

    def _status_transfer_rows(self, filters):
        rows, page = [], 1
        while True:
            result = list_transfer_history(filters, {"page": page, "count": 200})
            rows.extend({key: getattr(item, key, None) for key in
                         ("id", "src", "dest", "dest_storage", "status", "download_hash",
                          "media_source", "media_id", "music_type", "title")} for item in result.items)
            if not result.has_next:
                return rows
            page += 1

    def _status_download_tasks(self, registry, needed):
        groups, tasks = {}, {}
        for torrent_hash, entry in registry.items():
            groups.setdefault(entry.get("downloader"), []).append(torrent_hash)
        for downloader, hashes in groups.items():
            try:
                server = self._qb_service(downloader).instance
                rows, error = server.get_torrents(ids=hashes)
                if error:
                    raise SelectionError("下载器状态暂不可用")
                found = {str(row.get("hash", "")).lower(): row for row in rows or []}
            except Exception:
                tasks.update({torrent_hash: {"success": False} for torrent_hash in hashes})
                continue
            for torrent_hash in hashes:
                row = found.get(torrent_hash.lower())
                task = {"success": True, "state": row.get("state") if row else "missing",
                        "progress": row.get("progress") if row else None, "file_priorities": []}
                if row and needed.intersection(registry[torrent_hash].get("matches", {})):
                    try:
                        task["file_priorities"] = server.get_files(torrent_hash, retry=1, interval=0) or []
                    except Exception:
                        task["success"] = False
                tasks[torrent_hash] = task
        return tasks

    def _cached_library_index(self, state, wanted, settings):
        return self._status_index.get(
            settings=settings, wanted=wanted,
            titles={text_key(item["song"]["title"]) for item in state.get("tracks", {}).values() if item.get("present")},
            scan=self._library_index, stopped=self._stop.is_set,
        )

    def _active_subscription_keys(self):
        """Finished native history is not an active subscription retention requirement."""
        active, page = set(), 1
        while True:
            result = list_subscriptions({"media_types": [MediaType.MUSIC]}, {"page": page, "count": 200})
            active.update(track_key(self._state, item.media_source, item.media_id) for item in result.items
                          if str(item.media_source or "") in MUSIC_SOURCES)
            if not result.has_next:
                return active
            page += 1

    def _cleanup_history(self, now):
        """At most daily, retire inactive bookkeeping without weakening selected-file guards."""
        if self._stop.is_set() or not cleanup_due(self._state, now):
            return
        try:
            active = self._active_subscription_keys()
            settings = self._resolved_settings()
            # Download submissions update this same registry under the same lock.
            with self._selection_lock:
                registry = self.get_data("selected_downloads") or {}
                candidates = {key: entry for key, entry in registry.items()
                              if expired(entry.get("at"), now) and entry.get("phase") == "started"
                              and not active.intersection(entry.get("matches", {}))}
                tasks = self._status_download_tasks(candidates, set()) if candidates else {}
                retired = []
                for key, entry in candidates.items():
                    if self._stop.is_set():
                        return
                    task = tasks.get(key, {})
                    if not task.get("success") or task.get("state") != "missing":
                        continue
                    rows = self._status_transfer_rows({"media_types": [MediaType.MUSIC], "download_hash": key})
                    if retired_download({**entry, "hash": key}, task, rows, now=now,
                                        source_absent=local_source_absent,
                                        file_exists=lambda path, storage: self._status_file_exists(path, storage, settings)):
                        retired.append(key)
                for key in retired:
                    del registry[key]
                counts = prune_history(self._state, registry, now=now, active_subscriptions=active)
                if retired:
                    self.save_data("selected_downloads", registry)
                self._state["last_cleanup"] = {"at": now, "retention_days": RETENTION_DAYS,
                                               **counts, "downloads": len(retired)}
                self._save(self._state)
        except Exception:
            # Missing host facts never authorize deleting protective records; retry next sync.
            logger.warning("歌单历史清理暂缓，保留原记录，下次同步重试")

    def page_downloads(self):
        with self._status_lock:
            state = self.get_data(self.STATE_KEY) or {"tracks": {}}
            registry = self.get_data("selected_downloads") or {}
            try:
                settings = self._resolved_settings()
            except Exception:
                settings = {}
            checked = {}

            def exists(path, storage):
                key = (path, storage)
                if key not in checked:
                    checked[key] = self._status_file_exists(path, storage, settings)
                return checked[key]

            lifecycle = song_lifecycle(state, registry, {}, [], library_files=self._status_library_files, file_exists=exists)
            transfers, warning = [], ""
            needed = set(lifecycle["states"]) - set(lifecycle["library_files"])
            if needed:
                try:
                    transfers.extend(self._status_transfer_rows({"media_types": [MediaType.MUSIC],
                                                               "media_sources": [MediaSource(source) for source in MUSIC_SOURCES]}))
                except Exception:
                    warning = "部分整理记录暂时无法读取，入库状态将在下次更新时核对"
                for torrent_hash, entry in registry.items():
                    if needed.intersection(entry.get("matches", {})):
                        try:
                            transfers.extend(self._status_transfer_rows({"media_types": [MediaType.MUSIC],
                                                                       "download_hash": torrent_hash}))
                        except Exception:
                            warning = "部分整理记录暂时无法读取，入库状态将在下次更新时核对"
            confirmed = song_lifecycle(state, registry, {}, transfers, library_files=lifecycle["library_files"], file_exists=exists)
            missing = {mid: state["tracks"][mid]["song"] for mid in confirmed["states"] if mid not in confirmed["library_files"]}
            try:
                index = self._cached_library_index(state, {text_key(song["title"]) for song in missing.values()}, settings)
                for mid, song in missing.items():
                    path = next((index[(text_key(song["title"]), text_key(artist))] for artist in song.get("artists", [])
                                 if (text_key(song["title"]), text_key(artist)) in index), None)
                    if path and exists(path, "local"):
                        confirmed["library_files"][mid] = {"path": path, "storage": "local"}
            except Exception:
                warning = "部分本地歌曲标签暂时无法读取，入库状态将在下次更新时核对"
            tasks = self._status_download_tasks(registry, set(confirmed["states"]) - set(confirmed["library_files"]))
            lifecycle = song_lifecycle(state, registry, tasks, transfers, library_files=confirmed["library_files"], file_exists=exists)
            self._status_library_files = lifecycle["library_files"]
            return {"success": True, "downloads": download_cards(registry, state.get("tracks", {}), lambda key: tasks[key]),
                    "song_states": lifecycle["states"], "status_counts": lifecycle["counts"],
                    "status_updated_at": time.time(), "status_warning": warning}

    def get_render_mode(self):
        """使用宿主 Vue 共享运行时及插件静态资源入口。"""
        return "vue", "dist/assets"

    def get_form(self):
        """提供原生回退表单和当前配置默认值。"""
        fields = [
            ("VSwitch", "enabled", "启用持续同步", {}),
            ("VSwitch", "dry_run", "只预览歌单，暂不创建订阅", {}),
            ("VTextarea", "playlist_urls", "QQ 音乐歌单：每行一个链接或 ID", {"rows": 4, "autoGrow": True}),
            ("VTextarea", "netease_playlist_urls", "网易云音乐歌单：每行一个链接或 ID", {"rows": 4, "autoGrow": True}),
            ("VTextField", "interval", "同步间隔（分钟，至少 1）", {"type": "number"}),
            ("VTextField", "subscribe_workers", "同时创建订阅数（1–8，推荐 4）", {"type": "number"}),
            ("VSwitch", "immediate_search", "建好订阅立即搜索下载", {}),
            ("VTextField", "downloader", "下载器（留空跟随 MP 默认）", {"placeholder": "使用 MP 音乐订阅或系统默认下载器", "hint": "分轨选曲需要 qBittorrent", "persistentHint": True}),
            ("VTextField", "save_path", "下载目录（留空跟随 MP 音乐目录）", {"placeholder": "使用设置中的音乐下载目录"}),
            ("VTextField", "library_path", "音乐库目录（留空跟随 MP 音乐目录）", {"placeholder": "使用设置中的音乐库目录", "hint": "用于检查已有歌曲；整理位置由 MP 目录设置决定", "persistentHint": True}),
        ]
        content = [{"component": "VCol", "props": {"cols": 12}, "content": [{"component": component,
                    "props": {"model": model, "label": label, **props}}]} for component, model, label, props in fields]
        content.append({"component": "VCol", "props": {"cols": 12}, "content": [{"component": "VAlert",
                        "props": {"type": "info", "variant": "tonal"},
                        "text": "QQ 与网易云歌单分开填写，每行一个链接或 ID。公开歌单无需登录，同一录音跨平台去重。新增歌曲保持单曲订阅并立即搜索；分轨专辑仅勾选歌单歌曲，CUE 整轨跳过。"}]})
        return [{"component": "VForm", "content": [{"component": "VRow", "content": content}]}], {
            "enabled": False, "dry_run": True, "playlist_urls": self._config.get("playlist_urls", ""), "interval": 60,
            "netease_playlist_urls": self._config.get("netease_playlist_urls", ""),
            "subscribe_workers": 4, "immediate_search": True,
            "downloader": "", "save_path": "", "library_path": "",
        }

    def get_page(self):
        # Keep a native fallback and the host's has_page discovery contract.
        """提供原生回退详情页面。"""
        return [{"component": "VAlert", "props": {"type": "info", "variant": "tonal"},
                 "text": "QQ 音乐歌单数据使用交互页面展示。若未加载，请刷新插件页面。"}]
