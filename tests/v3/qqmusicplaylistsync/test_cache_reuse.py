import importlib.util
import os
import shutil
import sys
import time
from copy import deepcopy
from pathlib import Path
from threading import Event, RLock
from types import MethodType, SimpleNamespace

import pytest

from test_core import core
from test_selected_downloads import ROOT, FILES, plugin_methods, song
from test_seeding import seeding, SeedQB
from test_lifecycle import lifecycle

spec=importlib.util.spec_from_file_location('app.plugins.qqmusicplaylistsync.cache',ROOT/'cache.py')
cache=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=cache
spec.loader.exec_module(cache)


@pytest.fixture
def setup(tmp_path,monkeypatch):
    download=tmp_path/'download'
    root=download/'album'
    library=tmp_path/'library'
    root.mkdir(parents=True);library.mkdir()
    for name in FILES:(root/name).write_bytes(b'audio')
    (library/FILES[0]).write_bytes(b'audio')
    state={'tracks':{mid:dict(song=song(mid,title),present=True,status='pending',first_seen=1,attempts=0)
        for mid,title in [('one','纵横四海'),('two','山川')]}}
    state['tracks']['one'].update(status='library',library_path=str(library/FILES[0]))
    state['tracks']['two']['subscription_id']=22
    entry=dict(hash='a'*40,downloader='QB',phase='started',download_mode='full_album',
        files=[FILES[0]],fullpaths=[str(root/FILES[0])],source_root=str(root),download_files=list(FILES),
        matches={'one':FILES[0]},cleanup={'state':'retaining','ready_at':10})
    data={'selected_downloads':{'a'*40:entry},'state':state}
    rows=[dict(id=1,download_hash='a'*40,src=str(root/FILES[0]),dest=str(library/FILES[0]),status=True,dest_storage='local')]
    qb=SeedQB(download)
    directory=SimpleNamespace(download_path=str(download),library_path=str(library),library_storage='local',transfer_type='link')
    current={'directory':directory,'success':True,'record':True}
    calls,finished=[],[]
    native=SimpleNamespace(best_version=0,music_type='recording',media_source='qqmusic',media_id='two')
    current['native']=native
    chain=SimpleNamespace(subscription_repository=SimpleNamespace(get=lambda sid:native),
        finish_subscribe_or_not=lambda **kwargs:finished.append(kwargs))
    def transfer(**kwargs):
        calls.append(kwargs)
        path=Path(kwargs['fileitem'].path)
        assert str(path) in data['selected_downloads']['a'*40]['fullpaths']
        assert data['state']['tracks']['two']['cache_pending']
        assert kwargs['background'] is False and kwargs['manual'] is True and kwargs['sync_extra_files'] is False
        assert kwargs['target_directory'] is current['directory']
        if not current['success']:return False,'failed'
        dest=library/path.name
        if kwargs['transfer_type']=='link':os.link(path,dest)
        else:shutil.copy2(path,dest)
        if current['record']:rows.append(dict(id=2,download_hash='a'*40,src=str(path),dest=str(dest),status=True,dest_storage='local'))
        return True,''
    module=SimpleNamespace(DirectoryHelper=lambda:SimpleNamespace(get_download_dir_by_task_path=lambda **kwargs:current['directory']))
    monkeypatch.setitem(sys.modules,'app.application.directory',module)
    names={'_cache_directory','_reuse_cached','_finish_cache_subscription','guard_single_track','_owns_media'}
    ns=plugin_methods(names,dict(Path=Path,time=time,SelectionError=seeding.SelectionError,cache_candidates=cache.cache_candidates,
        source_path=cache.source_path,cached_destination=cache.cached_destination,completed_cached_file=cache.completed_cached_file,
        cache_source_exists=cache.cache_source_exists,allow_cached_track=cache.allow_cached_track,text_key=core.text_key,
        task_info=seeding.task_info,TransferChain=lambda:SimpleNamespace(do_transfer=transfer),
        SubscribeChain=lambda:chain,MetaMusic=lambda **kwargs:SimpleNamespace(**kwargs),
        FileItem=lambda **kwargs:SimpleNamespace(**kwargs),MediaType=SimpleNamespace(MUSIC='音乐')))
    plugin=SimpleNamespace(SOURCE='qqmusic',plugin_name='音乐歌单同步',_state=state,_stop=Event(),_selection_lock=RLock(),
        get_data=lambda key:deepcopy(data.get(key)),save_data=lambda k,v:data.update({k:deepcopy(v)}),
        _save=lambda value:data.update(state=deepcopy(value)),
        recognize_media=lambda **kwargs:SimpleNamespace(title='山川',artists=['李荣浩'],**kwargs),
        _status_transfer_rows=lambda filters:list(rows),
        _qb_service=lambda _:SimpleNamespace(instance=qb,module=SimpleNamespace(normalize_path=lambda path,name:path.as_posix())),
        _resolved_settings=lambda:{'library_path':str(library),'library_storage':'local'},
        _status_file_exists=lambda path,*args:bool(path) and Path(path).is_file())
    for name in names:setattr(plugin,name,MethodType(ns[name],plugin))
    return plugin,data,qb,current,calls,finished,root,library,rows


