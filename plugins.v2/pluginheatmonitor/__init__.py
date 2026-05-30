"""
插件热度监控插件
监控其他插件的下载量热度，当达到设定的里程碑时发送通知
"""
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

from apscheduler.triggers.cron import CronTrigger
from app.plugins import _PluginBase
from app.core.plugin import PluginManager
from app.helper.server import MoviePilotServerHelper
from app.schemas import NotificationType
from app.schemas.types import EventType
from app.core.event import eventmanager, Event
from app.log import logger

# 导入MCP插件助手
try:
    from app.plugins.mcpserver.dev.mcp_dev import (
        mcp_tool,
        mcp_prompt,
        MCPDecoratorMixin
    )
    MCP_DEV_AVAILABLE = True
except ImportError as e:
    logger.warning(f"MCPServer插件不可用，MCP功能将被禁用。错误详情: {str(e)}")
    MCP_DEV_AVAILABLE = False

    # 定义空的装饰器，避免语法错误
    def mcp_tool(*args, **kwargs):
        """空的MCP工具装饰器，当MCP不可用时使用"""
        def decorator(func):
            return func
        return decorator

    def mcp_prompt(*args, **kwargs):
        """空的MCP提示装饰器，当MCP不可用时使用"""
        def decorator(func):
            return func
        return decorator

    # 定义空的Mixin类
    class MCPDecoratorMixin:
        """空的MCP装饰器混入类，当MCP不可用时使用"""
        pass


