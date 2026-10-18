import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_subtitles import subtitles
library=importlib.import_module('zvideo_test.library')
automation=importlib.import_module('zvideo_test.automation')


class IncrementalLibraryTests(unittest.TestCase):
    def setup_worker(self,folder,config=None):
        root=Path(folder).resolve()/'media';root.mkdir(exist_ok=True)
        worker=automation.SubtitleAutomation(Path(folder)/'state',None,[root],config or {})
        return root,worker

    def run_scan(self,worker,**kwargs):
        self.assertTrue(worker.start(**kwargs)['success']);worker._thread.join(5)
        self.assertFalse(worker.progress['running'])
        self.assertFalse(worker.progress['error'],worker.progress['error'])

    def test_restart_reuses_unchanged_files_but_video_subtitle_and_nfo_changes_invalidate(self):
        with tempfile.TemporaryDirectory() as folder:
            root,worker=self.setup_worker(folder)
            a=root/'A.mkv';a.touch();b=root/'B.mkv';b.touch()
            with patch.object(automation,'inspect_media',return_value={'state':'missing','reason':'none'}) as inspect:
                self.run_scan(worker);self.assertEqual(inspect.call_count,2)
                restarted=automation.SubtitleAutomation(Path(folder)/'state',None,[root],{})
                self.run_scan(restarted);self.assertEqual((restarted.progress['checked'],restarted.progress['skipped']),(0,2))
                self.assertEqual(inspect.call_count,2)
                a.write_bytes(b'changed video');self.run_scan(restarted);self.assertEqual(restarted.progress['checked'],1)
                b.with_suffix('.zh.srt').write_text('new subtitle');self.run_scan(restarted);self.assertEqual(restarted.progress['checked'],1)
                a.with_suffix('.nfo').write_text('<movie><title>A new identity</title></movie>')
                self.run_scan(restarted);self.assertEqual(restarted.progress['checked'],1)
                (root/'Unrelated.srt').touch();self.run_scan(restarted);self.assertEqual(restarted.progress['checked'],0)
                self.assertTrue(restarted.snapshot()['coverage']['baseline_complete'])

    def test_show_nfo_change_invalidates_every_episode(self):
        with tempfile.TemporaryDirectory() as folder:
            root,worker=self.setup_worker(folder);season=root/'Season 1';season.mkdir()
            for n in (1,2):(season/f'Show.S01E{n:02}.mkv').touch()
            with patch.object(automation,'inspect_media',return_value={'state':'present','reason':'Chinese track'}):
                self.run_scan(worker)
                (root/'tvshow.nfo').write_text('<tvshow><title>Show</title><year>2026</year></tvshow>')
                self.run_scan(worker);self.assertEqual(worker.progress['checked'],2)
                self.run_scan(worker);self.assertEqual(worker.progress['checked'],0)

    def test_force_recheck_and_deleted_file_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            root,worker=self.setup_worker(folder)
            for name in ('A','B'):(root/(name+'.mkv')).touch()
            with patch.object(automation,'inspect_media',return_value={'state':'present','reason':'Chinese track'}):
                self.run_scan(worker);self.run_scan(worker,force=True)
                self.assertEqual((worker.progress['checked'],worker.progress['skipped']),(2,0))
                (root/'B.mkv').unlink();self.run_scan(worker)
                self.assertEqual(worker.snapshot()['total'],1);self.assertEqual(worker.progress['checked'],0)

    def test_stop_persists_pending_files_and_next_process_resumes(self):
        with tempfile.TemporaryDirectory() as folder:
            root,worker=self.setup_worker(folder)
            for n in range(3):(root/f'{n}.mkv').touch()
            def inspect(*args,**kwargs):
                worker.cancel();return {'state':'present','reason':'Chinese track'}
            with patch.object(automation,'inspect_media',side_effect=inspect):self.run_scan(worker)
            first=worker.snapshot();self.assertEqual(first['total'],3)
            self.assertEqual((first['coverage']['checked'],first['coverage']['pending']),(1,2))
            self.assertFalse(first['coverage']['baseline_complete'])
            self.assertEqual(first['task']['phase'],'已停止')
            restarted=automation.SubtitleAutomation(Path(folder)/'state',None,[root],{})
            with patch.object(automation,'inspect_media',return_value={'state':'present','reason':'Chinese track'}) as inspect:
                self.run_scan(restarted);self.assertEqual(inspect.call_count,2)
            self.assertEqual((restarted.progress['checked'],restarted.progress['skipped']),(2,1))
            self.assertTrue(restarted.snapshot()['coverage']['baseline_complete'])

    def test_missing_subtitles_can_retry_download_without_reprobing_video(self):
        with tempfile.TemporaryDirectory() as folder:
            root,worker=self.setup_worker(folder,{'subtitle_download_limit':2})
            for n in range(7):(root/f'{n}.mkv').touch()
            with patch.object(automation,'inspect_media',return_value={'state':'missing','reason':'no Chinese'}) as inspect,patch.object(worker,'_auto_download',return_value=False) as download:
                self.run_scan(worker,download=True);self.assertEqual(inspect.call_count,7);self.assertEqual(download.call_count,2)
                self.run_scan(worker,download=True);self.assertEqual(inspect.call_count,7);self.assertEqual(download.call_count,4)
                self.assertEqual(worker.progress['checked'],0)
                self.assertEqual(len({call.args[0]['id'] for call in download.call_args_list}),4)

    def test_unavailable_directory_or_failed_walk_does_not_erase_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root,worker=self.setup_worker(folder);(root/'A.strm').touch();self.run_scan(worker)
            root.rename(root.with_name('offline'))
            self.assertFalse(worker.start()['success']);self.assertEqual(len(worker.data['items']),1)
            root.with_name('offline').rename(root)
            with patch.object(automation,'library_files',side_effect=OSError('unreadable')):
                self.assertTrue(worker.start()['success']);worker._thread.join(5)
            self.assertEqual(len(worker.data['items']),1);self.assertTrue(worker.progress['error'])

    def test_custom_paths_are_validated_deduplicated_and_never_fall_back_on_error(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();child=root/'child';child.mkdir();other=root/'other';other.mkdir()
            roots,errors=library.resolve_roots([other],str(child)+'\n'+str(root)+'\n'+str(child))
            self.assertEqual(roots,[str(root)]);self.assertFalse(errors)
            roots,errors=library.resolve_roots([other],str(root/'missing'))
            self.assertFalse(roots);self.assertTrue(errors)
            for value in ('/','relative/path',str(root)+'/../other'):
                self.assertTrue(library.resolve_roots([other],value)[1])
            self.assertEqual(library.resolve_roots([other],'')[0],[str(other)])

    def test_only_transient_unknown_results_are_retried_without_file_changes(self):
        stable={'state':'unknown','fingerprint':'same','checked_at':1,'reason':'内嵌字幕语言未标注'}
        self.assertFalse(automation.SubtitleAutomation.needs_check(stable,'same'))
        self.assertTrue(automation.SubtitleAutomation.needs_check({**stable,'reason':'视频字幕轨道探测失败'},'same'))
        self.assertTrue(automation.SubtitleAutomation.needs_check({**stable,'state':'pending'},'same'))


if __name__=='__main__':unittest.main()
