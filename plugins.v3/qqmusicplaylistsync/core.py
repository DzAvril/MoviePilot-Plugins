"""QQ、网易云歌单完整读取与同步账本；不依赖 MP 运行环境。"""

import html
import re
import unicodedata
from datetime import datetime, timezone
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from urllib.parse import parse_qs, urlsplit, urlunsplit
from pathlib import PurePosixPath


class PlaylistError(ValueError):
    """歌单不可读或分页不完整，不能把部分结果当作完整快照。"""


MUSIC_SOURCES = ("qqmusic", "netease")


def playlist_cover_url(value, source):
    """Accept public music-platform image hosts and serve covers over HTTPS."""
    value = html.unescape(str(value or "")).strip()
    if value.startswith("//"):
        value = "https:" + value
    domains = {"qqmusic": ("y.gtimg.cn", "qpic.y.qq.com", "p.qpic.cn"),
               "netease": ("music.126.net", "music.127.net", "music.163.com")}.get(source, ())
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        if (url.scheme not in ("http", "https") or url.username or url.password
                or url.port not in (None, 80, 443)
                or not any(host == domain or host.endswith("." + domain) for domain in domains)):
            return ""
        return urlunsplit(("https", host, url.path, url.query, ""))
    except ValueError:
        return ""


def media_key(source, media_id):
    source = str(source or "qqmusic")
    return str(media_id) if source == "qqmusic" else f"{source}:{media_id}"


def track_key(state, source, media_id):
    key = media_key(source, media_id)
    return state.get("identity_aliases", {}).get(key, key)


def netease_playlist_id(value):
    value = str(value or "").strip()
    if value.isdigit() and 1 <= len(value) <= 20 and int(value) > 0:
        return value
    url = urlsplit(value)
    if url.scheme not in ("https", "http") or url.hostname not in ("music.163.com", "y.music.163.com"):
        raise PlaylistError("请填写网易云音乐歌单链接或数字歌单 ID")
    route = urlsplit(url.fragment) if url.fragment else url
    if not re.search(r"(?:^|/)playlist(?:/|$)", route.path):
        raise PlaylistError("请填写网易云歌单链接，不能使用单曲或专辑链接")
    candidate = (parse_qs(route.query).get("id") or [""])[0]
    if not candidate:
        match = re.search(r"/playlist/(\d+)", route.path)
        candidate = match.group(1) if match else ""
    if not candidate.isdigit() or len(candidate) > 20 or int(candidate) == 0:
        raise PlaylistError("链接中没有可识别的网易云歌单 ID")
    return candidate


def normalize_netease_song(raw):
    sid = str(raw.get("id") or "")
    title = html.unescape(str(raw.get("name") or "")).strip()
    artists = list(dict.fromkeys(html.unescape(str(artist.get("name") or "")).strip()
                                for artist in raw.get("ar", raw.get("artists", [])) or []))
    artists = [artist for artist in artists if artist]
    if not sid.isdigit() or sid == "0" or not title or not artists:
        raise PlaylistError("网易云未提供完整的歌曲 ID、歌名或歌手")
    album = raw.get("al", raw.get("album", {})) or {}
    published = album.get("publishTime") or raw.get("publishTime") or 0
    date = datetime.fromtimestamp(published / 1000, timezone.utc).strftime("%Y-%m-%d") if published > 0 else ""
    cover = str(album.get("picUrl") or "")
    cover_url = urlsplit(cover)
    if cover_url.scheme not in ("https", "http") or not (cover_url.hostname or "").endswith((".music.126.net", ".music.127.net", ".music.163.com")):
        cover = ""
    elif cover_url.scheme == "http":
        cover = "https:" + cover[5:]
    return {"mid": media_key("netease", sid), "id": int(sid), "source": "netease", "source_id": sid,
            "title": title, "artists": artists, "album": html.unescape(str(album.get("name") or "")),
            "album_mid": media_key("netease", album["id"]) if album.get("id") else "",
            "duration": int(raw.get("dt", raw.get("duration", 0)) or 0) // 1000,
            "year": int(date[:4]) if date else None, "release_date": date,
            "track_number": int(raw.get("no") or raw.get("position") or 0) or None, "cover_url": cover}


