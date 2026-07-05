import json
import traceback
import hashlib
import time
import random
import threading
import re
from datetime import datetime, timedelta, timezone
from typing import Any, List, Dict, Tuple, Optional
from functools import wraps
from collections import defaultdict
import sqlite3
import os
from urllib.parse import quote

from app.core.event import eventmanager, Event
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import WebhookEventInfo
from app.schemas.types import EventType
from app.core.config import settings

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except Exception:
    BackgroundScheduler = None


class SyncLoopProtector:
    """
    通过一个临时缓存来防止同步操作触发无限循环。
    当一个同步操作（例如，A -> B）成功后，B 会被临时"保护"起来。
    如果在短时间内（如15秒）收到了由 B 触发的相同类型的事件，该事件将被忽略。
    """

    def __init__(self, ttl_seconds: int = 15):
        # 缓存格式: (user_name, item_id, sync_type) -> 触发时间
        self._cache: Dict[Tuple[str, str, str], datetime] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = threading.Lock()

    def add(self, user_name: str, item_id: str, sync_type: str):
        """
        将一个被动同步的用户-项目组合添加到忽略缓存中。
        """
        if not all([user_name, item_id, sync_type]):
            return
        with self._lock:
            cache_key = (user_name, item_id, sync_type)
            self._cache[cache_key] = datetime.now()
            logger.debug(f"添加到防循环缓存: {cache_key}")
            # 主动清理一下过期条目，防止缓存无限增长
            self._cleanup_nolock()

    def is_protected(self, user_name: str, item_id: str, sync_type: str) -> bool:
        """
        检查一个传入的事件是否是被保护的（即，可能是同步循环）。
        """
        if not all([user_name, item_id, sync_type]):
            return False

        with self._lock:
            cache_key = (user_name, item_id, sync_type)
            if cache_key in self._cache:
                event_time = self._cache[cache_key]
                if datetime.now() - event_time < self._ttl:
                    logger.info(f"🔄 检测到循环同步事件，跳过处理: {cache_key}")
                    # 不再立即移除key，让它根据TTL自然过期，以处理并发事件
                    return True
        return False

    def _cleanup_nolock(self):
        """
        在锁内执行，移除缓存中的过期条目。
        """
        now = datetime.now()
        expired_keys = [
            key for key, timestamp in self._cache.items() if now - timestamp > self._ttl]
        for key in expired_keys:
            try:
                del self._cache[key]
            except KeyError:
                pass  # Already deleted by another thread


