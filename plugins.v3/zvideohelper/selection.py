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


def _number(value):
    if isinstance(value, int) and not isinstance(value, bool):return value
    text = str(value or '')
    if text.isascii() and text.isdigit():return int(text)
    digits = dict(zip('零〇一二两三四五六七八九', (0,0,1,2,2,3,4,5,6,7,8,9)))
    if text in digits:return digits[text]
    if text.count('十') == 1:
        tens, units = text.split('十')
        if tens in digits or not tens:
            if units in digits or not units:return digits.get(tens,1)*10 + digits.get(units,0)
    return None


def season_numbers(title):
    text = str(title or '')
    numbers = {int(v) for v in re.findall(r'(?i)(?<![a-z])S(\d{1,3})(?=E\d|[ ._\-]|$)',text)}
    numbers.update(int(v) for v in re.findall(r'(?i)S(\d{1,3})[ ._-]*E\d',text))
    numbers.update(int(v) for v in re.findall(r'(?i)Season[ ._-]*(\d{1,3})(?!\d)',text))
    numbers.update(int(v) for v in re.findall(r'(?i)(?<!\d)(\d{1,3})x\d{1,4}(?!\d)',text))
    numbers.update(n for v in re.findall(r'第([零〇一二两三四五六七八九十\d]+)季',text) if (n := _number(v)) is not None)
    for a,b in re.findall(r'(?i)S(\d{1,3})\s*[-~至]\s*S?(\d{1,3})(?!\d)',text):
        if 0 <= int(b)-int(a) <= 100:numbers.update(range(int(a),int(b)+1))
    return numbers


def episode_numbers(title):
    text = str(title or '')
    numbers = {int(v) for v in re.findall(r'(?i)(?:E|EP(?:ISODE)?[ ._-]*)(\d{1,4})(?!\d)',text)}
    numbers.update(int(v) for v in re.findall(r'(?i)(?<!\d)\d{1,3}x(\d{1,4})(?!\d)',text))
    numbers.update(n for v in re.findall(r'第([零〇一二两三四五六七八九十\d]+)(?:集|话|話)',text) if (n := _number(v)) is not None)
    for a,b in re.findall(r'(?i)E(\d{1,4})\s*[-~至]\s*E?(\d{1,4})(?!\d)',text):
        if 0 <= int(b)-int(a) <= 500:numbers.update(range(int(a),int(b)+1))
    # Number-only archive members are accepted only with a known parent season.
    base = text.rsplit('/',1)[-1]
    match = re.fullmatch(r'(?i)(\d{1,4})(?:[._ -](?:chs|cht|zh|en|eng))?\.(?:srt|ass|ssa|vtt)',base)
    if match:numbers.add(int(match[1]))
    return numbers


def episode_matches(title, season, episode, parent=''):
    seasons = season_numbers(title) or season_numbers(parent)
    episodes = episode_numbers(title) or episode_numbers(parent)
    return seasons == {season} and episodes == {episode}


def may_contain_episode(title, season, episode):
    seasons, episodes = season_numbers(title), episode_numbers(title)
    return (not seasons or season in seasons) and (not episodes or episode in episodes)


def project_seasons(record):
    get = record.get if isinstance(record,dict) else lambda key,default=None:getattr(record,key,default)
    info = get('season_info') or (get('tmdb_info') or {}).get('seasons') or []
    seasons = {}
    for row in info:
        if not isinstance(row,dict):continue
        number = _number(row.get('season_number'))
        if number is None or not 0 <= number <= 999:continue
        seasons[number] = {'number':number,'name':str(row.get('name') or ('特别篇' if number==0 else f'第 {number} 季')),
            'episode_count':_number(row.get('episode_count')) or 0,'air_date':str(row.get('air_date') or '')}
    return [seasons[k] for k in sorted(seasons)]


def project_episodes(data, season):
    episodes = {}
    for row in data.get('episodes',[]) if isinstance(data,dict) else []:
        if not isinstance(row,dict):continue
        number = _number(row.get('episode_number'))
        if number is None or not 1 <= number <= 9999 or _number(row.get('season_number',season)) != season:continue
        episodes[number] = {'number':number,'name':str(row.get('name') or f'第 {number} 集'),'air_date':str(row.get('air_date') or '')}
    return [episodes[k] for k in sorted(episodes)]