def fetch_netease_playlist(request, pid, batch_size=200):
    """Validate complete membership first, then fill omitted metadata in bounded batches."""
    response = request("/playlist/detail", {"id": str(pid)})
    if response.get("code") != 200:
        raise PlaylistError("网易云歌单不可访问，可能需要登录或已设为私密；保留上次完整结果")
    playlist = response.get("playlist") or response.get("result")
    if not isinstance(playlist, dict) or "trackCount" not in playlist:
        raise PlaylistError("网易云歌单缺少完整曲目数")
    expected = int(playlist["trackCount"])
    if not 0 <= expected <= 10000:
        raise PlaylistError("网易云歌单大小超出支持范围")
    raw_tracks = playlist.get("tracks") or []
    ids = [str(item.get("id") or "") for item in (playlist.get("trackIds") or raw_tracks)]
    if len(ids) != expected or len(set(ids)) != len(ids) or any(not sid.isdigit() or sid == "0" for sid in ids):
        raise PlaylistError(f"网易云歌单清单不完整：读取 {len(ids)}/{expected} 首，保留上次完整快照")
    wanted_ids = set(ids)
    by_id = {str(song.get("id")): song for song in raw_tracks if str(song.get("id")) in wanted_ids}
    missing = [sid for sid in ids if sid not in by_id]
    for start in range(0, len(missing), batch_size):
        batch = missing[start:start + batch_size]
        detail = request("/song/detail", {"ids": ",".join(batch)})
        if detail.get("code") != 200 or not isinstance(detail.get("songs"), list):
            raise PlaylistError("网易云歌曲详情未完整返回，保留上次完整快照")
        by_id.update({str(song.get("id")): song for song in detail["songs"] if str(song.get("id")) in batch})
    songs, unavailable = [], []
    for sid in ids:
        try:
            songs.append(normalize_netease_song(by_id.get(sid, {})))
        except (PlaylistError, TypeError, ValueError, OverflowError):
            unavailable.append({"songid": sid, "reason": "网易云暂未提供可用歌曲信息"})
    return {"id": media_key("netease", pid), "title": html.unescape(str(playlist.get("name") or "网易云歌单")),
            "cover_url": playlist_cover_url(playlist.get("coverImgUrl"), "netease"),
            "source": "netease", "total": expected, "songs": songs, "unavailable": unavailable,
            "member_ids": [media_key("netease", sid) for sid in ids]}


def playlist_id(value: str) -> str:
    value = str(value or "").strip()
    if value.isdigit() and 1 <= len(value) <= 20:
        return value
    url = urlsplit(value)
    if url.scheme not in ("https", "http") or not (
        url.hostname == "qq.com" or (url.hostname or "").endswith(".qq.com")
    ):
        raise PlaylistError("请填写 QQ 音乐歌单链接或数字歌单 ID")
    query = parse_qs(url.query)
    candidate = (query.get("id") or query.get("disstid") or [""])[0]
    if not candidate:
        match = re.search(r"/playlist/(\d+)", url.path)
        candidate = match.group(1) if match else ""
    if not candidate.isdigit() or len(candidate) > 20:
        raise PlaylistError("链接中没有可识别的歌单 ID")
    return candidate


def playlist_ids(values, resolve=playlist_id) -> list[str]:
    """配置一行一个链接或 ID，按真实歌单身份去重。"""
    lines = values.splitlines() if isinstance(values, str) else list(values or [])
    result = []
    for number, line in enumerate(lines, 1):
        line = str(line).strip()
        if not line:
            continue
        try:
            pid = resolve(line)
        except PlaylistError as error:
            raise PlaylistError(f"第 {number} 行：{error}") from error
        if pid not in result:
            result.append(pid)
    if not result:
        raise PlaylistError("请至少填写一个歌单链接或 ID")
    return result


def text_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", html.unescape(str(value or ""))).casefold()
    return "".join(c for c in value if c.isalnum())


AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".wav", ".aac", ".ape", ".dsf", ".aiff", ".aif", ".ogg", ".opus", ".wma"}


