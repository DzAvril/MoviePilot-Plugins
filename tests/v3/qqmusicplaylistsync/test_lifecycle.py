import sys
import importlib.util
from copy import deepcopy
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

from test_selected_downloads import plugin_methods

ROOT = Path(__file__).parents[3] / 'plugins.v3/qqmusicplaylistsync'
spec = importlib.util.spec_from_file_location('app.plugins.qqmusicplaylistsync.lifecycle', ROOT / 'lifecycle.py')
lifecycle = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lifecycle
spec.loader.exec_module(lifecycle)


def fixture():
    state = {'tracks': {mid: {'present': True, 'status': 'subscribed', 'song': {'title': title}}
                        for mid, title in [('a', '歌曲A'), ('b', '歌曲B'), ('c', '歌曲C')]}}
    registry = {'hash': {'files': ['01.A.flac', '02.B.flac'], 'fullpaths': ['/download/album/01.A.flac', '/download/album/02.B.flac'],
                         'source_root': '/download/album', 'matches': {'a': '01.A.flac', 'b': '02.B.flac'}}}
    task = {'success': True, 'state': 'downloading', 'progress': .5, 'file_priorities': [
        {'name': 'album/01.A.flac', 'priority': 1, 'progress': 1},
        {'name': 'album/02.B.flac', 'priority': 1, 'progress': .25},
        {'name': 'album/03.C.flac', 'priority': 0, 'progress': 1}]}
    return state, registry, {'hash': task}


def transfer(mid='a', success=True, **overrides):
    return {'id': 1, 'src': f'/download/album/0{1 if mid=="a" else 2}.{mid.upper()}.flac',
            'dest': f'/music/{mid}.flac', 'dest_storage': 'local', 'download_hash': 'hash', 'status': success, **overrides}


def project(state, registry, tasks, transfers=(), paths=(), **kwargs):
    return lifecycle.song_lifecycle(state, registry, tasks, transfers,
                                    file_exists=lambda path, storage: path in paths, **kwargs)


def test_progress_is_per_selected_track_not_whole_torrent_or_album():
    state, registry, tasks = fixture()
    before = deepcopy((state, registry, tasks))
    result = project(state, registry, tasks)
    assert result['states']['a']['status'] == 'downloaded'
    assert result['states']['b']['status'] == 'downloading' and result['states']['b']['progress'] == .25
    assert result['states']['c']['status'] == 'searching'
    assert sum(result['counts'].values()) == 3
    assert (state, registry, tasks) == before


def test_transfer_without_qq_id_links_only_its_exact_source_file_and_hash():
    state, registry, tasks = fixture()
    result = project(state, registry, tasks, [transfer()], ['/music/a.flac'])
    assert result['states']['a']['status'] == 'library'
    assert result['states']['b']['status'] == 'downloading'
    assert result['states']['c']['status'] == 'searching'
    assert result['library_files'] == {'a': {'path': '/music/a.flac', 'storage': 'local'}}


@pytest.mark.parametrize('overrides', [{'download_hash': 'other'}, {'src': '/other/01.A.flac'},
                                        {'src': '/download/album'}, {'status': None}])
def test_album_success_or_matching_basename_never_confirms_an_unverified_song(overrides):
    state, registry, tasks = fixture()
    result = project(state, registry, tasks, [transfer(**overrides)], ['/music/a.flac'])
    assert result['states']['a']['status'] != 'library'


def test_download_completed_requires_successful_transfer_and_a_valid_destination():
    state, registry, tasks = fixture()
    tasks['hash']['progress'] = 1
    result = project(state, registry, tasks, [transfer()], [])
    assert result['states']['a']['status'] == 'downloaded'
    assert result['states']['b']['status'] == 'downloading'
    assert result['states']['b']['progress'] == .25


def test_failed_transfer_is_visible_even_if_downloader_is_unavailable():
    state, registry, tasks = fixture()
    for live in (tasks, {}, {'hash': {'success': True, 'state': 'missing'}}):
        result = project(state, registry, live, [transfer(success=False)])
        assert result['states']['a']['status'] == 'transfer_failed'
        assert result['states']['b']['status'] != 'transfer_failed'


def test_confirmed_library_wins_over_missing_downloader_and_duplicate_downloads():
    state, registry, tasks = fixture()
    registry['other'] = deepcopy(registry['hash'])
    result = project(state, registry, {}, [transfer()], ['/music/a.flac'])
    assert result['states']['a']['status'] == 'library' and result['counts']['library'] == 1
    assert result['states']['b']['status'] == 'unknown'