def retry_on_failure(max_retries=3, base_delay=1, max_delay=60, backoff_factor=2):
    """
    装饰器：为函数添加指数退避重试机制
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    if result:  # 如果成功，直接返回
                        return result
                    elif attempt == max_retries:  # 最后一次尝试失败
                        logger.error(
                            f"{func.__name__} 在 {max_retries} 次重试后仍然失败")
                        return False
                except Exception as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(
                            f"{func.__name__} 重试 {max_retries} 次后仍然出现异常: {str(e)}")
                        raise e

                # 计算延迟时间（指数退避 + 随机抖动）
                delay = min(
                    base_delay * (backoff_factor ** attempt), max_delay)
                jitter = random.uniform(0, delay * 0.1)  # 添加10%的随机抖动
                total_delay = delay + jitter

                logger.warning(
                    f"{func.__name__} 第 {attempt + 1} 次尝试失败，{total_delay:.2f}秒后重试")
                time.sleep(total_delay)

            return False
        return wrapper
    return decorator


class LocalZSpaceInstance:
    """
    本机极影视兼容层实例。

    用于极空间环境中 MoviePilot 未显式配置 ZSpace 媒体服务器时的兜底接入。
    """
    _is_watchsync_zspace = True

    def __init__(self, name: str, host: str, token: str, user_id: str, username: str):
        self.name = name or "极影视"
        self._host = self._standardize_host(host)
        self._apikey = token
        self.user = user_id
        self._username = username or user_id

    @staticmethod
    def _standardize_host(host: str) -> str:
        host = (host or "").strip()
        if not host.endswith("/"):
            host += "/"
        return host

    def _headers(self, extra_headers: Optional[dict] = None) -> dict:
        headers = {
            "X-Emby-Token": self._apikey,
            "X-Emby-Authorization": f"MediaBrowser Token={self._apikey}",
        }
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _replace_url(self, url: str) -> str:
        return url.replace("[HOST]", self._host or "") \
            .replace("[APIKEY]", self._apikey or "") \
            .replace("[USER]", self.user or "")

    def get_user(self, user_name: Optional[str] = None) -> Optional[str]:
        if not user_name or user_name in (self._username, self.user, self.name):
            return self.user
        return None

    def get_data(self, url: str):
        try:
            from app.utils.http import RequestUtils
            return RequestUtils(headers=self._headers()).get_res(url=self._replace_url(url))
        except Exception as e:
            logger.error(f"连接本机极影视出错：{e}")
            return None

    def post_data(self, url: str, data: Optional[str] = None, headers: dict = None):
        try:
            from app.utils.http import RequestUtils
            return RequestUtils(headers=self._headers(headers)).post_res(
                url=self._replace_url(url), data=data)
        except Exception as e:
            logger.error(f"连接本机极影视出错：{e}")
            return None


class WatchSync(_PluginBase):
    # 插件名称
    plugin_name = "Emby观看记录同步"
    # 插件描述
    plugin_desc = "在不同用户之间同步观看记录（自用插件，不保证兼容性）"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/DzAvril/MoviePilot-Plugins/main/icons/emby_watch_sync.png"
    # 插件版本
    plugin_version = "1.1"
    # 插件作者
    plugin_author = "DzAvril"
    # 作者主页
    author_url = "https://github.com/DzAvril"
    # 插件配置项ID前缀
    plugin_config_prefix = "watchsync_"
    # 加载顺序
    plugin_order = 20
    # 可使用的用户级别
    auth_level = 2

    def __init__(self):
        super().__init__()
        self._enabled = False
        self._sync_groups = []  # 改为同步组列表
        self._sync_movies = True
        self._sync_tv = True
        self._sync_favorite = True  # 是否同步收藏事件
        self._sync_played = True    # 是否同步播放完成事件
        self._min_watch_time = 300  # 最小观看时间（秒）
        self._emby_instances = {}
        self._zspace_instances = {}
        self._server_types = {}
        self._db_path = None
        self._zspace_poll_enabled = True
        self._zspace_poll_interval = 30
        self._zspace_poll_limit = 20
        self._zspace_poll_bootstrap_recent_minutes = 120
        self._zspace_poll_state = {}
        self._zspace_poll_lock = threading.RLock()
        self._scheduler = None
        # 事件去重相关
        self._event_timestamps = {}
        self._sync_metrics = {
            'total_events': 0,
            'successful_syncs': 0,
            'failed_syncs': 0,
            'duplicate_events': 0,
            'api_errors': defaultdict(int),
            'last_sync_time': None
        }
        # 并发控制
        self._sync_lock = threading.RLock()  # 可重入锁
        self._active_syncs = {}  # 跟踪正在进行的同步
        self._max_concurrent_syncs = 3  # 最大并发同步数
        self._loop_protector = SyncLoopProtector(ttl_seconds=30)  # 用于防止同步循环
        self._init_database()

    def init_plugin(self, config: dict = None):
        """
        生效配置信息
        """
        logger.info("开始初始化观看记录同步插件...")

        if config:
            self._enabled = config.get("enabled", False)
            self._sync_groups = config.get("sync_groups", [])
            self._sync_movies = config.get("sync_movies", True)
            self._sync_tv = config.get("sync_tv", True)
            self._sync_favorite = config.get("sync_favorite", True)
            self._sync_played = config.get("sync_played", True)
            self._min_watch_time = config.get("min_watch_time", 300)
            self._zspace_poll_enabled = config.get("zspace_poll_enabled", True)
            self._zspace_poll_interval = self._coerce_int(
                config.get("zspace_poll_interval", 30), 30, 10)
            self._zspace_poll_limit = self._coerce_int(
                config.get("zspace_poll_limit", 20), 20, 1)
            self._zspace_poll_bootstrap_recent_minutes = self._coerce_int(
                config.get("zspace_poll_bootstrap_recent_minutes", 120), 120, 0)
            logger.info(f"加载配置: enabled={self._enabled}, sync_groups={len(self._sync_groups)}, "
                        f"sync_favorite={self._sync_favorite}, sync_played={self._sync_played}, "
                        f"zspace_poll_enabled={self._zspace_poll_enabled}, "
                        f"zspace_poll_interval={self._zspace_poll_interval}")

        # 获取Emby服务器实例
        self._load_emby_instances()
        self._start_zspace_poll_scheduler()

        # 记录API端点信息（简化日志）
        api_endpoints = self.get_api()
        logger.info(f"注册了 {len(api_endpoints)} 个API端点")

        if self._enabled:
            logger.info("观看记录同步插件已启用")
        else:
            logger.info("观看记录同步插件已禁用")

    @staticmethod
    def _coerce_int(value, default: int, min_value: int) -> int:
        """
        将配置值转为整数，并应用下限。
        """
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = default
        return max(value, min_value)

    def _generate_event_fingerprint(self, event_data: WebhookEventInfo) -> str:
        """
        生成更可靠的事件指纹 - 修复版本
        """
        # 提取关键信息
        json_obj = event_data.json_object
        user_id = json_obj.get("User", {}).get("Id", "")
        item_id = json_obj.get("Item", {}).get("Id", "")
        session_id = json_obj.get("Session", {}).get("Id", "")

        # 对于观看进度，使用范围而不是精确值，避免微小差异导致重复处理
        position_ticks = (json_obj.get("Session", {}).get("PositionTicks", 0) or
                          json_obj.get("PlaybackInfo", {}).get("PositionTicks", 0))

        # 将位置四舍五入到最近的10秒（100,000,000 ticks = 10秒）
        position_rounded = (position_ticks // 100000000) * 100000000

        # 创建更精确的指纹，但允许位置的小幅变化
        fingerprint_data = (f"{event_data.channel}_{event_data.event}_"
                            f"{user_id}_{item_id}_{session_id}_{position_rounded}")

        # 使用SHA256生成指纹，避免hash冲突
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()
        logger.debug(f"生成事件指纹: {fingerprint_data} -> {fingerprint[:16]}...")
        return fingerprint

    def _is_duplicate_event(self, event_fingerprint: str, time_window_seconds: int = 30) -> bool:
        """
        检查是否为重复事件（基于时间窗口）- 修复版本
        缩短时间窗口，避免过度过滤正常事件
        """
        current_time = datetime.now()

        # 清理过期的事件记录
        cutoff_time = current_time - \
            timedelta(seconds=time_window_seconds * 2)  # 保留更长时间用于清理
        expired_events = [fp for fp, timestamp in self._event_timestamps.items()
                          if timestamp < cutoff_time]
        for fp in expired_events:
            del self._event_timestamps[fp]

        # 检查是否为重复事件
        if event_fingerprint in self._event_timestamps:
            last_time = self._event_timestamps[event_fingerprint]
            time_diff = current_time - last_time
            if time_diff < timedelta(seconds=time_window_seconds):
                logger.info(
                    f"🔄 检测到重复事件，跳过处理: {event_fingerprint[:16]}... (间隔: {time_diff.total_seconds():.1f}秒)")
                return True
            else:
                logger.debug(f"事件间隔足够长，允许处理: {time_diff.total_seconds():.1f}秒")

        # 记录新事件
        self._event_timestamps[event_fingerprint] = current_time
        logger.debug(f"记录新事件: {event_fingerprint[:16]}...")
        return False

    def _is_event_a_sync_loop(self, event_data: WebhookEventInfo) -> bool:
        """
        使用 SyncLoopProtector 检查事件是否由插件自身的同步操作触发。
        """
        try:
            json_obj = event_data.json_object
            user_name = json_obj.get("User", {}).get("Name")
            item_id = json_obj.get("Item", {}).get("Id")
            sync_type = self._get_sync_type_from_event(event_data)

            if not all([user_name, item_id, sync_type]):
                return False

            return self._loop_protector.is_protected(user_name, item_id, sync_type)

        except Exception as e:
            logger.error(f"检查循环事件出错: {e}")
            return False

    def _get_sync_type_from_event(self, event_data: WebhookEventInfo) -> Optional[str]:
        """ 从 webhook 事件中解析出对应的 sync_type """
        json_obj = event_data.json_object
        event_type = event_data.event
        sync_type = None

        if event_type in ["playback.pause", "playback.stop"]:
            sync_type = "playback"
        elif event_type in ["user.favorite", "item.favorite", "item.rate"]:
            is_favorite = json_obj.get("Item", {}).get(
                "UserData", {}).get("IsFavorite", False)
            sync_type = "favorite" if is_favorite else "not_favorite"
        elif event_type in ["item.markplayed", "playback.scrobble"]:
            sync_type = "mark_played"
        elif event_type == "item.markunplayed":
            sync_type = "mark_unplayed"

        return sync_type

    def _add_to_ignore_cache(self, user_name: str, item_id: str, sync_type: str):
        """
        将一个成功的同步操作添加到忽略缓存中。
        """
        if not all([user_name, item_id, sync_type]):
            return
        cache_key = (user_name, item_id, sync_type)
        self._sync_ignore_cache[cache_key] = datetime.now()
        logger.debug(f"添加到同步忽略缓存: {cache_key}")

        # 清理旧缓存
        cutoff = datetime.now() - timedelta(minutes=5)
        expired_keys = [
            k for k, v in self._sync_ignore_cache.items() if v < cutoff]
        for key in expired_keys:
            del self._sync_ignore_cache[key]

    def _update_sync_metrics(self, event_type: str, success: bool = True, error_type: str = None):
        """
        更新同步指标
        """
        if event_type == 'event_received':
            self._sync_metrics['total_events'] += 1
        elif event_type == 'sync_completed':
            if success:
                self._sync_metrics['successful_syncs'] += 1
                self._sync_metrics['last_sync_time'] = datetime.now()
            else:
                self._sync_metrics['failed_syncs'] += 1
        elif event_type == 'duplicate_event':
            self._sync_metrics['duplicate_events'] += 1
        elif event_type == 'api_error' and error_type:
            self._sync_metrics['api_errors'][error_type] += 1

    def _init_database(self):
        """
        初始化数据库
        """
        try:
            # 获取插件数据目录
            plugin_data_dir = os.path.join(
                settings.PLUGIN_DATA_PATH, "watchsync/data")
            if not os.path.exists(plugin_data_dir):
                os.makedirs(plugin_data_dir)

            self._db_path = os.path.join(plugin_data_dir, "watchsync.db")

            # 创建数据库表
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()

                # 同步记录表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sync_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        source_server TEXT NOT NULL,
                        source_user TEXT NOT NULL,
                        target_server TEXT NOT NULL,
                        target_user TEXT NOT NULL,
                        media_name TEXT NOT NULL,
                        media_type TEXT NOT NULL,
                        media_id TEXT,
                        position_ticks INTEGER,
                        sync_type TEXT DEFAULT 'playback',
                        status TEXT NOT NULL,
                        error_message TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # 检查并添加sync_type字段（为了兼容旧数据库）
                try:
                    cursor.execute(
                        "ALTER TABLE sync_records ADD COLUMN sync_type TEXT DEFAULT 'playback'")
                except sqlite3.OperationalError:
                    # 字段已存在，忽略错误
                    pass

                # 统计信息表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sync_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL UNIQUE,
                        total_syncs INTEGER DEFAULT 0,
                        success_syncs INTEGER DEFAULT 0,
                        failed_syncs INTEGER DEFAULT 0,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                conn.commit()
                logger.info(f"数据库初始化完成: {self._db_path}")

        except Exception as e:
            logger.error(f"数据库初始化失败: {str(e)}")
            self._db_path = None

    def get_state(self) -> bool:
        return self._enabled

    def get_dashboard_meta(self) -> Optional[List[Dict[str, str]]]:
        """获取插件仪表盘元信息"""
        return [{"key": "watchsync", "name": "观看记录同步"}]

    def get_dashboard(
        self, key: str = "", **kwargs
    ) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], Optional[List[dict]]]]:
        """
        获取插件仪表盘页面
        """
        return (
            {"cols": 12, "md": 6},
            {
                "refresh": 30,  # 30秒刷新间隔
                "border": True,
                "title": "观看记录同步",
                "subtitle": "在不同用户之间同步观看记录和收藏状态",
                "render_mode": "vue",  # 使用Vue渲染模式
            },
            None,
        )

    def _load_emby_instances(self):
        """
        从主程序获取Emby和极影视服务器实例
        """
        self._emby_instances = {}
        self._zspace_instances = {}
        self._server_types = {}

        try:
            from app.core.module import ModuleManager
            module_manager = ModuleManager()
            emby_module = module_manager._running_modules.get("EmbyModule")
            if emby_module and hasattr(emby_module, 'get_instances'):
                instances = emby_module.get_instances()
                if instances:
                    for name, instance in instances.items():
                        self._emby_instances[name] = instance
                        self._server_types[name] = "emby"
                    logger.info(f"通过ModuleManager加载了 {len(instances)} 个Emby服务器实例")
        except Exception as e:
            logger.warning(f"ModuleManager方式获取Emby失败: {str(e)}")

        try:
            from app.core.module import ModuleManager
            module_manager = ModuleManager()
            zspace_module = module_manager._running_modules.get("ZSpaceModule")
            if zspace_module and hasattr(zspace_module, 'get_instances'):
                instances = zspace_module.get_instances()
                if instances:
                    for name, instance in instances.items():
                        self._emby_instances[name] = instance
                        self._zspace_instances[name] = instance
                        self._server_types[name] = "zspace"
                    logger.info(f"通过ModuleManager加载了 {len(instances)} 个极影视服务器实例")
        except Exception as e:
            logger.warning(f"ModuleManager方式获取极影视失败: {str(e)}")

        local_zspace = self._load_local_zspace_instance()
        if local_zspace:
            name, instance = local_zspace
            if name not in self._emby_instances:
                self._emby_instances[name] = instance
                self._zspace_instances[name] = instance
                self._server_types[name] = "zspace"
                logger.info(f"自动发现本机极影视服务器实例: {name}")

        logger.info(
            f"媒体服务器加载完成: Emby={len([s for s, t in self._server_types.items() if t == 'emby'])}, "
            f"ZSpace={len(self._zspace_instances)}")

    def _load_local_zspace_instance(self) -> Optional[Tuple[str, LocalZSpaceInstance]]:
        """
        从极空间挂载的 /zvideo/zvideo.db 自动发现本机极影视 Emby 兼容层。
        """
        db_path = os.environ.get("WATCHSYNC_ZSPACE_DB", "/zvideo/zvideo.db")
        if not os.path.exists(db_path):
            return None

        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                media = conn.execute(
                    "SELECT media_uid, media_uname, user_name FROM zvideo_media LIMIT 1"
                ).fetchone()
                if not media:
                    return None
                token_row = conn.execute(
                    "SELECT token FROM zvideo_media_token WHERE media_uid=? "
                    "ORDER BY updated DESC LIMIT 1",
                    (media["media_uid"],)
                ).fetchone()
                if not token_row or not token_row["token"]:
                    return None
        except Exception as e:
            logger.debug(f"读取本机极影视数据库失败，跳过自动发现: {e}")
            return None

        hosts = [
            os.environ.get("WATCHSYNC_ZSPACE_HOST"),
            os.environ.get("ZSPACE_EMBY_HOST"),
            "http://127.0.0.1:8021/",
            "http://172.17.0.1:8021/",
        ]
        user_id = media["media_uid"]
        username = media["media_uname"] or media["user_name"] or user_id
        token = token_row["token"]

        for host in [h for h in hosts if h]:
            instance = LocalZSpaceInstance("极影视", host, token, user_id, username)
            response = instance.get_data("[HOST]emby/System/Info")
            if response and response.status_code == 200:
                server_info = response.json() or {}
                server_name = server_info.get("ServerName") or "极影视"
                return server_name, instance

        logger.warning("发现 /zvideo/zvideo.db，但未能连通本机极影视 8021 Emby 兼容层")
        return None

    def _start_zspace_poll_scheduler(self):
        """
        启动极影视源端进度轮询。
        """
        self._stop_zspace_poll_scheduler()
        if not self._enabled or not self._zspace_poll_enabled:
            return
        if not self._zspace_instances:
            return
        if not self._has_zspace_poll_source_users():
            logger.info("同步组未配置极影视源用户，极影视进度轮询不启动")
            return
        if BackgroundScheduler is None:
            logger.warning("apscheduler不可用，极影视进度轮询未启动")
            return

        try:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._scheduler.add_job(
                func=self.poll_zspace_watch_progress,
                trigger="interval",
                seconds=self._zspace_poll_interval,
                next_run_time=datetime.now() + timedelta(seconds=5),
                id="watchsync_zspace_progress_poll",
                name="极影视观看进度轮询",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            self._scheduler.start()
            logger.info(
                f"极影视进度轮询已启动: interval={self._zspace_poll_interval}s, "
                f"limit={self._zspace_poll_limit}")
        except Exception as e:
            logger.error(f"启动极影视进度轮询失败: {e}")
            self._scheduler = None

    def _stop_zspace_poll_scheduler(self):
        """
        停止极影视进度轮询。
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown(wait=False)
                self._scheduler = None
        except Exception as e:
            logger.error(f"停止极影视进度轮询失败: {e}")

    def poll_zspace_watch_progress(self):
        """
        轮询极影视继续观看列表，将新增或变化的进度同步到同组用户。
        """
        if not self._enabled or not self._zspace_poll_enabled:
            return
        if not self._zspace_poll_lock.acquire(blocking=False):
            logger.debug("极影视进度轮询仍在执行，跳过本轮")
            return
        try:
            for server_name, zspace_instance in list(self._zspace_instances.items()):
                self._poll_zspace_instance(server_name, zspace_instance)
        except Exception as e:
            logger.error(f"极影视进度轮询失败: {e}")
            logger.error(traceback.format_exc())
            self._update_sync_metrics('api_error', False, 'zspace_poll')
        finally:
            self._zspace_poll_lock.release()

    def _poll_zspace_instance(self, server_name: str, zspace_instance):
        """
        轮询单个极影视实例。
        """
        source_users = self._get_zspace_poll_source_users(server_name)
        if not source_users:
            logger.debug(f"极影视服务器 {server_name} 未配置为同步源，跳过轮询")
            return

        for source_user in source_users:
            user_id = zspace_instance.get_user(source_user) if hasattr(zspace_instance, "get_user") else None
            if not user_id:
                logger.warning(f"极影视用户不存在，跳过轮询: {server_name}:{source_user}")
                continue

            items = self._fetch_zspace_resume_items(zspace_instance, user_id)
            logger.debug(
                f"极影视轮询获取继续观看条目: {server_name}:{source_user} -> {len(items)}")
            for item in items:
                position_ticks = self._get_resume_position_ticks(item)
                if not self._should_sync_zspace_resume_item(
                        server_name, source_user, item, position_ticks):
                    continue
                if self._loop_protector.is_protected(
                        source_user, item.get("Id"), "playback"):
                    logger.info(
                        f"跳过插件自身写入触发的极影视轮询回弹: "
                        f"{server_name}:{source_user} -> {item.get('Name')}")
                    continue
                logger.info(
                    f"极影视轮询触发同步: {server_name}:{source_user} -> "
                    f"{item.get('Name')} ({position_ticks} ticks)")
                self._sync_to_group_users(server_name, source_user, item, position_ticks)

    def _get_zspace_poll_source_users(self, server_name: str) -> List[str]:
        """
        获取配置中属于该极影视实例的源用户。
        """
        users = []
        for group in self._sync_groups:
            if not group.get("enabled", True):
                continue
            for user in group.get("users", []):
                config_server = user.get("server")
                username = user.get("username")
                if not username:
                    continue
                actual_server = self._get_actual_server_name(config_server)
                if actual_server != server_name:
                    continue
                if self._get_server_type(actual_server) != "zspace":
                    continue
                if username not in users:
                    users.append(username)
        return users

    def _has_zspace_poll_source_users(self) -> bool:
        """
        判断同步组里是否存在需要作为源端轮询的极影视用户。
        """
        for server_name in self._zspace_instances.keys():
            if self._get_zspace_poll_source_users(server_name):
                return True
        return False

    def _fetch_zspace_resume_items(self, zspace_instance, user_id: str) -> List[dict]:
        """
        读取极影视继续观看列表。
        """
        url = (
            f"[HOST]emby/Users/{user_id}/Items/Resume?api_key=[APIKEY]"
            f"&Recursive=true&MediaTypes=Video&Limit={self._zspace_poll_limit}"
            f"&Fields=ProviderIds,Path,SeriesName,ParentIndexNumber,IndexNumber,"
            f"RunTimeTicks,UserData,DateCreated,ProductionYear"
        )
        response = zspace_instance.get_data(url)
        if not response or response.status_code != 200:
            logger.warning(
                f"极影视继续观看列表读取失败: {response.status_code if response else 'No response'}")
            return []
        payload = response.json()
        if isinstance(payload, dict):
            return payload.get("Items") or []
        if isinstance(payload, list):
            return payload
        return []

    def _should_sync_zspace_resume_item(
            self, server_name: str, source_user: str, item: dict, position_ticks: int) -> bool:
        """
        判断极影视继续观看条目是否需要同步。
        """
        item_id = item.get("Id")
        if not item_id:
            return False
        if not position_ticks or position_ticks < self._min_watch_time * 10000000:
            return False

        user_data = item.get("UserData") or {}
        last_played = self._parse_zspace_datetime(
            user_data.get("LastPlayedDate") or item.get("LastPlayedDate"))
        signature = self._zspace_resume_signature(item, position_ticks)
        state_key = f"{server_name}:{source_user}:{item_id}"
        previous_signature = self._zspace_poll_state.get(state_key)
        if previous_signature == signature:
            return False

        self._zspace_poll_state[state_key] = signature
        if previous_signature is None and not self._is_recent_zspace_resume(last_played):
            logger.debug(f"极影视轮询初始化旧进度快照，暂不同步: {item.get('Name')}")
            return False
        return True

    @staticmethod
    def _get_resume_position_ticks(item: dict) -> int:
        """
        从极影视继续观看条目提取播放进度。
        """
        user_data = item.get("UserData") or {}
        value = user_data.get("PlaybackPositionTicks") or item.get("PlaybackPositionTicks") or 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _zspace_resume_signature(item: dict, position_ticks: int) -> str:
        """
        生成极影视继续观看去重签名。
        """
        user_data = item.get("UserData") or {}
        last_played = user_data.get("LastPlayedDate") or item.get("LastPlayedDate") or ""
        played = user_data.get("Played")
        return f"{position_ticks}:{last_played}:{played}"

    @staticmethod
    def _parse_zspace_datetime(value: Optional[str]) -> Optional[datetime]:
        """
        解析极影视/Emby风格时间。
        """
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None

    def _is_recent_zspace_resume(self, last_played: Optional[datetime]) -> bool:
        """
        判断首次轮询时是否应同步该继续观看条目。
        """
        if self._zspace_poll_bootstrap_recent_minutes <= 0:
            return True
        if not last_played:
            return False
        cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=self._zspace_poll_bootstrap_recent_minutes)
        return last_played >= cutoff

    @eventmanager.register(EventType.WebhookMessage)
    def handle_webhook_message(self, event: Event):
        """
        处理Webhook消息 - 改进版本
        """
        logger.info("收到Webhook消息")
        self._update_sync_metrics('event_received')

        if not self._enabled:
            logger.info("插件未启用，跳过处理")
            return

        if not event or not event.event_data:
            logger.warning("Webhook事件数据为空")
            return

        # 检查是否为插件自身操作触发的循环事件
        if self._is_event_a_sync_loop(event.event_data):
            self._update_sync_metrics('duplicate_events')
            return

        # 生成事件指纹并检查重复
        event_fingerprint = self._generate_event_fingerprint(event.event_data)
        if self._is_duplicate_event(event_fingerprint):
            logger.debug(f"检测到重复事件，跳过处理: {event_fingerprint[:16]}...")
            self._update_sync_metrics('duplicate_event')
            return

        # 处理WebhookEventInfo对象
        try:
            event_data: WebhookEventInfo = event.event_data

            # 只处理Emby和极影视的播放、收藏事件
            if event_data.channel not in ["emby", "zspace"]:
                return

            # 支持的事件类型：播放事件、收藏事件和播放完成事件
            supported_events = [
                "playback.pause", "playback.stop",  # 播放事件
                "playback.scrobble",                # 播放完成事件
                "user.favorite", "item.favorite",   # 收藏事件（可能的事件名）
                "item.rate",                        # 评分/收藏事件（Emby客户端收藏触发）
                "library.new", "library.update",    # 库更新事件（可能包含收藏信息）
                "item.markplayed", "item.markunplayed"  # 标记播放完成/未完成事件
            ]

            if event_data.event not in supported_events:
                return

            # 提取基本信息用于日志
            json_obj = event_data.json_object
            user_name = json_obj.get("User", {}).get("Name", "Unknown")
            item_name = json_obj.get("Item", {}).get("Name", "Unknown")
            logger.info(f"处理同步事件: {user_name} - {item_name}")

            # 将WebhookEventInfo转换为字典格式
            webhook_data = {
                "channel": event_data.channel,
                "event": event_data.event,
                "server_name": event_data.server_name,
                "json_object": event_data.json_object
            }

            # 根据事件类型分发处理
            if event_data.event in ["playback.pause", "playback.stop"]:
                self._handle_playback_event(webhook_data)
            elif event_data.event in ["user.favorite", "item.favorite", "item.rate",
                                      "library.new", "library.update"]:
                self._handle_favorite_event(webhook_data)
            elif event_data.event in ["playback.scrobble", "item.markplayed",
                                      "item.markunplayed"]:
                self._handle_played_status_event(webhook_data)

        except Exception as e:
            logger.error(f"处理Webhook消息失败: {str(e)}")
            logger.error(traceback.format_exc())
            self._update_sync_metrics('api_error', False, 'webhook_processing')

    def _handle_favorite_event(self, webhook_data):
        """
        处理收藏事件
        """
        logger.info("开始处理收藏事件")

        # 检查是否启用收藏同步
        if not self._sync_favorite:
            logger.info("收藏同步已禁用，跳过处理")
            return

        # 从webhook数据中提取信息
        json_object = webhook_data.get("json_object", {})
        if not json_object:
            logger.warning("json_object为空，跳过处理")
            return

        # 提取关键信息
        server_name = webhook_data.get("server_name")
        if not server_name:
            server_info = json_object.get("Server", {})
            server_name = server_info.get("Name") or server_info.get("Id")

        if not server_name:
            server_name = self._default_server_for_channel(
                webhook_data.get("channel"))

        user_name = json_object.get("User", {}).get("Name")
        item_info = json_object.get("Item", {})

        # 检查是否为收藏操作 - 尝试多种方式获取收藏状态
        is_favorite = False

        # 方式1: 直接从json_object获取
        if "IsFavorite" in json_object:
            is_favorite = json_object.get("IsFavorite", False)
        # 方式2: 从Item的UserData获取
        elif item_info.get("UserData", {}).get("IsFavorite") is not None:
            is_favorite = item_info.get(
                "UserData", {}).get("IsFavorite", False)
        # 方式3: 对于item.rate事件，检查是否为收藏操作
        elif webhook_data.get("event") == "item.rate":
            # 对于评分事件，检查UserData中的IsFavorite状态
            user_data = item_info.get("UserData", {})
            is_favorite = user_data.get("IsFavorite", False)
            logger.info(f"item.rate事件 - UserData: {user_data}")
        # 方式4: 根据事件类型判断
        elif webhook_data.get("event") in ["user.favorite", "item.favorite"]:
            # 对于收藏事件，假设是添加收藏（可能需要根据实际webhook数据调整）
            is_favorite = True

        logger.info(f"收藏事件 - 服务器: {server_name}, 用户: {user_name}")
        logger.info(
            f"媒体: {item_info.get('Name', 'Unknown')}, 收藏状态: {is_favorite}")
        logger.info(f"事件类型: {webhook_data.get('event')}")
        logger.info(f"完整webhook数据: {json_object}")

        if not all([server_name, user_name, item_info]):
            logger.warning("收藏事件数据不完整，跳过处理")
            logger.warning(
                f"server_name: {server_name}, user_name: {user_name}, item_info: {bool(item_info)}")
            return

        # 检查媒体类型是否需要同步
        item_type = item_info.get("Type")
        if item_type == "Movie" and not self._sync_movies:
            return
        if item_type in ["Episode", "Series"] and not self._sync_tv:
            return

        # 查找需要同步的目标用户
        target_users = self._find_sync_targets(server_name, user_name)
        if not target_users:
            logger.info(f"未找到用户 {user_name} 的同步目标")
            return

        # 执行收藏同步
        self._sync_favorite_to_targets(
            source_server=server_name,
            source_user=user_name,
            item_info=item_info,
            is_favorite=is_favorite,
            target_users=target_users
        )

    def _handle_played_status_event(self, webhook_data):
        """
        处理播放完成状态事件
        """
        logger.info("开始处理播放完成状态事件")

        # 检查是否启用播放完成同步
        if not self._sync_played:
            logger.info("播放完成同步已禁用，跳过处理")
            return

        # 从webhook数据中提取信息
        json_object = webhook_data.get("json_object", {})
        if not json_object:
            logger.warning("json_object为空，跳过处理")
            return

        # 提取关键信息
        server_name = webhook_data.get("server_name")
        if not server_name:
            server_info = json_object.get("Server", {})
            server_name = server_info.get("Name") or server_info.get("Id")

        if not server_name:
            server_name = self._default_server_for_channel(
                webhook_data.get("channel"))

        user_name = json_object.get("User", {}).get("Name")
        item_info = json_object.get("Item", {})

        # 判断是标记为已播放还是未播放
        event_type = webhook_data.get("event")
        is_played = event_type in ["playback.scrobble", "item.markplayed"]

        logger.info(f"播放状态事件 - 服务器: {server_name}, 用户: {user_name}")
        logger.info(
            f"媒体: {item_info.get('Name', 'Unknown')}, 播放状态: {is_played}")

        if not all([server_name, user_name, item_info]):
            logger.warning("播放状态事件数据不完整，跳过处理")
            return

        # 检查媒体类型是否需要同步
        item_type = item_info.get("Type")
        if item_type == "Movie" and not self._sync_movies:
            return
        if item_type in ["Episode", "Series"] and not self._sync_tv:
            return

        # 查找需要同步的目标用户
        target_users = self._find_sync_targets(server_name, user_name)
        if not target_users:
            logger.info(f"未找到用户 {user_name} 的同步目标")
            return

        # 执行播放状态同步
        self._sync_played_status_to_targets(
            source_server=server_name,
            source_user=user_name,
            item_info=item_info,
            is_played=is_played,
            target_users=target_users
        )

    def _sync_played_status_to_targets(self, source_server, source_user, item_info,
                                       is_played, target_users):
        """
        将播放完成状态同步到目标用户
        """
        item_name = item_info.get("Name", "Unknown")

        logger.info(f"开始同步播放状态: {item_name} -> {is_played}")

        for target_server, target_user in target_users:
            try:
                # 获取目标服务器实例
                emby_instance = self._emby_instances.get(target_server)
                if not emby_instance:
                    logger.error(f"未找到服务器实例: {target_server}")
                    continue

                # 在目标服务器上查找对应的媒体项
                target_item = self._find_matching_item(
                    emby_instance, target_user, item_info
                )

                # 从返回的项目中获取ID
                if isinstance(target_item, dict):
                    target_item_id = target_item.get("Id")
                else:
                    target_item_id = target_item

                if not target_item_id:
                    logger.warning(f"在服务器 {target_server} 上未找到匹配的媒体项")
                    continue

                # 设置播放完成状态
                success = self._set_item_played_status(
                    emby_instance, target_user, target_item_id, is_played
                )

                if success:
                    # 添加到忽略缓存
                    sync_type = "mark_played" if is_played else "mark_unplayed"
                    self._loop_protector.add(
                        target_user, target_item_id, sync_type)

                # 记录同步结果
                sync_type = "mark_played" if is_played else "mark_unplayed"
                self._record_sync_result(
                    source_server=source_server,
                    source_user=source_user,
                    target_server=target_server,
                    target_user=target_user,
                    item_info=item_info,
                    position_ticks=0,
                    status="success" if success else "error",
                    error_message=None if success else "播放状态同步失败",
                    sync_type=sync_type
                )

                if success:
                    action = "标记为已播放" if is_played else "标记为未播放"
                    logger.info(
                        f"成功同步播放状态: {item_name} -> {target_user} ({action})")
                else:
                    logger.error(f"播放状态同步失败: {item_name} -> {target_user}")

            except Exception as e:
                logger.error(f"播放状态同步异常: {str(e)}")
                sync_type = "mark_played" if is_played else "mark_unplayed"
                self._record_sync_result(
                    source_server=source_server,
                    source_user=source_user,
                    target_server=target_server,
                    target_user=target_user,
                    item_info=item_info,
                    position_ticks=0,
                    status="error",
                    error_message=str(e),
                    sync_type=sync_type
                )

    def _set_item_played_status(self, emby_instance, user_name, item_id, is_played):
        """
        设置媒体项的播放完成状态
        """
        try:
            # 获取用户ID
            user_id = self._get_user_id(emby_instance, user_name)
            if not user_id:
                logger.error(f"未找到用户: {user_name}")
                return False

            # 构建API URL
            if is_played:
                url = f"[HOST]emby/Users/{user_id}/PlayedItems/{item_id}?api_key=[APIKEY]"
                response = emby_instance.post_data(url)
            else:
                # 对于取消播放状态，需要使用DELETE请求
                url = f"[HOST]emby/Users/{user_id}/PlayedItems/{item_id}?api_key=[APIKEY]"
                response = self._delete_media_server_data(emby_instance, url)

            return response and response.status_code in [200, 204]

        except Exception as e:
            logger.error(f"设置播放状态失败: {str(e)}")
            return False

    def _find_sync_targets(self, source_server: str, source_user: str) -> List[Tuple[str, str]]:
        """
        查找需要同步的目标用户
        返回格式: [(target_server, target_user), ...]
        """
        target_users = []

        logger.info(f"查找同步目标 - 源用户: {source_server}:{source_user}")
        logger.info(f"当前配置的同步组数量: {len(self._sync_groups)}")

        # 查找包含源用户的同步组
        for i, group in enumerate(self._sync_groups):
            group_name = group.get("name", f"组{i+1}")
            logger.debug(
                f"检查同步组 '{group_name}' - 启用状态: {group.get('enabled', True)}")

            if not group.get("enabled", True):
                logger.debug(f"同步组 '{group_name}' 已禁用，跳过")
                continue

            # 检查源用户是否在这个同步组中
            source_user_found = False
            group_users = group.get("users", [])

            for user in group_users:
                user_server = user.get("server")
                user_name = user.get("username")

                # 检查服务器名匹配
                server_match = self._is_server_match(
                    user_server, source_server)

                if server_match and user_name == source_user:
                    source_user_found = True
                    logger.debug(f"在同步组 '{group_name}' 中找到源用户")
                    break

            if not source_user_found:
                logger.debug(f"源用户不在同步组 '{group_name}' 中")
                continue

            # 添加组内其他所有用户作为同步目标
            for target_user in group.get("users", []):
                target_server = target_user.get("server")
                target_username = target_user.get("username")

                # 跳过源用户自己
                server_match = self._is_server_match(
                    target_server, source_server)
                if server_match and target_username == source_user:
                    continue

                # 获取实际的目标服务器名称
                actual_target_server = self._get_actual_server_name(
                    target_server)
                if not actual_target_server:
                    logger.warning(f"无法找到目标服务器的实际名称: {target_server}")
                    continue

                target_users.append((actual_target_server, target_username))
                logger.debug(
                    f"添加同步目标: {actual_target_server}:{target_username}")

        logger.info(f"找到 {len(target_users)} 个同步目标用户")
        return target_users

    def _sync_favorite_to_targets(self, source_server, source_user, item_info,
                                  is_favorite, target_users):
        """
        将收藏状态同步到目标用户
        """
        item_name = item_info.get("Name", "Unknown")
        item_id = item_info.get("Id")

        logger.info(f"开始同步收藏状态: {item_name} -> {is_favorite}")

        for target_server, target_user in target_users:
            try:
                # 获取目标服务器实例
                emby_instance = self._emby_instances.get(target_server)
                if not emby_instance:
                    logger.error(f"未找到服务器实例: {target_server}")
                    continue

                # 在目标服务器上查找对应的媒体项
                target_item = self._find_matching_item(
                    emby_instance, target_user, item_info
                )

                # 从返回的项目中获取ID
                if isinstance(target_item, dict):
                    target_item_id = target_item.get("Id")
                else:
                    target_item_id = target_item

                if not target_item_id:
                    logger.warning(f"在服务器 {target_server} 上未找到匹配的媒体项")
                    continue

                # 设置收藏状态
                success = self._set_item_favorite(
                    emby_instance, target_user, target_item_id, is_favorite
                )

                if success:
                    # 添加到忽略缓存
                    sync_type = "favorite" if is_favorite else "not_favorite"
                    self._loop_protector.add(
                        target_user, target_item_id, sync_type)

                # 记录同步结果 - 区分收藏和取消收藏
                sync_type = "favorite" if is_favorite else "not_favorite"
                self._record_sync_result(
                    source_server=source_server,
                    source_user=source_user,
                    target_server=target_server,
                    target_user=target_user,
                    item_info=item_info,
                    position_ticks=0,
                    status="success" if success else "error",
                    error_message=None if success else "收藏同步失败",
                    sync_type=sync_type
                )

                if success:
                    action = "收藏" if is_favorite else "取消收藏"
                    logger.info(f"成功同步{action}: {item_name} -> {target_user}")
                else:
                    logger.error(f"收藏同步失败: {item_name} -> {target_user}")

            except Exception as e:
                logger.error(f"收藏同步异常: {str(e)}")
                # 在异常情况下也区分收藏和取消收藏
                sync_type = "favorite" if is_favorite else "not_favorite"
                self._record_sync_result(
                    source_server=source_server,
                    source_user=source_user,
                    target_server=target_server,
                    target_user=target_user,
                    item_info=item_info,
                    position_ticks=0,
                    status="error",
                    error_message=str(e),
                    sync_type=sync_type
                )

    def _set_item_favorite(self, emby_instance, user_name, item_id, is_favorite):
        """
        设置媒体项的收藏状态
        """
        try:
            # 获取用户ID
            user_id = self._get_user_id(emby_instance, user_name)
            if not user_id:
                logger.error(f"未找到用户: {user_name}")
                return False

            logger.info(
                f"设置收藏状态: user_id={user_id}, item_id={item_id}, is_favorite={is_favorite}")

            # 构建API URL - 使用正确的Emby API格式
            if is_favorite:
                url = f"[HOST]emby/Users/{user_id}/FavoriteItems/{item_id}?api_key=[APIKEY]"
                response = emby_instance.post_data(url, data="")
            else:
                # 对于取消收藏，需要使用DELETE请求
                url = f"[HOST]emby/Users/{user_id}/FavoriteItems/{item_id}?api_key=[APIKEY]"
                response = self._delete_media_server_data(emby_instance, url)

            if response:
                logger.info(f"收藏API响应状态: {response.status_code}")
                if response.status_code in [200, 204]:
                    logger.info(f"成功设置收藏状态: {is_favorite}")
                    return True
                else:
                    logger.error(
                        f"收藏API调用失败: {response.status_code}, {response.text}")
                    return False
            else:
                logger.error("收藏API调用无响应")
                return False

        except Exception as e:
            logger.error(f"设置收藏状态失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _get_user_id(self, emby_instance, user_name):
        """
        获取用户ID
        """
        try:
            if self._is_zspace_instance(emby_instance) and hasattr(emby_instance, "get_user"):
                return emby_instance.get_user(user_name)

            url = f"[HOST]emby/Users?api_key=[APIKEY]"
            response = emby_instance.get_data(url)

            if response and response.status_code == 200:
                users = response.json()
                for user in users:
                    if user.get("Name") == user_name:
                        return user.get("Id")

            return None
        except Exception as e:
            logger.error(f"获取用户ID失败: {str(e)}")
            return None

    def _delete_media_server_data(self, media_server, url: str):
        """
        发送DELETE请求。极影视兼容层需要 X-Emby-Token，不能只依赖 query api_key。
        """
        actual_url = url.replace("[HOST]", getattr(media_server, "_host", "") or "") \
            .replace("[APIKEY]", getattr(media_server, "_apikey", "") or "") \
            .replace("[USER]", getattr(media_server, "user", "") or "")
        headers = None
        if self._is_zspace_instance(media_server):
            token = getattr(media_server, "_apikey", "") or ""
            headers = {
                "X-Emby-Token": token,
                "X-Emby-Authorization": f"MediaBrowser Token={token}",
            }
        from app.utils.http import RequestUtils
        return RequestUtils(headers=headers).delete_res(actual_url)

    def _cleanup_expired_syncs(self):
        """
        清理过期的同步记录
        """
        current_time = datetime.now()
        expired_threshold = timedelta(minutes=10)  # 10分钟超时

        with self._sync_lock:
            expired_keys = [
                key for key, start_time in self._active_syncs.items()
                if current_time - start_time > expired_threshold
            ]

            for key in expired_keys:
                logger.warning(f"清理过期同步: {key}")
                del self._active_syncs[key]

    def get_sync_status(self) -> dict:
        """
        获取同步状态信息
        """
        with self._sync_lock:
            return {
                "metrics": dict(self._sync_metrics),
                "active_syncs": len(self._active_syncs),
                "max_concurrent": self._max_concurrent_syncs,
                "event_cache_size": len(self._event_timestamps),
                "emby_servers": len(self._emby_instances),
                "zspace_servers": len(self._zspace_instances),
                "sync_groups": len([g for g in self._sync_groups if g.get("enabled", True)]),
                "zspace_poll_enabled": self._zspace_poll_enabled,
                "zspace_poll_interval": self._zspace_poll_interval,
                "zspace_poll_source_users": {
                    server_name: self._get_zspace_poll_source_users(server_name)
                    for server_name in self._zspace_instances.keys()
                }
            }

    def _handle_playback_event(self, webhook_data):
        """
        处理播放事件
        """
        logger.info("开始处理播放事件")
        logger.debug(f"Webhook数据: {webhook_data}")

        # 从webhook数据中提取信息
        json_object = webhook_data.get("json_object", {})
        if not json_object:
            logger.warning("json_object为空，跳过处理")
            return

        # 提取关键信息
        # 尝试多种方式获取服务器名称
        server_name = webhook_data.get("server_name")
        if not server_name:
            # 从Server字段获取服务器名称
            server_info = json_object.get("Server", {})
            server_name = server_info.get("Name") or server_info.get("Id")

        # 如果还是没有服务器名称，尝试使用第一个可用的服务器
        if not server_name:
            server_name = self._default_server_for_channel(
                webhook_data.get("channel"))
            logger.info(f"未找到服务器名称，按channel选择可用服务器: {server_name}")

        user_name = json_object.get("User", {}).get("Name")
        item_info = json_object.get("Item", {})
        session_info = json_object.get("Session", {})

        # 尝试从PlaybackInfo获取观看进度信息
        playback_info = json_object.get("PlaybackInfo", {})
        if not session_info.get("PositionTicks") and playback_info.get("PositionTicks"):
            session_info["PositionTicks"] = playback_info.get("PositionTicks")

        logger.info(f"提取的信息 - 服务器: {server_name}, 用户: {user_name}")
        logger.info(
            f"媒体信息: {item_info.get('Name', 'Unknown')} ({item_info.get('Type', 'Unknown')})")
        logger.info(f"观看进度: {session_info.get('PositionTicks', 0)} ticks")

        if not all([server_name, user_name, item_info]):
            logger.warning("Webhook数据不完整，跳过处理")
            logger.warning(
                f"server_name: {server_name}, user_name: {user_name}, item_info: {bool(item_info)}")
            return

        # 检查媒体类型是否需要同步
        item_type = item_info.get("Type")
        if item_type == "Movie" and not self._sync_movies:
            return
        if item_type in ["Episode", "Series"] and not self._sync_tv:
            return

        # 检查观看时长 - 尝试多个数据源
        play_duration_ticks = session_info.get("PlayDurationTicks", 0)
        if not play_duration_ticks:
            # 尝试从PlaybackInfo获取
            playback_info = json_object.get("PlaybackInfo", {})
            play_duration_ticks = playback_info.get("PlayDurationTicks", 0)

        # 如果还是没有，尝试从Item的RunTimeTicks计算
        if not play_duration_ticks:
            item_runtime = item_info.get("RunTimeTicks", 0)
            position_ticks = session_info.get(
                "PositionTicks", 0) or playback_info.get("PositionTicks", 0)
            if item_runtime and position_ticks:
                # 假设播放时长等于观看进度（对于暂停/停止事件）
                play_duration_ticks = position_ticks

        play_duration = play_duration_ticks / 10000000  # 转换为秒
        logger.info(
            f"计算的观看时长: {play_duration}s (来源: {play_duration_ticks} ticks)")

        if play_duration < self._min_watch_time:
            logger.info(
                f"观看时长 {play_duration}s 小于最小时长 {self._min_watch_time}s，跳过同步")
            return

        # 获取观看进度
        position_ticks = session_info.get("PositionTicks", 0)
        if not position_ticks:
            position_ticks = playback_info.get("PositionTicks", 0)

        logger.info(
            f"观看进度: {position_ticks} ticks ({position_ticks / 10000000:.1f}s)")

        logger.info(
            f"开始同步观看记录: 服务器={server_name}, 用户={user_name}, 媒体={item_info.get('Name')}")

        # 查找需要同步的同步组
        self._sync_to_group_users(
            server_name, user_name, item_info, position_ticks)

    def _sync_to_group_users(self, source_server: str, source_user: str, item_info: dict, position_ticks: int):
        """
        同步到同步组内的其他用户
        """
        logger.info(f"开始查找同步组 - 源用户: {source_server}:{source_user}")
        logger.info(f"当前配置的同步组数量: {len(self._sync_groups)}")
        logger.info(f"可用的媒体服务器实例: {list(self._emby_instances.keys())}")

        synced_count = 0

        # 查找包含源用户的同步组
        for i, group in enumerate(self._sync_groups):
            group_name = group.get("name", f"组{i+1}")
            logger.info(
                f"检查同步组 '{group_name}' - 启用状态: {group.get('enabled', True)}")

            if not group.get("enabled", True):
                logger.info(f"同步组 '{group_name}' 已禁用，跳过")
                continue

            # 检查源用户是否在这个同步组中
            source_user_found = False
            group_users = group.get("users", [])
            logger.info(f"同步组 '{group_name}' 包含 {len(group_users)} 个用户")

            for user in group_users:
                user_server = user.get("server")
                user_name = user.get("username")
                logger.info(f"检查用户: {user_server}:{user_name}")

                # 改进服务器名匹配逻辑
                server_match = self._is_server_match(
                    user_server, source_server)
                logger.info(
                    f"服务器匹配结果: {user_server} vs {source_server} = {server_match}")

                if server_match and user_name == source_user:
                    source_user_found = True
                    logger.info(f"在同步组 '{group_name}' 中找到源用户")
                    break

            if not source_user_found:
                logger.info(f"源用户不在同步组 '{group_name}' 中")
                continue

            # 同步到组内其他所有用户
            logger.info(f"开始向同步组 '{group_name}' 内的其他用户同步")

            for target_user in group.get("users", []):
                target_server = target_user.get("server")
                target_username = target_user.get("username")

                # 跳过源用户自己
                server_match = self._is_server_match(
                    target_server, source_server)
                if server_match and target_username == source_user:
                    logger.info(f"跳过源用户自己: {target_server}:{target_username}")
                    continue

                # 获取实际的目标服务器名称（用于API调用）
                actual_target_server = self._get_actual_server_name(
                    target_server)
                if not actual_target_server:
                    logger.warning(f"无法找到目标服务器的实际名称: {target_server}")
                    logger.warning(
                        f"可用的服务器实例: {list(self._emby_instances.keys())}")
                    continue

                logger.info(
                    f"准备同步到用户: {target_server}:{target_username} (实际服务器: {actual_target_server})")
                logger.info(
                    f"目标服务器实例是否存在: {actual_target_server in self._emby_instances}")

                if self._sync_watch_progress_with_retry(source_server, source_user, actual_target_server, target_username, item_info, position_ticks):
                    synced_count += 1
                    logger.info(
                        f"同步到组内用户成功: {target_server}:{target_username}")
                    self._update_sync_metrics('sync_completed', True)
                else:
                    logger.warning(
                        f"同步到组内用户失败: {target_server}:{target_username}")
                    self._update_sync_metrics('sync_completed', False)

        if synced_count > 0:
            logger.info(f"成功同步到 {synced_count} 个组内用户")
        else:
            logger.info("未找到匹配的同步组或同步失败")

    def _is_server_match(self, config_server: str, actual_server: str) -> bool:
        """
        检查配置中的服务器名是否与实际服务器名匹配 - 改进版本
        支持多种匹配方式：
        1. 精确匹配（最高优先级）
        2. 配置中使用"Emby"/"ZSpace"作为通用名称时，仅匹配对应类型服务器
        3. 严格的部分匹配（避免误匹配）
        """
        if not config_server or not actual_server:
            return False

        # 精确匹配（最高优先级）
        if config_server == actual_server:
            logger.debug(f"服务器精确匹配: {config_server}")
            return True

        config_lower = config_server.lower()
        actual_lower = actual_server.lower()
        actual_type = self._get_server_type(actual_server)

        # 如果配置中使用"Emby"作为通用名称，只匹配Emby服务器实例
        if config_lower == "emby":
            if actual_type == "emby":
                matched = True
            elif actual_type == "zspace":
                matched = False
            else:
                matched = self._has_server_type("emby") and not self._looks_like_zspace_server_name(actual_server)
            logger.debug(f"Emby服务器通用匹配: {config_server} -> {actual_server} = {matched}")
            return matched

        # 如果配置中使用极影视通用名称，只匹配ZSpace服务器实例
        if config_lower in ["zspace", "zvideo", "jiyingshi", "极影视"]:
            matched = actual_type == "zspace" or self._looks_like_zspace_server_name(actual_server)
            logger.debug(f"极影视服务器通用匹配: {config_server} -> {actual_server} = {matched}")
            return matched

        # 改进的部分匹配逻辑 - 更严格的匹配条件
        # 只有当配置的服务器名是实际服务器名的子串，且长度足够时才匹配
        # 避免短名称误匹配（如"a"匹配"abc"）
        min_match_length = 3
        if (len(config_server) >= min_match_length and
            config_lower in actual_lower and
                len(config_server) / len(actual_server) > 0.3):  # 至少30%的长度匹配
            logger.debug(f"服务器部分匹配: {config_server} -> {actual_server}")
            return True

        # 反向匹配 - 实际服务器名是配置名的子串
        if (len(actual_server) >= min_match_length and
            actual_lower in config_lower and
                len(actual_server) / len(config_server) > 0.3):
            logger.debug(f"服务器反向匹配: {config_server} -> {actual_server}")
            return True

        logger.debug(f"服务器不匹配: {config_server} vs {actual_server}")
        return False

    def _get_server_type(self, server_name: str) -> str:
        """
        获取服务器类型，返回 emby / zspace / unknown。
        """
        if not server_name:
            return "unknown"
        if server_name in self._server_types:
            return self._server_types[server_name]
        if server_name in self._zspace_instances:
            return "zspace"
        instance = self._emby_instances.get(server_name)
        if self._is_zspace_instance(instance):
            return "zspace"
        if instance:
            return "emby"
        return "unknown"

    def _has_server_type(self, server_type: str) -> bool:
        """
        判断当前实例列表中是否存在指定类型的服务器。
        """
        return any(
            self._get_server_type(server_name) == server_type
            for server_name in self._emby_instances.keys()
        )

    def _looks_like_zspace_server_name(self, server_name: str) -> bool:
        """
        识别没有登记到实例表里的极影视/ZSpace服务器名。
        """
        if not server_name:
            return False
        if server_name in self._zspace_instances:
            return True
        server_lower = server_name.lower()
        return any(alias in server_lower for alias in [
            "zspace",
            "zvideo",
            "jiyingshi",
            "ji-ying-shi",
            "qizhi",
            "极影视",
            "极空间",
        ])

    def _default_server_for_channel(self, channel: str) -> Optional[str]:
        """
        根据Webhook channel选择默认服务器。
        """
        expected_type = "zspace" if channel == "zspace" else "emby"
        for server_name in self._emby_instances.keys():
            if self._get_server_type(server_name) == expected_type:
                return server_name
        for server_name in self._emby_instances.keys():
            return server_name
        return None

    def _is_zspace_instance(self, instance) -> bool:
        """
        判断实例是否为极影视兼容层。
        """
        if not instance:
            return False
        if getattr(instance, "_is_watchsync_zspace", False):
            return True
        class_name = instance.__class__.__name__.lower()
        module_name = instance.__class__.__module__.lower()
        return "zspace" in class_name or "zspace" in module_name

    def _get_actual_server_name(self, config_server: str) -> Optional[str]:
        """
        根据配置中的服务器名获取实际的服务器名称
        """
        if not config_server:
            return None

        # 如果配置的服务器名直接存在于实例中，直接返回
        if config_server in self._emby_instances:
            return config_server

        config_lower = config_server.lower()

        # 如果配置中使用"Emby"作为通用名称，返回第一个Emby服务器
        if config_lower == "emby":
            for server_name in self._emby_instances.keys():
                if self._get_server_type(server_name) == "emby":
                    return server_name
            return None

        # 如果配置中使用极影视通用名称，返回第一个ZSpace服务器
        if config_lower in ["zspace", "zvideo", "jiyingshi", "极影视"]:
            for server_name in self._zspace_instances.keys():
                return server_name
            return None

        # 尝试部分匹配
        for server_name in self._emby_instances.keys():
            if config_server.lower() in server_name.lower() or server_name.lower() in config_server.lower():
                return server_name

        return None

    @retry_on_failure(max_retries=3, base_delay=2, max_delay=30)
    def _sync_watch_progress_with_retry(self, source_server: str, source_user: str,
                                        target_server: str, target_user: str,
                                        item_info: dict, position_ticks: int) -> bool:
        """
        带重试机制和并发控制的观看进度同步
        """
        sync_key = f"{target_server}:{target_user}:{item_info.get('Id', '')}"

        with self._sync_lock:
            # 检查是否已有相同的同步在进行
            if sync_key in self._active_syncs:
                logger.debug(f"同步已在进行中，跳过: {sync_key}")
                return False

            # 检查并发同步数量限制
            if len(self._active_syncs) >= self._max_concurrent_syncs:
                logger.warning(
                    f"达到最大并发同步数限制 ({self._max_concurrent_syncs})，跳过同步")
                return False

            # 标记同步开始
            self._active_syncs[sync_key] = datetime.now()

        try:
            return self._sync_watch_progress(source_server, source_user, target_server,
                                             target_user, item_info, position_ticks)
        finally:
            # 清理同步标记
            with self._sync_lock:
                self._active_syncs.pop(sync_key, None)

    def _sync_watch_progress(self, source_server: str, source_user: str, target_server: str, target_user: str,
                             item_info: dict, position_ticks: int) -> bool:
        """
        同步观看进度到目标用户
        """
        try:
            # 获取目标服务器实例
            target_emby = self._emby_instances.get(target_server)
            if not target_emby:
                logger.error(f"未找到目标服务器实例: {target_server}")
                return False

            # 健康检查
            if not self._health_check_emby_connection(target_server, target_emby):
                logger.error(f"目标服务器 {target_server} 健康检查失败")
                return False

            # 在目标服务器查找对应媒体
            target_item = self._find_matching_item(
                target_emby, target_user, item_info)
            if not target_item:
                logger.warning(f"在目标服务器 {target_server} 中未找到匹配的媒体")
                return False

            # 检查目标媒体项目的数据结构
            logger.debug(f"找到的目标媒体项目类型: {type(target_item)}")
            if isinstance(target_item, dict):
                logger.debug(f"目标媒体项目字典键: {list(target_item.keys())}")
                logger.debug(f"目标媒体项目内容: {target_item}")
            else:
                logger.debug(f"目标媒体项目属性: {dir(target_item)}")
                logger.debug(f"目标媒体项目内容: {target_item}")

            # 获取媒体ID，支持不同的数据结构
            target_item_id = None
            if isinstance(target_item, dict):
                # 尝试多种可能的ID字段名
                target_item_id = (target_item.get("Id") or
                                  target_item.get("id") or
                                  target_item.get("item_id") or
                                  target_item.get("ItemId"))
                logger.info(
                    f"从字典获取ID: Id={target_item.get('Id')}, id={target_item.get('id')}, item_id={target_item.get('item_id')}, ItemId={target_item.get('ItemId')}")
            elif hasattr(target_item, 'Id'):
                target_item_id = target_item.Id
                logger.info(f"从对象属性获取ID: {target_item_id}")
            elif hasattr(target_item, 'id'):
                target_item_id = target_item.id
                logger.info(f"从对象属性获取id: {target_item_id}")
            elif hasattr(target_item, 'item_id'):
                target_item_id = target_item.item_id
                logger.info(f"从对象属性获取item_id: {target_item_id}")

            if not target_item_id:
                logger.error(f"无法获取目标媒体的ID")
                logger.error(f"数据结构: {type(target_item)}")
                if isinstance(target_item, dict):
                    logger.error(f"字典键: {list(target_item.keys())}")
                    logger.error(f"字典内容: {target_item}")
                else:
                    logger.error(
                        f"对象属性: {[attr for attr in dir(target_item) if not attr.startswith('_')]}")
                return False

            logger.info(f"目标媒体ID: {target_item_id}")

            # 更新目标用户的观看进度
            success = self._update_user_progress(
                target_emby, target_user, target_item_id, position_ticks)

            if success:
                # 添加到忽略缓存
                self._loop_protector.add(
                    target_user, target_item_id, "playback")

            # 记录同步结果
            self._record_sync_result(
                source_server=source_server,
                source_user=source_user,
                target_server=target_server,
                target_user=target_user,
                item_info=item_info,
                position_ticks=position_ticks,
                status="success" if success else "error",
                error_message=None if success else "更新观看进度失败",
                sync_type="playback"
            )

            if success:
                logger.info(
                    f"同步成功: {target_server}:{target_user} - {item_info.get('Name')}")
                return True
            else:
                logger.error(f"更新观看进度失败: {target_server}:{target_user}")
                return False

        except Exception as e:
            logger.error(f"同步观看进度失败: {str(e)}")
            return False

    def _find_matching_item(self, emby_instance, target_user, source_item: dict) -> Optional[dict]:
        """
        在目标服务器中查找匹配的媒体项目
        """
        try:
            if self._is_zspace_instance(emby_instance):
                return self._find_matching_zspace_item(
                    emby_instance, target_user, source_item)

            media_name = source_item.get("Name", "Unknown")
            media_type = source_item.get("Type", "Unknown")
            logger.info(f"开始查找匹配媒体: {media_name} ({media_type})")

            # 优先使用TMDB ID匹配
            provider_ids = source_item.get("ProviderIds", {})
            tmdb_id = provider_ids.get("Tmdb")
            imdb_id = provider_ids.get("Imdb")

            logger.info(f"媒体标识符: TMDB={tmdb_id}, IMDB={imdb_id}")

            if tmdb_id:
                logger.info(f"尝试使用TMDB ID匹配: {tmdb_id}")
                # 使用TMDB ID搜索
                if source_item.get("Type") == "Movie":
                    results = emby_instance.get_movies(
                        title="", tmdb_id=int(tmdb_id))
                    logger.info(
                        f"电影TMDB搜索结果数量: {len(results) if results else 0}")
                else:
                    # 对于电视剧，需要特殊处理
                    results = self._search_tv_by_tmdb(emby_instance, tmdb_id)
                    logger.info(
                        f"电视剧TMDB搜索结果数量: {len(results) if results else 0}")

                if results:
                    result_item = results[0].__dict__ if hasattr(
                        results[0], '__dict__') else results[0]
                    logger.info(
                        f"TMDB匹配成功: {result_item.get('Name', 'Unknown')}")
                    return result_item
                else:
                    logger.info("TMDB匹配失败，继续尝试其他方式")

            # 如果TMDB ID匹配失败，尝试IMDB ID
            if imdb_id:
                logger.info(f"尝试使用IMDB ID匹配: {imdb_id}")
                # 这里可以添加IMDB ID搜索逻辑
                pass

            # 最后尝试名称/剧名匹配
            search_terms = self._get_media_search_terms(source_item)
            year = source_item.get("ProductionYear")
            logger.info(f"尝试名称匹配: {search_terms} ({year})")

            if search_terms:
                try:
                    user_id = emby_instance.get_user(target_user)
                    if not user_id:
                        logger.error(f"未找到用户: {target_user}")
                        return False

                    include_types = "Movie" if source_item.get("Type") == "Movie" else "Series,Episode"
                    for term in search_terms:
                        logger.info(f"通过名称搜索媒体: {term} ({year})")
                        search_url = (
                            f"[HOST]emby/Users/{user_id}/Items?api_key=[APIKEY]"
                            f"&Recursive=true&IncludeItemTypes={include_types}"
                            f"&SearchTerm={quote(str(term))}&Limit=50"
                            f"&Fields=ProviderIds,SeriesName,ParentIndexNumber,IndexNumber,"
                            f"Path,UserData,ProductionYear,RunTimeTicks"
                        )
                        if year and source_item.get("Type") == "Movie":
                            search_url += f"&Years={year}"

                        response = emby_instance.get_data(search_url)
                        if response and response.status_code == 200:
                            items = response.json().get("Items", [])
                            logger.info(f"名称搜索 '{term}' 返回 {len(items)} 个媒体项目")
                            best_item = self._pick_best_matching_item(source_item, items)
                            if best_item:
                                logger.info(
                                    f"媒体名称匹配成功: {best_item.get('Name', 'Unknown')}")
                                return best_item
                        else:
                            logger.warning(
                                f"媒体名称搜索API调用失败: {response.status_code if response else 'No response'}")
                    logger.info("未找到名称匹配的媒体")
                    return None

                except Exception as e:
                    logger.error(f"通过名称搜索电视剧失败: {str(e)}")
                    return None

            logger.warning(f"所有匹配方式都失败，未找到匹配的媒体: {media_name}")
            return None

        except Exception as e:
            logger.error(f"查找匹配媒体失败: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def _get_media_search_terms(self, source_item: dict) -> List[str]:
        """
        生成媒体搜索词。剧集来源可能只有本地单集标题，需补充剧名。
        """
        terms = []
        if source_item.get("Type") == "Movie":
            candidates = [
                source_item.get("Name"),
                source_item.get("OriginalTitle"),
            ]
        else:
            series_name = source_item.get("SeriesName")
            candidates = [
                source_item.get("Name"),
                series_name,
                self._normalize_series_name(series_name),
                source_item.get("OriginalTitle"),
            ]
        for term in candidates:
            if term and term not in terms:
                terms.append(term)
        return terms

    def _find_matching_zspace_item(self, zspace_instance, target_user, source_item: dict) -> Optional[dict]:
        """
        在极影视兼容层中查找匹配媒体。
        """
        try:
            media_name = source_item.get("Name", "Unknown")
            media_type = source_item.get("Type", "Unknown")
            user_id = zspace_instance.get_user(target_user)
            if not user_id:
                logger.error(f"未找到极影视用户: {target_user}")
                return None

            # 如果来源已经是极影视ID，先尝试直接读取。
            source_item_id = source_item.get("Id")
            if source_item_id and str(source_item_id).startswith("video_"):
                direct_url = f"[HOST]emby/Users/{user_id}/Items/{source_item_id}?api_key=[APIKEY]"
                direct_response = zspace_instance.get_data(direct_url)
                if direct_response and direct_response.status_code == 200:
                    return direct_response.json()

            include_types = "Movie" if media_type == "Movie" else "Episode"
            search_terms = []
            for term in [
                source_item.get("SeriesName"),
                source_item.get("Name"),
                source_item.get("OriginalTitle"),
            ]:
                if term and term not in search_terms:
                    search_terms.append(term)

            for term in search_terms:
                search_url = (
                    f"[HOST]emby/Users/{user_id}/Items?api_key=[APIKEY]"
                    f"&Recursive=true&IncludeItemTypes={include_types}"
                    f"&SearchTerm={quote(str(term))}&Limit=30"
                    f"&Fields=ProviderIds,OriginalTitle,ProductionYear,Path,UserData,"
                    f"SeriesName,ParentIndexNumber,IndexNumber,RunTimeTicks"
                )
                response = zspace_instance.get_data(search_url)
                if not response or response.status_code != 200:
                    logger.warning(
                        f"极影视媒体搜索失败: {response.status_code if response else 'No response'}")
                    continue
                items = response.json().get("Items", [])
                logger.info(f"极影视搜索 '{term}' 返回 {len(items)} 个结果")
                match_candidates = self._expand_zspace_episode_candidates(
                    zspace_instance, user_id, source_item, items)
                best_item = self._pick_best_matching_item(source_item, match_candidates)
                if best_item:
                    logger.info(f"极影视匹配成功: {best_item.get('Name')}")
                    return best_item

            logger.warning(f"极影视未找到匹配媒体: {media_name} ({media_type})")
            return None
        except Exception as e:
            logger.error(f"极影视查找匹配媒体失败: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def _expand_zspace_episode_candidates(
            self, zspace_instance, user_id: str, source_item: dict, candidates: List[dict]) -> List[dict]:
        """
        极影视搜索剧名时可能只返回 Series，需要展开剧集后再按季/集号匹配。
        """
        if source_item.get("Type") != "Episode" or not candidates:
            return candidates

        expanded = [
            item for item in candidates
            if item.get("Type") == "Episode"
        ]
        for item in candidates:
            if item.get("Type") != "Series":
                continue
            series_id = item.get("Id")
            if not series_id:
                continue
            url = (
                f"[HOST]emby/Shows/{series_id}/Episodes?api_key=[APIKEY]"
                f"&UserId={user_id}"
                f"&Fields=ProviderIds,OriginalTitle,ProductionYear,Path,UserData,"
                f"SeriesName,ParentIndexNumber,IndexNumber,RunTimeTicks"
            )
            response = zspace_instance.get_data(url)
            if not response or response.status_code != 200:
                logger.warning(
                    f"极影视剧集展开失败: {series_id} -> "
                    f"{response.status_code if response else 'No response'}")
                continue
            episode_items = response.json().get("Items", [])
            logger.info(
                f"极影视展开剧集: {item.get('Name')} -> {len(episode_items)} 个候选")
            expanded.extend(episode_items)

        return expanded or candidates

    def _pick_best_matching_item(self, source_item: dict, candidates: List[dict]) -> Optional[dict]:
        """
        从搜索结果中挑选最接近的媒体项。
        """
        if not candidates:
            return None

        source_type = source_item.get("Type")
        source_name = (source_item.get("Name") or "").strip().lower()
        source_series = self._normalize_series_name(
            source_item.get("SeriesName")).lower()
        source_year = source_item.get("ProductionYear")
        source_season = source_item.get("ParentIndexNumber")
        source_episode = source_item.get("IndexNumber")
        source_provider_ids = source_item.get("ProviderIds", {}) or {}
        source_tmdb = source_provider_ids.get("Tmdb")

        for item in candidates:
            provider_ids = item.get("ProviderIds", {}) or {}
            if source_tmdb and provider_ids.get("Tmdb") == source_tmdb:
                return item

        if source_type == "Movie":
            for item in candidates:
                item_name = (item.get("Name") or "").strip().lower()
                item_year = item.get("ProductionYear")
                if item_name == source_name and (
                        not source_year or not item_year or str(item_year) == str(source_year)):
                    return item

        if source_type in ["Episode", "Series"]:
            for item in candidates:
                if source_type == "Episode" and item.get("Type") != "Episode":
                    continue
                item_series = self._normalize_series_name(
                    item.get("SeriesName") or item.get("Name")).lower()
                item_season = item.get("ParentIndexNumber")
                item_episode = item.get("IndexNumber")
                if source_type == "Episode" and source_season and (
                        not item_season or str(source_season) != str(item_season)):
                    continue
                if source_type == "Episode" and source_episode and (
                        not item_episode or str(source_episode) != str(item_episode)):
                    continue
                if source_type != "Episode" and source_season and item_season and str(source_season) != str(item_season):
                    continue
                if source_type != "Episode" and source_episode and item_episode and str(source_episode) != str(item_episode):
                    continue
                if source_series and item_series and source_series != item_series:
                    continue
                return item

            for item in candidates:
                item_name = (item.get("Name") or "").strip().lower()
                item_series = self._normalize_series_name(
                    item.get("SeriesName") or item.get("Name")).lower()
                if source_series and item_series and source_series != item_series:
                    continue
                if source_name and item_name and source_name != item_name:
                    continue
                return item

            return None

        return candidates[0]

    @staticmethod
    def _normalize_series_name(name: Optional[str]) -> str:
        """
        规范化剧名，去掉极影视常见的季尾缀。
        """
        if not name:
            return ""
        value = str(name).strip()
        patterns = [
            r"\s*第\s*\d+\s*季\s*$",
            r"\s*[Ss]eason\s*\d+\s*$",
            r"\s*[Ss]\d+\s*$",
        ]
        for pattern in patterns:
            value = re.sub(pattern, "", value).strip()
        return value

    def _search_tv_by_tmdb(self, emby_instance, tmdb_id: str):
        """
        通过TMDB ID搜索电视剧
        """
        try:
            logger.info(f"通过TMDB ID搜索电视剧: {tmdb_id}")

            # 尝试使用通用搜索API
            # 构建搜索URL
            search_url = f"[HOST]emby/Items?api_key=[APIKEY]&Recursive=true&IncludeItemTypes=Series,Episode&Fields=ProviderIds"

            response = emby_instance.get_data(search_url)
            if response and response.status_code == 200:
                items = response.json().get("Items", [])
                logger.info(f"搜索到 {len(items)} 个电视剧项目")

                # 查找匹配的TMDB ID
                for item in items:
                    provider_ids = item.get("ProviderIds", {})
                    if provider_ids.get("Tmdb") == tmdb_id:
                        logger.info(f"找到TMDB匹配的电视剧: {item.get('Name')}")
                        return [item]

                logger.info("未找到TMDB匹配的电视剧")
            else:
                logger.warning(
                    f"电视剧搜索API调用失败: {response.status_code if response else 'No response'}")

            return None

        except Exception as e:
            logger.error(f"通过TMDB ID搜索电视剧失败: {str(e)}")
            return None

    def _update_user_progress(self, emby_instance, user_name: str, item_id: str, position_ticks: int) -> bool:
        """
        更新用户观看进度
        """
        try:
            # 获取用户ID
            user_id = emby_instance.get_user(user_name)
            if not user_id:
                logger.error(f"未找到用户: {user_name}")
                return False

            if self._is_zspace_instance(emby_instance):
                return self._update_zspace_progress(
                    emby_instance, user_id, item_id, position_ticks)

            success = self._update_progress_via_userdata(
                emby_instance, user_id, item_id, position_ticks)
            if success:
                return True

        except Exception as e:
            logger.error(f"更新用户观看进度失败: {str(e)}")
            return False

    def _update_zspace_progress(self, zspace_instance, user_id: str, item_id: str, position_ticks: int) -> bool:
        """
        通过极影视Emby兼容层更新播放进度。
        """
        try:
            logger.info(
                f"使用极影视 Sessions/Playing/Progress 更新进度: user_id={user_id}, "
                f"item_id={item_id}, position={position_ticks}")
            url = "[HOST]emby/Sessions/Playing/Progress"
            data = {
                "ItemId": item_id,
                "UserId": user_id,
                "PositionTicks": position_ticks,
                "IsPaused": True,
                "IsMuted": False,
                "PlayMethod": "DirectPlay",
                "PlaySessionId": "watchsync",
                "MediaSourceId": item_id,
                "CanSeek": True,
                "EventName": "timeupdate"
            }
            response = zspace_instance.post_data(
                url,
                json.dumps(data),
                headers={"Content-Type": "application/json"}
            )
            if response and response.status_code in [200, 204]:
                logger.info(f"极影视进度更新成功: {position_ticks} ticks")
                return True
            logger.error(
                f"极影视进度更新失败: {response.status_code if response else 'No response'}")
            if response:
                logger.error(f"响应内容: {response.text}")
            self._update_sync_metrics('api_error', False, 'zspace_progress_api')
            return False
        except Exception as e:
            logger.error(f"极影视进度更新异常: {str(e)}")
            logger.error(traceback.format_exc())
            self._update_sync_metrics(
                'api_error', False, 'zspace_progress_api_exception')
            return False

    def _update_progress_via_userdata(self, emby_instance, user_id: str, item_id: str, position_ticks: int) -> bool:
        """
        通过UserData API更新播放进度 - 修复版本
        """
        try:
            logger.info(
                f"使用UserData API更新进度: user_id={user_id}, item_id={item_id}, position={position_ticks}")

            # 首先获取当前的UserData以保持其他字段不变
            current_userdata = self._get_current_userdata(
                emby_instance, user_id, item_id)
            logger.debug(f"当前UserData: {current_userdata}")

            url = f"[HOST]emby/Users/{user_id}/Items/{item_id}/UserData"

            # 构建UserData更新请求 - 只包含必要字段
            data = {
                "PlaybackPositionTicks": position_ticks,
                "LastPlayedDate": datetime.now().isoformat() + "Z"  # 更新最后播放时间
            }

            # 保持现有的重要字段
            if current_userdata.get("PlayCount") is not None:
                data["PlayCount"] = current_userdata["PlayCount"]
            if current_userdata.get("IsFavorite") is not None:
                data["IsFavorite"] = current_userdata["IsFavorite"]
            if current_userdata.get("Rating") is not None:
                data["Rating"] = current_userdata["Rating"]
            if current_userdata.get("PlayCount") is not None:
                data["PlayCount"] = current_userdata["PlayCount"]
            if current_userdata.get("Played") is not None:
                data["Played"] = current_userdata["Played"]

            url_with_params = f"{url}?api_key=[APIKEY]"
            logger.debug(f"UserData API请求: {url_with_params}")
            logger.debug(f"请求数据: {data}")

            response = emby_instance.post_data(url_with_params, json.dumps(data),
                                               headers={"Content-Type": "application/json"})

            if response and response.status_code in [200, 204]:
                logger.info(
                    f"UserData API成功更新用户 {user_id} 的观看进度到 {position_ticks} ticks")

                # 验证更新是否成功
                updated_userdata = self._get_current_userdata(
                    emby_instance, user_id, item_id)
                actual_position = updated_userdata.get(
                    "PlaybackPositionTicks", 0)
                logger.info(
                    f"验证更新结果: 期望={position_ticks}, 实际={actual_position}")

                return True
            else:
                logger.error(
                    f"UserData API更新失败: {response.status_code if response else 'No response'}")
                if response:
                    logger.error(f"响应内容: {response.text}")
                self._update_sync_metrics('api_error', False, 'userdata_api')
                return False

        except Exception as e:
            logger.error(f"UserData API更新观看进度失败: {str(e)}")
            logger.error(traceback.format_exc())
            self._update_sync_metrics(
                'api_error', False, 'userdata_api_exception')
            return False

    def _get_current_userdata(self, emby_instance, user_id: str, item_id: str) -> dict:
        """
        获取当前的UserData
        """
        try:
            url = f"[HOST]emby/Users/{user_id}/Items/{item_id}?api_key=[APIKEY]"
            response = emby_instance.get_data(url)

            if response and response.status_code == 200:
                item_data = response.json()
                return item_data.get("UserData", {})
            else:
                logger.warning(
                    f"获取当前UserData失败: {response.status_code if response else 'No response'}")
                return {}

        except Exception as e:
            logger.warning(f"获取当前UserData异常: {str(e)}")
            return {}

    def _get_item_runtime(self, emby_instance, item_id: str) -> int:
        """
        获取媒体项目的运行时长
        """
        try:
            url = f"[HOST]emby/Items/{item_id}?api_key=[APIKEY]"
            response = emby_instance.get_data(url)

            if response and response.status_code == 200:
                item_data = response.json()
                return item_data.get("RunTimeTicks", 0)
            else:
                return 0

        except Exception as e:
            logger.warning(f"获取媒体运行时长异常: {str(e)}")
            return 0

    def _health_check_emby_connection(self, server_name: str, emby_instance) -> bool:
        """
        检查Emby服务器连接健康状态
        """
        try:
            url = f"[HOST]emby/System/Info?api_key=[APIKEY]"
            response = emby_instance.get_data(url)

            if response and response.status_code == 200:
                server_info = response.json()
                logger.debug(
                    f"Emby服务器 {server_name} 健康检查通过: {server_info.get('ServerName', 'Unknown')}")
                return True
            else:
                logger.warning(
                    f"Emby服务器 {server_name} 健康检查失败: {response.status_code if response else 'No response'}")
                return False

        except Exception as e:
            logger.error(f"Emby服务器 {server_name} 健康检查异常: {str(e)}")
            return False

    def _record_sync_result(self, source_server: str, source_user: str, target_server: str,
                            target_user: str, item_info: dict, position_ticks: int,
                            status: str, error_message: str = None, sync_type: str = "playback"):
        """
        记录同步结果到数据库
        """
        if not self._db_path:
            return

        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()

                # 插入同步记录
                cursor.execute('''
                    INSERT INTO sync_records
                    (timestamp, source_server, source_user, target_server, target_user,
                     media_name, media_type, media_id, position_ticks, sync_type, status, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    datetime.now().isoformat(),
                    source_server,
                    source_user,
                    target_server,
                    target_user,
                    item_info.get('Name', ''),
                    item_info.get('Type', ''),
                    item_info.get('Id', ''),
                    position_ticks,
                    sync_type,
                    status,
                    error_message
                ))

                # 更新统计信息
                today = datetime.now().strftime('%Y-%m-%d')
                cursor.execute('''
                    INSERT OR IGNORE INTO sync_stats (date, total_syncs, success_syncs, failed_syncs)
                    VALUES (?, 0, 0, 0)
                ''', (today,))

                if status == 'success':
                    cursor.execute('''
                        UPDATE sync_stats
                        SET total_syncs = total_syncs + 1, success_syncs = success_syncs + 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE date = ?
                    ''', (today,))
                else:
                    cursor.execute('''
                        UPDATE sync_stats
                        SET total_syncs = total_syncs + 1, failed_syncs = failed_syncs + 1,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE date = ?
                    ''', (today,))

                conn.commit()

        except Exception as e:
            logger.error(f"记录同步结果失败: {str(e)}")

    def get_api(self) -> List[Dict[str, Any]]:
        """
        注册插件API
        """
        return [
            {
                "path": "/servers",
                "endpoint": self._get_servers,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取Emby服务器列表",
                "description": "获取已配置的Emby服务器列表"
            },
            {
                "path": "/users",
                "endpoint": self._get_users_endpoint,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取服务器用户列表",
                "description": "获取指定服务器的用户列表"
            },

            {
                "path": "/stats",
                "endpoint": self._get_stats,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取同步统计",
                "description": "获取同步统计信息"
            },
            {
                "path": "/records",
                "endpoint": self._get_records_endpoint,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取同步记录",
                "description": "获取历史同步记录，支持分页参数(limit, offset)"
            },
            {
                "path": "/status",
                "endpoint": self._get_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取同步状态",
                "description": "获取实时同步状态和指标"
            },
            {
                "path": "/records/old",
                "endpoint": self._clear_old_records_endpoint,
                "methods": ["DELETE"],
                "auth": "bear",
                "summary": "清理旧记录",
                "description": "清理指定天数前的同步记录，支持days参数"
            }
        ]

    def _get_servers(self) -> Dict[str, Any]:
        """
        获取Emby服务器列表
        """
        try:
            logger.info("API调用: 获取Emby服务器列表")
            servers = []

            if not self._emby_instances:
                logger.warning("没有找到Emby服务器实例")
                return {"success": True, "data": [], "message": "没有找到Emby服务器实例"}

            for name, instance in self._emby_instances.items():
                server_info = {
                    "name": name,
                    "type": self._get_server_type(name),
                    "host": instance._host if hasattr(instance, '_host') else "",
                    "status": "online" if instance else "offline"
                }
                servers.append(server_info)
                logger.info(f"找到服务器: {name} - {server_info['host']}")

            logger.info(f"返回 {len(servers)} 个服务器")
            return {"success": True, "data": servers}
        except Exception as e:
            logger.error(f"获取服务器列表失败: {str(e)}")
            return {"success": False, "message": str(e)}

    def _get_users_endpoint(self) -> Dict[str, Any]:
        """
        API端点：获取所有服务器的用户列表
        """
        logger.info("用户API端点调用")
        logger.info(f"当前媒体服务器实例数量: {len(self._emby_instances)}")
        logger.info(f"媒体服务器实例列表: {list(self._emby_instances.keys())}")

        try:
            all_users = {}
            for server_name, emby_instance in self._emby_instances.items():
                logger.info(f"开始处理服务器: {server_name}")
                logger.info(f"Emby实例是否为空: {emby_instance is None}")

                users = self._get_server_users(emby_instance)
                all_users[server_name] = users
                logger.info(f"服务器 {server_name} 获取到 {len(users)} 个用户")

                if users:
                    logger.info(f"用户详情: {users}")
                else:
                    logger.warning(f"服务器 {server_name} 用户列表为空")

            logger.info(f"最终返回数据: {all_users}")
            return {"success": True, "data": all_users}
        except Exception as e:
            logger.error(f"获取用户列表失败: {str(e)}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return {"success": False, "message": str(e)}

    def _get_users_internal(self, server) -> Dict[str, Any]:
        """
        内部方法：获取服务器用户列表
        """
        logger.info(f"内部用户获取方法调用，服务器: '{server}'")
        logger.info(
            f"可用的媒体服务器实例: {list(self._emby_instances.keys()) if self._emby_instances else '无'}")

        # 如果没有传入server参数，尝试获取第一个可用服务器
        if not server and self._emby_instances:
            server = list(self._emby_instances.keys())[0]
            logger.info(f"未指定服务器，使用第一个可用服务器: {server}")

        # 检查服务器名称是否存在
        if server and server not in self._emby_instances:
            logger.warning(f"请求的服务器 '{server}' 不存在")
            logger.info(f"尝试模糊匹配服务器名称...")

            # 尝试模糊匹配（忽略大小写，部分匹配）
            for available_server in self._emby_instances.keys():
                if server.lower() in available_server.lower() or available_server.lower() in server.lower():
                    logger.info(
                        f"找到匹配的服务器: '{available_server}' 匹配 '{server}'")
                    server = available_server
                    break

        return self._get_users(server)

    def _get_users(self, server: str = None) -> Dict[str, Any]:
        """
        获取服务器用户列表
        """
        try:
            server_name = server
            logger.info(f"API调用: 获取服务器用户列表, 服务器: {server_name}")

            if not server_name:
                logger.warning("缺少服务器名称参数")
                available_servers = list(self._emby_instances.keys())
                return {"success": False, "message": f"缺少服务器名称参数, 可用服务器: {available_servers}"}

            emby_instance = self._emby_instances.get(server_name)
            if not emby_instance:
                logger.error(f"未找到服务器: {server_name}")
                available_servers = list(self._emby_instances.keys())
                return {"success": False, "message": f"未找到服务器: {server_name}, 可用服务器: {available_servers}"}

            # 获取用户列表
            users = self._get_server_users(emby_instance)
            logger.info(f"获取到 {len(users)} 个用户")
            return {"success": True, "data": users}

        except Exception as e:
            logger.error(f"获取用户列表失败: {str(e)}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return {"success": False, "message": str(e)}

    def _get_server_users(self, emby_instance) -> List[Dict[str, str]]:
        """
        获取服务器用户列表
        """
        try:
            logger.info(f"开始获取Emby服务器用户列表...")
            logger.info(f"Emby实例类型: {type(emby_instance)}")

            if not emby_instance:
                logger.error("Emby实例为空")
                return []

            if self._is_zspace_instance(emby_instance):
                user_id = emby_instance.get_user(None) if hasattr(emby_instance, "get_user") else getattr(
                    emby_instance, "user", None)
                user_name = getattr(emby_instance, "_username", None) or user_id
                if user_id and user_name:
                    return [{"id": user_id, "name": user_name}]
                return []

            url = f"[HOST]emby/Users?api_key=[APIKEY]"
            logger.info(f"请求URL模板: {url}")

            # 添加调试信息，查看Emby实例的属性
            logger.info(
                f"Emby实例host: {getattr(emby_instance, '_host', 'N/A')}")
            logger.info(f"Emby实例apikey: {getattr(emby_instance, '_apikey', 'N/A')[:10]}..." if getattr(
                emby_instance, '_apikey', None) else "Emby实例apikey: N/A")

            response = emby_instance.get_data(url)
            logger.info(
                f"API响应状态: {response.status_code if response else '无响应'}")

            if response is None:
                logger.error("响应对象为None，可能是网络连接问题或URL格式错误")
            elif hasattr(response, 'url'):
                logger.info(f"实际请求URL: {response.url}")

            if response and hasattr(response, 'request') and hasattr(response.request, 'url'):
                logger.info(f"请求URL: {response.request.url}")

            if response and response.status_code == 200:
                users_data = response.json()
                logger.info(f"从Emby API获取到 {len(users_data)} 个用户")

                user_list = []
                for user in users_data:
                    user_info = {"id": user["Id"], "name": user["Name"]}
                    user_list.append(user_info)
                    logger.info(
                        f"处理用户: {user_info['name']} (ID: {user_info['id']})")

                logger.info(f"最终返回 {len(user_list)} 个用户")
                return user_list
            else:
                logger.error(
                    f"Emby API调用失败，状态码: {response.status_code if response else '无响应'}")
                if response:
                    logger.error(f"响应内容: {response.text[:200]}")
                return []

        except Exception as e:
            logger.error(f"获取用户列表失败: {str(e)}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")
            return []

    def _get_stats(self) -> Dict[str, Any]:
        """
        获取同步统计信息
        """
        try:
            if not self._db_path:
                return {"success": False, "message": "数据库未初始化"}

            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()

                # 从sync_records表获取详细统计
                cursor.execute('''
                    SELECT timestamp, source_user, target_user, sync_type, status, created_at
                    FROM sync_records
                    ORDER BY created_at DESC
                ''')

                all_records = cursor.fetchall()
                total_syncs = len(all_records)
                success_syncs = len(
                    [r for r in all_records if r[4] == 'success'])
                failed_syncs = total_syncs - success_syncs

                # 计算成功率
                success_rate = (success_syncs / total_syncs *
                                100) if total_syncs > 0 else 0

                # 计算今日同步次数 - 修复时区问题
                today = datetime.now().date()
                today_syncs = 0
                for record in all_records:
                    if record[5]:  # created_at字段
                        try:
                            # 处理不同的日期格式
                            record_date_str = record[5]
                            if 'T' in record_date_str:
                                record_date = datetime.fromisoformat(
                                    record_date_str.replace('Z', '+00:00')).date()
                            else:
                                record_date = datetime.strptime(
                                    record_date_str, '%Y-%m-%d %H:%M:%S').date()

                            if record_date == today:
                                today_syncs += 1
                        except Exception as e:
                            logger.debug(f"解析日期失败: {record_date_str}, 错误: {e}")
                            continue

                # 计算活跃用户数（最近24小时）
                yesterday = datetime.now() - timedelta(hours=24)
                recent_records = [r for r in all_records if r[5] and
                                  datetime.fromisoformat(r[5]) >= yesterday]
                active_users = set()
                for record in recent_records:
                    active_users.add(record[1])  # source_user
                    active_users.add(record[2])  # target_user

                # 统计同步类型
                sync_types = set()
                for record in all_records:
                    sync_types.add(record[3] or 'playback')

                # 获取同步组数量
                enabled_groups = len(
                    [g for g in self._sync_groups if g.get("enabled", True)])
                total_users = sum(len(g.get("users", []))
                                  for g in self._sync_groups if g.get("enabled", True))

                stats = {
                    "总同步次数": total_syncs,
                    "今日同步次数": today_syncs,
                    "成功次数": success_syncs,
                    "失败次数": failed_syncs,
                    "成功率": f"{success_rate:.1f}",
                    "活跃用户数": len(active_users),
                    "同步类型": list(sync_types),
                    "同步组数": enabled_groups,
                    "组内用户数": total_users
                }

                return {"success": True, "data": stats}

        except Exception as e:
            logger.error(f"获取统计信息失败: {str(e)}")
            return {"success": False, "message": str(e)}

    def _get_records(self, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        """
        获取同步记录，支持分页
        """
        try:
            if not self._db_path:
                return {"success": False, "message": "数据库未初始化"}

            # 限制最大记录数，防止性能问题
            limit = min(max(limit, 10), 100)  # 最小10条，最大100条
            offset = max(offset, 0)  # offset不能为负数

            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()

                # 先获取总记录数
                cursor.execute('SELECT COUNT(*) FROM sync_records')
                total_count = cursor.fetchone()[0]

                # 获取同步记录
                cursor.execute('''
                    SELECT id, timestamp, source_server, source_user, target_server, target_user,
                           media_name, media_type, sync_type, status, error_message, created_at, position_ticks
                    FROM sync_records
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                ''', (limit, offset))

                records = []
                for row in cursor.fetchall():
                    records.append({
                        "id": row[0],
                        "timestamp": row[1],
                        "source_server": row[2],
                        "source_user": row[3],
                        "target_server": row[4],
                        "target_user": row[5],
                        "media_name": row[6],
                        "media_type": row[7],
                        "sync_type": row[8],
                        "status": row[9],
                        "error_message": row[10],
                        "created_at": row[11],
                        "position_ticks": row[12]
                    })

                # 计算是否还有更多记录
                has_more = (offset + len(records)) < total_count

                return {
                    "success": True,
                    "data": records,
                    "pagination": {
                        "total": total_count,
                        "offset": offset,
                        "limit": limit,
                        "has_more": has_more,
                        "current_count": len(records)
                    }
                }

        except Exception as e:
            logger.error(f"获取同步记录失败: {str(e)}")
            return {"success": False, "message": str(e)}

    def _get_records_endpoint(self, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
        """
        API端点：获取同步记录，支持分页参数
        """
        try:
            return self._get_records(limit, offset)
        except Exception as e:
            logger.error(f"获取同步记录端点失败: {str(e)}")
            return {"success": False, "message": str(e)}

    def _clear_old_records_endpoint(self, days: int = 30) -> Dict[str, Any]:
        """
        API端点：清理旧记录，支持days参数
        """
        try:
            return self._clear_old_records(days)
        except Exception as e:
            logger.error(f"清理旧记录端点失败: {str(e)}")
            return {"success": False, "message": str(e)}

    def _get_status(self):
        """
        获取同步状态API
        """
        try:
            # 清理过期的同步记录
            self._cleanup_expired_syncs()

            # 获取状态信息
            status = self.get_sync_status()

            # 添加额外的状态信息
            status.update({
                "plugin_enabled": self._enabled,
                "sync_movies": self._sync_movies,
                "sync_tv": self._sync_tv,
                "min_watch_time": self._min_watch_time,
                "last_update": datetime.now().isoformat()
            })

            return {
                "success": True,
                "data": status
            }

        except Exception as e:
            logger.error(f"获取同步状态失败: {str(e)}")
            return {"success": False, "message": str(e)}

    def _clear_old_records(self, days: int = 30) -> Dict[str, Any]:
        """
        清理指定天数前的旧记录
        """
        try:
            if not self._db_path:
                return {"success": False, "message": "数据库未初始化"}

            # 限制天数范围，防止误删
            days = max(min(days, 365), 1)  # 最小1天，最大365天
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()

                # 删除指定天数前的记录
                cursor.execute('''
                    DELETE FROM sync_records
                    WHERE created_at < ?
                ''', (cutoff_date,))

                deleted_count = cursor.rowcount
                conn.commit()

                logger.info(f"清理了 {deleted_count} 条旧记录")
                return {
                    "success": True,
                    "message": f"成功清理了 {deleted_count} 条{days}天前的记录"
                }

        except Exception as e:
            logger.error(f"清理旧记录失败: {str(e)}")
            return {"success": False, "message": str(e)}

    @staticmethod
    def get_render_mode() -> Tuple[str, Optional[str]]:
        """
        获取插件渲染模式
        """
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，返回Vue组件配置
        """
        # 返回空配置，使用Vue组件
        return [], {}

    def get_page(self) -> List[dict]:
        """
        拼装插件详情页面，返回Vue组件配置
        """
        # 返回空配置，使用Vue组件
        return []

    def stop_service(self):
        """
        退出插件
        """
        self._stop_zspace_poll_scheduler()
        logger.info("观看记录同步插件已停止")
