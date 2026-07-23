#!/usr/bin/env python3
"""Regression for RemoveLink issues #54/#55.

A downloader can delete an original source file long after MoviePilot created
one or more hardlinks in the media library.  Those library hardlinks have a
later monitor add_time than the source, but they are not re-organize
replacements and must be deleted together with the source.
"""

from datetime import datetime, timedelta
from pathlib import Path
import os
import runpy
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
_helpers = runpy.run_path(
    str(REPO_ROOT / "tests" / "removelink_rehardlink_same_identity_regression.py"),
    run_name="removelink_test_helpers",
)


def main():
    module, eventmanager = _helpers["load_removelink_module"]()
    plugin = module.RemoveLink()
    plugin._notify = True
    plugin._delete_history = True
    plugin._delete_torrents = True
    plugin._delete_scrap_infos = False
    plugin._custom_scrap_extensions = []
    plugin.exclude_dirs = ""
    plugin.monitor_dirs = ""
    plugin._delay_seconds = 30

    history_calls = []
    plugin.delete_history = lambda path: history_calls.append(path)

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        source = root / "download" / "episode.mkv"
        links = [
            root / "library-a" / "episode.mkv",
            root / "library-b" / "episode.mkv",
        ]
        source.parent.mkdir()
        for link in links:
            link.parent.mkdir()
        source.write_bytes(b"episode")
        for link in links:
            os.link(source, link)

        stat_info = source.stat()
        source_add_time = datetime.now() - timedelta(days=2)
        # These hardlinks were created after the source was downloaded, but
        # well before the current deletion event.  They are normal library
        # links, not a replacement created by a just-finished re-organize.
        library_add_time = datetime.now() - timedelta(minutes=5)
        task_time = datetime.now()
        plugin.file_state = {
            str(source): module.FileInfo(
                dev=stat_info.st_dev,
                inode=stat_info.st_ino,
                add_time=source_add_time,
            ),
            **{
                str(link): module.FileInfo(
                    dev=stat_info.st_dev,
                    inode=stat_info.st_ino,
                    add_time=library_add_time,
                )
                for link in links
            },
        }

        source.unlink()
        # handle_deleted() removes the source entry before queuing this task.
        plugin.file_state.pop(str(source))
        task = module.DeletionTask(
            file_path=source,
            deleted_dev=stat_info.st_dev,
            deleted_inode=stat_info.st_ino,
            deleted_add_time=source_add_time,
            timestamp=task_time,
        )
        plugin._execute_delayed_deletion(task)

        assert task.processed is True
        assert all(not link.exists() for link in links), (
            "downloader source deletion left library hardlinks behind"
        )
        assert all(str(link) not in plugin.file_state for link in links)
        assert history_calls == [str(source), *(str(link) for link in links)]
        assert len(eventmanager.calls) == 3
        assert len(plugin.messages) == 1

    print("PASS: source deletion removes older library hardlinks (#54/#55)")


if __name__ == "__main__":
    main()
