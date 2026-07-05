#!/usr/bin/env python3
"""
Regression checks for WatchSync's ZSpace/极影视 adapter behavior.

Run inside the plugin repository:
    python3 tests/watchsync_zspace_adapter_regression.py
"""

import importlib.util
import json
import sys
import tempfile
import types
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote


REPO_ROOT = Path(__file__).resolve().parents[1]
WATCHSYNC_FILE = REPO_ROOT / "plugins.v2" / "watchsync" / "__init__.py"
CONFIG_FILE = REPO_ROOT / "plugins.v2" / "watchsync" / "src" / "components" / "Config.vue"


class Response:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class FakeZSpace:
    _is_watchsync_zspace = True

    def __init__(self):
        self._host = "http://zspace/"
        self._apikey = "token"
        self.user = "zspace-user-id"
        self._username = "admin"
        self.get_urls = []
        self.post_calls = []
        self.resume_items = []

    def get_user(self, user_name=None):
        if user_name in (None, "", self._username, self.user):
            return self.user
        return None

    def get_data(self, url):
        self.get_urls.append(url)
        if "/System/Info" in url:
            return Response(200, {"ServerName": "极影视"})
        if "/Items/Resume" in url:
            return Response(
                200,
                {
                    "Items": self.resume_items,
                    "TotalRecordCount": len(self.resume_items),
                },
            )
        if "/Items/item-1" in url:
            return Response(
                200,
                {
                    "Id": "item-1",
                    "UserData": {
                        "PlaybackPositionTicks": 0,
                        "Played": False,
                        "IsFavorite": False,
                    },
                },
            )
        if "/Shows/zspace-series-2/Episodes" in url:
            return Response(
                200,
                {
                    "Items": [
                        {
                            "Id": "zspace-episode-1",
                            "Name": "安稳之地",
                            "Type": "Episode",
                            "SeriesName": "降世神通：最后的气宗 第 2 季",
                            "ParentIndexNumber": 2,
                            "IndexNumber": 1,
                        },
                        {
                            "Id": "zspace-episode-3",
                            "Name": "高墙秘城",
                            "Type": "Episode",
                            "SeriesName": "降世神通：最后的气宗 第 2 季",
                            "ParentIndexNumber": 2,
                            "IndexNumber": 3,
                        }
                    ],
                    "TotalRecordCount": 1,
                },
            )
        if "SearchTerm=降世神通：最后的气宗" in unquote(url):
            return Response(
                200,
                {
                    "Items": [
                        {
                            "Id": "zspace-series-2",
                            "Name": "降世神通：最后的气宗 第 2 季",
                            "Type": "Series",
                        }
                    ],
                    "TotalRecordCount": 1,
                },
            )
        return Response(404, {}, "not implemented")

    def post_data(self, url, data=None, headers=None):
        self.post_calls.append({"url": url, "data": data, "headers": headers})
        return Response(204, {})


class FakeEmby:
    def __init__(self):
        self._host = "http://emby/"
        self._apikey = "emby-token"
        self.get_urls = []

    def get_user(self, user_name=None):
        if user_name == "dz2177":
            return "emby-user-id"
        return None

    def get_data(self, url):
        self.get_urls.append(url)
        decoded = unquote(url)
        if "SearchTerm=高墙秘城" in decoded:
            return Response(200, {"Items": [], "TotalRecordCount": 0})
        if "SearchTerm=降世神通：最后的气宗" in decoded:
            return Response(
                200,
                {
                    "Items": [
                        {
                            "Id": "episode-1",
                            "Name": "安全之地",
                            "Type": "Episode",
                            "SeriesName": "降世神通：最后的气宗",
                            "ParentIndexNumber": 2,
                            "IndexNumber": 1,
                        },
                        {
                            "Id": "episode-3",
                            "Name": "隔阂与秘密之城",
                            "Type": "Episode",
                            "SeriesName": "降世神通：最后的气宗",
                            "ParentIndexNumber": 2,
                            "IndexNumber": 3,
                        },
                    ],
                    "TotalRecordCount": 2,
                },
            )
        return Response(200, {"Items": [], "TotalRecordCount": 0})


def install_import_stubs(plugin_data_dir):
    app = types.ModuleType("app")

    eventmanager = types.SimpleNamespace(
        register=lambda event_type: (lambda func: func)
    )
    app_core_event = types.ModuleType("app.core.event")
    app_core_event.eventmanager = eventmanager
    app_core_event.Event = object

    app_log = types.ModuleType("app.log")
    app_log.logger = types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )

    app_plugins = types.ModuleType("app.plugins")
    app_plugins._PluginBase = type("_PluginBase", (), {"__init__": lambda self: None})

    app_schemas = types.ModuleType("app.schemas")
    app_schemas.WebhookEventInfo = object

    app_schema_types = types.ModuleType("app.schemas.types")
    app_schema_types.EventType = types.SimpleNamespace(WebhookMessage="WebhookMessage")

    app_core_config = types.ModuleType("app.core.config")
    app_core_config.settings = types.SimpleNamespace(PLUGIN_DATA_PATH=str(plugin_data_dir))

    app_utils_http = types.ModuleType("app.utils.http")
    app_utils_http.RequestUtils = lambda headers=None: types.SimpleNamespace(
        delete_res=lambda url: Response(200, {})
    )

    sys.modules.update(
        {
            "app": app,
            "app.core.event": app_core_event,
            "app.log": app_log,
            "app.plugins": app_plugins,
            "app.schemas": app_schemas,
            "app.schemas.types": app_schema_types,
            "app.core.config": app_core_config,
            "app.utils.http": app_utils_http,
        }
    )


