import sys
import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

path = Path(__file__).parents[3] / "plugins.v3/qqmusicplaylistsync/core.py"
spec = importlib.util.spec_from_file_location("app.plugins.qqmusicplaylistsync.core", path)
core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = core
spec.loader.exec_module(core)


def raw_song(number):
    return {"mid": f"song{number:05}", "name": f"歌曲 {number}", "singer": [{"name": "歌手"}],
            "album": {"name": "专辑", "mid": "album001"}, "interval": 180}


def envelope(songs, total, more):
    return {"code": 0, "req_0": {"code": 0, "data": {"songlist": songs,
            "total_song_num": total, "hasmore": int(more), "dirinfo": {"title": "我的歌单"}}}}


def snapshot(numbers):
    songs = [core.normalize_song(raw_song(n)) for n in numbers]
    return {"id": "9060297214", "title": "我的歌单", "total": len(songs), "songs": songs}


def test_fetches_all_291_tracks_in_three_pages():
    offsets = []

    def request(pid, offset, count):
        offsets.append(offset)
        end = min(291, offset + count)
        return envelope([raw_song(n) for n in range(offset, end)], 291, end < 291)

    result = core.fetch_playlist(request, "9060297214", page_size=100)
    assert offsets == [0, 100, 200]
    assert len(result["songs"]) == result["total"] == 291


def test_does_not_accept_truncated_public_web_preview():
    with pytest.raises(core.PlaylistError, match="分页不完整"):
        core.fetch_playlist(lambda *_: envelope([raw_song(1)], 291, False), "1")


def test_repeated_page_is_not_treated_as_new_songs():
    with pytest.raises(core.PlaylistError, match="重复返回同一页"):
        core.fetch_playlist(lambda *_: envelope([raw_song(1)], 291, True), "1")


def test_changed_total_during_pagination_retries_whole_snapshot():
    def request(pid, offset, count):
        return envelope([raw_song(offset)], 2 if offset == 0 else 3, True)

    with pytest.raises(core.PlaylistError, match="歌单发生变化"):
        core.fetch_playlist(request, "1", page_size=1)


def test_invalid_and_private_playlist_response_does_not_become_empty_snapshot():
    with pytest.raises(core.PlaylistError):
        core.fetch_playlist(lambda *_: {"code": -1}, "1")


def test_filtered_qq_items_are_reported_and_not_silently_lost():
    data = envelope([raw_song(1)], 1, False)
    data["req_0"]["data"]["filtered_song"] = [{"songid": 325368696, "songtype": 13}]
    result = core.fetch_playlist(lambda *_: data, "1")
    state = core.merge_snapshot(None, result, 100)
    assert state["playlist"]["unavailable"] == [{"songid": 325368696, "songtype": 13}]
    assert core.summary(state)["tracked"] == 1


def test_special_qq_entry_is_completed_through_public_metadata_detail():
    data = envelope([raw_song(1)], 1, False)
    data["req_0"]["data"]["filtered_song"] = [{"songid": 325368696, "songtype": 13}]
    extra = raw_song(2)
    extra["id"] = 325368696
    result = core.fetch_playlist(lambda *_: data, "1", fetch_filtered=lambda _: [extra])
    assert result["total"] == 2
    assert len(result["songs"]) == 2
    assert result["unavailable"] == []


def test_unreadable_special_entry_does_not_block_readable_tracks():
    data = envelope([raw_song(1)], 1, False)
    data["req_0"]["data"]["filtered_song"] = [{"songid": 325368696, "songtype": 13}]
    result = core.fetch_playlist(lambda *_: data, "1", fetch_filtered=lambda _: [{"id": 325368696}])
    assert len(result["songs"]) == 1
    assert len(result["unavailable"]) == 1


@pytest.mark.parametrize("value", ["9060297214", "https://i2.y.qq.com/playlist?id=9060297214",
                                     "https://y.qq.com/n/ryqq_v2/playlist/9060297214"])
def test_parses_shared_urls_without_keeping_tracking_parameters(value):
    assert core.playlist_id(value) == "9060297214"


@pytest.mark.parametrize("value", ["https://qq.com.evil.test/?id=12", "file:///etc/passwd", "https://example.com/?id=12"])
def test_does_not_fetch_user_controlled_hosts(value):
    with pytest.raises(core.PlaylistError):
        core.playlist_id(value)


