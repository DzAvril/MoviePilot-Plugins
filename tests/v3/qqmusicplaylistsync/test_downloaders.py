import importlib.util
import sys
import time
from datetime import datetime, timezone
from threading import Lock
from types import MethodType, SimpleNamespace
from typing import NamedTuple

import pytest

from test_selected_downloads import ROOT, FILES, QB, core, plugin_methods, selected, submission
from test_lifecycle import lifecycle

spec=importlib.util.spec_from_file_location('app.plugins.qqmusicplaylistsync.downloaders',ROOT/'downloaders.py')
downloaders=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=downloaders
spec.loader.exec_module(downloaders)


class File(NamedTuple):
    name:str
    size:int
    completed:int
    priority:int
    selected:bool
    id:int


class TR:
    def __init__(self,qb):
        self.qb=qb
        self.unavailable=False
        self.seconds=123
        self.rpc_calls=[]
        def change(**kwargs):
            self.rpc_calls.append(kwargs)
            self.qb.row['tags']=','.join(kwargs['labels'])
        def get(**kwargs):
            self.rpc_calls.append(kwargs)
            return [SimpleNamespace(hashString='a'*40,seconds_seeding=self.seconds)]
        self.trc=SimpleNamespace(change_torrent=change,get_torrents=get)

    def get_torrents(self,ids=None):
        rows,error=self.qb.get_torrents(ids=ids)
        return [SimpleNamespace(hashString=r['hash'],status={'stoppedDL':'stopped','stalledUP':'seeding',
            'queuedDL':'download_pending','queuedUP':'seed_pending'}.get(r['state'],r['state']),
            percent_done=r.get('progress',0),download_dir=r['save_path'],name='album',labels=r['tags'].split(','),
            added_date=datetime.fromtimestamp(1000,timezone.utc),error=0) for r in rows],self.unavailable

    def get_files(self,tid):
        return [File(r['name'],r.get('size',5),int(r.get('size',5)*r['progress']),0,bool(r['priority']),r['index'])
                for r in self.qb.get_files(tid)]

    def set_files(self,tid,file_ids):
        return self.qb.set_files(torrent_hash=tid,file_ids=file_ids,priority=1)

    def set_unwanted_files(self,tid,file_ids):
        return self.qb.set_files(torrent_hash=tid,file_ids=file_ids,priority=0)

    def add_torrent(self,*,content,download_dir,is_paused,labels,cookie):
        return self.qb.add_torrent(content=content,download_dir=download_dir,is_paused=is_paused,tag=labels,
                                  cookie=cookie,content_layout='Original')

    def set_torrent_tag(self,ids,tags):
        self.qb.row['tags']=','.join(tags)
        return True

    def stop_torrents(self,ids):return self.qb.stop_torrents(ids=ids)
    def start_torrents(self,ids):return self.qb.start_torrents(ids=ids)


def service(qb):
    return SimpleNamespace(name='TR',type='transmission',instance=downloaders.TransmissionAdapter(TR(qb)),
        module=SimpleNamespace(normalize_path=lambda p,n:str(p)))


def test_qb_service_is_returned_unchanged():
    qb=SimpleNamespace(type='qbittorrent')
    assert downloaders.supported_service(qb,'QB') is qb


@pytest.mark.parametrize('kind',[None,'aria2'])
def test_missing_or_unsupported_client_reports_clear_configuration_error(kind):
    value=SimpleNamespace(type=kind) if kind else None
    with pytest.raises(selected.SelectionError,match='下载器'):
        downloaders.supported_service(value,'music')


def test_tr_normal_file_priority_zero_still_means_wanted():
    qb=QB();adapter=service(qb).instance
    rows=adapter.get_files('a'*40)
    assert all(r['priority']==1 for r in rows)
    adapter.set_files('a'*40,[12],0)
    assert adapter.get_files('a'*40)[0]['priority']==0
    adapter.set_files('a'*40,[12],1)
    assert adapter.get_files('a'*40)[0]['priority']==1


@pytest.mark.parametrize('status,expected',[('stoppedDL','pausedDL'),('queuedDL','queuedDL'),
    ('queuedUP','queuedUP'),('checking','checkingDL'),('check_pending','checkingDL'),
    ('downloading','downloading'),('stalledUP','stalledUP'),('weird','unknown')])
def test_tr_task_contract_normalizes_paths_tags_and_states(status,expected):
    qb=QB();qb.row.update(state=status,progress=0.5)
    rows,error=service(qb).instance.get_torrents(ids=['a'*40])
    assert not error and rows[0]['state']==expected
    assert rows[0]['save_path']==qb.row['save_path'] and rows[0]['content_path']==qb.row['content_path']
    assert rows[0]['hash']=='a'*40 and rows[0]['added_on']==1000


def test_tr_labels_preserve_unrelated_labels_and_allow_clear():
    qb=QB();qb.row['tags']='site,user,已整理'
    adapter=service(qb).instance
    adapter.remove_torrents_tag(ids=['a'*40],tag=['已整理'])
    adapter.set_torrents_tag(ids=['a'*40],tags=['QQ歌单选曲'])
    assert set(qb.row['tags'].split(','))=={'site','user','QQ歌单选曲'}
    adapter.remove_torrents_tag(ids=['a'*40],tag=['site','user','QQ歌单选曲'])
    assert qb.row['tags']=='' and adapter.client.rpc_calls[-1]['labels']==[]


def test_tr_label_read_failure_never_overwrites_labels():
    adapter=service(QB()).instance;adapter.client.unavailable=True
    with pytest.raises(selected.SelectionError,match='标签无法核验'):
        adapter.set_torrents_tag(ids=['a'*40],tags=['new'])
    assert not adapter.client.rpc_calls