@pytest.mark.parametrize('mode',['link','copy'])
def test_complete_cached_track_uses_native_directory_mode_and_never_downloads(setup,mode):
    plugin,data,qb,current,calls,finished,root,library,_=setup
    current['directory'].transfer_type=mode
    source=root/FILES[2];before=source.read_bytes();library_index={}
    assert plugin._reuse_cached(library_index,{})==1
    dest=library/FILES[2]
    assert source.read_bytes()==dest.read_bytes()==before
    assert ((source.stat().st_ino==dest.stat().st_ino) is (mode=='link'))
    assert calls[0]['transfer_type']==mode and len(calls)==1
    assert finished[0]['force'] is True
    assert data['state']['tracks']['two']['status']=='library'
    assert not data['state']['tracks']['two']['cache_pending']
    saved=data['selected_downloads']['a'*40]
    assert saved['files']==[FILES[0],FILES[2]] and saved['download_files']==FILES
    assert saved['cleanup']=={} and saved['matches']['two']==FILES[2]
    assert all(not isinstance(call,tuple) for call in qb.calls) and 'pause' not in qb.calls and 'resume' not in qb.calls
    assert plugin._reuse_cached({}, {})==0 and len(calls)==1
    assert core.process_pending(plugin._state,now=10,limit=0,existing={},in_library=lambda _:None,
        subscribe=lambda _:pytest.fail('cached song downloaded again'),save=lambda _:None)==0


@pytest.mark.parametrize('change',['progress','size','missing','checking'])
def test_incomplete_changed_or_missing_cache_stays_available_for_native_subscription(setup,change):
    plugin,data,qb,current,calls,finished,root,library,_=setup
    if change=='progress':qb.files[2]['progress']=0.5
    elif change=='size':qb.files[2]['size']=999
    elif change=='missing':(root/FILES[2]).unlink()
    else:qb.row['state']='checkingDL'
    assert plugin._reuse_cached({}, {})==0 and not calls
    assert not plugin._state['tracks']['two'].get('cache_pending')
    assert not (library/FILES[2]).exists() and not finished
    assert data['selected_downloads']['a'*40]['files']==[FILES[0]]


@pytest.mark.parametrize('mode',['move','softlink',None])
def test_source_destructive_or_unknown_modes_never_trigger_cache_transfer(setup,mode):
    plugin,_,_,current,calls,_,root,library,_=setup
    current['directory'].transfer_type=mode
    assert plugin._reuse_cached({}, {})==0 and not calls
    assert (root/FILES[2]).exists() and not (library/FILES[2]).exists()


def test_transfer_failure_blocks_duplicate_download_and_retries_cache_next_sync(setup):
    plugin,data,_,current,calls,finished,root,library,_=setup
    current['success']=False
    assert plugin._reuse_cached({}, {})==0
    item=plugin._state['tracks']['two']
    assert item['cache_pending'] and item['cache_import_error'] and not finished
    assert core.process_pending(plugin._state,now=10,limit=0,existing={},in_library=lambda _:None,
        subscribe=lambda _:pytest.fail('failed cache transfer caused another download'),save=lambda _:None)==0
    media=SimpleNamespace(media_source='qqmusic',media_id='two',music_type='recording')
    event=SimpleNamespace(event_data=SimpleNamespace(context=SimpleNamespace(media_info=media),cancel=False))
    plugin.guard_single_track(event)
    assert event.event_data.cancel and '缓存' in event.event_data.reason
    result=lifecycle.song_lifecycle(plugin._state,data['selected_downloads'],
        {'a'*40:{'success':True,'state':'stalledUP','file_priorities':setup[2].files}},[],file_exists=lambda *args:False)
    assert result['states']['two']['status']=='transfer_failed'
    current['success']=True
    assert plugin._reuse_cached({}, {})==1
    assert (root/FILES[2]).exists() and (library/FILES[2]).exists() and len(calls)==2


def test_native_acceptance_without_successful_record_is_not_reported_as_imported(setup):
    plugin,_,_,current,_,finished,_,_,_=setup
    current['record']=False
    assert plugin._reuse_cached({}, {})==0
    assert plugin._state['tracks']['two']['cache_pending'] and not finished
    assert plugin._state['tracks']['two']['status']=='pending'


def test_removing_new_song_from_playlist_does_not_import_cached_track(setup):
    plugin,_,_,_,calls,_,_,library,_=setup
    plugin._state['tracks']['two']['present']=False
    assert plugin._reuse_cached({}, {})==0 and not calls and not (library/FILES[2]).exists()


def test_foreign_subscription_identity_is_not_forced_complete(setup):
    plugin,_,_,_,_,finished,_,_,_=setup
    media=SimpleNamespace(media_source='netease',media_id='other',title='wrong',artists=['other'])
    plugin._finish_cache_subscription(plugin._state['tracks']['two'],media,{})
    assert not finished


def test_wash_subscription_keeps_its_native_completion_rules(setup):
    plugin,_,_,current,_,finished,_,_,_=setup
    current['native'].best_version=1
    media=SimpleNamespace(media_source='qqmusic',media_id='two',title='山川',artists=['李荣浩'])
    plugin._finish_cache_subscription(plugin._state['tracks']['two'],media,{})
    assert not finished


def test_source_and_library_overlap_never_triggers_transfer(setup):
    plugin,_,_,current,calls,_,root,_,_=setup
    current['directory'].library_path=str(root)
    assert plugin._reuse_cached({}, {})==0 and not calls


def test_cache_directory_reads_changed_mp_mode_each_time(setup):
    plugin,_,_,current,_,_,root,_,_=setup
    assert plugin._cache_directory(None,root/FILES[2]).transfer_type=='link'
    current['directory']=SimpleNamespace(**{**vars(current['directory']),'transfer_type':'copy'})
    assert plugin._cache_directory(None,root/FILES[2]).transfer_type=='copy'