def test_incremental_sync_creates_only_new_track_and_preserves_removed_files():
    state = core.merge_snapshot(None, snapshot([1, 2]), 100)
    created = []

    def subscribe(song):
        created.append(song["mid"])
        return 100 + len(created), ""

    core.process_pending(state, now=100, limit=10, existing={}, in_library=lambda _: None,
                         subscribe=subscribe, save=lambda _: None)
    state = core.merge_snapshot(state, snapshot([2, 3]), 200)
    core.process_pending(state, now=200, limit=10, existing={}, in_library=lambda _: None,
                         subscribe=subscribe, save=lambda _: None)
    assert created == ["song00001", "song00002", "song00003"]
    assert state["tracks"]["song00001"]["status"] == "subscribed"
    assert state["tracks"]["song00001"]["present"] is False
    assert core.summary(state)["subscribed"] == 2


def test_crash_after_native_commit_is_reconciled_without_duplicate_creation():
    state = core.merge_snapshot(None, snapshot([1]), 100)
    calls = []
    core.process_pending(state, now=100, limit=10, existing={"song00001": 42}, in_library=lambda _: None,
                         subscribe=lambda s: calls.append(s), save=lambda _: None)
    assert calls == []
    assert state["tracks"]["song00001"]["subscription_id"] == 42


def test_existing_library_track_is_not_subscribed_again():
    state = core.merge_snapshot(None, snapshot([1]), 100)
    core.process_pending(state, now=100, limit=10, existing={}, in_library=lambda _: "/music/existing.m4a",
                         subscribe=lambda _: pytest.fail("should not subscribe"), save=lambda _: None)
    assert core.summary(state)["library"] == 1


def test_failure_is_retried_after_one_hour_not_marked_successful():
    state = core.merge_snapshot(None, snapshot([1]), 100)
    calls = []

    def subscribe(song):
        calls.append(song)
        return (None, "暂时不可用") if len(calls) == 1 else (99, "")

    for now in (100, 200, 3701):
        core.process_pending(state, now=now, limit=10, existing={}, in_library=lambda _: None,
                             subscribe=subscribe, save=lambda _: None)
        if now == 200:
            assert len(calls) == 1
            assert core.summary(state)["failed"] == 1
    assert len(calls) == 2
    assert core.summary(state)["subscribed"] == 1


def test_batch_limit_and_stop_leave_durable_pending_queue():
    state = core.merge_snapshot(None, snapshot(range(30)), 100)
    writes = []
    core.process_pending(state, now=100, limit=3, existing={}, in_library=lambda _: None,
                         subscribe=lambda _: (42, ""), save=lambda s: writes.append(deepcopy(s)))
    assert core.summary(state)["subscribed"] == 3
    assert core.summary(state)["pending"] == 27
    core.process_pending(state, now=200, limit=30, existing={}, in_library=lambda _: None,
                         subscribe=lambda _: pytest.fail("stopped"), save=lambda _: None, stopped=lambda: True)
    assert core.summary(state)["pending"] == 27
    assert len(writes) == 4


def test_new_favorite_has_priority_over_initial_backfill_queue():
    state = core.merge_snapshot(None, snapshot([1, 2, 3]), 100)
    state = core.merge_snapshot(state, snapshot([4, 1, 2, 3]), 200)
    created = []
    core.process_pending(state, now=200, limit=1, existing={}, in_library=lambda _: None,
                         subscribe=lambda song: (created.append(song["mid"]) or 42, ""), save=lambda _: None)
    assert created == ["song00004"]
    assert core.summary(state)["pending"] == 3


def test_unlimited_round_processes_whole_playlist_and_marks_immediate_search():
    state = core.merge_snapshot(None, snapshot(range(291)), 100)
    seen = []
    core.process_pending(state, now=100, limit=0, existing={}, in_library=lambda _: None,
                         subscribe=lambda song: (seen.append(song['mid']) or len(seen), ''), save=lambda _: None)
    assert len(seen) == 291
    assert core.summary(state)['pending'] == 0
    assert all(item['search_pending'] for item in state['tracks'].values())


