#!/usr/bin/env python3
"""
Regression checks for MCPServer OpenAI-compatible schemas and user info output.

Run inside the plugin repository:
    python3 tests/mcpserver_openai_schema_user_info_regression.py
"""

import importlib.util
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
USER_INFO_FILE = REPO_ROOT / "plugins.v2" / "mcpserver" / "tools" / "user" / "info.py"
PT_STATS_FILE = (
    REPO_ROOT / "plugins.v2" / "mcpserver" / "tools" / "database" / "pt_stats.py"
)
BUILTIN_TOOL_FILES = [
    ("mcpserver.tools.user.info", USER_INFO_FILE),
    ("mcpserver.tools.site.sites", REPO_ROOT / "plugins.v2" / "mcpserver" / "tools" / "site" / "sites.py"),
    ("mcpserver.tools.media.recognize", REPO_ROOT / "plugins.v2" / "mcpserver" / "tools" / "media" / "recognize.py"),
    ("mcpserver.tools.media.subscribe", REPO_ROOT / "plugins.v2" / "mcpserver" / "tools" / "media" / "subscribe.py"),
    ("mcpserver.tools.media.download", REPO_ROOT / "plugins.v2" / "mcpserver" / "tools" / "media" / "download.py"),
    ("mcpserver.tools.database.pt_stats", PT_STATS_FILE),
]
COMBINATORS = ("anyOf", "oneOf", "allOf", "not")
TOP_LEVEL_FORBIDDEN = (*COMBINATORS, "enum")


class BaseTool:
    def __init__(self, token_manager=None):
        self.token_manager = token_manager


class TextContent:
    def __init__(self, type, text=None, **kwargs):
        self.type = type
        self.text = text


class Tool:
    def __init__(self, name, description, inputSchema):
        self.name = name
        self.description = description
        self.inputSchema = inputSchema


def install_import_stubs():
    mcp = types.ModuleType("mcp")
    mcp_types = types.ModuleType("mcp.types")
    mcp_types.TextContent = TextContent
    mcp_types.ImageContent = TextContent
    mcp_types.EmbeddedResource = TextContent
    mcp_types.Tool = Tool
    mcp.types = mcp_types

    anyio = types.ModuleType("anyio")

    async def sleep(*args, **kwargs):
        return None

    anyio.sleep = sleep

    package_names = [
        "mcpserver",
        "mcpserver.tools",
        "mcpserver.tools.user",
        "mcpserver.tools.site",
        "mcpserver.tools.media",
        "mcpserver.tools.database",
    ]
    packages = {}
    for name in package_names:
        package = types.ModuleType(name)
        package.__path__ = []
        packages[name] = package

    base = types.ModuleType("mcpserver.tools.base")
    base.BaseTool = BaseTool

    resource_cache_module = types.ModuleType("mcpserver.tools.resource_cache")

    class ResourceCache:
        def generate_resource_id(self, torrent_info):
            return "resource-id"

        def store_resource(self, *args, **kwargs):
            return None

        def get_resource(self, *args, **kwargs):
            return None

    resource_cache_module.resource_cache = ResourceCache()

    sys.modules.update(
        {
            "mcp": mcp,
            "mcp.types": mcp_types,
            "anyio": anyio,
            **packages,
            "mcpserver.tools.base": base,
            "mcpserver.tools.resource_cache": resource_cache_module,
        }
    )


def load_module(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def assert_no_type_with_combinator(node, path="$"):
    if isinstance(node, dict):
        if "type" in node:
            conflicts = sorted(key for key in COMBINATORS if key in node)
            assert not conflicts, f"{path} has type with {conflicts}"
        for key, value in node.items():
            assert_no_type_with_combinator(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, item in enumerate(node):
            assert_no_type_with_combinator(item, f"{path}[{index}]")


def get_tool(tool_info, tool_name):
    tools = tool_info if isinstance(tool_info, list) else [tool_info]
    for tool in tools:
        if tool.name == tool_name:
            return tool
    raise AssertionError(f"missing tool {tool_name}")


def iter_tool_classes(modules):
    for module in modules:
        for value in module.__dict__.values():
            if (
                isinstance(value, type)
                and value is not BaseTool
                and value.__name__.endswith("Tool")
            ):
                yield value


def assert_openai_compatible_schema(tool):
    schema = tool.inputSchema
    assert schema.get("type") == "object", f"{tool.name} schema must be object: {schema}"
    for key in TOP_LEVEL_FORBIDDEN:
        assert key not in schema, f"{tool.name} top-level {key} should not be present"
    assert_no_type_with_combinator(schema, f"tool:{tool.name}")


def main():
    install_import_stubs()
    modules = [
        load_module(module_name, file_path)
        for module_name, file_path in BUILTIN_TOOL_FILES
    ]
    user_module = sys.modules["mcpserver.tools.user.info"]
    pt_stats_module = sys.modules["mcpserver.tools.database.pt_stats"]

    user_tool = user_module.UserInfoTool()
    custom_avatar = "data:image/png;base64," + ("a" * 12000)
    response = {
        "username": "alice",
        "nickname": "测试用户",
        "avatar": custom_avatar,
        "profile": {
            "custom_avatar": custom_avatar,
            "roles": ["admin", "user"],
        },
    }
    text = user_tool._format_user_response(response, "用户 alice 的信息")[0].text
    assert "data:image/png;base64" not in text, text[:200]
    assert "[base64 image omitted, 12022 chars]" in text, text
    assert len(text) < 2000, len(text)

    http_avatar = "https://example.com/avatar.png"
    http_text = user_tool._format_user_response(
        {"username": "bob", "avatar": http_avatar}, "用户 bob 的信息"
    )[0].text
    assert http_avatar in http_text, http_text

    pt_tool = pt_stats_module.PTStatsTool()
    query_tool = get_tool(pt_tool.tool_info, "query-pt-stats")
    schema = query_tool.inputSchema
    assert "site_domain" in schema["properties"], schema
    assert "site_name" in schema["properties"], schema

    checked_tools = 0
    for tool_class in iter_tool_classes(modules):
        tool_infos = tool_class().tool_info
        if not isinstance(tool_infos, list):
            tool_infos = [tool_infos]
        for tool in tool_infos:
            assert_openai_compatible_schema(tool)
            checked_tools += 1
    assert checked_tools >= 20, checked_tools

    print(
        "PASS: MCPServer schemas are OpenAI-compatible "
        f"({checked_tools} tools) and user avatars are trimmed"
    )


if __name__ == "__main__":
    main()