def track_file_selection(song: dict, files: list[str], related_songs=()) -> dict:
    """按完整歌名精确选分轨；序号、目录名或专辑同名不能代替歌曲证据。"""
    paths = [PurePosixPath(str(name).replace("\\", "/")) for name in files or []]
    result = {"allowed": False, "files": [], "matches": {}, "audio_count": 0}

    def reject(reason):
        return {**result, "reason": reason}

    if any(p.is_absolute() or ".." in p.parts or "\x00" in str(p) for p in paths):
        return reject("种子文件路径异常，跳过")
    if len({str(p) for p in paths}) != len(paths):
        return reject("种子文件路径重复，无法安全选曲")
    if any(p.suffix.casefold() == ".cue" for p in paths):
        return reject("含 CUE 的资源暂跳过，保留单曲订阅")
    audio = [p for p in paths if p.suffix.casefold() in AUDIO_EXTENSIONS]
    result["audio_count"] = len(audio)

    def matching(target):
        def credit_base(value):
            value = unicodedata.normalize("NFKC", value)
            credit = re.search(r"\s*[\[(]\s*(?:feat\.?|ft\.?|featuring)\s+([^\])]+)[\])]\s*$", value, re.I)
            if credit:
                names = re.split(r"\s*[,，/&、]\s*|\s+and\s+", credit[1], flags=re.I)
                if names and all(text_key(name) in {text_key(a) for a in target["artists"]} for name in names):
                    return value[:credit.start()].strip()
            return value

        titles = {text_key(target["title"]), text_key(credit_base(target["title"]))}
        allowed = set(titles)
        for title in titles:
            for artist in target["artists"]:
                allowed.update({text_key(artist) + title, title + text_key(artist)})
        found = []
        for path in audio:
            stem = re.sub(r"^\s*(?:CD\d+[ ._-]+)?\d{1,3}[\s._-]+", "", path.stem, flags=re.I)
            if text_key(stem) in allowed or text_key(credit_base(stem)) in allowed:
                found.append(str(path))
        return found

    requested = matching(song)
    if len(requested) != 1:
        return reject("目标歌曲未找到唯一匹配音频，跳过缺曲或版本歧义资源")
    selected = set(requested)
    matches = {str(song.get("mid") or "target"): requested[0]}
    artist_keys = {text_key(a) for a in song["artists"]}
    for other in related_songs:
        # 仅顺带选择当前歌单中同歌手、同一发行的歌曲，不猜测合辑归属。
        same_album = bool(song.get("album_mid") and song.get("album_mid") == other.get("album_mid"))
        if not same_album:
            same_album = bool(song.get("album") and text_key(song["album"]) == text_key(other.get("album")))
        if not same_album or not artist_keys.intersection(text_key(a) for a in other["artists"]):
            continue
        found = matching(other)
        if len(found) == 1:
            selected.add(found[0])
            matches[str(other["mid"])] = found[0]
    result.update(allowed=True, files=[str(p) for p in audio if str(p) in selected], matches=matches,
                  reason=f"已核验分轨：只选 {len(selected)}/{len(audio)} 首歌单歌曲")
    return result


def single_track_check(song: dict, files: list[str]) -> tuple[bool, str]:
    """兼容旧检查入口；单曲身份允许从分轨专辑精确选取。"""
    plan = track_file_selection(song, files)
    return plan["allowed"], plan["reason"]


def normalize_song(raw: dict) -> dict:
    mid = str(raw.get("mid") or raw.get("songmid") or "")
    title = html.unescape(str(raw.get("name") or raw.get("title") or raw.get("songname") or "")).strip()
    singers = raw.get("singer") or []
    artists = [html.unescape(str(s.get("name") or "")).strip() for s in singers]
    artists = list(dict.fromkeys(a for a in artists if a))
    if not re.fullmatch(r"[A-Za-z0-9]{5,40}", mid) or not title or not artists:
        raise PlaylistError("QQ 返回了缺少歌曲 ID、标题或歌手的条目")
    album = raw.get("album") or {}
    date = str(raw.get("time_public") or "")
    return {
        "mid": mid,
        "id": raw.get("id") or raw.get("songid"),
        "title": title,
        "artists": artists,
        "album": html.unescape(str(album.get("name") or album.get("title") or raw.get("albumname") or "")),
        "album_mid": str(album.get("mid") or raw.get("albummid") or ""),
        "duration": int(raw.get("interval") or 0),
        "year": int(date[:4]) if date[:4].isdigit() else None,
        "release_date": date,
        "track_number": int(raw.get("index_album") or 0) or None,
    }