class PluginHeatMonitor(_PluginBase, MCPDecoratorMixin):
    """插件热度监控"""

    plugin_name = "插件热度监控"
    plugin_desc = "监控已安装的下载量热度，支持日历热力图可视化"
    plugin_icon = "https://raw.githubusercontent.com/DzAvril/MoviePilot-Plugins/main/icons/heatmonitor.png"
    plugin_version = "1.8.2"
    plugin_author = "DzAvril"
    author_url = "https://github.com/DzAvril"
    plugin_config_prefix = "pluginheatmonitor_"
    plugin_order = 20
    auth_level = 1
    # Vue组件支持
    plugin_component = True

    # 常量
    DEFAULT_INCREMENT = 100
    DEFAULT_CRON = "0 */1 * * *"

    # 私有属性
    _enabled = False
    _cron = DEFAULT_CRON
    _monitored_plugins = {}  # 监控的插件配置
    _enable_notification = True  # 是否启用通知
    _download_increment = DEFAULT_INCREMENT
    _run_once = False  # 立即运行一次
    _enable_mcp = True  # 是否启用MCP工具

    # 缓存
    _plugin_cache = None
    _plugin_cache_time = 0
    _cache_ttl = 300  # 5分钟缓存
    
    def init_plugin(self, config: dict = None):
        """初始化插件"""
        # 注销MCP功能
        self.stop_service()

        if not config:
            return

        # 加载基础配置
        self._load_basic_config(config)

        # 处理插件监控配置
        if "selected_plugins" in config:
            self._update_monitored_plugins(config)

        # 启动或停止服务
        self._setup_service()

        # 初始化MCP功能
        if self._enable_mcp and MCP_DEV_AVAILABLE:
            try:
                logger.info("初始化插件热度监控MCP功能")
                self.init_mcp_decorators()
            except Exception as e:
                logger.error(f"MCP初始化失败: {str(e)}")
        elif not self._enable_mcp:
            logger.info("MCP功能已禁用")

    def _load_basic_config(self, config: dict):
        """加载基础配置"""
        self._enabled = config.get("enabled", False)
        self._cron = config.get("cron", self.DEFAULT_CRON)
        self._monitored_plugins = config.get("monitored_plugins", {})
        self._enable_notification = config.get("enable_notification", True)
        self._run_once = config.get("run_once", False)
        self._download_increment = config.get("download_increment", self.DEFAULT_INCREMENT)
        self._enable_mcp = config.get("enable_mcp", True)

    def _update_monitored_plugins(self, config: dict):
        """更新监控插件配置"""
        selected_plugins = config.get("selected_plugins", [])

        try:
            # 解析下载增量
            increment_value = self._parse_increment_value(self._download_increment)

            if increment_value > 0:
                # 清理移除的插件数据
                self._cleanup_removed_plugins(selected_plugins)

                # 重建监控配置
                self._rebuild_monitored_plugins(selected_plugins, increment_value)

                logger.info(f"成功更新监控列表：当前监控 {len(selected_plugins)} 个插件")
        except ValueError as e:
            logger.error(f"解析下载增量设置失败：{str(e)}")

    def _parse_increment_value(self, download_increment) -> int:
        """解析下载增量值"""
        if download_increment:
            return int(download_increment)

        # 从现有配置获取或使用默认值
        existing_increments = [
            cfg.get("download_increment", self.DEFAULT_INCREMENT)
            for cfg in self._monitored_plugins.values()
        ]
        return existing_increments[0] if existing_increments else self.DEFAULT_INCREMENT

    def _cleanup_removed_plugins(self, selected_plugins: List[str]):
        """更新监控插件配置时的清理（保留历史数据）"""
        old_plugins = set(self._monitored_plugins.keys())
        new_plugins = set(selected_plugins)
        removed_plugins = old_plugins - new_plugins

        if removed_plugins:
            logger.info(f"插件 {', '.join(removed_plugins)} 已从监控列表中移除，但历史数据已保留")

    def _rebuild_monitored_plugins(self, selected_plugins: List[str], increment_value: int):
        """重建监控插件配置"""
        self._monitored_plugins = {}
        for plugin_id in selected_plugins:
            self._monitored_plugins[plugin_id] = {
                "download_increment": increment_value
            }
            logger.info(f"添加插件监控：{plugin_id}，下载增量：{increment_value}")

    def _setup_service(self):
        """设置服务状态"""
        self.stop_service()

        if self._enabled:
            self._log_service_status()
            if self._run_once:
                self._execute_immediate_check()
        else:
            logger.info("插件热度监控已禁用")

    def _log_service_status(self):
        """记录服务状态日志"""
        logger.info("插件热度监控已启用")
        logger.info(f"定时任务已配置，Cron表达式：{self._cron}")
        logger.info(f"当前监控 {len(self._monitored_plugins)} 个插件")
        logger.info(f"通知功能：{'启用' if self._enable_notification else '禁用'}")

    def _execute_immediate_check(self):
        """执行立即检查"""
        logger.info("执行立即运行一次...")

        def run_check():
            try:
                time.sleep(0.1)  # 确保init_plugin完成
                self._check_plugin_heat()
                logger.info("立即运行完成")
            except Exception as e:
                logger.error(f"立即运行出错：{str(e)}", exc_info=True)

        thread = threading.Thread(target=run_check, daemon=True)
        thread.start()

        # 重置立即运行标志
        self._run_once = False
        self._update_config_after_immediate_run()

    def _update_config_after_immediate_run(self):
        """立即运行后更新配置"""
        # 获取当前监控的插件ID列表
        selected_plugins = list(self._monitored_plugins.keys())

        # 获取下载增量值（从第一个监控插件的配置中获取）
        download_increment = self.DEFAULT_INCREMENT
        if self._monitored_plugins:
            first_config = next(iter(self._monitored_plugins.values()))
            download_increment = first_config.get("download_increment", self.DEFAULT_INCREMENT)

        self.update_config({
            "run_once": self._run_once,
            "enabled": self._enabled,
            "cron": self._cron,
            "monitored_plugins": self._monitored_plugins,
            "selected_plugins": selected_plugins,
            "enable_notification": self._enable_notification,
            "download_increment": download_increment,
        })

    def _get_cached_plugins(self) -> List:
        """获取缓存的插件列表"""
        current_time = time.time()
        if (self._plugin_cache is None or
            current_time - self._plugin_cache_time > self._cache_ttl):
            plugin_manager = PluginManager()
            self._plugin_cache = plugin_manager.get_local_plugins()
            self._plugin_cache_time = current_time
        return self._plugin_cache

    def _get_plugin_info(self, plugin_id: str) -> Tuple[str, str]:
        """获取插件名称和图标"""
        plugins = self._get_cached_plugins()

        for plugin in plugins:
            if plugin.id == plugin_id:
                name = plugin.plugin_name or plugin_id
                icon = self._get_plugin_icon_url(plugin)
                return name, icon

        return plugin_id, "mdi-puzzle"

    def _get_plugin_desc(self, plugin_id: str) -> str:
        """获取插件描述"""
        plugins = self._get_cached_plugins()

        for plugin in plugins:
            if plugin.id == plugin_id:
                return plugin.plugin_desc or ""

        return ""

    def _get_plugin_icon_url(self, plugin) -> str:
        """获取插件图标URL"""
        if not plugin.plugin_icon:
            return "mdi-puzzle"

        if plugin.plugin_icon.startswith('http'):
            return plugin.plugin_icon
        else:
            return f"./plugin_icon/{plugin.plugin_icon}"

    def get_state(self) -> bool:
        """获取插件状态"""
        return self._enabled
    
    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件服务
        """
        if self._enabled and self._cron:
            return [
                {
                    "id": "PluginHeatMonitor",
                    "name": "插件热度监控",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self._check_plugin_heat,
                    "kwargs": {}
                }
            ]
        return []

    def stop_service(self):
        """停止插件服务"""
        pass
    
    def _check_plugin_heat(self):
        """检查插件热度"""
        if not self._enabled:
            logger.debug("插件热度监控未启用，跳过检查")
            return

        if not self._monitored_plugins:
            logger.debug("没有配置监控插件，跳过检查")
            return

        try:
            logger.info(f"🔍 开始检查插件热度... 监控插件数量：{len(self._monitored_plugins)}")

            # 获取插件统计数据
            statistics = MoviePilotServerHelper.get_plugin_statistic()

            if not statistics:
                logger.warning("⚠️ 无法获取插件统计数据")
                return

            logger.debug(f"获取到统计数据，包含 {len(statistics)} 个插件")

            # 检查每个监控的插件
            notifications_sent = 0
            for plugin_id, config in self._monitored_plugins.items():
                logger.debug(f"检查插件：{plugin_id}")

                # 检查插件是否在统计数据中
                if plugin_id not in statistics:
                    logger.warning(f"⚠️ 插件 {plugin_id} 不在统计数据中，可能未安装或未被使用")
                    continue

                # 检查单个插件
                result = self._check_single_plugin(plugin_id, config, statistics)
                if result:
                    notifications_sent += 1

            if notifications_sent > 0:
                logger.info(f"✅ 插件热度检查完成，发送了 {notifications_sent} 个通知")
            else:
                logger.info("✅ 插件热度检查完成，无需发送通知")

        except Exception as e:
            logger.error(f"❌ 检查插件热度时出错：{str(e)}", exc_info=True)
    
    def _check_single_plugin(self, plugin_id: str, config: dict, statistics: dict) -> bool:
        """检查单个插件的热度，返回是否发送了通知"""
        try:
            # 获取当前下载量
            current_downloads = statistics.get(plugin_id, 0)

            # 获取历史数据
            history_key = f"history_{plugin_id}"
            history_data = self.get_data(history_key) or {}

            # 获取配置
            download_increment = config.get("download_increment", 100)
            last_notification_downloads = history_data.get("last_notification_downloads", current_downloads)
            last_notification_time = history_data.get("last_notification_time", time.time())

            logger.debug(f"检查插件 {plugin_id}：当前下载量={current_downloads}, 上次通知下载量={last_notification_downloads}, 增量阈值={download_increment}")

            # 如果是第一次检查，初始化数据
            if "last_downloads" not in history_data:
                # 初始化数据，但不记录今天的下载量为增量
                # 因为这是第一次检查，我们不知道今天实际增加了多少
                history_data.update({
                    "last_downloads": current_downloads,
                    "last_notification_downloads": current_downloads,
                    "last_notification_time": time.time(),
                    "last_check_time": time.time(),
                    "daily_downloads": {}  # 初始化为空，等下次检查时再记录增量
                })
                self.save_data(history_key, history_data)
                logger.info(f"初始化插件 {plugin_id} 监控数据，当前下载量：{current_downloads}，等待下次检查记录增量")
                return False  # 初始化时不算发送通知

            # 检查并迁移旧版本的错误数据
            self._migrate_legacy_data(plugin_id, history_data, current_downloads)

            # 更新每日下载量记录（记录增量而不是总量）
            self._update_daily_downloads(history_data, current_downloads)

            # 计算自上次通知以来的增量
            increment_since_last_notification = current_downloads - last_notification_downloads
            logger.debug(f"插件 {plugin_id} 自上次通知增量：{increment_since_last_notification}")

            notification_sent = False
            # 检查是否达到下载增量阈值
            if increment_since_last_notification >= download_increment:
                logger.info(f"插件 {plugin_id} 达到增量阈值！增量：{increment_since_last_notification} >= {download_increment}")

                # 计算时间间隔
                current_time = time.time()
                time_elapsed = current_time - last_notification_time

                # 发送增量通知
                notification_sent = self._send_increment_notification(
                    plugin_id,
                    current_downloads,
                    increment_since_last_notification,
                    time_elapsed
                )

                # 只有在通知成功发送后才更新历史数据
                if notification_sent:
                    history_data.update({
                        "last_notification_downloads": current_downloads,
                        "last_notification_time": current_time,
                    })

                    logger.info(f"插件 {plugin_id} 通知发送成功，进度已重置。新的基准下载量：{current_downloads}")
                else:
                    logger.warning(f"插件 {plugin_id} 通知发送失败，不更新历史数据")
            else:
                logger.debug(f"插件 {plugin_id} 未达到增量阈值：{increment_since_last_notification} < {download_increment}")

            # 更新当前下载量和检查时间
            history_data.update({
                "last_downloads": current_downloads,
                "last_check_time": time.time()
            })

            # 保存历史数据
            self.save_data(history_key, history_data)
            logger.debug(f"插件 {plugin_id} 历史数据已保存")

            return notification_sent

        except Exception as e:
            logger.error(f"检查插件 {plugin_id} 热度时出错：{str(e)}", exc_info=True)
            return False
    
    def _send_increment_notification(self, plugin_id: str, current_downloads: int, increment: int, time_elapsed: float) -> bool:
        """发送下载增量通知"""
        try:
            plugin_name, _ = self._get_plugin_info(plugin_id)
            time_str = self._format_time_elapsed(time_elapsed)

            # 构建通知内容
            title = "📈 插件下载增量通知"
            text = (f"插件「{plugin_name}」下载量增长！\n\n"
                   f"📊 当前下载量：{current_downloads:,}\n"
                   f"📈 下载增量：{increment:,}\n"
                   f"⏱️ 用时：{time_str}")

            # 发送通知（如果启用）
            if self._enable_notification:
                return self._send_notification(title, text, plugin_name, increment, current_downloads, time_str)
            else:
                logger.info(f"📢 插件 {plugin_name} 达到增量阈值 - 下载增量：{increment}，当前下载量：{current_downloads}，用时：{time_str}（通知已禁用）")
                return True  # 通知被禁用时也认为是"成功"的

        except Exception as e:
            logger.error(f"发送下载增量通知时出错：{str(e)}", exc_info=True)
            return False

    def _send_notification(self, title: str, text: str, plugin_name: str, increment: int, current_downloads: int, time_str: str) -> bool:
        """发送通知消息"""
        try:
            self.post_message(
                mtype=NotificationType.Plugin,
                title=title,
                text=text
            )
            logger.info(f"✅ 插件 {plugin_name} 通知发送成功 - 下载增量：{increment}，当前下载量：{current_downloads}，用时：{time_str}")
            return True
        except Exception as e:
            logger.error(f"❌ 插件 {plugin_name} 通知发送失败：{str(e)}")
            return False

    def _format_time_elapsed(self, seconds: float) -> str:
        """格式化时间间隔"""
        if seconds < 60:
            return f"{seconds:.0f}秒"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}分钟"
        elif seconds < 86400:
            hours = seconds / 3600
            return f"{hours:.1f}小时"
        else:
            days = seconds / 86400
            return f"{days:.1f}天"

    def _update_daily_downloads(self, history_data: dict, current_downloads: int):
        """更新每日下载量记录（记录增量而不是总量）"""
        today = datetime.now().strftime("%Y-%m-%d")
        daily_downloads = history_data.get("daily_downloads", {})
        last_downloads = history_data.get("last_downloads", current_downloads)

        # 计算今天的增量
        daily_increment = current_downloads - last_downloads

        # 只有当增量大于0时才记录（避免负数或0增量污染数据）
        if daily_increment > 0:
            # 如果今天已有记录，需要处理新旧数据结构兼容性
            if today in daily_downloads:
                # 检查现有数据是否为新格式（字典）还是旧格式（数字）
                existing_data = daily_downloads[today]
                if isinstance(existing_data, dict):
                    # 新格式：累加到value字段
                    daily_downloads[today]["value"] += daily_increment
                else:
                    # 旧格式：转换为新格式并累加
                    daily_downloads[today] = {
                        "value": existing_data + daily_increment,
                        "is_historical": False
                    }
            else:
                # 新记录：使用新格式
                daily_downloads[today] = {
                    "value": daily_increment,
                    "is_historical": False
                }

            logger.debug(f"记录今日增量：{daily_increment}，今日累计增量：{self._get_day_value(daily_downloads[today])}")
        elif daily_increment < 0:
            # 如果出现负增量，可能是数据重置或其他问题，记录警告但不更新
            logger.warning(f"检测到负增量 {daily_increment}，可能是数据重置，跳过记录")
        # daily_increment == 0 时不记录，这是正常情况

        history_data["daily_downloads"] = daily_downloads

    def _get_day_value(self, day_data) -> int:
        """获取某天的下载量值，兼容新旧数据格式"""
        if isinstance(day_data, dict):
            return day_data.get("value", 0)
        else:
            # 旧格式，直接返回数值
            return day_data if isinstance(day_data, (int, float)) else 0

    def _is_historical_data(self, day_data) -> bool:
        """检查某天的数据是否为历史数据"""
        if isinstance(day_data, dict):
            return day_data.get("is_historical", False)
        else:
            # 旧格式，不是历史数据
            return False

    def _calculate_historical_total(self, daily_downloads: dict) -> int:
        """计算历史记录期间的总增量（排除历史数据块）"""
        total = 0
        for day_data in daily_downloads.values():
            # 只统计非历史数据的增量
            if not self._is_historical_data(day_data):
                total += self._get_day_value(day_data)
        return total

    def _get_plugin_download_stats(self, plugin_id: str, current_downloads: int, daily_downloads: dict) -> dict:
        """获取插件下载统计信息"""
        historical_increments = self._calculate_historical_total(daily_downloads)

        # 监控前的下载量 = 当前总下载量 - 监控期间的增量
        pre_monitoring_downloads = max(0, current_downloads - historical_increments)

        return {
            "current_total": current_downloads,  # 当前总下载量
            "historical_increments": historical_increments,  # 监控期间的增量
            "pre_monitoring": pre_monitoring_downloads,  # 监控前的下载量
            "monitoring_period_days": len(daily_downloads)  # 监控天数
        }

    def _migrate_legacy_data(self, plugin_id: str, history_data: dict, current_downloads: int):
        """迁移旧版本的错误数据格式"""
        daily_downloads = history_data.get("daily_downloads", {})

        # 检查是否存在错误的数据格式（总量而不是增量）
        if daily_downloads:
            # 提取所有非历史数据的值，兼容新旧格式
            values = []
            for day_data in daily_downloads.values():
                if not self._is_historical_data(day_data):
                    values.append(self._get_day_value(day_data))

            max_daily = max(values) if values else 0

            # 如果最大单日"增量"超过当前总下载量的50%，很可能是错误数据
            if max_daily > current_downloads * 0.5:
                logger.warning(f"检测到插件 {plugin_id} 的历史数据可能有误，清理并重置")

                # 清理错误的daily_downloads数据
                history_data["daily_downloads"] = {}

                # 重置通知基准，避免立即触发大量通知
                history_data["last_notification_downloads"] = current_downloads

                self.save_data(f"history_{plugin_id}", history_data)
                logger.info(f"已清理插件 {plugin_id} 的错误历史数据并重置基准")

    def _generate_heatmap_data(self, daily_downloads: dict, days: int = 90) -> List[List]:
        """生成热力图数据"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days-1)

        heatmap_data = []
        current_date = start_date

        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")

            # 获取当天下载量，兼容新旧格式
            day_data = daily_downloads.get(date_str)
            downloads = self._get_day_value(day_data) if day_data else 0

            # 计算相对于前一天的增量
            prev_date_str = (current_date - timedelta(days=1)).strftime("%Y-%m-%d")
            prev_day_data = daily_downloads.get(prev_date_str)
            prev_downloads = self._get_day_value(prev_day_data) if prev_day_data else downloads
            daily_increment = max(0, downloads - prev_downloads)

            # 格式：[日期索引, 星期几, 增量值]
            # 日期索引：从开始日期算起的天数
            # 星期几：0-6 (周一到周日)
            # 增量值：当天的下载增量
            day_index = (current_date - start_date).days
            weekday = current_date.weekday()

            heatmap_data.append([day_index, weekday, daily_increment])
            current_date += timedelta(days=1)

        return heatmap_data

    def _calculate_heatmap_levels(self, heatmap_data: List[List]) -> List[List]:
        """计算热力图颜色等级，智能排除历史下载量异常值"""
        if not heatmap_data:
            return []

        # 提取所有增量值
        increments = [item[2] for item in heatmap_data]

        if not increments:
            return []

        # 智能检测并排除历史下载量异常值
        filtered_increments = self._filter_historical_outliers(increments)

        # 使用过滤后的数据计算最大值
        max_increment = max(filtered_increments) if filtered_increments else max(increments)

        # 定义5个等级的阈值
        if max_increment == 0:
            levels = [0, 0, 0, 0, 0]
        else:
            levels = [
                0,  # 无下载
                max_increment * 0.2,  # 20%
                max_increment * 0.4,  # 40%
                max_increment * 0.6,  # 60%
                max_increment * 0.8,  # 80%
            ]

        # 为每个数据点分配等级
        result = []
        for item in heatmap_data:
            day_index, weekday, increment = item

            # 确定等级 (0-4)
            level = 0
            for i, threshold in enumerate(levels):
                if increment >= threshold:
                    level = i

            result.append([day_index, weekday, level])

        return result

    def _filter_historical_outliers(self, increments: List[int]) -> List[int]:
        """过滤历史下载量异常值，排除第一天可能的历史数据"""
        if len(increments) <= 1:
            return increments

        # 计算除第一天外其他天数的统计信息
        other_days = increments[1:]
        if not other_days:
            return increments

        # 计算其他天数的平均值和最大值
        avg_other_days = sum(other_days) / len(other_days)
        max_other_days = max(other_days)

        # 如果第一天的值远大于其他天数，则认为是历史数据异常值
        first_day = increments[0]

        # 判断条件：
        # 1. 第一天的值大于其他天数平均值的10倍
        # 2. 第一天的值大于其他天数最大值的5倍
        # 3. 第一天的值大于1000且大于其他天数平均值的5倍
        is_historical_outlier = (
            (avg_other_days > 0 and first_day > avg_other_days * 10) or
            (max_other_days > 0 and first_day > max_other_days * 5) or
            (first_day > 1000 and avg_other_days > 0 and first_day > avg_other_days * 5)
        )

        if is_historical_outlier:
            logger.info(f"检测到历史下载量异常值：第一天={first_day}，其他天数平均值={avg_other_days:.1f}，最大值={max_other_days}，已排除第一天数据用于颜色深度计算")
            return other_days

        return increments

    @eventmanager.register(EventType.PluginAction)
    def handle_remote_command(self, event: Event):
        """处理远程命令事件"""
        if not event:
            return

        event_data = event.event_data
        if not event_data or event_data.get("action") != "get_monitored_downloads":
            return

        logger.info("收到远程命令：获取监控插件实时下载统计")

        try:
            # 获取监控插件下载统计
            result = self._get_monitored_plugins_downloads()

            # 发送结果通知
            self.post_message(
                channel=event_data.get("channel"),
                title="📊 监控插件下载统计",
                text=self._format_downloads_message(result),
                userid=event_data.get("user"),
            )

            logger.info("远程命令执行完成：获取监控插件实时下载统计")

        except Exception as e:
            logger.error(f"执行远程命令失败：{str(e)}", exc_info=True)
            self.post_message(
                channel=event_data.get("channel"),
                title="❌ 获取下载统计失败",
                text=f"执行失败：{str(e)}",
                userid=event_data.get("user"),
            )

    def _get_monitored_plugins_downloads(self) -> Dict[str, Any]:
        """获取当前监控插件的实时总下载量统计"""
        try:
            if not self._monitored_plugins:
                return {
                    "status": "empty",
                    "message": "暂无监控插件",
                    "plugins": [],
                    "total_downloads": 0,
                    "monitored_count": 0,
                    "last_update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

            # 获取实时插件统计数据
            current_stats = MoviePilotServerHelper.get_plugin_statistic()

            if not current_stats:
                return {
                    "status": "error",
                    "message": "无法获取插件统计数据",
                    "plugins": [],
                    "total_downloads": 0,
                    "monitored_count": 0,
                    "last_update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

            plugins_data = []
            total_downloads = 0

            for plugin_id, config in self._monitored_plugins.items():
                # 获取插件信息
                plugin_name, plugin_icon = self._get_plugin_info(plugin_id)

                # 获取当前实时下载量
                current_downloads = current_stats.get(plugin_id, 0)
                total_downloads += current_downloads

                # 获取历史数据用于获取最后检查时间
                history_key = f"history_{plugin_id}"
                history_data = self.get_data(history_key) or {}
                last_check_time = history_data.get("last_check_time")

                # 格式化最后检查时间
                last_check_formatted = None
                if last_check_time:
                    last_check_formatted = datetime.fromtimestamp(last_check_time).strftime("%Y-%m-%d %H:%M:%S")

                plugins_data.append({
                    "plugin_id": plugin_id,
                    "plugin_name": plugin_name,
                    "plugin_icon": plugin_icon,
                    "current_downloads": current_downloads,
                    "last_check_time": last_check_formatted
                })

            return {
                "status": "success",
                "message": f"成功获取 {len(plugins_data)} 个监控插件的下载统计",
                "plugins": plugins_data,
                "total_downloads": total_downloads,
                "monitored_count": len(self._monitored_plugins),
                "last_update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        except Exception as e:
            logger.error(f"获取监控插件下载统计失败：{str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"获取统计数据失败：{str(e)}",
                "plugins": [],
                "total_downloads": 0,
                "monitored_count": 0,
                "last_update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

    def _format_downloads_message(self, result: Dict[str, Any]) -> str:
        """格式化下载统计消息"""
        if result["status"] == "empty":
            return "📭 暂无监控插件"

        if result["status"] == "error":
            return f"❌ {result['message']}"

        plugins = result["plugins"]
        total_downloads = result["total_downloads"]
        monitored_count = result["monitored_count"]
        last_update_time = result["last_update_time"]

        message_lines = [
            f"📊 监控插件下载统计报告",
            f"",
            f"🔢 监控插件数量：{monitored_count}",
            f"📈 总下载量：{total_downloads:,}",
            f"🕐 更新时间：{last_update_time}",
            f"",
            f"📋 详细统计："
        ]

        for plugin in plugins:
            plugin_name = plugin["plugin_name"]
            current_downloads = plugin["current_downloads"]

            message_lines.extend([
                f"🔸 {plugin_name}：{current_downloads:,}",
            ])

        return "\n".join(message_lines)


    def get_command(self) -> List[Dict[str, Any]]:
        """注册插件命令"""
        return [
            {
                "cmd": "/get_monitored_downloads",
                "event": EventType.PluginAction,
                "desc": "插件实时下载量",
                "category": "插件监控",
                "data": {"action": "get_monitored_downloads"},
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        """注册插件API"""
        api_endpoints = [
            {
                "path": "/config",
                "endpoint": self._get_config,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取当前配置",
            },
            {
                "path": "/config",
                "endpoint": self._save_config,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "保存配置",
            },
            {
                "path": "/data",
                "endpoint": self._get_dashboard_data,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取仪表板数据",
            },
            {
                "path": "/plugins",
                "endpoint": self._get_available_plugins,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取可用插件列表",
            },
            {
                "path": "/run_once",
                "endpoint": self._trigger_run_once,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即运行一次",
            },
            {
                "path": "/status",
                "endpoint": self._get_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取插件状态",
            },
            {
                "path": "/heatmap-data",
                "endpoint": self._get_heatmap_data,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取热力图数据",
            },
            {
                "path": "/year-data/<year>",
                "endpoint": self._get_year_data,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取年份数据",
            },
            {
                "path": "/month-data/<month_key>",
                "endpoint": self._get_month_data,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取月份数据",
            },
            {
                "path": "/plugin-heatmap",
                "endpoint": self._get_plugin_heatmap_query,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取指定插件的热力图数据",
            },
            {
                "path": "/plugin-list",
                "endpoint": self._get_monitored_plugin_list,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "获取监控插件列表",
            },
            {
                "path": "/reset-data",
                "endpoint": self._reset_plugin_data,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "重置插件数据",
            },
            {
                "path": "/reset-plugin-heatmap",
                "endpoint": self._reset_plugin_heatmap,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "重置指定插件的热力图数据",
            },
        ]

        # 添加 MCP API 端点（仅在启用时）
        if self._enable_mcp:
            try:
                if hasattr(self, 'get_mcp_api_endpoints'):
                    mcp_endpoints = self.get_mcp_api_endpoints()
                    if mcp_endpoints:
                        api_endpoints.extend(mcp_endpoints)
                        logger.debug(f"添加了 {len(mcp_endpoints)} 个 MCP API 端点")
            except Exception as e:
                logger.error(f"获取 MCP API 端点失败: {str(e)}")
        else:
            logger.debug("MCP功能已禁用，跳过MCP API端点注册")

        return api_endpoints

    # --- Vue Integration Methods ---
    @staticmethod
    def get_render_mode() -> Tuple[str, Optional[str]]:
        """Declare Vue rendering mode and assets path."""
        return "vue", "dist/assets"

    # --- API Endpoint Implementations ---
    def _get_current_config(self) -> Dict[str, Any]:
        """获取当前配置"""
        # 获取实际的下载增量值
        download_increment = self._download_increment
        if not download_increment and self._monitored_plugins:
            # 从第一个监控插件的配置中获取
            first_config = next(iter(self._monitored_plugins.values()))
            download_increment = first_config.get("download_increment", self.DEFAULT_INCREMENT)
        elif not download_increment:
            download_increment = self.DEFAULT_INCREMENT

        return {
            "enabled": self._enabled,
            "enable_notification": self._enable_notification,
            "enable_mcp": self._enable_mcp,
            "cron": self._cron,
            "download_increment": download_increment,
            "monitored_plugins": list(self._monitored_plugins.keys()) if self._monitored_plugins else []
        }

    def _get_config(self) -> Dict[str, Any]:
        """API Endpoint: Returns current plugin configuration."""
        return self._get_current_config()

    def _save_config(self, config_payload: dict) -> Dict[str, Any]:
        """API Endpoint: Saves plugin configuration."""
        try:
            logger.info(f"收到配置保存请求: {config_payload}")

            # 更新配置
            self.init_plugin(config_payload)

            # 保存配置
            self.update_config(config_payload)

            logger.info("配置已保存并重新初始化")
            return {"status": "success", "message": "配置已成功保存", "config": self._get_current_config()}

        except Exception as e:
            logger.error(f"保存配置时发生错误: {e}", exc_info=True)
            return {"status": "error", "message": f"保存配置失败: {e}", "config": self._get_current_config()}

    def _get_dashboard_data(self) -> Dict[str, Any]:
        """API Endpoint: Returns dashboard data for Vue components."""
        try:
            if not self._monitored_plugins:
                return {
                    "status": "empty",
                    "message": "暂无监控插件",
                    "plugins": [],
                    "total_downloads": 0,
                    "last_check_time": None
                }

            current_stats = MoviePilotServerHelper.get_plugin_statistic()

            if not current_stats:
                return {
                    "status": "error",
                    "message": "无法获取插件统计数据",
                    "plugins": [],
                    "total_downloads": 0,
                    "last_check_time": None
                }

            plugins_data = []
            total_downloads = 0
            global_last_check_time = None

            for plugin_id, config in self._monitored_plugins.items():
                history_key = f"history_{plugin_id}"
                history_data = self.get_data(history_key) or {}

                # 获取插件信息
                plugin_name, plugin_icon = self._get_plugin_info(plugin_id)

                current_downloads = current_stats.get(plugin_id, 0)
                download_increment = config.get("download_increment", self.DEFAULT_INCREMENT)
                last_notification_downloads = history_data.get("last_notification_downloads", current_downloads)
                daily_downloads = history_data.get("daily_downloads", {})

                # 收集全局信息
                if global_last_check_time is None and history_data.get("last_check_time"):
                    last_check_time = datetime.fromtimestamp(history_data["last_check_time"])
                    global_last_check_time = last_check_time.strftime("%Y-%m-%d %H:%M:%S")

                # 计算当前进度
                increment_since_last = current_downloads - last_notification_downloads
                total_downloads += current_downloads

                # 获取详细统计信息
                stats = self._get_plugin_download_stats(plugin_id, current_downloads, daily_downloads)

                # 构建插件数据
                plugins_data.append({
                    "id": plugin_id,
                    "name": plugin_name,
                    "icon": plugin_icon,
                    "current_downloads": current_downloads,
                    "increment_since_last": increment_since_last,
                    "download_increment": download_increment,
                    "daily_downloads": daily_downloads,
                    "progress_percentage": min(100, (increment_since_last / download_increment) * 100) if download_increment > 0 else 0,
                    # 新增详细统计信息
                    "stats": stats
                })

            return {
                "status": "success",
                "plugins": plugins_data,
                "total_downloads": total_downloads,
                "last_check_time": global_last_check_time,
                "monitored_count": len(self._monitored_plugins)
            }

        except Exception as e:
            logger.error(f"获取仪表板数据时出错：{str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"获取数据时出错: {str(e)}",
                "plugins": [],
                "total_downloads": 0,
                "last_check_time": None
            }

    def _get_available_plugins(self) -> Dict[str, Any]:
        """API Endpoint: Returns available plugins for configuration."""
        try:
            plugins = self._get_cached_plugins()
            plugin_options = [
                {
                    "title": plugin.plugin_name or plugin.id,
                    "value": plugin.id,
                    "icon": self._get_plugin_icon_url(plugin)
                }
                for plugin in plugins if plugin.installed
            ]

            return {
                "status": "success",
                "plugins": plugin_options
            }
        except Exception as e:
            logger.error(f"获取可用插件列表时出错：{str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"获取插件列表失败: {str(e)}",
                "plugins": []
            }

    def _trigger_run_once(self) -> Dict[str, Any]:
        """API Endpoint: Trigger immediate execution."""
        try:
            if not self._enabled:
                return {"status": "error", "message": "插件未启用"}

            if not self._monitored_plugins:
                return {"status": "error", "message": "没有配置监控插件"}

            # 执行立即检查
            def run_check():
                try:
                    time.sleep(0.1)
                    self._check_plugin_heat()
                    logger.info("手动触发的立即运行完成")
                except Exception as e:
                    logger.error(f"手动触发的立即运行出错：{str(e)}", exc_info=True)

            thread = threading.Thread(target=run_check, daemon=True)
            thread.start()

            return {"status": "success", "message": "已触发立即运行"}

        except Exception as e:
            logger.error(f"触发立即运行时出错：{str(e)}", exc_info=True)
            return {"status": "error", "message": f"触发失败: {str(e)}"}

    def _get_status(self) -> Dict[str, Any]:
        """API Endpoint: Get plugin status for Page.vue."""
        try:
            if not self._monitored_plugins:
                return {
                    "status": "empty",
                    "monitored_plugins": [],
                    "total_downloads": 0,
                    "total_daily_growth": 0,
                    "global_last_check_time": None,
                    "version": self.plugin_version
                }

            current_stats = MoviePilotServerHelper.get_plugin_statistic()

            if not current_stats:
                return {
                    "status": "error",
                    "message": "无法获取插件统计数据",
                    "monitored_plugins": [],
                    "total_downloads": 0,
                    "total_daily_growth": 0,
                    "global_last_check_time": None,
                    "version": self.plugin_version
                }

            monitored_plugins = []
            total_downloads = 0
            total_daily_growth = 0
            global_last_check_time = None
            today = datetime.now().strftime("%Y-%m-%d")

            for plugin_id, config in self._monitored_plugins.items():
                history_key = f"history_{plugin_id}"
                history_data = self.get_data(history_key) or {}

                plugin_name, plugin_icon = self._get_plugin_info(plugin_id)
                plugin_desc = self._get_plugin_desc(plugin_id)
                current_downloads = current_stats.get(plugin_id, 0)
                last_notification_downloads = history_data.get("last_notification_downloads", current_downloads)
                increment_since_last = current_downloads - last_notification_downloads

                # 获取当日增长量
                daily_downloads = history_data.get("daily_downloads", {})
                today_growth = 0
                if today in daily_downloads:
                    today_data = daily_downloads[today]
                    if not self._is_historical_data(today_data):
                        today_growth = self._get_day_value(today_data)

                if global_last_check_time is None and history_data.get("last_check_time"):
                    last_check_time = datetime.fromtimestamp(history_data["last_check_time"])
                    global_last_check_time = last_check_time.strftime("%Y-%m-%d %H:%M:%S")

                total_downloads += current_downloads
                total_daily_growth += today_growth

                monitored_plugins.append({
                    "id": plugin_id,
                    "name": plugin_name,
                    "icon": plugin_icon,
                    "downloads": current_downloads,
                    "increment_since_last": increment_since_last,
                    "download_increment": config.get("download_increment", self.DEFAULT_INCREMENT),
                    "daily_growth": today_growth,
                    "last_check": global_last_check_time,
                    "desc": plugin_desc
                })

            return {
                "status": "success",
                "monitored_plugins": monitored_plugins,
                "total_downloads": total_downloads,
                "total_daily_growth": total_daily_growth,
                "global_last_check_time": global_last_check_time,
                "version": self.plugin_version
            }

        except Exception as e:
            logger.error(f"获取状态数据时出错：{str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"获取状态失败: {str(e)}",
                "monitored_plugins": [],
                "total_downloads": 0,
                "total_daily_growth": 0,
                "global_last_check_time": None,
                "version": self.plugin_version
            }

    # --- Abstract/Base Methods Implementation ---
    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        """Returns None for Vue form, but provides initial config data."""
        return None, self._get_current_config()

    def get_page(self) -> Optional[List[dict]]:
        """Vue mode doesn't use Vuetify page definitions."""
        return None

    def get_dashboard_meta(self) -> Optional[List[Dict[str, str]]]:
        """获取插件仪表盘元信息"""
        return [
            {
                "key": "heatmonitor",
                "name": "插件热度监控"
            }
        ]

    def get_dashboard(self, key: str = "", **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], Optional[List[dict]]]]:
        """获取插件仪表盘页面 - Vue模式"""
        return (
            {"cols": 12, "md": 6},
            {
                "refresh": 30,
                "border": True,
                "title": "插件热度监控",
                "subtitle": "监控插件下载量热度变化",
                "render_mode": "vue",
                "pluginConfig": {
                    "dashboard_refresh_interval": 30,
                    "dashboard_auto_refresh": True,
                },
            },
            None,
        )

    # Color utility methods for Vue components (used by API endpoints)
    def _get_year_level(self, downloads: int) -> int:
        """获取年份下载量等级"""
        if downloads >= 50000:
            return 4
        elif downloads >= 20000:
            return 3
        elif downloads >= 5000:
            return 2
        elif downloads > 0:
            return 1
        return 0

    def _get_month_level(self, downloads: int) -> int:
        """获取月份下载量等级"""
        if downloads >= 5000:
            return 4
        elif downloads >= 2000:
            return 3
        elif downloads >= 500:
            return 2
        elif downloads > 0:
            return 1
        return 0

    def _get_day_level(self, downloads: int) -> int:
        """获取天数下载量等级"""
        if downloads >= 1000:
            return 4
        elif downloads >= 500:
            return 3
        elif downloads >= 100:
            return 2
        elif downloads > 0:
            return 1
        return 0

    def _get_blue_color(self, level: int) -> str:
        """获取蓝色系颜色 - 年份"""
        colors = {
            0: "#e3f2fd",  # 无数据 - 浅蓝
            1: "#bbdefb",  # 少量 - 淡蓝
            2: "#64b5f6",  # 一般 - 中蓝
            3: "#2196f3",  # 较多 - 蓝色
            4: "#1565c0"   # 很多 - 深蓝
        }
        return colors.get(level, "#e3f2fd")

    def _get_orange_color(self, level: int) -> str:
        """获取橙色系颜色 - 月份"""
        colors = {
            0: "#fff3e0",  # 无数据 - 浅橙
            1: "#ffcc80",  # 少量 - 淡橙
            2: "#ffb74d",  # 一般 - 中橙
            3: "#ff9800",  # 较多 - 橙色
            4: "#e65100"   # 很多 - 深橙
        }
        return colors.get(level, "#fff3e0")

    def _get_green_color(self, level: int) -> str:
        """获取绿色系颜色 - 天数"""
        colors = {
            0: "#ebedf0",  # 无数据 - 灰色
            1: "#c6e48b",  # 少量 - 浅绿
            2: "#7bc96f",  # 一般 - 中绿
            3: "#239a3b",  # 较多 - 绿色
            4: "#196127"   # 很多 - 深绿
        }
        return colors.get(level, "#ebedf0")

    def _get_level_color(self, level: int) -> str:
        """获取等级对应的颜色 - 保持兼容性"""
        return self._get_green_color(level)

    def _get_heatmap_data(self) -> Dict[str, Any]:
        """API Endpoint: Get heatmap data for Page.vue."""
        try:
            if not self._monitored_plugins:
                return {
                    "status": "empty",
                    "yearData": {},
                    "monthData": {},
                    "dayData": {}
                }

            # 收集所有插件的历史数据
            all_daily_downloads = {}

            for plugin_id in self._monitored_plugins.keys():
                history_key = f"history_{plugin_id}"
                history_data = self.get_data(history_key) or {}
                daily_downloads = history_data.get("daily_downloads", {})

                # 合并所有插件的每日下载量（排除历史数据）
                for date, day_data_item in daily_downloads.items():
                    downloads = self._get_day_value(day_data_item)
                    is_historical = self._is_historical_data(day_data_item)

                    # 只统计非历史数据
                    if not is_historical:
                        if date not in all_daily_downloads:
                            all_daily_downloads[date] = 0
                        all_daily_downloads[date] += downloads

            # 智能过滤历史异常值
            filtered_daily_downloads = self._filter_daily_historical_outliers(all_daily_downloads)

            # 生成年份、月份、天数数据
            year_data = {}
            month_data = {}
            day_data = {}

            for date_str, downloads in filtered_daily_downloads.items():
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    year = date_obj.year
                    month_key = f"{year}-{date_obj.month:02d}"

                    # 累计年份数据
                    if year not in year_data:
                        year_data[year] = 0
                    year_data[year] += downloads

                    # 累计月份数据
                    if month_key not in month_data:
                        month_data[month_key] = 0
                    month_data[month_key] += downloads

                    # 天数数据
                    day_data[date_str] = downloads

                except ValueError:
                    continue

            return {
                "status": "success",
                "yearData": year_data,
                "monthData": month_data,
                "dayData": day_data
            }

        except Exception as e:
            logger.error(f"获取热力图数据时出错：{str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"获取热力图数据失败: {str(e)}",
                "yearData": {},
                "monthData": {},
                "dayData": {}
            }

    def _filter_daily_historical_outliers(self, daily_downloads: Dict[str, int]) -> Dict[str, int]:
        """过滤每日下载量中的历史异常值"""
        if len(daily_downloads) <= 1:
            return daily_downloads

        # 按日期排序
        sorted_dates = sorted(daily_downloads.keys())
        if len(sorted_dates) <= 1:
            return daily_downloads

        # 获取第一天和其他天数的数据
        first_date = sorted_dates[0]
        first_day_downloads = daily_downloads[first_date]

        other_days_downloads = [daily_downloads[date] for date in sorted_dates[1:]]

        if not other_days_downloads:
            return daily_downloads

        # 计算其他天数的统计信息
        avg_other_days = sum(other_days_downloads) / len(other_days_downloads)
        max_other_days = max(other_days_downloads)

        # 判断第一天是否为历史异常值
        is_historical_outlier = (
            (avg_other_days > 0 and first_day_downloads > avg_other_days * 10) or
            (max_other_days > 0 and first_day_downloads > max_other_days * 5) or
            (first_day_downloads > 1000 and avg_other_days > 0 and first_day_downloads > avg_other_days * 5)
        )

        if is_historical_outlier:
            logger.info(f"热力图数据中检测到历史异常值：{first_date}={first_day_downloads}，其他天数平均值={avg_other_days:.1f}，已排除该日期")
            # 返回排除第一天的数据
            return {date: downloads for date, downloads in daily_downloads.items() if date != first_date}

        return daily_downloads

    def _get_plugin_heatmap(self, plugin_id: str) -> Dict[str, Any]:
        """API Endpoint: 获取指定插件的热力图数据"""
        try:
            if plugin_id not in self._monitored_plugins:
                return {
                    "status": "error",
                    "message": f"插件 {plugin_id} 未被监控",
                    "yearData": {},
                    "monthData": {},
                    "dayData": {},
                    "current_downloads": 0
                }

            # 获取插件历史数据
            history_key = f"history_{plugin_id}"
            history_data = self.get_data(history_key) or {}
            daily_downloads = history_data.get("daily_downloads", {})

            # 获取当前下载量
            current_stats = MoviePilotServerHelper.get_plugin_statistic()
            current_downloads = current_stats.get(plugin_id, 0) if current_stats else 0

            # 获取插件信息
            plugin_name, _ = self._get_plugin_info(plugin_id)

            if not daily_downloads:
                # 即使没有历史增量数据，也返回成功状态，显示空的热力图
                return {
                    "status": "success",
                    "plugin_id": plugin_id,
                    "plugin_name": plugin_name,
                    "yearData": {},
                    "monthData": {},
                    "dayData": {},
                    "total_days": 0,
                    "current_downloads": current_downloads,
                    "message": f"插件 {plugin_name} 暂无历史增量数据，当前总下载量：{current_downloads}"
                }

            # 先提取非历史数据用于智能过滤
            non_historical_data = {}
            for date_str, day_data_item in daily_downloads.items():
                downloads = self._get_day_value(day_data_item)
                is_historical = self._is_historical_data(day_data_item)
                if not is_historical:
                    non_historical_data[date_str] = downloads

            # 智能过滤历史异常值
            filtered_non_historical = self._filter_daily_historical_outliers(non_historical_data)

            # 生成年度数据
            year_data = {}
            month_data = {}
            day_data = {}

            for date_str, day_data_item in daily_downloads.items():
                try:
                    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                    year = date_obj.year
                    month_key = f"{year}-{date_obj.month:02d}"

                    # 获取实际的下载量值
                    downloads = self._get_day_value(day_data_item)
                    is_historical = self._is_historical_data(day_data_item)

                    # 累计年度数据（排除历史数据和异常值）
                    if not is_historical and date_str in filtered_non_historical:
                        year_data[year] = year_data.get(year, 0) + downloads

                    # 累计月度数据（排除历史数据和异常值）
                    if not is_historical and date_str in filtered_non_historical:
                        month_data[month_key] = month_data.get(month_key, 0) + downloads

                    # 日度数据（包含历史数据标记，但标记异常值）
                    if isinstance(day_data_item, dict):
                        # 如果是被过滤的异常值，添加标记
                        if not is_historical and date_str not in filtered_non_historical:
                            day_data_item = day_data_item.copy()
                            day_data_item["is_outlier"] = True
                        day_data[date_str] = day_data_item
                    else:
                        # 兼容旧格式
                        is_outlier = not is_historical and date_str not in filtered_non_historical
                        day_data[date_str] = {
                            "value": downloads,
                            "is_historical": is_historical,
                            "is_outlier": is_outlier
                        }

                except ValueError:
                    continue

            return {
                "status": "success",
                "plugin_id": plugin_id,
                "plugin_name": plugin_name,
                "yearData": year_data,
                "monthData": month_data,
                "dayData": day_data,
                "total_days": len(day_data),
                "current_downloads": current_downloads
            }

        except Exception as e:
            logger.error(f"获取插件 {plugin_id} 热力图数据时出错：{str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"获取插件热力图数据失败: {str(e)}",
                "yearData": {},
                "monthData": {},
                "dayData": {},
                "current_downloads": 0
            }

    def _get_monitored_plugin_list(self) -> Dict[str, Any]:
        """API Endpoint: 获取监控插件列表"""
        try:
            if not self._monitored_plugins:
                return {
                    "status": "empty",
                    "message": "暂无监控插件",
                    "plugins": []
                }

            plugins_list = []

            # 获取当前下载统计
            current_stats = MoviePilotServerHelper.get_plugin_statistic()

            for plugin_id in self._monitored_plugins.keys():
                plugin_name, plugin_icon = self._get_plugin_info(plugin_id)

                # 获取插件统计信息
                history_key = f"history_{plugin_id}"
                history_data = self.get_data(history_key) or {}
                daily_downloads = history_data.get("daily_downloads", {})

                # 获取当前下载量
                current_downloads = current_stats.get(plugin_id, 0) if current_stats else 0

                plugins_list.append({
                    "id": plugin_id,
                    "name": plugin_name,
                    "icon": plugin_icon,
                    "data_points": len(daily_downloads),
                    "has_data": current_downloads > 0,  # 只要有当前下载量就显示热力图
                    "current_downloads": current_downloads
                })

            return {
                "status": "success",
                "plugins": plugins_list,
                "total_count": len(plugins_list)
            }

        except Exception as e:
            logger.error(f"获取监控插件列表时出错：{str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"获取插件列表失败: {str(e)}",
                "plugins": []
            }

    def _get_plugin_heatmap_query(self, plugin_id: str = None) -> Dict[str, Any]:
        """API Endpoint: 获取指定插件的热力图数据（查询参数版本）"""
        if not plugin_id:
            return {
                "status": "error",
                "message": "缺少plugin_id参数",
                "yearData": {},
                "monthData": {},
                "dayData": {}
            }

        return self._get_plugin_heatmap(plugin_id)

    def _reset_plugin_data(self, reset_payload: dict = None) -> Dict[str, Any]:
        """API Endpoint: 重置插件数据"""
        try:
            if not reset_payload:
                reset_payload = {}

            plugin_id = reset_payload.get("plugin_id")
            reset_type = reset_payload.get("reset_type", "daily_downloads")  # daily_downloads, all, notification_base

            if not plugin_id:
                return {
                    "status": "error",
                    "message": "缺少plugin_id参数"
                }

            if plugin_id not in self._monitored_plugins:
                return {
                    "status": "error",
                    "message": f"插件 {plugin_id} 未被监控"
                }

            history_key = f"history_{plugin_id}"
            history_data = self.get_data(history_key) or {}

            if not history_data:
                return {
                    "status": "error",
                    "message": f"插件 {plugin_id} 无历史数据"
                }

            # 获取当前下载量用于重置基准
            current_stats = MoviePilotServerHelper.get_plugin_statistic()
            current_downloads = current_stats.get(plugin_id, 0) if current_stats else 0

            if reset_type == "daily_downloads":
                # 清理每日下载量数据，并设置重置基准
                yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                history_data["daily_downloads"] = {
                    yesterday: current_downloads  # 将当前总下载量记录为昨天的基准
                }
                logger.info(f"已重置插件 {plugin_id} 的每日下载量数据，设置基准：{yesterday} = {current_downloads}")

            elif reset_type == "notification_base":
                # 重置通知基准
                history_data["last_notification_downloads"] = current_downloads
                history_data["last_notification_time"] = time.time()
                logger.info(f"已重置插件 {plugin_id} 的通知基准为 {current_downloads}")

            elif reset_type == "all":
                # 完全重置所有数据
                history_data = {
                    "last_downloads": current_downloads,
                    "last_notification_downloads": current_downloads,
                    "last_notification_time": time.time(),
                    "last_check_time": time.time(),
                    "daily_downloads": {}
                }
                logger.info(f"已完全重置插件 {plugin_id} 的所有数据")

            else:
                return {
                    "status": "error",
                    "message": f"不支持的重置类型: {reset_type}"
                }

            # 保存更新后的数据
            self.save_data(history_key, history_data)

            plugin_name, _ = self._get_plugin_info(plugin_id)

            return {
                "status": "success",
                "message": f"已成功重置插件 {plugin_name} 的数据",
                "plugin_id": plugin_id,
                "plugin_name": plugin_name,
                "reset_type": reset_type,
                "current_downloads": current_downloads
            }

        except Exception as e:
            logger.error(f"重置插件数据时出错：{str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"重置数据失败: {str(e)}"
            }

    def _reset_plugin_heatmap(self, reset_payload: dict = None) -> Dict[str, Any]:
        """API Endpoint: 重置指定插件的热力图数据"""
        try:
            if not reset_payload:
                reset_payload = {}

            plugin_id = reset_payload.get("plugin_id")

            if not plugin_id:
                return {
                    "status": "error",
                    "message": "缺少plugin_id参数"
                }

            # 获取插件信息
            plugin_name, _ = self._get_plugin_info(plugin_id)

            # 检查插件是否存在历史数据
            history_key = f"history_{plugin_id}"
            history_data = self.get_data(history_key) or {}

            if not history_data:
                return {
                    "status": "error",
                    "message": f"插件 {plugin_name} 暂无历史数据"
                }

            # 获取当前下载量
            current_stats = MoviePilotServerHelper.get_plugin_statistic()
            current_downloads = current_stats.get(plugin_id, 0) if current_stats else 0

            # 重置热力图数据，保留历史总下载量
            # 将当前总下载量记录在重置日期前一天作为历史数据
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

            # 创建新的daily_downloads结构，包含历史数据标记
            history_data["daily_downloads"] = {
                yesterday: {
                    "value": current_downloads,
                    "is_historical": True,  # 标记为历史数据
                    "reset_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            }

            # 更新基准下载量，确保从现在开始正确计算增量
            history_data["last_downloads"] = current_downloads

            # 重置通知基准，确保increment_since_last从0开始
            history_data["last_notification_downloads"] = current_downloads
            history_data["last_notification_time"] = time.time()

            # 保存更新后的数据
            self.save_data(history_key, history_data)

            logger.info(f"已重置插件 {plugin_name} 的热力图数据，设置基准下载量：{current_downloads}")

            return {
                "status": "success",
                "message": f"已成功重置插件 {plugin_name} 的热力图数据",
                "plugin_id": plugin_id,
                "plugin_name": plugin_name,
                "current_downloads": current_downloads,
                "reset_baseline": {
                    "downloads": current_downloads,
                    "reset_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            }

        except Exception as e:
            logger.error(f"重置插件热力图数据时出错：{str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"重置热力图数据失败: {str(e)}"
            }

    def _get_year_data(self, year: str) -> Dict[str, Any]:
        """API Endpoint: Get year data for Page.vue."""
        try:
            # 转换年份为整数
            try:
                year_int = int(year)
            except ValueError:
                return {
                    "status": "error",
                    "message": "无效的年份格式",
                    "monthData": {},
                    "dayData": {}
                }

            if not self._monitored_plugins:
                return {
                    "status": "empty",
                    "monthData": {},
                    "dayData": {}
                }

            # 收集指定年份的数据
            month_data = {}
            day_data = {}

            for plugin_id in self._monitored_plugins.keys():
                history_key = f"history_{plugin_id}"
                history_data = self.get_data(history_key) or {}
                daily_downloads = history_data.get("daily_downloads", {})

                for date_str, day_data_item in daily_downloads.items():
                    try:
                        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                        if date_obj.year == year_int:
                            month_key = f"{year_int}-{date_obj.month:02d}"

                            downloads = self._get_day_value(day_data_item)
                            is_historical = self._is_historical_data(day_data_item)

                            # 只统计非历史数据
                            if not is_historical:
                                # 累计月份数据
                                if month_key not in month_data:
                                    month_data[month_key] = 0
                                month_data[month_key] += downloads

                                # 天数数据
                                if date_str not in day_data:
                                    day_data[date_str] = 0
                                day_data[date_str] += downloads

                    except ValueError:
                        continue

            return {
                "status": "success",
                "monthData": month_data,
                "dayData": day_data
            }

        except Exception as e:
            logger.error(f"获取年份数据时出错：{str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"获取年份数据失败: {str(e)}",
                "monthData": {},
                "dayData": {}
            }

    def _get_month_data(self, month_key: str) -> Dict[str, Any]:
        """API Endpoint: Get month data for Page.vue."""
        try:
            if not self._monitored_plugins:
                return {
                    "status": "empty",
                    "dayData": {}
                }

            # 解析月份键 (格式: YYYY-MM)
            try:
                year, month = month_key.split('-')
                year = int(year)
                month = int(month)
            except (ValueError, IndexError):
                return {
                    "status": "error",
                    "message": "无效的月份格式",
                    "dayData": {}
                }

            # 收集指定月份的数据
            day_data = {}

            for plugin_id in self._monitored_plugins.keys():
                history_key = f"history_{plugin_id}"
                history_data = self.get_data(history_key) or {}
                daily_downloads = history_data.get("daily_downloads", {})

                for date_str, day_data_item in daily_downloads.items():
                    try:
                        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                        if date_obj.year == year and date_obj.month == month:
                            downloads = self._get_day_value(day_data_item)
                            is_historical = self._is_historical_data(day_data_item)

                            # 只统计非历史数据
                            if not is_historical:
                                if date_str not in day_data:
                                    day_data[date_str] = 0
                                day_data[date_str] += downloads

                    except ValueError:
                        continue

            return {
                "status": "success",
                "dayData": day_data
            }

        except Exception as e:
            logger.error(f"获取月份数据时出错：{str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"获取月份数据失败: {str(e)}",
                "dayData": {}
            }

    # ==================== MCP工具 ====================

    @mcp_tool(
        name="get-plugin-download-stats",
        description="获取插件热度监控的下载量统计信息",
        parameters=[
            {
                "name": "plugin_id",
                "description": "插件ID，如果不指定则返回所有监控插件的统计信息",
                "required": False,
                "type": "string"
            },
            {
                "name": "include_details",
                "description": "是否包含详细信息（如每日下载量、活跃天数等）",
                "required": False,
                "type": "boolean"
            }
        ]
    )
    def get_plugin_download_stats_tool(self, plugin_id: str = None, include_details: bool = True) -> dict:
        """获取插件下载量统计信息的MCP工具"""
        try:
            if not self._enabled:
                return {
                    "status": "disabled",
                    "message": "插件热度监控未启用"
                }

            if not self._enable_mcp:
                return {
                    "status": "disabled",
                    "message": "MCP工具功能未启用"
                }

            if not self._monitored_plugins:
                return {
                    "status": "empty",
                    "message": "暂无监控插件",
                    "total_plugins": 0,
                    "plugins": []
                }

            # 获取当前下载统计
            current_stats = MoviePilotServerHelper.get_plugin_statistic()

            if not current_stats:
                return {
                    "status": "error",
                    "message": "无法获取插件统计数据"
                }

            result = {
                "status": "success",
                "timestamp": datetime.now().isoformat(),
                "total_plugins": len(self._monitored_plugins),
                "plugins": []
            }

            # 如果指定了特定插件ID
            if plugin_id:
                if plugin_id not in self._monitored_plugins:
                    return {
                        "status": "error",
                        "message": f"插件 {plugin_id} 未在监控列表中"
                    }

                plugin_stats = self._get_single_plugin_stats(plugin_id, current_stats, include_details)
                result["plugins"] = [plugin_stats]
                result["total_plugins"] = 1
            else:
                # 获取所有监控插件的统计信息
                total_downloads = 0
                total_today_growth = 0

                for monitored_plugin_id in self._monitored_plugins.keys():
                    plugin_stats = self._get_single_plugin_stats(monitored_plugin_id, current_stats, include_details)
                    result["plugins"].append(plugin_stats)
                    total_downloads += plugin_stats.get("current_downloads", 0)
                    total_today_growth += plugin_stats.get("today_growth", 0)

                result["summary"] = {
                    "total_downloads": total_downloads,
                    "total_today_growth": total_today_growth
                }

            return result

        except Exception as e:
            logger.error(f"获取插件下载统计失败: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"获取统计信息失败: {str(e)}"
            }

    def _get_single_plugin_stats(self, plugin_id: str, current_stats: dict, include_details: bool) -> dict:
        """获取单个插件的统计信息"""
        try:
            # 获取插件基本信息
            plugin_name, _ = self._get_plugin_info(plugin_id)
            current_downloads = current_stats.get(plugin_id, 0)

            # 获取历史数据
            history_key = f"history_{plugin_id}"
            history_data = self.get_data(history_key) or {}
            daily_downloads = history_data.get("daily_downloads", {})

            # 基本统计信息
            stats = {
                "plugin_id": plugin_id,
                "plugin_name": plugin_name,
                "current_downloads": current_downloads
            }

            if include_details:
                # 计算详细统计信息
                today = datetime.now().strftime("%Y-%m-%d")

                # 今日增长量
                today_growth = 0
                if today in daily_downloads:
                    today_data = daily_downloads[today]
                    if not self._is_historical_data(today_data):
                        today_growth = self._get_day_value(today_data)

                # 活跃天数（有下载量增长的天数）
                active_days = 0
                consecutive_active_days = 0
                last_date = None

                # 按日期排序
                sorted_dates = sorted(daily_downloads.keys(), reverse=True)

                for date in sorted_dates:
                    day_data = daily_downloads[date]
                    if not self._is_historical_data(day_data) and self._get_day_value(day_data) > 0:
                        active_days += 1

                        # 计算连续活跃天数
                        if last_date is None:
                            consecutive_active_days = 1
                            last_date = datetime.strptime(date, "%Y-%m-%d")
                        else:
                            current_date = datetime.strptime(date, "%Y-%m-%d")
                            if (last_date - current_date).days == 1:
                                consecutive_active_days += 1
                                last_date = current_date
                            else:
                                break
                    elif last_date is not None:
                        break

                # 监控期间总增长量
                monitoring_increments = self._calculate_historical_total(daily_downloads)

                # 最后检查时间
                last_check_time = history_data.get("last_check_time")
                last_check_formatted = None
                if last_check_time:
                    last_check_formatted = datetime.fromtimestamp(last_check_time).strftime("%Y-%m-%d %H:%M:%S")

                stats.update({
                    "today_growth": today_growth,
                    "active_days": active_days,
                    "consecutive_active_days": consecutive_active_days,
                    "monitoring_increments": monitoring_increments,
                    "monitoring_days": len(daily_downloads),
                    "last_check_time": last_check_formatted
                })

            return stats

        except Exception as e:
            logger.error(f"获取插件 {plugin_id} 统计信息失败: {str(e)}")
            return {
                "plugin_id": plugin_id,
                "plugin_name": plugin_id,
                "current_downloads": 0,
                "error": str(e)
            }

    def stop_service(self):
        """停止插件服务"""
        try:
            if hasattr(self, 'stop_mcp_decorators'):
                # 停止MCP功能
                self.stop_mcp_decorators()
        except Exception as e:
            logger.error(f"停止MCP服务失败: {str(e)}")
