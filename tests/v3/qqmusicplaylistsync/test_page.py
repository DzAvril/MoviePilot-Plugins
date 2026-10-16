import sys
import importlib.util
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).parents[3] / 'plugins.v3/qqmusicplaylistsync'
spec = importlib.util.spec_from_file_location('app.plugins.qqmusicplaylistsync.page', ROOT / 'page.py')
page = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = page
spec.loader.exec_module(page)


def state():
    return {'tracks': {str(i): {'present': True, 'status': 'subscribed', 'playlist_ids': ['one', 'two'],
            'song': {'title': f'歌曲{i}', 'album': '专辑', 'artists': ['歌手'], 'cookie': 'private'}}
            for i in range(321)}}


def test_projection_keeps_all_songs_and_shared_playlist_membership_without_private_fields():
    source = state()
    source['tracks']['removed'] = {'present': False}
    before = deepcopy(source)
    overview = {'playlists': [{'id': 'one', 'title': '歌单', 'total': 291, 'mids': ['private']}],
                'playlist': {'unavailable': ['x']}, 'tracked': 321, 'subscribed': 301, 'library': 20}
    data = page.page_projection(source, overview, {'enabled': True, 'cookie': 'private'},
        {'save_path': '/music', 'cookie': 'private'}, {}, [])
    assert len(data['songs']) == 321
    assert data['songs'][0]['playlist_ids'] == ['one', 'two']
    assert data['unavailable'] == 1
    assert 'private' not in str(data)
    assert source == before


def test_metadata_projection_never_contacts_the_downloader_and_does_not_invent_completion():
    source = state()
    registry = {'hash': {'matches': {'0': '01.flac'}, 'files': ['disc/01.flac'], 'phase': 'started',
                         'audio_count': 10, 'title': 'resource', 'enclosure': 'https://private', 'cookie': 'secret'}}
    before = deepcopy(registry)
    card = page.download_cards(registry, source['tracks'])[0]
    assert card['progress'] is None and card['state'] is None
    assert card['title'] == '专辑' and card['artists'] == ['歌手']
    assert card['files'] == ['01.flac'] and card['selected'] == 1
    assert 'private' not in str(card) and 'secret' not in str(card)
    assert registry == before


def test_live_progress_failure_is_isolated_and_real_progress_survives():
    registry = {'bad': {'at': 2}, 'good': {'at': 1}}
    def read(key):
        if key == 'bad':
            raise RuntimeError('https://signed.secret/credentials')
        return {'success': True, 'progress': 0.82, 'state': 'stalledDL', 'cookie': 'secret'}
    cards = page.download_cards(registry, {}, read)
    assert cards[0]['progress'] is None and cards[0]['live_error']
    assert cards[1]['progress'] == .82 and cards[1]['state'] == 'stalledDL'
    assert 'secret' not in str(cards)


def test_download_history_is_bounded_and_missing_or_nonfinite_progress_is_unknown():
    registry = {str(i): {'at': i} for i in range(12)}
    cards = page.download_cards(registry, {}, lambda _: {'success': True, 'state': 'missing', 'progress': float('nan')})
    assert [card['id'] for card in cards] == ['11', '10', '9', '8', '7', '6']
    assert all(card['state'] == 'missing' and card['progress'] is None for card in cards)


def test_page_routes_require_login_and_preserve_existing_api_key_routes():
    from types import SimpleNamespace
    from test_selected_downloads import plugin_methods
    endpoint = lambda: None
    plugin = SimpleNamespace(**{name: endpoint for name in ('sync', 'status', 'selection_details', 'maintain_downloads', 'page_data', 'page_downloads')})
    routes = plugin_methods({'get_api'}, {})['get_api'](plugin)
    assert next(route for route in routes if route['path']=='/maintain_downloads')['methods']==['POST']
    by_path = {route['path']: route for route in routes}
    for path in ('/sync', '/status', '/selection'):
        assert by_path[path]['auth'] == 'apikey'
    for path in ('/page_data', '/page_downloads', '/page_sync'):
        assert by_path[path]['auth'] == 'bear'
    assert not any(route.get('allow_anonymous') for route in routes)
