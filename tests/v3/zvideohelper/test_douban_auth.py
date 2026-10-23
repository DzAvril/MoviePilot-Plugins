"""Offline regressions: real Requests cookies, no MoviePilot or HTTP calls."""
import ast
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import requests

ROOT = Path(__file__).resolve().parents[3] / 'plugins.v3/zvideohelper'
COOKIE = 'dbcl2="offline-user"; ck=old-token=='


def load_helper(parser=None):
    # Exercise the real class without importing/starting MoviePilot. The search
    # parser is mocked; CK parsing and RequestsCookieJar are not substituted.
    tree = ast.parse((ROOT / 'DoubanHelper.py').read_text())
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.ImportFrom) and
        ((node.module or '').startswith('app.') or node.module == 'bs4')) and
        not isinstance(node, ast.If)]
    scope = {'logger': Mock(), 'CookieCloudHelper': Mock(), 'BeautifulSoup': parser or Mock()}
    exec(compile(tree, str(ROOT / 'DoubanHelper.py'), 'exec'), scope)
    return SimpleNamespace(**scope)


def response(status=200, payload=None, text='', cookies=(), url='https://www.douban.com/', location=None):
    result = requests.Response()
    result.status_code = status
    result.url = url
    result._content = (json.dumps(payload) if payload is not None else text).encode()
    result.encoding = 'utf-8'
    for name, value in cookies:
        result.cookies.set(name, value, domain='.douban.com', path='/')
    if cookies:
        result.headers['Set-Cookie'] = ', '.join(f'{name}={value}; Path=/' for name, value in cookies)
    if location:
        result.headers['Location'] = location
    return result


class Harness:
    def __init__(self, module=None, get_results=None, post_results=None):
        self.module = module or load_helper()
        self.session = requests.Session()
        self.session.get = Mock(side_effect=get_results or [response()])
        self.session.post = Mock(side_effect=post_results or [response(payload={'r': 0})])
        self.patches = [patch.object(requests, 'Session', return_value=self.session),
                        patch.object(requests, 'get', self.session.get),
                        patch.object(requests, 'post', self.session.post),
                        patch.object(requests.sessions.Session, 'send',
                                     side_effect=AssertionError('HTTP is forbidden in offline tests'))]

    def __enter__(self):
        for item in self.patches:
            item.start()
        return self

    def __exit__(self, *args):
        for item in reversed(self.patches):
            item.stop()
        self.session.close()

    def helper(self, cookie=COOKIE):
        return self.module.DoubanHelper(user_cookie=cookie)


