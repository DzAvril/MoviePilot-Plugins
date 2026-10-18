import importlib
import json
import unittest
from unittest.mock import patch
from test_subtitles import subtitles
selection=importlib.import_module('zvideo_test.selection')

MEDIA={'id':'157239','media_type':'tv','title':'异形：地球','original_title':'Alien: Earth','year':'2025','imdb_id':'tt13623632'}


class EpisodeMatchingTests(unittest.TestCase):
    def test_episode_and_season_must_both_match_without_prefix_collision(self):
        for title,parent,expected in [('Show.S01E01.chs.srt','',True),('ShowS01E01.chs.srt','',True),('Show.S01E010.chs.srt','',False),
                ('Show.S02E01.chs.srt','Show.S01.zip',False),('Show.S01E01E02.chs.srt','',False),('Show.S01E01-E08.chs.srt','',False),
                ('Show.1x01.chs.srt','',True),('第一季第一集.ass','',True),('E01.chs.srt','Show.Season.1.zip',True),
                ('01.chs.srt','Show.S01.zip',True),('简中.ass','Show.S01E01.zip',True),('简中.ass','Show.S01.zip',False)]:
            with self.subTest(title=title,parent=parent):self.assertEqual(selection.episode_matches(title,1,1,parent),expected)
        self.assertTrue(selection.episode_matches('Show.S00E01.ass',0,1))
        self.assertTrue(selection.episode_matches('第二季第二十六集.ass',2,26))

    def test_whole_season_and_ranges_can_be_inspected_but_other_episodes_skip(self):
        self.assertTrue(selection.may_contain_episode('Show.S01.zip',1,3))
        self.assertTrue(selection.may_contain_episode('Show.S01E01-E08.zip',1,3))
        self.assertFalse(selection.may_contain_episode('Show.S01E08.zip',1,3))
        self.assertFalse(selection.may_contain_episode('Show.S02.zip',1,3))

    def test_catalog_keeps_specials_and_actual_episode_numbers(self):
        seasons=selection.project_seasons({'season_info':[{'season_number':1,'name':'第一季','episode_count':8},{'season_number':0,'name':'特别篇','episode_count':1}]})
        self.assertEqual([s['number'] for s in seasons],[0,1])
        episodes=selection.project_episodes({'episodes':[{'season_number':1,'episode_number':1,'name':'开端'},
            {'season_number':1,'episode_number':3,'name':'后续'},{'season_number':2,'episode_number':2,'name':'别季'}]},1)
        self.assertEqual([ep['number'] for ep in episodes],[1,3])


class EpisodeSearchTests(unittest.TestCase):
    def service(self):
        items=[{'sub_id':key,'sub_title':name,'download_url':'https://example.com/synthetic-private-locator'} for key,name in [
            ('one','Alien.S01E01.chs.srt'),('two','Alien.S01E02.chs.srt'),('wrong-season','Alien.S02E01.chs.srt'),
            ('season-pack','Alien.S01.zip'),('episode-two-pack','Alien.S01E02.zip')]]
        provider=lambda args:{'ok':True,'data':{'subs':[{'name':'异形：地球','imdb':'tt13623632','subs':items}]}}
        service=subtitles.SubtitleService('/unused',run=provider)
        def preview(operation,params):
            self.assertEqual(operation,'preview')
            return {'subs':[{'sub_title':title} for title in ['S01E01.chs.ass','S01E02.chs.ass','S02E01.chs.ass','简中.ass']]}
        return service,preview

    def test_archive_members_are_filtered_and_preview_stays_single_episode(self):
        service,preview=self.service()
        with patch.object(service,'_request',side_effect=preview) as request:
            response=service.search_episode(MEDIA,1,1)
            self.assertTrue(response['success']);self.assertEqual(response['count'],2)
            self.assertEqual(request.call_count,1)
            self.assertEqual({c['title'] for c in response['candidates']},{'Alien.S01E01.chs.srt','S01E01.chs.ass'})
            member=next(c for c in response['candidates'] if c.get('archive_title'))
            selected=service.preview(member['id'])
            self.assertEqual([f['title'] for f in selected['files']],['S01E01.chs.ass'])
            self.assertNotIn('synthetic-private-locator',json.dumps(response))
            self.assertTrue(service.search_episode(MEDIA,1,1)['cached'])

    def test_switching_episode_reuses_archive_preview_and_excludes_old_episode(self):
        service,preview=self.service()
        with patch.object(service,'_request',side_effect=preview) as request:
            service.search_episode(MEDIA,1,1)
            response=service.search_episode(MEDIA,1,2)
            self.assertTrue(response['success'])
            self.assertTrue(all(selection.episode_matches(c['title'],1,2,parent=c.get('archive_title','')) for c in response['candidates']))
            # Whole-season archive is reused; only the E02-specific archive is new.
            self.assertEqual(request.call_count,2)
            self.assertEqual(response['checked_archives'],1)

    def test_episode_filter_runs_before_generic_archive_display_limit(self):
        service,preview=self.service()
        names=[{'sub_title':f'S01E{e:03}.chs.ass'} for e in range(1,501)]
        with patch.object(service,'_request',return_value={'subs':names}):
            broad=service.search_selected(MEDIA)
            pack=next(c for c in broad['candidates'] if c['subtitle_id']=='season-pack')
            result=service.preview(pack['id'],1,450)
        self.assertEqual([f['title'] for f in result['files']],['S01E450.chs.ass'])

    def test_failed_archive_does_not_leak_unverified_pack_into_results(self):
        service,_=self.service()
        with patch.object(service,'_request',side_effect=subtitles.SubtitleError('预览失败')):
            result=service.search_episode(MEDIA,1,1)
        self.assertTrue(result['success']);self.assertEqual([c['title'] for c in result['candidates']],['Alien.S01E01.chs.srt'])
        self.assertTrue(result['archive_warning'])
        self.assertFalse(service._episode_cache)


if __name__=='__main__':unittest.main()