def test_cached_and_preexisting_library_files_are_rechecked_without_editing_subscription_ledger():
    state, registry, tasks = fixture()
    state['tracks']['c'].update(status='library', library_path='/music/c.flac')
    before = deepcopy(state)
    cache = {'a': {'path': '/music/a.flac', 'storage': 'local'}, 'b': {'path': '/music/deleted.flac', 'storage': 'local'}}
    result = project(state, registry, tasks, paths=['/music/a.flac', '/music/c.flac'], library_files=cache)
    assert result['counts']['library'] == 2
    assert result['states']['b']['status'] == 'downloading'
    assert 'b' not in result['library_files'] and state == before


def test_legacy_identity_requires_exact_recording_and_song_title():
    state, registry, tasks = fixture()
    row = transfer(media_id='c', media_source='qqmusic', music_type='recording', title='歌曲C', dest='/music/c.flac', src='/older/c.flac')
    assert project(state, {}, {}, [row], ['/music/c.flac'])['states']['c']['status'] == 'library'
    for key, value in [('music_type', 'album'), ('title', '同名专辑'), ('media_source', 'other'), ('status', False)]:
        bad = {**row, key: value}
        assert project(state, {}, {}, [bad], ['/music/c.flac'])['states']['c']['status'] == 'searching'


@pytest.mark.parametrize('mode', ['unchecked', 'ambiguous', 'unknown'])
def test_unselected_or_unverifiable_file_never_inherits_100_percent_aggregate_progress(mode):
    state, registry, tasks = fixture()
    tasks['hash']['progress'] = 1
    if mode == 'unchecked': tasks['hash']['file_priorities'][0]['priority'] = 0
    elif mode == 'ambiguous': tasks['hash']['file_priorities'].append(deepcopy(tasks['hash']['file_priorities'][0]))
    else: tasks['hash']['file_priorities'][0]['progress'] = None
    assert project(state, registry, tasks)['states']['a']['status'] == 'unknown'


@pytest.mark.parametrize('qstate,label', [('checkingDL', '校验中'), ('pausedDL', '下载已暂停'), ('queuedDL', '等待下载'), ('error', '下载异常')])
def test_actual_download_state_and_track_progress_are_preserved(qstate, label):
    state, registry, tasks = fixture()
    tasks['hash']['state'] = qstate
    result = project(state, registry, tasks)
    assert result['states']['b']['status_label'] == label
    assert result['states']['b']['progress'] == .25
    if qstate == 'checkingDL': assert result['states']['a']['status'] == 'downloading'


def test_removed_songs_do_not_affect_counts():
    state, registry, tasks = fixture()
    state['tracks']['a']['present'] = False
    result = project(state, registry, tasks, [transfer()], ['/music/a.flac'])
    assert 'a' not in result['states'] and sum(result['counts'].values()) == 2


def test_native_file_check_rejects_empty_wrong_storage_and_outside_library_paths(tmp_path):
    library = tmp_path/'music'
    library.mkdir()
    file = library/'song.flac'
    file.write_bytes(b'audio')
    ns = plugin_methods({'_status_file_exists'}, {'Path': Path})
    exists = lambda path, storage='local': ns['_status_file_exists'](None, path, storage, {'library_path': str(library), 'library_storage': 'local'})
    assert exists(str(file))
    for path in (None, '', str(tmp_path/'outside.flac'), str(library), str(library/'../outside.flac')):
        assert not exists(path)
    assert not exists(str(file), 'u115')
    file.write_bytes(b'')
    assert not exists(str(file))


def test_downloader_is_read_once_per_service_and_only_unconfirmed_tasks_read_files():
    calls = []
    def get_torrents(**kwargs):
        calls.append(('tasks', kwargs['ids']))
        return [{'hash': 'first', 'state': 'downloading', 'progress': .5},
                {'hash': 'done', 'state': 'stalledUP', 'progress': 1}], None
    def get_files(torrent_hash, **kwargs):
        calls.append(('files', torrent_hash))
        return []
    server = SimpleNamespace(get_torrents=get_torrents, get_files=get_files)
    plugin = SimpleNamespace(_qb_service=lambda _: SimpleNamespace(instance=server))
    ns = plugin_methods({'_status_download_tasks'}, {'SelectionError': ValueError})
    result = ns['_status_download_tasks'](plugin, {'first': {'downloader': 'QB', 'matches': {'a': 'a.flac'}},
              'done': {'downloader': 'QB', 'matches': {'b': 'b.flac'}}}, {'a'})
    assert calls == [('tasks', ['first', 'done']), ('files', 'first')]
    assert result['done']['progress'] == 1