def fetch_playlist(request_page, pid: str, page_size: int = 1000, fetch_filtered=None) -> dict:
    """按总数与 hasmore 双重校验分页，拒绝截断、重复页和错误响应。"""
    songs = []
    title, cover_url = "", ""
    expected = None
    signatures = set()
    unavailable = {}
    offset = 0
    while offset < 10000:
        envelope = request_page(pid, offset, page_size)
        response = envelope.get("req_0") or {}
        if envelope.get("code") != 0 or response.get("code") != 0:
            raise PlaylistError("QQ 歌单接口请求失败，请稍后重试")
        data = response.get("data")
        if not isinstance(data, dict) or "total_song_num" not in data:
            raise PlaylistError("QQ 歌单接口缺少总曲目数")
        total = int(data["total_song_num"])
        if not 0 <= total <= 10000:
            raise PlaylistError("歌单大小超出支持范围")
        if expected is not None and total != expected:
            raise PlaylistError("读取过程中歌单发生变化，下次重新获取完整快照")
        expected = total
        for item in data.get("filtered_song") or []:
            unavailable[str(item.get("songid"))] = item
        info = data.get("dirinfo") or {}
        title = html.unescape(str(info.get("title") or title))
        cover_url = (playlist_cover_url(info.get("picurl"), "qqmusic")
                     or playlist_cover_url(info.get("picurl2"), "qqmusic") or cover_url)
        raw_songs = data.get("songlist")
        if not isinstance(raw_songs, list):
            raise PlaylistError("QQ 歌单曲目列表格式异常")
        page = [normalize_song(s) for s in raw_songs]
        signature = tuple(s["mid"] for s in page)
        if page and signature in signatures:
            raise PlaylistError("QQ 接口重复返回同一页，已保留上一次完整快照")
        signatures.add(signature)
        songs.extend(page)
        offset += len(page)
        if offset >= total and not data.get("hasmore"):
            break
        if not page or not data.get("hasmore"):
            raise PlaylistError(f"歌单分页不完整：只读到 {offset}/{total} 首")
    else:
        raise PlaylistError("歌单分页超过上限")
    if len(songs) != expected:
        raise PlaylistError("歌单曲目数与接口声明不一致")
    unique = {song["mid"]: song for song in songs}
    if unavailable and fetch_filtered:
        for raw in fetch_filtered(list(unavailable.values())):
            try:
                song = normalize_song(raw)
            except PlaylistError:
                continue
            if str(song["id"]) in unavailable:
                unique[song["mid"]] = song
                unavailable.pop(str(song["id"]))
    return {"id": pid, "title": title, "cover_url": cover_url, "total": len(unique), "songs": list(unique.values()),
            "unavailable": list(unavailable.values())}


def merge_snapshot(previous: dict | None, snapshot: dict, now: float) -> dict:
    """兼容旧单歌单调用，账本自动迁移且保留成功记录。"""
    pid = snapshot["id"]
    return merge_playlists(previous, {pid: snapshot}, {}, [pid], now)


def merge_playlists(previous, snapshots, errors, configured, now):
    """各歌单独立快照，合并成员关系；失败保留该歌单上次完整结果。"""
    state = previous or {"version": 1, "tracks": {}}
    tracks = state.setdefault("tracks", {})
    aliases = state.setdefault("identity_aliases", {})

    def fingerprint(song):
        if not song.get("album") or not song.get("duration"):
            return None
        return (text_key(song["title"]), tuple(sorted(text_key(artist) for artist in song["artists"])), text_key(song["album"]))

    recordings = {}
    for mid, item in tracks.items():
        fp = fingerprint(item["song"])
        if fp:
            recordings.setdefault(fp, []).append(mid)
    if "playlists" not in state:
        old = state.get("playlist", {})
        state["playlists"] = {}
        if old.get("id"):
            state["playlists"][old["id"]] = {
                **old, "mids": [mid for mid, item in tracks.items() if item.get("present")],
                "last_fetch": state.get("last_fetch"), "last_error": "",
            }
    playlists = state["playlists"]
    for pid, entry in playlists.items():
        entry["enabled"] = pid in configured
        if entry["enabled"]:
            entry.pop("disabled_since", None)
        else:
            entry.setdefault("disabled_since", now)
    for pid in configured:
        platform = "netease" if pid.startswith("netease:") else "qqmusic"
        entry = playlists.setdefault(pid, {"id": pid, "title": f"{'网易云' if platform == 'netease' else 'QQ'} 歌单 {pid.split(':')[-1]}", "total": 0, "mids": []})
        entry["source"] = platform
        entry.update(enabled=True, last_attempt=now)
        entry.pop("disabled_since", None)
        if pid in snapshots:
            snapshot = snapshots[pid]
            for song in snapshot["songs"]:
                raw_mid = song["mid"]
                mid = aliases.get(raw_mid, raw_mid)
                fp = fingerprint(song)
                if mid not in tracks and fp:
                    candidates = [key for key in recordings.get(fp, [])
                                  if tracks[key]["song"].get("source", "qqmusic") != song.get("source", "qqmusic")
                                  and fingerprint(tracks[key]["song"]) == fp
                                  and abs(tracks[key]["song"]["duration"] - song["duration"]) <= 2
                                  and (not tracks[key]["song"].get("year") or not song.get("year")
                                       or tracks[key]["song"]["year"] == song["year"])]
                    if len(candidates) == 1:
                        mid = candidates[0]
                        aliases[raw_mid] = mid
                item = tracks.setdefault(mid, {"status": "pending", "attempts": 0, "first_seen": now})
                if raw_mid == mid:
                    item["song"] = song
                item["last_seen"] = now
                if fp and mid not in recordings.setdefault(fp, []):
                    recordings[fp].append(mid)
            entry.update({k: snapshot[k] for k in ("id", "title", "total")})
            if "cover_url" in snapshot:
                entry["cover_url"] = playlist_cover_url(snapshot["cover_url"], platform)
            members = snapshot.get("member_ids", [song["mid"] for song in snapshot["songs"]])
            entry.update(mids=list(dict.fromkeys(aliases.get(mid, mid) for mid in members if aliases.get(mid, mid) in tracks)),
                         unavailable=snapshot.get("unavailable", []), last_fetch=now, last_error="")
        elif pid in errors:
            entry["last_error"] = errors[pid]
    for item in tracks.values():
        item["playlist_ids"] = []
    for pid in configured:
        for mid in playlists[pid]["mids"]:
            if mid in tracks:
                tracks[mid]["playlist_ids"].append(pid)
    for item in tracks.values():
        item["present"] = bool(item["playlist_ids"])
        if item["present"]:
            item.pop("inactive_since", None)
        else:
            # Legacy inactive rows get a full retention window starting on migration.
            item.setdefault("inactive_since", now)
    unavailable = [item for pid in configured for item in playlists[pid].get("unavailable", [])]
    state["playlist"] = {
        "id": configured[0] if len(configured) == 1 else "",
        "title": playlists[configured[0]]["title"] if len(configured) == 1 else f"{len(configured)} 个歌单",
        "total": sum(item["present"] for item in tracks.values()), "unavailable": unavailable,
    }
    if snapshots:
        state["last_fetch"] = now
    state["last_error"] = "；".join(f"{pid}：{error}" for pid, error in errors.items())
    state["version"] = 2
    return state


