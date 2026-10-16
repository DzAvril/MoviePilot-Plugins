import json
from copy import deepcopy
from threading import Event
from types import SimpleNamespace

import pytest

from test_core import core
from test_selected_downloads import plugin_methods, submission, FILES
from test_lifecycle import lifecycle
from test_multiple_playlists import method
from test_search_dispatch import fixture as search_fixture, plugin_method


def raw(sid=1, **overrides):
    return {'id': sid, 'name': '歌曲', 'ar': [{'name': '歌手'}],
            'al': {'id': 9, 'name': '专辑', 'picUrl': 'http://p1.music.126.net/cover.jpg'},
            'dt': 180000, 'publishTime': 1609459200000, 'no': 1, **overrides}


def snapshot(songs, pid='netease:123'):
    return dict(id=pid, title='歌单', total=len(songs), songs=songs,
                member_ids=[song['mid'] for song in songs])


@pytest.mark.parametrize('url', ['80068278', 'https://music.163.com/#/my/m/music/playlist?id=80068278',
    'https://music.163.com/playlist?id=80068278&userid=1',
    'https://y.music.163.com/m/playlist?id=80068278', 'https://music.163.com/playlist/80068278'])
def test_accepts_desktop_mobile_share_and_user_fragment_routes(url):
    assert core.netease_playlist_id(url) == '80068278'


@pytest.mark.parametrize('url', ['0', 'https://music.163.com/song?id=1', 'https://music.163.com/album?id=1',
    'https://music.163.com.evil.test/playlist?id=1', 'file:///playlist?id=1',
    'https://music.163.com/playlist?id=-1', 'https://music.163.com/myplaylist?id=1'])
def test_rejects_invalid_ids_other_media_and_foreign_hosts(url):
    with pytest.raises(core.PlaylistError):
        core.netease_playlist_id(url)


@pytest.mark.parametrize('total', [270, 1205])
def test_fetches_every_id_in_bounded_batches_and_restores_playlist_order(total):
    calls = []
    def request(route, query):
        calls.append((route, query))
        if route == '/playlist/detail':
            return dict(code=200, playlist=dict(name='完整歌单', trackCount=total,
                trackIds=[{'id': sid} for sid in range(1, total+1)], tracks=[raw(sid) for sid in range(1, 7)]))
        ids = [int(sid) for sid in query['ids'].split(',')]
        assert len(ids) <= 200
        return dict(code=200, songs=[raw(sid) for sid in reversed(ids)])
    result = core.fetch_netease_playlist(request, '80068278')
    assert result['total'] == len(result['songs']) == total
    assert [song['source_id'] for song in result['songs']] == [str(sid) for sid in range(1, total+1)]
    assert len(calls) == 1 + (total-6+199)//200
    assert result['id'] == 'netease:80068278' and not result['unavailable']


@pytest.mark.parametrize('payload', [dict(code=20001), dict(code=200, playlist={}),
    dict(code=200, playlist=dict(trackCount=2, trackIds=[{'id': 1}], tracks=[raw()])),
    dict(code=200, playlist=dict(trackCount=2, trackIds=[{'id': 1}, {'id': 1}]))])
def test_private_truncated_or_duplicate_membership_never_becomes_successful_snapshot(payload):
    with pytest.raises(core.PlaylistError):
        core.fetch_netease_playlist(lambda *_: payload, '1')


def test_failed_detail_batch_preserves_entire_old_snapshot():
    def request(route, query):
        if route == '/playlist/detail':
            return dict(code=200, playlist=dict(trackCount=1, trackIds=[{'id': 1}]))
        return dict(code=500, songs=[])
    with pytest.raises(core.PlaylistError):
        core.fetch_netease_playlist(request, '1')


