"""Source inspection and reversible moves. Never unlink, rmtree, or follow symlinks."""

import os
import stat
import ctypes
import sys
from pathlib import Path

from .core import digest, lines, mapped_paths, overlaps

TRASH = ".cleaninvalidseed-trash"
PARTIAL = (".!qb", ".part", ".partial", ".tmp", ".!ut")


def root_stat(root):
    path = Path(root)
    if not path.is_absolute() or path.resolve(strict=True) != path or not path.is_dir():
        raise ValueError("源目录不存在、不是目录或包含软链接")
    return path.stat()


def fingerprint(path, device, *, limit=50000, stopped=lambda: False):
    """Fingerprint all descendants so a changed or recently modified directory stays protected."""
    records, size, newest = [], 0, 0
    stack = [Path(path)]
    while stack:
        if stopped():
            raise ValueError("检测或操作已停止")
        entry = stack.pop()
        info = entry.lstat()
        if info.st_dev != device or stat.S_ISLNK(info.st_mode) or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ValueError("包含软链接、挂载点或特殊文件，保留源文件")
        if entry != Path(path) and os.path.ismount(entry):
            raise ValueError("包含挂载点，保留源文件")
        if entry.name.casefold().endswith(PARTIAL):
            raise ValueError("包含未完成下载文件，保留源文件")
        records.append((str(entry.relative_to(path)), info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode))
        newest = max(newest, info.st_mtime, info.st_ctime)
        if stat.S_ISREG(info.st_mode):
            size += info.st_size
        else:
            stack.extend(entry.iterdir())
        if len(records) > limit:
            raise ValueError("目录条目过多，请单独检查")
    return {"signature": digest(sorted(records)), "size": size, "newest": newest,
            "inode": Path(path).lstat().st_ino, "entries": len(records)}


def inspect_sources(mappings, tasks, config, now, stopped=lambda: False):
    rows, warnings = [], []
    for mapping in mappings:
        if stopped():
            raise ValueError("检测已停止")
        root = Path(mapping["root"])
        try:
            info = root_stat(root)
            protected = mapped_paths(mapping, tasks)
            if str(root) in protected:
                continue
            children = sorted(root.iterdir())
        except (ValueError, OSError) as error:
            warnings.append(f"{root}：{error}" if isinstance(error, ValueError) else f"{root}：源目录暂不可读取，已跳过")
            continue
        for path in children:
            if stopped():
                raise ValueError("检测已停止")
            if path.name.startswith(".") or any(x.casefold() in path.name.casefold() for x in lines(config["exclude_keywords"])):
                continue
            if any(overlaps(str(path), used) for used in protected):
                continue
            try:
                fp = fingerprint(path, info.st_dev, stopped=stopped)
                if now - fp["newest"] < config["file_min_age_days"] * 86400:
                    continue
                rows.append({"id": digest(["file", str(path)]), "kind": "file", "name": path.name,
                             "path": str(path), "root": str(root), "root_inode": info.st_ino,
                             "device": info.st_dev, "status": "candidate", "reason": "全部下载器清单中均无路径引用",
                             **fp})
            except (OSError, ValueError):
                warnings.append(f"已保护 {path.name}：内容无法完整验证或含软链接、挂载点、未完成文件")
            if len(rows) > 1000:
                raise ValueError("源文件候选超过 1000，已停止，请缩小目录范围")
    return rows, list(dict.fromkeys(warnings))[:30]


def _move_no_replace(source_fd, source, destination_fd, destination):
    """The absence check and rename must be one OS operation, including on restore."""
    library = ctypes.CDLL(None, use_errno=True)
    name, flag = ("renameat2", 1) if sys.platform.startswith("linux") else ("renameatx_np", 4)
    function = getattr(library, name, None) if sys.platform.startswith("linux") or sys.platform == "darwin" else None
    if function is None:
        raise ValueError("当前系统不支持无覆盖移动，源文件保留")
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    result = function(source_fd, os.fsencode(source), destination_fd, os.fsencode(destination), flag)
    if result:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


