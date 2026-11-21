"""Regression tests for STRM query rewriting and output isolation."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from threading import Event
from urllib.parse import parse_qs, urlencode, urlsplit

PLUGIN = Path(__file__).resolve().parents[3] / "plugins.v3" / "strmmirror"
spec = importlib.util.spec_from_file_location("strmmirror_core", PLUGIN / "mirror.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Mirror = module.Mirror
CODE = "ab0123456789cdEFG"
NEXT_CODE = "zz0123456789cdEFG"


class TestMirror(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name).resolve()
        self.source = self.root / "direct"
        self.target = self.root / "tunnel"
        self.source.mkdir()
        self.url = "https://relay.example.test/redirect?gateway_token=new-token"
        self.mirror = Mirror(self.source, self.target, self.url)
        self.stopped = Event()

    def source_file(self, relative, code=CODE, name="原片 + 4K.mkv"):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        query = {"pickcode": code, "apikey": "old-api-key", "gateway_token": "old-token"}
        if name is not None:
            query["file_name"] = name
        path.write_text(f"https://nas.example.test{module.REDIRECT_PATH}?{urlencode(query)}\n", encoding="utf-8")
        return path

    def test_creates_relative_path_and_only_copies_media_parameters(self):
        relative = Path("series/中文/Season 01/01.strm")
        source = self.source_file(relative)
        original = source.read_bytes()
        (source.parent / "episode.nfo").write_text("metadata", encoding="utf-8")
        stats = self.mirror.scan(self.stopped)
        self.assertEqual(stats["created"], 1)
        output = self.target / relative
        actual = urlsplit(output.read_text(encoding="utf-8").strip())
        self.assertEqual((actual.hostname, actual.path), ("relay.example.test", "/redirect"))
        self.assertEqual(parse_qs(actual.query), {
            "pickcode": [CODE], "file_name": ["原片 + 4K.mkv"], "gateway_token": ["new-token"],
        })
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual((output.parent / "episode.nfo").read_text(encoding="utf-8"), "metadata")

    def test_reconciles_updates_new_files_and_missing_outputs(self):
        relative = "movies/Example.STRM"
        self.source_file(relative, name=None)
        self.assertEqual(self.mirror.scan(self.stopped)["created"], 1)
        output = self.target / relative
        before = output.stat().st_mtime_ns
        self.assertEqual(self.mirror.scan(self.stopped)["unchanged"], 1)
        self.assertEqual(output.stat().st_mtime_ns, before)
        self.source_file(relative, code=NEXT_CODE, name=None)
        self.source_file("movies/New.strm")
        report = self.mirror.scan(self.stopped)
        self.assertEqual((report["created"], report["updated"]), (1, 1))
        self.assertIn(f"pickcode={NEXT_CODE}", output.read_text(encoding="utf-8"))
        self.assertNotIn("file_name=", output.read_text(encoding="utf-8"))
        output.unlink()
        self.assertEqual(self.mirror.scan(self.stopped)["created"], 1)
        (self.source / relative).unlink()
        self.mirror.scan(self.stopped)
        self.assertTrue(output.is_file())

    def test_skips_invalid_urls_and_destination_symlinks(self):
        self.source_file("linked/source.strm")
        (self.source / "invalid.strm").write_text("https://somewhere.example.test/video.mp4", encoding="utf-8")
        self.target.mkdir()
        external = self.root / "outside"
        external.mkdir()
        (self.target / "linked").symlink_to(external, target_is_directory=True)
        self.assertEqual(self.mirror.scan(self.stopped)["skipped"], 2)
        self.assertEqual(list(external.iterdir()), [])
        with self.assertRaises(ValueError):
            Mirror(self.source, self.source / "nested", self.url)
        with self.assertRaises(ValueError):
            Mirror(self.source, self.target, self.url + "&pickcode=placeholder")

    def test_stop_and_missing_source_do_not_create_output(self):
        self.source_file("movies/Example.strm")
        self.stopped.set()
        self.mirror.scan(self.stopped)
        self.assertFalse(self.target.exists())
        missing = Mirror(self.root / "missing", self.target, self.url)
        with self.assertRaises(OSError):
            missing.scan(Event())
        self.assertFalse(self.target.exists())

    def test_event_syncs_series_posters_and_accepts_later_sidecars(self):
        self.source_file("series/国产剧/新剧/Season 01/S01E01.strm")
        self.mirror.scan(self.stopped)
        episode = self.source_file("series/国产剧/新剧/Season 02/S02E01.strm")
        poster = episode.parent.parent / "poster.jpg"
        poster.write_bytes(b"show poster")
        other = self.source_file("movies/动画电影/unrelated/other.strm")
        self.assertEqual(self.mirror.sync_changes({episode}, self.stopped)["created"], 1)
        self.assertEqual((self.target / poster.relative_to(self.source)).read_bytes(), b"show poster")
        self.assertFalse((self.target / other.relative_to(self.source)).exists())
        subtitle = episode.with_suffix(".ass")
        subtitle.write_bytes(b"late subtitle")
        self.assertEqual(self.mirror.sync_changes({subtitle}, self.stopped)["sidecars"], 1)
        self.assertEqual((self.target / subtitle.relative_to(self.source)).read_bytes(), b"late subtitle")

    def test_folder_arrival_and_flat_title_only_copy_associated_files(self):
        episode = self.source_file("series/日韩剧/新剧/Season 01/S01E01.strm")
        title = episode.parent.parent
        cover = title / "cover.png"
        cover.write_bytes(b"cover")
        self.assertEqual(self.mirror.sync_changes({title}, self.stopped)["sidecars"], 1)
        file = self.source_file("movies/华语电影/电影.strm")
        poster = file.with_name("电影-poster.jpg")
        poster.write_bytes(b"poster")
        unrelated = file.with_name("其他电影-poster.jpg")
        unrelated.write_bytes(b"other")
        self.assertEqual(self.mirror.sync_changes({file}, self.stopped)["sidecars"], 1)
        self.assertFalse((self.target / unrelated.relative_to(self.source)).exists())
