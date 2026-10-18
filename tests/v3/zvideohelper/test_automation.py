import importlib
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from test_subtitles import subtitles
library = importlib.import_module('zvideo_test.library')
automation = importlib.import_module('zvideo_test.automation')

CHINESE = '1\n00:00:01,000 --> 00:00:03,000\n这里是一条中文字幕用于实际内容检查\n'.encode()
ENGLISH = b'1\n00:00:01,000 --> 00:00:03,000\nThis is an English subtitle with no Chinese dialogue.\n'


class LibraryTests(unittest.TestCase):
    def test_external_chinese_wins_even_when_embedded_only_english(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder)/'Movie.mkv';video.touch();video.with_suffix('.srt').write_bytes(CHINESE)
            result = library.inspect_media(video, probe=lambda p:self.fail('positive sidecar should avoid probe'))
            self.assertEqual(result['state'],'present')

    def test_embedded_chinese_and_unknown_language_are_distinguished(self):
        with tempfile.TemporaryDirectory() as folder:
            video=Path(folder)/'Movie.mkv';video.touch()
            for tags, expected in [({'language':'chi'},'present'),({'language':'und'},'unknown'),({'language':'eng'},'missing'),({'title':'Chinese (Traditional)'},'present')]:
                with self.subTest(tags=tags):self.assertEqual(library.inspect_media(video,probe=lambda p:{'streams':[{'tags':tags}]})['state'],expected)
            self.assertEqual(library.inspect_media(video,probe=lambda p:{})['state'],'unknown')

    def test_strm_and_bitmap_unknown_never_read_remote_video(self):
        with tempfile.TemporaryDirectory() as folder:
            video=Path(folder)/'Movie.strm';video.write_text('synthetic-private-strm')
            self.assertEqual(library.inspect_media(video,probe=lambda p:self.fail('must not probe STRM'))['state'],'unknown')
            video=video.with_suffix('.mkv');video.touch();video.with_suffix('.sup').touch()
            self.assertEqual(library.inspect_media(video,probe=lambda p:{'streams':[]})['state'],'unknown')

    def test_japanese_and_ass_metadata_do_not_count_as_chinese_dialogue(self):
        self.assertIsNone(library.chinese_text('日本語字幕です。日本漢字混在かな'.encode()))
        self.assertFalse(library.chinese_text(ENGLISH))
        self.assertIsNone(library.chinese_text('[Script Info]\nTitle: 中文标题不能作为中文对白证据'.encode(),'.ass'))
        self.assertTrue(library.chinese_text(CHINESE))

    def test_series_nfo_uses_show_identity_instead_of_episode_imdb(self):
        with tempfile.TemporaryDirectory() as folder:
            show=Path(folder)/'Show';season=show/'Season 1';season.mkdir(parents=True)
            video=season/'Show - S01E03.mkv';video.touch()
            video.with_suffix('.nfo').write_text('<episodedetails><title>Episode</title><uniqueid type="imdb">tt9999999</uniqueid></episodedetails>')
            (show/'tvshow.nfo').write_text('<tvshow><title>Show</title><year>2020</year><uniqueid type="imdb">tt1111111</uniqueid></tvshow>')
            data=library.media_metadata(video)
            self.assertEqual((data['title'],data['imdb_id'],data['season'],data['episode']),('Show','tt1111111',1,3))

    def test_symlink_and_disc_trees_are_not_scanned(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'root';root.mkdir();outside=Path(folder)/'outside.mkv';outside.touch()
            (root/'link.mkv').symlink_to(outside);(root/'BDMV').mkdir();(root/'BDMV'/'part.mkv').touch();(root/'yes.mkv').touch()
            self.assertEqual([p.name for p in library.library_files([root])],['yes.mkv'])


class MatchingAndWriteTests(unittest.TestCase):
    def test_wrong_movie_episode_and_edition_are_rejected(self):
        m={'title':'Show','imdb_id':'tt1111111','year':'2020','season':1,'episode':3}
        score=lambda name,imdb='tt1111111':automation.match_score(m,'Show.S01E03.mkv',name,'Show',imdb)
        self.assertLess(score('Show.S01E04.chs.srt'),0)
        self.assertLess(score('Show.S01E03.chs.srt','tt2222222'),0)
        self.assertLess(score('Show.S01E03.extended.chs.srt'),0)
        self.assertGreaterEqual(score('Show.S01E03.chs.srt'),0)
        self.assertLess(score('Show.S01E03E04.chs.srt'),0)

    def test_atomic_publish_preserves_existing_subtitle_and_media(self):
        with tempfile.TemporaryDirectory() as folder:
            video=Path(folder)/'Movie.mkv';video.write_bytes(b'original-video')
            sub=Path(folder)/'incoming.srt';sub.write_bytes(CHINESE)
            saved=automation.write_sidecar(video,sub)
            sub.write_bytes(b'replacement')
            with self.assertRaises(subtitles.SubtitleError):automation.write_sidecar(video,sub)
            self.assertEqual(saved.read_bytes(),CHINESE);self.assertEqual(video.read_bytes(),b'original-video')
            self.assertFalse(list(Path(folder).glob('.zvideo-sub-*')))

    def test_unknown_skips_search_and_cursor_resumes_next_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'library';root.mkdir()
            for name in ['a.strm','b.strm','c.strm']:(root/name).touch()
            svc=subtitles.SubtitleService(Path(folder)/'cli',run=lambda a:self.fail('unknown must never search'))
            worker=automation.SubtitleAutomation(Path(folder)/'state',svc,[root],{'subtitle_batch':2})
            worker._lock.acquire();worker.progress.update(running=True);worker._run(True)
            self.assertEqual(len(worker.data['items']),2)
            worker._lock.acquire();worker._run(True)
            self.assertEqual(len(worker.data['items']),3)
            self.assertTrue(all(i['state']=='unknown' for i in worker.data['items'].values()))

    def test_expired_auth_pauses_and_notifies_once_then_can_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'library';root.mkdir();(root/'Movie.mkv').touch()
            svc=subtitles.SubtitleService(Path(folder)/'cli',run=lambda a:None);notices=[]
            worker=automation.SubtitleAutomation(Path(folder)/'state',svc,[root],{'subtitle_batch':1},notice=notices.append)
            def fail(item):svc.auth_failed=True;raise subtitles.SubtitleError('授权失效')
            with patch.object(automation,'inspect_media',return_value={'state':'missing','reason':'none'}),patch.object(worker,'_auto_download',side_effect=fail):
                for _ in range(2):worker._lock.acquire();worker._run(True)
            self.assertEqual(len(notices),1)
            self.assertNotIn('attempt_at',next(iter(worker.data['items'].values())))
            svc.auth_failed=False
            with patch.object(automation,'inspect_media',return_value={'state':'missing','reason':'none'}),patch.object(worker,'_auto_download',return_value=True):
                worker._lock.acquire();worker._run(True)
            self.assertEqual(worker.progress['downloaded'],1)

    def test_chinese_original_language_skips_probe_and_subtitle_search(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'library';root.mkdir();(root/'Chinese Movie.mkv').touch()
            svc=subtitles.SubtitleService(Path(folder)/'cli',run=lambda a:self.fail('Chinese media must never search'))
            worker=automation.SubtitleAutomation(Path(folder)/'state',svc,[root],{},language_resolver=lambda m:'zh')
            metadata={'title':'Chinese Movie','tmdb_id':'123','imdb_id':'tt1111111','season':None,'episode':None,'original_language':''}
            with patch.object(automation,'media_metadata',return_value=metadata),patch.object(automation,'inspect_media',side_effect=AssertionError('must skip probe')):
                worker._lock.acquire();worker._run(True)
            self.assertEqual(next(iter(worker.data['items'].values()))['state'],'excluded')
            self.assertEqual(worker.snapshot()['counts']['excluded'],1)

    def test_unknown_original_language_does_not_assume_foreign(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'library';root.mkdir();(root/'Unknown.mkv').touch()
            svc=subtitles.SubtitleService(Path(folder)/'cli',run=lambda a:self.fail('unknown must never search'))
            worker=automation.SubtitleAutomation(Path(folder)/'state',svc,[root],{},language_resolver=lambda m:'')
            worker._lock.acquire();worker._run(True)
            self.assertEqual(next(iter(worker.data['items'].values()))['state'],'unknown')

    def test_mount_translation_and_staging_only_override(self):
        service=subtitles.SubtitleService('/config/plugins/ZvideoHelper/subtitle-cli')
        mounts='42 1 0:63 /nvme11/123/data/config_live /config rw - zfuse.zfsv3 zfsv3 rw\n'
        with patch.object(Path,'read_text',return_value=mounts):
            self.assertEqual(service._nas_stage('/config/plugins/ZvideoHelper/subtitle-cli/staging/job/video.mkv'),'/tmp/zfsv3/nvme11/123/data/config_live/plugins/ZvideoHelper/subtitle-cli/staging/job/video.mkv')
        with self.assertRaises(subtitles.SubtitleError):service._nas_stage('/outside/path','/safe/staging')


class ToolInstallTests(unittest.TestCase):
    def test_wrong_binary_is_rejected_without_creating_executable(self):
        module=importlib.import_module('zvideo_test.tool_install')
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(module.install_tool(folder,b'untrusted')['success'])
            self.assertFalse((Path(folder)/'zspace-cli').exists())

    def test_verified_upload_is_private_and_cannot_replace_existing_tool(self):
        module=importlib.import_module('zvideo_test.tool_install');payload=b'synthetic verified binary'
        with tempfile.TemporaryDirectory() as folder,patch.object(module.platform,'machine',return_value='x86_64'),patch.dict(module.HASHES,{'x86_64':hashlib.sha256(payload).hexdigest()}):
            self.assertTrue(module.install_tool(folder,payload)['success'])
            executable=Path(folder)/'zspace-cli'
            self.assertEqual(executable.stat().st_mode & 0o777,0o700)
            self.assertFalse(module.install_tool(folder,payload)['success'])
            self.assertEqual(executable.read_bytes(),payload)


if __name__=='__main__':unittest.main()
