#!/usr/bin/env python3
"""
Regression check for RemoveLink startup without watchdog.

Run inside the plugin repository:
    python3 tests/removelink_watchfiles_compat_regression.py
"""

from dataclasses import dataclass
from pathlib import Path
import importlib.util
import sys
import tempfile
import types


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class FileItem:
    storage: str
    path: str
    type: str
    name: str = ""
    extension: str = ""


class Logger:
    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    warn = warning

    def error(self, *args, **kwargs):
        pass


class SystemMessage:
    def __init__(self):
        self.messages = []

    def put(self, *args, **kwargs):
        self.messages.append((args, kwargs))


class PluginBase:
    def __init__(self):
        self.systemmessage = SystemMessage()

    def post_message(self, *args, **kwargs):
        pass


class TransferHistoryOper:
    pass


class StorageChain:
    pass


class Change:
    added = "added"
    deleted = "deleted"
    modified = "modified"


WATCH_CALLS = []


def watch(path, **kwargs):
    WATCH_CALLS.append((path, kwargs))
    return iter(())


def install_import_stubs():
    for module_name in list(sys.modules):
        if module_name == "watchdog" or module_name.startswith("watchdog."):
            del sys.modules[module_name]

    watchfiles = types.ModuleType("watchfiles")
    watchfiles.Change = Change
    watchfiles.watch = watch

    app = types.ModuleType("app")
    schemas = types.ModuleType("app.schemas")
    schemas.FileItem = FileItem
    schemas.NotificationType = types.SimpleNamespace(SiteMessage="SiteMessage")
    app.schemas = schemas

    app_db = types.ModuleType("app.db")
    transferhistory_oper = types.ModuleType("app.db.transferhistory_oper")
    transferhistory_oper.TransferHistoryOper = TransferHistoryOper

    app_log = types.ModuleType("app.log")
    app_log.logger = Logger()

    app_plugins = types.ModuleType("app.plugins")
    app_plugins._PluginBase = PluginBase

    app_core = types.ModuleType("app.core")
    app_core_event = types.ModuleType("app.core.event")
    app_core_event.eventmanager = types.SimpleNamespace(send_event=lambda *a, **k: None)

    app_schemas_types = types.ModuleType("app.schemas.types")
    app_schemas_types.EventType = types.SimpleNamespace(
        DownloadFileDeleted="DownloadFileDeleted"
    )

    app_chain = types.ModuleType("app.chain")
    app_chain_storage = types.ModuleType("app.chain.storage")
    app_chain_storage.StorageChain = StorageChain

    sys.modules.update(
        {
            "watchfiles": watchfiles,
            "app": app,
            "app.schemas": schemas,
            "app.db": app_db,
            "app.db.transferhistory_oper": transferhistory_oper,
            "app.log": app_log,
            "app.plugins": app_plugins,
            "app.core": app_core,
            "app.core.event": app_core_event,
            "app.schemas.types": app_schemas_types,
            "app.chain": app_chain,
            "app.chain.storage": app_chain_storage,
        }
    )


def load_removelink_class():
    install_import_stubs()
    plugin_file = REPO_ROOT / "plugins" / "removelink" / "__init__.py"
    spec = importlib.util.spec_from_file_location("removelink_plugin", plugin_file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.RemoveLink


def main():
    RemoveLink = load_removelink_class()
    plugin = RemoveLink()

    with tempfile.TemporaryDirectory() as tmp_dir:
        plugin.init_plugin(
            {
                "enabled": True,
                "monitor_dirs": tmp_dir,
                "monitor_strm_deletion": False,
                "delayed_deletion": True,
            }
        )
        plugin.stop_service()

    assert WATCH_CALLS, "watchfiles.watch was not used for monitoring fallback"
    assert plugin.systemmessage.messages == []

    print("PASS: RemoveLink imports and starts with watchfiles when watchdog is absent")


if __name__ == "__main__":
    main()
