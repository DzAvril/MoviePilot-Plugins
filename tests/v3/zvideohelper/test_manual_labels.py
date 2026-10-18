import importlib
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from test_subtitles import subtitles
from test_automation import CHINESE

library=importlib.import_module('zvideo_test.library')
automation=importlib.import_module('zvideo_test.automation')


class ManualLabelTests(unittest.TestCase):
    def setup_worker(self, folder, suffix='.mkv', language='en'):
        root=Path(folder).resolve()/'media';root.mkdir()
        video=root/('Movie (2025)'+suffix);video.write_bytes(b'original video')
        video.with_suffix('.nfo').write_text('<movie><title>Movie</title><year>2025</year><original_language>'+language+'</original_language><uniqueid type="imdb">tt1111111</uniqueid></movie>')
        service=Mock();service.auth_failed=False
        worker=automation.SubtitleAutomation(Path(folder)/'state',service,[root],{},language_resolver=lambda m:language)
        key=library.media_key(video)
        worker.data['items'][key]={'id':key,'path':str(video),**library.media_metadata(video),'original_language':language,
            'state':'unknown','reason':'unlabeled embedded track','checked_at':time.time(),'fingerprint':library.media_fingerprint(video),
            'subtitle_evidence_version':library.SUBTITLE_EVIDENCE_VERSION}
        return worker,video,key,service

    def run_scan(self, worker, **kwargs):
        self.assertTrue(worker.start(**kwargs)['success']);worker._thread.join(5)
        self.assertFalse(worker.progress['running']);self.assertFalse(worker.progress['error'],worker.progress['error'])

    def test_hard_subtitle_label_persists_restarts_force_scan_and_nfo_changes_then_resets(self):
        with tempfile.TemporaryDirectory() as folder:
            worker,video,key,service=self.setup_worker(folder)
            self.assertTrue(worker.mark(key,'present')['success'])
            self.assertEqual(worker.snapshot()['counts']['present'],1)
            self.assertEqual(worker.snapshot()['items'][0]['detected_state'],'unknown')
            self.assertEqual(worker.destinations('','movie')['items'][0]['manual_state'],'present')
            with patch.object(worker,'_auto_download',side_effect=AssertionError('hard subtitles must never download')):
                self.run_scan(worker,download=True)
            self.assertFalse(worker.manual_download('any',key)['success']);service.fetch.assert_not_called()
            restarted=automation.SubtitleAutomation(worker.root,service,[video.parent],{},language_resolver=lambda m:'en')
            video.with_suffix('.nfo').write_text(video.with_suffix('.nfo').read_text().replace('<title>Movie','<title>Movie updated'))
            with patch.object(automation,'inspect_media',return_value={'state':'missing','reason':'no selectable Chinese'}):
                self.run_scan(restarted,force=True)
            self.assertEqual(restarted.snapshot()['items'][0]['state'],'present')
            self.assertEqual(restarted.data['items'][key]['state'],'missing')
            self.assertTrue(restarted.mark(key,'auto')['success'])
            item=restarted.snapshot()['items'][0]
            self.assertEqual(item['state'],'missing');self.assertNotIn('manual_state',item)

    def test_confirmed_missing_unknown_media_can_be_supplemented_and_label_clears(self):
        with tempfile.TemporaryDirectory() as folder:
            worker,video,key,service=self.setup_worker(folder)
            incoming=Path(folder)/'incoming.srt';incoming.write_bytes(CHINESE)
            candidate={'id':'candidate','title':'Movie.2025.chs.srt','movie':'Movie','imdb_id':'tt1111111','download_available':True}
            service.search.return_value={'success':True,'candidates':[candidate]}
            service.preview.return_value={'success':True,'files':[{'id':'file','title':candidate['title'],'chinese_label':True}]}
            service.fetch.return_value={'path':incoming,'chinese':True}
            worker.data['items'][key]['attempt_at']=time.time()
            self.assertTrue(worker.mark(key,'missing')['success'])
            self.assertNotIn('attempt_at',worker.data['items'][key])
            self.run_scan(worker,download=True)
            self.assertEqual(worker.progress['downloaded'],1)
            self.assertEqual(video.with_name(video.stem+'.zh.srt').read_bytes(),CHINESE)
            item=worker.snapshot()['items'][0]
            self.assertEqual(item['state'],'present');self.assertNotIn('manual_state',item)

    def test_confirming_missing_does_not_bypass_original_language_or_strm_policy(self):
        for suffix,language in (('.mkv','zh'),('.mkv',''),('.strm','en')):
            with self.subTest(suffix=suffix,language=language),tempfile.TemporaryDirectory() as folder:
                worker,video,key,service=self.setup_worker(folder,suffix,language)
                worker.mark(key,'missing')
                with patch.object(worker,'_auto_download',side_effect=AssertionError('policy must still skip')):
                    self.run_scan(worker,download=True)
                self.assertEqual(worker.snapshot()['items'][0]['state'],'missing')

    def test_replacing_video_invalidates_label_but_subtitle_changes_preserve_it(self):
        with tempfile.TemporaryDirectory() as folder:
            worker,video,key,service=self.setup_worker(folder);worker.mark(key,'present')
            with patch.object(automation,'inspect_media',return_value={'state':'unknown','reason':'unlabeled'}):
                video.with_suffix('.en.srt').write_bytes(b'English')
                self.run_scan(worker);self.assertEqual(worker.snapshot()['items'][0]['manual_state'],'present')
                video.write_bytes(b'a different video file');self.run_scan(worker)
                self.assertNotIn('manual_state',worker.snapshot()['items'][0])
                worker.mark(key,'present');video.unlink();self.run_scan(worker)
                self.assertFalse(worker.data['manual_labels'])

    def test_new_present_confirmation_during_fetch_prevents_late_write(self):
        with tempfile.TemporaryDirectory() as folder:
            worker,video,key,service=self.setup_worker(folder);worker.mark(key,'missing')
            incoming=Path(folder)/'incoming.srt';incoming.write_bytes(CHINESE)
            def fetch(*args):
                worker.mark(key,'present');return {'path':incoming,'chinese':True}
            service.fetch.side_effect=fetch
            with patch.object(automation,'inspect_media',return_value={'state':'missing'}):
                result=worker.manual_download('file',key)
            self.assertFalse(result['success']);self.assertIn('人工确认',result['message'])
            self.assertFalse(video.with_name(video.stem+'.zh.srt').exists())

    def test_invalid_or_pending_labels_do_not_mutate_state(self):
        with tempfile.TemporaryDirectory() as folder:
            worker,video,key,service=self.setup_worker(folder)
            self.assertFalse(worker.mark(key,'arbitrary')['success'])
            self.assertFalse(worker.mark('not-an-indexed-media','present')['success'])
            worker.data['items'][key]['state']='pending'
            self.assertFalse(worker.mark(key,'present')['success'])
            self.assertFalse(worker.data['manual_labels'])


if __name__=='__main__':unittest.main()