def test_deleted_song_is_visible_and_its_previous_member_is_retained():
    song = core.normalize_netease_song(raw())
    previous = core.merge_playlists(None, {'netease:123': snapshot([song])}, {}, ['netease:123'], 10)
    payload = dict(code=200, playlist=dict(trackCount=1, trackIds=[{'id': 1}], tracks=[]))
    result = core.fetch_netease_playlist(lambda route, _: payload if route == '/playlist/detail' else dict(code=200, songs=[]), '123')
    assert result['unavailable'][0]['songid'] == '1'
    assert result['member_ids'] == ['netease:1']
    merged = core.merge_playlists(previous, {'netease:123': result}, {}, ['netease:123'], 20)
    assert merged['tracks']['netease:1']['present']
    assert merged['playlists']['netease:123']['unavailable']


def test_normalization_preserves_recording_version_and_public_artwork():
    song = core.normalize_netease_song(raw(name='歌曲 (Live)'))
    assert song['mid'] == 'netease:1' and song['source_id'] == '1'
    assert song['title'] == '歌曲 (Live)' and song['duration'] == 180
    assert song['year'] == 2021 and song['release_date'] == '2021-01-01'
    assert song['cover_url'] == 'https://p1.music.126.net/cover.jpg'
    assert not core.normalize_netease_song(raw(al={'name': '专辑', 'picUrl': 'http://127.0.0.1/private'}))['cover_url']


def test_cross_platform_recording_alias_preserves_old_qq_subscription_and_native_identity():
    qq = dict(mid='qq00001', title='歌曲', artists=['歌手'], album='专辑', duration=180, year=2021)
    old = core.merge_playlists(None, {'123': snapshot([qq], '123')}, {}, ['123'], 10)
    old['tracks']['qq00001'].update(status='subscribed', subscription_id=42, search_requested_at=11)
    net = core.normalize_netease_song(raw())
    merged = core.merge_playlists(old, {'netease:123': snapshot([net])}, {}, ['123','netease:123'], 20)
    assert len(merged['tracks']) == 1
    assert merged['tracks']['qq00001']['subscription_id'] == 42
    assert merged['tracks']['qq00001']['search_requested_at'] == 11
    assert merged['tracks']['qq00001']['song'] == qq
    assert merged['tracks']['qq00001']['playlist_ids'] == ['123','netease:123']
    assert core.track_key(merged, 'netease', 1) == 'qq00001'
    restored = json.loads(json.dumps(merged))
    again = core.merge_playlists(restored, {}, {'netease:123':'temporarily private'}, ['netease:123'], 30)
    assert again['tracks']['qq00001']['present'] and again['tracks']['qq00001']['subscription_id'] == 42


@pytest.mark.parametrize('changes', [{'title':'歌曲 (Live)'}, {'album':'精选集'}, {'duration':183},
                                    {'year':2022}, {'artists':['其他歌手']}, {'album':''}])
def test_different_versions_or_uncertain_recordings_are_not_merged(changes):
    net = core.normalize_netease_song(raw())
    qq = {**net, 'source':'qqmusic', 'mid':'qq00001', **changes}
    merged = core.merge_playlists(None, {'1':snapshot([qq],'1'), 'netease:1':snapshot([net],'netease:1')}, {}, ['1','netease:1'], 10)
    assert len(merged['tracks']) == 2 and not merged['identity_aliases']


def test_ambiguous_cross_platform_candidates_are_not_merged():
    net = core.normalize_netease_song(raw())
    qq = [{**net, 'source':'qqmusic', 'mid':mid} for mid in ['qq00001','qq00002']]
    merged = core.merge_playlists(None, {'1':snapshot(qq,'1'), 'netease:1':snapshot([net],'netease:1')}, {}, ['1','netease:1'], 10)
    assert len(merged['tracks']) == 3 and not merged['identity_aliases']


