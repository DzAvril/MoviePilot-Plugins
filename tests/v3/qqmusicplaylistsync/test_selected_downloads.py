import ast
import importlib.util
import sys
import time
from copy import deepcopy
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event, Lock, RLock
from types import MethodType, ModuleType, SimpleNamespace

import pytest

from test_core import core

ROOT = Path(__file__).parents[3] / 'plugins.v3/qqmusicplaylistsync'
spec = importlib.util.spec_from_file_location('app.plugins.qqmusicplaylistsync.selected', ROOT / 'selected.py')
selected = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = selected
spec.loader.exec_module(selected)


def song(mid='one', title='纵横四海', album='纵横四海', artist='李荣浩'):
    return dict(mid=mid, title=title, album=album, artists=[artist], album_mid='album001')


def test_album_selection_takes_all_wanted_tracks_and_excludes_unwanted_and_other_versions():
    plan = core.track_file_selection(song(), ['01. 纵横四海.m4a', '02. 我们好好的.m4a', '03. 山川.m4a',
         '04. 山川 (Live).m4a', 'cover.jpg'], [song('two', '山川'), song('three', '我们好好的', artist='别人')])
    assert plan['allowed'] and plan['audio_count'] == 4
    assert plan['files'] == ['01. 纵横四海.m4a', '03. 山川.m4a']
    assert plan['matches'] == {'one': '01. 纵横四海.m4a', 'two': '03. 山川.m4a'}


@pytest.mark.parametrize('files', [['01.flac'], ['山川.flac'], ['纵横四海.flac', '纵横四海.mp3'],
                                 ['纵横四海.flac', 'album.cue'], ['../纵横四海.flac'], ['/纵横四海.flac']])
def test_no_number_guessing_ambiguous_versions_cue_or_unsafe_path(files):
    assert not core.track_file_selection(song(), files)['allowed']


def test_featured_artist_credit_is_allowed_only_when_the_credited_artist_is_in_the_song():
    target = song(title='对等关系')
    target['artists'] = ['李荣浩', '张惠妹']
    files = ['05. 对等关系 (feat. 张惠妹).m4a', '07. 习惯晚睡.m4a']
    assert core.track_file_selection(target,files)['files'] == [files[0]]
    target['artists'] = ['李荣浩']
    assert not core.track_file_selection(target,files)['allowed']
    assert not core.track_file_selection(song(title='对等关系'),['对等关系 (Live).m4a'])['allowed']


class QB:
    def __init__(self, existing=True):
        self.calls = []
        self.exists = existing
        self.row = dict(hash='a'*40, state='stoppedDL', save_path='/sata/Download/Music',
                        content_path='/sata/Download/Music/album',tags='MP,已整理')
        # qB IDs are deliberately unrelated to torrent ordering.
        self.files = [dict(index=12, name='album/01. 纵横四海.m4a', priority=1, progress=0),
                      dict(index=4, name='album/02. 我们好好的.m4a', priority=1, progress=0),
                      dict(index=8, name='album/03. 山川.m4a', priority=1, progress=0),
                      dict(index=21, name='album/cover.jpg', priority=1, progress=0)]
        self.fail_set = False
        self.lie_readback = False

    def get_torrents(self, **kwargs):
        return ([deepcopy(self.row)] if self.exists else []), None

    def stop_torrents(self, **kwargs):
        self.calls.append('pause')
        self.row['state'] = 'stoppedDL'
        return True

    def get_files(self, *args, **kwargs):
        self.calls.append('read-files')
        rows = deepcopy(self.files)
        if self.lie_readback:
            for row in rows:
                row['priority'] = 1
        return rows

    def set_files(self, **kwargs):
        self.calls.append(('select', kwargs['priority'], set(kwargs['file_ids'])))
        assert self.row['state'] == 'stoppedDL'
        if self.fail_set:
            return False
        for row in self.files:
            if row['index'] in kwargs['file_ids']:
                row['priority'] = kwargs['priority']
        return True

    def start_torrents(self, **kwargs):
        self.calls.append('resume')
        self.row['state'] = 'downloading'
        return True

    def add_torrent(self, **kwargs):
        self.calls.append(('add', kwargs['is_paused']))
        assert kwargs['is_paused'] and kwargs['content_layout'] == 'Original'
        self.exists = True
        return True, ['a'*40]

    def remove_torrents_tag(self, **kwargs):
        self.calls.append('clear-organized-tag')
        self.row['tags'] = ','.join(t for t in self.row['tags'].split(',') if t not in kwargs['tag'])

    def set_torrents_tag(self, **kwargs):
        self.calls.append('set-tags')
        self.row['tags'] = ','.join(set(self.row['tags'].split(',')).union(kwargs['tags']))


