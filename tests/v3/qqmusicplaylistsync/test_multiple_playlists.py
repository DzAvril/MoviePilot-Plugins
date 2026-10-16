import ast
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlsplit,urljoin

import pytest

from test_core import core,envelope,raw_song


def method(name, **namespace):
    p=Path(__file__).parents[3]/'plugins.v3/qqmusicplaylistsync/__init__.py'
    cls=next(n for n in ast.parse(p.read_text()).body if isinstance(n,ast.ClassDef))
    node=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
    scope={'PlaylistError':core.PlaylistError,'playlist_id':core.playlist_id,'urlsplit':urlsplit,'urljoin':urljoin,
           'ThreadPoolExecutor':ThreadPoolExecutor,'as_completed':as_completed,'fetch_playlist':core.fetch_playlist,**namespace}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(p),'exec'),scope)
    return scope[name]


def test_short_qq_link_resolves_canonical_id_without_following_unvalidated_redirects():
    calls=[]
    def get(url,**kwargs):
        calls.append((url,kwargs))
        return SimpleNamespace(status_code=302,headers={'Location':'https://y.qq.com/n/ryqq_v2/playlist/9450108630?x=1'})
    plugin=SimpleNamespace(_playlist_aliases={})
    resolve=method('_resolve_playlist_id',RequestUtils=lambda **_:SimpleNamespace(get_res=get))
    short='https://c6.y.qq.com/base/fcgi-bin/u?__=TSWtRgFdqLnS'
    assert resolve(plugin,short)=='9450108630'
    assert resolve(plugin,short)=='9450108630'
    assert calls==[(short,{'allow_redirects':False})]


def test_short_link_external_redirect_is_rejected_before_requesting_destination():
    calls=[]
    def get(url,**kwargs):
        calls.append(url)
        return SimpleNamespace(status_code=302,headers={'Location':'http://127.0.0.1/secret?id=1'})
    resolve=method('_resolve_playlist_id',RequestUtils=lambda **_:SimpleNamespace(get_res=get))
    with pytest.raises(core.PlaylistError,match='跳转'):
        resolve(SimpleNamespace(_playlist_aliases={}),'https://c6.y.qq.com/base/fcgi-bin/u?__=test')
    assert len(calls)==1


def test_canonical_ids_do_not_make_network_requests_and_unknown_hosts_are_not_fetched():
    resolve=method('_resolve_playlist_id',RequestUtils=lambda **_:pytest.fail('unexpected request'))
    plugin=SimpleNamespace(_playlist_aliases={})
    assert resolve(plugin,'9450108630')=='9450108630'
    with pytest.raises(core.PlaylistError):
        resolve(plugin,'https://example.test/?id=12')


def test_one_unreadable_playlist_does_not_cancel_other_fetches():
    def request(pid,offset,count):
        if pid=='2':raise core.PlaylistError('private playlist')
        return envelope([raw_song(int(pid))],1,False)
    plugin=SimpleNamespace(_request_page=request,_fetch_filtered=lambda _:[])
    snapshots,errors=method('_fetch_playlists')(plugin,['1','2','3'])
    assert set(snapshots)=={'1','3'}
    assert errors=={'2':'private playlist'}