def summary(state: dict) -> dict:
    counts = {k: 0 for k in ("pending", "subscribed", "library", "failed")}
    for item in state.get("tracks", {}).values():
        if item.get("present"):
            counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {
        "playlist": state.get("playlist", {}),
        "playlists": [{k: v for k, v in entry.items() if k != "mids"}
                      for entry in state.get("playlists", {}).values() if entry.get("enabled")],
        "tracked": sum(counts.values()),
        **counts,
        "last_fetch": state.get("last_fetch"),
        "last_sync": state.get("last_sync"),
        "last_error": state.get("last_error", ""),
    }


def process_pending(state, *, now, limit, existing, in_library, subscribe, save, stopped=lambda: False,
                    workers=1):
    """limit=0 一轮处理全部；有界并行调用宿主，只有主线程更新持久账本。"""
    created = 0
    attempted = 0
    # 新增歌曲优先于首次导入的历史积压，避免新收藏等待整轮回填完成。
    ordered = sorted(state["tracks"].items(), key=lambda pair: pair[1]["first_seen"], reverse=True)
    def candidates():
        nonlocal attempted
        for mid, item in ordered:
            if stopped() or (limit and attempted >= limit):
                break
            if not item.get("present") or item["status"] in ("library", "subscribed"):
                continue
            if item.get("retry_at", 0) > now:
                continue
            if mid in existing:
                item.update(status="subscribed", subscription_id=existing[mid], error="", search_pending=True)
                save(state)
                continue
            library_path = in_library(item["song"])
            if library_path:
                item.update(status="library", library_path=library_path, error="")
                save(state)
                continue
            attempted += 1
            item["attempts"] += 1
            yield mid, item

    def commit(mid, item, result):
        nonlocal created
        try:
            sid, error = result
            if not sid:
                raise RuntimeError(error or "MP 没有返回订阅 ID")
            item.update(status="subscribed", subscription_id=sid, error="", synced_at=now, search_pending=True)
            existing[mid] = sid
            created += 1
        except Exception as error:
            item.update(status="failed", error=str(error)[:250], retry_at=now + 3600)
        save(state)

    def call(song):
        try:
            return subscribe(song)
        except Exception as error:
            return None, str(error)[:250]

    if workers <= 1:
        for mid, item in candidates():
            commit(mid, item, call(item["song"]))
    else:
        iterator = iter(candidates())
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="qq-subscribe") as executor:
            pending = {}
            exhausted = False
            while pending or not exhausted:
                while len(pending) < workers and not exhausted:
                    candidate = next(iterator, None)
                    if candidate is None:
                        exhausted = True
                        break
                    mid, item = candidate
                    pending[executor.submit(call, item["song"])] = (mid, item)
                if pending:
                    done, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        mid, item = pending.pop(future)
                        # 停止后仍保存已经提交成功的在途任务，最多 workers 个。
                        commit(mid, item, future.result())
    state["last_sync"] = now
    save(state)
    return created
