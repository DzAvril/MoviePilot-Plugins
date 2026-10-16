import pytest

from test_core import core, envelope, raw_song
from test_netease import raw as netease_song
from test_page import page


@pytest.mark.parametrize('source,value,expected', [
    ('qqmusic', 'http://y.gtimg.cn/music/cover.jpg', 'https://y.gtimg.cn/music/cover.jpg'),
    ('qqmusic', '//qpic.y.qq.com/music_cover/cover/300?n=1&amp;a=2',
     'https://qpic.y.qq.com/music_cover/cover/300?n=1&a=2'),
    ('netease', 'https://p1.music.126.net/cover.jpg', 'https://p1.music.126.net/cover.jpg'),
    ('netease', 'http://p2.music.127.net/cover.jpg', 'https://p2.music.127.net/cover.jpg'),
])
def test_public_platform_covers_use_https(source, value, expected):
    assert core.playlist_cover_url(value, source) == expected


@pytest.mark.parametrize('source,value', [
    ('qqmusic', 'https://y.gtimg.cn.evil.test/cover.jpg'),
    ('netease', 'http://127.0.0.1/internal'),
    ('netease', 'https://example.test/cover.jpg'),
    ('qqmusic', 'https://user:password@y.gtimg.cn/cover.jpg'),
    ('qqmusic', 'https://y.gtimg.cn:8080/cover.jpg'),
    ('qqmusic', 'file:///tmp/cover.jpg'),
    ('qqmusic', 'data:image/svg+xml,anything'),
    ('qqmusic', 'https://[invalid'),
    ('netease', None),
])
def test_unrecognized_or_invalid_cover_urls_fall_back_without_breaking_sync(source, value):
    assert core.playlist_cover_url(value, source) == ''


def test_qq_cover_survives_later_pages_that_only_include_song_metadata():
    calls = []
    def request(pid, offset, count):
        calls.append(offset)
        response = envelope([raw_song(offset + 1)], 2, offset == 0)
        if offset == 0:
            response['req_0']['data']['dirinfo']['picurl'] = 'http://y.gtimg.cn/playlist.jpg'
        return response
    result = core.fetch_playlist(request, '123', page_size=1)
    assert result['cover_url'] == 'https://y.gtimg.cn/playlist.jpg'
    assert len(result['songs']) == 2 and calls == [0, 1]


def test_both_platform_covers_reach_page_projection_and_failed_fetch_keeps_the_previous_cover():
    response = envelope([raw_song(1)], 1, False)
    response['req_0']['data']['dirinfo']['picurl'] = 'https://y.gtimg.cn/qq.jpg'
    qq = core.fetch_playlist(lambda *a: response, '123')
    calls = []
    def request(route, query):
        calls.append(route)
        return {'code': 200, 'playlist': {'name': '网易云歌单', 'trackCount': 1,
            'tracks': [netease_song()], 'coverImgUrl': 'http://p1.music.126.net/netease.jpg'}}
    netease = core.fetch_netease_playlist(request, '456')
    assert calls == ['/playlist/detail']
    pids = ['123', 'netease:456']
    state = core.merge_playlists(None, dict(zip(pids, (qq, netease))), {}, pids, 10)
    state = core.merge_playlists(state, {}, dict.fromkeys(pids, 'unavailable'), pids, 20)
    data = page.page_projection(state, core.summary(state), {}, {}, {}, [])
    assert [p['cover_url'] for p in data['playlists']] == [
        'https://y.gtimg.cn/qq.jpg', 'https://p1.music.126.net/netease.jpg']
    qq['cover_url'] = 'https://y.gtimg.cn/new.jpg'
    state = core.merge_playlists(state, {'123': qq}, {}, pids, 30)
    assert state['playlists']['123']['cover_url'] == 'https://y.gtimg.cn/new.jpg'
