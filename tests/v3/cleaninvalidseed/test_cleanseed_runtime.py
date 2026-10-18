from copy import deepcopy
from types import SimpleNamespace
import threading
import time

import pytest

from conftest import core, raw_task


class QB:
    def __init__(self):
        self.rows = [raw_task(), raw_task(hash="b" * 40, name="Healthy", trackers=[
            {"url": "https://tracker.example/secret", "tier": 0, "status": 2, "msg": ""}])]
        self.calls, self.error, self.lie, self.refuse = [], False, False, False

    def get_torrents(self, ids=None):
        return deepcopy([r for r in self.rows if ids is None or r["hash"] in ids]), self.error

    def delete_torrents(self, *, delete_file, ids):
        self.calls.append(("remove", delete_file, ids))
        assert delete_file is False
        if self.refuse:
            return False
        if not self.lie:
            self.rows = [r for r in self.rows if r["hash"] != ids]
        return True

    def set_torrents_tag(self, *, ids, tags):
        self.calls.append(("tag", ids, tags))
        for row in self.rows:
            if row["hash"] == ids:
                row["tags"] += "," + ",".join(tags)


def setup(runtime, monkeypatch, **changes):
    qb = QB()
    service = SimpleNamespace(type="qbittorrent", instance=qb)
    configs = {"QB": SimpleNamespace(type="qbittorrent", enabled=True)}
    services = {"QB": service}
    helper = SimpleNamespace(get_configs=lambda include_disabled=False: configs, get_services=lambda: services)
    monkeypatch.setattr(runtime, "DownloaderHelper", lambda: helper)
    plugin = runtime.CleanInvalidSeed()
    plugin.init_plugin({"downloaders": ["QB"], "grace_hours": 1, "min_seeding_days": 0, **changes})
    return plugin, qb, configs, services


def ready(plugin, monkeypatch, runtime):
    now = time.time()
    monkeypatch.setattr(runtime.time, "time", lambda: now - 7200)
    assert plugin.clean_invalid_seed(preview=True)["success"]
    monkeypatch.setattr(runtime.time, "time", lambda: now)
    assert plugin.clean_invalid_seed(preview=True)["success"]
    row = next(row for row in plugin._state["report"]["rows"] if row["status"] == "candidate")
    assert row["ready"]
    return row


def request(plugin, runtime, row, action="remove"):
    return {"scan_id": plugin._state["report"]["scan_id"], "ids": [row["id"]], "action": action,
            "confirmation": runtime.CONFIRMATIONS[action]}


def test_manual_and_startup_scans_never_use_the_configured_automatic_remove_mode(runtime, monkeypatch):
    plugin, qb, *_ = setup(runtime, monkeypatch, action="remove")
    ready(plugin, monkeypatch, runtime)
    assert not qb.calls
    plugin.start_scan()
    for _ in range(100):
        if not plugin._busy:
            break
        threading.Event().wait(.005)
    assert not qb.calls and not plugin._busy


def test_failed_inventory_clears_evidence_and_never_changes_a_client(runtime, monkeypatch):
    plugin, qb, *_ = setup(runtime, monkeypatch)
    ready(plugin, monkeypatch, runtime)
    qb.error = True
    result = plugin.clean_invalid_seed()
    assert not result["success"] and not plugin._state["observations"] and not qb.calls
    assert not plugin.execute(request(plugin, runtime, plugin._state["report"]["rows"][0]))["success"]


@pytest.mark.parametrize("reason", ["offline", "disabled", "unsupported"])
def test_source_scan_requires_all_configured_clients_even_when_only_one_is_selected(runtime, monkeypatch, reason):
    plugin, qb, configs, services = setup(runtime, monkeypatch, detect_invalid_files=True)
    configs["Other"] = SimpleNamespace(type="unknown" if reason == "unsupported" else "transmission", enabled=reason != "disabled")
    assert not plugin.clean_invalid_seed()["success"] and not qb.calls


def test_confirmed_remove_keeps_files_checks_absence_and_cannot_be_replayed(runtime, monkeypatch):
    plugin, qb, *_ = setup(runtime, monkeypatch)
    row = ready(plugin, monkeypatch, runtime)
    payload = request(plugin, runtime, row)
    result = plugin.execute(payload)
    assert result["success"] and result["results"][0]["status"] == "success"
    assert qb.calls == [("remove", False, "a" * 40)]
    assert not plugin.execute(payload)["success"] and len(qb.calls) == 1
    assert len(plugin._state["history"]) == 1