def test_tr_submission_downloads_full_album_but_native_history_only_has_playlist_tracks(monkeypatch):
    qb,data,hist,result,plugin=submission(monkeypatch,service_factory=service,music_source='netease')
    assert result==('a'*40,None) and qb.calls[-1]=='resume'
    assert hist[0].file_list==[FILES[0],FILES[2]]
    assert all(row['priority']>0 for row in qb.files)
    assert data['selected_downloads']['a'*40]['download_files']==FILES
    assert not data['download_errors']
    for file,blocked in [(FILES[0],False),(FILES[1],True)]:
        event=SimpleNamespace(event_data=SimpleNamespace(cancel=False,transfer_type='link',
            fileitem=SimpleNamespace(storage='local',path='/sata/Download/Music/album/'+file)))
        plugin.guard_selected_transfer(event)
        assert event.event_data.cancel==blocked


def test_tr_failed_selection_stays_paused_and_persists_error_without_native_success(monkeypatch):
    qb,data,hist,result,_=submission(monkeypatch,service_factory=service,failure='fail_set',music_source='netease')
    assert result[0] is None and not hist and 'resume' not in qb.calls
    assert data['selected_downloads']['a'*40]['phase']=='paused'
    assert data['download_errors']['netease:one']['reason']


def test_switching_downloader_never_replaces_an_existing_qb_registry(monkeypatch):
    prior={'a'*40:dict(hash='a'*40,downloader='OtherQB',files=[FILES[0]],fullpaths=['keep'],phase='started')}
    qb,data,hist,result,_=submission(monkeypatch,registry=prior,service_factory=service)
    assert result[0] is None and not qb.calls and not hist
    assert data['selected_downloads']==prior


def test_tr_seeding_duration_is_explicitly_queried_and_missing_duration_is_unknown():
    adapter=service(QB()).instance
    assert adapter.seeding_seconds('a'*40)==123
    assert adapter.client.rpc_calls[-1]['arguments']==['hashString','secondsSeeding']
    adapter.client.trc.get_torrents=lambda **kwargs:(_ for _ in ()).throw(RuntimeError('private details'))
    assert adapter.seeding_seconds('a'*40) is None


def test_cross_client_cleanup_checks_use_each_clients_path_mapping_even_for_same_hash():
    entry={'downloader':'TR','source_root':'/mp/download/album','hash':'a'*40}
    qb=QB()
    qb.row.update(content_path='/qb/download/album',save_path='/qb/download')
    service=SimpleNamespace(instance=qb,module=SimpleNamespace(normalize_path=lambda p,n:str(p).replace('/mp','/qb')))
    with pytest.raises(selected.SelectionError,match='仍使用该目录'):
        downloaders.check_shared_clients(entry,{'QB':service})
    qb.row['content_path']='/qb/download/other-album'
    downloaders.check_shared_clients(entry,{'QB':service})
    qb.get_torrents=lambda:([],True)
    with pytest.raises(selected.SelectionError,match='无法核对'):
        downloaders.check_shared_clients(entry,{'QB':service})


def test_readable_downloader_check_is_cached_and_recovers_after_failure():
    now=[100];calls=[]
    instance=SimpleNamespace(get_torrents=lambda **kwargs:(calls.append(kwargs) or [],True))
    ns=plugin_methods({'_downloader_status'},dict(time=SimpleNamespace(monotonic=lambda:now[0]),SelectionError=selected.SelectionError))
    plugin=SimpleNamespace(_guard_lock=Lock(),_downloader_checks={},_download_options=lambda:{'downloader':None},
        _default_downloader=lambda:'default',_download_service=lambda name:SimpleNamespace(type='transmission',instance=instance))
    check=MethodType(ns['_downloader_status'],plugin)
    assert not check('siteTR')['available'] and check('siteTR')['supported']
    assert len(calls)==1 and check('siteTR')['name']=='siteTR'
    now[0]+=61;instance.get_torrents=lambda **kwargs:([],False)
    assert check('siteTR')['available']


def test_downloader_probe_does_not_leak_unexpected_exception_details():
    ns=plugin_methods({'_downloader_status'},dict(time=time,SelectionError=selected.SelectionError))
    def fail(_):raise RuntimeError('password=never-display')
    plugin=SimpleNamespace(_guard_lock=Lock(),_downloader_checks={},_download_options=lambda:{'downloader':'TR'},
        _default_downloader=lambda:'QB',_download_service=fail)
    result=ns['_downloader_status'](plugin)
    assert 'never-display' not in result['error'] and 'TR' in result['error']


def test_submission_error_shows_on_song_but_never_overrides_confirmed_library_or_active_download():
    state={'tracks':{'one':dict(present=True,status='subscribed',song={'title':'Song'})}}
    errors={'one':{'reason':'无法连接下载器 TR'}}
    result=lifecycle.song_lifecycle(state,{}, {}, [],file_exists=lambda *a:False,download_errors=errors)
    assert result['states']['one']['status']=='download_failed'
    assert result['states']['one']['status_message']==errors['one']['reason']
    result=lifecycle.song_lifecycle(state,{}, {}, [],library_files={'one':{'path':'/music/song','storage':'local'}},
        file_exists=lambda *a:True,download_errors=errors)
    assert result['states']['one']['status']=='library'
    entry={'files':['song.flac'],'fullpaths':['/download/song.flac'],'matches':{'one':'song.flac'}}
    tasks={'hash':{'success':True,'state':'downloading','file_priorities':[{'name':'song.flac','priority':1,'progress':0.4}]}}
    result=lifecycle.song_lifecycle(state,{'hash':entry},tasks,[],file_exists=lambda *a:False,download_errors=errors)
    assert result['states']['one']['status']=='downloading'
