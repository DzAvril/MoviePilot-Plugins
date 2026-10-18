"""Project film/TV choices and keep subtitle results tied to one work."""
import re


def validate_lookup(keyword, media_type='all'):
    if not isinstance(keyword, str) or not keyword.strip() or len(keyword) > 200 or any(ord(c) < 32 for c in keyword):
        raise ValueError('请输入 1–200 个字符的影视名称')
    if media_type not in {'all', 'movie', 'tv'}:
        raise ValueError('请选择电影、剧集或全部')
    return keyword.strip()


def project_media(record):
    get = record.get if isinstance(record, dict) else lambda key, default=None:getattr(record,key,default)
    source = get('media_source')
    if getattr(source, 'value', source) not in {None, '', 'themoviedb', 'tmdb'}:return None
    kind = get('type') or get('media_type')
    kind = {'电影':'movie', '电视剧':'tv', 'movie':'movie', 'tv':'tv'}.get(getattr(kind,'value',kind))
    identifier = str(get('tmdb_id') or get('media_id') or '')
    title = str(get('title') or '').strip()
    if not kind or not re.fullmatch(r'[1-9]\d{0,11}',identifier) or not title:return None
    year = str(get('year') or '')
    return {'id':identifier, 'media_type':kind, 'title':title,
        'original_title':str(get('original_title') or get('original_name') or ''),
        'year':year if re.fullmatch(r'\d{4}',year) else '',
        'overview':str(get('overview') or '')[:240], 'imdb_id':str(get('imdb_id') or '')}


def project_media_choices(records):
    choices, seen = [], set()
    for record in records:
        item = project_media(record)
        if not item or (item['media_type'],item['id']) in seen:continue
        seen.add((item['media_type'],item['id']));choices.append(item)
    return choices


def selected_candidates(candidates, media):
    """An explicit IMDb mismatch must never fall back to a keyword match."""
    normalize = lambda text:re.sub(r'[^\w\u4e00-\u9fff]','',str(text)).casefold()
    aliases = {normalize(media.get(key,'')) for key in ('title','original_title')} - {''}
    year, imdb = str(media.get('year') or ''), str(media.get('imdb_id') or '')
    matched = []
    for candidate in candidates:
        found_imdb = str(candidate.get('imdb_id') or '')
        if imdb and found_imdb:
            if imdb == found_imdb:matched.append(candidate)
            continue
        group = str(candidate.get('movie') or '')
        group_name = re.sub(r'\s*[（(]?(?:19|20)\d{2}[）)]?\s*$', '', group)
        # A sequel's name containing the original name is not the same work.
        if normalize(group_name) not in aliases:continue
        if not year or year not in group + ' ' + str(candidate.get('title') or ''):continue
        matched.append(candidate)
    return matched
