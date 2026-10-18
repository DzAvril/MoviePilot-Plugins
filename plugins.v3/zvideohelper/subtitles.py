"""NAS subtitle adapter. Only the original CLI owns OAuth credentials."""

import hashlib
from html import unescape
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import secrets
import tempfile

from .library import TEXT, chinese_text, chinese_label, decode_text
from .authorization import BrowserAuthorization
from .selection import selected_candidates, episode_matches, may_contain_episode


class SubtitleError(Exception):
    pass


def query_plan(keyword="", imdb_id=""):
    keyword, imdb_id = str(keyword or "").strip(), str(imdb_id or "").strip()
    if any(len(value) > 200 or any(ord(char) < 32 for char in value) for value in (keyword, imdb_id)):
        raise SubtitleError("搜索词需为 1–200 个字符")
    if imdb_id and not re.fullmatch(r"tt\d{6,12}", imdb_id):
        raise SubtitleError("IMDb ID 格式应为 tt 开头的数字")
    queries = list(dict.fromkeys(value for value in (imdb_id, keyword) if value))
    if not queries:
        raise SubtitleError("请输入片名或 IMDb ID")
    return queries


def project_candidates(data):
    """Do not send provider download locators to the browser or plugin history."""
    groups = data.get("subs", []) if isinstance(data, dict) else []
    if not isinstance(groups, list):
        raise SubtitleError("字幕服务返回结构异常，请稍后重试")
    candidates, seen = [], set()
    for group in groups:
        if not isinstance(group, dict) or not isinstance(group.get("subs"), list):
            continue
        for item in group["subs"]:
            if not isinstance(item, dict) or not isinstance(item.get("sub_title"), str) or not item["sub_title"].strip():
                continue
            subtitle_id = str(item.get("sub_id") or "")
            if not subtitle_id:
                continue
            title = unescape(item["sub_title"])
            key = hashlib.sha256((subtitle_id + "\0" + title).encode()).hexdigest()[:20]
            if key in seen:
                continue
            seen.add(key)
            suffix = Path(title).suffix.lower().lstrip(".")
            candidates.append({"id": key, "subtitle_id": subtitle_id, "title": title, "chinese_label":chinese_label(title),
                "movie": str(group.get("name") or ""), "imdb_id": str(group.get("imdb") or ""),
                "size": str(item.get("size") or ""),
                "format": suffix.upper() if suffix in {"ass", "ssa", "srt", "vtt", "zip", "rar", "7z", "sup", "idx", "sub"} else "未标注",
                "download_available": bool(item.get("download_url"))})
    return candidates


