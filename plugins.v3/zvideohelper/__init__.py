from datetime import datetime, timedelta
import sqlite3
import json
from .DoubanHelper import DoubanHelper
from .subtitles import SubtitleService, SubtitleError
from .automation import SubtitleAutomation
from .selection import validate_lookup, project_media, project_media_choices, project_seasons, project_episodes
from fastapi import Body, File, UploadFile
from .tool_install import install_tool
from fastapi.responses import FileResponse
from app.helper.directory import DirectoryHelper
from app.chain.media import MediaChain
from app.domain.metainfo import MetaInfo
from app.modules.themoviedb.tmdbapi import TmdbApi
from itertools import zip_longest
from app.schemas.types import MediaSource, MediaType
from enum import Enum

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.schemas.types import EventType, NotificationType
from app.core.event import eventmanager, Event
from pathlib import Path

from app.core.config import settings
from app.plugins import _PluginBase
from typing import Any, List, Dict, Tuple, Optional
from app.log import logger
import time

# 豆瓣状态
class DoubanStatus(Enum):
    WATCHING = "do"
    DONE = "collect"


class ZvideoHelper(_PluginBase):
    # 插件名称
    plugin_name = "极影视助手"
    # 插件描述
    plugin_desc = "定时补全中文字幕、网页授权、手动字幕搜索下载与豆瓣同步"
    # 插件图标
    plugin_icon = "zvideo.png"
    # 插件版本
    plugin_version = "1.9.2"
    # 插件作者
    plugin_author = "DzAvril"
    # 作者主页
    author_url = "https://github.com/DzAvril"
    # 插件配置项ID前缀
    plugin_config_prefix = "zvideohelper"
    # 加载顺序
    plugin_order = 1
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _enabled = False
    _cron = None
    _notify = False
    _onlyonce = False
    _sync_douban_status = False
    _clean_cache = False
    _use_douban_score = False
    _douban_helper = None
    _cached_data: dict = {}
    _db_path = ""
    _cookie = ""
    _douban_score_update_days = 0
    # 定时器
    _scheduler: Optional[BackgroundScheduler] = None
    _should_stop = False

    def init_plugin(self, config: dict = None):
        self._should_stop = False
        # 停止现有任务
        self.stop_service()
        self._subtitle_enabled = (config or {}).get("subtitle_enabled", True)
        self._subtitle_config = {k:v for k,v in (config or {}).items() if k.startswith("subtitle_")}
        self._subtitle_series_cache = {}
        self._subtitle_service = SubtitleService(self.get_data_path() / "subtitle-cli")

        if config:
            self._enabled = config.get("enabled")
            self._cron = config.get("cron")
            self._notify = config.get("notify")
            self._onlyonce = config.get("onlyonce")
            self._db_path = config.get("db_path")
            self._cookie = config.get("cookie")
            self._sync_douban_status = config.get("sync_douban_status")
            self._clean_cache = config.get("clean_cache")
            self._use_douban_score = config.get("use_douban_score")
            self._douban_score_update_days = int(config.get("douban_score_update_days") or 0)
            if self._sync_douban_status or self._use_douban_score:
                self._douban_helper = DoubanHelper(user_cookie=self._cookie)

        try:
            roots = [d.library_path for d in DirectoryHelper().get_local_library_dirs() if d.media_type in ("电影", "电视剧", None, "")]
        except Exception:
            roots = []
        self._subtitle_automation = SubtitleAutomation(self.get_data_path(), self._subtitle_service, roots, self._subtitle_config,
            notice=lambda text:self.systemmessage.put(text, title="极影视字幕授权"), language_resolver=self.subtitle_original_language)

        # 获取历史数据
        self._cached_data = (
            self.get_data("zvideohelper")
            if self.get_data("zvideohelper") is not None
            else dict()
        )
        # 加载模块
        if self._onlyonce:
            if self._clean_cache:
                self._cached_data = {}
                self.save_data("zvideohelper", self._cached_data)
                self._clean_cache = False
            # 检查数据库路径是否存在
            path = Path(self._db_path)
            if not path.exists():
                logger.error(f"极影视数据库路径不存在: {self._db_path}")
                self._onlyonce = False
                self._clean_cache = False
                self._update_config()
                if self._notify:
                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title=f"【极影视助手】",
                        text=f"极影视数据库路径不存在: {self._db_path}",
                    )
                return

            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            logger.info(f"极影视助手服务启动，立即运行一次")
            self._scheduler.add_job(
                func=self.do_job,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ))
                + timedelta(seconds=3),
                name="极影视助手",
            )
            # 关闭一次性开关
            self._onlyonce = False
            self._update_config()

            # 启动任务
            if self._scheduler.get_jobs():
                self._scheduler.print_jobs()
                self._scheduler.start()

    def get_state(self) -> bool:
        return bool(self._enabled or getattr(self, "_subtitle_enabled", True))

    def _update_config(self):
        self.update_config(
            {
                "onlyonce": False,
                "cron": self._cron,
                "enabled": self._enabled,
                "notify": self._notify,
                "db_path": self._db_path,
                "cookie": self._cookie,
                "sync_douban_status": self._sync_douban_status,
                "clean_cache": self._clean_cache,
                "use_douban_score": self._use_douban_score,
                "douban_score_update_days": self._douban_score_update_days,
                **self._subtitle_config,
                "subtitle_enabled": self._subtitle_enabled,
            }
        )

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        :return: 命令关键字、事件、描述、附带数据
        """
        return [
            {
                "cmd": "/sync_zvideo_to_douban",
                "event": EventType.PluginAction,
                "desc": "同步极影视观影状态",
                "category": "",
                "data": {"action": "sync_zvideo_to_douban"},
            },
            {
                "cmd": "/use_douban_score",
                "event": EventType.PluginAction,
                "desc": "极影视使用豆瓣评分",
                "category": "",
                "data": {"action": "use_douban_score"},
            },
            {
                "cmd": "/use_tmdb_score",
                "event": EventType.PluginAction,
                "desc": "极影视使用tmdb评分",
                "category": "",
                "data": {"action": "use_tmdb_score"},
            },
        ]

    @eventmanager.register(EventType.PluginAction)
    def handle_command(self, event: Event):
        if event:
            event_data = event.event_data
            if event_data:
                if (
                    event_data.get("action") == "sync_zvideo_to_douban"
                    or event_data.get("action") == "use_douban_score"
                    or event_data.get("action") == "use_tmdb_score"
                ):
                    if event_data.get("action") == "sync_zvideo_to_douban":
                        logger.info("收到命令，开始同步极影视观影状态 ...")
                        self.post_message(
                            channel=event.event_data.get("channel"),
                            title="开始同步极影视观影状态 ...",
                            userid=event.event_data.get("user"),
                        )
                        self.sync_douban_status()
                        if event:
                            self.post_message(
                                channel=event.event_data.get("channel"),
                                title="同步极影视观影状态完成！",
                                userid=event.event_data.get("user"),
                            )
                    elif event_data.get("action") == "use_douban_score":
                        logger.info("收到命令，开始使用豆瓣评分 ...")
                        self.post_message(
                            channel=event.event_data.get("channel"),
                            title="开始使用豆瓣评分 ...",
                            userid=event.event_data.get("user"),
                        )
                        self.use_douban_score()
                        if event:
                            self.post_message(
                                channel=event.event_data.get("channel"),
                                title="使用豆瓣评分完成！",
                                userid=event.event_data.get("user"),
                            )
                    elif event_data.get("action") == "use_tmdb_score":
                        logger.info("收到命令，开始使用tmdb评分 ...")
                        self.post_message(
                            channel=event.event_data.get("channel"),
                            title="开始使用tmdb评分 ...",
                            userid=event.event_data.get("user"),
                        )
                        self.use_tmdb_score()
                        if event:
                            self.post_message(
                                channel=event.event_data.get("channel"),
                                title="使用tmdb评分完成！",
                                userid=event.event_data.get("user"),
                            )

    def get_api(self) -> List[Dict[str, Any]]:
        routes = [("subtitle_series", self.subtitle_series, "GET"), ("subtitle_media_search", self.subtitle_media_search, "GET"), ("subtitle_selected", self.subtitle_selected, "POST"), ("subtitle_status", self.subtitle_status, "GET"), ("subtitle_search", self.subtitle_search, "GET"),
            ("subtitle_preview", self.subtitle_preview, "POST"), ("subtitle_download", self.subtitle_download, "POST"),
            ("subtitle_file", self.subtitle_file, "GET"), ("subtitle_library", self.subtitle_library, "GET"),
            ("subtitle_scan", self.subtitle_scan, "POST"), ("subtitle_auth_start", self.subtitle_auth_start, "POST"),
            ("subtitle_auth_state", self.subtitle_auth_state, "GET"), ("subtitle_tool_install", self.subtitle_tool_install, "POST"), ("subtitle_auth_submit", self.subtitle_auth_submit, "POST")]
        return [{"path":"/"+name, "endpoint":endpoint, "methods":[method], "auth":"bear", "summary":"极影视字幕"} for name,endpoint,method in routes]

    def subtitle_status(self):
        return {"success": True, "enabled": self._subtitle_enabled, **self._subtitle_service.status()}

    def subtitle_search(self, keyword: str = "", imdb_id: str = ""):
        if not self._subtitle_enabled:return {"success":False, "message":"请先开启字幕功能"}
        return self._subtitle_service.search(keyword, imdb_id)

    def subtitle_media_search(self, keyword: str = "", media_type: str = "all"):
        if not self._subtitle_enabled:return {"success":False, "message":"请先开启字幕功能"}
        try:keyword = validate_lookup(keyword, media_type)
        except ValueError as error:return {"success":False, "message":str(error)}
        try:
            chain = MediaChain();groups = []
            for kind in ([MediaType.MOVIE,MediaType.TV] if media_type == 'all' else [MediaType.MOVIE if media_type == 'movie' else MediaType.TV]):
                meta = MetaInfo(keyword);meta.type = kind
                groups.append(chain.search_medias(meta=meta, media_source=MediaSource.TMDB) or [])
            records = [item for row in zip_longest(*groups) for item in row if item is not None]
            items = [item for item in project_media_choices(records) if media_type == 'all' or item['media_type'] == media_type]
            return {"success":True, "items":items, "count":len(items),
                "message":"" if items else "未找到作品，可尝试原名或加上年份再搜索"}
        except Exception:
            return {"success":False, "message":"影视资料查询暂不可用，请检查 MoviePilot 的 TMDB 连接后重试"}

    def subtitle_series(self, tmdb_id: str = "", season: int = -1):
        if not self._subtitle_enabled:return {"success":False,"message":"请先开启字幕功能"}
        if not tmdb_id.isascii() or not tmdb_id.isdigit() or not 1 <= len(tmdb_id) <= 12 or int(tmdb_id)<=0 or not -1 <= season <= 999:
            return {"success":False,"message":"请从列表选择电视剧和季"}
        key = (tmdb_id,season);cached = self._subtitle_series_cache.get(key)
        if cached and time.monotonic()-cached[0]<600:return cached[1]
        try:
            details = MediaChain().recognize_media(media_source=MediaSource.TMDB, media_id=tmdb_id, mtype=MediaType.TV)
            media = project_media(details) if details else None
            if not media or media['id']!=tmdb_id or media['media_type']!='tv':return {"success":False,"message":"无法读取该剧资料，请稍后重试"}
            seasons = project_seasons(details)
            if not seasons:return {"success":False,"message":"TMDB 尚未提供该剧季集资料"}
            if season>=0 and season not in {s['number'] for s in seasons}:return {"success":False,"message":"所选季不在该剧的季列表中"}
            episodes = []
            if season>=0:
                data = TmdbApi().get_tv_season_detail(int(tmdb_id),season)
                episodes = project_episodes(data,season)
                if not episodes:return {"success":False,"message":"该季暂无可用集列表，请选择其他季或稍后重试"}
            result = {"success":True,"selected_media":media,"seasons":seasons,"season":season,"episodes":episodes}
            if len(self._subtitle_series_cache)>=64:self._subtitle_series_cache.clear()
            self._subtitle_series_cache[key]=(time.monotonic(),result)
            return result
        except Exception:return {"success":False,"message":"季集资料查询失败，请检查 TMDB 连接后重试"}

    def subtitle_selected(self, payload: dict = Body(...)):
        if not self._subtitle_enabled:return {"success":False, "message":"请先开启字幕功能"}
        identifier, kind = str(payload.get('tmdb_id') or ''), payload.get('media_type')
        if not identifier.isascii() or not identifier.isdigit() or not 1 <= len(identifier) <= 12 or int(identifier) <= 0 or not isinstance(kind,str) or kind not in {'movie','tv'}:
            return {"success":False, "message":"请先从候选列表选择一部电影或剧集"}
        try:
            details = MediaChain().recognize_media(media_source=MediaSource.TMDB, media_id=identifier,
                mtype=MediaType.MOVIE if kind == 'movie' else MediaType.TV)
            media = project_media(details) if details else None
        except Exception:media = None
        if not media or media['id'] != identifier or media['media_type'] != kind:
            return {"success":False, "message":"无法读取所选作品资料，请重新选择或稍后重试"}
        if kind == 'tv':
            season, episode = payload.get('season'), payload.get('episode')
            if type(season) is not int or type(episode) is not int or not 0<=season<=999 or not 1<=episode<=9999:
                return {"success":False,"message":"请先选择季和集，再查询本集字幕"}
            catalog = self.subtitle_series(identifier,season)
            if not catalog.get('success'):return catalog
            selected = next((ep for ep in catalog['episodes'] if ep['number']==episode),None)
            if not selected:return {"success":False,"message":"所选集不在该季的集列表中"}
            media.update(season=season,episode=episode,episode_title=selected['name'])
            return self._subtitle_service.search_episode(media,season,episode)
        return self._subtitle_service.search_selected(media)

    def subtitle_preview(self, payload: dict = Body(...)):
        if not self._subtitle_enabled:return {"success":False, "message":"请先开启字幕功能"}
        return self._subtitle_service.preview(str(payload.get("id") or ""))

    def subtitle_download(self, payload: dict = Body(...)):
        if not self._subtitle_enabled:return {"success":False, "message":"请先开启字幕功能"}
        return self._subtitle_automation.manual_download(str(payload.get("file_id") or ""), str(payload.get("media_id") or ""))

    def subtitle_file(self, ticket: str = ""):
        if not self._subtitle_enabled:return {"success":False, "message":"请先开启字幕功能"}
        try:
            path, name = self._subtitle_service.download_file(ticket)
            return FileResponse(path, filename=name, media_type="application/octet-stream", headers={"Cache-Control":"no-store"})
        except SubtitleError as error:return {"success":False, "message":str(error)}

    def subtitle_library(self):
        return self._subtitle_automation.snapshot()

    def subtitle_scan(self, payload: dict = Body(...)):
        if not self._subtitle_enabled:return {"success":False, "message":"请先开启字幕功能"}
        return self._subtitle_automation.start(download=payload.get("download") is True, keyword=payload.get("keyword", ""))

    async def subtitle_tool_install(self, file: UploadFile = File(...)):
        if not self._subtitle_service._lock.acquire(blocking=False):return {"success":False,"message":"字幕服务正忙"}
        try:
            content = await file.read(8 * 1024 * 1024 + 1)
            return install_tool(self._subtitle_service.root, content)
        except OSError:return {"success":False,"message":"工具导入失败，请检查插件数据目录权限"}
        finally:self._subtitle_service._lock.release();await file.close()

    def subtitle_auth_start(self):
        if not self._subtitle_enabled:return {"success":False, "message":"请先开启字幕功能"}
        if self._subtitle_automation.progress['running']:return {"success":False, "message":"请等待当前媒体检查结束"}
        if not self._subtitle_service._lock.acquire(blocking=False):return {"success":False, "message":"字幕服务正忙，请稍后重试"}
        try:return self._subtitle_service.authorization.start()
        finally:self._subtitle_service._lock.release()

    def subtitle_auth_state(self):
        result = self._subtitle_service.authorization.state()
        if result['state'] == 'complete':
            self._subtitle_service.auth_failed = False
            self._subtitle_service._cache.clear()
        return {"success":True, **result}

    def subtitle_auth_submit(self, payload: dict = Body(...)):
        # Authorization code stays in the POST body and the private terminal pipe.
        return self._subtitle_service.authorization.submit(payload.get("session", ""), payload.get("code", ""))

    @staticmethod
    def subtitle_original_language(metadata):
        if not metadata.get('tmdb_id'):return ''
        media = MediaChain().recognize_media(media_source=MediaSource.TMDB, media_id=metadata['tmdb_id'],
            mtype=MediaType.TV if metadata.get('season') is not None else MediaType.MOVIE)
        return getattr(media, 'original_language', '') if media else ''

    def subtitle_scheduled_job(self):
        if self._subtitle_enabled and self._subtitle_config.get("subtitle_auto"):
            self._subtitle_automation.start(download=True)

    def get_render_mode(self):
        return "vue", "dist/assets"

    def get_service(self) -> List[Dict[str, Any]]:
        services = []
        if self._enabled and self._cron:
            services.append({"id":"ZvideoHelper", "name":"极影视助手", "trigger":CronTrigger.from_crontab(self._cron), "func":self.do_job, "kwargs":{}})
        if self._subtitle_enabled and self._subtitle_config.get("subtitle_auto"):
            try:
                trigger = CronTrigger.from_crontab(self._subtitle_config.get("subtitle_cron") or "*/30 * * * *")
                services.append({"id":"ZvideoHelperSubtitles", "name":"极影视中文字幕补全", "trigger":trigger, "func":self.subtitle_scheduled_job, "kwargs":{}})
            except ValueError:logger.warning("极影视字幕执行周期无效，请检查插件设置")
        return services

    def do_job(self):
        self._should_stop = False
        if self._sync_douban_status:
            self.sync_douban_status()
        if self._use_douban_score:
            self.use_douban_score()
        else:
            self.use_tmdb_score()

    def set_douban_watching(self):
        watching_douban_id = []
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT collection_id FROM zvideo_playlist")
            collection_ids = cursor.fetchall()
            collection_ids = set([collection_id[0] for collection_id in collection_ids])
            meta_info_list = []
            for collection_id in collection_ids:
                if self._should_stop:
                    logger.info("检测到中断请求，停止同步在看状态...")
                    break
                cursor.execute(
                    "SELECT meta_info FROM zvideo_collection WHERE collection_id = ? AND type = 200",
                    (collection_id,),
                )
                rows = cursor.fetchall()
                for row in rows:
                    if self._should_stop:
                        logger.info("检测到中断请求，停止同步在看状态...")
                        break
                    try:
                        meta_info_json = json.loads(row[0])
                        meta_info_list.append(meta_info_json)
                    except json.JSONDecodeError as e:
                        logger.error(
                            f"An error occurred while decoding JSON for collection_id {collection_id}: {e}"
                        )
            for meta_info in meta_info_list:
                if self._should_stop:
                    logger.info("检测到中断请求，停止同步在看状态...")
                    break
                try:
                    douban_id = meta_info["relation"]["douban"]["douban_id"]
                    title = meta_info["title"]
                except Exception as e:
                    logger.error(f"meta_info: {meta_info}，解析失败: {e}")
                    continue
                if self._cached_data.get(title) is not None:
                    logger.info(f"已处理过: {title}，跳过...")
                    continue
                if douban_id == 0:
                    _, douban_id, _ = self.get_douban_info_by_name(title)
                if douban_id is not None:
                    watching_douban_id.append((title, douban_id))
                else:
                    logger.error(f"未找到豆瓣ID: {title}")

        except sqlite3.Error as e:
            logger.error(f"An error occurred: {e}")

        finally:
            # 确保游标和连接在使用完后关闭
            if cursor:
                cursor.close()
            if conn:
                conn.close()
            message = ""
            for item in watching_douban_id:
                status = DoubanStatus.WATCHING.value
                ret = self._douban_helper.set_watching_status(
                    subject_id=item[1], status=status, private=True
                )
                if ret:
                    self._cached_data[item[0]] = status
                    logger.info(f"title: {item[0]}, douban_id: {item[1]}，已标记为在看")
                    message += f"{item[0]}，已标记为在看\n"
                else:
                    logger.error(
                        f"title: {item[0]}, douban_id: {item[1]}，标记在看失败"
                    )
                    message += f"{item[0]}，***标记在看失败***\n"
            if self._notify and len(message) > 0:
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title="【极影视助手】",
                    text=message,
                )

    def set_douban_done(self):
        watching_douban_id = []
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT collection_id FROM zvideo_collection_tags WHERE tag_name='是否看过'"
            )
            collection_ids = cursor.fetchall()
            collection_ids = set([collection_id[0] for collection_id in collection_ids])
            meta_info_list = []
            for collection_id in collection_ids:
                if self._should_stop:
                    logger.info("检测到中断请求，停止同步已看状态...")
                    break
                cursor.execute(
                    "SELECT meta_info FROM zvideo_collection WHERE collection_id = ?",
                    (collection_id,),
                )
                rows = cursor.fetchall()
                for row in rows:
                    if self._should_stop:
                        logger.info("检测到中断请求，停止同步已看状态...")
                        break
                    try:
                        meta_info_json = json.loads(row[0])
                        meta_info_list.append(meta_info_json)
                    except json.JSONDecodeError as e:
                        logger.error(
                            f"An error occurred while decoding JSON for collection_id {collection_id}: {e}"
                        )
            for meta_info in meta_info_list:
                if self._should_stop:
                    logger.info("检测到中断请求，停止同步已看状态...")
                    break
                try:
                    douban_id = meta_info["relation"]["douban"]["douban_id"]
                    title = meta_info["title"]
                except Exception as e:
                    logger.error(f"meta_info: {meta_info}，解析失败: {e}")
                    continue
                if self._cached_data.get(title) == DoubanStatus.DONE.value:
                    logger.info(f"已处理过: {title}，跳过...")
                    continue
                if douban_id == 0:
                    _, douban_id, _ = self.get_douban_info_by_name(title)
                if douban_id is not None:
                    watching_douban_id.append((title, douban_id))
                else:
                    logger.error(f"未找到豆瓣ID: {title}")

        except sqlite3.Error as e:
            logger.error(f"An error occurred: {e}")

        finally:
            # 确保游标和连接在使用完后关闭
            if cursor:
                cursor.close()
            if conn:
                conn.close()
            message = ""
            for item in watching_douban_id:
                status = DoubanStatus.DONE.value
                ret = self._douban_helper.set_watching_status(
                    subject_id=item[1], status=status, private=True
                )
                if ret:
                    self._cached_data[item[0]] = status
                    logger.info(f"title: {item[0]}, douban_id: {item[1]},已标记为已看")
                    message += f"{item[0]}，已标记为已看\n"
                else:
                    logger.error(
                        f"title: {item[0]}, douban_id: {item[1]}, 标记已看失败"
                    )
                    message += f"{item[0]}，***标记已看失败***\n"
            if self._notify and len(message) > 0:
                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title="【极影视助手】",
                    text=message,
                )

    def get_douban_info_by_name(self, title):
        logger.info(f"正在查询：{title}")
        # 延迟10s，以防频繁请求被豆瓣封接口
        time.sleep(10)
        subject_name, subject_id, score = self._douban_helper.get_subject_id(
            title=title
        )
        logger.info(
            f"查询到：subject_name: {subject_name}, subject_id: {subject_id}, score: {score}"
        )
        return subject_name, subject_id, score

    # 填充zvideo_collection中所有行的douban_score
    def fill_douban_score(self):
        logger.info("获取豆瓣评分...")
        conn = sqlite3.connect(self._db_path)
        conn.text_factory = str
        cursor = conn.cursor()
        cursor.execute("SELECT rowid, extend_type, meta_info, updated_at FROM zvideo_collection")
        rows = cursor.fetchall()
        message = ""
        for row in rows:
            if self._should_stop:
                logger.info("检测到中断请求，停止获取豆瓣评分...")
                break
            try:
                rowid, extend_type, meta_info_json, updated_at = row
                # 合集，不处理
                if extend_type == 7:
                    continue
                meta_info_dict = json.loads(meta_info_json)
                # 如果meta_info为空，跳过
                if meta_info_dict.get("douban_score") is None:
                    continue
                title = meta_info_dict["title"]
                current_time = datetime.now()
                need_update = False
                # 检查是否需要更新评分
                try:
                    douban_score = float(meta_info_dict.get("douban_score", 0))
                except (TypeError, ValueError):
                    douban_score = 0
                if douban_score == 0:
                    need_update = True
                    logger.info(f"未找到豆瓣评分，需要更新：{title}")
                elif updated_at and self._douban_score_update_days > 0:
                    try:
                        update_at_str = updated_at.split('+')[0]
                        if '.' in update_at_str:
                            parts = update_at_str.split('.')
                            if len(parts) > 1:
                                microseconds = parts[1][:6]
                                update_at_str = f"{parts[0]}.{microseconds}"
                            update_time = datetime.strptime(update_at_str, "%Y-%m-%d %H:%M:%S.%f")
                        else:
                            update_time = datetime.strptime(update_at_str, "%Y-%m-%d %H:%M:%S")
                        time_diff = current_time - update_time
                        if time_diff.days >= self._douban_score_update_days:
                            need_update = True
                            logger.info(f"豆瓣评分已过期，需要更新：{title}，上次更新时间：{update_at_str}")
                    except Exception as e:
                        logger.error(f"解析update_at时间失败: {e}, 原始值: {updated_at}")
                        need_update = True
                elif not updated_at and self._douban_score_update_days > 0:
                    need_update = True
                    logger.info(f"未找到更新时间，需要更新豆瓣评分：{title}")
                if need_update:
                    old_score = meta_info_dict.get("douban_score", 0)
                    try:
                        old_score = float(old_score)
                    except (TypeError, ValueError):
                        old_score = 0
                    try:
                        _, _, score = self.get_douban_info_by_name(title)
                    except Exception as e:
                        logger.error(f"获取豆瓣评分失败: {e}")
                        score = None
                    if score:
                        try:
                            score = float(score)
                        except (TypeError, ValueError):
                            score = 0
                        score_changed = old_score > 0 and old_score != score
                        meta_info_dict["douban_score"] = score
                        updated_meta_info_json = json.dumps(meta_info_dict, ensure_ascii=False)
                        tz = pytz.timezone(settings.TZ)
                        current_time = datetime.now(tz)
                        current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S.%f") + current_time.strftime("%z")[:3] + ":" + current_time.strftime("%z")[3:]
                        cursor.execute(
                            "UPDATE zvideo_collection SET meta_info = ?, updated_at = ? WHERE rowid = ?",
                            (updated_meta_info_json, current_time_str, rowid),
                        )
                        conn.commit()
                        if score_changed:
                            change_direction = "上升" if score > old_score else "下降"
                            change_amount = abs(score - old_score)
                            change_msg = f"更新豆瓣评分：{title} {old_score} → {score} ({change_direction}{change_amount:.1f})"
                            logger.info(change_msg)
                            message += f"{title} 评分{change_direction}：{old_score} → {score}\n"
                        elif old_score == 0 and score > 0:
                            logger.info(f"首次获取豆瓣评分：{title} {score}")
                            message += f"{title} 获取豆瓣评分：{score}\n"
                        else:
                            logger.info(f"豆瓣评分未变化：{title} {score}")
                    else:
                        logger.error(f"未找到豆瓣评分：{title}")
                else:
                    logger.info(
                        f"无需更新豆瓣评分：{title} {meta_info_dict['douban_score']}"
                    )
            except Exception as e:
                logger.error(f"处理条目 {row} 时发生异常: {e}")
        if self._notify and len(message) > 0:
            self.post_message(
                mtype=NotificationType.SiteMessage,
                title="【极影视助手】",
                text=message,
            )
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    def use_douban_score(self):
        logger.info("使用豆瓣评分...")
        self.fill_douban_score()
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        # 将meta_info的douban_score值同步到zvideo_collection表的score列
        cursor.execute(
            """
            UPDATE zvideo_collection
            SET score = CAST(JSON_EXTRACT(meta_info, '$.douban_score') AS DECIMAL(3,1))
            WHERE CAST(JSON_EXTRACT(meta_info, '$.douban_score') AS DECIMAL(3,1)) <> 0.0
            """
        )
        conn.commit()

        if cursor:
            cursor.close()
        if conn:
            conn.close()
        logger.info("更新极影视为豆瓣评分...")

    def use_tmdb_score(self):
        logger.info("使用tmdb评分...")
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()
        # 将meta_info的score值同步到zvideo_collection表的score列
        cursor.execute(
            """
            UPDATE zvideo_collection
            SET score = CAST(JSON_EXTRACT(meta_info, '$.score') AS DECIMAL(3,1))
            WHERE JSON_EXTRACT(meta_info, '$.score') IS NOT NULL
            """
        )
        conn.commit()
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        logger.info("更新极影视为tmdb评分...")

    def sync_douban_status(self):
        self.set_douban_watching()
        self.set_douban_done()
        # 缓存数据
        self.save_data("zvideohelper", self._cached_data)

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol", "props": {"cols": 12},
                                "content": [{"component": "VSwitch", "props": {
                                    "model": "subtitle_enabled", "label": "开启字幕搜索"}}],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "notify",
                                            "label": "开启通知",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "onlyonce",
                                            "label": "立即运行一次",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "sync_douban_status",
                                            "label": "同步在看/已看至豆瓣",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "use_douban_score",
                                            "label": "使用豆瓣评分",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "clean_cache",
                                            "label": "清理缓存数据",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {"model": "cron", "label": "执行周期"},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "douban_score_update_days",
                                            "label": "豆瓣评分更新周期(天)",
                                            "placeholder": "0则不更新",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "cookie",
                                            "label": "豆瓣cookie",
                                            "rows": 1,
                                            "placeholder": "留空则从cookiecloud获取",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "db_path",
                                            "label": "极影视数据库路径",
                                            "rows": 1,
                                            "placeholder": "极影视路径为/zspace/zsrp/sqlite/zvideo/zvideo.db，需先映射路径",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                },
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "error",
                                            "variant": "tonal",
                                            "text": "强烈建议使用前备份数据库，以免因插件bug导致数据库异常",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                },
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "本插件基于极影视数据库扩展功能，需开启ssh后通过portainer、1panel等工具映射极影视数据库路径",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                },
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "极影视默认使用tmdb评分，勾选'使用豆瓣评分'后，将使用豆瓣评分。豆瓣无评分的继续使用tmdb评分",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                },
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "豆瓣评分更新周期是指多少天后重新获取豆瓣评分，防止评分变化。设为0则不更新已有评分",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ], {
            "enabled": False,
            "notify": False,
            "onlyonce": False,
            "cron": "0 0 * * *",
            "douban_score_update_days": 0,
            "subtitle_enabled": True,
        }

    def get_page(self) -> List[dict]:
        return [{"component": "VAlert", "props": {"type": "info", "variant": "tonal"},
                 "text": "在极影视助手的字幕搜索页面输入片名或 IMDb ID。首次使用需完成 NAS 独立授权。"}]

    def stop_service(self):
        """
        退出插件
        """
        self._should_stop = True
        if getattr(self, "_subtitle_automation", None):self._subtitle_automation.stop()
        if getattr(self, "_subtitle_service", None):self._subtitle_service.authorization.close()
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error("退出插件失败：%s" % str(e))
