"""Normalize MP's Transmission client to the verified music-task contract."""

import time
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

from .selected import SelectionError


def supported_service(service, name):
    if not service:
        raise SelectionError(f"未找到下载器 {name or '（未配置）'}，请检查 MP 下载器设置")
    if service.type not in ("qbittorrent", "transmission"):
        raise SelectionError(f"下载器 {name} 的类型 {service.type} 不受支持，请使用 qBittorrent 或 Transmission")
    if service.type == "qbittorrent":
        return service
    return SimpleNamespace(name=service.name, type=service.type, module=service.module,
                           instance=TransmissionAdapter(service.instance))


class TransmissionAdapter:
    """Keep daemon-specific fields and label replacement out of selection/seeding code."""

    def __init__(self, client):
        self.client = client

    def get_torrents(self, ids=None):
        rows, error = self.client.get_torrents(ids=ids)
        if error:
            return [], error
        result = []
        for row in rows or []:
            status = str(row.status).lower()
            progress = float(row.percent_done)
            state = {"stopped": "pausedUP" if progress == 1 else "pausedDL",
                     "check_pending": "checkingDL", "checking": "checkingDL",
                     "download_pending": "queuedDL", "downloading": "downloading",
                     "seed_pending": "queuedUP", "seeding": "stalledUP"}.get(status, "unknown")
            if row.error:
                state = "error"
            result.append({"hash": row.hashString.lower(), "state": state, "progress": progress,
                           "save_path": str(row.download_dir),
                           "content_path": str(PurePosixPath(row.download_dir) / row.name),
                           "tags": ",".join(row.labels or []), "added_on": int(row.added_date.timestamp()),
                           "seeding_time": None})
        return result, False

    def get_files(self, torrent_hash, retry=1, interval=0):
        for attempt in range(retry):
            rows = self.client.get_files(torrent_hash)
            if rows is not None:
                # TR priority=0 is normal priority; selected controls wanted/unwanted.
                return [{"index": row.id, "name": row.name, "size": row.size,
                         "priority": 1 if row.selected else 0,
                         "progress": row.completed / row.size if row.size else 1} for row in rows]
            if attempt + 1 < retry:
                time.sleep(interval)
        raise SelectionError("Transmission 文件清单读取失败，任务已保留")

    def set_files(self, torrent_hash, file_ids, priority):
        if priority > 0:
            return self.client.set_files(tid=torrent_hash, file_ids=file_ids)
        return self.client.set_unwanted_files(tid=torrent_hash, file_ids=file_ids)

    def add_torrent(self, *, content, download_dir, is_paused, tag, cookie=None, **kwargs):
        return self.client.add_torrent(content=content, download_dir=download_dir,
                                       is_paused=is_paused, labels=tag, cookie=cookie)

    def stop_torrents(self, ids):
        return self.client.stop_torrents(ids=ids)

    def start_torrents(self, ids):
        return self.client.start_torrents(ids=ids)

    def delete_torrents(self, *, delete_file, ids):
        return self.client.delete_torrents(delete_file=delete_file, ids=ids)

    def remove_torrents_tag(self, *, ids, tag):
        for key in ids:
            self._write_labels(key, [label for label in self._read_labels(key) if label not in tag])

    def set_torrents_tag(self, *, ids, tags):
        for key in ids:
            self._write_labels(key, list(dict.fromkeys(self._read_labels(key) + tags)))

    def _read_labels(self, key):
        rows, error = self.client.get_torrents(ids=[key])
        if error or len(rows or []) != 1:
            raise SelectionError("Transmission 标签无法核验，任务保持暂停")
        return list(rows[0].labels or [])

    def _write_labels(self, key, labels):
        try:
            if labels:
                if not self.client.set_torrent_tag(ids=[key], tags=labels):
                    raise ValueError("label update rejected")
            else:
                # MP's wrapper rejects an empty list; the RPC explicitly supports it.
                self.client.trc.change_torrent(ids=[key], labels=[])
        except Exception:
            raise SelectionError("Transmission 标签更新失败，任务保持暂停") from None

    def seeding_seconds(self, torrent_hash):
        """The MP client's normal query omits secondsSeeding; request it explicitly."""
        try:
            rows = self.client.trc.get_torrents(ids=[torrent_hash], arguments=["hashString", "secondsSeeding"])
            row = next((row for row in rows if row.hashString.lower() == torrent_hash.lower()), None)
            return row.seconds_seeding if row else None
        except Exception:
            return None


def check_shared_clients(entry, services):
    """A second daemon may seed the same physical source through a different mount."""
    for name, service in services.items():
        if name == entry['downloader']:
            continue
        root = PurePosixPath(str(service.module.normalize_path(Path(entry['source_root']), name)))
        rows, error = service.instance.get_torrents()
        if error:
            raise SelectionError(f"无法核对下载器 {name} 的共享文件，保留文件")
        for row in rows or []:
            other = PurePosixPath(str(row.get('content_path') or row.get('save_path') or '/'))
            if other.is_relative_to(root) or root.is_relative_to(other):
                raise SelectionError(f"下载器 {name} 的任务仍使用该目录，保留文件")