class SubtitleService:
    def __init__(self, root, run=None):
        self.root = Path(root)
        self._run_override = run
        self._lock = threading.Lock()
        self._cache = {}
        self._sources = {}
        self._downloads = {}
        self._preview_cache = {}
        self._archive_names = {}
        self._episode_cache = {}
        self._episode_lock = threading.Lock()
        self.authorization = BrowserAuthorization(self.root)
        self.auth_failed = False

    def _run(self, args, timeout=150, payload=None):
        if self._run_override:
            return self._run_override(args)
        native = self.root / "zspace-cli"
        if not native.is_file() or not os.access(native, os.X_OK):
            raise SubtitleError("NAS 字幕授权工具尚未安装，请先完成插件初始化")
        env = dict(os.environ, ZSPACE_CLI_HOME=str(self.root / "profile"))
        try:
            result = subprocess.run(args, input=json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None, capture_output=True, timeout=timeout, env=env)
            document = json.loads(result.stdout if result.returncode == 0 else result.stderr)
        except subprocess.TimeoutExpired:
            raise SubtitleError("字幕搜索超时，请稍后重试") from None
        except (OSError, ValueError):
            raise SubtitleError("字幕授权工具暂不可用，请检查 NAS 授权状态") from None
        if not isinstance(document, dict) or result.returncode or not document.get("ok"):
            code = document.get("error", {}).get("code", "") if isinstance(document, dict) else ""
            if code in {"E_NOT_LOGGED_IN", "E_OAUTH", "E_CREDENTIAL", "E_AUTH"} or any(s in str(document.get("error", {}).get("message", "")) for s in ("N001208", "token失效", "invalid_grant", "401")):
                self.auth_failed = True
                raise SubtitleError("授权已失效，请在插件页面重新授权；自动下载已暂停")
            raise SubtitleError("字幕服务请求失败，请检查 NAS 授权和网络连接后重试")
        if "status" not in args:
            self.auth_failed = False
        return document

    def status(self):
        native = self.root / "zspace-cli"
        if not self._run_override and (not native.is_file() or not os.access(native, os.X_OK)):
            return {"installed": False, "authorized": False, "message": "NAS 字幕授权工具尚未安装"}
        try:
            result = self._run([str(native), "--profile", "zvideohelper", "status"], timeout=20)
            authorized = bool(result.get("data", {}).get("logged_in"))
            return {"installed": True, "authorized": authorized and not self.auth_failed,
                    "message": "NAS 已授权，临期自动续期" if authorized and not self.auth_failed else "请在插件页面完成极空间授权"}
        except SubtitleError as error:
            return {"installed": True, "authorized": False, "message": str(error)}

    def search(self, keyword="", imdb_id=""):
        if self.authorization.active():
            return {"success":False, "message":"正在进行授权，请完成后重试"}
        try:
            queries = query_plan(keyword, imdb_id)
        except SubtitleError as error:
            return {"success": False, "message": str(error)}
        cache_key = tuple(queries)
        cached = self._cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < 300:
            return {**cached[1], "cached": True}
        if not self._lock.acquire(blocking=False):
            return {"success": False, "message": "已有字幕搜索正在进行，请稍后重试"}
        try:
            attempts, candidates = [], []
            for query in queries:
                result = self._run([sys.executable, str(Path(__file__).with_name("subtitle_cli.py")),
                    "--original-bin", str(self.root / "zspace-cli"), "--profile", "zvideohelper", "--timeout", "25",
                    "media", "subtitle-search", "--dedicated-profile", "--params", json.dumps({"q": query}, ensure_ascii=False)])
                attempts.append(query)
                data = result.get("data", {})
                candidates = project_candidates(data)
                self._remember(data, candidates)
                if candidates:
                    break
            response = {"success": True, "count": len(candidates), "candidates": candidates,
                        "queries": attempts, "cached": False,
                        "message": "" if candidates else "未找到字幕，可尝试中文片名、原名或 IMDb ID"}
            if len(self._cache) >= 8:
                self._cache.clear()
            self._cache[cache_key] = (time.monotonic(), response)
            return response
        except SubtitleError as error:
            return {"success": False, "message": str(error)}
        finally:
            self._lock.release()


    def search_selected(self, media):
        queries = list(dict.fromkeys(q for q in (media.get('imdb_id'), media.get('title'), media.get('original_title')) if q))
        attempts = []
        for query in queries:
            response = self.search(imdb_id=query) if re.fullmatch(r"tt\d{6,12}", query) else self.search(keyword=query)
            attempts.extend(response.get('queries',[]))
            if not response.get('success'):return {**response, 'selected_media':media}
            candidates = selected_candidates(response.get('candidates',[]),media)
            if candidates:
                return {**response, 'selected_media':media, 'candidates':candidates, 'count':len(candidates), 'queries':attempts}
        return {'success':True, 'selected_media':media, 'candidates':[], 'count':0, 'queries':attempts,
            'message':'未找到能确认属于所选作品的字幕；可核对年份或选择其他作品'}

    def search_episode(self, media, season, episode):
        key = (media['id'],season,episode)
        cached = self._episode_cache.get(key)
        if cached and time.monotonic()-cached[0] < 300 and all(c['id'] in self._sources for c in cached[1]['candidates']):
            return {**cached[1], 'cached':True}
        if not self._episode_lock.acquire(blocking=False):return {'success':False,'message':'已有单集字幕查询正在进行，请稍后重试'}
        try:
            response = self.search_selected(media)
            if not response.get('success'):return response
            matched, seen = [], set();checked = failed = 0;started = time.monotonic()
            for candidate in response.get('candidates',[]):
                if not may_contain_episode(candidate['title'],season,episode):continue
                if Path(candidate['title']).suffix.lower() in TEXT:
                    if episode_matches(candidate['title'],season,episode):matched.append(candidate)
                    continue
                if checked >= 20 or time.monotonic()-started > 90:
                    failed += 1;continue
                preview = self.preview(candidate['id'],season,episode);checked += not preview.get('cached',False)
                if not preview.get('success'):
                    if self.auth_failed:return preview
                    failed += 1;continue
                for file in preview.get('files',[]):
                    if not episode_matches(file['title'],season,episode,parent=candidate['title']):continue
                    source = self._source(file['id']);identity = (source['sub_id'],file['title'])
                    if identity in seen:continue
                    seen.add(identity)
                    source.update(episode_season=season,episode_number=episode,episode_parent=candidate['title'])
                    matched.append({**candidate,'id':file['id'],'title':file['title'],
                        'chinese_label':file['chinese_label'],
                        'format':Path(file['title']).suffix.lstrip('.').upper(),'archive_title':candidate['title']})
            result = {**response,'candidates':matched,'count':len(matched),'season':season,'episode':episode,
                'checked_archives':checked,'archive_warning':f'{failed} 个字幕包未能完成核对，未混入结果；可再次查询重试' if failed else '',
                'message':'' if matched else '未找到能确认属于所选集的字幕；季集不明的条目未展示'}
            if not failed:
                if len(self._episode_cache)>=16:self._episode_cache.clear()
                self._episode_cache[key]=(time.monotonic(),result)
            return result
        except SubtitleError as error:return {'success':False,'message':str(error)}
        finally:self._episode_lock.release()

    def _remember(self, data, candidates):
        lookup = {(str(i.get("sub_id") or ""), unescape(str(i.get("sub_title") or ""))): (i, g)
                  for g in data.get("subs", []) if isinstance(g, dict) for i in g.get("subs", []) if isinstance(i, dict)}
        now = time.monotonic()
        self._sources = {k:v for k,v in self._sources.items() if now - v[0] < 900}
        if len(self._sources) > 1000:self._sources.clear()
        for c in candidates:
            item, group = lookup[(c["subtitle_id"], c["title"])]
            self._sources[c["id"]] = (now, {"sub_id":str(item["sub_id"]), "download_url":item.get("download_url", ""),
                "sub_title":c["title"], "imdb_id":str(group.get("imdb") or ""), "movie":str(group.get("name") or "")})

    def _source(self, identifier):
        entry = self._sources.get(identifier)
        if not entry or time.monotonic() - entry[0] >= 900:
            raise SubtitleError("搜索结果已过期，请重新搜索")
        return entry[1]

    def _request(self, operation, params):
        if self.authorization.active():raise SubtitleError("正在授权，请完成后重试")
        return self._run([sys.executable, str(Path(__file__).with_name("subtitle_cli.py")), "--original-bin", str(self.root / "zspace-cli"),
                          "nas-subtitle-request", operation], payload=params).get("data", {})

    def preview(self, identifier, season=None, episode=None):
        cache_key = identifier if season is None else (identifier,season,episode)
        cached = self._preview_cache.get(cache_key)
        if cached and time.monotonic()-cached[0] < 300 and all(f['id'] in self._sources for f in cached[1]['files']):
            return {**cached[1], 'cached':True}
        if not self._lock.acquire(blocking=False):return {"success":False, "message":"字幕服务正忙，请稍后重试"}
        try:
            source = self._source(identifier)
            content_cached = False
            if Path(source["sub_title"]).suffix.lower() in TEXT:
                names = [source["sub_title"]]
                content_cached = True
            else:
                archive = self._archive_names.get(identifier)
                if archive and time.monotonic()-archive[0]<300:
                    names = archive[1]
                    content_cached = True
                else:
                    data = self._request("preview", {k:source[k] for k in ("sub_id", "download_url")})
                    names = [i["sub_title"] for i in data.get("subs", []) if isinstance(i, dict) and isinstance(i.get("sub_title"), str) and Path(i["sub_title"]).suffix.lower() in TEXT]
                    if sum(map(len,names))<=250000:
                        if len(self._archive_names)>=32:self._archive_names.clear()
                        self._archive_names[identifier]=(time.monotonic(),names)
            if season is not None:
                names = [name for name in names if episode_matches(name,season,episode,parent=source['sub_title'])]
            if source.get('episode_number') is not None:
                names = [name for name in names if episode_matches(name,source['episode_season'],source['episode_number'],parent=source.get('episode_parent',''))]
            files = []
            for name in names[:300]:
                key = secrets.token_urlsafe(20)
                self._sources[key] = (time.monotonic(), {**source, "sub_title":name,
                    **({'episode_season':season,'episode_number':episode,'episode_parent':source['sub_title']} if season is not None else {})})
                files.append({"id":key, "title":name, "chinese_label":chinese_label(name)})
            result = {"success":True, "files":files, "cached":content_cached, "message":"" if files else "压缩包中没有支持的 SRT / ASS / SSA / VTT 文本字幕"}
            if len(self._preview_cache)>=64:self._preview_cache.clear()
            self._preview_cache[cache_key]=(time.monotonic(),result)
            return result
        except SubtitleError as error:return {"success":False, "message":str(error)}
        finally:self._lock.release()

    def _nas_stage(self, path, override=""):
        """Translate only our staging directory, using the kernel bind mount map."""
        if not Path(path).is_relative_to(self.root / 'staging'):
            raise SubtitleError('字幕缓存路径超出插件 staging 目录')
        if override:
            base = str(override).rstrip('/')
            if not base.startswith('/') or '..' in Path(base).parts:raise SubtitleError("NAS 缓存路径无效")
            return base + '/' + str(Path(path).relative_to(self.root / 'staging'))
        try:
            mappings = []
            for line in Path('/proc/self/mountinfo').read_text().splitlines():
                before, after = line.split(' - ', 1);parts = before.split();fs = after.split()[0]
                decode = lambda value: re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), value)
                mount, root = Path(decode(parts[4])), decode(parts[3])
                if fs == 'zfuse.zfsv3' and Path(path).is_relative_to(mount):
                    mappings.append((len(str(mount)), '/tmp/zfsv3' + root.rstrip('/') + '/' + str(Path(path).relative_to(mount))))
            if mappings:return max(mappings)[1]
        except (OSError, ValueError, IndexError):pass
        raise SubtitleError("无法自动识别 NAS 缓存位置，请在设置中填写插件 staging 目录在 NAS 上的路径")

    def fetch(self, identifier, nas_cache=""):
        if not self._lock.acquire(blocking=False):raise SubtitleError("字幕服务正忙，请稍后重试")
        try:
            source = self._source(identifier)
            suffix = Path(source['sub_title']).suffix.lower()
            if suffix not in TEXT:raise SubtitleError("请先选择压缩包内的文本字幕")
            staging = self.root / 'staging';staging.mkdir(parents=True, exist_ok=True, mode=0o700)
            # Stale temporary files are ours, not media or credentials.
            for old in staging.iterdir():
                if old.is_dir() and re.fullmatch(r'[0-9a-f]{32}', old.name) and time.time() - old.stat().st_mtime > 86400:
                    import shutil
                    shutil.rmtree(old)
            import uuid
            folder = staging / uuid.uuid4().hex;folder.mkdir(mode=0o700)
            placeholder = folder / 'video.mkv';placeholder.touch(mode=0o600)
            nas_path = self._nas_stage(placeholder, nas_cache)
            self._request('download', {k:source[k] for k in ('sub_id','download_url','sub_title')} | {'file_name':nas_path, 'encrypted_path':'', 'from':''})
            files = [p for p in folder.iterdir() if p.is_file() and not p.is_symlink() and p.suffix.lower() == suffix]
            if len(files) != 1 or not 16 <= files[0].stat().st_size <= 8 * 1024 * 1024:
                raise SubtitleError("字幕未写入插件缓存，或大小超出限制")
            data = files[0].read_bytes()
            if b'<!doctype html' in data[:1000].lower() or b'<html' in data[:1000].lower():raise SubtitleError("下载返回了网页，未保存到媒体库")
            decoded = decode_text(data)
            if decoded is None or not re.search(r'(?:\d{1,2}:)?\d{2}:\d{2}[.,]\d{1,3}', decoded):
                raise SubtitleError("下载内容不是可识别的文本字幕，未保存到媒体库")
            ticket = secrets.token_urlsafe(24)
            self._downloads = {k:v for k,v in self._downloads.items() if time.monotonic() - v[0] < 900}
            self._downloads[ticket] = (time.monotonic(), files[0], Path(source['sub_title']).name)
            return {'ticket':ticket, 'path':files[0], 'name':Path(source['sub_title']).name, 'chinese':chinese_text(data, suffix)}
        finally:self._lock.release()

    def download_file(self, ticket):
        entry = self._downloads.get(ticket)
        if not entry or time.monotonic() - entry[0] >= 900 or not entry[1].is_file():raise SubtitleError("下载链接已过期，请重新下载")
        return entry[1], entry[2]
