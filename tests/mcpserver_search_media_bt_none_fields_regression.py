#!/usr/bin/env python3
"""
Regression check for MCPServer search result formatting with BT site resources.

Run inside the plugin repository:
    python3 tests/mcpserver_search_media_bt_none_fields_regression.py
"""

import importlib.util
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD_FILE = (
    REPO_ROOT / "plugins.v2" / "mcpserver" / "tools" / "media" / "download.py"
)


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


class MediaRecognizeTool:
    def __init__(self, token_manager=None):
        self.token_manager = token_manager


class ResourceCache:
    def __init__(self):
        self.stored = {}

    def generate_resource_id(self, torrent_info):
        assert isinstance(torrent_info, dict), type(torrent_info)
        return "res_bt_regression"

    def store_resource(self, resource_id, torrent_info):
        assert isinstance(torrent_info, dict), type(torrent_info)
        self.stored[resource_id] = torrent_info
        return True


def install_import_stubs():
    mcp = types.ModuleType("mcp")
    mcp_types = types.ModuleType("mcp.types")
    mcp_types.TextContent = TextContent
    mcp_types.ImageContent = TextContent
    mcp_types.Tool = Tool
    mcp.types = mcp_types

    package_names = [
        "mcpserver",
        "mcpserver.tools",
        "mcpserver.tools.media",
    ]
    packages = {}
    for name in package_names:
        package = types.ModuleType(name)
        package.__path__ = []
        packages[name] = package

    base = types.ModuleType("mcpserver.tools.base")
    base.BaseTool = BaseTool

    recognize = types.ModuleType("mcpserver.tools.media.recognize")
    recognize.MediaRecognizeTool = MediaRecognizeTool

    resource_cache_module = types.ModuleType("mcpserver.tools.resource_cache")
    resource_cache_module.resource_cache = ResourceCache()

    sys.modules.update(
        {
            "mcp": mcp,
            "mcp.types": mcp_types,
            **packages,
            "mcpserver.tools.base": base,
            "mcpserver.tools.media.recognize": recognize,
            "mcpserver.tools.resource_cache": resource_cache_module,
        }
    )


def load_download_module():
    module_name = "mcpserver.tools.media.download"
    spec = importlib.util.spec_from_file_location(module_name, DOWNLOAD_FILE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main():
    install_import_stubs()
    download = load_download_module()
    tool = download.MovieDownloadTool()

    bt_like_torrents = [
        {
            "torrent_info": {
                "description": None,
                "title": None,
                "site_name": "Mikan",
                "size": 734003200,
                "seeders": None,
                "peers": None,
                "enclosure": "https://mikanani.me/Download/2026/test.torrent",
            },
            "meta_info": {
                "subtitle": None,
                "org_string": None,
                "video_encode": None,
                "audio_encode": None,
                "resource_type": None,
            },
        },
        {
            "torrent_info": ["unexpected nested shape"],
            "meta_info": "unexpected nested shape",
            "description": None,
            "title": "ACG.RIP BT fallback title 1080p",
            "site_name": "ACG.RIP",
            "enclosure": "https://acg.rip/t/1.torrent",
        },
    ]

    output = tool._format_search_results(
        bt_like_torrents,
        keyword="动画",
        detailed=True,
        limit=50,
    )

    assert "搜索媒体资源时出错" not in output, output
    assert "argument of type NoneType is not iterable" not in output, output
    assert "资源标识符: res_bt_regression" in output, output
    assert "Mikan" in output, output
    assert "ACG.RIP BT fallback title 1080p" in output, output

    print("PASS: MCPServer formats BT search resources with nullable fields")


if __name__ == "__main__":
    main()
