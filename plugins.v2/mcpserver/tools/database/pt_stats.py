import logging
import sqlite3
import os
import sys
from pathlib import Path
from typing import List, Dict, Any
import mcp.types as types
from ..base import BaseTool

# 添加父目录到路径，以便导入utils
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(parent_dir)

# Configure logging
logger = logging.getLogger(__name__)


class PTStatsTool(BaseTool):
    """PT站点数据统计分析工具"""
    
    def __init__(self, token_manager=None):
        super().__init__(token_manager)
        # 数据库路径 - 自动检测生产环境或开发环境
        self.db_path_candidates = []
        self.db_path = self._get_database_path()

    def _get_database_path(self) -> str:
        """自动检测数据库路径，兼容 Docker、Windows 和本地开发环境。"""
        candidates = self._get_database_path_candidates()
        self.db_path_candidates = candidates

        for candidate in candidates:
            if os.path.exists(candidate):
                logger.info(f"使用MoviePilot数据库: {candidate}")
                return candidate

        fallback = candidates[0] if candidates else "user.db"
        logger.warning(
            "数据库文件不存在，已尝试候选路径: %s",
            ", ".join(candidates) if candidates else fallback,
        )
        return fallback

    def _get_database_path_candidates(self) -> List[str]:
        """按优先级生成 user.db 候选路径。"""
        candidates = []

        def add_candidate(path_value):
            if not path_value:
                return
            path = Path(str(path_value)).expanduser()
            if path.name != "user.db":
                path = path / "user.db"
            candidate = str(path)
            if candidate not in candidates:
                candidates.append(candidate)

        # 显式配置优先：父进程会注入 MCPSERVER_USER_DB_PATH，用户也可手动设置。
        for env_name in (
            "MCPSERVER_USER_DB_PATH",
            "MOVIEPILOT_USER_DB_PATH",
            "MP_USER_DB_PATH",
            "USER_DB_PATH",
        ):
            add_candidate(os.environ.get(env_name))

        for env_name in (
            "MCPSERVER_CONFIG_PATH",
            "MOVIEPILOT_CONFIG_PATH",
            "MOVIEPILOT_CONFIG_DIR",
            "MP_CONFIG_PATH",
            "MP_CONFIG_DIR",
            "CONFIG_PATH",
        ):
            add_candidate(os.environ.get(env_name))

        # 如果工具进程能访问 MoviePilot settings，复用其配置目录。
        try:
            from app.core.config import settings

            add_candidate(getattr(settings, "CONFIG_PATH", None))
        except Exception as e:
            logger.debug(f"无法从MoviePilot settings读取CONFIG_PATH: {e}")

        plugin_dir = Path(__file__).resolve().parents[2]
        cwd = Path.cwd()

        # 常见 MoviePilot 与本地开发候选路径。
        for path in (
            Path("/config/user.db"),
            cwd / "user.db",
            cwd / "config" / "user.db",
            plugin_dir / "user.db",
            plugin_dir / "config" / "user.db",
            Path.home() / ".moviepilot" / "user.db",
            Path.home() / ".moviepilot" / "config" / "user.db",
            Path.home() / "MoviePilot" / "user.db",
            Path.home() / "MoviePilot" / "config" / "user.db",
        ):
            add_candidate(path)

        return candidates

    def _get_db_connection(self):
        """获取数据库连接"""
        if not os.path.exists(self.db_path):
            candidates = self.db_path_candidates or [self.db_path]
            raise FileNotFoundError(
                "数据库文件不存在，已尝试以下候选路径: "
                + "; ".join(candidates)
            )
        return sqlite3.connect(self.db_path)

    def _format_size(self, size_bytes: float) -> str:
        """格式化文件大小，大于1000GB时使用TB单位"""
        if size_bytes is None or size_bytes == 0:
            return "0 GB"

        # 转换为GB
        size_gb = size_bytes / (1024 * 1024 * 1024)

        # 如果大于1000GB，使用TB单位
        if size_gb >= 1000:
            size_tb = size_gb / 1024
            return f"{size_tb:,.2f} TB"
        else:
            return f"{size_gb:,.1f} GB"

    def _format_messages(self, message_unread: int, message_unread_contents: str) -> str:
        """格式化未读消息内容"""
        if not message_unread or message_unread == 0:
            return ""

        message_text = f"📬 未读消息: {message_unread}条\n"

        # 解析消息内容
        if message_unread_contents:
            try:
                import json
                contents = json.loads(message_unread_contents) if isinstance(message_unread_contents, str) else message_unread_contents
                if contents and isinstance(contents, list):
                    message_text += "📝 消息内容:\n"
                    for i, msg in enumerate(contents[:3], 1):  # 最多显示3条消息
                        if isinstance(msg, list) and len(msg) >= 3:
                            title = msg[0]
                            time = msg[1]
                            content = msg[2]
                            message_text += f"   {i}. {title} ({time})\n"
                            # 限制内容长度，避免过长
                            if len(content) > 100:
                                content = content[:100] + "..."
                            message_text += f"      {content}\n"
                    if len(contents) > 3:
                        message_text += f"   ... 还有{len(contents) - 3}条消息\n"
            except Exception as e:
                logger.warning(f"解析消息内容失败: {e}")
                message_text += "   (消息内容解析失败)\n"

        return message_text
    
    def _execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """执行SQL查询并返回结果"""
        try:
            with self._get_db_connection() as conn:
                conn.row_factory = sqlite3.Row  # 使结果可以按列名访问
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()
                # 转换为字典列表
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"数据库查询失败: {e}")
            raise
    
    async def execute(
        self, tool_name: str, arguments: dict
    ) -> List[types.TextContent]:
        """执行工具"""
        try:
            if tool_name == "query-pt-stats":
                site_domain = arguments.get("site_domain")
                site_name = arguments.get("site_name")
                return await self._get_single_site_stats(site_domain, site_name)
            else:
                return [
                    types.TextContent(
                        type="text",
                        text=f"错误：未知的工具 '{tool_name}'"
                    )
                ]
        except Exception as e:
            logger.error(f"工具执行失败: {e}")
            return [
                types.TextContent(
                    type="text",
                    text=f"查询失败: {str(e)}"
                )
            ]

    async def _get_single_site_stats(self, site_domain: str = None, site_name: str = None) -> List[types.TextContent]:
        """获取单个站点的详细统计数据"""
        if not site_domain and not site_name:
            return [
                types.TextContent(
                    type="text",
                    text="错误：请提供 site_domain 或 site_name 参数"
                )
            ]

        # 构建查询条件
        if site_domain:
            where_condition = "sud.domain = ?"
            param = site_domain
        else:
            where_condition = "s.name = ?"
            param = site_name

        query = f"""
        SELECT
            COALESCE(s.name, sud.domain) as site_name,
            sud.domain,
            ROUND(sud.bonus, 2) as bonus,
            sud.seeding as seeding_count,
            sud.seeding_size,
            sud.upload,
            sud.download,
            ROUND(sud.ratio, 2) as ratio,
            sud.user_level,
            sud.message_unread,
            sud.message_unread_contents,
            sud.updated_time
        FROM siteuserdata sud
        LEFT JOIN site s ON sud.domain = s.domain
        WHERE {where_condition}
        ORDER BY sud.rowid DESC
        LIMIT 1
        """

        results = self._execute_query(query, (param,))
        if not results:
            search_term = site_domain or site_name
            return [
                types.TextContent(
                    type="text",
                    text=f"未找到站点数据: {search_term}"
                )
            ]

        # 获取最新的记录
        site_data = results[0]

        # 格式化大小数据
        seeding_size_str = self._format_size(site_data['seeding_size'])
        upload_size_str = self._format_size(site_data['upload'])
        download_size_str = self._format_size(site_data['download'])

        # 格式化未读消息
        message_str = self._format_messages(site_data['message_unread'], site_data['message_unread_contents'])

        text = f"""🎯 {site_data['site_name']} 站点详细数据

🌐 站点域名: {site_data['domain']}
✨ 魔力值: {site_data['bonus']:,.2f}
🌱 做种数: {site_data['seeding_count']}个
💾 做种体积: {seeding_size_str}
⬆️ 上传量: {upload_size_str}
⬇️ 下载量: {download_size_str}
📊 分享率: {site_data['ratio']:.2f}
👤 用户等级: {site_data['user_level'] or '未知'}
🕒 更新时间: {site_data['updated_time'] or '未知'}
"""

        # 如果有未读消息，添加到结果中
        if message_str:
            text += "\n" + message_str

        return [types.TextContent(type="text", text=text)]
    
    @property
    def tool_info(self) -> types.Tool:
        """返回工具信息"""
        return types.Tool(
            name="query-pt-stats",
            description="查询PT站点详细数据统计，获取指定站点的魔力值、做种数、上传下载量、分享率等信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "site_domain": {
                        "type": "string",
                        "description": "站点域名（与site_name二选一；如果同时提供，优先使用site_domain）"
                    },
                    "site_name": {
                        "type": "string",
                        "description": "站点名称（与site_domain二选一；如果同时提供，优先使用site_domain）"
                    }
                },
                "description": "必须提供 site_domain 或 site_name 中的一个参数；如果同时提供，优先使用 site_domain。"
            }
        )
