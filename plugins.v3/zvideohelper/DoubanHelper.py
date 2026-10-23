import re
from html.parser import HTMLParser
from http.cookies import CookieError, SimpleCookie
from typing import Optional, Tuple
from urllib.parse import unquote, urlsplit

import requests
from bs4 import BeautifulSoup
from app.helper.cookiecloud import CookieCloudHelper
from app.log import logger


class _DoubanFormParser(HTMLParser):
    """Read the named CSRF input without interpreting unrelated Set-Cookies."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ck = ""
        self.input_names = set()

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "input":
            return
        attrs = dict(attrs)
        name = attrs.get("name", "")
        self.input_names.add(name)
        if name == "ck" and attrs.get("value"):
            self.ck = attrs["value"]

    @property
    def is_login(self):
        return "form_password" in self.input_names


class DoubanHelper:
    REQUEST_TIMEOUT = 20

    def __init__(self, user_cookie: Optional[str] = None):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36 Edg/113.0.1774.57',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.6,en;q=0.4,en-GB;q=0.2,zh-TW;q=0.2',
            'DNT': '1',
        }
        self.refresh_auth(user_cookie)

    def refresh_auth(self, user_cookie: Optional[str] = None) -> bool:
        """Reload credentials once per sync, never retaining a failed cloud read."""
        self.cookies = {}
        self.ck = None
        self.auth_failed = False
        self.session.cookies.clear()
        raw_cookie = user_cookie
        if not raw_cookie:
            try:
                cookie_dict, _ = CookieCloudHelper().download()
                raw_cookie = cookie_dict.get("douban.com") if isinstance(cookie_dict, dict) else None
            except Exception:
                # Provider errors may contain credentials; do not interpolate them.
                logger.error("获取CookieCloud豆瓣Cookie失败")
        if isinstance(raw_cookie, str):
            try:
                self.cookies = {key: value.value for key, value in SimpleCookie(raw_cookie).items()}
            except CookieError:
                logger.error("豆瓣Cookie格式无效，请更新插件Cookie或CookieCloud")
        self.cookies.pop('__utmz', None)
        for key, value in self.cookies.items():
            self.session.cookies.set(key, value, domain='.douban.com', path='/', secure=True)
        self.ck = self.cookies.get('ck')
        # A public/anonymous Cookie cannot authenticate interest writes. Searches
        # remain available through the same helper even when readiness is false.
        if not self.cookies.get('dbcl2'):
            self.auth_failed = True
            logger.error("豆瓣认证失败：缺少登录Cookie dbcl2")
        else:
            self.set_ck()
        if not self.ck:
            logger.error("豆瓣认证失败：缺少CSRF令牌ck")
        return self.is_ready()

    def is_ready(self) -> bool:
        """Minimum write readiness, not a claim that the server accepted login."""
        return bool(self.cookies.get('dbcl2') and self.ck and not self.auth_failed)

    @staticmethod
    def _login_url(url):
        parsed = urlsplit(url or '')
        host = parsed.hostname or ''
        return (host == 'accounts.douban.com' or
                ((host == 'douban.com' or host.endswith('.douban.com') or not host) and
                 any(path in parsed.path for path in ('/accounts/login', '/passport/login'))))

    def _auth_rejected(self, response) -> bool:
        rejected = (response.status_code in (401, 403) or
                    self._login_url(response.url) or
                    self._login_url(response.headers.get('Location')))
        if not rejected and response.status_code == 200 and response.text.lstrip().startswith('<'):
            parser = _DoubanFormParser()
            parser.feed(response.text)
            rejected = parser.is_login
        if rejected:
            self.auth_failed = True
            logger.error(f"豆瓣认证失败（HTTP {response.status_code} 或登录页面），停止本轮状态提交")
        return rejected

    def _store_ck(self, ck):
        # Canonicalize the shared CSRF cookie so host-specific copies cannot
        # disagree with the value sent in the movie.douban.com form.
        for cookie in list(self.session.cookies):
            if cookie.name == 'ck':
                self.session.cookies.clear(cookie.domain, cookie.path, cookie.name)
        if ck:
            self.session.cookies.set('ck', ck, domain='.douban.com', path='/', secure=True)
            self.cookies['ck'] = ck
        self.ck = ck

    def _sync_response_ck(self, response, from_html=False):
        tokens = [cookie.value for cookie in response.cookies
                  if cookie.name == 'ck' and cookie.value and
                  cookie.domain.lstrip('.') in ('douban.com', 'www.douban.com', 'movie.douban.com')]
        ck = tokens[-1] if tokens else None
        if not ck and from_html:
            parser = _DoubanFormParser()
            parser.feed(response.text)
            ck = parser.ck
        self._store_ck(ck or self.ck)

    def set_ck(self):
        try:
            response = self.session.get("https://www.douban.com/", headers=self.headers,
                                        timeout=self.REQUEST_TIMEOUT, allow_redirects=False)
        except requests.RequestException:
            logger.error("获取豆瓣CSRF令牌失败：网络错误，保留已有令牌")
            return
        if response is None:
            logger.error("获取豆瓣CSRF令牌失败：无响应")
            return
        if self._auth_rejected(response):
            return
        if response.status_code != 200:
            logger.error(f"获取豆瓣CSRF令牌失败：HTTP {response.status_code}")
            return
        self._sync_response_ck(response, from_html=True)

    def get_subject_id(self, title: str) -> Tuple[str, str, str]:
        url = f"https://www.douban.com/search?cat=1002&q={title}"
        print(f"请求URL: {url}")
        try:
            response = self.session.get(url, headers=self.headers, timeout=self.REQUEST_TIMEOUT)
        except requests.RequestException:
            logger.error(f"搜索 {title} 失败：网络错误")
            return None, None, None
        if response is None or response.status_code != 200:
            logger.error(f"搜索 {title} 失败：HTTP {response.status_code if response is not None else '无响应'}")
            return None, None, None
        self._sync_response_ck(response)
        soup = BeautifulSoup(response.text, 'html.parser')
        title_divs = soup.find_all("div", class_="title")
        subject_items = []
        for div in title_divs:
            item = {}
            a_tag = div.find_all("a")[0]
            item["title"] = a_tag.string.strip()
            if len(div.find_all(class_="subject-cast")) == 0:
                continue
            span_tag = div.find_all(class_="subject-cast")[0]
            year = span_tag.string[-4:]
            if year.isdigit():
                item["year"] = year
            rating_nums = div.find_all(class_="rating_nums")
            if rating_nums:
                item["rating_nums"] = rating_nums[0].string
            else:
                item["rating_nums"] = "0"
            link = unquote(a_tag["href"])
            if "subject/" in link:
                pattern = r"subject/(\d+)/"
                match = re.search(pattern, link)
                if match:
                    item["subject_id"] = match.group(1)
            subject_items.append(item)
        if not subject_items:
            print(f"找不到 {title} 相关条目")
            return None, None, None
        for subject_item in subject_items:
            print(f"找到: {subject_item['title']} {subject_item['subject_id']} 评分: {subject_item['rating_nums']}")
            return subject_item["title"], subject_item["subject_id"], subject_item["rating_nums"]
        return None, None, None

    def set_watching_status(self, subject_id: str, status: str = "do", private: bool = True) -> bool:
        if not self.is_ready():
            return False
        headers = {**self.headers,
                   "Referer": f"https://movie.douban.com/subject/{subject_id}/",
                   "Origin": "https://movie.douban.com"}
        data_json = {
            "ck": self.ck,
            "interest": status,
            "rating": "",
            "foldcollect": "U",
            "tags": "",
            "comment": ""
        }
        if private:
            data_json["private"] = "on"
        try:
            response = self.session.post(
                url=f"https://movie.douban.com/j/subject/{subject_id}/interest",
                headers=headers, data=data_json, timeout=self.REQUEST_TIMEOUT, allow_redirects=False)
        except requests.RequestException:
            logger.error(f"豆瓣状态提交失败：douban_id={subject_id}，网络错误")
            return False
        # Response is falsey on 4xx/5xx: do not swallow the authentication cause.
        if response is None:
            logger.error(f"豆瓣状态提交失败：douban_id={subject_id}，无响应")
            return False
        if self._auth_rejected(response):
            return False
        if response.status_code != 200:
            logger.error(f"豆瓣状态提交失败：douban_id={subject_id}，HTTP {response.status_code}")
            return False
        self._sync_response_ck(response)
        try:
            payload = response.json()
        except ValueError:
            logger.error(f"豆瓣状态提交失败：douban_id={subject_id}，响应不是JSON")
            return False
        ret = payload.get('r') if isinstance(payload, dict) else None
        if type(ret) is int and ret == 0:
            return True
        logger.error(f"豆瓣状态提交失败：douban_id={subject_id}，业务响应未明确成功")
        return False


if __name__ == "__main__":
    doubanHelper = DoubanHelper()
    subject_title, subject_id, score = doubanHelper.get_subject_id("火线 第 3 季")
    logger.info(f"subject_title: {subject_title}, subject_id: {subject_id}, score: {score}")
    doubanHelper.set_watching_status(subject_id=subject_id, status="do", private=True)