FILES = ['01. 纵横四海.m4a', '02. 我们好好的.m4a', '03. 山川.m4a', 'cover.jpg']


def test_qb_file_ids_are_mapped_by_name_and_non_audio_is_unchecked():
    qb = QB()
    selected.ensure_paused(qb, 'a'*40)
    result = selected.choose_files(qb, 'a'*40, 'album', FILES, {FILES[0], FILES[2]})
    assert result == [FILES[0], FILES[2]]
    assert {r['index'] for r in qb.files if r['priority']} == {12, 8}
    assert qb.calls[-1] == 'read-files' and 'resume' not in qb.calls


@pytest.mark.parametrize('failure', ['fail_set', 'lie_readback', 'missing_file'])
def test_partial_or_failed_file_selection_never_starts_the_task(failure):
    qb = QB()
    if failure == 'missing_file':
        qb.files.pop()
    else:
        setattr(qb, failure, True)
    with pytest.raises(selected.SelectionError):
        selected.choose_files(qb, 'a'*40, 'album', FILES, {FILES[0]})
    assert 'resume' not in qb.calls and qb.row['state'] == 'stoppedDL'


def plugin_methods(names, namespace):
    namespace.update({key: getattr(core, key) for key in ('MUSIC_SOURCES', 'media_key', 'track_key')})
    nodes = [n for n in ast.parse((ROOT / '__init__.py').read_text()).body if isinstance(n, ast.ClassDef)][0].body
    methods = [n for n in nodes if isinstance(n, ast.FunctionDef) and n.name in names]
    for node in methods:
        node.decorator_list = []
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(ROOT / '__init__.py'), 'exec'), namespace)
    return namespace


def install_fake_modules(monkeypatch):
    torrent = ModuleType('app.application.torrent.download')
    torrent.TorrentHelper = SimpleNamespace(get_torrent_hash=lambda _: 'a'*40)
    config = ModuleType('app.sdk.config')
    config.settings = SimpleNamespace(TORRENT_TAG='MP')
    monkeypatch.setitem(sys.modules, torrent.__name__, torrent)
    monkeypatch.setitem(sys.modules, config.__name__, config)


@dataclass(frozen=True)
class Prepared:
    file_list: list
    torrent_content: bytes = b'torrent'
    download_dir: Path = Path('/sata/Download/Music')
    folder_name: str = 'album'
    site_downloader: str = 'QB'
    torrent: object = None
    media: object = None


def submission(monkeypatch, *, existing=False, failure=None, registry=None, owned=True, single=False,
               download_dir='/sata/Download/Music', music_source='qqmusic', transfer_type='link', service_factory=None):
    install_fake_modules(monkeypatch)
    qb = QB(existing)
    qb.row.update(save_path=download_dir,content_path=download_dir+'/album')
    if single:
        qb.files = [dict(index=0,name=FILES[0],priority=1,progress=0)]
        qb.row['content_path'] = download_dir+'/' + FILES[0]
    if failure:
        setattr(qb, failure, True)
    data = {'selected_downloads': deepcopy(registry or {})}
    ns = plugin_methods({'_submit_selected', '_file_plan', 'guard_selected_transfer', '_record_download_error'},
                        dict(Path=Path, time=time, replace=replace, SelectionError=selected.SelectionError,
                             choose_files=selected.choose_files, task_info=selected.task_info,
                             ensure_paused=selected.ensure_paused, track_file_selection=core.track_file_selection,
                             logger=SimpleNamespace(info=lambda *_: None, warning=lambda *_: None)))
    plugin = SimpleNamespace(SOURCE='qqmusic', plugin_name='QQ音乐歌单同步', _stop=Event(), _adapter_error='',
        _selection_lock=RLock(), _guard_lock=Lock(), _config={'save_path':'/sata/Download/Music','downloader':'QB'},
        _state={'tracks':{core.media_key(music_source,'one'):dict(song=song(core.media_key(music_source,'one')), present=True),
                          core.media_key(music_source,'two'):dict(song=song(core.media_key(music_source,'two'),'山川'),present=True)}},
        get_data=lambda key:deepcopy(data.get(key)), save_data=lambda k,v:data.update({k:deepcopy(v)}),
        _download_options=lambda:dict(downloader='QB',save_path=None),_default_downloader=lambda:'QB',
        _resolved_settings=lambda:dict(transfer_type=transfer_type),
        _download_service=lambda _: service_factory(qb) if service_factory else SimpleNamespace(instance=qb, module=SimpleNamespace(normalize_path=lambda p,n:str(p))))
    for name in ('_file_plan','guard_selected_transfer','_record_download_error'):
        setattr(plugin,name,MethodType(ns[name],plugin))
    history = SimpleNamespace(media_source=music_source if owned else 'musicbrainz', music_type='recording',media_id='one')
    captured = []
    def settle(**kwargs):
        qb.calls.append('native-history')
        captured.append(kwargs['prepared'])
        assert qb.row['state'] == 'stoppedDL'
    owner = SimpleNamespace(_subscription_download_cancelled=lambda _:False,
             download_history_repository=SimpleNamespace(get_by_hash=lambda _:history),_settle_accepted_download=settle)
    prepared = Prepared([FILES[0]] if single else FILES, folder_name='' if single else 'album',download_dir=Path(download_dir),
                        torrent=SimpleNamespace(title='李荣浩 - 纵横四海', site_cookie=None),
                        media=SimpleNamespace(category='音乐'))
    result = ns['_submit_selected'](plugin,owner,prepared=prepared,
             context=SimpleNamespace(media_info=SimpleNamespace(media_id='one',media_source=music_source,title='纵横四海')),
             episodes=None,channel=None,source='subscribe',downloader='QB',userid=None,username=None,
             label=None,custom_words=None,governance=None)
    return qb, data, captured, result, plugin


