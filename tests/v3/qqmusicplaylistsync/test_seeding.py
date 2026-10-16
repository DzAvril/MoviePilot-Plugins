import importlib.util
import fcntl
import os
import sys
import time
from copy import deepcopy
from pathlib import Path
from threading import Event, RLock
from types import SimpleNamespace

import pytest

from test_selected_downloads import ROOT, QB, FILES, selected, plugin_methods, song
from test_core import core

spec = importlib.util.spec_from_file_location('app.plugins.qqmusicplaylistsync.seeding', ROOT / 'seeding.py')
seeding = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = seeding
spec.loader.exec_module(seeding)
DAY, NOW = 86400, 100 * 86400


class SeedQB(QB):
    def __init__(self, directory):
        super().__init__()
        self.row.update(state='stalledUP', progress=1, added_on=1000, seeding_time=100,
                        save_path=str(directory),content_path=str(directory/'album'),tags='MP,QQ歌单选曲')
        for row in self.files:
            row.update(progress=1, size=5)
        self.others, self.remove_lies = [], False

    def get_torrents(self, **kwargs):
        rows,error = super().get_torrents(**kwargs)
        return (rows if kwargs.get('ids') else rows+deepcopy(self.others)),error

    def delete_torrents(self, *, delete_file, ids):
        assert delete_file is False and ids == ['a'*40]
        self.calls.append('remove-task-keep-data')
        if not self.remove_lies:
            self.exists=False
        return True


@pytest.fixture
def case(tmp_path):
    download,library=tmp_path/'download',tmp_path/'music'
    root=download/'album'
    root.mkdir(parents=True)
    library.mkdir()
    for name in FILES:
        (root/name).write_bytes(b'audio')
    wanted=[FILES[0],FILES[2]]
    entry=dict(hash='a'*40,downloader='QB',phase='started',source_root=str(root),
               files=wanted,fullpaths=[str(root/name) for name in wanted],matches={'one':FILES[0],'two':FILES[2]})
    rows=[]
    for i,name in enumerate(wanted,1):
        os.link(root/name,library/name)
        rows.append(dict(id=i,download_hash='a'*40,src=str(root/name),dest=str(library/name),
                         dest_storage='local',status=True))
    qb=SeedQB(download)
    saved=[]
    options=dict(normalize=str,settings={'library_path':str(library),'library_storage':'local'},
        days=1,now=NOW,transfers=lambda:list(rows),save=lambda:saved.append(deepcopy(entry)),
        audio_extensions={'.m4a'})
    return entry,qb,options,root,library,rows,saved


def run(case,**overrides):
    entry,qb,options,*_=case
    return seeding.maintain_entry(entry,qb,**{**options,**overrides})


def due(case):
    run(case)
    case[1].row['seeding_time'] += DAY
    case[2]['now'] += DAY


def test_disabled_cleanup_never_reads_transfer_history_or_removes_files(case):
    run(case,days=0,transfers=lambda:pytest.fail('disabled cleanup queried history'))
    entry,qb,_,root,*_=case
    assert entry['download_mode']=='full_album' and entry['files']==[FILES[0],FILES[2]]
    assert entry['download_files']==FILES and entry['cleanup']['state']=='disabled'
    assert all((root/name).is_file() for name in FILES)
    assert qb.exists and 'remove-task-keep-data' not in qb.calls


@pytest.mark.parametrize('paused',[False,True])
def test_old_partial_task_becomes_full_album_without_expanding_import_whitelist(case,paused):
    entry,qb,*_=case
    qb.row.update(state='stoppedDL' if paused else 'queuedUP')
    qb.files[1].update(priority=0,progress=0)
    qb.files[-1].update(priority=0,progress=0)
    run(case,days=0)
    assert all(row['priority']>0 for row in qb.files)
    assert entry['files']==[FILES[0],FILES[2]]
    assert ('resume' in qb.calls) is not paused


def test_selected_completion_is_not_full_completion_and_never_starts_retention(case):
    case[1].files[1]['progress']=0.5
    run(case)
    assert case[0]['cleanup']['state']=='waiting_download'
    assert 'ready_at' not in case[0]['cleanup']