def load_watchsync(plugin_data_dir):
    install_import_stubs(plugin_data_dir)
    module_name = "watchsync_under_test"
    spec = importlib.util.spec_from_file_location(module_name, WATCHSYNC_FILE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.WatchSync


def main():
    with tempfile.TemporaryDirectory() as temp_dir:
        WatchSync = load_watchsync(Path(temp_dir))
        plugin = WatchSync()
        zspace = FakeZSpace()
        plugin._emby_instances = {"Emby": object(), "极影视": zspace}
        plugin._zspace_instances = {"极影视": zspace}

        assert plugin._is_server_match("ZSpace", "极影视")
        assert plugin._is_server_match("Emby", "4e9a9c8f62cf")
        assert not plugin._is_server_match("极影视", "4e9a9c8f62cf")
        assert not plugin._is_server_match("Emby", "极影视")
        assert plugin._get_actual_server_name("ZSpace") == "极影视"
        assert plugin._default_server_for_channel("zspace") == "极影视"
        assert plugin._default_server_for_channel("emby") == "Emby"

        assert plugin._get_server_users(zspace) == [
            {"id": "zspace-user-id", "name": "admin"}
        ]

        assert plugin._update_user_progress(zspace, "admin", "item-1", 1230000000)
        assert zspace.post_calls, "expected progress write"
        progress_call = zspace.post_calls[-1]
        assert "/Sessions/Playing/Progress" in progress_call["url"], progress_call
        payload = json.loads(progress_call["data"])
        assert payload["PositionTicks"] == 1230000000, payload
        assert payload["ItemId"] == "item-1", payload
        assert payload["UserId"] == "zspace-user-id", payload

        plugin._sync_groups = [
            {
                "name": "group",
                "enabled": True,
                "users": [
                    {"server": "极影视", "username": "admin"},
                    {"server": "Emby", "username": "dz2177"},
                ],
            }
        ]
        plugin._min_watch_time = 60
        plugin._zspace_poll_state = {}
        plugin._zspace_poll_bootstrap_recent_minutes = 120
        sync_calls = []
        plugin._sync_to_group_users = lambda server, user, item, ticks: sync_calls.append(
            (server, user, item, ticks)
        )
        zspace.resume_items = [
            {
                "Id": "video-recent",
                "Name": "高墙秘城",
                "Type": "Episode",
                "SeriesName": "降世神通：最后的气宗 第 2 季",
                "ParentIndexNumber": 2,
                "IndexNumber": 3,
                "UserData": {
                    "PlaybackPositionTicks": 18380000000,
                    "LastPlayedDate": datetime.now(timezone.utc).isoformat(),
                    "Played": False,
                },
            }
        ]

        plugin._poll_zspace_instance("极影视", zspace)
        assert len(sync_calls) == 1, sync_calls
        assert sync_calls[0][0] == "极影视"
        assert sync_calls[0][1] == "admin"
        assert sync_calls[0][2]["Id"] == "video-recent"
        assert sync_calls[0][3] == 18380000000

        plugin._poll_zspace_instance("极影视", zspace)
        assert len(sync_calls) == 1, sync_calls

        emby = FakeEmby()
        matched_item = plugin._find_matching_item(
            emby,
            "dz2177",
            {
                "Id": "video-recent",
                "Name": "高墙秘城",
                "Type": "Episode",
                "SeriesName": "降世神通：最后的气宗 第 2 季",
                "ParentIndexNumber": 2,
                "IndexNumber": 3,
                "ProviderIds": {},
            },
        )
        assert matched_item and matched_item["Id"] == "episode-3", matched_item

        zspace.post_calls.clear()
        plugin._emby_instances = {"Emby": object(), "极影视": zspace}
        plugin._zspace_instances = {"极影视": zspace}
        plugin._server_types = {"Emby": "emby", "极影视": "zspace"}
        plugin._sync_watch_progress(
            "4e9a9c8f62cf",
            "dz2177",
            "极影视",
            "admin",
            {
                "Id": "episode-3",
                "Name": "隔阂与秘密之城",
                "Type": "Episode",
                "SeriesName": "降世神通：最后的气宗",
                "ParentIndexNumber": 2,
                "IndexNumber": 3,
                "ProviderIds": {},
            },
            18400000000,
        )
        assert zspace.post_calls, "expected Emby source playback to write ZSpace progress"
        zspace_payload = json.loads(zspace.post_calls[-1]["data"])
        assert zspace_payload["ItemId"] == "zspace-episode-3", zspace_payload

        zspace.resume_items = [
            {
                "Id": "zspace-episode-3",
                "Name": "高墙秘城",
                "Type": "Episode",
                "SeriesName": "降世神通：最后的气宗 第 2 季",
                "ParentIndexNumber": 2,
                "IndexNumber": 3,
                "UserData": {
                    "PlaybackPositionTicks": 18400000000,
                    "LastPlayedDate": datetime.now(timezone.utc).isoformat(),
                    "Played": False,
                },
            }
        ]
        plugin._enabled = True
        plugin._zspace_poll_enabled = True
        plugin._zspace_poll_state = {}
        sync_calls.clear()
        plugin.poll_zspace_watch_progress()
        assert sync_calls == [], "plugin-originated ZSpace writes must not bounce back through polling"

        plugin._enabled = True
        plugin._zspace_poll_enabled = False
        sync_calls.clear()
        plugin.poll_zspace_watch_progress()
        assert sync_calls == [], "disabled ZSpace source sync must not poll Resume"

        config_source = CONFIG_FILE.read_text()
        assert "hasZspaceInGroups" in config_source
        assert "zspace_poll_enabled" in config_source
        assert "zspace_poll_interval" in config_source

    print("PASS: WatchSync uses ZSpace adapter paths for users and progress")


if __name__ == "__main__":
    main()
