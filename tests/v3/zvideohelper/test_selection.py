import importlib
import json
import unittest
from test_subtitles import subtitles
selection = importlib.import_module('zvideo_test.selection')


def group(name, imdb, sub_id, title):
    return {'name':name,'imdb':imdb,'subs':[{'sub_id':sub_id,'sub_title':title,'download_url':'https://example.com/synthetic-private-locator'}]}


class FilmSelectionTests(unittest.TestCase):
    def test_choices_distinguish_movie_and_tv_with_same_id_and_hide_unneeded_data(self):
        records=[{'tmdb_id':348,'title':'异形','type':'电影','year':'1979','imdb_id':'tt0078748','secret':'synthetic-private'},
            {'tmdb_id':348,'title':'同名剧集','type':'电视剧','year':'2025'},
            {'tmdb_id':348,'title':'异形','type':'电影','year':'1979'},
            {'media_id':1,'title':'歌曲','type':'音乐'},
            {'media_id':99,'media_source':'douban','title':'其他来源','type':'电影'}]
        result=selection.project_media_choices(records)
        self.assertEqual([(i['id'],i['media_type'],i['year']) for i in result],[('348','movie','1979'),('348','tv','2025')])
        self.assertNotIn('synthetic-private',json.dumps(result))

    def test_selected_imdb_excludes_remakes_and_provider_keyword_noise(self):
        media={'id':'348','media_type':'movie','title':'异形','original_title':'Alien','year':'1979','imdb_id':'tt0078748'}
        queries=[]
        def provider(args):
            queries.append(json.loads(args[args.index('--params')+1])['q'])
            return {'ok':True,'data':{'subs':[group('异形','tt0078748','a','Alien.1979.chs.srt'),
                group('异形2','tt0090605','b','Aliens.1986.chs.srt'),group('异形','tt9999999','c','Alien.1979.chs.srt')]}}
        result=subtitles.SubtitleService('/unused',run=provider).search_selected(media)
        self.assertEqual(queries,['tt0078748'])
        self.assertEqual([c['subtitle_id'] for c in result['candidates']],['a'])
        self.assertEqual(result['selected_media'],media)
        self.assertNotIn('synthetic-private-locator',json.dumps(result))

    def test_title_fallback_checks_exact_work_name_and_year(self):
        media={'id':'348','media_type':'movie','title':'异形','original_title':'Alien','year':'1979','imdb_id':'tt0078748'}
        queries=[]
        def provider(args):
            query=json.loads(args[args.index('--params')+1])['q'];queries.append(query)
            groups=[] if query.startswith('tt') else [group('异形','','a','Alien.1979.chs.srt'),
                group('异形','','b','Alien.2011.chs.srt'),group('异形2','','c','Alien.1979.sequel.chs.srt')]
            return {'ok':True,'data':{'subs':groups}}
        result=subtitles.SubtitleService('/unused',run=provider).search_selected(media)
        self.assertEqual(queries,['tt0078748','异形'])
        self.assertEqual([c['subtitle_id'] for c in result['candidates']],['a'])

    def test_unconfirmed_subtitles_remain_empty_instead_of_showing_other_films(self):
        media={'id':'348','media_type':'movie','title':'异形','original_title':'Alien','year':'1979','imdb_id':'tt0078748'}
        response={'ok':True,'data':{'subs':[group('异形2','tt0090605','b','Aliens.1986.chs.srt')]}}
        result=subtitles.SubtitleService('/unused',run=lambda a:response).search_selected(media)
        self.assertTrue(result['success']);self.assertEqual(result['count'],0)
        self.assertIn('所选作品',result['message'])

    def test_lookup_rejects_empty_control_characters_and_unknown_media_types(self):
        for keyword,kind in [('', 'all'),('film\nextra','movie'),('film','music')]:
            with self.subTest(keyword=keyword,kind=kind),self.assertRaises(ValueError):selection.validate_lookup(keyword,kind)


if __name__=='__main__':unittest.main()