class DoubanAuthTests(unittest.TestCase):
    def test_named_cookie_not_first_and_equals_value(self):
        with Harness(get_results=[response(cookies=[('bid', 'not-the-token'), ('ck', 'new-token==')])]) as h:
            helper = h.helper()
            self.assertEqual(helper.ck, 'new-token==')
            self.assertEqual(helper.cookies['ck'], helper.ck)

    def test_no_new_ck_preserves_supplied_ck(self):
        with Harness() as h:
            helper = h.helper()
            self.assertEqual(helper.ck, 'old-token==')
            self.assertEqual(helper.cookies['ck'], 'old-token==')

    def test_unrelated_set_cookie_does_not_replace_ck(self):
        with Harness(get_results=[response(cookies=[('bid', 'unrelated')])]) as h:
            self.assertEqual(h.helper().ck, 'old-token==')

    def test_ck_rotated_on_post_is_used_by_next_form(self):
        with Harness(post_results=[response(payload={'r': 0}, cookies=[('ck', 'rotated==')]),
                                   response(payload={'r': 0})]) as h:
            helper = h.helper()
            self.assertTrue(helper.set_watching_status('123'))
            self.assertTrue(helper.set_watching_status('456'))
            self.assertEqual(h.session.post.call_args.kwargs['data']['ck'], 'rotated==')
            self.assertEqual(helper.cookies['ck'], 'rotated==')
            self.assertEqual(h.session.cookies.get('ck'), 'rotated==')

    def test_ck_rotated_on_public_lookup_is_used_by_write(self):
        with Harness(get_results=[response(), response(cookies=[('ck', 'search-token==')])]) as h:
            helper = h.helper()
            h.module.BeautifulSoup.return_value.find_all.return_value = []
            helper.get_subject_id('Example')
            self.assertTrue(helper.set_watching_status('123'))
            self.assertEqual(h.session.post.call_args.kwargs['data']['ck'], 'search-token==')

    def test_html_hidden_ck_is_decoded(self):
        with Harness(get_results=[response(text='<input value="html&amp;token==" type="hidden" name="ck">')]) as h:
            self.assertEqual(h.helper().ck, 'html&token==')

    def test_new_ck_updates_cookie_jar_dictionary_and_form(self):
        with Harness(get_results=[response(cookies=[('ck', 'first==')]), response(cookies=[('ck', 'second==')])]) as h:
            helper = h.helper()
            helper.set_ck()
            self.assertTrue(helper.set_watching_status('123', status='collect'))
            self.assertEqual(helper.ck, 'second==')
            self.assertEqual(helper.cookies['ck'], 'second==')
            self.assertEqual(h.session.cookies.get('ck'), 'second==')
            self.assertEqual(h.session.post.call_args.kwargs['data']['ck'], 'second==')
            self.assertEqual(h.session.post.call_args.kwargs['data']['interest'], 'collect')

    def test_no_manual_host_or_cookie_and_local_post_headers(self):
        with Harness() as h:
            helper = h.helper()
            original = helper.headers.copy()
            helper.set_watching_status('123')
            self.assertEqual(helper.headers, original)
            for call in h.session.get.call_args_list + h.session.post.call_args_list:
                headers = call.kwargs.get('headers', {})
                self.assertTrue({'host', 'cookie'}.isdisjoint(k.lower() for k in headers))
                self.assertGreater(call.kwargs['timeout'], 0)
            self.assertFalse(h.session.post.call_args.kwargs['allow_redirects'])

    def test_cookies_are_scoped_to_douban_not_other_domains(self):
        with Harness() as h:
            helper = h.helper()
            movie = h.session.prepare_request(requests.Request('GET', 'https://movie.douban.com/'))
            other = h.session.prepare_request(requests.Request('GET', 'https://example.org/'))
            self.assertIn('dbcl2=', movie.headers.get('Cookie', ''))
            self.assertNotIn('Cookie', other.headers)
            self.assertTrue(helper.is_ready())

    def test_cookiecloud_refresh_reloads_both_rounds(self):
        module = load_helper()
        module.CookieCloudHelper.return_value.download.side_effect = [
            ({'douban.com': 'dbcl2=user-one; ck=one=='}, ''),
            ({'douban.com': 'dbcl2=user-two; ck=two=='}, '')]
        with Harness(module, get_results=[response(), response()]) as h:
            helper = h.helper(None)
            self.assertEqual(helper.cookies['dbcl2'], 'user-one')
            helper.refresh_auth()
            self.assertEqual(helper.cookies['dbcl2'], 'user-two')
            self.assertEqual(helper.ck, 'two==')
            self.assertEqual(module.CookieCloudHelper.return_value.download.call_count, 2)
            self.assertEqual(h.session.get.call_count, 2)

    def test_manual_cookie_takes_precedence_over_cookiecloud(self):
        with Harness(get_results=[response(), response()]) as h:
            helper = h.helper()
            helper.refresh_auth(user_cookie='dbcl2=manual-new; ck=manual==')
            h.module.CookieCloudHelper.assert_not_called()
            self.assertEqual(helper.cookies['dbcl2'], 'manual-new')
            self.assertEqual(helper.ck, 'manual==')

    def test_cookiecloud_none_missing_domain_empty_and_download_error_are_safe(self):
        for download in [(None, 'offline failure'), ({}, ''), ({'douban.com': ''}, ''), RuntimeError('offline')]:
            with self.subTest(download=type(download).__name__):
                module = load_helper()
                if isinstance(download, Exception):
                    module.CookieCloudHelper.return_value.download.side_effect = download
                else:
                    module.CookieCloudHelper.return_value.download.return_value = download
                with Harness(module) as h:
                    helper = h.helper(None)
                    self.assertFalse(helper.is_ready())
                    self.assertFalse(helper.set_watching_status('123'))
                    h.session.post.assert_not_called()

    def test_refresh_does_not_reuse_old_credentials_when_cookiecloud_is_empty(self):
        module = load_helper()
        module.CookieCloudHelper.return_value.download.side_effect = [({'douban.com': COOKIE}, ''), (None, 'offline')]
        with Harness(module) as h:
            helper = h.helper(None)
            helper.refresh_auth()
            self.assertFalse(helper.is_ready())
            self.assertNotIn('dbcl2', helper.cookies)
            self.assertFalse(helper.set_watching_status('123'))
            h.session.post.assert_not_called()

    def test_missing_dbcl2_or_ck_never_posts(self):
        for cookie in ['ck=anonymous==', 'dbcl2=user', 'bid=anonymous']:
            with self.subTest(cookie=cookie), Harness() as h:
                helper = h.helper(cookie)
                self.assertFalse(helper.is_ready())
                self.assertFalse(helper.set_watching_status('123'))
                h.session.post.assert_not_called()

    def test_only_exact_integer_zero_is_success(self):
        for payload, expected in [({'r': 0}, True), ({'r': False}, False), ({'r': 1}, False),
                                  ({}, False), ({'r': None}, False), ({'r': True}, False),
                                  ({'r': 0.0}, False), ({'r': '0'}, False), ([], False)]:
            with self.subTest(payload=payload), Harness(post_results=[response(payload=payload)]) as h:
                self.assertIs(h.helper().set_watching_status('123'), expected)

    def test_business_false_does_not_guess_unreleased(self):
        with Harness(post_results=[response(payload={'r': False})]) as h:
            self.assertFalse(h.helper().set_watching_status('123'))
            self.assertNotIn('未开播', str(h.module.logger.mock_calls))

    def test_html_200_invalid_json_and_timeout_fail_without_raising(self):
        for result in [response(text='<html>not JSON</html>'), requests.Timeout('offline')]:
            with self.subTest(result=type(result).__name__), Harness(post_results=[result]) as h:
                helper = h.helper()
                self.assertFalse(helper.set_watching_status('123'))
                self.assertTrue(helper.is_ready(), 'a per-item failure must not invalidate unrelated work')

    def test_http_401_403_login_redirect_and_login_html_block_further_posts(self):
        cases = [response(401), response(403),
                 response(302, location='https://accounts.douban.com/passport/login'),
                 response(text='<form><input name="form_email"><input name="form_password" type="password"></form>')]
        for result in cases:
            with self.subTest(status=result.status_code, text=result.text), Harness(post_results=[result]) as h:
                helper = h.helper()
                self.assertFalse(helper.set_watching_status('123'))
                self.assertFalse(helper.is_ready())
                self.assertTrue(helper.auth_failed)
                self.assertFalse(helper.set_watching_status('456'))
                self.assertEqual(h.session.post.call_count, 1)
                self.assertTrue(h.module.logger.error.called)
                if result.status_code in (401, 403):
                    self.assertIn(str(result.status_code), str(h.module.logger.error.call_args_list))

    def test_auth_rejection_during_ck_refresh_blocks_writes(self):
        with Harness(get_results=[response(403)]) as h:
            helper = h.helper()
            self.assertFalse(helper.is_ready())
            self.assertFalse(helper.set_watching_status('123'))
            h.session.post.assert_not_called()

    def test_ck_timeout_preserves_existing_token_without_crashing(self):
        with Harness(get_results=[requests.Timeout('offline')]) as h:
            self.assertEqual(h.helper().ck, 'old-token==')

    def test_credentials_and_response_bodies_are_not_logged(self):
        with Harness(post_results=[response(403, text='SECRET-BODY')]) as h:
            helper = h.helper('dbcl2=SECRET-USER; ck=SECRET-TOKEN')
            helper.set_watching_status('123')
            logs = str(h.module.logger.mock_calls)
            for secret in ['SECRET-USER', 'SECRET-TOKEN', 'SECRET-BODY']:
                self.assertNotIn(secret, logs)

    def test_anonymous_search_still_uses_public_endpoint(self):
        with Harness(get_results=[response(), response(text='<html>search</html>')]) as h:
            helper = h.helper('bid=anonymous')
            h.module.BeautifulSoup.return_value.find_all.return_value = []
            self.assertEqual(helper.get_subject_id('Example'), (None, None, None))
            self.assertTrue(any('/search?' in str(call) for call in h.session.get.call_args_list))
            self.assertEqual(h.session.post.call_count, 0)

    @unittest.skipUnless(importlib.util.find_spec('bs4'), 'optional real BeautifulSoup integration unavailable')
    def test_anonymous_search_parses_title_subject_and_score_with_real_bs4(self):
        from bs4 import BeautifulSoup
        module = load_helper(parser=BeautifulSoup)
        html = ('<div class="title"><a href="https://movie.douban.com/subject/123/">Example</a>'
                '<span class="subject-cast">演员 / 2026</span><span class="rating_nums">8.7</span></div>')
        with Harness(module, get_results=[response(text=html)]) as h:
            self.assertEqual(h.helper('bid=anonymous').get_subject_id('Example'), ('Example', '123', '8.7'))
            h.session.post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
