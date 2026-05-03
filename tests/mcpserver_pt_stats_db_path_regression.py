#!/usr/bin/env python3
"""
Regression check for MCPServer PT stats database path detection.

Run inside the plugin repository:
    python3 tests/mcpserver_pt_stats_db_path_regression.py
"""

import importlib.util
import os
import sqlite3
import sys
import tempfile
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PT_STATS_FILE = (
    REPO_ROOT / "plugins.v2" / "mcpserver" / "tools" / "database" / "pt_stats.py"
)


class BaseTool:
    def __init__(self, token_manager=None):
        self.token_manager = token_manager


class TextContent:
    def __init__(self, type, text):
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
    mcp_types.Tool = Tool
    mcp.types = mcp_types

    package_names = [
        "mcpserver",
        "mcpserver.tools",
        "mcpserver.tools.database",
    ]
    packages = {}
    for name in package_names:
        package = types.ModuleType(name)
        package.__path__ = []
        packages[name] = package

    base = types.ModuleType("mcpserver.tools.base")
    base.BaseTool = BaseTool

    sys.modules.update(
        {
            "mcp": mcp,
            "mcp.types": mcp_types,
            **packages,
            "mcpserver.tools.base": base,
        }
    )


def load_pt_stats_tool():
    install_import_stubs()
    module_name = "mcpserver.tools.database.pt_stats"
    spec = importlib.util.spec_from_file_location(module_name, PT_STATS_FILE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.PTStatsTool


def reset_db_path_env():
    for env_name in (
        "MCPSERVER_USER_DB_PATH",
        "MOVIEPILOT_USER_DB_PATH",
        "MP_USER_DB_PATH",
        "USER_DB_PATH",
        "MCPSERVER_CONFIG_PATH",
        "MOVIEPILOT_CONFIG_PATH",
        "MOVIEPILOT_CONFIG_DIR",
        "MP_CONFIG_PATH",
        "MP_CONFIG_DIR",
        "CONFIG_PATH",
    ):
        os.environ.pop(env_name, None)


def main():
    original_cwd = os.getcwd()
    PTStatsTool = load_pt_stats_tool()

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_dir = temp_path / "MoviePilot Config"
            config_dir.mkdir()
            db_path = config_dir / "user.db"

            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE marker (id INTEGER PRIMARY KEY)")
                conn.execute("INSERT INTO marker DEFAULT VALUES")

            os.chdir(temp_path)
            reset_db_path_env()
            os.environ["MCPSERVER_USER_DB_PATH"] = str(db_path)

            tool = PTStatsTool()
            assert Path(tool.db_path) == db_path, tool.db_path
            with tool._get_db_connection() as conn:
                count = conn.execute("SELECT COUNT(*) FROM marker").fetchone()[0]
            assert count == 1, count

            reset_db_path_env()
            missing_db = temp_path / "missing-config" / "user.db"
            os.environ["MCPSERVER_USER_DB_PATH"] = str(missing_db)

            missing_tool = PTStatsTool()
            try:
                missing_tool._get_db_connection()
            except FileNotFoundError as e:
                message = str(e)
            else:
                raise AssertionError("expected FileNotFoundError for missing user.db")

            assert "已尝试以下候选路径" in message, message
            assert str(missing_db) in message, message
    finally:
        os.chdir(original_cwd)
        reset_db_path_env()

    print("PASS: MCPServer PT stats finds configured user.db and reports candidates")


if __name__ == "__main__":
    main()
