"""Bounded inspection of local MoviePilot library files; unknown is never missing."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

VIDEO = {'.mkv', '.mp4', '.avi', '.mov', '.m4v', '.ts', '.wmv', '.strm', '.iso'}
TEXT = {'.srt', '.ass', '.ssa', '.vtt'}
SUB = TEXT | {'.sup', '.idx', '.sub'}
ZH = re.compile(r'(?i)(?:^|[.\s_\-\[\]()])(?:zh(?:[-_](?:cn|tw|hans|hant))?|zho|chi|chs|cht)(?:$|[.\s_\-\[\]()])|简[体中]|繁[体中]|中文|中英|英中|双语|雙語')
FOREIGN = re.compile(r'(?i)(?:^|[.\s_\-])(?:en|eng|ja|jpn|ko|kor|fr|fra|fre|de|ger|es|spa)(?:$|[.\s_\-])')


def chinese_label(value):
    return bool(ZH.search(str(value or '')))


def decode_text(data):
    for encoding in ('utf-8-sig',) + (('utf-16',) if data.startswith((b'\xff\xfe', b'\xfe\xff')) else ()) + ('gb18030', 'big5'):
        try:
            text = data.decode(encoding)
            if '\x00' not in text:
                return text
        except (UnicodeError, LookupError):
            pass
    return None


def chinese_text(data, suffix='.srt'):
    text = decode_text(data)
    if text is None:
        return None
    if suffix.lower() in {'.ass', '.ssa'}:
        text = '\n'.join(line.split(',', 9)[-1] for line in text.splitlines() if line.lower().startswith('dialogue:'))
    text = re.sub(r'\{[^}]*\}|<[^>]*>', '', text)
    han = len(re.findall(r'[\u4e00-\u9fff]', text))
    kana = len(re.findall(r'[\u3040-\u30ff]', text))
    if han >= 8 and kana == 0:
        return True
    if han or kana or len(re.findall('[A-Za-z]', text)) < 20:
        return None
    return False


SUBTITLE_EVIDENCE_VERSION = 1


def external_subtitle_inventory(path):
    """Describe associated sidecars without exposing their dialogue."""
    path=Path(path);files=[]
    for item in sorted(path.parent.iterdir()):
        if item.suffix.lower() not in SUB or not (item.stem==path.stem or item.stem.startswith(path.stem+'.')):continue
        chinese=None;basis='语言信息不足'
        if item.is_symlink() or not item.is_file():basis='文件不可读取'
        elif chinese_label(item.name):chinese=True;basis='文件名语言标记'
        elif item.suffix.lower() in TEXT:
            try:
                with item.open('rb') as handle:chinese=chinese_text(handle.read(2*1024*1024),item.suffix)
                basis='字幕正文检查'
            except OSError:basis='文件不可读取'
            if chinese is None and FOREIGN.search(item.name):chinese=False;basis='文件名语言标记'
        elif FOREIGN.search(item.name):chinese=False;basis='文件名语言标记'
        files.append({'name':item.name,'format':item.suffix.lstrip('.').upper(),'chinese':chinese,
            'language':'中文' if chinese is True else '非中文' if chinese is False else '语言待确认','basis':basis})
    return files


def missing_subtitle_reason(external):
    if external:return f'已发现 {len(external)} 个非中文外挂字幕，未发现中文字幕；不识别画面烧录字幕'
    return '未发现中文外挂或已标注的中文内嵌字幕；不识别画面烧录字幕'


def inspect_media(path, probe=None, probe_observer=None):
    path=Path(path);details={'external_subtitles':[],'subtitle_evidence_version':SUBTITLE_EVIDENCE_VERSION}
    def result(state,reason,**extra):return {**details,'state':state,'reason':reason,**extra}
    try:
        external=external_subtitle_inventory(path);details['external_subtitles']=external
        positive=next((f for f in external if f['chinese'] is True),None)
        if positive:
            return result('present','已有中文外挂字幕' if positive['basis']=='文件名语言标记' else '外挂字幕正文包含中文',evidence=positive['name'])
        unknown=['外挂字幕语言无法确认：'+f['name'] for f in external if f['chinese'] is None]
        if path.suffix.lower() in {'.strm','.iso'}:
            return result('unknown','STRM / 原盘需要媒体端轨道信息，当前不自动读取远程视频')
        if chinese_label(path.name) or re.search(r'(?i)(?:\bHC\b|硬字幕|内嵌中字|内封中字)',path.name):
            unknown.append('文件名提示中字，需要确认是否为烧录字幕')
        if any((path.parent/folder).is_dir() for folder in ('Subs','subs','Subtitles','subtitles')):
            unknown.append('存在字幕子目录，需要人工确认关联')
        if probe:data=probe(path)
        else:
            command=(['nice','-n','10'] if shutil.which('nice') else [])+['ffprobe','-v','error','-threads','1','-probesize','8M','-analyzeduration','5000000',
                '-select_streams','s','-show_entries','stream=index,codec_name:stream_tags=language,title','-of','json',str(path)]
            started=time.monotonic()
            try:response=subprocess.run(command,capture_output=True,timeout=25)
            finally:
                if probe_observer:probe_observer(time.monotonic()-started)
            if response.returncode or len(response.stdout)>1024*1024:return result('unknown','视频字幕轨道探测失败')
            data=json.loads(response.stdout)
        if not isinstance(data.get('streams'),list):return result('unknown','探测结果没有完整轨道列表')
        for stream in data['streams']:
            tags=stream.get('tags') or {};language=str(tags.get('language') or '').lower();title=str(tags.get('title') or '')
            if language in {'zh','zho','chi','cmn','yue'} or language.startswith('zh-') or chinese_label(title) or re.search('(?i)chinese|mandarin|cantonese',title):
                return result('present','已有中文内嵌字幕',evidence=language or title)
            if not language or language in {'und','unknown'}:unknown.append('内嵌字幕语言未标注')
        if unknown:return result('unknown','；'.join(dict.fromkeys(unknown)))
        return result('missing',missing_subtitle_reason(external))
    except (OSError,ValueError,subprocess.TimeoutExpired):
        return result('unknown','字幕信息无法读取或探测超时')


def media_metadata(path, read_nfo=True):
    path = Path(path)
    title = re.split(r'(?i)[ ._-]S\d{1,2}E\d{1,3}|[ ._(](?:19|20)\d{2}', path.stem)[0].replace('.', ' ').strip()
    data = {'title': title, 'imdb_id': '', 'tmdb_id': '', 'original_language': '', 'year': '', 'season': None, 'episode': None}
    episode = re.search(r'(?i)S(\d{1,2})E(\d{1,3})(?!\d|[ ._-]?E\d)', path.stem)
    if episode:data.update(season=int(episode[1]), episode=int(episode[2]))
    year = re.search(r'\b((?:19|20)\d{2})\b', str(path.parent.name))
    if year:data['year'] = year[1]
    if not read_nfo:return data
    nfos = [path.with_suffix('.nfo'), path.parent / 'movie.nfo']
    if episode:nfos += [parent / 'tvshow.nfo' for parent in list(path.parents)[:3]]
    for nfo in nfos:
        try:
            if nfo.stat().st_size > 2 * 1024 * 1024:continue
            raw = nfo.read_bytes()
            if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():continue
            root = ET.fromstring(raw)
            if not episode or root.tag == 'tvshow':
                data['title'] = root.findtext('title') or data['title']
                data['year'] = root.findtext('year') or data['year']
            imdb = next((node.text for node in root.findall('uniqueid') if node.get('type') == 'imdb'), None) or root.findtext('imdbid') or root.findtext('imdb_id')
            if not episode or root.tag == 'tvshow':
                tmdb = next((node.text for node in root.findall('uniqueid') if node.get('type') == 'tmdb'), None) or root.findtext('tmdbid')
                if tmdb and tmdb.isdigit():data['tmdb_id'] = tmdb
                data['original_language'] = root.findtext('original_language') or data['original_language']
            if imdb and re.fullmatch(r'tt\d{6,12}', imdb) and (not episode or root.tag == 'tvshow'):data['imdb_id'] = imdb
            if root.tag in {'movie', 'tvshow'}:break
        except (OSError, ET.ParseError):pass
    return data


def library_files(roots, strict=False):
    """Deterministic walk; no symlink traversal or network storage."""
    for folder in sorted(set(map(str, roots))):
        root = Path(folder).resolve()
        if str(root) == '/' or not root.is_dir():
            if strict:raise OSError('影视目录不可读取')
            continue
        def fail(error):
            if strict:raise error
        for directory, dirs, files in os.walk(root, followlinks=False, onerror=fail):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in {'BDMV', 'CERTIFICATE', 'VIDEO_TS', '@eaDir'} and not (Path(directory) / d).is_symlink())
            for name in sorted(files):
                path = Path(directory) / name
                if path.suffix.lower() in VIDEO and not path.is_symlink() and path.is_file():
                    yield path


def media_key(path):
    return hashlib.sha256(str(Path(path).absolute()).encode()).hexdigest()[:24]


def resolve_roots(automatic, custom=''):
    """A configured but unavailable directory must not silently widen the scope."""
    if not isinstance(custom,str):return [],['影视目录配置必须是每行一个绝对路径']
    entries = custom.splitlines() if custom.strip() else automatic
    roots, errors = [], []
    for value in entries:
        value = str(value or '').strip()
        if not value:continue
        path = Path(value)
        if not path.is_absolute() or '..' in path.parts or str(path)=='/':
            errors.append('目录必须是具体的绝对路径：'+value);continue
        resolved = path.resolve()
        if str(resolved)=='/':
            errors.append('请配置具体的影视目录，不能扫描整个根目录');continue
        if not resolved.is_dir() or not os.access(resolved,os.R_OK|os.X_OK):
            errors.append('目录不存在或不可读取：'+value);continue
        if any(resolved.is_relative_to(old) for old in roots):continue
        roots = [old for old in roots if not old.is_relative_to(resolved)]+[resolved]
    if not roots and not errors:errors.append('没有可用影视目录，请在插件设置中配置或检查 MoviePilot 媒体目录')
    return list(map(str,roots)),errors


def media_fingerprint(path, cache=None):
    """Track local inputs without reading the video or subtitle bodies.

    Directory and NFO stat caches are scoped to one inventory pass, so adding
    external subtitles or changing a show's NFO invalidates the next pass.
    """
    path = Path(path);cache = cache if cache is not None else {}
    def stamp(item):
        key = ('stat',str(item))
        if key not in cache:
            try:
                stat = item.stat();cache[key]=(stat.st_size,stat.st_mtime_ns,stat.st_ino)
            except FileNotFoundError:cache[key]=None
        return cache[key]
    key = ('directory',str(path.parent))
    if key not in cache:
        cache[key]=[p for p in path.parent.iterdir() if p.suffix.lower() in SUB or p.name in {'Subs','subs','Subtitles','subtitles'}]
    sidecars = [(p.name,stamp(p)) for p in cache[key] if p.name in {'Subs','subs','Subtitles','subtitles'} or p.stem==path.stem or p.stem.startswith(path.stem+'.')]
    nfos = [path.with_suffix('.nfo'),path.parent/'movie.nfo'] + [parent/'tvshow.nfo' for parent in list(path.parents)[:3]]
    inputs = [stamp(path),sorted(sidecars),[(str(nfo),stamp(nfo)) for nfo in nfos]]
    return hashlib.sha256(json.dumps(inputs,ensure_ascii=False).encode()).hexdigest()