def test_retention_requires_both_elapsed_days_and_actual_seeding_time(case):
    run(case)
    entry,qb,options,root,*_=case
    assert entry['cleanup']['ready_at']==NOW and entry['cleanup']['due_at']==NOW+DAY
    run(case,now=NOW+2*DAY)
    assert qb.exists and (root/FILES[1]).exists()
    qb.row['seeding_time'] += DAY
    run(case,now=NOW+2*DAY)
    assert entry['cleanup']['state']=='done'
    assert not qb.exists and not (root/FILES[1]).exists()


def test_cleanup_unlinks_only_unimported_audio_and_keeps_hardlinks_cover_and_library(case):
    due(case)
    run(case)
    entry,qb,_,root,library,_,_=case
    assert entry['cleanup']['state']=='done' and entry['cleanup']['deleted']==1
    assert not (root/FILES[1]).exists() and (root/'cover.jpg').is_file()
    for name in entry['files']:
        assert (root/name).read_bytes()==(library/name).read_bytes()==b'audio'
        assert (root/name).stat().st_ino==(library/name).stat().st_ino
    calls=list(qb.calls)
    run(case)
    assert qb.calls==calls


@pytest.mark.parametrize('missing',[True,False])
def test_missing_library_or_latest_failed_transfer_defers_and_resets_timer(case,missing):
    due(case)
    entry,qb,_,root,library,rows,_=case
    if missing:
        (library/FILES[0]).unlink()
    else:
        rows.append({**rows[0],'id':99,'status':False})
    run(case)
    assert entry['cleanup']['state']=='waiting_library' and 'ready_at' not in entry['cleanup']
    assert qb.exists and (root/FILES[1]).exists()


def test_new_playlist_song_not_yet_in_import_whitelist_blocks_cleanup(case):
    due(case)
    run(case,pending_selection=True)
    assert case[0]['cleanup']['state']=='waiting_library' and case[1].exists


def test_remote_library_or_absent_task_never_authorizes_file_deletion(case):
    run(case,settings={**case[2]['settings'],'library_storage':'u115'})
    assert case[0]['cleanup']['state']=='waiting_library'
    case[1].exists=False
    case[0]['cleanup']={}
    run(case,now=NOW+10*DAY)
    assert (case[3]/FILES[1]).exists() and not case[0]['cleanup']


@pytest.mark.parametrize('change',['save_path','content_path','tag','unsafe_name','missing_name','known_inventory'])
def test_changed_task_ownership_layout_or_inventory_never_mutates_files(case,change):
    entry,qb,_,root,*_=case
    if change in {'save_path','content_path'}:
        qb.row[change]='/other'
    elif change=='tag':qb.row['tags']='MP'
    elif change=='unsafe_name':qb.files[1]['name']='album/../other.m4a'
    elif change=='missing_name':qb.files.pop(0)
    else:entry['download_files']=FILES[:-1]
    with pytest.raises(selected.SelectionError):run(case)
    assert qb.exists and (root/FILES[1]).exists() and 'pause' not in qb.calls


def test_shared_content_with_another_torrent_prevents_removal(case):
    due(case)
    qb=case[1]
    qb.others=[dict(hash='b'*40,content_path=qb.row['content_path'])]
    with pytest.raises(selected.SelectionError,match='其他下载任务'):run(case)
    assert qb.exists and (case[3]/FILES[1]).exists()


def test_false_success_from_qb_remove_never_allows_unlink(case,monkeypatch):
    due(case)
    case[1].remove_lies=True
    monkeypatch.setattr(seeding.time,'sleep',lambda _:None)
    with pytest.raises(selected.SelectionError,match='尚未确认'):run(case)
    assert (case[3]/FILES[1]).exists() and case[1].exists


def test_restart_after_task_removal_resumes_only_recorded_file_cleanup(case):
    due(case)
    options=case[2]
    def crash():
        if case[0]['cleanup']['state']=='removed':raise RuntimeError('simulated restart')
    with pytest.raises(RuntimeError,match='simulated'):run(case,save=crash)
    assert not case[1].exists and (case[3]/FILES[1]).exists()
    run(case)
    assert case[0]['cleanup']['state']=='done' and not (case[3]/FILES[1]).exists()


def test_stopping_plugin_after_task_removal_keeps_all_cached_audio(case):
    due(case)
    stopped=Event()
    def save():
        if case[0]['cleanup']['state']=='removed':stopped.set()
    with pytest.raises(selected.SelectionError,match='已停止'):run(case,save=save,stopped=stopped.is_set)
    assert not case[1].exists and (case[3]/FILES[1]).exists()


