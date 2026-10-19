#!/usr/bin/env python3
"""Native settings compatibility; no running watcher or real media is touched."""
from pathlib import Path
import json
import runpy
import unittest

_helpers = runpy.run_path(
    str(Path(__file__).with_name("removelink_rehardlink_same_identity_regression.py")),
    run_name="removelink_test_helpers",
)

LEGACY_DEFAULTS = {
    "enabled": False, "notify": False, "delete_scrap_infos": False,
    "delete_torrents": False, "delete_history": False,
    "delayed_deletion": True, "delay_seconds": 30, "monitor_dirs": "",
    "exclude_dirs": "", "exclude_keywords": "", "custom_scrap_extensions": "",
    "monitor_strm_deletion": False, "strm_path_mappings": "",
}


def nodes(items):
    for item in items:
        yield item
        yield from nodes(item.get("content", []))


class SettingsCompatibility(unittest.TestCase):
    def setUp(self):
        module, self.events = _helpers["load_removelink_module"]()
        self.plugin = module.RemoveLink()

    def test_existing_keys_defaults_and_field_bindings_are_preserved(self):
        form, defaults = self.plugin.get_form()
        self.assertEqual(defaults, LEGACY_DEFAULTS)
        fields = [n for n in nodes(form) if "model" in n.get("props", {})]
        self.assertEqual(len(fields), len(defaults))
        self.assertEqual({n["props"]["model"] for n in fields}, set(defaults))
        for field in fields:
            self.assertTrue(field["props"]["label"])
            model = field["props"]["model"]
            expected = "VSwitch" if isinstance(defaults[model], bool) else (
                "VTextField" if model == "delay_seconds" else "VTextarea"
            )
            self.assertEqual(field["component"], expected)
        delay = next(n["props"] for n in fields if n["props"]["model"] == "delay_seconds")
        self.assertEqual((delay["min"], delay["max"]), (10, 86400))
        json.dumps(form, ensure_ascii=False)

    def test_viewing_settings_does_not_start_watchers_or_process_deletions(self):
        marker = object()
        self.plugin.deletion_queue = [marker]
        self.plugin.file_state = {"unchanged": marker}
        def unexpected(*args, **kwargs):
            self.fail("Opening settings must not initialize or run cleanup")
        for name in ("init_plugin", "stop_service", "_process_deletion_queue"):
            setattr(self.plugin, name, unexpected)
        self.plugin.get_form()
        self.assertEqual(self.plugin.deletion_queue, [marker])
        self.assertEqual(self.plugin.file_state, {"unchanged": marker})
        self.assertEqual(self.events.calls, [])
        self.assertEqual(self.plugin.messages, [])


if __name__ == "__main__":
    unittest.main()
