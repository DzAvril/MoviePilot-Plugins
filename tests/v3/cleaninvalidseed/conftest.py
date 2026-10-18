import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).parents[3] / "plugins.v3/cleaninvalidseed"
package = ModuleType("cis_pure")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
core = __import__("cis_pure.core", fromlist=["*"])
files = __import__("cis_pure.files", fromlist=["*"])


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    class Base:
        def get_data(self, key):
            return getattr(self, "saved", {}).get(key)

        def save_data(self, key, value):
            self.saved = {key: value}

        def get_data_path(self):
            return tmp_path / "plugin-data"

        def update_config(self, config):
            self.updated = config

        def post_message(self, **kwargs):
            self.messages = [*getattr(self, "messages", []), kwargs]

    for name in ("app", "app.sdk", "app.core"):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    monkeypatch.setitem(sys.modules, "app.sdk.plugin", SimpleNamespace(_PluginBase=Base))
    monkeypatch.setitem(sys.modules, "app.sdk.logging", SimpleNamespace(logger=SimpleNamespace(warning=lambda *_: None)))
    monkeypatch.setitem(sys.modules, "app.sdk.services", SimpleNamespace(DownloaderHelper=lambda: None))
    monkeypatch.setitem(sys.modules, "app.core.config", SimpleNamespace(settings=SimpleNamespace(TZ="Asia/Shanghai")))
    monkeypatch.setitem(sys.modules, "app.schemas", SimpleNamespace(NotificationType=SimpleNamespace(SiteMessage="site")))
    spec = importlib.util.spec_from_file_location("cis_runtime", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def raw_task(**overrides):
    return {"hash": "a" * 40, "name": "Example", "state": "stalledUP", "size": 100, "progress": 1,
            "seeding_time": 20 * 86400, "content_path": "/downloads/movie/Example", "added_on": 100,
            "category": "movies", "tags": "MP,已整理", "trackers": [
                {"url": "https://tracker.example/secret/announce", "status": 4, "msg": "Torrent not exists", "tier": 0}], **overrides}


def tasks(**overrides):
    bad = core.task_record(raw_task(**overrides), "qbittorrent", "QB")
    good = core.task_record(raw_task(hash="b" * 40, name="Healthy", content_path="/downloads/movie/Healthy", trackers=[
        {"url": "https://tracker.example/another-secret/announce", "status": 2, "msg": "", "tier": 0}]), "qbittorrent", "QB")
    return [bad, good]
