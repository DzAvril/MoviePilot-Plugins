import ast
from pathlib import Path
from types import SimpleNamespace, MethodType
from threading import Lock
import time

from test_core import core


def guard(files, *, content=b'torrent', source='qqmusic', music_type='recording', enclosure='https://example.test/immutable.torrent', error=False, downloader_available=True):
    path = Path(__file__).parents[3]/'plugins.v3/qqmusicplaylistsync/__init__.py'
    tree = ast.parse(path.read_text())
    cls = next(n for n in tree.body if isinstance(n,ast.ClassDef))
    methods = [n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in
               ('guard_single_track','_inspect_plan','_file_plan','_owns_media','_record_download_error')]
    for method in methods:
        method.decorator_list = []
    calls=[]
    saved={}
    def download(_):
        calls.append('inspect')
        if error: raise RuntimeError('credential-must-not-be-logged')
        return content,'folder',files
    namespace={'time':time,'DownloadChain':lambda:SimpleNamespace(download_torrent=download),
               'MUSIC_SOURCES':core.MUSIC_SOURCES,'track_key':core.track_key,
               'track_file_selection':core.track_file_selection,'logger':SimpleNamespace(info=lambda text:calls.append(text))}
    exec(compile(ast.Module(body=methods,type_ignores=[]),str(path),'exec'),namespace)
    plugin=SimpleNamespace(SOURCE='qqmusic',plugin_name='QQ音乐歌单同步',plugin_version='1.4.0',_guard_lock=Lock(),_guard_cache={},
             _adapter_error='',
             _downloader_status=lambda *_:dict(name='TR',available=downloader_available,error='' if downloader_available else '无法连接下载器 TR'),
             _download_options=lambda:dict(downloader=None,save_path=None),
             _state={'tracks':{'mid123':{'song':{'title':'纵横四海','artists':['李荣浩']}}}},
             get_data=lambda key:saved.get(key),save_data=lambda key,value:saved.update({key:value}))
    for method in methods:
        setattr(plugin,method.name,MethodType(namespace[method.name],plugin))
    event=SimpleNamespace(event_data=SimpleNamespace(cancel=False,source=None,reason=None,
              context=SimpleNamespace(media_info=SimpleNamespace(media_source=source,music_type=music_type,media_id='mid123'),
                                      torrent_info=SimpleNamespace(title='李荣浩 - 纵横四海',site=1,enclosure=enclosure))))
    namespace['guard_single_track'](plugin,event)
    return event,calls,saved


def test_download_event_accepts_album_only_after_the_target_file_is_verified():
    event,calls,saved=guard(['01. 纵横四海.m4a','02. 我们好好的.m4a'])
    assert not event.event_data.cancel
    assert saved['single_track_checks'][-1]['allowed'] is True
    assert '1/2' in saved['single_track_checks'][-1]['reason']


def test_download_event_allows_verified_track():
    event,calls,saved=guard(['01. 纵横四海.m4a'])
    assert not event.event_data.cancel
    assert saved['single_track_checks'][-1]['allowed'] is True
    assert event.event_data.options['save_path'] is None


def test_other_sources_and_explicit_album_subscriptions_are_not_intercepted():
    for source,mtype in [('musicbrainz','recording'),('qqmusic','album')]:
        event,calls,saved=guard(['01. one.m4a','02. two.m4a'],source=source,music_type=mtype)
        assert not event.event_data.cancel and not calls and not saved


def test_metadata_or_network_failure_never_falls_back_to_unchecked_download():
    for options in [{'enclosure':'magnet:?xt=urn:btih:abc'},{'error':True},{'content':None}]:
        event,calls,_=guard([],**options)
        assert event.event_data.cancel
        assert 'credential' not in str(calls)


def test_download_event_skips_cue_before_any_downloader_submission():
    event,_,saved=guard(['纵横四海.flac','album.cue'])
    assert event.event_data.cancel and 'CUE' in saved['single_track_checks'][-1]['reason']


def test_unavailable_downloader_is_rejected_before_torrent_fetch_and_error_is_persisted():
    event,calls,saved=guard(['01. 纵横四海.flac'],downloader_available=False)
    assert event.event_data.cancel and 'TR' in event.event_data.reason
    assert not calls and 'single_track_checks' not in saved
    assert saved['download_errors']['mid123']['reason']==event.event_data.reason
