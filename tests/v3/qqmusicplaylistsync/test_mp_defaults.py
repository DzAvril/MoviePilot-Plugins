from pathlib import Path
from types import SimpleNamespace, MethodType
import sys

import pytest

from test_selected_downloads import plugin_methods
from test_core import core


def fixture(monkeypatch, overrides=None):
    current = {'defaults':{}, 'download':'/music-download', 'library':'/music-library',
               'configs':{'other':SimpleNamespace(name='other',default=False),
                          'QB':SimpleNamespace(name='QB',default=True)}}
    class Directory:
        def get_download_dir_by_task_path(self,media,task_path):
            return self.get_dir(media)

        def get_dir(self,media,**kwargs):
            assert media.type=='音乐'
            return SimpleNamespace(library_path=current['library'],library_storage='local')
    def resolve(**kwargs):
        assert kwargs['media_info'].type=='音乐'
        path=kwargs['save_path'] or current['download']
        return 'local',Path(path) if path else None,'' if path else '未找到下载目录'
    monkeypatch.setitem(sys.modules,'app.application.configuration',SimpleNamespace(
        get_configured_system_config=lambda:SimpleNamespace(get=lambda _:current['defaults'])))
    monkeypatch.setitem(sys.modules,'app.schemas.types',SimpleNamespace(SystemConfigKey=SimpleNamespace(DefaultMusicSubscribeConfig='music-defaults')))
    monkeypatch.setitem(sys.modules,'app.sdk.services',SimpleNamespace(DownloaderHelper=lambda:SimpleNamespace(get_configs=lambda:current['configs'])))
    monkeypatch.setitem(sys.modules,'app.application.directory',SimpleNamespace(DirectoryHelper=Directory))
    ns=plugin_methods({'_download_options','_default_downloader','_resolved_settings'},dict(
        Path=Path,DownloadChain=lambda:SimpleNamespace(_resolve_media_download_dir=resolve),
        MusicInfo=lambda **kwargs:SimpleNamespace(type='音乐',**kwargs)))
    plugin=SimpleNamespace(_config={'downloader':'','save_path':'','library_path':'',**(overrides or {})})
    for name in ('_download_options','_default_downloader','_resolved_settings'):
        setattr(plugin,name,MethodType(ns[name],plugin))
    return plugin,current


def test_unconfigured_values_resolve_music_directory_and_explicit_default_downloader(monkeypatch):
    plugin,current=fixture(monkeypatch)
    resolved=plugin._resolved_settings()
    assert resolved['downloader']=='QB'
    assert resolved['save_path']=='/music-download' and resolved['library_path']=='/music-library'
    assert all(resolved['follow_mp'].values()) and not resolved['error']
    assert plugin._config=={'downloader':'','save_path':'','library_path':''}


def test_music_subscription_defaults_take_precedence_over_system_defaults(monkeypatch):
    plugin,current=fixture(monkeypatch)
    current['defaults']={'downloader':'MusicQB','save_path':'/subscription-music'}
    resolved=plugin._resolved_settings()
    assert resolved['downloader']=='MusicQB' and resolved['save_path']=='/subscription-music'


def test_explicit_plugin_fields_override_only_the_filled_values(monkeypatch):
    plugin,current=fixture(monkeypatch,{'save_path':'/custom-download'})
    current['defaults']={'downloader':'MusicQB','save_path':'/default-download'}
    resolved=plugin._resolved_settings()
    assert resolved['save_path']=='/custom-download' and resolved['downloader']=='MusicQB'
    assert resolved['library_path']=='/music-library'
    assert resolved['follow_mp']=={'downloader':True,'save_path':False,'library_path':True}


def test_mp_setting_changes_are_read_again_without_saving_resolved_paths(monkeypatch):
    plugin,current=fixture(monkeypatch)
    plugin._resolved_settings()
    current.update(download='/new-download',library='/new-library')
    current['configs']['QB'].default=False
    current['configs']['other'].default=True
    resolved=plugin._resolved_settings()
    assert resolved['downloader']=='other' and resolved['save_path']=='/new-download' and resolved['library_path']=='/new-library'
    assert all(value=='' for value in plugin._config.values())


def test_new_subscription_leaves_native_optional_fields_unset_for_default_resolution():
    calls=[]
    ns=plugin_methods({'_subscribe'},dict(SubscribeChain=lambda:SimpleNamespace(add=lambda **kwargs:calls.append(kwargs)),
        MediaType=SimpleNamespace(MUSIC='音乐'),MediaSource=str))
    plugin=SimpleNamespace(SOURCE='qqmusic',plugin_name='音乐歌单同步',_config={'downloader':'','save_path':''},
                           _state={'tracks':{'one':{'playlist_ids':['123']}}})
    ns['_subscribe'](plugin,{'mid':'one','title':'歌曲','artists':['歌手']})
    assert calls[0]['downloader'] is None and calls[0]['save_path'] is None
    assert calls[0]['music_type']=='recording'


@pytest.mark.parametrize('settings',[{'library_path':None,'library_storage':'local'},
                                     {'library_path':'/remote-music','library_storage':'u115'}])
def test_no_library_directory_never_scans_the_current_working_directory(settings):
    ns=plugin_methods({'_library_index'},dict(Path=Path,text_key=core.text_key))
    plugin=SimpleNamespace(_state={'tracks':{'one':{'present':True,'status':'pending','song':{'title':'歌曲'}}}},
                           _resolved_settings=lambda:settings)
    assert ns['_library_index'](plugin)=={}
