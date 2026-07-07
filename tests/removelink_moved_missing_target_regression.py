#!/usr/bin/env python3
"""
Regression check for RemoveLink moved events whose target has already vanished.

Run inside the plugin repository:
    python3 tests/removelink_moved_missing_target_regression.py
"""

from dataclasses import dataclass
from datetime import datetime
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


class MoveEvent:
    is_directory = False

    def __init__(self, src_path, dest_path):
        self.src_path = str(src_path)
        self.dest_path = str(dest_path)


def main():
    module, _ = load_removelink_module()
    plugin = module.RemoveLink()
    plugin._delayed_deletion = True
    plugin._delay_seconds = 60
    plugin.deletion_queue = []
    plugin._deletion_timer = None
    plugin.exclude_keywords = ""

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        src = root / "source" / "episode02.mkv"
        transient_dest = root / "source__tmp" / "episode02.mkv"
        src.parent.mkdir()
        transient_dest.parent.mkdir()
        src.write_bytes(b"episode")
        stat_info = src.stat()
        add_time = datetime.now()
        plugin.file_state = {
            str(src): module.FileInfo(
                dev=stat_info.st_dev,
                inode=stat_info.st_ino,
                add_time=add_time,
            )
        }

        # Simulate watchfiles reporting a move during a whole-directory removal:
        # the source is gone and the transient target no longer exists by the time
        # the handler tries to add it to file_state.
        src.unlink()
        handler = module.FileMonitorHandler(str(root), plugin)
        handler.on_moved(MoveEvent(src, transient_dest))

        assert str(src) not in plugin.file_state
        assert str(transient_dest) not in plugin.file_state
        assert len(plugin.deletion_queue) == 1
        task = plugin.deletion_queue[0]
        assert task.file_path == src
        assert task.deleted_dev == stat_info.st_dev
        assert task.deleted_inode == stat_info.st_ino
        assert task.deleted_add_time == add_time
        assert plugin._deletion_timer is not None
        plugin._deletion_timer.cancel()

    # A normal rename/move where the destination still exists must only update
    # file_state and must not schedule cleanup.
    plugin.deletion_queue = []
    plugin._deletion_timer = None
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        src = root / "library" / "movie.mp"
        dest = root / "library" / "movie.mkv"
        src.parent.mkdir()
        src.write_bytes(b"movie")
        stat_info = src.stat()
        add_time = datetime.now()
        plugin.file_state = {
            str(src): module.FileInfo(
                dev=stat_info.st_dev,
                inode=stat_info.st_ino,
                add_time=add_time,
            )
        }
        os.rename(src, dest)

        handler = module.FileMonitorHandler(str(root), plugin)
        handler.on_moved(MoveEvent(src, dest))

        assert str(src) not in plugin.file_state
        assert str(dest) in plugin.file_state
        assert len(plugin.deletion_queue) == 0
        assert plugin._deletion_timer is None

    print("PASS: moved event with missing target is queued as source deletion without breaking normal renames")


if __name__ == "__main__":
    main()
