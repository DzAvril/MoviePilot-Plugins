import importlib.util
import contextlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3] / "plugins.v3/zvideohelper"
package = types.ModuleType("zvideo_test");package.__path__ = [str(ROOT)];sys.modules["zvideo_test"] = package
spec = importlib.util.spec_from_file_location("zvideo_test.subtitles", ROOT / "subtitles.py")
subtitles = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = subtitles
spec.loader.exec_module(subtitles)
spec = importlib.util.spec_from_file_location("zvideo_subtitle_cli", ROOT / "subtitle_cli.py")
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)


def result(items):
    return {"ok": True, "data": {"subs": [{"name": "测试电影", "imdb": "tt0111161", "subs": items}]}}


ITEM = {"sub_id": "sample-id", "sub_title": "测试&amp;电影.简英双语.ass", "size": "32KB", "download_url": "https://example.com/sub?secret=synthetic-private-locator"}


class SubtitleServiceTests(unittest.TestCase):
    def test_imdb_empty_result_falls_back_to_title_and_caches_safe_projection(self):
        queries = []
        def run(args):
            query = json.loads(args[args.index("--params") + 1])["q"]
            queries.append(query)
            return result([] if query.startswith("tt") else [ITEM, ITEM])
        service = subtitles.SubtitleService("/unused", run=run)
        response = service.search("测试电影", "tt0111161")
        self.assertTrue(response["success"])
        self.assertEqual(queries, ["tt0111161", "测试电影"])
        self.assertEqual(response["count"], 1)
        self.assertEqual(response["candidates"][0]["format"], "ASS")
        self.assertIn("测试&电影", response["candidates"][0]["title"])
        self.assertNotIn("synthetic-private-locator", json.dumps(response))
        self.assertNotIn("download_url", json.dumps(list(service._cache.values())))
        self.assertTrue(service.search("测试电影", "tt0111161")["cached"])
        self.assertEqual(len(queries), 2)

    def test_provider_failure_does_not_become_empty_success(self):
        def failed(args):
            raise subtitles.SubtitleError("请先在 NAS 终端完成极空间授权")
        response = subtitles.SubtitleService("/unused", run=failed).search("测试电影")
        self.assertFalse(response["success"])
        self.assertNotIn("candidates", response)

    def test_txt_only_resource_reports_actual_unsupported_member_and_caches_it(self):
        service = subtitles.SubtitleService('/unused', run=lambda args:result([{**ITEM,'sub_title':'Movie 特效字幕'}]))
        candidate = service.search('Movie')['candidates'][0]
        with patch.object(service,'_request',return_value={'subs':[{'sub_title':'Movie 特效字幕.txt','download_url':ITEM['download_url']}]}) as request:
            preview = service.preview(candidate['id'])
            self.assertEqual(preview['files'],[])
            self.assertEqual(preview['unsupported_files'],['Movie 特效字幕.txt'])
            self.assertIn('仅提供 TXT 说明文件',preview['message'])
            self.assertNotIn('synthetic-private-locator',json.dumps(preview))
            self.assertEqual(service.preview(candidate['id'])['unsupported_files'],preview['unsupported_files'])
            self.assertEqual(request.call_count,1)

    def test_malformed_archive_response_is_a_visible_error(self):
        service = subtitles.SubtitleService('/unused', run=lambda args:result([{**ITEM,'sub_title':'Movie.zip'}]))
        candidate = service.search('Movie')['candidates'][0]
        for data in ({'subs':None},{'subs':'bad'},[]):
            with self.subTest(data=data),patch.object(service,'_request',return_value=data):
                preview=service.preview(candidate['id'])
                self.assertFalse(preview['success'])
                self.assertIn('文件列表异常',preview['message'])

    def test_mixed_pack_keeps_subtitle_downloadable_and_lists_other_files(self):
        service = subtitles.SubtitleService('/unused', run=lambda args:result([{**ITEM,'sub_title':'Movie.zip'}]))
        candidate = service.search('Movie')['candidates'][0]
        with patch.object(service,'_request',return_value={'subs':[{'sub_title':'Movie.chs.ass'},{'sub_title':'readme.txt'}]}):
            preview=service.preview(candidate['id'])
        self.assertEqual([f['title'] for f in preview['files']],['Movie.chs.ass'])
        self.assertEqual(service.preview(preview['files'][0]['id'])['unsupported_files'],[])

    def test_malformed_provider_envelope_and_invalid_input_are_rejected(self):
        with self.assertRaises(subtitles.SubtitleError):
            subtitles.project_candidates({"subs": "not-a-list"})
        for keyword, imdb in [("", ""), ("movie", "bad-id"), ("movie\nextra", ""), ("x" * 201, "")]:
            with self.subTest(keyword=keyword, imdb=imdb), self.assertRaises(subtitles.SubtitleError):
                subtitles.query_plan(keyword, imdb)

    def test_busy_search_is_reported_without_starting_another_request(self):
        service = subtitles.SubtitleService("/unused", run=lambda args: self.fail("must not call provider"))
        service._lock.acquire()
        self.assertFalse(service.search("电影")["success"])
        service._lock.release()

    def test_native_cli_errors_never_echo_raw_output_or_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            native = Path(folder) / "zspace-cli"
            native.touch(mode=0o700)
            service = subtitles.SubtitleService(folder)
            process = type("Result", (), {"returncode": 1, "stdout": b"", "stderr": json.dumps({"ok": False, "error": {"code": "E_OAUTH", "message": "synthetic-private-token"}}).encode()})()
            with patch.object(subtitles.subprocess, "run", return_value=process):
                response = service.search("电影")
            self.assertFalse(response["success"])
            self.assertNotIn("synthetic-private-token", json.dumps(response))

    def test_dedicated_mode_cannot_modify_a_shared_profile(self):
        with self.assertRaises(transport.ExtensionError):
            transport.parse_search(["--profile", "default", "media", "subtitle-search", "--dedicated-profile", "--params", '{"q":"movie"}'])
        request = transport.parse_search(["--profile", "zvideohelper", "media", "subtitle-search", "--dedicated-profile", "--params", '{"q":"movie"}'])
        self.assertTrue(request.dedicated_profile)

    def test_dedicated_connection_is_restored_after_search_failure(self):
        request = transport.parse_search(["--profile", "zvideohelper", "media", "subtitle-search", "--dedicated-profile", "--params", '{"q":"movie"}'])
        calls = []
        def native(args, timeout, env=None):
            calls.append(args)
            if args[-1] == "doctor":
                return 0, {"ok": True, "data": {"transport": {"kind": "lan", "base_url": "http://192.168.1.93:5055"}}}
            if args[-1] == "status":
                return 0, {"ok": True}
            raise transport.ExtensionError("E_NETWORK", "synthetic failure")
        @contextlib.contextmanager
        def relay(*args):
            yield "http://127.0.0.1:12345"
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"ZSPACE_CLI_HOME": folder}), patch.object(transport, "cli_json", side_effect=native), patch.object(transport, "relay", relay):
            with self.assertRaises(transport.ExtensionError):
                transport.search("/native-cli", request)
        self.assertEqual(calls[-1][-4:], ["--clear-host", "--mode", "auto", "status"])
        self.assertTrue(all(args[args.index("--profile") + 1] == "zvideohelper" for args in calls))


if __name__ == "__main__":
    unittest.main()
