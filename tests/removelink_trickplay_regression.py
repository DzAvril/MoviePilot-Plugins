#!/usr/bin/env python3
"""Issue #60: exercise real plugin methods with stubs and temporary files only.

Run: python3 tests/removelink_trickplay_regression.py
No running MoviePilot/Jellyfin instance is required or exercised.
"""
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import os
import runpy
import shutil
import tempfile
import unittest

_helpers = runpy.run_path(
    str(Path(__file__).with_name("removelink_rehardlink_same_identity_regression.py")),
    run_name="removelink_test_helpers",
)


class TrickplayRegression(unittest.TestCase):
    def setUp(self):
        self.module, self.events = _helpers["load_removelink_module"]()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plugin = self.module.RemoveLink()
        self.plugin.file_state = {}
        self.plugin.deletion_queue = []
        self.plugin._deletion_timer = None
        self.plugin._notify = True
        self.plugin._delete_history = True
        self.plugin._delete_torrents = True
        self.plugin._delete_scrap_infos = True
        self.plugin._delayed_deletion = True
        self.plugin._delay_seconds = 30
        self.plugin._custom_scrap_extensions = []
        self.plugin.exclude_keywords = ""
        self.plugin.exclude_dirs = ""
        self.plugin.monitor_dirs = str(self.root)
        self.history = []
        self.plugin.delete_history = self.history.append
        # Advance task timestamps explicitly; never start background timers.
        self.plugin._start_deletion_timer = lambda *args: None
        self.handler = self.module.FileMonitorHandler(str(self.root), self.plugin)
        self.media = self.write("library/Show.S01E01.mkv", b"video")
        self.preview = self.media.with_suffix(".trickplay")
        self.marker = self.write("library/Show.S01E01.trickplay/320 - 10x10/.jellyfin-trickplay")
        self.jpgs = [self.write(f"library/Show.S01E01.trickplay/320 - 10x10/{i}.jpg") for i in range(2)]

    def write(self, name, data=b"preview"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def info(self, path, age=120):
        stat = path.stat()
        return self.module.FileInfo(stat.st_dev, stat.st_ino, datetime.now() - timedelta(seconds=age))

    def event(self, path, directory=False, dest=None):
        return SimpleNamespace(src_path=str(path), is_directory=directory, dest_path=str(dest))

    def task(self, path, info):
        return self.module.DeletionTask(path, info.dev, info.inode, info.add_time, datetime.now() - timedelta(seconds=31))

    def quiet(self):
        self.assertEqual(self.events.calls, [])
        self.assertEqual(self.history, [])
        self.assertEqual(self.plugin.messages, [])

    def previews_intact(self):
        self.assertTrue(self.media.exists())
        self.assertTrue(all(p.exists() for p in self.jpgs), "preview JPGs were deleted")
        self.assertTrue(self.preview.is_dir())

    def test_marker_delayed_identity_branches(self):
        # Force both identity branches, independent of filesystem inode reuse.
        for matching in (True, False):
            with self.subTest(matching=matching):
                for jpg in self.jpgs:
                    jpg.parent.mkdir(parents=True, exist_ok=True)
                    jpg.write_bytes(b"preview")
                info = self.info(self.jpgs[0], age=120)
                candidate = info._replace(add_time=datetime.now())
                if not matching:
                    candidate = candidate._replace(dev=info.dev + 1, inode=info.inode + 1)
                self.plugin.file_state = {str(self.jpgs[0]): candidate}
                self.marker.unlink(missing_ok=True)
                task = self.task(self.marker, info)
                self.plugin.deletion_queue = [task]
                self.plugin._process_deletion_queue()
                self.assertTrue(task.processed)
                self.assertEqual(self.plugin.deletion_queue, [])
                self.assertIsNone(self.plugin._deletion_timer)
                self.previews_intact()
                self.quiet()

    def test_scan_prunes_subtree_and_direct_monitor_root(self):
        hidden = self.write("library/.trickplay/sub/movie.mkv")
        upper = self.write("library/Other.TRICKPLAY/sub/0.jpg")
        ordinary = self.write("library/trickplay/movie.mkv")
        similar = self.write("library/Other.trickplay.backup/movie.mkv")
        state = self.module.updateState([str(self.root), str(self.marker.parent)])
        self.assertEqual(set(state), {str(self.media), str(ordinary), str(similar)})
        for path in (hidden, upper):
            self.handler.on_created(self.event(path))
        self.assertEqual(self.plugin.file_state, {})

    def test_preview_create_update_regenerate(self):
        for _ in range(2):
            self.marker.write_bytes(b"generating")
            self.handler.on_created(self.event(self.marker))
            self.marker.unlink()
            self.handler.on_deleted(self.event(self.marker))
            for jpg in self.jpgs:
                jpg.unlink()
                self.handler.on_deleted(self.event(jpg))
                jpg.write_bytes(b"new preview")
                self.handler.on_created(self.event(jpg))
                self.handler.on_created(self.event(jpg))
        self.assertEqual(self.plugin.file_state, {})
        self.assertEqual(self.plugin.deletion_queue, [])
        self.previews_intact()
        self.quiet()

    def test_directory_and_subdirectory_delete_move(self):
        for path in (self.preview, self.marker.parent):
            self.handler.on_deleted(self.event(path, directory=True))
            self.handler.on_moved(self.event(path, directory=True, dest=self.root / "gone"))
        self.assertEqual(self.plugin.deletion_queue, [])
        self.previews_intact()
        self.quiet()

    def test_actual_preview_directory_moves_and_removal(self):
        subdir = self.marker.parent
        dest = self.preview / "640 - 10x10"
        subdir.rename(dest)
        self.handler.on_moved(self.event(subdir, directory=True, dest=dest))
        moved_preview = self.preview.with_name("Moved.trickplay")
        self.preview.rename(moved_preview)
        self.handler.on_moved(self.event(self.preview, directory=True, dest=moved_preview))
        jpg = moved_preview / dest.name / "0.jpg"
        moved_jpg = jpg.with_name("2.jpg")
        jpg.rename(moved_jpg)
        self.handler.on_moved(self.event(jpg, dest=moved_jpg))
        self.assertTrue(moved_jpg.exists())
        shutil.rmtree(moved_preview)
        for path in (moved_jpg, moved_jpg.parent, moved_preview):
            self.handler.on_deleted(self.event(path, directory=path != moved_jpg))
        self.assertTrue(self.media.exists())
        self.assertEqual(self.plugin.file_state, {})
        self.assertEqual(self.plugin.deletion_queue, [])
        self.quiet()

    def test_stale_state_delete_and_move(self):
        for delayed in (True, False):
            self.plugin._delayed_deletion = delayed
            for path in (self.marker, self.jpgs[0]):
                info = self.info(path)
                self.plugin.file_state = {str(path): info}
                self.plugin.handle_deleted(path)
                self.assertNotIn(str(path), self.plugin.file_state)
                self.plugin.file_state = {str(path): info}
                self.handler.on_moved(self.event(path, dest=self.preview / "gone.jpg"))
                self.assertNotIn(str(path), self.plugin.file_state)
        self.assertEqual(self.plugin.deletion_queue, [])
        self.previews_intact()
        self.quiet()

    def test_direct_cleanup_and_strm_defenses(self):
        self.marker.unlink()
        self.plugin.delete_scrap_infos(self.marker)
        self.plugin.delete_empty_folders(self.marker)
        lookups = []
        self.plugin._get_storage_path_from_strm = lambda path: lookups.append(path)
        self.plugin.handle_strm_deleted(self.preview / "accidental.strm")
        self.assertEqual(lookups, [], "preview reached STRM lookup")
        self.previews_intact()
        self.quiet()

    def test_real_media_deletion_exact_stem_and_multiple_dots(self):
        other = self.write("library/Show.S01E010.mkv", b"other video")
        other_jpg = self.write("library/Show.S01E010.trickplay/320/0.jpg")
        self.marker.unlink()
        info = self.info(self.media)
        self.plugin.file_state = {str(self.media): info}
        self.media.unlink()
        self.plugin._delayed_deletion = False
        self.plugin.handle_deleted(self.media)
        self.assertFalse(self.preview.exists())
        self.assertTrue(other.exists())
        self.assertTrue(other_jpg.exists(), "same-prefix preview directory was deleted")
        self.assertEqual(self.history, [str(self.media)])
        self.assertEqual(len(self.events.calls), 1)

    def test_reorganize_keeps_new_hardlink_cleans_old_preview(self):
        new = self.media.with_name("Show.S01E01.new.mkv")
        os.link(self.media, new)
        new_preview = self.write("library/Show.S01E01.new.trickplay/320/0.jpg")
        old_info = self.info(self.media)
        self.plugin.file_state = {str(new): self.info(new, age=1)}
        self.media.unlink()
        task = self.task(self.media, old_info)
        self.plugin._execute_delayed_deletion(task)
        self.assertTrue(task.processed)
        self.assertTrue(new.exists())
        self.assertTrue(new_preview.exists())
        self.assertFalse(self.preview.exists())
        self.quiet()

    def test_source_deletion_cleans_hardlink_and_preview(self):
        source = self.root / "downloads/movie.mkv"
        source.parent.mkdir()
        os.link(self.media, source)
        info = self.info(source, age=3600)
        self.plugin.file_state = {str(self.media): self.info(self.media, age=600)}
        source.unlink()
        task = self.task(source, info)
        self.plugin._execute_delayed_deletion(task)
        self.assertTrue(task.processed)
        self.assertFalse(self.media.exists())
        self.assertFalse(self.preview.exists())
        self.assertEqual(len(self.events.calls), 2)
        self.assertEqual(self.history, [str(source), str(self.media)])

    def test_stale_preview_candidate_cannot_save_real_hardlink(self):
        source = self.root / "downloads/movie.mkv"
        source.parent.mkdir()
        os.link(self.media, source)
        info = self.info(source, age=3600)
        preview_info = info._replace(add_time=datetime.now())
        self.plugin.file_state = {
            str(self.jpgs[0]): preview_info,
            str(self.media): self.info(self.media, age=600),
        }
        source.unlink()
        task = self.task(source, info)
        self.plugin._execute_delayed_deletion(task)
        self.assertTrue(task.processed)
        self.assertFalse(self.media.exists())
        self.assertFalse(self.preview.exists())

    def test_preview_hardlink_target_is_protected(self):
        # Even stale tracking must not unlink media intentionally put in a preview tree.
        protected = self.preview / "accidental.mkv"
        os.link(self.media, protected)
        info = self.info(self.media)
        self.plugin.file_state = {str(protected): info}
        self.plugin._delete_scrap_infos = False
        self.media.unlink()
        task = self.task(self.media, info)
        self.plugin._execute_delayed_deletion(task)
        self.assertTrue(protected.exists())
        self.assertNotIn(str(protected), self.plugin.file_state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