def test_netease_creates_native_recording_with_raw_id_and_mp_directory_defaults():
    calls = []
    ns = plugin_methods({'_subscribe'}, dict(SubscribeChain=lambda:SimpleNamespace(add=lambda **kw:calls.append(kw)),
                        MediaType=SimpleNamespace(MUSIC='音乐'), MediaSource=str))
    song = core.normalize_netease_song(raw())
    plugin = SimpleNamespace(SOURCE='qqmusic', plugin_name='音乐歌单同步', _config=dict(downloader='',save_path=''),
                             _state={'tracks':{song['mid']:{'playlist_ids':['netease:123']}}})
    ns['_subscribe'](plugin, song)
    assert calls[0]['media_source'] == 'netease' and calls[0]['media_id'] == '1'
    assert calls[0]['music_type'] == 'recording' and calls[0]['title'] == '歌曲'
    assert calls[0]['downloader'] is None and calls[0]['save_path'] is None


def test_alias_recognition_returns_requested_native_identity_and_owns_only_recordings():
    ns = plugin_methods({'recognize_media','_owns_media','_file_plan'}, dict(MediaSource=str,
                        MusicInfo=lambda **kw:SimpleNamespace(**kw), track_file_selection=core.track_file_selection))
    song = dict(mid='qq00001',title='歌曲',artists=['歌手'],album='专辑',album_mid='abc123')
    plugin = SimpleNamespace(SOURCE='qqmusic',_state={'identity_aliases':{'netease:1':'qq00001'},
        'tracks':{'qq00001':dict(song=song,present=True)}})
    media = ns['recognize_media'](plugin, media_source='netease',media_id='1',music_type='recording')
    assert media.media_source == 'netease' and media.media_id == '1'
    assert media.detail_link == 'https://music.163.com/song?id=1' and media.cover_url.endswith('abc123.jpg')
    assert ns['_owns_media'](plugin,media)
    assert ns['_file_plan'](plugin,media,['01. 歌曲.flac','02. 别的歌.flac'])['files'] == ['01. 歌曲.flac']
    assert not ns['_file_plan'](plugin,media,['歌曲.flac','album.cue'])['allowed']
    media.music_type='album'
    assert not ns['_owns_media'](plugin,media)


def test_netease_uses_same_pause_select_verify_and_resume_download_flow(monkeypatch):
    qb, data, history, result, _ = submission(monkeypatch,music_source='netease')
    assert result == ('a'*40,None)
    assert history[0].file_list == [FILES[0],FILES[2]]
    assert qb.calls.index('native-history') < qb.calls.index('resume')
    assert {row['index'] for row in qb.files if row['priority']} == {12,8}


def test_netease_subscriptions_are_dispatched_immediately_in_manual_queue():
    plugin, chain, events = search_fixture()
    plugin._state['tracks']['song00001']['song']['mid']='netease:1'
    plugin._state['tracks']['netease:1']=plugin._state['tracks'].pop('song00001')
    chain.subscription_repository.get(11).media_source='netease'
    chain.subscription_repository.get(11).media_id='1'
    assert plugin_method(chain,events)(plugin) == 2
    assert events[0][1]['source'] == 'manual' and events[-1][2]['delay_seconds'] == 0


def test_failed_netease_fetch_does_not_block_qq_playlists():
    plugin = SimpleNamespace(_request_page=lambda *_:None, _fetch_filtered=lambda _:[],
                             _netease_request=lambda *_:dict(code=401))
    fetch = method('_fetch_playlists', fetch_playlist=lambda *_,**kw:dict(id='1',songs=[]),
                   fetch_netease_playlist=core.fetch_netease_playlist)
    snapshots, errors = fetch(plugin,['1','netease:123'])
    assert list(snapshots) == ['1'] and 'netease:123' in errors


def test_netease_transfer_identity_updates_its_canonical_song_only():
    state = {'identity_aliases':{'netease:1':'qq00001'}, 'tracks':{'qq00001':dict(
        present=True,status='subscribed',song={'title':'歌曲'})}}
    row = dict(id=1,media_source='netease',media_id='1',music_type='recording',title='歌曲',
               status=True,dest='/music/song.flac',dest_storage='local')
    result = lifecycle.song_lifecycle(state,{}, {}, [row],file_exists=lambda path,storage:path==row['dest'])
    assert result['states']['qq00001']['status'] == 'library'
