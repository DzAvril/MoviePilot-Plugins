"""Create a second STRM tree using the 115 media parameters from a source tree."""

import os
import re
import shutil
import stat
from collections import Counter
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urlsplit, urlunsplit

REDIRECT_PATH = "/api/v1/plugin/P115StrmHelper/redirect_url"
PICKCODE = re.compile(r"[A-Za-z0-9]{17}")
MAX_STRM_BYTES = 16 * 1024


def absolute_path(value):
    path = Path(str(value or "").strip())
    if not path.is_absolute():
        raise ValueError("请填写容器内的绝对目录，且不能使用根目录")
    resolved = path.resolve()
    if resolved == Path("/"):
        raise ValueError("不能使用根目录")
    return resolved


def http_url(value):
    if any(char.isspace() or ord(char) < 32 for char in value):
        raise ValueError("URL 含有未编码的空白或控制字符")
    url = urlsplit(value)
    if url.scheme not in {"http", "https"} or not url.hostname or url.username is not None or url.fragment:
        raise ValueError("请填写完整的 HTTP(S) URL")
    if url.port == 0:
        raise ValueError("URL 端口必须大于零")
    return url


class Mirror:
    def __init__(self, source, target, target_url):
        self.source = absolute_path(source)
        self.target = absolute_path(target)
        if self.source.is_relative_to(self.target) or self.target.is_relative_to(self.source):
            raise ValueError("源目录和输出目录必须分开，不能互相包含")
        self.url = http_url(str(target_url or "").strip())
        self.static_query = parse_qsl(self.url.query, keep_blank_values=True, max_num_fields=32)
        if any(key.lower() in {"pickcode", "file_name"} for key, _ in self.static_query):
            raise ValueError("新 URL 中的 pickcode 和 file_name 由插件填充，请移除这两个参数")
        self._groups = set()
        self._flat = {}

    def render(self, raw):
        source_url = http_url(raw.decode("utf-8-sig").strip())
        if source_url.path != REDIRECT_PATH:
            raise ValueError("不是 115 STRM 助手的跳转链接")
        query = parse_qs(source_url.query, keep_blank_values=True, max_num_fields=32)
        codes = query.get("pickcode", [])
        names = query.get("file_name", [])
        if len(codes) != 1 or not PICKCODE.fullmatch(codes[0]) or len(names) > 1:
            raise ValueError("缺少有效的 115 取件码，或参数重复")
        params = [("pickcode", codes[0])]
        if names and names[0]:
            params.append(("file_name", names[0]))
        target_query = urlencode(params + self.static_query, quote_via=quote)
        target = self.url._replace(query=target_query)
        return (urlunsplit(target) + "\n").encode("utf-8")

    @staticmethod
    def _signature(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def _files(self, root, stopped):
        def walk_error(error):
            raise error

        for directory, dirs, files in os.walk(root, onerror=walk_error, followlinks=False):
            if stopped.is_set():
                return
            parent = Path(directory)
            dirs[:] = [name for name in dirs if not (parent / name).is_symlink()]
            yield from (parent / name for name in files if not name.startswith(".strmmirror-"))

    def _scope(self, path):
        parts = path.relative_to(self.source).parts
        if len(parts) >= 4 and parts[0] in ("movies", "series"):
            return self.source.joinpath(*parts[:3])
        if path.parent == self.source or (len(parts) == 3 and parts[0] in ("movies", "series")):
            # Flat category: share only the sidecars named for this specific title.
            return path
        return path.parent

    @staticmethod
    def _is_strm(path):
        return path.suffix.lower() == ".strm"

    @staticmethod
    def _associated(path, stem):
        return path.name.startswith((stem + ".", stem + "-"))

    def _output(self, source):
        output = self.target / source.relative_to(self.source)
        if source.resolve() != source or output.parent.resolve() != output.parent or output.is_symlink():
            raise ValueError("不跟随媒体目录或文件的符号链接")
        return output

    def _render_file(self, path):
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_STRM_BYTES:
            raise ValueError("STRM 文件不是有效的普通文件")
        with path.open("rb") as handle:
            raw = handle.read(MAX_STRM_BYTES + 1)
        if len(raw) != before.st_size or self._signature(path.lstat()) != self._signature(before):
            raise BlockingIOError("STRM 文件仍在写入")
        return before, self.render(raw)

    def _write(self, source, stopped, rendered=None):
        output = self._output(source)
        before = rendered[0] if rendered else source.lstat()
        if not stat.S_ISREG(before.st_mode):
            return "skipped"
        try:
            previous = output.lstat()
        except FileNotFoundError:
            previous = None
        if previous:
            if not stat.S_ISREG(previous.st_mode) or os.path.samestat(before, previous):
                return "skipped"
            if rendered:
                data = rendered[1]
                if previous.st_size == len(data) and output.read_bytes() == data:
                    return "unchanged"
            elif (before.st_size, before.st_mtime_ns) == (previous.st_size, previous.st_mtime_ns):
                return "unchanged"

        output.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=output.parent, prefix=".strmmirror-", delete=False) as handle:
            temporary = Path(handle.name)
        try:
            if rendered:
                temporary.write_bytes(rendered[1])
                os.chmod(temporary, stat.S_IMODE((previous or before).st_mode) & 0o777)
            else:
                shutil.copy2(source, temporary, follow_symlinks=False)
            if stopped.is_set() or self._signature(source.lstat()) != self._signature(before):
                return "pending"
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        if rendered:
            return "updated" if previous else "created"
        return "sidecars"

    def _record_write(self, counts, path, stopped, rendered=None):
        try:
            counts[self._write(path, stopped, rendered)] += 1
        except (FileNotFoundError, BlockingIOError):
            counts["pending"] += 1
        except (ValueError, RuntimeError):
            counts["skipped"] += 1
        except OSError:
            counts["errors"] += 1

    def _sync_scope(self, scope, stopped, counts):
        if self._is_strm(scope) and not scope.is_dir():
            strms = [scope]
            sidecars = [p for p in scope.parent.iterdir()
                        if not self._is_strm(p) and self._associated(p, scope.stem)]
            flat = True
        else:
            files = list(self._files(scope, stopped))
            strms = [p for p in files if self._is_strm(p)]
            sidecars = [p for p in files if not self._is_strm(p)]
            flat = False

        rendered = []
        for path in strms:
            if stopped.is_set():
                return
            try:
                rendered.append((path, self._render_file(path)))
            except (FileNotFoundError, BlockingIOError):
                counts["pending"] += 1
            except (ValueError, RuntimeError):
                counts["skipped"] += 1
            except OSError:
                counts["errors"] += 1
        if not rendered:
            return
        if flat:
            self._flat.setdefault(scope.parent, set()).add(scope)
        else:
            self._groups.add(scope)
        for path in sidecars:
            if stopped.is_set():
                return
            self._record_write(counts, path, stopped)
        for path, content in rendered:
            if stopped.is_set():
                return
            self._record_write(counts, path, stopped, content)

    def _scopes_under(self, directory, stopped):
        return {self._scope(p) for p in self._files(directory, stopped) if self._is_strm(p)}

    def _sync_scopes(self, scopes, stopped, counts):
        for scope in sorted(scopes):
            if stopped.is_set():
                break
            try:
                self._sync_scope(scope, stopped, counts)
            except (FileNotFoundError, BlockingIOError):
                counts["pending"] += 1
            except OSError:
                counts["errors"] += 1

    def scan(self, stopped):
        if not self.source.is_dir() or self.source.resolve() != self.source:
            raise OSError("源目录不可用")
        if self.target.resolve() != self.target or (self.target.exists() and not self.target.is_dir()):
            raise OSError("输出目录不可用")
        if self.target.exists() and self.source.samefile(self.target):
            raise OSError("源目录和输出目录指向同一位置")
        counts = Counter()
        self._sync_scopes(self._scopes_under(self.source, stopped), stopped, counts)
        return counts

    def sync_changes(self, paths, stopped):
        counts = Counter()
        scopes = set()
        sidecars = set()
        for path in sorted(paths):
            if stopped.is_set():
                return counts
            if not path.is_relative_to(self.source) or path.is_symlink() or path.resolve() != path:
                continue
            if path.is_dir():
                try:
                    scopes.update(self._scopes_under(path, stopped))
                except FileNotFoundError:
                    continue
                except OSError:
                    counts["errors"] += 1
            elif self._is_strm(path) and path.is_file():
                scopes.add(self._scope(path))
            elif path.is_file() and not path.name.startswith(".strmmirror-"):
                sidecars.add(path)

        self._sync_scopes(scopes, stopped, counts)
        for path in sorted(sidecars):
            if stopped.is_set():
                break
            if any(p in scopes for p in path.parents):
                continue
            flat = self._flat.get(path.parent, ())
            if any(p in self._groups for p in path.parents) or any(
                p.is_file() and self._associated(path, p.stem) for p in flat
            ):
                self._record_write(counts, path, stopped)
        return counts
