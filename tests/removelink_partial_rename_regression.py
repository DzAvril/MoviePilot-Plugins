#!/usr/bin/env python3
"""
Regression check for RemoveLink when a downloader renames an incomplete file to a
temporary name (Transmission ``X.mkv.part`` / qBittorrent ``X.mkv.!qB``).

The rename keeps the same file entity (dev+inode) on disk, so it must not be
treated as "source deleted" and must not remove the library hardlinks.

Run inside the plugin repository:
    python3 tests/removelink_partial_rename_regression.py
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


def make_plugin(module, delayed: bool):
    plugin = module.RemoveLink()
    plugin._delayed_deletion = delayed
    plugin._delay_seconds = 60
    plugin._delete_scrap_infos = False
    plugin._delete_torrents = False
    plugin._delete_history = False
    plugin._notify = True
    plugin.deletion_queue = []
    plugin._deletion_timer = None
    plugin.exclude_dirs = ""
    plugin.exclude_keywords = ""
    plugin.monitor_dirs = ""
    return plugin


def make_source_and_link(root: Path):
    """Create a download source and its library hardlink, both tracked."""
    src = root / "download" / "Show.S01E01.1080p.mkv"
    link = root / "library" / "Show (2024)" / "Season 1" / "Show - S01E01 - 第 1 集.mkv"
    src.parent.mkdir(parents=True)
    link.parent.mkdir(parents=True)
    src.write_bytes(b"episode")
    os.link(src, link)
    stat_info = src.stat()
    add_time = datetime.now()
    file_state = {
        str(src): FileInfoFactory(stat_info, add_time),
        str(link): FileInfoFactory(stat_info, add_time),
    }
    return src, link, stat_info, file_state


FileInfoFactory = None


def main():
    global FileInfoFactory
    module, eventmanager = load_removelink_module()
    FileInfoFactory = lambda stat_info, add_time: module.FileInfo(  # noqa: E731
        dev=stat_info.st_dev, inode=stat_info.st_ino, add_time=add_time
    )

    # Case 1: watchdog moved event X.mkv -> X.mkv.part (Transmission rename-partial-files).
    # The target is filtered as a temp file, but the entity still exists: no cleanup.
    plugin = make_plugin(module, delayed=True)
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        src, link, stat_info, plugin.file_state = make_source_and_link(root)
        part = src.with_name(src.name + ".part")
        os.rename(src, part)

        handler = module.FileMonitorHandler(str(root), plugin)
        handler.on_moved(MoveEvent(src, part))

        assert str(src) not in plugin.file_state
        assert str(part) not in plugin.file_state, "temp file must stay filtered"
        assert str(link) in plugin.file_state
        assert plugin.deletion_queue == [], "rename to .part must not queue deletion"
        assert plugin._deletion_timer is None
        assert link.exists()

        # Downloader finishes and renames back: the source is tracked again.
        os.rename(part, src)
        handler.on_moved(MoveEvent(part, src))
        assert str(src) in plugin.file_state
        assert plugin.deletion_queue == []

    # Case 2: watchfiles compat mode only reports deleted(X.mkv); the delayed task
    # must notice X.mkv.part still points at the same entity and skip cleanup.
    plugin = make_plugin(module, delayed=True)
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        src, link, stat_info, plugin.file_state = make_source_and_link(root)
        os.rename(src, src.with_name(src.name + ".!qB"))

        plugin.handle_deleted(src)
        assert len(plugin.deletion_queue) == 1
        plugin._deletion_timer.cancel()
        task = plugin.deletion_queue[0]

        plugin._execute_delayed_deletion(task)
        assert link.exists(), "library hardlink must survive a .!qB rename"
        assert str(link) in plugin.file_state
        assert plugin.messages == []
        assert eventmanager.calls == []

    # Case 3: immediate mode with a .part rename must also keep the hardlink.
    plugin = make_plugin(module, delayed=False)
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        src, link, stat_info, plugin.file_state = make_source_and_link(root)
        os.rename(src, src.with_name(src.name + ".part"))

        plugin.handle_deleted(src)
        assert link.exists(), "library hardlink must survive a .part rename"
        assert str(link) in plugin.file_state
        assert plugin.messages == []

    # Case 4 (control): a real deletion still removes the hardlink in both modes.
    for delayed in (True, False):
        plugin = make_plugin(module, delayed=delayed)
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            src, link, stat_info, plugin.file_state = make_source_and_link(root)
            src.unlink()

            plugin.handle_deleted(src)
            if delayed:
                assert len(plugin.deletion_queue) == 1
                plugin._deletion_timer.cancel()
                plugin._execute_delayed_deletion(plugin.deletion_queue[0])
            assert not link.exists(), "real deletion must still remove the hardlink"
            assert str(link) not in plugin.file_state
            assert len(plugin.messages) == 1

    # Case 5: a stale .part next to a *different* entity must not mask a real deletion.
    plugin = make_plugin(module, delayed=False)
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        src, link, stat_info, plugin.file_state = make_source_and_link(root)
        src.unlink()
        src.with_name(src.name + ".part").write_bytes(b"unrelated new download")

        plugin.handle_deleted(src)
        assert not link.exists(), "unrelated .part must not block cleanup"

    print("PASS: downloader temp renames (.part/.!qB) keep library hardlinks; real deletions still clean up")


if __name__ == "__main__":
    main()
