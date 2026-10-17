import importlib.util
import os
import sys
from copy import deepcopy
from pathlib import Path
from threading import Event, Lock, RLock
from types import MethodType, SimpleNamespace

import pytest

from test_core import core, snapshot
from test_selected_downloads import plugin_methods
from test_lifecycle import lifecycle

ROOT = Path(__file__).parents[3] / 'plugins.v3/qqmusicplaylistsync'


def load(name):
    spec = importlib.util.spec_from_file_location(f'app.plugins.qqmusicplaylistsync.{name}', ROOT / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


library, history = load('library'), load('history')
DAY = 86400
NOW = 200 * DAY
OLD = 100 * DAY


def test_cache_covers_other_playlist_titles_without_rescanning_and_expires_after_ten_minutes():
    clock, calls = [0], []
    cache = library.LibraryIndexCache(clock=lambda: clock[0])
    def scan(**kwargs):
        calls.append(kwargs)
        return {('a', 'artist'): '/music/a', ('b', 'artist'): '/music/b'}
    options = dict(settings={'library_path': '/music'}, titles={'a', 'b'}, scan=scan)
    assert cache.get(wanted={'a'}, **options) == {('a', 'artist'): '/music/a'}
    for second in range(15, 600, 15):
        clock[0] = second
        assert cache.get(wanted={'b'}, **options) == {('b', 'artist'): '/music/b'}
    assert len(calls) == 1
    assert cache.snapshot()['scans'] == 1
    clock[0] = 600
    cache.get(wanted={'a'}, **options)
    assert len(calls) == 2
    assert cache.snapshot()['scans'] == 2


def test_directory_storage_and_new_title_invalidate_the_cache_and_clear_old_tags():
    cache = library.LibraryIndexCache()
    calls = []
    def scan(**kwargs):
        calls.append(kwargs['settings']['library_path'])
        return {}
    options = dict(wanted={'a'}, titles={'a'}, scan=scan)
    cache.get(settings={'library_path': '/one'}, **options)
    cache.tags['old-file'] = 'old'
    cache.get(settings={'library_path': '/two'}, **options)
    assert not cache.tags and calls == ['/one', '/two']
    cache.get(settings={'library_path': '/two'}, wanted={'new'}, titles={'a', 'new'}, scan=scan)
    assert len(calls) == 3
    cache.get(settings={'library_path': '/two', 'library_storage': 'u115'}, **options)
    cache.get(settings={'library_path': None}, **options)
    assert len(calls) == 3 and not cache.index


def test_failed_or_interrupted_scan_is_not_cached():
    cache, stopped = library.LibraryIndexCache(), Event()
    def fail(**kwargs): raise OSError('unavailable')
    options = dict(settings={'library_path': '/music'}, wanted={'a'}, titles={'a'})
    with pytest.raises(OSError): cache.get(scan=fail, **options)
    assert cache.refreshed_at is None
    def interrupt(**kwargs):
        stopped.set()
        return {('a', 'artist'): '/music/a'}
    assert cache.get(scan=interrupt, stopped=stopped.is_set, **options) == {}
    assert cache.refreshed_at is None


def test_metadata_cache_is_bounded_and_retains_latest_entries():
    cache = library.TagCache(limit=2)
    cache['a'], cache['b'], cache['c'] = 1, 2, 3
    assert list(cache) == ['b', 'c']
    cache['c'] = 4
    assert len(cache) == 2 and cache['c'] == 4


def test_real_status_refresh_walks_once_but_rechecks_deleted_files_and_native_transfers(tmp_path):
    root = tmp_path / 'music'
    root.mkdir()
    found = root / 'a.flac'
    found.write_bytes(b'audio')
    clock, walks, transfers = [0], [], []
    state = {'tracks': {mid: {'present': True, 'status': 'subscribed', 'song':
             {'title': title, 'artists': ['artist']}} for mid, title in [('a', 'A'), ('b', 'B')]}}
    class Tags(dict):
        @property
        def tags(self): return self
    def walk(*args, **kwargs):
        walks.append(args[0])
        return os.walk(*args, **kwargs)
    ns = plugin_methods({'_library_index', '_cached_library_index', '_status_file_exists', 'page_downloads'}, {
        'Path': Path, 'os': SimpleNamespace(walk=walk), 'AudioFile': lambda path, **k: Tags(title=[path.stem.upper()], artist=['artist']),
        'MutagenError': RuntimeError, 'text_key': core.text_key, 'song_lifecycle': lifecycle.song_lifecycle,
        'MediaType': SimpleNamespace(MUSIC='music'), 'MediaSource': str, 'MUSIC_SOURCES': ('qqmusic', 'netease'),
        'download_cards': lambda *a: [], 'time': SimpleNamespace(time=lambda: NOW)})
    plugin = SimpleNamespace(_stop=Event(), _status_lock=Lock(), _status_library_files={}, _downloader_status=lambda:{},
        _status_index=library.LibraryIndexCache(clock=lambda: clock[0]), AUDIO_EXTENSIONS={'.flac'},
        STATE_KEY='state', get_data=lambda key: state if key == 'state' else {},
        _resolved_settings=lambda: {'library_path': str(root), 'library_storage': 'local'},
        _status_transfer_rows=lambda filters: list(transfers), _status_download_tasks=lambda *a: {})
    for name in ('_library_index', '_cached_library_index', '_status_file_exists', 'page_downloads'):
        setattr(plugin, name, MethodType(ns[name], plugin))
    assert plugin.page_downloads()['song_states']['a']['status'] == 'library'
    clock[0] = 15
    assert plugin.page_downloads()['song_states']['a']['status'] == 'library'
    assert len(walks) == 1
    found.unlink()
    clock[0] = 30
    assert plugin.page_downloads()['song_states']['a']['status'] != 'library'
    # A new successful native transfer is visible without waiting for the directory scan.
    other = root / 'b.flac'
    other.write_bytes(b'audio')
    transfers.append(dict(id=1, media_source='qqmusic', media_id='b', music_type='recording',
                          title='B', status=True, dest=str(other), dest_storage='local'))
    assert plugin.page_downloads()['song_states']['b']['status'] == 'library'
    assert len(walks) == 1
    clock[0] = 600
    plugin.page_downloads()
    assert len(walks) == 2


def test_membership_timestamps_allow_full_grace_period_and_survive_failed_fetches():
    state = core.merge_snapshot(None, snapshot([1, 2]), OLD)
    pid = state['playlist']['id']
    core.merge_playlists(state, {pid: snapshot([1])}, {}, [pid], NOW)
    assert state['tracks']['song00002']['inactive_since'] == NOW
    core.merge_playlists(state, {}, {pid: 'private'}, [pid], NOW + DAY)
    assert state['tracks']['song00001']['present']
    assert 'inactive_since' not in state['tracks']['song00001']
    assert state['tracks']['song00002']['inactive_since'] == NOW
    core.merge_playlists(state, {}, {}, [], NOW + 2 * DAY)
    assert state['playlists'][pid]['disabled_since'] == NOW + 2 * DAY
    core.merge_playlists(state, {pid: snapshot([1, 2])}, {}, [pid], NOW + 3 * DAY)
    assert 'disabled_since' not in state['playlists'][pid]
    assert all('inactive_since' not in item for item in state['tracks'].values())


def test_retention_protects_current_subscriptions_and_all_selected_file_guards():
    state = {'tracks': {mid: dict(present=mid == 'current', inactive_since=OLD,
             song={'title': mid}) for mid in ['current', 'native', 'guarded', 'old', 'recent', 'legacy']},
             'identity_aliases': {'netease:old': 'old', 'netease:guarded': 'guarded'},
             'playlists': {'disabled': dict(enabled=False, disabled_since=OLD, mids=['old']),
                           'failed': dict(enabled=True, mids=['current']),
                           'recent': dict(enabled=False, disabled_since=NOW, mids=['recent'])}}
    state['tracks']['recent']['inactive_since'] = NOW
    state['tracks']['legacy'].pop('inactive_since')
    registry = {'hash': {'matches': {'guarded': 'file'}}}
    removed = history.prune_history(state, registry, now=NOW, active_subscriptions={'native'})
    assert removed == {'tracks': 1, 'aliases': 1, 'playlists': 1}
    assert set(state['tracks']) == {'current', 'native', 'guarded', 'recent', 'legacy'}
    assert state['identity_aliases'] == {'netease:guarded': 'guarded'}
    assert set(state['playlists']) == {'failed', 'recent'}


def retired_fixture():
    entry = dict(hash='hash', phase='started', at=OLD, source_root='/download/album', files=['a', 'b'],
                 fullpaths=['/download/album/a', '/download/album/b'])
    rows = [dict(id=i, download_hash='hash', src=path, status=True,
                 dest=f'/music/{i}', dest_storage='local') for i, path in enumerate(entry['fullpaths'], 1)]
    options = dict(now=NOW, source_absent=lambda path: True, file_exists=lambda path, storage: True)
    return entry, dict(success=True, state='missing'), rows, options


def test_download_guard_only_retires_after_every_selected_file_is_in_library():
    entry, task, rows, options = retired_fixture()
    assert history.retired_download(entry, task, rows, **options)
    assert not history.retired_download(entry, task, rows[:1], **options)
    rows.append({**rows[0], 'id': 5, 'status': False})
    assert not history.retired_download(entry, task, rows, **options)


@pytest.mark.parametrize('field,value', [('phase', 'paused'), ('phase', 'preparing'), ('at', NOW),
    ('at', None), ('error', 'failed'), ('source_root', ''), ('source_root', '/download/../unsafe'), ('fullpaths', [])])
def test_unfinished_new_or_unverifiable_download_records_never_expire(field, value):
    entry, task, rows, options = retired_fixture()
    entry[field] = value
    assert not history.retired_download(entry, task, rows, **options)


@pytest.mark.parametrize('task', [dict(success=False), dict(success=True, state='uploading'),
                                 dict(success=True, state='downloading')])
def test_existing_or_unreachable_downloader_tasks_keep_their_guard(task):
    entry, _, rows, options = retired_fixture()
    assert not history.retired_download(entry, task, rows, **options)


def test_remaining_source_or_missing_library_file_keeps_guard():
    entry, task, rows, options = retired_fixture()
    assert not history.retired_download(entry, task, rows, **{**options, 'source_absent': lambda _: False})
    assert not history.retired_download(entry, task, rows, **{**options, 'file_exists': lambda *a: False})


def test_source_absence_requires_a_missing_file_and_preserves_symlinks_or_permission_errors(tmp_path, monkeypatch):
    missing = tmp_path / 'missing'
    assert history.local_source_absent(missing)
    link = tmp_path / 'link'
    link.symlink_to(missing)
    assert not history.local_source_absent(link)
    def denied(self): raise PermissionError('permission denied')
    monkeypatch.setattr(Path, 'lstat', denied)
    assert not history.local_source_absent(missing)


def cleanup_fixture():
    data = {'selected_downloads': {}}
    writes, calls = [], []
    plugin = SimpleNamespace(_state={'tracks': {'old': dict(present=False, inactive_since=OLD)}},
        _stop=Event(), _selection_lock=RLock(),
        _active_subscription_keys=lambda: calls.append('active') or set(),
        _resolved_settings=lambda: {}, get_data=lambda key: data.get(key),
        _status_download_tasks=lambda *a: {}, _status_transfer_rows=lambda filters: [],
        _status_file_exists=lambda *a: False, save_data=lambda key, value: data.update({key: value}),
        _save=lambda state: writes.append(deepcopy(state)))
    ns = plugin_methods({'_cleanup_history'}, dict(cleanup_due=history.cleanup_due, expired=history.expired,
         retired_download=history.retired_download, prune_history=history.prune_history,
         RETENTION_DAYS=history.RETENTION_DAYS, local_source_absent=lambda _: True,
         logger=SimpleNamespace(warning=lambda *a: None),
         MediaType=SimpleNamespace(MUSIC='music')))
    plugin._cleanup_history = MethodType(ns['_cleanup_history'], plugin)
    return plugin, data, writes, calls


def test_daily_cleanup_runs_once_and_leaves_native_state_untouched():
    plugin, data, writes, calls = cleanup_fixture()
    plugin._cleanup_history(NOW)
    assert not plugin._state['tracks'] and writes[-1]['last_cleanup']['tracks'] == 1
    plugin._cleanup_history(NOW + 3600)
    assert calls == ['active'] and len(writes) == 1
    plugin._cleanup_history(NOW + DAY)
    assert len(writes) == 2
    assert set(data) == {'selected_downloads'}


def test_missing_native_subscription_facts_defer_cleanup_without_mutation():
    plugin, _, writes, _ = cleanup_fixture()
    def unavailable(): raise OSError('temporarily unavailable')
    plugin._active_subscription_keys = unavailable
    before = deepcopy(plugin._state)
    plugin._cleanup_history(NOW)
    assert plugin._state == before and not writes


def test_cleanup_removes_retired_guards_but_preserves_active_tasks_and_their_song_records():
    plugin, data, writes, _ = cleanup_fixture()
    entry, task, rows, _ = retired_fixture()
    entry['matches'] = {'old': 'a'}
    data['selected_downloads'] = {'retired': deepcopy(entry), 'active': deepcopy(entry)}
    data['selected_downloads']['active']['matches'] = {'protected': 'a'}
    plugin._state['tracks']['protected'] = dict(present=False, inactive_since=OLD)
    plugin._status_download_tasks = lambda *a: {'retired': task, 'active': dict(success=True, state='stalledUP')}
    plugin._status_transfer_rows = lambda filters: [{**row, 'download_hash': 'retired'} for row in rows]
    plugin._status_file_exists = lambda *a: True
    plugin._cleanup_history(NOW)
    assert set(data['selected_downloads']) == {'active'}
    assert set(plugin._state['tracks']) == {'protected'}
    assert writes[-1]['last_cleanup']['downloads'] == 1


def test_active_subscription_query_paginates_without_reading_completed_history():
    calls = []
    def query(filters, request):
        calls.append(request['page'])
        return SimpleNamespace(items=[SimpleNamespace(media_source='netease', media_id='1')],
                               has_next=request['page'] == 1)
    ns = plugin_methods({'_active_subscription_keys'}, dict(list_subscriptions=query,
         MediaType=SimpleNamespace(MUSIC='music'), MUSIC_SOURCES=core.MUSIC_SOURCES, track_key=core.track_key))
    plugin = SimpleNamespace(_state={'identity_aliases': {'netease:1': 'qq-id'}})
    assert ns['_active_subscription_keys'](plugin) == {'qq-id'}
    assert calls == [1, 2]
