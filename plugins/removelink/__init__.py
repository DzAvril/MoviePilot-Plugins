import os
import platform
import shutil
import threading
import time
import traceback
from pathlib import Path
from typing import List, Tuple, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple

from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver
from app.db.transferhistory_oper import TransferHistoryOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import NotificationType
from app.core.event import eventmanager
from app.schemas.types import EventType
from app.chain.storage import StorageChain
from app import schemas

state_lock = threading.Lock()
deletion_queue_lock = threading.Lock()


class FileInfo(NamedTuple):
    """文件信息"""

    inode: int
    add_time: datetime


@dataclass
class DeletionTask:
    """延迟删除任务"""

    file_path: Path
    deleted_inode: int
    timestamp: datetime
    processed: bool = False


class FileMonitorHandler(FileSystemEventHandler):
    """
    目录监控处理
    """

    def __init__(
        self, monpath: str, sync: Any, monitor_type: str = "hardlink", **kwargs
    ):
        super(FileMonitorHandler, self).__init__(**kwargs)
        self._watch_path = monpath
        self.sync = sync
        self.monitor_type = monitor_type  # "hardlink" 或 "strm"

    def _is_excluded_file(self, file_path: Path) -> bool:
        """检查文件是否应该被排除"""
        # 排除临时文件
        if file_path.suffix in [".!qB", ".part", ".mp", ".tmp", ".temp"]:
            return True
        # 检查关键字过滤
        if self.sync.exclude_keywords:
            for keyword in self.sync.exclude_keywords.split("\n"):
                if keyword and keyword in str(file_path):
                    logger.debug(f"{file_path} 命中过滤关键字 {keyword}，不处理")
                    return True
        return False

    def _add_file_to_state(self, file_path: Path):
        """添加文件到状态管理"""
        if self._is_excluded_file(file_path):
            return

        with state_lock:
            try:
                if not file_path.exists():
                    return
                stat_info = file_path.stat()
                file_info = FileInfo(inode=stat_info.st_ino, add_time=datetime.now())
                self.sync.file_state[str(file_path)] = file_info
                logger.debug(f"添加文件到监控：{file_path}")
            except (OSError, PermissionError) as e:
                logger.debug(f"无法访问文件 {file_path}：{e}")
            except Exception as e:
                logger.error(f"新增文件记录失败：{str(e)}")

    def on_created(self, event):
        if event.is_directory:
            return
        file_path = Path(event.src_path)
        logger.info(f"监测到新增文件：{file_path}")
        self._add_file_to_state(file_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        # 处理移动事件：移除源文件，添加目标文件
        src_path = Path(event.src_path)
        dest_path = Path(event.dest_path)

        logger.info(f"监测到文件移动：{src_path} -> {dest_path}")

        # 从状态中移除源文件
        with state_lock:
            self.sync.file_state.pop(str(src_path), None)

        # 添加目标文件
        self._add_file_to_state(dest_path)

    def on_deleted(self, event):
        file_path = Path(event.src_path)
        if event.is_directory:
            # 单独处理文件夹删除触发删除种子
            if self.sync._delete_torrents:
                # 发送事件
                logger.info(f"监测到删除文件夹：{file_path}")
                # 文件夹删除发送 DownloadFileDeleted 事件
                eventmanager.send_event(
                    EventType.DownloadFileDeleted, {"src": str(file_path)}
                )
            return
        if file_path.suffix in [".!qB", ".part", ".mp"]:
            return
        logger.info(f"监测到删除文件：{file_path}")
        # 命中过滤关键字不处理
        if self.sync.exclude_keywords:
            for keyword in self.sync.exclude_keywords.split("\n"):
                if keyword and keyword in str(file_path):
                    logger.info(f"{file_path} 命中过滤关键字 {keyword}，不处理")
                    return

        # 根据监控类型处理删除事件
        if self.monitor_type == "strm":
            # STRM 监控目录：只处理 strm 文件删除，其他文件忽略
            if file_path.suffix.lower() == ".strm":
                self.sync.handle_strm_deleted(file_path)
            # 其他文件（如刮削文件）在 STRM 监控目录中被忽略，避免触发硬链接清理
        else:
            # 硬链接监控目录：处理硬链接文件删除
            self.sync.handle_deleted(file_path)


def updateState(monitor_dirs: List[str]):
    """
    更新监控目录的文件列表
    """
    # 记录开始时间
    start_time = time.time()
    file_state = {}
    init_time = datetime.now()
    error_count = 0

    for mon_path in monitor_dirs:
        if not os.path.exists(mon_path):
            logger.warning(f"监控目录不存在：{mon_path}")
            continue

        try:
            for root, _, files in os.walk(mon_path):
                for file_name in files:
                    file_path = Path(root) / file_name
                    try:
                        if not file_path.exists():
                            continue
                        # 获取文件统计信息
                        stat_info = file_path.stat()
                        # 记录文件信息
                        file_info = FileInfo(inode=stat_info.st_ino, add_time=init_time)
                        file_state[str(file_path)] = file_info
                    except (OSError, PermissionError) as e:
                        error_count += 1
                        logger.debug(f"无法访问文件 {file_path}：{e}")
        except Exception as e:
            logger.error(f"扫描目录 {mon_path} 时发生错误：{e}")

    # 记录结束时间
    end_time = time.time()
    # 计算耗时
    elapsed_time = end_time - start_time

    logger.info(
        f"更新文件列表完成，共计 {len(file_state)} 个文件，耗时 {elapsed_time:.2f} 秒"
    )
    if error_count > 0:
        logger.warning(f"扫描过程中有 {error_count} 个文件无法访问")

    return file_state


class RemoveLink(_PluginBase):
    # 插件名称
    plugin_name = "清理媒体文件"
    # 插件描述
    plugin_desc = "媒体文件清理工具：支持硬链接文件清理、STRM文件清理、刮削文件清理（元数据、图片、字幕）、转移记录清理、种子联动删除等功能"
    # 插件图标
    plugin_icon = "Ombi_A.png"
    # 插件版本
    plugin_version = "2.10"
    # 插件作者
    plugin_author = "DzAvril"
    # 作者主页
    author_url = "https://github.com/DzAvril"
    # 插件配置项ID前缀
    plugin_config_prefix = "linkdeleted_"
    # 加载顺序
    plugin_order = 0
    # 可使用的用户级别
    auth_level = 1

    # 刮削文件扩展名（包括字幕文件）
    SCRAP_EXTENSIONS = [
        # 元数据文件
        ".nfo",
        ".xml",
        # 图片文件
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".tbn",
        ".fanart",
        ".gif",
        ".bmp",
        # 字幕文件
        ".srt",
        ".ass",
        ".ssa",
        ".sub",
        ".idx",
        ".vtt",
        ".sup",
        ".pgs",
        ".smi",
        ".rt",
        ".sbv",
        ".csf-bk",
        ".csf-tmp",
    ]

    # 刮削/媒体服务器生成的关联目录后缀
    SCRAP_DIR_SUFFIXES = [
        ".trickplay",
    ]

    # preivate property
    monitor_dirs = ""
    exclude_dirs = ""
    exclude_keywords = ""
    _enabled = False
    _notify = False
    _delete_scrap_infos = False
    _delete_torrents = False
    _delete_history = False
    _delayed_deletion = True
    _delay_seconds = 30
    _monitor_strm_deletion = False
    strm_path_mappings = ""
    custom_scrap_extensions = ""
    _custom_scrap_extensions = []
    _transferhistory = None
    _storagechain = None
    _observer = []
    # 监控目录的文件列表 {文件路径: FileInfo(inode, add_time)}
    file_state: Dict[str, FileInfo] = {}
    # 延迟删除队列
    deletion_queue: List[DeletionTask] = []
    # 延迟删除定时器
    _deletion_timer = None

    @staticmethod
    def __choose_observer():
        """
        选择最优的监控模式
        """
        system = platform.system()

        try:
            if system == "Linux":
                from watchdog.observers.inotify import InotifyObserver

                return InotifyObserver()
            elif system == "Darwin":
                from watchdog.observers.fsevents import FSEventsObserver

                return FSEventsObserver()
            elif system == "Windows":
                from watchdog.observers.read_directory_changes import WindowsApiObserver

                return WindowsApiObserver()
        except Exception as error:
            logger.warn(f"导入模块错误：{error}，将使用 PollingObserver 监控目录")
        return PollingObserver()

    def init_plugin(self, config: dict = None):
        logger.info(f"初始化媒体文件清理插件")
        self._transferhistory = TransferHistoryOper()
        self._storagechain = StorageChain()

        if config:
            self._enabled = config.get("enabled")
            self._notify = config.get("notify")
            self.monitor_dirs = config.get("monitor_dirs")
            self.exclude_dirs = config.get("exclude_dirs") or ""
            self.exclude_keywords = config.get("exclude_keywords") or ""
            self._delete_scrap_infos = config.get("delete_scrap_infos")
            self._delete_torrents = config.get("delete_torrents")
            self._delete_history = config.get("delete_history")
            self._delayed_deletion = config.get("delayed_deletion", True)
            self._monitor_strm_deletion = config.get("monitor_strm_deletion", False)
            self.strm_path_mappings = config.get("strm_path_mappings") or ""
            self.custom_scrap_extensions = config.get("custom_scrap_extensions") or ""
            self._custom_scrap_extensions = self._parse_custom_scrap_extensions(
                self.custom_scrap_extensions
            )
            # 验证延迟时间范围，允许用户设置较长的延迟时间（最长 24 小时）
            delay_seconds = config.get("delay_seconds", 30)
            try:
                self._delay_seconds = max(10, min(86400, int(delay_seconds)))
            except (TypeError, ValueError):
                self._delay_seconds = 30

        # 停止现有任务
        self.stop_service()

        # 初始化延迟删除队列
        self.deletion_queue = []

        if self._enabled:
            # 记录延迟删除配置状态
            if self._delayed_deletion:
                logger.info(f"延迟删除功能已启用，延迟时间: {self._delay_seconds} 秒")
            else:
                logger.info("延迟删除功能已禁用，将使用立即删除模式")

            # 记录 STRM 监控配置状态
            strm_monitor_dirs = []
            if self._monitor_strm_deletion:
                logger.info("STRM 文件删除监控功能已启用")
                if self.strm_path_mappings:
                    mappings = self._parse_strm_path_mappings()
                    logger.info(f"配置了 {len(mappings)} 个 STRM 路径映射")
                    # 从映射配置中提取 STRM 监控目录
                    strm_monitor_dirs = list(mappings.keys())
                    logger.info(f"STRM 监控目录：{strm_monitor_dirs}")
                else:
                    logger.warning("STRM 监控已启用但未配置路径映射")
            else:
                logger.info("STRM 文件删除监控功能已禁用")

            # 读取硬链接监控目录配置
            hardlink_monitor_dirs = []
            if self.monitor_dirs:
                hardlink_monitor_dirs = [
                    d.strip() for d in self.monitor_dirs.split("\n") if d.strip()
                ]
                logger.info(f"硬链接监控目录：{hardlink_monitor_dirs}")

            # 启动硬链接监控
            for mon_path in hardlink_monitor_dirs:
                if not mon_path:
                    continue
                try:
                    # 使用优化的监控器选择
                    observer = self.__choose_observer()
                    self._observer.append(observer)
                    observer.schedule(
                        FileMonitorHandler(mon_path, self, monitor_type="hardlink"),
                        mon_path,
                        recursive=True,
                    )
                    observer.daemon = True
                    observer.start()
                    logger.info(f"{mon_path} 的硬链接监控服务启动")
                except Exception as e:
                    err_msg = str(e)
                    # 特殊处理 inotify 限制错误
                    if "inotify" in err_msg and "reached" in err_msg:
                        logger.warn(
                            f"目录监控服务启动出现异常：{err_msg}，请在宿主机上（不是docker容器内）执行以下命令并重启："
                            + """
                             echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf
                             echo fs.inotify.max_user_instances=524288 | sudo tee -a /etc/sysctl.conf
                             sudo sysctl -p
                             """
                        )
                    else:
                        logger.error(f"{mon_path} 启动硬链接监控失败：{err_msg}")
                    self.systemmessage.put(
                        f"{mon_path} 启动硬链接监控失败：{err_msg}",
                        title="媒体文件清理",
                    )

            # 启动 STRM 监控
            for mon_path in strm_monitor_dirs:
                if not mon_path:
                    continue
                try:
                    # 使用优化的监控器选择
                    observer = self.__choose_observer()
                    self._observer.append(observer)
                    observer.schedule(
                        FileMonitorHandler(mon_path, self, monitor_type="strm"),
                        mon_path,
                        recursive=True,
                    )
                    observer.daemon = True
                    observer.start()
                    logger.info(f"{mon_path} 的 STRM 监控服务启动")
                except Exception as e:
                    err_msg = str(e)
                    # 特殊处理 inotify 限制错误
                    if "inotify" in err_msg and "reached" in err_msg:
                        logger.warn(
                            f"目录监控服务启动出现异常：{err_msg}，请在宿主机上（不是docker容器内）执行以下命令并重启："
                            + """
                             echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf
                             echo fs.inotify.max_user_instances=524288 | sudo tee -a /etc/sysctl.conf
                             sudo sysctl -p
                             """
                        )
                    else:
                        logger.error(f"{mon_path} 启动 STRM 监控失败：{err_msg}")
                    self.systemmessage.put(
                        f"{mon_path} 启动 STRM 监控失败：{err_msg}",
                        title="媒体文件清理",
                    )

            # 合并所有监控目录用于文件状态更新
            all_monitor_dirs = hardlink_monitor_dirs + strm_monitor_dirs

            # 更新监控集合 - 在所有线程停止后安全获取锁
            with state_lock:
                self.file_state = updateState(all_monitor_dirs)
                logger.debug("监控集合更新完成")

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    # 插件总体说明
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "title": "🧹 媒体文件清理插件",
                                            "text": "全面的媒体文件清理工具，支持硬链接文件清理和STRM文件清理两种模式，可独立启用。硬链接清理用于监控硬链接文件删除并自动清理相关文件；STRM清理用于监控STRM文件删除并删除对应的网盘文件。同时支持刮削文件清理（元数据、图片、字幕）、转移记录清理、种子联动删除等功能。",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # 公用配置
                    {
                        "component": "VRow",
                        "content": [
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
                                            "label": "发送通知",
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
                                            "model": "delete_scrap_infos",
                                            "label": "清理刮削文件",
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
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "delete_torrents",
                                            "label": "联动删除种子",
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
                                            "model": "delete_history",
                                            "label": "删除转移记录",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # 硬链接清理配置分隔线
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VDivider",
                                        "props": {"style": "margin: 20px 0;"},
                                    }
                                ],
                            },
                        ],
                    },
                    # 硬链接清理配置标题
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "primary",
                                            "variant": "tonal",
                                            "title": "🔗 硬链接清理配置",
                                            "text": "监控硬链接文件删除，自动清理相关的硬链接文件、刮削文件和转移记录。",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # 硬链接延迟删除配置
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "delayed_deletion",
                                            "label": "启用延迟删除",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "delay_seconds",
                                            "label": "延迟时间(秒)",
                                            "type": "number",
                                            "min": 10,
                                            "max": 86400,
                                            "placeholder": "30",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # 硬链接监控目录配置
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
                                            "model": "monitor_dirs",
                                            "label": "硬链接监控目录",
                                            "rows": 5,
                                            "placeholder": "硬链接源目录及目标目录均需加入监控，每一行一个目录",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    # 硬链接排除配置
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "exclude_dirs",
                                            "label": "不删除目录",
                                            "rows": 3,
                                            "placeholder": "该目录下的文件不会被动删除，一行一个目录",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextarea",
                                        "props": {
                                            "model": "exclude_keywords",
                                            "label": "排除关键词",
                                            "rows": 3,
                                            "placeholder": "每一行一个关键词",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # 硬链接配置说明
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
                                            "model": "custom_scrap_extensions",
                                            "label": "自定义刮削文件后缀",
                                            "rows": 3,
                                            "placeholder": "每行或逗号分隔一个后缀，例如：.txt\n.json\n-mediainfo.json",
                                            "hint": "开启清理刮削文件后生效，会与内置 .nfo/.jpg/.srt 等后缀一起联动清理",
                                            "persistent-hint": True,
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    # 硬链接配置说明
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "warning",
                                            "variant": "tonal",
                                            "text": "延迟删除功能：启用后，文件删除时不会立即删除硬链接，而是等待指定时间后再检查文件是否仍被删除。这可以防止媒体重整理导致的意外删除。",
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
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "硬链接监控：源目录和硬链接目录都需要添加到监控目录中；如需实现删除硬链接时不删除源文件，可把源文件目录配置到不删除目录中。",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # STRM清理配置分隔线
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VDivider",
                                        "props": {"style": "margin: 20px 0;"},
                                    }
                                ],
                            },
                        ],
                    },
                    # STRM清理配置标题
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "success",
                                            "variant": "tonal",
                                            "title": "📺 STRM文件清理配置",
                                            "text": "监控STRM文件删除，自动删除网盘上对应的视频文件。监控目录会自动从路径映射中获取。",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # STRM功能开关
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "monitor_strm_deletion",
                                            "label": "启用STRM文件监控",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # STRM路径映射配置
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
                                            "model": "strm_path_mappings",
                                            "label": "STRM路径映射",
                                            "rows": 4,
                                            "placeholder": "STRM目录:存储类型:网盘目录，每行一个映射关系\n例如：/ssd/strm:u115:/media\n例如：/nas/strm:alipan:/阿里云盘/媒体",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    # STRM配置说明
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "STRM文件监控：启用后会自动监控映射中的STRM目录，当STRM文件删除时会查找并删除网盘上对应的视频文件。路径映射格式：STRM目录:存储类型:网盘目录，例如 /ssd/strm:u115:/media 表示 /ssd/strm/test.strm 对应115网盘中以 /media/test 为前缀的视频文件。",
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
                                        "component": "VAlert",
                                        "props": {
                                            "type": "success",
                                            "variant": "tonal",
                                            "text": "支持的存储类型：local（本地存储）、alipan（阿里云盘）、u115（115网盘）、rclone（Rclone挂载）、alist（Alist挂载）。",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    # 公用功能说明
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VDivider",
                                        "props": {"style": "margin: 20px 0;"},
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
                                        "component": "VAlert",
                                        "props": {
                                            "type": "warning",
                                            "variant": "tonal",
                                            "text": "联动删除种子需安装插件[下载器助手]并打开监听源文件事件。清理刮削文件功能会删除相关的.nfo、.jpg等元数据文件，请谨慎开启。",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                ],
            }
        ], {
            "enabled": False,
            "notify": False,
            "delete_scrap_infos": False,
            "delete_torrents": False,
            "delete_history": False,
            "delayed_deletion": True,
            "delay_seconds": 30,
            "monitor_dirs": "",
            "exclude_dirs": "",
            "exclude_keywords": "",
            "custom_scrap_extensions": "",
            "monitor_strm_deletion": False,
            "strm_path_mappings": "",
        }

    def get_page(self) -> List[dict]:
        pass

    def stop_service(self):
        """
        退出插件
        """
        logger.debug("开始停止服务")

        # 首先停止文件监控，防止新的删除事件
        if self._observer:
            for observer in self._observer:
                try:
                    observer.stop()
                    observer.join()
                except Exception as e:
                    print(str(e))
                    logger.error(f"停止目录监控失败：{str(e)}")
        self._observer = []
        logger.debug("文件监控已停止")

        # 停止延迟删除定时器
        if self._deletion_timer:
            try:
                self._deletion_timer.cancel()
                self._deletion_timer = None
                logger.debug("延迟删除定时器已停止")
            except Exception as e:
                logger.error(f"停止延迟删除定时器失败：{str(e)}")

        # 处理剩余的延迟删除任务
        tasks_to_process = []
        with deletion_queue_lock:
            if self.deletion_queue:
                logger.info(f"处理剩余的 {len(self.deletion_queue)} 个延迟删除任务")
                tasks_to_process = [
                    task for task in self.deletion_queue if not task.processed
                ]
                self.deletion_queue.clear()

        # 在锁外处理任务，避免死锁
        for task in tasks_to_process:
            self._execute_delayed_deletion(task)

        logger.debug("服务停止完成")

    @staticmethod
    def _normalize_config_path(config_path: str) -> str:
        """规范化配置中的目录路径，保留不存在路径的可比较形式。"""
        return os.path.normcase(os.path.normpath(str(Path(config_path).expanduser())))

    @classmethod
    def _is_same_or_child_path(cls, path: Path, base_path: str) -> bool:
        """判断 path 是否等于 base_path 或位于 base_path 下，避免子串误匹配。"""
        if not base_path:
            return False
        normalized_path = cls._normalize_config_path(str(path))
        normalized_base = cls._normalize_config_path(base_path)
        try:
            return os.path.commonpath([normalized_path, normalized_base]) == normalized_base
        except ValueError:
            return False

    def __is_excluded(self, file_path: Path) -> bool:
        """
        是否排除目录
        """
        for exclude_dir in self.exclude_dirs.split("\n"):
            exclude_dir = exclude_dir.strip()
            if exclude_dir and self._is_same_or_child_path(file_path, exclude_dir):
                return True
        return False

    @staticmethod
    def _parse_custom_scrap_extensions(custom_extensions: str) -> List[str]:
        """
        解析用户自定义刮削文件后缀，支持换行、逗号和中文逗号分隔。
        """
        if not custom_extensions:
            return []
        extensions = []
        for item in custom_extensions.replace("，", ",").replace("\n", ",").split(","):
            extension = item.strip().lower()
            if not extension:
                continue
            if not extension.startswith(".") and not extension.startswith("-"):
                extension = f".{extension}"
            if extension not in extensions:
                extensions.append(extension)
        return extensions

    def _scrap_extensions(self) -> List[str]:
        """
        返回内置和用户自定义刮削文件后缀。
        """
        extensions = list(self.SCRAP_EXTENSIONS)
        for extension in self._custom_scrap_extensions:
            if extension not in extensions:
                extensions.append(extension)
        return extensions

    def _is_scrap_file(self, path: Path) -> bool:
        """
        判断文件是否属于可联动清理的刮削文件。
        """
        name = path.name.lower()
        return any(name.endswith(extension) for extension in self._scrap_extensions())

    def scrape_files_left(self, path):
        """
        检查path目录是否只包含刮削文件
        """
        # 检查path下是否有非刮削文件或非刮削目录
        for file in path.iterdir():
            if file.is_dir():
                if file.suffix.lower() not in self.SCRAP_DIR_SUFFIXES:
                    return False
                continue
            if not self._is_scrap_file(file):
                return False
        return True

    def delete_scrap_infos(self, path):
        """
        清理path相关的刮削文件
        """
        if not self._delete_scrap_infos:
            return
        # 文件所在目录已被删除则退出
        if not os.path.exists(path.parent):
            return
        try:
            if not self._is_scrap_file(path):
                # 清理与path相关的刮削文件
                name_prefix = path.stem
                for file in path.parent.iterdir():
                    if not file.name.startswith(name_prefix):
                        continue
                    if file.is_dir() and file.suffix.lower() in self.SCRAP_DIR_SUFFIXES:
                        shutil.rmtree(file)
                        logger.info(f"删除刮削目录：{file}")
                    elif self._is_scrap_file(file):
                        file.unlink()
                        logger.info(f"删除刮削文件：{file}")
        except Exception as e:
            logger.error(f"清理刮削文件发生错误：{str(e)}.")
        # 清理空目录
        self.delete_empty_folders(path)

    def delete_history(self, path):
        """
        清理path相关的转移记录
        """
        if not self._delete_history:
            return
        # 查找转移记录
        transfer_history = self._transferhistory.get_by_src(path)
        if transfer_history:
            # 删除转移记录
            self._transferhistory.delete(transfer_history.id)
            logger.info(f"删除转移记录：{transfer_history.id}")

    def delete_empty_folders(self, path):
        """
        从指定路径开始，逐级向上层目录检测并删除空目录，直到遇到非空目录或到达指定监控目录为止
        """
        # logger.info(f"清理空目录: {path}")
        while True:
            parent_path = path.parent
            if self.__is_excluded(parent_path):
                break
            # parent_path如已被删除则退出检查
            if not os.path.exists(parent_path):
                break
            # 如果当前路径等于监控目录之一，停止向上检查
            if parent_path in self.monitor_dirs.split("\n"):
                break

            # 若目录下只剩刮削文件，则清空文件夹
            try:
                if self.scrape_files_left(parent_path):
                    # 清除目录下所有文件
                    for file in parent_path.iterdir():
                        if file.is_dir():
                            shutil.rmtree(file)
                            logger.info(f"删除刮削目录：{file}")
                        else:
                            file.unlink()
                            logger.info(f"删除刮削文件：{file}")
            except Exception as e:
                logger.error(f"清理刮削文件发生错误：{str(e)}.")

            try:
                if not os.listdir(parent_path):
                    os.rmdir(parent_path)
                    logger.info(f"清理空目录：{parent_path}")
                    if self._notify:
                        self.post_message(
                            mtype=NotificationType.SiteMessage,
                            title="📁 目录清理",
                            text=f"🗑️ 清理空目录：{parent_path}",
                        )
                else:
                    break
            except Exception as e:
                logger.error(f"清理空目录发生错误：{str(e)}")

            # 更新路径为父目录，准备下一轮检查
            path = parent_path

    def _unlink_tracked_file(self, file: Path, state_key: str, action: str) -> bool:
        """
        删除 file_state 中记录的硬链接文件。

        监控事件可能先后到达：用户手动删除源文件后，又在插件处理前手动删除了
        对应硬链接。此时 file_state 里仍可能保存着已不存在的路径，直接 unlink
        会抛出 FileNotFoundError 并中断当前批次清理。这里把这种过期状态视为
        已经被外部清理，移除记录后继续处理其它文件，避免删除队列/监控流程被卡住。
        """
        if self.__is_excluded(file):
            logger.debug(f"文件 {file} 在不删除目录中，跳过")
            return False

        try:
            logger.info(f"{action}硬链接文件：{state_key}")
            file.unlink()
        except FileNotFoundError:
            logger.warning(f"硬链接文件已不存在，清理过期监控记录：{state_key}")
            self.file_state.pop(state_key, None)
            return False
        except OSError as e:
            logger.error(f"删除硬链接文件失败：{state_key} - {e}")
            return False

        self.file_state.pop(state_key, None)
        return True

    def _execute_delayed_deletion(self, task: DeletionTask):
        """
        执行延迟删除任务
        """
        try:
            logger.debug(f"开始执行延迟删除任务: {task.file_path}")

            # 验证原文件是否仍然被删除（未被重新创建）
            if task.file_path.exists():
                logger.info(f"文件 {task.file_path} 已被重新创建，跳过删除操作")
                return

            # 检查是否有相同inode的新文件（重新硬链接的情况）
            with state_lock:
                for path, file_info in self.file_state.items():
                    if file_info.inode == task.deleted_inode and path != str(
                        task.file_path
                    ):
                        # 检查文件是否在删除任务创建之后被添加到监控中
                        if file_info.add_time > task.timestamp:
                            logger.info(
                                f"检测到相同inode的新文件 {path}，添加时间 {file_info.add_time} 晚于删除时间 {task.timestamp}，可能是重新硬链接，跳过删除操作"
                            )
                            return

            # 延迟执行所有删除相关操作
            logger.debug(
                f"文件 {task.file_path} 确认被删除且无重新硬链接，开始执行延迟删除操作"
            )

            # 清理刮削文件
            self.delete_scrap_infos(task.file_path)
            if self._delete_torrents:
                # 只有非刮削文件才发送 DownloadFileDeleted 事件
                if not self._is_scrap_file(task.file_path):
                    eventmanager.send_event(
                        EventType.DownloadFileDeleted, {"src": str(task.file_path)}
                    )
            # 删除转移记录
            self.delete_history(str(task.file_path))

            # 查找并删除硬链接文件
            deleted_files = []

            with state_lock:
                for path, file_info in self.file_state.copy().items():
                    if file_info.inode == task.deleted_inode:
                        file = Path(path)
                        if not self._unlink_tracked_file(file, path, "延迟删除"):
                            continue
                        deleted_files.append(path)

                        # 清理硬链接文件相关的刮削文件
                        self.delete_scrap_infos(file)
                        if self._delete_torrents:
                            # 只有非刮削文件才发送 DownloadFileDeleted 事件
                            if not self._is_scrap_file(file):
                                eventmanager.send_event(
                                    EventType.DownloadFileDeleted, {"src": str(file)}
                                )
                        # 删除硬链接文件的转移记录
                        self.delete_history(str(file))

            # 发送通知（在锁外执行）
            if self._notify and deleted_files:
                file_count = len(deleted_files)

                # 构建通知内容
                notification_parts = [f"🗂️ 源文件：{task.file_path}"]

                if file_count == 1:
                    notification_parts.append(f"🔗 硬链接：{deleted_files[0]}")
                else:
                    notification_parts.append(f"🔗 删除了 {file_count} 个硬链接文件")

                # 添加其他操作记录
                if self._delete_history:
                    notification_parts.append("📝 已清理转移记录")
                if self._delete_torrents:
                    notification_parts.append("🌱 已联动删除种子")
                if self._delete_scrap_infos:
                    notification_parts.append("🖼️ 已清理刮削文件")

                self.post_message(
                    mtype=NotificationType.SiteMessage,
                    title="🧹 媒体文件清理",
                    text=f"⏰ 延迟删除完成\n\n" + "\n".join(notification_parts),
                )

        except Exception as e:
            logger.error(f"执行延迟删除任务失败：{str(e)} - {traceback.format_exc()}")
        finally:
            task.processed = True

    def _process_deletion_queue(self):
        """
        处理延迟删除队列
        """
        try:
            current_time = datetime.now()
            tasks_to_process = []

            # 先获取需要处理的任务，避免在处理任务时持有锁
            with deletion_queue_lock:
                # 找到需要处理的任务
                for task in self.deletion_queue:
                    if not task.processed:
                        elapsed = (current_time - task.timestamp).total_seconds()
                        if elapsed >= self._delay_seconds:
                            tasks_to_process.append(task)

                if tasks_to_process:
                    logger.debug(
                        f"处理延迟删除队列，待处理任务数: {len(tasks_to_process)}"
                    )

            # 在锁外处理任务，避免死锁
            processed_count = 0
            for task in tasks_to_process:
                try:
                    self._execute_delayed_deletion(task)
                    processed_count += 1
                except Exception as e:
                    logger.error(f"处理延迟删除任务失败：{task.file_path} - {e}")

            # 重新获取锁进行清理和定时器管理
            with deletion_queue_lock:
                # 清理已处理的任务
                original_count = len(self.deletion_queue)
                self.deletion_queue = [
                    task for task in self.deletion_queue if not task.processed
                ]
                cleaned_count = original_count - len(self.deletion_queue)

                if cleaned_count > 0:
                    logger.debug(f"清理了 {cleaned_count} 个已处理的任务")

                # 如果还有未处理的任务，重新启动定时器
                if self.deletion_queue:
                    # 计算下一个任务的等待时间
                    next_task_time = min(
                        (task.timestamp.timestamp() + self._delay_seconds)
                        for task in self.deletion_queue
                        if not task.processed
                    )
                    wait_time = max(1, next_task_time - current_time.timestamp())

                    logger.debug(
                        f"还有 {len(self.deletion_queue)} 个任务待处理，"
                        f"{wait_time:.1f} 秒后重新检查"
                    )
                    self._start_deletion_timer(wait_time)
                else:
                    self._deletion_timer = None
                    logger.debug("延迟删除队列已清空，定时器停止")

        except Exception as e:
            logger.error(f"处理延迟删除队列失败：{str(e)} - {traceback.format_exc()}")
            # 确保定时器状态正确
            with deletion_queue_lock:
                self._deletion_timer = None

    def _start_deletion_timer(self, delay_time: float = None):
        """
        启动延迟删除定时器
        注意：此方法假设调用前已检查没有运行中的定时器
        """
        if delay_time is None:
            delay_time = self._delay_seconds

        self._deletion_timer = threading.Timer(delay_time, self._process_deletion_queue)
        self._deletion_timer.daemon = True
        self._deletion_timer.start()

    def handle_deleted(self, file_path: Path):
        """
        处理删除事件
        """
        logger.debug(f"处理删除事件: {file_path}")

        # 删除的文件对应的监控信息
        with state_lock:
            # 删除的文件信息
            file_info = self.file_state.get(str(file_path))
            if not file_info:
                logger.debug(f"文件 {file_path} 未在监控列表中，跳过处理")
                return
            else:
                deleted_inode = file_info.inode
                self.file_state.pop(str(file_path))

            # 根据配置选择立即删除或延迟删除
            if self._delayed_deletion:
                # 延迟删除模式 - 所有删除操作都延迟执行
                logger.info(
                    f"文件 {file_path.name} 加入延迟删除队列，延迟 {self._delay_seconds} 秒"
                )
                task = DeletionTask(
                    file_path=file_path,
                    deleted_inode=deleted_inode,
                    timestamp=datetime.now(),
                )

                with deletion_queue_lock:
                    self.deletion_queue.append(task)
                    # 只有在没有定时器运行时才启动新的定时器
                    # 避免频繁的删除事件重置定时器导致任务永远不被处理
                    if not self._deletion_timer:
                        self._start_deletion_timer()
                        logger.debug("启动延迟删除定时器")
                    else:
                        logger.debug("延迟删除定时器已在运行，任务已加入队列")
            else:
                # 立即删除模式（原有逻辑）
                deleted_files = []

                # 清理刮削文件
                self.delete_scrap_infos(file_path)
                if self._delete_torrents:
                    # 只有非刮削文件才发送 DownloadFileDeleted 事件
                    if not self._is_scrap_file(file_path):
                        eventmanager.send_event(
                            EventType.DownloadFileDeleted, {"src": str(file_path)}
                        )
                # 删除转移记录
                self.delete_history(str(file_path))

                try:
                    # 在file_state中查找与deleted_inode有相同inode的文件并删除
                    for path, file_info in self.file_state.copy().items():
                        if file_info.inode == deleted_inode:
                            file = Path(path)
                            if not self._unlink_tracked_file(file, path, "立即删除"):
                                continue
                            deleted_files.append(path)

                            # 清理刮削文件
                            self.delete_scrap_infos(file)
                            if self._delete_torrents:
                                # 只有非刮削文件才发送 DownloadFileDeleted 事件
                                if not self._is_scrap_file(file):
                                    eventmanager.send_event(
                                        EventType.DownloadFileDeleted,
                                        {"src": str(file)},
                                    )
                            # 删除转移记录
                            self.delete_history(str(file))

                    # 发送通知
                    if self._notify and deleted_files:
                        file_count = len(deleted_files)

                        # 构建通知内容
                        notification_parts = [f"🗂️ 源文件：{file_path}"]

                        if file_count == 1:
                            notification_parts.append(f"🔗 硬链接：{deleted_files[0]}")
                        else:
                            notification_parts.append(
                                f"🔗 删除了 {file_count} 个硬链接文件"
                            )

                        # 添加其他操作记录
                        if self._delete_history:
                            notification_parts.append("📝 已清理转移记录")
                        if self._delete_torrents:
                            notification_parts.append("🌱 已联动删除种子")
                        if self._delete_scrap_infos:
                            notification_parts.append("🖼️ 已清理刮削文件")

                        self.post_message(
                            mtype=NotificationType.SiteMessage,
                            title="🧹 媒体文件清理",
                            text=f"⚡ 立即删除完成\n\n" + "\n".join(notification_parts),
                        )

                except Exception as e:
                    logger.error(
                        "删除硬链接文件发生错误：%s - %s"
                        % (str(e), traceback.format_exc())
                    )

    def _parse_strm_path_mappings(self) -> Dict[str, Tuple[str, str]]:
        """
        解析 strm 路径映射配置
        返回格式: {strm_path: (storage_type, storage_path)}
        """
        mappings = {}
        if not self.strm_path_mappings:
            return mappings

        for line in self.strm_path_mappings.split("\n"):
            line = line.strip()
            if not line or ":" not in line:
                continue
            try:
                # 支持格式: strm_path:storage_type:storage_path 或 strm_path:storage_path (默认local)
                parts = line.split(":", 2)
                if len(parts) == 2:
                    # 默认使用 local 存储
                    strm_path, storage_path = parts
                    storage_type = "local"
                elif len(parts) == 3:
                    # 指定存储类型
                    strm_path, storage_type, storage_path = parts
                else:
                    logger.warning(f"无效的 strm 路径映射配置: {line}")
                    continue

                mappings[strm_path.strip()] = (
                    storage_type.strip(),
                    storage_path.strip(),
                )
            except ValueError:
                logger.warning(f"无效的 strm 路径映射配置: {line}")

        return mappings

    def _get_storage_path_from_strm(self, strm_file_path: Path) -> Tuple[str, str]:
        """
        根据 strm 文件路径获取对应的网盘存储路径
        返回 (storage_type, storage_path) 或 (None, None)
        """
        mappings = self._parse_strm_path_mappings()
        strm_path_str = str(strm_file_path)

        for strm_prefix, (storage_type, storage_prefix) in mappings.items():
            if strm_path_str.startswith(strm_prefix):
                # 计算相对路径
                relative_path = strm_path_str[len(strm_prefix) :].lstrip("/")
                # 构建网盘路径，去掉 .strm 后缀
                storage_file_path = storage_prefix.rstrip("/") + "/" + relative_path
                if storage_file_path.endswith(".strm"):
                    storage_file_path = storage_file_path[:-5]  # 去掉 .strm 后缀

                return storage_type, storage_file_path

        return None, None

    def _find_storage_media_file(
        self, storage_type: str, base_path: str
    ) -> schemas.FileItem:
        """
        在网盘中查找以指定路径为前缀的视频文件
        """
        from app.core.config import settings

        # 获取父目录
        parent_path = str(Path(base_path).parent)
        parent_item = schemas.FileItem(
            storage=storage_type,
            path=parent_path if parent_path.endswith("/") else parent_path + "/",
            type="dir",
        )

        # 检查父目录是否存在
        if not self._storagechain.exists(parent_item):
            logger.debug(f"父目录不存在: [{storage_type}] {parent_path}")
            return None

        # 列出父目录中的文件
        files = self._storagechain.list_files(parent_item, recursion=False)
        if not files:
            logger.debug(f"父目录为空: [{storage_type}] {parent_path}")
            return None

        # 查找以 base_path 为前缀的视频文件
        base_name = Path(base_path).name
        for file_item in files:
            if file_item.type == "file" and file_item.name.startswith(base_name):
                # 检查是否为视频文件
                if (
                    file_item.extension
                    and f".{file_item.extension.lower()}" in settings.RMT_MEDIAEXT
                ):
                    logger.info(
                        f"找到匹配的视频文件: [{storage_type}] {file_item.path}"
                    )
                    return file_item

        logger.debug(f"未找到匹配的视频文件: [{storage_type}] {base_path}")
        return None

    def _delete_storage_scrap_files(
        self, storage_type: str, storage_file_item: schemas.FileItem
    ) -> int:
        """
        删除网盘中的刮削文件
        返回删除的文件数量
        """
        if not self._delete_scrap_infos:
            return 0

        deleted_count = 0
        try:
            # 获取父目录
            parent_path = str(Path(storage_file_item.path).parent)
            parent_item = schemas.FileItem(
                storage=storage_type,
                path=parent_path if parent_path.endswith("/") else parent_path + "/",
                type="dir",
            )

            # 检查父目录是否存在
            if not self._storagechain.exists(parent_item):
                logger.debug(f"网盘父目录不存在: [{storage_type}] {parent_path}")
                return 0

            # 列出父目录中的文件
            files = self._storagechain.list_files(parent_item, recursion=False)
            if not files:
                logger.debug(f"网盘父目录为空: [{storage_type}] {parent_path}")
                return 0

            # 获取视频文件的基础名称（不含扩展名）
            base_name = Path(storage_file_item.path).stem

            # 查找并删除刮削文件
            for file_item in files:
                if file_item.type == "file":
                    file_stem = Path(file_item.name).stem
                    file_ext = Path(file_item.name).suffix.lower()

                    # 检查是否为相关的刮削文件
                    if (
                        file_stem.startswith(base_name)
                        and self._is_scrap_file(Path(file_item.name))
                    ) or (
                        file_item.name.lower()
                        in [
                            "poster.jpg",
                            "backdrop.jpg",
                            "fanart.jpg",
                            "banner.jpg",
                            "logo.png",
                        ]
                    ):

                        # 删除刮削文件
                        if self._storagechain.delete_file(file_item):
                            logger.info(
                                f"删除网盘刮削文件: [{storage_type}] {file_item.path}"
                            )
                            deleted_count += 1
                        else:
                            logger.warning(
                                f"删除网盘刮削文件失败: [{storage_type}] {file_item.path}"
                            )

            logger.info(
                f"网盘刮削文件清理完成: [{storage_type}] {parent_path}，删除了 {deleted_count} 个文件"
            )

        except Exception as e:
            logger.error(
                f"清理网盘刮削文件失败: [{storage_type}] {storage_file_item.path} - {str(e)}"
            )

        return deleted_count

    def _delete_storage_empty_folders(
        self, storage_type: str, storage_file_item: schemas.FileItem
    ) -> int:
        """
        删除网盘中的空目录
        返回删除的目录数量
        """
        deleted_count = 0
        try:
            # 获取父目录
            parent_path = str(Path(storage_file_item.path).parent)
            current_path = parent_path

            # 逐级向上检查并删除空目录
            while current_path and current_path != "/" and current_path != "\\":
                # 获取当前目录的正确 FileItem（包含 fileid）
                current_item = self._get_storage_dir_item(storage_type, current_path)
                if not current_item:
                    logger.debug(f"网盘目录不存在: [{storage_type}] {current_path}")
                    break

                # 列出目录中的文件
                files = self._storagechain.list_files(current_item, recursion=False)

                if not files:
                    # 目录为空，删除它
                    if self._storagechain.delete_file(current_item):
                        logger.info(f"删除网盘空目录: [{storage_type}] {current_path}")
                        deleted_count += 1

                        # 继续检查上级目录
                        current_path = str(Path(current_path).parent)
                        if current_path == current_path.replace(
                            str(Path(current_path).name), ""
                        ).rstrip("/\\"):
                            # 已到达根目录
                            break
                    else:
                        logger.warning(
                            f"删除网盘空目录失败: [{storage_type}] {current_path}"
                        )
                        break
                else:
                    # 目录不为空，检查是否只包含刮削文件
                    only_scrap_files = True
                    for file_item in files:
                        if file_item.type == "file":
                            if not self._is_scrap_file(Path(file_item.name)):
                                only_scrap_files = False
                                break
                        else:
                            # 包含子目录，不删除
                            only_scrap_files = False
                            break

                    if only_scrap_files and files:
                        # 目录只包含刮削文件，删除所有文件
                        for file_item in files:
                            if file_item.type == "file":
                                if self._storagechain.delete_file(file_item):
                                    logger.info(
                                        f"删除网盘刮削文件: [{storage_type}] {file_item.path}"
                                    )
                                else:
                                    logger.warning(
                                        f"删除网盘刮削文件失败: [{storage_type}] {file_item.path}"
                                    )

                        # 重新获取目录信息并检查是否为空
                        current_item = self._get_storage_dir_item(
                            storage_type, current_path
                        )
                        if current_item:
                            files = self._storagechain.list_files(
                                current_item, recursion=False
                            )
                            if not files:
                                # 现在目录为空，删除它
                                if self._storagechain.delete_file(current_item):
                                    logger.info(
                                        f"删除网盘空目录: [{storage_type}] {current_path}"
                                    )
                                    deleted_count += 1

                                    # 继续检查上级目录
                                    current_path = str(Path(current_path).parent)
                                    if current_path == current_path.replace(
                                        str(Path(current_path).name), ""
                                    ).rstrip("/\\"):
                                        break
                                else:
                                    break
                            else:
                                break
                        else:
                            break
                    else:
                        # 目录包含非刮削文件或子目录，停止向上检查
                        break

            if deleted_count > 0:
                logger.info(
                    f"网盘空目录清理完成: [{storage_type}] 删除了 {deleted_count} 个目录"
                )

        except Exception as e:
            logger.error(
                f"清理网盘空目录失败: [{storage_type}] {storage_file_item.path} - {str(e)}"
            )

        return deleted_count

    def _get_storage_dir_item(
        self, storage_type: str, dir_path: str
    ) -> schemas.FileItem:
        """
        获取网盘目录的正确 FileItem（包含 fileid）
        """
        try:
            # 获取父目录
            parent_path = str(Path(dir_path).parent)
            if parent_path == dir_path:
                # 已经是根目录
                return None

            parent_item = schemas.FileItem(
                storage=storage_type,
                path=parent_path if parent_path.endswith("/") else parent_path + "/",
                type="dir",
            )

            # 检查父目录是否存在
            if not self._storagechain.exists(parent_item):
                return None

            # 列出父目录中的文件，查找目标目录
            files = self._storagechain.list_files(parent_item, recursion=False)
            if not files:
                return None

            # 查找目标目录
            target_name = Path(dir_path).name
            for file_item in files:
                if file_item.type == "dir" and file_item.name == target_name:
                    return file_item

            return None

        except Exception as e:
            logger.debug(
                f"获取网盘目录信息失败: [{storage_type}] {dir_path} - {str(e)}"
            )
            return None

    def handle_strm_deleted(self, strm_file_path: Path):
        """
        处理 strm 文件删除事件
        """
        logger.info(f"处理 strm 文件删除: {strm_file_path}")

        try:
            # 获取对应的网盘文件路径
            storage_type, storage_path = self._get_storage_path_from_strm(
                strm_file_path
            )

            if not storage_type or not storage_path:
                logger.warning(
                    f"无法找到 strm 文件 {strm_file_path} 对应的网盘路径映射"
                )
                return

            # 查找网盘中的视频文件
            storage_file_item = self._find_storage_media_file(
                storage_type, storage_path
            )

            if not storage_file_item:
                logger.info(
                    f"网盘中未找到对应的视频文件: [{storage_type}] {storage_path}"
                )
                return

            logger.info(f"准备删除网盘文件: [{storage_type}] {storage_file_item.path}")

            # 删除网盘文件
            if self._storagechain.delete_file(storage_file_item):
                logger.info(
                    f"成功删除网盘文件: [{storage_type}] {storage_file_item.path}"
                )

                # 清理本地 strm 目录的刮削文件
                local_scrap_deleted = 0
                if self._delete_scrap_infos:
                    self.delete_scrap_infos(strm_file_path)
                    local_scrap_deleted = 1  # 简化计数，实际可能删除多个

                # 清理网盘上的刮削文件
                storage_scrap_deleted = 0
                storage_dirs_deleted = 0
                if self._delete_scrap_infos:
                    storage_scrap_deleted = self._delete_storage_scrap_files(
                        storage_type, storage_file_item
                    )
                    # 清理网盘空目录
                    storage_dirs_deleted = self._delete_storage_empty_folders(
                        storage_type, storage_file_item
                    )

                # 删除转移记录（通过网盘文件路径查询）
                history_deleted = False
                if self._delete_history:
                    history_deleted = self.delete_history_by_dest(
                        storage_file_item.path
                    )

                # 发送通知
                if self._notify:
                    # 构建通知内容
                    notification_parts = [f"🗂️ STRM 文件：{strm_file_path}"]
                    notification_parts.append(
                        f"🗑️ 已删除网盘文件：[{storage_type}] {storage_file_item.path}"
                    )

                    # 添加其他操作记录
                    if self._delete_history:
                        if history_deleted:
                            notification_parts.append("📝 已清理转移记录")
                        else:
                            notification_parts.append("📝 无转移记录")
                    if self._delete_scrap_infos:
                        if local_scrap_deleted > 0 and storage_scrap_deleted > 0:
                            scrap_msg = f"🖼️ 已清理刮削文件（本地+网盘 {storage_scrap_deleted} 个）"
                        elif local_scrap_deleted > 0:
                            scrap_msg = "🖼️ 已清理本地刮削文件"
                        elif storage_scrap_deleted > 0:
                            scrap_msg = (
                                f"🖼️ 已清理网盘刮削文件（{storage_scrap_deleted} 个）"
                            )
                        else:
                            scrap_msg = "🖼️ 无刮削文件需要清理"

                        # 添加空目录清理信息
                        if storage_dirs_deleted > 0:
                            scrap_msg += f"，清理空目录 {storage_dirs_deleted} 个"

                        notification_parts.append(scrap_msg)

                    self.post_message(
                        mtype=NotificationType.SiteMessage,
                        title="🧹 媒体文件清理",
                        text=f"✅ 清理完成\n\n" + "\n".join(notification_parts),
                    )
            else:
                logger.error(
                    f"删除网盘文件失败: [{storage_type}] {storage_file_item.path}"
                )

        except Exception as e:
            logger.error(
                f"处理 strm 文件删除失败: {strm_file_path} - {str(e)} - {traceback.format_exc()}"
            )

    def delete_history_by_dest(self, dest_path: str) -> bool:
        """
        通过目标路径删除转移记录
        返回是否成功删除了转移记录
        """
        if not self._delete_history:
            return False
        # 查找转移记录
        transfer_history = self._transferhistory.get_by_dest(dest_path)
        if transfer_history:
            # 删除转移记录
            self._transferhistory.delete(transfer_history.id)
            logger.info(f"删除转移记录：{transfer_history.id} - {dest_path}")
            return True
        else:
            logger.debug(f"未找到转移记录：{dest_path}")
            return False