def test_parallel_creates_are_bounded_and_ledger_writes_stay_on_caller_thread():
    import threading
    state = core.merge_snapshot(None, snapshot(range(12)), 100)
    barrier = threading.Barrier(4)
    active = 0
    maximum = 0
    mutex = threading.Lock()
    caller = threading.get_ident()
    def subscribe(song):
        nonlocal active, maximum
        with mutex:
            active += 1
            maximum = max(active, maximum)
        barrier.wait(timeout=3)
        with mutex:
            active -= 1
        return int(song['mid'][4:]) + 1, ''
    def save(_):
        assert threading.get_ident() == caller
    count = core.process_pending(state, now=100, limit=0, workers=4, existing={},
                                 in_library=lambda _: None, subscribe=subscribe, save=save)
    assert count == 12
    assert maximum == 4
    assert core.summary(state)['subscribed'] == 12


def test_parallel_failure_does_not_block_other_songs():
    state = core.merge_snapshot(None, snapshot(range(20)), 100)
    def subscribe(song):
        if song['mid'] == 'song00003':
            raise RuntimeError('one failure')
        return int(song['mid'][4:]) + 1, ''
    core.process_pending(state, now=100, limit=0, workers=4, existing={}, in_library=lambda _: None,
                         subscribe=subscribe, save=lambda _: None)
    assert core.summary(state)['subscribed'] == 19
    assert core.summary(state)['failed'] == 1


def test_parallel_stop_saves_in_flight_commits_without_filling_more_work():
    import threading
    state = core.merge_snapshot(None, snapshot(range(291)), 100)
    stopped = threading.Event()
    count = core.process_pending(state, now=100, limit=0, workers=4, existing={},
                                 in_library=lambda _: None, subscribe=lambda _: (42, ''),
                                 save=lambda _: stopped.set(), stopped=stopped.is_set)
    assert 1 <= count <= 4
    assert core.summary(state)['pending'] == 291 - count


def test_same_named_album_selects_only_the_requested_track():
    song = {'title': '纵横四海', 'artists': ['李荣浩']}
    result = core.track_file_selection(song, ['李荣浩 - 纵横四海/01. 纵横四海.m4a',
                    '李荣浩 - 纵横四海/02. 我们好好的.m4a','李荣浩 - 纵横四海/03. 山川.m4a'])
    assert result['allowed'] and result['audio_count'] == 3
    assert result['files'] == ['李荣浩 - 纵横四海/01. 纵横四海.m4a']


@pytest.mark.parametrize('filename', ['01. 纵横四海.m4a','李荣浩 - 纵横四海.flac','纵横四海.mp3'])
def test_verified_single_audio_with_optional_artwork_is_allowed(filename):
    ok, _ = core.single_track_check({'title':'纵横四海','artists':['李荣浩']}, [filename, 'cover.jpg', 'album.nfo'])
    assert ok


@pytest.mark.parametrize('files', [[], ['cover.jpg'], ['我们好好的.m4a'],
                                    ['纵横四海.flac','纵横四海.cue'], ['纵横四海.flac','纵横四海.mp3']])
def test_unverified_or_different_track_or_cue_image_is_blocked(files):
    ok, _ = core.single_track_check({'title':'纵横四海','artists':['李荣浩']},files)
    assert not ok


def test_title_substring_does_not_match_a_different_song():
    ok, _ = core.single_track_check({'title':'Love','artists':['Artist']},['Love Story.flac'])
    assert not ok


def test_multiple_playlist_inputs_accepts_urls_ids_and_deduplicates_identity():
    assert core.playlist_ids('9060297214\nhttps://y.qq.com/n/ryqq_v2/playlist/9450108630\n\n9060297214') == ['9060297214','9450108630']
    assert core.playlist_ids(['12', '12', '34']) == ['12','34']


def test_multiple_playlist_input_errors_include_line_number():
    with pytest.raises(core.PlaylistError, match='第 2 行'):
        core.playlist_ids('12\nhttps://example.test/playlist?id=34')
    with pytest.raises(core.PlaylistError, match='至少'):
        core.playlist_ids('\n  \n')


def multi_snapshot(pid, numbers):
    result = snapshot(numbers)
    result.update(id=pid,title=f'歌单 {pid}')
    return result