@pytest.mark.parametrize("mode", ["lie", "refuse", "readback_failure"])
def test_api_return_value_never_becomes_a_false_success(runtime, monkeypatch, mode):
    plugin, qb, *_ = setup(runtime, monkeypatch)
    row = ready(plugin, monkeypatch, runtime)
    if mode == "readback_failure":
        original = qb.delete_torrents
        def remove(**kwargs):
            result = original(**kwargs)
            qb.error = True
            return result
        qb.delete_torrents = remove
    else:
        setattr(qb, mode, True)
    result = plugin.execute(request(plugin, runtime, row))
    assert result["results"][0]["status"] == "uncertain"
    assert plugin._state["history"][0]["status"] != "success"


def test_append_tag_preserves_existing_tags_and_verifies_result(runtime, monkeypatch):
    plugin, qb, *_ = setup(runtime, monkeypatch)
    row = ready(plugin, monkeypatch, runtime)
    result = plugin.execute(request(plugin, runtime, row, "tag"))
    assert result["results"][0]["status"] == "success"
    assert qb.rows[0]["tags"] == "MP,已整理,无效做种"


@pytest.mark.parametrize("change", ["new_task", "healthy", "incomplete", "excluded", "old_plan", "changed_config", "no_confirmation"])
def test_fresh_state_config_plan_and_confirmation_are_checked_before_every_mutation(runtime, monkeypatch, change):
    plugin, qb, *_ = setup(runtime, monkeypatch)
    row = ready(plugin, monkeypatch, runtime)
    payload = request(plugin, runtime, row)
    if change == "new_task": qb.rows[0]["added_on"] += 1
    elif change == "healthy": qb.rows[0]["trackers"][0]["status"] = 2
    elif change == "incomplete": qb.rows[0]["progress"] = .5
    elif change == "excluded": qb.rows[0]["tags"] += ",protected"
    elif change == "old_plan": plugin._state["report"]["at"] -= 601
    elif change == "changed_config": plugin._config["max_actions"] = 1
    elif change == "no_confirmation": payload["confirmation"] = "yes"
    result = plugin.execute(payload)
    assert not qb.calls
    assert not result["success"] or result["results"][0]["status"] == "skipped"


def test_operation_lock_does_not_erase_a_valid_report_or_observations(runtime, monkeypatch):
    plugin, qb, *_ = setup(runtime, monkeypatch)
    row = ready(plugin, monkeypatch, runtime)
    before = deepcopy(plugin._state)
    runtime.OPERATION_LOCK.acquire()
    try:
        assert not plugin.clean_invalid_seed()["success"]
        assert not plugin.execute(request(plugin, runtime, row))["success"]
        assert plugin.page_data()["busy"]
    finally:
        runtime.OPERATION_LOCK.release()
    assert plugin._state == before and not qb.calls


def test_public_page_projects_only_redacted_tracker_evidence(runtime, monkeypatch):
    plugin, qb, *_ = setup(runtime, monkeypatch)
    qb.rows[0]["trackers"][0]["msg"] = "failed https://tracker.example/very-secret?passkey=secret"
    plugin.clean_invalid_seed()
    page = plugin.page_data()
    assert "very-secret" not in str(page) and "passkey=secret" not in str(page)
    assert "hash" not in page["report"]["rows"][0] and "signature" not in page["report"]["rows"][0]


def test_native_routes_are_authenticated_and_no_get_route_mutates_state(runtime, monkeypatch):
    plugin, *_ = setup(runtime, monkeypatch)
    routes = plugin.get_api()
    assert len(routes) == 8 and all(route["auth"] in ("bear", "apikey") for route in routes)
    assert all(route["endpoint"] == plugin.page_data for route in routes if route["methods"] == ["GET"])


def test_manual_preview_does_not_send_configured_notifications(runtime, monkeypatch):
    plugin, *_ = setup(runtime, monkeypatch, notify=True, notify_all=True)
    assert plugin.clean_invalid_seed(preview=True)["success"]
    assert not getattr(plugin, "messages", [])


