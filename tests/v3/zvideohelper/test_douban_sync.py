"""Run only status-sync methods against fake SQL reads and HTTP; never start MP."""
import ast
from enum import Enum
import json
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import Mock

import requests

from test_douban_auth import COOKIE, ROOT, Harness, load_helper, response


class FakeCursor:
    def __init__(self, watching, done):
        self.watching, self.done, self.query, self.group = watching, done, '', None
        self.closed = False

    def execute(self, query, params=None):
        if not query.lstrip().startswith('SELECT'):
            raise AssertionError('offline sync fixture forbids DB writes')
        self.query = query
        if 'FROM zvideo_playlist' in query:
            self.group = self.watching
        elif 'FROM zvideo_collection_tags' in query:
            self.group = self.done

    def fetchall(self):
        if 'SELECT collection_id' in self.query:
            return [('one-fixture-group',)] if self.group else []
        return [(json.dumps({'title': title, 'relation': {'douban': {'douban_id': subject}}}),)
                for title, subject in self.group]

    def close(self):
        self.closed = True


def plugin(helper_module, watching=(), done=(), cookie=COOKIE, notify=True, helper=None):
    tree = ast.parse((ROOT / '__init__.py').read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'ZvideoHelper')
    methods = [node for node in cls.body if isinstance(node, ast.FunctionDef) and
               (node.name in ('sync_douban_status', 'set_douban_watching', 'set_douban_done') or
                (node.name.startswith('_') and 'douban' in node.name))]
    cursor = FakeCursor(watching, done)
    connection = Mock()
    connection.cursor.return_value = cursor
    sql = SimpleNamespace(connect=Mock(return_value=connection), Error=RuntimeError)
    scope = {'DoubanHelper': helper_module.DoubanHelper, 'logger': helper_module.logger,
             'sqlite3': sql, 'json': json, 'NotificationType': SimpleNamespace(SiteMessage='site'),
             'DoubanStatus': Enum('DoubanStatus', {'WATCHING': 'do', 'DONE': 'collect'})}
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(ROOT / '__init__.py'), 'exec'), scope)
    obj = SimpleNamespace(_douban_helper=helper, _cookie=cookie, _notify=notify,
                          _should_stop=False, _sync_douban_status=True, _cached_data={},
                          _db_path='OFFLINE-FAKE-DO-NOT-OPEN', post_message=Mock(), save_data=Mock())
    for node in methods:
        setattr(obj, node.name, MethodType(scope[node.name], obj))
    return obj, sql, connection, cursor