def test_multiple_playlists_share_one_subscription_per_mid():
    state = core.merge_playlists(None, {'1':multi_snapshot('1',[1,2]),'2':multi_snapshot('2',[2,3])}, {}, ['1','2'], 100)
    created=[]
    core.process_pending(state, now=100, limit=0, existing={}, in_library=lambda _:None,
                         subscribe=lambda song:(created.append(song['mid']) or len(created),''), save=lambda _:None)
    assert len(created)==3
    assert core.summary(state)['subscribed']==3
    assert state['tracks']['song00002']['playlist_ids']==['1','2']
    assert len(core.summary(state)['playlists'])==2


def test_removal_from_one_playlist_does_not_remove_membership_in_another():
    state = core.merge_playlists(None, {'1':multi_snapshot('1',[1,2]),'2':multi_snapshot('2',[2,3])}, {}, ['1','2'], 100)
    state = core.merge_playlists(state, {'1':multi_snapshot('1',[1]),'2':multi_snapshot('2',[2,3])}, {}, ['1','2'], 200)
    assert state['tracks']['song00002']['present']
    assert state['tracks']['song00002']['playlist_ids']==['2']
    assert core.summary(state)['tracked']==3


def test_failure_in_one_playlist_preserves_its_previous_snapshot_and_accepts_other_updates():
    state = core.merge_playlists(None, {'1':multi_snapshot('1',[1,2]),'2':multi_snapshot('2',[2,3])}, {}, ['1','2'], 100)
    state = core.merge_playlists(state, {'2':multi_snapshot('2',[3,4])}, {'1':'temporary error'}, ['1','2'], 200)
    assert state['tracks']['song00001']['present']
    assert state['tracks']['song00002']['playlist_ids']==['1']
    assert state['tracks']['song00004']['present']
    assert state['playlists']['1']['last_fetch']==100
    assert state['playlists']['1']['last_error']=='temporary error'
    assert state['playlists']['2']['last_error']==''
    assert core.summary(state)['tracked']==4


def test_removing_a_playlist_keeps_existing_records_without_queuing_its_exclusive_tracks():
    state = core.merge_playlists(None, {'1':multi_snapshot('1',[1,2]),'2':multi_snapshot('2',[2,3])}, {}, ['1','2'], 100)
    state = core.merge_playlists(state, {'2':multi_snapshot('2',[2,3])}, {}, ['2'], 200)
    assert not state['tracks']['song00001']['present']
    assert state['tracks']['song00001']['status']=='pending'
    assert state['tracks']['song00002']['playlist_ids']==['2']
    assert not state['playlists']['1']['enabled']
    assert len(core.summary(state)['playlists'])==1


def test_legacy_single_playlist_ledger_migrates_without_losing_completed_subscriptions():
    song=core.normalize_song(raw_song(1))
    state={'version':1,'playlist':{'id':'1','title':'old','total':1},'last_fetch':50,
           'tracks':{song['mid']:{'song':song,'present':True,'status':'subscribed','attempts':1,'first_seen':50,
                                 'subscription_id':123,'search_pending':False,'search_requested_at':70}}}
    state=core.merge_playlists(state, {'2':multi_snapshot('2',[1,2])}, {'1':'temporarily offline'}, ['1','2'], 100)
    item=state['tracks']['song00001']
    assert state['version']==2
    assert item['subscription_id']==123 and item['status']=='subscribed'
    assert item['search_pending'] is False and item['search_requested_at']==70
    assert item['first_seen']==50 and item['playlist_ids']==['1','2']
    assert core.summary(state)['tracked']==2


def test_restart_and_unchanged_multi_playlist_do_not_create_or_search_again():
    import json
    inputs={'1':multi_snapshot('1',[1,2]),'2':multi_snapshot('2',[2,3])}
    state=core.merge_playlists(None,inputs,{},['1','2'],100)
    for item in state['tracks'].values(): item.update(status='subscribed',subscription_id=42,search_pending=False,search_requested_at=101)
    state=json.loads(json.dumps(state))
    state=core.merge_playlists(state,inputs,{},['1','2'],200)
    assert core.process_pending(state,now=200,limit=0,existing={},in_library=lambda _:None,
                                subscribe=lambda _:pytest.fail('duplicate'),save=lambda _:None)==0
    assert not any(item['search_pending'] for item in state['tracks'].values())