def test_transmission_inventory_explicitly_requests_file_dependencies_and_duration(runtime, monkeypatch):
    plugin, _, configs, services = setup(runtime, monkeypatch, downloaders=["TR"])
    calls = []
    raw = SimpleNamespace(hash_string="c" * 40, name="Original", status="seeding", download_dir="/tr/movie", added_date="2020-01-01",
                          percent_done=1, progress=100, seconds_seeding=900000, total_size=100, labels=["Keep"], error=0,
                          tracker_stats=[SimpleNamespace(announce="https://tracker.example/secret", has_announced=True, last_announce_succeeded=True, last_announce_result="Success")],
                          get_files=lambda: [SimpleNamespace(name="Renamed/a.mkv")])
    def get(**kwargs):
        calls.append(kwargs)
        return [raw]
    services["TR"] = SimpleNamespace(type="transmission", instance=SimpleNamespace(_trarg=["name", "percentDone"], trc=SimpleNamespace(get_torrents=get)))
    configs["TR"] = SimpleNamespace(type="transmission", enabled=True)
    tasks, _, _ = plugin._inventory(plugin._config, plugin._stop)
    assert tasks[0]["progress"] == 1 and tasks[0]["paths"] == ["/tr/movie/Renamed/a.mkv"]
    assert set(calls[0]["arguments"]) >= {"files", "priorities", "wanted", "secondsSeeding"}


def test_source_quarantine_is_reversible_and_never_touches_shared_task_files(runtime, monkeypatch, tmp_path):
    plugin, qb, *_ = setup(runtime, monkeypatch, detect_invalid_files=True)
    root = (tmp_path / "sources").resolve(); root.mkdir()
    used = root / "Used"; used.mkdir(); (used / "a.mkv").write_bytes(b"keep")
    orphan = root / "Orphan"; orphan.mkdir(); (orphan / "b.mkv").write_bytes(b"recover")
    plugin._config["download_dirs"] = f"{root}:/downloads/movie"
    qb.rows[0]["content_path"] = "/downloads/movie/Used/a.mkv"
    qb.rows[1]["content_path"] = "/downloads/movie/Used"
    now = time.time() + 20 * 86400
    monkeypatch.setattr(runtime.time, "time", lambda: now - 7200)
    assert plugin.clean_invalid_seed(preview=True)["success"]
    monkeypatch.setattr(runtime.time, "time", lambda: now)
    assert plugin.clean_invalid_seed(preview=True)["success"]
    row = next(row for row in plugin._state["report"]["rows"] if row["kind"] == "file")
    assert row["ready"]
    result = plugin.execute(request(plugin, runtime, row, "quarantine"))
    assert result["results"][0]["status"] == "success" and not orphan.exists()
    entry = next(iter(plugin._state["trash"].values()))
    assert plugin.restore({"id": entry["id"]})["success"]
    assert (orphan / "b.mkv").read_bytes() == b"recover" and (used / "a.mkv").read_bytes() == b"keep"
    assert not qb.calls and not plugin._state["trash"]


def test_stopping_or_reinitializing_during_collection_cancels_the_old_scan(runtime, monkeypatch):
    plugin, qb, *_ = setup(runtime, monkeypatch)
    original = qb.get_torrents
    def get(**kwargs):
        result = original(**kwargs)
        plugin.init_plugin({"downloaders": ["QB"]})
        return result
    qb.get_torrents = get
    assert not plugin.clean_invalid_seed(preview=True)["success"]
    assert not qb.calls and not plugin._state.get("report")


def test_unchanged_status_returns_only_revision_and_live_busy_flag(runtime, monkeypatch):
    plugin, *_ = setup(runtime, monkeypatch)
    assert plugin.clean_invalid_seed(preview=True)["success"]
    first = plugin.page_data()
    next_response = plugin.page_data(first["revision"])
    assert next_response == {"success": True, "unchanged": True, "revision": first["revision"], "busy": False}
    plugin._busy = True
    assert plugin.page_data(first["revision"])["busy"]


def test_conflicting_source_mapping_does_not_hide_task_results_or_scan_source_files(runtime, monkeypatch):
    plugin, qb, *_ = setup(runtime, monkeypatch, detect_invalid_files=True, download_dirs="/mp/movie:/dl/movie\n/mp/other:/dl/movie")
    assert plugin.clean_invalid_seed(preview=True)["success"]
    report = plugin._state["report"]
    assert report["warnings"] and all(row["kind"] == "torrent" for row in report["rows"])
    assert not qb.calls
