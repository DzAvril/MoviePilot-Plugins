"""Periodic, resumable inspection and conservative subtitle supplementation."""
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time

from .library import chinese_label, inspect_media, library_files, media_key, media_metadata, media_fingerprint, resolve_roots, external_subtitle_inventory, missing_subtitle_reason, SUBTITLE_EVIDENCE_VERSION
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
    target = media.with_name(media.stem + '.zh' + subtitle.suffix.lower())
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
        self.root = Path(root);self.service = service;self.automatic_roots = list(roots);self.config = dict(config);self.notice = notice;self.language_resolver = language_resolver
        self._lock = threading.Lock();self._data_lock = threading.RLock();self._stop = threading.Event();self._cancel = threading.Event();self._thread = None
        self.roots,self.root_errors = resolve_roots(self.automatic_roots,self.config.get('subtitle_library_paths',''))
        self.state_path = self.root / 'subtitle-library.json'
        try:
            data = json.loads(self.state_path.read_text())
            self.data = data if isinstance(data, dict) and isinstance(data.get('items'), dict) else {}
        except (OSError, ValueError):self.data = {}
        self.data.setdefault('items', {});self.data.setdefault('cursor', '');self.data.setdefault('languages', {})
        self.data.setdefault('manual_labels', {})
        if language_resolver:
            for item in self.data['items'].values():
                if item.get('state') == 'missing' and not item.get('original_language'):
                    item.update(state='unknown', reason='等待重新核对 TMDB 原始语言')
        self.progress = {'running':False, 'checked':0, 'downloaded':0}

    def snapshot(self, keyword='', state='all', page=1, page_size=20):
        if not isinstance(keyword,str) or len(keyword)>200 or any(ord(c)<32 for c in keyword):
            return {'success':False,'message':'请输入不超过 200 个字符的影视名称'}
        if state not in {'all','pending','present','missing','unknown','excluded'}:
            return {'success':False,'message':'检查状态无效'}
        keyword = keyword.strip()
        with self._data_lock:all_items = [self.effective_item(i) for i in self.data['items'].values()]
        items = [i for i in all_items if self.matches_keyword(i,keyword)]
        counts = {state:sum(i.get('state') == state for i in items) for state in ('pending','present','missing','unknown','excluded')}
        scoped_total = len(items)
        if state!='all':items = [i for i in items if i.get('state')==state]
        items.sort(key=lambda i:(-i.get('checked_at',0),i['path']))
        page_size = max(1,min(200,int(page_size)));pages = max(1,(len(items)+page_size-1)//page_size)
        page = max(1,min(pages,int(page)))
        task = dict(self.progress if self.progress['running'] else self.data.get('last_task',self.progress))
        return {'success':True, **self.progress, 'auto_enabled':bool(self.config.get('subtitle_auto')), 'cron':self.config.get('subtitle_cron','*/30 * * * *'),
            'roots':self.roots, 'root_source':'custom' if isinstance(self.config.get('subtitle_library_paths'),str) and self.config['subtitle_library_paths'].strip() else 'moviepilot',
            'root_errors':self.root_errors,'counts':counts, 'total_indexed':len(all_items), 'scoped_total':scoped_total,
            'coverage':{'discovered':len(all_items),'checked':sum(i.get('state')!='pending' for i in all_items),
                'pending':sum(i.get('state')=='pending' for i in all_items),'last_inventory':self.data.get('last_inventory'),
                'baseline_complete':bool(not self.root_errors and self.data.get('baseline_complete') and self.data.get('catalog_roots')==self.roots
                    and all(i.get('fingerprint') and i.get('state')!='pending' for i in all_items))},
            'download_limit':max(1,min(20,int(self.config.get('subtitle_download_limit',5)))),
            'total':len(items),'page':page,'pages':pages,'page_size':page_size,'keyword':keyword,'state':state,'task':task,
            'last_run':self.data.get('last_run'), 'last_message':self.data.get('last_message',''),
            'items':items[(page-1)*page_size:page*page_size]}

    @staticmethod
    def matches_keyword(item, keyword):
        return not keyword or keyword.casefold() in (str(item.get('title',''))+' '+str(item.get('path',''))).casefold()

    def effective_item(self, item):
        result=dict(item)
        with self._data_lock:label=dict(self.data['manual_labels'].get(item.get('id'),{}))
        if label.get('state') in {'present','missing'}:
            result.update(detected_state=item['state'],detected_reason=item.get('reason',''),
                manual_state=label['state'],manual_at=label['updated_at'],state=label['state'],
                reason='人工确认已有中文（含硬字幕），已跳过自动补全' if label['state']=='present' else '人工确认缺少中文字幕')
        return result

    @staticmethod
    def video_signature(path):
        value=Path(path).stat()
        return [value.st_size,value.st_mtime_ns,value.st_ino]

    def mark(self, identifier, state):
        if state not in {'present','missing','auto'}:return {'success':False,'message':'人工标记无效'}
        try:
            media=self.target(identifier)
            with self._data_lock:
                if self.data['items'][identifier]['state']=='pending':raise SubtitleError('请等待此文件检查完成后再确认')
                if state=='auto':
                    self.data['manual_labels'].pop(identifier,None)
                    self.data['items'][identifier].pop('attempt_at',None)
                else:
                    self.data['manual_labels'][identifier]={'state':state,'updated_at':time.time(),'video_signature':self.video_signature(media)}
                    if state=='missing':self.data['items'][identifier].pop('attempt_at',None)
                self._save();item=self.effective_item(self.data['items'][identifier])
            return {'success':True,'item':item,'message':'已恢复最近一次自动判断，可强制重检更新结果' if state=='auto' else '人工确认已保存，后续扫描会保留'}
        except (SubtitleError,OSError) as error:return {'success':False,'message':str(error) if isinstance(error,SubtitleError) else '标记保存失败，请检查媒体和插件目录权限'}

    def manual_state(self, identifier):
        with self._data_lock:return self.data['manual_labels'].get(identifier,{}).get('state')

    def destinations(self, tmdb_id, media_type, season=-1, episode=-1):
        items = [self.effective_item(i) for i in self.data['items'].values() if str(i.get('tmdb_id'))==str(tmdb_id)
            and (i.get('season') is not None)==(media_type=='tv')
            and (season<0 or i.get('season')==season) and (episode<0 or i.get('episode')==episode)]
        return {'success':True,'items':sorted(items,key=lambda i:i['path'])}

    def _save(self):
        with self._data_lock:
            self.root.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='.subtitle-state-', dir=self.root)
            try:
                with os.fdopen(fd,'w') as h:json.dump(self.data, h, ensure_ascii=False)
                os.replace(name, self.state_path)
            finally:
                if os.path.exists(name):os.unlink(name)

    def start(self, download=False, keyword="", force=False):
        if not isinstance(keyword,str) or len(keyword)>200 or any(ord(c)<32 for c in keyword):return {'success':False,'message':'媒体筛选名称无效'}
        if self._stop.is_set():return {'success':False,'message':'插件正在停止，请稍后重试'}
        self.roots,self.root_errors = resolve_roots(self.automatic_roots,self.config.get('subtitle_library_paths',''))
        if self.root_errors:return {'success':False,'message':'；'.join(self.root_errors)}
        if not self._lock.acquire(blocking=False):return {'success':False, 'message':'已有媒体检查正在运行'}
        self._cancel.clear()
        self.progress = {'running':True, 'checked':0, 'downloaded':0, 'mode':'补全' if download else '检查',
            'keyword':keyword.strip(),'matched':0,'planned':0,'started_at':time.time(),'current_title':'','error':''}
        self._thread = threading.Thread(target=self._run, args=(download, keyword.strip(), force), daemon=True);self._thread.start()
        return {'success':True, 'message':'已开始后台检查与补全' if download else '已开始后台'+('强制重检' if force else '增量检查（首次会完整建索引）')}

    def stop(self):self._stop.set()

    def cancel(self):
        if not self.progress['running']:return {'success':True,'message':'当前没有检查任务'}
        self._cancel.set()
        return {'success':True,'message':'将在当前文件处理结束后停止本次任务；已完成结果会保存，下次增量检查可续扫'}

    def interrupted(self):return self._stop.is_set() or self._cancel.is_set()

    def target(self, identifier):
        item = self.data['items'].get(identifier)
        if not item:raise SubtitleError('请先检查媒体库，再选择要保存字幕的媒体')
        path = Path(item['path'])
        if not path.is_file() or path.is_symlink() or not any(path.resolve().is_relative_to(Path(r).resolve()) for r in self.roots):
            raise SubtitleError('媒体已移动或不在本地入库目录中')
        return path

    def manual_download(self, file_id, media_id=''):
        try:
            if media_id and self.manual_state(media_id)=='present':raise SubtitleError('已人工确认有中文（含硬字幕），请恢复自动判断后再保存；仍可下载到当前设备')
            result = self.service.fetch(file_id, self.config.get('subtitle_nas_cache',''))
            if not media_id:return {'success':True, 'ticket':result['ticket'], 'name':result['name']}
            media = self.target(media_id)
            if result['chinese'] is not True:raise SubtitleError('无法确认字幕正文为中文，已阻止自动标注中文；可选择下载到本机查看')
            if self.manual_state(media_id)!='missing' and inspect_media(media)['state'] == 'present':raise SubtitleError('媒体已有中文字幕，已保留现有字幕')
            if self._stop.is_set():raise SubtitleError('插件正在停止，请稍后重试')
            with self._data_lock:
                if self.manual_state(media_id)=='present':raise SubtitleError('已人工确认有中文（含硬字幕），已停止保存')
                saved = write_sidecar(media, result['path'])
                self.data['manual_labels'].pop(media_id,None)
                self.data['items'][media_id].update(state='present', reason='手动下载中文外挂字幕', saved=saved.name, checked_at=time.time(),fingerprint=media_fingerprint(media),
                    external_subtitles=external_subtitle_inventory(media),subtitle_evidence_version=SUBTITLE_EVIDENCE_VERSION)
                self._save()
            return {'success':True, 'message':'已保存到媒体旁边：'+saved.name}
        except (SubtitleError, OSError) as error:
            return {'success':False, 'message':str(error) if isinstance(error,SubtitleError) else '字幕保存失败，请检查目录写入权限'}

    def _auto_download(self, item):
        if self.manual_state(item['id'])=='present':return False
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
                if self.manual_state(item['id'])!='missing' and inspect_media(media)['state'] != 'missing':return False
                with self._data_lock:
                    if self.manual_state(item['id'])=='present':return False
                    saved = write_sidecar(media, result['path'])
                    self.data['manual_labels'].pop(item['id'],None)
                    item.update(state='present', reason='自动下载中文外挂字幕', saved=saved.name, subtitle=chosen['title'],
                        external_subtitles=external_subtitle_inventory(media),subtitle_evidence_version=SUBTITLE_EVIDENCE_VERSION)
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
        with self._data_lock:self.data['languages'][key] = {'language':language, 'time':time.time()}
        return language

    @staticmethod
    def needs_check(old, fingerprint, force=False):
        if force or old.get('state')=='pending' or old.get('fingerprint')!=fingerprint:return True
        retryable = old.get('state')=='unknown' and any(word in old.get('reason','') for word in ('TMDB','探测失败','探测超时','无法读取'))
        return retryable and time.time()-old.get('checked_at',0)>=86400

    def _checkpoint(self, force=False):
        if force or self.progress['checked']-self._checkpoint_checked>=100 or time.monotonic()-self._checkpoint_time>=10:
            with self._data_lock:
                self.data['last_task']=dict(self.progress);self._save()
            self._checkpoint_checked=self.progress['checked'];self._checkpoint_time=time.monotonic()

    def _probe_observer(self, elapsed):
        self.progress['probed']+=1
        self.progress['probe_seconds']=round(self.progress['probe_seconds']+elapsed,3)

    def _refresh_external_evidence(self, media, old):
        if old.get('state') not in {'missing','unknown'} or old.get('subtitle_evidence_version')==SUBTITLE_EVIDENCE_VERSION:return
        try:external=external_subtitle_inventory(media)
        except OSError:return
        refreshed={**old,'external_subtitles':external,'subtitle_evidence_version':SUBTITLE_EVIDENCE_VERSION}
        positive=next((f for f in external if f['chinese'] is True),None)
        if positive:refreshed.update(state='present',reason='已有中文外挂字幕',evidence=positive['name'])
        elif old['state']=='missing':
            if any(f['chinese'] is None for f in external):refreshed.update(state='unknown',reason='已发现外挂字幕，但语言无法确认；不会自动补全')
            else:refreshed['reason']=missing_subtitle_reason(external)
        with self._data_lock:self.data['items'][old['id']]=refreshed
        self.progress['evidence_refreshed']+=1

    def _inspect_one(self, media, fingerprint, old):
        metadata=media_metadata(media);self.progress['current_title']=metadata['title']
        language=self.original_language(metadata)
        if language in {'zh','zho','chi','cmn','yue','cn'} or language.startswith('zh-'):
            inspection={'state':'excluded','reason':'TMDB 原始语言为中文，已跳过自动字幕搜索'}
        elif not language and self.language_resolver:
            inspection={'state':'unknown','reason':'未能获得 TMDB 原始语言，等待人工确认；不会自动搜索'}
        else:inspection=inspect_media(media,probe_observer=self._probe_observer)
        item={'id':media_key(media),'path':str(media),**metadata,**inspection,'original_language':language,
            'fingerprint':fingerprint,'checked_at':time.time()}
        for name in ('attempt_at','saved','subtitle'):
            if old.get(name):item[name]=old[name]
        with self._data_lock:self.data['items'][item['id']]=item
        self.progress['checked']+=1

    def _run(self, download, keyword="", force=False):
        lock=None;completed=False
        self.progress={'running':True,'checked':0,'downloaded':0,'mode':'检查与补全' if download else '检查',
            'keyword':keyword,'matched':0,'planned':0,'discovered':0,'skipped':0,'probed':0,'probe_seconds':0,'evidence_refreshed':0,
            'started_at':time.time(),'current_title':'','error':'','phase':'发现文件',
            'scan_type':'强制重检' if force else '增量检查'}
        self._checkpoint_checked=0;self._checkpoint_time=time.monotonic()
        try:
            self.root.mkdir(parents=True,exist_ok=True)
            lock=(self.root/'subtitle-automation.lock').open('a')
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise SubtitleError('上次字幕任务仍在结束，请稍后重试')
            if self.root_errors:raise SubtitleError('；'.join(self.root_errors))
            files=[]
            for media in library_files(self.roots,strict=True):
                if self.interrupted():return
                files.append(media);self.progress['discovered']+=1
            # Only a completely enumerated set can remove obsolete index entries.
            current={media_key(p) for p in files}
            with self._data_lock:
                items={k:dict(v) for k,v in self.data['items'].items() if k in current}
                for media in files:
                    key=media_key(media)
                    if key not in items:items[key]={'id':key,'path':str(media),**media_metadata(media,read_nfo=False),
                        'state':'pending','reason':'已发现文件，等待首次检查','checked_at':0}
                self.data['items']=items;self.data['catalog_roots']=list(self.roots);self.data['last_inventory']=time.time()
                self.data['manual_labels']={key:value for key,value in self.data['manual_labels'].items() if key in current}
            if not force and any(not i.get('fingerprint') for i in items.values()):self.progress['scan_type']='首次全量检查'
            scoped=[p for p in files if self.matches_keyword(items[media_key(p)],keyword)]
            self.progress.update(matched=len(scoped),phase='比较文件变化')
            cache={};queue=[]
            for media in scoped:
                if self.interrupted():return
                key=media_key(media);old=dict(items[key])
                try:fingerprint=media_fingerprint(media,cache)
                except OSError:
                    with self._data_lock:items[key].update(state='unknown',reason='本地文件暂时无法读取，等待后续检查')
                    continue
                with self._data_lock:
                    label=self.data['manual_labels'].get(key)
                    if label and label.get('video_signature')!=self.video_signature(media):self.data['manual_labels'].pop(key,None)
                if self.needs_check(old,fingerprint,force):
                    queue.append((media,fingerprint,old))
                    with self._data_lock:items[key].update(state='pending',reason='等待检查文件变化' if old.get('fingerprint') else '等待首次检查')
                else:
                    self._refresh_external_evidence(media,old)
                    self.progress['skipped']+=1
            self.data['baseline_complete']=all(i.get('fingerprint') and i['state']!='pending' for i in items.values())
            self.progress.update(planned=len(queue),phase='检查字幕')
            self._checkpoint(force=True)
            for media,fingerprint,old in queue:
                if self.interrupted():return
                before_probes=self.progress['probed']
                try:self._inspect_one(media,fingerprint,old)
                except OSError:
                    with self._data_lock:items[media_key(media)].update(state='unknown',reason='本地文件暂时无法读取，等待后续检查')
                    self.progress['checked']+=1
                self._checkpoint()
                # One low-priority probe at a time; yield between actual probes.
                if self.progress['probed']>before_probes:self._cancel.wait(.1)
            self.data['baseline_complete']=all(i.get('fingerprint') and i['state']!='pending' for i in items.values())
            if self.data['baseline_complete']:self.data['last_full_scan']=time.time()
            self._checkpoint(force=True)
            if download and not self.interrupted():
                self.progress['phase']='补全字幕'
                limit=max(1,min(20,int(self.config.get('subtitle_download_limit',5))))
                eligible=[dict(items[media_key(p)]) for p in scoped if self.effective_item(items[media_key(p)])['state']=='missing'
                    and p.suffix.lower() not in {'.strm','.iso'}
                    and str(items[media_key(p)].get('original_language') or '').lower() not in {'zh','zho','chi','cmn','yue','cn'}
                    and not str(items[media_key(p)].get('original_language') or '').lower().startswith('zh-')
                    and (not self.language_resolver or items[media_key(p)].get('original_language'))
                    and time.time()-items[media_key(p)].get('attempt_at',0)>=86400]
                eligible.sort(key=lambda i:(i.get('attempt_at',0),-i.get('checked_at',0)))
                for item in eligible[:limit]:
                    if self.interrupted():return
                    self.progress['current_title']=item['title'];item['attempt_at']=time.time()
                    with self._data_lock:items[item['id']]=dict(item)
                    try:
                        if self._auto_download(item):
                            self.progress['downloaded']+=1;item['fingerprint']=media_fingerprint(Path(item['path']))
                        self.data['auth_notified']=False
                    except SubtitleError as error:
                        item['reason']=str(error)
                        if self.service.auth_failed:
                            item.pop('attempt_at',None)
                            if not self.data.get('auth_notified') and self.notice:self.notice('极影视字幕授权失效，自动下载已暂停。请打开插件页面重新授权，无需终端。')
                            self.data['auth_notified']=True;break
                    except OSError:item['reason']='文件无法读取或字幕保存失败，请检查权限'
                    finally:
                        with self._data_lock:items[item['id']]=dict(item)
                    self._checkpoint()
            completed=not self.interrupted()
            self.data['last_run']=time.time()
            self.data['last_message']='发现 %s 个文件，本次检查 %s 个，复用 %s 个结果，下载 %s 份字幕' % (len(files),self.progress['checked'],self.progress['skipped'],self.progress['downloaded'])
        except Exception as error:
            self.data['last_message']=str(error) if isinstance(error,SubtitleError) else '本轮检查失败，请检查影视目录可读性与探测工具；已有记录已保留'
            self.progress['error']=self.data['last_message']
        finally:
            self.progress.update(running=False,finished_at=time.time(),phase='已完成' if completed else '已停止' if self.interrupted() else '失败')
            try:self._checkpoint(force=True)
            except OSError:pass
            if lock:lock.close()
            self._lock.release()