def test_readded_task_or_replaced_file_after_removal_intent_keeps_files(case,monkeypatch):
    due(case)
    case[1].remove_lies=True
    monkeypatch.setattr(seeding.time,'sleep',lambda _:None)
    with pytest.raises(selected.SelectionError):run(case)
    case[1].remove_lies=False
    case[1].row['added_on']+=1
    with pytest.raises(selected.SelectionError,match='重新添加'):run(case)
    case[1].row['added_on']-=1
    path=case[3]/FILES[1]
    path.write_bytes(b'a different file')
    with pytest.raises(selected.SelectionError,match='替换'):run(case)
    assert path.exists() and case[1].exists


def test_symlinked_cache_file_does_not_delete_external_target(case,tmp_path):
    due(case)
    outside=tmp_path/'outside.m4a'
    outside.write_bytes(b'keep')
    path=case[3]/FILES[1]
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(selected.SelectionError,match='链接'):run(case)
    assert outside.read_bytes()==b'keep' and path.is_symlink() and case[1].exists


def test_single_track_torrent_has_no_unimported_audio_to_clean(tmp_path):
    qb=SeedQB(tmp_path)
    qb.files=[dict(index=0,name='single.m4a',priority=1,progress=1)]
    qb.row['content_path']=str(tmp_path/'single.m4a')
    entry=dict(hash='a'*40,phase='started',source_root=str(tmp_path/'single.m4a'),files=['single.m4a'],
               fullpaths=[str(tmp_path/'single.m4a')])
    seeding.maintain_entry(entry,qb,normalize=str,settings={},days=1,now=NOW,
        transfers=lambda:pytest.fail('no extra audio'),save=lambda:None,audio_extensions={'.m4a'})
    assert entry['cleanup']['state']=='not_needed' and qb.exists


@pytest.mark.parametrize('value,expected',[(None,0),('',0),('invalid',0),(-1,0),('7',7),(3651,3650),(float('inf'),0),(1.5,0),(True,0)])
def test_retention_days_are_bounded_and_invalid_values_disable_cleanup(value,expected):
    assert seeding.retention_days(value)==expected


def test_real_plugin_maintenance_preserves_registry_and_defers_new_playlist_song(case,tmp_path):
    entry,qb,options,_,_,transfers,_=case
    state={'tracks':{'one':dict(song=song(),present=True),
                     'two':dict(song=song('two','山川'),present=True)}}
    data={'selected_downloads':{'a'*40:entry},'state':state}
    plugin=SimpleNamespace(_stop=Event(),_selection_lock=RLock(),_state=state,STATE_KEY='state',
        _config={'dry_run':False,'unselected_cleanup_days':1},AUDIO_EXTENSIONS={'.m4a'},
        get_state=lambda:True,get_data_path=lambda:tmp_path/'plugin-data',get_data=lambda key:deepcopy(data.get(key)),
        save_data=lambda key,value:data.update({key:deepcopy(value)}),
        _resolved_settings=lambda:{**options['settings'],'transfer_type':'link'},
        _qb_service=lambda _:SimpleNamespace(instance=qb,module=SimpleNamespace(normalize_path=lambda p,n:p.as_posix())),
        _status_transfer_rows=lambda filters:transfers)
    method=plugin_methods({'maintain_downloads'},dict(fcntl=fcntl,deepcopy=deepcopy,time=time,Path=Path,
        maintain_entry=seeding.maintain_entry,SelectionError=selected.SelectionError,
        track_file_selection=core.track_file_selection,MediaType=SimpleNamespace(MUSIC='music')))['maintain_downloads']
    assert method(plugin)==dict(success=True,upgraded=1,cleaned=0,deferred=0)
    saved=data['selected_downloads']['a'*40]
    assert saved['files']==entry['files'] and saved['cleanup']['state']=='retaining'
    # Playlist snapshot may add a song before native search has expanded the import list.
    state['tracks']['three']=dict(song=song('three','我们好好的'),present=True)
    data['state']=deepcopy(state)
    method(plugin)
    assert data['selected_downloads']['a'*40]['cleanup']['state']=='waiting_library'
    plugin._config['dry_run']=True
    calls=list(qb.calls)
    assert not method(plugin)['success'] and qb.calls==calls
