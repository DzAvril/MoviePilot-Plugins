import json
import logging
import re
import mcp.types as types
from ..base import BaseTool


# Configure logging
logger = logging.getLogger(__name__)


class UserInfoTool(BaseTool):
    _IMAGE_FIELD_NAMES = ("avatar", "image", "icon")
    _MAX_STRING_LENGTH = 500
    _MAX_COLLECTION_ITEMS = 20
    _MAX_NESTING_DEPTH = 4

    async def execute(
        self, tool_name: str, arguments: dict
    ) -> list[types.TextContent]:
        if tool_name == "user-info":
            return await self._get_current_user()
        elif tool_name == "get-user":
            return await self._get_user_by_name(arguments.get("username"))
        else:
            return [
                types.TextContent(
                    type="text",
                    text=f"错误：未知的工具 '{tool_name}'"
                )
            ]

    async def _get_current_user(self) -> list[types.TextContent]:
        """获取当前用户信息"""
        response = await self._make_request(
            method="GET",
            endpoint="/api/v1/user/current"
        )
        return self._format_user_response(response, "当前用户信息")

    async def _get_user_by_name(
        self, username: str
    ) -> list[types.TextContent]:
        """获取指定用户信息"""
        if not username:
            return [
                types.TextContent(
                    type="text",
                    text="错误：请提供用户名"
                )
            ]

        response = await self._make_request(
            method="GET",
            endpoint=f"/api/v1/user/{username}"
        )
        return self._format_user_response(response, f"用户 {username} 的信息")

    def _format_user_response(
        self, response: dict, title: str
    ) -> list[types.TextContent]:
        """格式化用户信息响应"""
        if "error" in response:
            return [
                types.TextContent(
                    type="text",
                    text=f"获取用户信息失败: {response['error']}"
                )
            ]

        user_info = []
        for key, value in response.items():
            value = self._sanitize_user_value(key, value)
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, indent=2)
            user_info.append(f"{key}: {value}")

        return [
            types.TextContent(
                type="text",
                text=f"{title}:\n" + "\n".join(user_info)
            )
        ]

    def _sanitize_user_value(self, key, value, depth=0):
        """移除用户信息中不适合返回给MCP客户端的大字段"""
        if depth >= self._MAX_NESTING_DEPTH:
            return self._omitted_placeholder(value, "nested value")

        if isinstance(value, str):
            return self._sanitize_user_string(key, value)

        if isinstance(value, list):
            sanitized = [
                self._sanitize_user_value(key, item, depth + 1)
                for item in value[:self._MAX_COLLECTION_ITEMS]
            ]
            if len(value) > self._MAX_COLLECTION_ITEMS:
                sanitized.append(
                    f"[list truncated, {len(value) - self._MAX_COLLECTION_ITEMS} items omitted]"
                )
            return sanitized

        if isinstance(value, dict):
            sanitized = {}
            for index, (child_key, child_value) in enumerate(value.items()):
                if index >= self._MAX_COLLECTION_ITEMS:
                    sanitized["..."] = (
                        f"[dict truncated, {len(value) - self._MAX_COLLECTION_ITEMS} fields omitted]"
                    )
                    break
                sanitized[child_key] = self._sanitize_user_value(
                    child_key, child_value, depth + 1
                )
            return sanitized

        return value

    def _sanitize_user_string(self, key, value: str) -> str:
        if self._is_base64_data_image(value):
            return self._omitted_placeholder(value, "base64 image")

        if self._is_image_field(key) and len(value) > self._MAX_STRING_LENGTH:
            if re.match(r"^https?://", value, re.IGNORECASE):
                return value
            return self._omitted_placeholder(value, "large image field")

        if len(value) > self._MAX_STRING_LENGTH:
            return (
                value[:self._MAX_STRING_LENGTH]
                + f"... [truncated, {len(value) - self._MAX_STRING_LENGTH} chars omitted]"
            )

        return value

    def _is_base64_data_image(self, value: str) -> bool:
        return bool(
            re.match(r"^\s*data:image/[^,]*;base64,", value, re.IGNORECASE)
        )

    def _is_image_field(self, key) -> bool:
        key_text = str(key).lower()
        return any(field_name in key_text for field_name in self._IMAGE_FIELD_NAMES)

    def _omitted_placeholder(self, value, label: str) -> str:
        if isinstance(value, str):
            length = len(value)
        else:
            try:
                length = len(json.dumps(value, ensure_ascii=False))
            except (TypeError, ValueError):
                length = len(str(value))
        return f"[{label} omitted, {length} chars]"

    @property
    def tool_info(self) -> list[types.Tool]:
        return [
            types.Tool(
                name="user-info",
                description="获取当前用户信息",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            types.Tool(
                name="get-user",
                description="获取指定用户信息",
                inputSchema={
                    "type": "object",
                    "required": ["username"],
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "要查询的用户名"
                        }
                    },
                },
            )
        ]
