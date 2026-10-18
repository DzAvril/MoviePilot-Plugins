"""Periodic, resumable inspection and conservative subtitle supplementation."""
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time

from .library import chinese_label, inspect_media, library_files, media_key, media_metadata
from .subtitles import SubtitleError


def match_score(metadata, path, title, movie='', imdb_id=''):
    """Require media identity and, for series, an explicit exact episode."""
    name = str(title)
    norm = lambda value: re.sub(r'[^\w\u4e00-\u9fff]', '', str(value)).lower()
    imdb = metadata.get('imdb_id')
    if imdb and imdb_id:
        if imdb != imdb_id:return -1
    else:
        expected = norm(metadata.get('title'))
        if not expected or expected not in norm(movie + ' ' + name):return -1
        year = str(metadata.get('year') or '')
        if not year or year not in name + ' ' + movie:return -1
    if metadata.get('episode') is not None:
        episode = re.search(r'(?i)S(\d{1,2})E(\d{1,3})(?!\d|[ ._-]?E\d)', name)
        if not episode or (int(episode[1]), int(episode[2])) != (metadata['season'], metadata['episode']):return -1
    elif re.search(r'(?i)S\d{1,2}E\d', name):return -1
    # Conflicting editions can have different timing even for the same IMDb ID.
    for edition in ('extended', 'director', 'theatrical', '加长', '导演剪辑'):
        if (edition in name.lower()) != (edition in str(path).lower()):return -1
    score = 20 if chinese_label(name) else 0
    for source in ('bluray', 'web-dl', 'webrip', 'hdtv', 'remux', '2160p', '1080p', '720p'):
        if source in str(path).lower() and source in name.lower():score += 3
    if '.chs.' in name.lower() or '简中' in name:score += 2
    return score


def write_sidecar(media, subtitle):
    """Atomic no-replace publish: an existing subtitle is never overwritten."""
    media, subtitle = Path(media), Path(subtitle)
    target = media.with_name(media.stem + '.zh.zvideo' + subtitle.suffix.lower())
    data = subtitle.read_bytes()
    fd, temp = tempfile.mkstemp(prefix='.zvideo-sub-', dir=media.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data);handle.flush();os.fsync(handle.fileno())
        os.chmod(temp, 0o644)
        os.link(temp, target, follow_symlinks=False)
    except FileExistsError:
        raise SubtitleError('同名字幕已存在，已保留原文件') from None
    finally:
        try:os.unlink(temp)
        except OSError:pass
    return target


