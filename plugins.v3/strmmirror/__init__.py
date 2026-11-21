"""MoviePilot V3 plugin that mirrors a 115 STRM library using filesystem events."""

from threading import Event, Thread

from app.sdk.logging import logger
from app.sdk.plugin import _PluginBase

from .mirror import Mirror

DEFAULTS = {
    "enabled": False,
    "source_path": "",
    "target_path": "",
    "target_url": "",
}


class StrmMirror(_PluginBase):
    plugin_name = "115 STRM 副库"
    plugin_desc = "监听 115 STRM 新增与更新，将影片目录和附属文件同步到独立副库。"
    plugin_icon = "Ombi_A.png"
    plugin_version = "1.1.0"
    plugin_author = "DzAvril"
    author_url = "https://github.com/DzAvril"
    plugin_config_prefix = "strmmirror_"
    plugin_order = 20
    auth_level = 1

    def init_plugin(self, config=None):
        self.stop_service()
        self._worker = None
        self._config = {key: (config or {}).get(key, default) for key, default in DEFAULTS.items()}
        self._status = "自动同步已停用。"
        if not self._config["enabled"]:
            return
        try:
            from .monitor import watch
            mirror = Mirror(self._config["source_path"], self._config["target_path"], self._config["target_url"])
        except ImportError:
            self._status = "缺少文件系统监听依赖，无法启动实时监听。"
            logger.warning(f"{self.plugin_name}：{self._status}")
            return
        except (ValueError, OSError, RuntimeError):
            self._status = "配置无效，请检查源目录、输出目录和播放 URL。"
            logger.warning(f"{self.plugin_name}：{self._status}")
            return
        stopped = Event()
        self._stop = stopped
        self._status = "正在启动文件系统监听。"
        self._worker = Thread(
            target=watch,
            args=(mirror, stopped, lambda status: self._report(status, stopped)),
            name="StrmMirror",
            daemon=True,
        )
        self._worker.start()

    def _report(self, status, stopped):
        if not stopped.is_set():
            self._status = status
            logger.info(f"{self.plugin_name}：{status}")

    def get_state(self):
        worker = getattr(self, "_worker", None)
        return bool(worker and worker.is_alive() and not self._stop.is_set())

    def get_service(self):
        return []

    def stop_service(self):
        worker = getattr(self, "_worker", None)
        if worker:
            self._stop.set()
            worker.join(timeout=5)

    def get_command(self):
        return []

    def get_api(self):
        return []

    def get_form(self):
        fields = [
            ("VSwitch", "enabled", "启用实时同步", {}),
            ("VTextField", "source_path", "源 STRM 目录", {"placeholder": "/ssd/strm"}),
            ("VTextField", "target_path", "副库输出目录", {"placeholder": "/ssd/strm-funnel"}),
            ("VTextField", "target_url", "新的 STRM 播放 URL",
             {"type": "password", "autocomplete": "off",
              "hint": "填到跳转接口，可带网关令牌。取件码和文件名从源 STRM 读取。",
              "persistentHint": True}),
        ]
        content = [{"component": component, "props": {"model": model, "label": label, **options}}
                   for component, model, label, options in fields]
        return [{"component": "VForm", "content": content}], dict(getattr(self, "_config", DEFAULTS))

    def get_page(self):
        status = getattr(self, "_status", "自动同步已停用。")
        return [{"component": "VAlert", "props": {"type": "info", "variant": "tonal"}, "text": status}]