def test_new_task_is_added_paused_selected_read_back_recorded_then_resumed(monkeypatch):
    qb,data,hist,result,_ = submission(monkeypatch)
    assert result == ('a'*40, None)
    assert qb.calls[0] == ('add',True)
    assert qb.calls.index('native-history') < qb.calls.index('resume')
    assert hist[0].file_list == [FILES[0], FILES[2]]
    assert {row['index'] for row in qb.files if row['priority']} == {12,4,8,21}
    assert data['selected_downloads']['a'*40]['download_files'] == FILES
    assert data['selected_downloads']['a'*40]['files'] == [FILES[0],FILES[2]]
    assert data['selected_downloads']['a'*40]['phase'] == 'started'
    assert '已整理' not in qb.row['tags'] and 'QQ歌单选曲' in qb.row['tags']


def test_failed_qb_selection_has_no_native_success_or_resume(monkeypatch):
    qb,data,hist,result,_ = submission(monkeypatch,failure='fail_set')
    assert result[0] is None and not hist and 'resume' not in qb.calls
    assert qb.row['state'] == 'stoppedDL' and data['selected_downloads']['a'*40]['phase'] == 'paused'


def test_existing_qq_task_is_reused_and_existing_unrelated_task_is_untouched(monkeypatch):
    qb,_,hist,result,_ = submission(monkeypatch,existing=True)
    assert result[0] == 'a'*40 and hist and not any(isinstance(c,tuple) and c[0]=='add' for c in qb.calls)
    qb,_,hist,result,_ = submission(monkeypatch,existing=True,owned=False)
    assert result[0] is None and not hist and not qb.calls


def test_later_song_unions_import_whitelist_while_entire_album_remains_selected(monkeypatch):
    prior={'a'*40:dict(hash='a'*40,downloader='QB',files=[FILES[1]],matches={},source_root='/sata/Download/Music/album')}
    qb,data,hist,result,_=submission(monkeypatch,existing=True,registry=prior)
    assert result[0] == 'a'*40 and set(hist[0].file_list) == set(FILES[:3])
    assert all(file['priority'] == 1 for file in qb.files)


@pytest.mark.parametrize('transfer_type', ['move', 'softlink', None])
def test_full_album_submission_refuses_source_destructive_or_unverified_transfer_modes(monkeypatch,transfer_type):
    qb,_,hist,result,_=submission(monkeypatch,transfer_type=transfer_type)
    assert result[0] is None and not hist and not qb.calls


def test_full_album_transfer_guard_allows_link_and_copy_but_blocks_move(monkeypatch):
    _,_,_,_,plugin=submission(monkeypatch)
    for mode,blocked in [('link',False),('copy',False),('move',True),('softlink',True)]:
        event=SimpleNamespace(event_data=SimpleNamespace(cancel=False,transfer_type=mode,
            fileitem=SimpleNamespace(storage='local',path='/sata/Download/Music/album/'+FILES[0])))
        plugin.guard_selected_transfer(event)
        assert event.event_data.cancel == blocked