def move_to_trash(row, entry_id, *, stopped=lambda: False, before_move=lambda: None):
    """Use directory descriptors; never overwrite or traverse a substituted root/trash symlink."""
    root = Path(row["root"])
    info = root_stat(root)
    if (info.st_dev, info.st_ino) != (row["device"], row["root_inode"]):
        raise ValueError("源目录已改变，已取消")
    name = Path(row["path"]).name
    if root / name != Path(row["path"]) or name.startswith("."):
        raise ValueError("候选路径无效")
    if fingerprint(root / name, info.st_dev, stopped=stopped)["signature"] != row["signature"]:
        raise ValueError("文件内容已变化，请重新检测")
    with_directory = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = os.open(root, with_directory)
    trash_fd = None
    try:
        if os.fstat(root_fd).st_ino != row["root_inode"]:
            raise ValueError("源目录已替换")
        try:
            os.mkdir(TRASH, mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        trash_fd = os.open(TRASH, with_directory, dir_fd=root_fd)
        if os.fstat(trash_fd).st_dev != info.st_dev:
            raise ValueError("回收区必须与源文件处于同一文件系统")
        source = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        if source.st_ino != row["inode"] or stat.S_ISLNK(source.st_mode):
            raise ValueError("源文件已替换")
        destination = entry_id
        try:
            os.stat(destination, dir_fd=trash_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError("回收区目标已存在")
        if stopped():
            raise ValueError("操作已停止，源文件保留")
        before_move()
        if stopped():
            raise ValueError("操作已停止，源文件保留")
        _move_no_replace(root_fd, name, trash_fd, destination)
        os.fsync(root_fd)
        os.fsync(trash_fd)
        return str(root / TRASH / destination)
    finally:
        if trash_fd is not None:
            os.close(trash_fd)
        os.close(root_fd)


def reconcile_entry(entry):
    """Only resolve an interrupted intent when root, source and destination identities prove it."""
    root, original = Path(entry["root"]), Path(entry["path"])
    if original.parent != root or original.name.startswith(".") or Path(entry["trash_path"]) != root / TRASH / entry["id"]:
        return "uncertain"
    root_fd = trash_fd = None
    try:
        info = root_stat(root)
        expected_root = (entry["device"], entry["root_inode"])
        if (info.st_dev, info.st_ino) != expected_root:
            return "uncertain"
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        root_fd = os.open(root, flags)
        current = os.fstat(root_fd)
        if (current.st_dev, current.st_ino) != expected_root:
            return "uncertain"
        try:
            source = os.stat(original.name, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            source = None
        destination = None
        try:
            trash_fd = os.open(TRASH, flags, dir_fd=root_fd)
        except FileNotFoundError:
            pass
        else:
            if os.fstat(trash_fd).st_dev != info.st_dev:
                return "uncertain"
            try:
                destination = os.stat(entry["id"], dir_fd=trash_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
        def matches(item):
            return item is not None and (item.st_dev, item.st_ino) == (entry["device"], entry["inode"]) and (stat.S_ISREG(item.st_mode) or stat.S_ISDIR(item.st_mode))
        if matches(source) and destination is None:
            return "unmoved"
        if source is None and matches(destination):
            return "quarantined"
    except (OSError, ValueError):
        pass
    finally:
        if trash_fd is not None:
            os.close(trash_fd)
        if root_fd is not None:
            os.close(root_fd)
    return "uncertain"


def restore_entry(entry, *, stopped=lambda: False):
    root, original = Path(entry["root"]), Path(entry["path"])
    if original.parent != root or original.name.startswith("."):
        raise ValueError("原始路径无效")
    if Path(entry["trash_path"]) != root / TRASH / entry["id"]:
        raise ValueError("回收区路径无效")
    info = root_stat(root)
    if (info.st_dev, info.st_ino) != (entry["device"], entry["root_inode"]):
        raise ValueError("源目录或挂载点已改变，请人工检查回收区")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = os.open(root, flags)
    trash_fd = None
    try:
        trash_fd = os.open(TRASH, flags, dir_fd=root_fd)
        item = os.stat(entry["id"], dir_fd=trash_fd, follow_symlinks=False)
        if item.st_ino != entry["inode"] or stat.S_ISLNK(item.st_mode):
            raise ValueError("回收区条目已改变，请人工检查")
        try:
            os.stat(original.name, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError("原位置已有同名内容，保留双方文件")
        if stopped():
            raise ValueError("操作已停止，回收区内容保留")
        _move_no_replace(trash_fd, entry["id"], root_fd, original.name)
        os.fsync(root_fd)
        os.fsync(trash_fd)
    finally:
        if trash_fd is not None:
            os.close(trash_fd)
        os.close(root_fd)