def test_transfer_query_paginates_all_rows_with_bounded_pages():
    calls = []
    def query(filters, request):
        calls.append((filters, request))
        return SimpleNamespace(items=[SimpleNamespace(id=request['page'])], has_next=request['page'] == 1)
    ns = plugin_methods({'_status_transfer_rows'}, {'list_transfer_history': query})
    rows = ns['_status_transfer_rows'](None, {'download_hash': 'hash'})
    assert [row['id'] for row in rows] == [1, 2]
    assert [request['count'] for _, request in calls] == [200, 200]
    assert all(filters == {'download_hash': 'hash'} for filters, _ in calls)


def test_library_tags_confirm_already_present_files_and_invalidate_on_file_change(tmp_path):
    import os
    from threading import Event
    from test_core import core
    root = tmp_path/'music'
    root.mkdir()
    audio = root/'song.flac'
    audio.write_bytes(b'audio')
    calls=[]
    current={'artist':'李荣浩'}
    class Tags(dict):
        @property
        def tags(self): return self
    def read(path, **kwargs):
        calls.append(str(path))
        return Tags(title=['模特'], artist=[current['artist']])
    ns=plugin_methods({'_library_index'}, {'Path':Path,'os':os,'AudioFile':read,'MutagenError':RuntimeError,'text_key':core.text_key})
    plugin=SimpleNamespace(_stop=Event(),AUDIO_EXTENSIONS={'.flac'})
    cache={}
    options={'wanted':{core.text_key('模特')},'tag_cache':cache,
             'settings':{'library_path':str(root),'library_storage':'local'}}
    query=lambda: ns['_library_index'](plugin,**options)
    assert query()[(core.text_key('模特'),core.text_key('李荣浩'))] == str(audio)
    query()
    assert len(calls)==1
    current['artist']='其他歌手'
    audio.write_bytes(b'changed audio')
    assert (core.text_key('模特'),core.text_key('李荣浩')) not in query()
    assert len(calls)==2
    audio.unlink()
    assert query()=={} and cache=={}


def test_live_endpoint_accepts_verified_existing_tags_despite_duplicate_transfer_failure_and_rechecks_deletion():
    from threading import Lock
    from test_core import core
    state,registry,tasks=fixture()
    for item in state['tracks'].values(): item['song']['artists']=['李荣浩']
    paths={'/music/a.flac'}
    needed_calls=[]
    plugin=SimpleNamespace(STATE_KEY='state',SOURCE='qqmusic',_status_lock=Lock(),
        _status_library_files={},_status_tag_cache={},
        get_data=lambda key: state if key=='state' else registry,
        _resolved_settings=lambda:{'library_path':'/music','library_storage':'local'},
        _status_file_exists=lambda path,storage,settings:path in paths,
        _status_transfer_rows=lambda filters:[transfer(success=False,download_hash='older-resource')],
        _library_index=lambda **kwargs:{(core.text_key('歌曲A'),core.text_key('李荣浩')):'/music/a.flac'})
    def read_tasks(registry,needed):
        needed_calls.append(set(needed))
        return {}
    plugin._status_download_tasks=read_tasks
    ns=plugin_methods({'page_downloads'}, {'song_lifecycle':lifecycle.song_lifecycle,'text_key':core.text_key,
        'MediaType':SimpleNamespace(MUSIC='音乐'),'MediaSource':str,'download_cards':lambda *args:[],
        'time':SimpleNamespace(time=lambda:100)})
    before=deepcopy(state)
    result=ns['page_downloads'](plugin)
    assert result['song_states']['a']['status']=='library'
    assert 'a' not in needed_calls[-1]
    assert result['status_counts']['library']==1
    assert '/music/a.flac' not in str(result) and 'library_files' not in result
    assert state==before
    paths.clear()
    result=ns['page_downloads'](plugin)
    assert result['song_states']['a']['status']!='library' and 'a' in needed_calls[-1]