class DoubanSyncTests(unittest.TestCase):
    def test_missing_dbcl2_batch_has_zero_posts_and_one_actionable_notice(self):
        with Harness(get_results=[response()] * 3) as h:
            obj, sql, _, _ = plugin(h.module, watching=[(f'Show {n}', str(n)) for n in range(12)],
                                    done=[('Done', '99')], cookie='ck=anonymous==')
            obj.sync_douban_status()
            h.session.post.assert_not_called()
            sql.connect.assert_not_called()
            obj.post_message.assert_called_once()
            notice = obj.post_message.call_args.kwargs['text']
            self.assertIn('认证失败', notice)
            self.assertIn('请重新登录豆瓣并同步CookieCloud/更新插件Cookie', notice)
            self.assertNotIn('未开播', notice)
            self.assertEqual(obj._cached_data, {})
            self.assertTrue(obj._sync_douban_status)

    def test_missing_ck_and_notify_disabled_silently_skip_writes(self):
        with Harness(get_results=[response()] * 3) as h:
            obj, _, _, _ = plugin(h.module, watching=[('Show', '1')], cookie='dbcl2=user', notify=False)
            obj.sync_douban_status()
            h.session.post.assert_not_called()
            obj.post_message.assert_not_called()
            self.assertEqual(obj._cached_data, {})

    def test_every_sync_refreshes_cookiecloud_once_and_clears_stale_credentials(self):
        module = load_helper()
        module.CookieCloudHelper.return_value.download.side_effect = [
            ({'douban.com': 'dbcl2=old-user; ck=old=='}, ''),
            ({'douban.com': 'dbcl2=new-user; ck=new=='}, ''),
            (None, 'offline failure')]
        with Harness(module, get_results=[response()] * 3) as h:
            helper = h.helper(None)
            obj, _, _, _ = plugin(module, watching=[('Show', '1')], cookie=None, helper=helper)
            obj.sync_douban_status()
            self.assertEqual(helper.cookies['dbcl2'], 'new-user')
            self.assertEqual(h.session.post.call_args.kwargs['data']['ck'], 'new==')
            obj._cached_data = {}
            obj.sync_douban_status()
            self.assertEqual(module.CookieCloudHelper.return_value.download.call_count, 3)
            self.assertEqual(h.session.post.call_count, 1)
            self.assertEqual(obj._cached_data, {})
            obj.post_message.assert_any_call(mtype='site', title='【极影视助手】',
                text='豆瓣认证失败，已停止本轮状态同步。请重新登录豆瓣并同步CookieCloud/更新插件Cookie。')

    def test_business_failures_never_cache_and_later_valid_items_continue(self):
        failures = [{'r': False}, {'r': 1}, {}, {'r': None}, {'r': True}]
        with Harness(get_results=[response()] * 2,
                     post_results=[response(payload=item) for item in failures] + [response(payload={'r': 0})]) as h:
            obj, _, connection, cursor = plugin(h.module, watching=[(f'Show {n}', str(n)) for n in range(6)])
            obj.sync_douban_status()
            self.assertEqual(h.session.post.call_count, 6)
            self.assertEqual(obj._cached_data, {'Show 5': 'do'})
            obj.save_data.assert_called_once_with('zvideohelper', {'Show 5': 'do'})
            self.assertTrue(cursor.closed)
            self.assertTrue(connection.close.called)

    def test_html_and_timeout_do_not_abort_later_valid_business_items(self):
        with Harness(get_results=[response()] * 2, post_results=[response(text='<html>bad gateway</html>'),
                     requests.Timeout('offline'), response(payload={'r': 0})]) as h:
            obj, _, _, _ = plugin(h.module, watching=[('HTML', '1'), ('Timeout', '2'), ('Valid', '3')])
            obj.sync_douban_status()
            self.assertEqual(h.session.post.call_count, 3)
            self.assertEqual(obj._cached_data, {'Valid': 'do'})

    def test_unexpected_per_item_error_does_not_abort_other_items(self):
        with Harness(get_results=[response()] * 2) as h:
            helper = h.helper()
            helper.set_watching_status = Mock(side_effect=[ValueError('offline item'), True])
            obj, _, _, _ = plugin(h.module, watching=[('Bad', '1'), ('Good', '2')], helper=helper)
            obj.sync_douban_status()
            self.assertEqual(obj._cached_data, {'Good': 'do'})
            self.assertEqual(helper.set_watching_status.call_count, 2)

    def test_first_auth_failure_stops_remaining_watching_and_done_posts(self):
        for result in [response(401), response(403),
                       response(302, location='https://accounts.douban.com/passport/login')]:
            with self.subTest(status=result.status_code), Harness(get_results=[response()] * 2, post_results=[result] * 20) as h:
                obj, _, _, _ = plugin(h.module, watching=[(f'Show {n}', str(n)) for n in range(12)],
                                       done=[('Done', '99')])
                obj.sync_douban_status()
                self.assertEqual(h.session.post.call_count, 1)
                self.assertEqual(obj._cached_data, {})
                obj.post_message.assert_called_once()
                self.assertIn('请重新登录豆瓣', obj.post_message.call_args.kwargs['text'])

    def test_done_auth_failure_also_stops_remaining_posts(self):
        with Harness(get_results=[response()] * 2, post_results=[response(403)] * 3) as h:
            obj, _, _, _ = plugin(h.module, done=[('Done 1', '1'), ('Done 2', '2')])
            obj.sync_douban_status()
            self.assertEqual(h.session.post.call_count, 1)
            self.assertEqual(obj._cached_data, {})
            obj.post_message.assert_called_once()

    def test_success_before_auth_failure_remains_cached_but_failure_does_not(self):
        with Harness(get_results=[response()] * 2, post_results=[response(payload={'r': 0}), response(403)]) as h:
            obj, _, _, _ = plugin(h.module, watching=[('Success', '1'), ('Rejected', '2'), ('Skipped', '3')])
            obj.sync_douban_status()
            self.assertEqual(h.session.post.call_count, 2)
            self.assertEqual(obj._cached_data, {'Success': 'do'})
            obj.save_data.assert_called_once_with('zvideohelper', {'Success': 'do'})

    def test_watching_and_done_keep_existing_cache_transition_rules(self):
        with Harness(get_results=[response()] * 2, post_results=[response(payload={'r': 0})] * 3) as h:
            obj, _, _, _ = plugin(h.module, watching=[('Cached', '1'), ('New', '2')],
                                    done=[('Cached', '1'), ('Done', '3')])
            obj._cached_data = {'Cached': 'do', 'Done': 'collect'}
            obj.sync_douban_status()
            self.assertEqual(h.session.post.call_count, 2)
            self.assertEqual(obj._cached_data, {'Cached': 'collect', 'New': 'do', 'Done': 'collect'})


if __name__ == '__main__':
    unittest.main()