class SubtitleAutomation:
    def __init__(self, root, service, roots, config, notice=None, language_resolver=None):
        self.root = Path(root);self.service = service;self.roots = list(roots);self.config = dict(config);self.notice = notice;self.language_resolver = language_resolver
        self._lock = threading.Lock();self._stop = threading.Event();self._thread = None
        self.state_path = self.root / 'subtitle-library.json'
        try:
            data = json.loads(self.state_path.read_text())
            self.data = data if isinstance(data, dict) and isinstance(data.get('items'), dict) else {}
        except (OSError, ValueError):self.data = {}
        self.data.setdefault('items', {});self.data.setdefault('cursor', '');self.data.setdefault('languages', {})
        if language_resolver:
            for item in self.data['items'].values():
                if item.get('state') == 'missing' and not item.get('original_language'):
                    item.update(state='unknown', reason='等待重新核对 TMDB 原始语言')
        self.progress = {'running':False, 'checked':0, 'downloaded':0}

    def snapshot(self, keyword='', state='all', page=1, page_size=20):
        if not isinstance(keyword,str) or len(keyword)>200 or any(ord(c)<32 for c in keyword):
            return {'success':False,'message':'请输入不超过 200 个字符的影视名称'}
        if state not in {'all','present','missing','unknown','excluded'}:
            return {'success':False,'message':'检查状态无效'}
        keyword = keyword.strip()
        items = [dict(i) for i in self.data['items'].values() if self.matches_keyword(i,keyword)]
        counts = {state:sum(i.get('state') == state for i in items) for state in ('present','missing','unknown','excluded')}
        scoped_total = len(items)
        if state!='all':items = [i for i in items if i.get('state')==state]
        items.sort(key=lambda i:(-i.get('checked_at',0),i['path']))
        page_size = max(1,min(200,int(page_size)));pages = max(1,(len(items)+page_size-1)//page_size)
        page = max(1,min(pages,int(page)))
        task = dict(self.progress if self.progress['running'] else self.data.get('last_task',self.progress))
        return {'success':True, **self.progress, 'auto_enabled':bool(self.config.get('subtitle_auto')), 'cron':self.config.get('subtitle_cron','*/30 * * * *'),
            'roots':self.roots, 'counts':counts, 'total_indexed':len(self.data['items']), 'scoped_total':scoped_total,
            'batch_size':max(1,min(100,int(self.config.get('subtitle_batch',25)))),
            'total':len(items),'page':page,'pages':pages,'page_size':page_size,'keyword':keyword,'state':state,'task':task,
            'last_run':self.data.get('last_run'), 'last_message':self.data.get('last_message',''),
            'items':items[(page-1)*page_size:page*page_size]}

    @staticmethod
    def matches_keyword(item, keyword):
        return not keyword or keyword.casefold() in (str(item.get('title',''))+' '+str(item.get('path',''))).casefold()

    def destinations(self, tmdb_id, media_type, season=-1, episode=-1):
        items = [dict(i) for i in self.data['items'].values() if str(i.get('tmdb_id'))==str(tmdb_id)
            and (i.get('season') is not None)==(media_type=='tv')
            and (season<0 or i.get('season')==season) and (episode<0 or i.get('episode')==episode)]
        return {'success':True,'items':sorted(items,key=lambda i:i['path'])}

    def _save(self):
        self.root.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.subtitle-state-', dir=self.root)
        try:
            with os.fdopen(fd,'w') as h:json.dump(self.data, h, ensure_ascii=False)
            os.replace(name, self.state_path)
        finally:
            if os.path.exists(name):os.unlink(name)

    def start(self, download=False, keyword=""):
        if not isinstance(keyword,str) or len(keyword)>200 or any(ord(c)<32 for c in keyword):return {'success':False,'message':'媒体筛选名称无效'}
        if not self._lock.acquire(blocking=False):return {'success':False, 'message':'已有媒体检查正在运行'}
        self.progress = {'running':True, 'checked':0, 'downloaded':0, 'mode':'补全' if download else '检查',
            'keyword':keyword.strip(),'matched':0,'planned':0,'started_at':time.time(),'current_title':'','error':''}
        self._thread = threading.Thread(target=self._run, args=(download, keyword.strip()), daemon=True);self._thread.start()
        return {'success':True, 'message':'已开始后台补全' if download else '已开始后台检查'}

    def stop(self):self._stop.set()

    def target(self, identifier):
        item = self.data['items'].get(identifier)
        if not item:raise SubtitleError('请先检查媒体库，再选择要保存字幕的媒体')
        path = Path(item['path'])
        if not path.is_file() or path.is_symlink() or not any(path.resolve().is_relative_to(Path(r).resolve()) for r in self.roots):
            raise SubtitleError('媒体已移动或不在本地入库目录中')
        return path

    def manual_download(self, file_id, media_id=''):
        try:
            result = self.service.fetch(file_id, self.config.get('subtitle_nas_cache',''))
            if not media_id:return {'success':True, 'ticket':result['ticket'], 'name':result['name']}
            media = self.target(media_id)
            if result['chinese'] is not True:raise SubtitleError('无法确认字幕正文为中文，已阻止自动标注中文；可选择下载到本机查看')
            if inspect_media(media)['state'] == 'present':raise SubtitleError('媒体已有中文字幕，已保留现有字幕')
            if self._stop.is_set():raise SubtitleError('插件正在停止，请稍后重试')
            saved = write_sidecar(media, result['path'])
            self.data['items'][media_id].update(state='present', reason='手动下载中文外挂字幕', saved=saved.name, checked_at=time.time())
            self._save()
            return {'success':True, 'message':'已保存到媒体旁边：'+saved.name}
        except (SubtitleError, OSError) as error:
            return {'success':False, 'message':str(error) if isinstance(error,SubtitleError) else '字幕保存失败，请检查目录写入权限'}

    def _auto_download(self, item):
        media = self.target(item['id']);before = media.stat();metadata = media_metadata(media)
        found = self.service.search(metadata['title'], metadata['imdb_id'])
        if not found.get('success'):raise SubtitleError(found.get('message','字幕搜索失败'))
        candidates = []
        for c in found['candidates']:
            if not c['download_available']:continue
            constraint = dict(metadata)
            if Path(c['title']).suffix.lower() not in {'.srt','.ass','.ssa','.vtt'} and not re.search(r'(?i)S\d{1,2}E\d', c['title']):
                constraint['episode'] = None
            score = match_score(constraint, media, c['title'], c['movie'], c['imdb_id'])
            if score >= 0:candidates.append((score,c))
        candidates.sort(key=lambda v:v[0], reverse=True)
        for _, candidate in candidates[:3]:
            preview = self.service.preview(candidate['id'])
            if not preview.get('success'):raise SubtitleError(preview.get('message','字幕预览失败'))
            files = [(match_score(metadata, media, f['title'], candidate['movie'], candidate['imdb_id']), f) for f in preview['files']]
            files = sorted((v for v in files if v[0] >= 0 and v[1]['chinese_label']), key=lambda v:v[0], reverse=True)
            for _, chosen in files[:2]:
                result = self.service.fetch(chosen['id'], self.config.get('subtitle_nas_cache',''))
                if result['chinese'] is not True:continue
                after = media.stat()
                if (before.st_size,before.st_mtime_ns) != (after.st_size,after.st_mtime_ns):raise SubtitleError('媒体文件正在变化，延后处理')
                if self._stop.is_set():return False
                if inspect_media(media)['state'] != 'missing':return False
                saved = write_sidecar(media, result['path'])
                item.update(state='present', reason='自动下载中文外挂字幕', saved=saved.name, subtitle=chosen['title'])
                return True
        item['reason'] = '未找到可确认影片身份、季集和中文内容的字幕，等待手动选择'
        return False

    def original_language(self, metadata):
        language = str(metadata.get('original_language') or '').lower().strip()
        if language:return language
        key = ('tv:' if metadata.get('season') is not None else 'movie:') + str(metadata.get('tmdb_id') or '')
        if not metadata.get('tmdb_id') or not self.language_resolver:return ''
        cached = self.data['languages'].get(key)
        if cached and time.time() - cached['time'] < (86400 * 30 if cached['language'] else 3600):return cached['language']
        try:language = str(self.language_resolver(metadata) or '').lower().strip()
        except Exception:language = ''
        self.data['languages'][key] = {'language':language, 'time':time.time()}
        return language

    def _run(self, download, keyword=""):
        lock = None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            lock = (self.root / 'subtitle-automation.lock').open('a')
            try:fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:raise SubtitleError('上次字幕任务仍在结束，请稍后重试')
            files = sorted(library_files(self.roots), key=str)
            current = {media_key(p) for p in files}
            self.data['items'] = {k:v for k,v in self.data['items'].items() if k in current}
            if keyword:files = [p for p in files if self.matches_keyword({**self.data['items'].get(media_key(p),{}),'path':str(p)},keyword)]
            cursor = self.data.get('cursor','')
            # New arrivals first, then the least recently checked files. New
            # media do not wait for a full rotation of an existing large library.
            files.sort(key=lambda p:(media_key(p) in self.data['items'], self.data['items'].get(media_key(p),{}).get('checked_at',-p.stat().st_mtime)))
            limit = max(1,min(100,int(self.config.get('subtitle_batch',25))))
            self.progress.update(keyword=keyword,matched=len(files),planned=min(len(files),limit))
            auth_notified = bool(self.data.get('auth_notified'));attempts = 0
            for media in files[:limit]:
                if self._stop.is_set():break
                key = media_key(media);old = self.data['items'].get(key,{})
                metadata = media_metadata(media);language = self.original_language(metadata)
                self.progress['current_title'] = metadata['title']
                if language in {'zh','zho','chi','cmn','yue','cn'} or language.startswith('zh-'):
                    inspection = {'state':'excluded', 'reason':'TMDB 原始语言为中文，已跳过自动字幕搜索'}
                elif not language and self.language_resolver:
                    inspection = {'state':'unknown', 'reason':'未能获得 TMDB 原始语言，等待人工确认；不会自动搜索'}
                else:inspection = inspect_media(media)
                item = {'id':key, 'path':str(media), **metadata, **inspection, 'original_language':language, 'checked_at':time.time()}
                if old.get('attempt_at'):item['attempt_at'] = old['attempt_at']
                self.data['items'][key] = item;self.data['cursor'] = str(media);self.progress['checked'] += 1
                if download and item['state'] == 'missing' and attempts < 5 and time.time() - old.get('attempt_at',0) >= 86400:
                    item['attempt_at'] = time.time();attempts += 1
                    try:
                        if self._auto_download(item):self.progress['downloaded'] += 1
                        self.data['auth_notified'] = False
                    except SubtitleError as error:
                        item['reason'] = str(error)
                        if self.service.auth_failed:
                            self.data['cursor'] = cursor
                            item.pop('attempt_at',None)
                            if not auth_notified and self.notice:self.notice('极影视字幕授权失效，自动下载已暂停。请打开插件页面重新授权，无需终端。')
                            self.data['auth_notified'] = True;break
                    except OSError:item['reason'] = '文件无法读取或字幕保存失败，请检查权限'
                self._save()
            self.data['last_run'] = time.time()
            self.data['last_message'] = '本轮检查 %s 个媒体，下载 %s 份字幕%s' % (self.progress['checked'],self.progress['downloaded'], '；媒体筛选：'+keyword if keyword else '；分批轮询全部本地影视库')
            self._save()
        except Exception as error:
            self.data['last_message'] = str(error) if isinstance(error,SubtitleError) else '本轮检查失败，请检查本地影视库与探测工具'
            self.progress['error'] = self.data['last_message']
        finally:
            self.progress['running'] = False
            self.progress['finished_at'] = time.time()
            self.data['last_task'] = dict(self.progress)
            try:self._save()
            except OSError:pass
            if lock:lock.close()
            self._lock.release()
