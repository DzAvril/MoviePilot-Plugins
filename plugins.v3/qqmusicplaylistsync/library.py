"""Bounded metadata and short-lived indexes for local music status checks."""

import time
from collections import OrderedDict


class TagCache(OrderedDict):
    """Keep metadata reuse bounded even when the local library is very large."""

    def __init__(self, limit=20000):
        super().__init__()
        self.limit = limit

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        while len(self) > self.limit:
            self.popitem(last=False)


class LibraryIndexCache:
    """Scan once per window; file existence and native transfers remain live checks."""

    def __init__(self, ttl=600, clock=time.monotonic):
        self.ttl = ttl
        self.clock = clock
        self.tags = TagCache()
        self.root = None
        self.titles = set()
        self.index = {}
        self.refreshed_at = None
        self.scans = 0

    def snapshot(self):
        return {"scans": self.scans, "tag_cache_files": len(self.tags), "index_entries": len(self.index),
                "age_seconds": round(max(0, self.clock() - self.refreshed_at), 1) if self.refreshed_at is not None else None}

    def get(self, *, settings, wanted, titles, scan, stopped=lambda: False):
        identity = (settings.get("library_path"), settings.get("library_storage") or "local")
        if identity != self.root:
            self.root = identity
            self.tags.clear()
            self.titles.clear()
            self.index.clear()
            self.refreshed_at = None
        if not wanted or not identity[0] or identity[1] != "local" or stopped():
            return {}
        now = self.clock()
        if (self.refreshed_at is None or now - self.refreshed_at >= self.ttl
                or not wanted.issubset(self.titles)):
            covered = set(titles) | set(wanted)
            index = scan(wanted=covered, tag_cache=self.tags, settings=settings)
            if stopped():
                return {}
            self.index, self.titles = index, covered
            self.refreshed_at = self.clock()
            self.scans += 1
        return {key: path for key, path in self.index.items() if key[0] in wanted}