def test_unwanted_existing_audio_cannot_be_organized_but_other_paths_can(monkeypatch):
    _,_,_,_,plugin=submission(monkeypatch)
    for path,blocked in [('/sata/Download/Music/album/'+FILES[1],True),
                         ('/sata/Download/Music/album/'+FILES[0],False),
                         ('/sata/Download/Music/other/audio.flac',False)]:
        event=SimpleNamespace(event_data=SimpleNamespace(cancel=False,fileitem=SimpleNamespace(storage='local',path=path)))
        plugin.guard_selected_transfer(event)
        assert event.event_data.cancel == blocked


def test_single_file_selection_does_not_claim_the_entire_shared_music_directory(monkeypatch):
    _,data,_,result,plugin=submission(monkeypatch,single=True)
    assert result[0] == 'a'*40
    assert data['selected_downloads']['a'*40]['source_root'] == '/sata/Download/Music/' + FILES[0]
    event=SimpleNamespace(event_data=SimpleNamespace(cancel=False,
          fileitem=SimpleNamespace(storage='local',path='/sata/Download/Music/other-song.flac')))
    plugin.guard_selected_transfer(event)
    assert not event.event_data.cancel


def test_selection_uses_the_native_resolved_directory_instead_of_a_hard_coded_root(monkeypatch):
    _,data,_,result,_=submission(monkeypatch,download_dir='/sata/Download/NewMusic')
    assert result[0] == 'a'*40
    entry=data['selected_downloads']['a'*40]
    assert entry['source_root']=='/sata/Download/NewMusic/album'
    assert all(path.startswith('/sata/Download/NewMusic/album/') for path in entry['fullpaths'])


def test_runtime_adapter_promotes_only_verified_album_files_and_preserves_other_media(monkeypatch):
    @dataclass(frozen=True)
    class MusicMatch:
        status: str
        reason: str

    @dataclass(frozen=True)
    class Match:
        torrent: object
        music_match: object

    class MusicOwner:
        @staticmethod
        def _music_keywords(media,keyword,include_candidates):
            return [media.title, 'Artist '+media.title] + ([media.album] if include_candidates else [])

    class DownloadOwner:
        def _submit_prepared_download(self,*,prepared,context,governance,**kwargs):
            return 'original',None

    def match_torrents(*,mediainfo,include_candidates,**kwargs):
        return [Match('valid',MusicMatch('album','related_album')),
                Match('missing',MusicMatch('album','related_album')),
                Match('unknown-artist',MusicMatch('candidate','artist_unverified')),
                Match('single',MusicMatch('exact','matched'))] if include_candidates else []

    result=ModuleType('app.chain.search.result')
    result._match_torrents=match_torrents
    search=ModuleType('app.chain.search')
    search.result=result
    modules={'app.chain.search':search,'app.chain.search.result':result,
             'app.chain.search.music':SimpleNamespace(SearchMusicOwner=MusicOwner),
             'app.chain.download.submission':SimpleNamespace(DownloadSubmissionOwner=DownloadOwner),
             'app.domain.music':SimpleNamespace(MusicMatch=MusicMatch)}
    for name,module in modules.items():
        monkeypatch.setitem(sys.modules,name,module)
    plugin=SimpleNamespace(_stop=Event(),_owns_media=lambda m:bool(m and m.source=='qqmusic'),
        _inspect_plan=lambda media,torrent:dict(allowed=torrent=='valid'),
        _submit_selected=lambda owner,**kwargs:('selected',None))
    media=SimpleNamespace(source='qqmusic',title='Song',album='Album',artists=['Artist'],album_artist='Artist')
    adapter=selected.RuntimeAdapter(plugin)
    adapter.install()
    assert MusicOwner._music_keywords(media,None,False)[:2] == ['Song','Artist Album']
    matches=result._match_torrents(mediainfo=media,include_candidates=False)
    assert [m.torrent for m in matches] == ['valid','single']
    assert matches[0].music_match.reason == 'qqmusic_split_track_verified'
    assert DownloadOwner()._submit_prepared_download(prepared=None,context=SimpleNamespace(media_info=media),governance=None)[0]=='selected'
    other=SimpleNamespace(**{**vars(media),'source':'musicbrainz'})
    assert result._match_torrents(mediainfo=other,include_candidates=False)==[]
    assert DownloadOwner()._submit_prepared_download(prepared=None,context=SimpleNamespace(media_info=other),governance=None)[0]=='original'
    # 热重载不叠加包装；旧实例停止不能卸下新实例。
    newer=selected.RuntimeAdapter(plugin)
    newer.install()
    adapter.uninstall()
    assert result._match_torrents is not match_torrents
    newer.uninstall()
    assert result._match_torrents is match_torrents
