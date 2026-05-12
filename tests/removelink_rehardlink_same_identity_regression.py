#!/usr/bin/env python3
"""
Regression check for RemoveLink re-organize hardlink handling.

Run inside the plugin repository:
    python3 tests/removelink_rehardlink_same_identity_regression.py
"""

from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
import importlib.util
import os
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


class PluginBase:
    def __init__(self):
        self.messages = []

    def post_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))


class TransferHistoryOper:
    pass


class StorageChain:
    pass


class FileSystemEventHandler:
    pass


class PollingObserver:
    pass


class EventManager:
    def __init__(self):
        self.calls = []

    def send_event(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def install_import_stubs():
    eventmanager = EventManager()

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
    app_core_event.eventmanager = eventmanager

    app_schemas_types = types.ModuleType("app.schemas.types")
    app_schemas_types.EventType = types.SimpleNamespace(
        DownloadFileDeleted="DownloadFileDeleted"
    )

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
    return eventmanager


def load_removelink_module():
    eventmanager = install_import_stubs()
    plugin_file = REPO_ROOT / "plugins" / "removelink" / "__init__.py"
    spec = importlib.util.spec_from_file_location("removelink_plugin", plugin_file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, eventmanager


def main():
    module, eventmanager = load_removelink_module()
    plugin = module.RemoveLink()
    plugin._notify = True
    plugin._delete_history = True
    plugin._delete_torrents = True
    plugin._delete_scrap_infos = True

    history_calls = []
    scrap_calls = []
    plugin.delete_history = lambda path: history_calls.append(path)
    plugin.delete_scrap_infos = lambda path: scrap_calls.append(path)

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        source = root / "source" / "movie.mkv"
        old_link = root / "library-old" / "movie.mkv"
        new_link = root / "library-new" / "movie.mkv"
        source.parent.mkdir()
        old_link.parent.mkdir()
        new_link.parent.mkdir()
        source.write_bytes(b"movie")
        os.link(source, old_link)
        os.link(source, new_link)

        stat_info = old_link.stat()
        old_add_time = datetime.now() - timedelta(seconds=2)
        new_add_time = datetime.now() - timedelta(seconds=1)
        task_time = datetime.now()

        plugin.file_state = {
            str(old_link): module.FileInfo(
                dev=stat_info.st_dev,
                inode=stat_info.st_ino,
                add_time=old_add_time,
            ),
            str(new_link): module.FileInfo(
                dev=stat_info.st_dev,
                inode=stat_info.st_ino,
                add_time=new_add_time,
            ),
        }

        old_link.unlink()
        task = module.DeletionTask(
            file_path=old_link,
            deleted_dev=stat_info.st_dev,
            deleted_inode=stat_info.st_ino,
            deleted_add_time=old_add_time,
            timestamp=task_time,
        )

        plugin._execute_delayed_deletion(task)

        assert task.processed is True
        assert new_link.exists(), "newer same device+inode hardlink was deleted"
        assert str(new_link) in plugin.file_state
        assert plugin.messages == []
        assert history_calls == []
        assert scrap_calls == []
        assert eventmanager.calls == []

    print("PASS: newer same device+inode re-hardlink skips deletion and notifications")


if __name__ == "__main__":
    main()
