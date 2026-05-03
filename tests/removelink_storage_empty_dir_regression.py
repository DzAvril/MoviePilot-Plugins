#!/usr/bin/env python3
"""
Regression check for RemoveLink STRM cloud empty-directory cleanup.

Run inside the plugin repository:
    python3 tests/removelink_storage_empty_dir_regression.py
"""

from dataclasses import dataclass
from pathlib import Path
import importlib.util
import sys
import types


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class FileItem:
    storage: str
    path: str
    type: str
    name: str = ""
    extension: str = ""

    def copy(self, update=None):
        data = self.__dict__.copy()
        data.update(update or {})
        return FileItem(**data)


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


class PluginBase:
    def post_message(self, *args, **kwargs):
        pass


class StorageChain:
    pass


class TransferHistoryOper:
    pass


class FileSystemEventHandler:
    pass


class PollingObserver:
    pass


def install_import_stubs():
    watchdog = types.ModuleType("watchdog")
    watchdog_events = types.ModuleType("watchdog.events")
    watchdog_events.FileSystemEventHandler = FileSystemEventHandler
    watchdog_observers = types.ModuleType("watchdog.observers")
    watchdog_polling = types.ModuleType("watchdog.observers.polling")
    watchdog_polling.PollingObserver = PollingObserver

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
    app_schemas_types.EventType = types.SimpleNamespace(DownloadFileDeleted="DownloadFileDeleted")

    app_chain = types.ModuleType("app.chain")
    app_chain_storage = types.ModuleType("app.chain.storage")
    app_chain_storage.StorageChain = StorageChain

    sys.modules.update(
        {
            "watchdog": watchdog,
            "watchdog.events": watchdog_events,
            "watchdog.observers": watchdog_observers,
            "watchdog.observers.polling": watchdog_polling,
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


class MockStorageChain:
    def __init__(self):
        self.calls = []
        self.children = {
            "/test/dir/": [
                FileItem(
                    storage="alist",
                    path="/test/dir/nulldirectory",
                    type="dir",
                    name="nulldirectory",
                )
            ],
            "/test/dir/nulldirectory": [],
            "/test/": [
                FileItem(storage="alist", path="/test/dir", type="dir", name="dir")
            ],
            "/test/dir": [
                FileItem(
                    storage="alist",
                    path="/test/dir/another-show",
                    type="dir",
                    name="another-show",
                )
            ],
        }

    def exists(self, file_item):
        self.calls.append(("exists", file_item.path, file_item.type))
        return True

    def list_files(self, file_item, recursion=False):
        self.calls.append(("list_files", file_item.path, file_item.type, recursion))
        return self.children[file_item.path]

    def delete_file(self, file_item):
        endpoint = (
            "/api/fs/remove_empty_directory"
            if file_item.type == "dir"
            else "/api/fs/remove"
        )
        self.calls.append((endpoint, file_item.path, file_item.type, file_item.name))
        return True


def main():
    RemoveLink = load_removelink_class()
    plugin = RemoveLink()
    plugin._storagechain = MockStorageChain()
    plugin._delete_scrap_infos = False

    deleted = plugin._delete_storage_empty_folders(
        "alist",
        FileItem(
            storage="alist",
            path="/test/dir/nulldirectory/movie.mkv",
            type="file",
            name="movie.mkv",
        ),
    )

    remove_calls = [
        call for call in plugin._storagechain.calls if call[0] == "/api/fs/remove"
    ]
    empty_dir_calls = [
        call
        for call in plugin._storagechain.calls
        if call[0] == "/api/fs/remove_empty_directory"
    ]

    assert deleted == 1, plugin._storagechain.calls
    assert remove_calls == [
        ("/api/fs/remove", "/test/dir/nulldirectory", "file", "nulldirectory")
    ], plugin._storagechain.calls
    assert empty_dir_calls == [], plugin._storagechain.calls

    print("PASS: empty dir /test/dir/nulldirectory is deleted via /api/fs/remove only")


if __name__ == "__main__":
    main()
