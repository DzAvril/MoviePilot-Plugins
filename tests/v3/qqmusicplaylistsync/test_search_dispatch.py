"""隔离宿主依赖，验证插件实际队列提交方法的契约与持久化顺序。"""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import time

import pytest
from test_core import core


def plugin_method(chain, events, scheduler_result=True):
    path = Path(__file__).parents[3] / 'plugins.v3/qqmusicplaylistsync/__init__.py'
    tree = ast.parse(path.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == '_queue_search')
    module = ast.Module(body=[method], type_ignores=[])
    namespace = {'SubscribeChain': lambda: chain, 'time': time,
                 'MUSIC_SOURCES':core.MUSIC_SOURCES,'track_key':core.track_key,
                 'add_plugin_once_job': lambda *args, **kwargs: events.append(('wake', args, kwargs)) or scheduler_result,
                 'logger': SimpleNamespace(info=lambda _: None)}
    exec(compile(module, str(path), 'exec'), namespace)
    return namespace['_queue_search']


def fixture():
    events = []
    active = {11: SimpleNamespace(media_source='qqmusic', media_id='song00001'),
              12: SimpleNamespace(media_source='qqmusic', media_id='song00002'),
              99: SimpleNamespace(media_source='musicbrainz', media_id='song00003')}
    def enqueue(**kwargs):
        events.append(('enqueue', kwargs))
        return SimpleNamespace(created_count=0, coalesced_count=len(kwargs['subscription_ids']),
                               batch=SimpleNamespace(batch_id='batch-123'))
    chain = SimpleNamespace(subscription_repository=SimpleNamespace(get=active.get),
                            subscription_search_repository=SimpleNamespace(enqueue=enqueue),
                            resume_search_queue=lambda: None)
    state = {'tracks': {f'song0000{i}': {'present': True, 'status': 'subscribed',
              'song': {'mid': f'song0000{i}'}, 'subscription_id': sid}
              for i, sid in [(1, 11), (2, 12), (3, 99), (4, 123)]}}
    plugin = SimpleNamespace(SOURCE='qqmusic', _state=state,
                             _save=lambda value: events.append(('save', deepcopy(value))))
    return plugin, chain, events


def test_dispatch_promotes_only_matching_qq_subscriptions_then_wakes_immediately():
    plugin, chain, events = fixture()
    method = plugin_method(chain, events)
    assert method(plugin) == 2
    assert [event[0] for event in events] == ['enqueue', 'save', 'wake']
    args = events[0][1]
    assert args['subscription_ids'] == (11, 12)
    assert args['source'] == 'manual' and args['priority'] == 100
    assert args['available_at_by_subscription'] is None
    assert events[-1][2]['delay_seconds'] == 0
    assert events[-1][2]['func_kwargs']['limit'] >= 2
    assert all(not item['search_pending'] for item in plugin._state['tracks'].values())
    events.clear()
    assert method(plugin) == 0
    assert not any(event[0] in ('enqueue', 'wake') for event in events)


def test_enqueue_failure_does_not_mark_pending_searches_as_dispatched():
    plugin, chain, events = fixture()
    def fail(**_):
        raise RuntimeError('queue unavailable')
    chain.subscription_search_repository.enqueue = fail
    with pytest.raises(RuntimeError, match='queue unavailable'):
        plugin_method(chain, events)(plugin)
    assert events == []
    assert all('search_requested_at' not in item for item in plugin._state['tracks'].values())


def test_persistent_queue_is_kept_when_scheduler_cannot_wake():
    plugin, chain, events = fixture()
    assert plugin_method(chain, events, scheduler_result=False)(plugin) == 2
    assert events[0][0] == 'enqueue'
    assert plugin._state['last_search']['targets'] == 2
