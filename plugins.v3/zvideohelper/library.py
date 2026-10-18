"""Bounded inspection of local MoviePilot library files; unknown is never missing."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
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


def inspect_media(path, probe=None):
    path = Path(path)
    try:
        unknown = []
        for item in path.parent.iterdir():
            if item.suffix.lower() not in SUB or not (item.stem == path.stem or item.stem.startswith(path.stem + '.')):
                continue
            if item.is_symlink() or not item.is_file():
                unknown.append('外挂字幕不可读取');continue
            if chinese_label(item.name):
                return {'state': 'present', 'reason': '已有中文外挂字幕', 'evidence': item.name}
            if item.suffix.lower() in TEXT:
                with item.open('rb') as handle:
                    chinese = chinese_text(handle.read(2 * 1024 * 1024), item.suffix)
                if chinese is True:
                    return {'state': 'present', 'reason': '外挂字幕正文包含中文', 'evidence': item.name}
                if chinese is None and not FOREIGN.search(item.name):unknown.append('外挂字幕语言无法确认')
            elif not FOREIGN.search(item.name):unknown.append('图形外挂字幕语言未标注')
        if path.suffix.lower() in {'.strm', '.iso'}:
            return {'state': 'unknown', 'reason': 'STRM / 原盘需要媒体端轨道信息，当前不自动读取远程视频'}
        if chinese_label(path.name) or re.search(r'(?i)(?:\bHC\b|硬字幕|内嵌中字|内封中字)', path.name):
            unknown.append('文件名提示中字，需要确认是否为烧录字幕')
        if any((path.parent / folder).is_dir() for folder in ('Subs', 'subs', 'Subtitles', 'subtitles')):
            unknown.append('存在字幕子目录，需要人工确认关联')
        if probe:
            data = probe(path)
        else:
            result = subprocess.run(['ffprobe', '-v', 'error', '-probesize', '8M', '-analyzeduration', '5000000',
                '-select_streams', 's', '-show_entries', 'stream=index,codec_name:stream_tags=language,title', '-of', 'json', str(path)],
                capture_output=True, timeout=25)
            if result.returncode or len(result.stdout) > 1024 * 1024:
                return {'state': 'unknown', 'reason': '视频字幕轨道探测失败'}
            data = json.loads(result.stdout)
        if not isinstance(data.get('streams'), list):
            return {'state': 'unknown', 'reason': '探测结果没有完整轨道列表'}
        for stream in data['streams']:
            tags = stream.get('tags') or {}
            language = str(tags.get('language') or '').lower()
            title = str(tags.get('title') or '')
            if language in {'zh', 'zho', 'chi', 'cmn', 'yue'} or language.startswith('zh-') or chinese_label(title) or re.search('(?i)chinese|mandarin|cantonese', title):
                return {'state': 'present', 'reason': '已有中文内嵌字幕', 'evidence': language or title}
            if not language or language in {'und', 'unknown'}:
                unknown.append('内嵌字幕语言未标注')
        if unknown:return {'state': 'unknown', 'reason': '；'.join(dict.fromkeys(unknown))}
        return {'state': 'missing', 'reason': '未发现中文外挂或已标注的中文内嵌字幕；不识别画面烧录字幕'}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {'state': 'unknown', 'reason': '字幕信息无法读取或探测超时'}


def media_metadata(path):
    path = Path(path)
    title = re.split(r'(?i)[ ._-]S\d{1,2}E\d{1,3}|[ ._(](?:19|20)\d{2}', path.stem)[0].replace('.', ' ').strip()
    data = {'title': title, 'imdb_id': '', 'tmdb_id': '', 'original_language': '', 'year': '', 'season': None, 'episode': None}
    episode = re.search(r'(?i)S(\d{1,2})E(\d{1,3})(?!\d|[ ._-]?E\d)', path.stem)
    if episode:data.update(season=int(episode[1]), episode=int(episode[2]))
    year = re.search(r'\b((?:19|20)\d{2})\b', str(path.parent.name))
    if year:data['year'] = year[1]
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


def library_files(roots):
    """Deterministic walk; no symlink traversal or network storage."""
    for folder in sorted(set(map(str, roots))):
        root = Path(folder).resolve()
        if str(root) == '/' or not root.is_dir():continue
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.') and d not in {'BDMV', 'CERTIFICATE', 'VIDEO_TS', '@eaDir'} and not (Path(directory) / d).is_symlink())
            for name in sorted(files):
                path = Path(directory) / name
                if path.suffix.lower() in VIDEO and not path.is_symlink() and path.is_file():
                    yield path


def media_key(path):
    return hashlib.sha256(str(Path(path).absolute()).encode()).hexdigest()[:24]
