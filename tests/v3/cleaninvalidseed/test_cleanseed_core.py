from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest

from conftest import core, tasks, raw_task


def cfg(**changes):
    return core.config_values({"downloaders": ["QB"], **changes})


@pytest.mark.parametrize("message", ["Could not connect to tracker", "Your account is disabled!", "HTTP 403", "Invalid passkey", "Connection timed out", "Too many requests", "Tracker maintenance", "Permission denied", "Service unavailable", "账号被禁用"])
def test_transport_account_and_permission_errors_never_authorize_cleanup_even_if_custom(message):
    rows = tasks(trackers=[{"url": "https://tracker.example/announce", "tier": 0, "status": 4, "msg": message}])
    assert core.classify(rows, cfg(custom_error_msg=message))[0]["status"] == "warning"


@pytest.mark.parametrize("message", ["Torrent not exists", "  TORRENT NOT EXISTS!  ", "torrent not registered with this tracker", "Torrent banned."])
def test_explicit_permanent_errors_are_normalized_and_require_healthy_same_tracker(message):
    rows = tasks(trackers=[{"url": "https://tracker.example/announce", "tier": 0, "status": 4, "msg": message}])
    assert core.classify(rows, cfg())[0]["status"] == "candidate"
    assert core.classify(rows[:1], cfg())[0]["status"] == "warning"


@pytest.mark.parametrize("trackers", [[], [{"url": "DHT", "tier": -1, "status": 2}], [{"url": "https://tracker.example/announce", "status": 3, "msg": "Torrent not exists"}], [{"url": "https://tracker.example/announce", "status": 4, "msg": "Torrent not exists"}, {"url": "https://other.example/announce", "status": 1, "msg": ""}]])
def test_empty_synthetic_updating_or_unknown_tracker_evidence_never_authorizes_removal(trackers):
    assert core.classify(tasks(trackers=trackers), cfg())[0]["status"] != "candidate"


@pytest.mark.parametrize("changes", [{"state": "pausedUP"}, {"state": "stoppedUP"}, {"state": "checkingUP"}, {"state": "queuedUP"}, {"state": "moving"}, {"progress": 0.999}, {"progress": None}, {"seeding_time": None}, {"seeding_time": 1}])
def test_incomplete_paused_checking_and_short_seeding_tasks_are_protected(changes):
    assert core.classify(tasks(**changes), cfg())[0]["status"] == "protected"


@pytest.mark.parametrize("changes", [{"exclude_categories": " movies \n"}, {"exclude_labels": " MP\n"}, {"exclude_keywords": "EXAMPLE"}])
def test_exclusions_are_applied_consistently_in_the_preview(changes):
    assert core.classify(tasks(), cfg(**changes))[0]["status"] == "protected"


def test_observation_requires_elapsed_window_and_spaced_scans_and_resets_changed_evidence():
    config = cfg(confirmations=3, grace_hours=24)
    rows = core.classify(tasks(), config)
    state = core.observe(rows, {}, config, 1000)
    state = core.observe(rows, state, config, 1001)
    assert state[rows[0]["id"]]["count"] == 1 and not rows[0]["ready"]
    state = core.observe(rows, state, config, 4600)
    assert not rows[0]["ready"]
    state = core.observe(rows, state, config, 87400)
    assert rows[0]["ready"]
    changed = core.classify(tasks(added_on=999), config)
    state = core.observe(changed, state, config, 90000)
    assert state[changed[0]["id"]]["count"] == 1 and not changed[0]["ready"]
    assert core.observe(core.classify(tasks(trackers=[]), config), state, config, 100000) == {}


def test_long_outage_does_not_age_earlier_evidence_into_readiness():
    config = cfg(grace_hours=1)
    rows = core.classify(tasks(), config)
    state = core.observe(rows, {}, config, 1000)
    state = core.observe(rows, state, config, 1000 + 3 * 86400)
    assert not rows[0]["ready"] and state[rows[0]["id"]]["count"] == 1


def test_transmission_uses_renamed_actual_file_paths_and_real_seeding_seconds():
    raw = SimpleNamespace(hash_string="c" * 40, name="Original Name", status="seeding", download_dir="/tr/movie",
                          labels=["Existing"], percent_done=1, seconds_seeding=timedelta(days=20),
                          tracker_stats=[SimpleNamespace(announce="https://tracker.example/pk", has_announced=True, last_announce_succeeded=False, last_announce_result="Torrent not exists")])
    task = core.task_record(raw, "transmission", "TR", files=[SimpleNamespace(name="Renamed/feature.mkv")])
    assert task["paths"] == ["/tr/movie/Renamed/feature.mkv"]
    assert task["seed_seconds"] == 20 * 86400 and task["hash"] == "c" * 40
    assert task["trackers"][0]["failed"] and not task["trackers"][0]["healthy"]
    assert "pk" not in str(task["trackers"])


@pytest.mark.parametrize("announced,succeeded", [(False, False), (False, True), (None, None)])
def test_transmission_has_to_announce_before_error_is_evidence(announced, succeeded):
    raw = {"trackerStats": [{"announce": "https://tracker.example/a", "hasAnnounced": announced, "lastAnnounceSucceeded": succeeded, "lastAnnounceResult": "Torrent not exists"}]}
    assert not core.tracker_records(raw, "transmission")[0]["failed"]


@pytest.mark.parametrize("filename", ["../escape", "/absolute", "folder/../escape"])
def test_invalid_transmission_file_paths_abort_inventory(filename):
    with pytest.raises(ValueError):
        core.task_record({"downloadDir": "/tr/movie"}, "transmission", "TR", files=[{"name": filename}])


@pytest.mark.parametrize("value", [-1, "nan", "inf", 1.5, True, "oops", 0])
def test_invalid_observation_config_fails_closed(value):
    with pytest.raises(ValueError):
        cfg(confirmations=value)


def test_legacy_upgrade_keeps_rules_but_never_reenables_destructive_flags():
    config = core.config_values({"enabled": True, "delete_invalid_torrents": True, "delete_invalid_files": True,
                                 "label_only": True, "min_seeding_days": 10, "downloaders": ["TR"], "download_dirs": "/mp/movie:/tr/movie", "label": None})
    assert config["action"] == "preview" and config["enabled"]
    assert config["file_min_age_days"] == 10 and config["download_dirs"] == "/mp/movie:/tr/movie"
    assert "delete_invalid_files" not in config and config["label"] == "无效做种"


def test_tracker_credentials_are_never_exposed_in_error_projections():
    text = core.safe_message("failed https://host/p/secret?passkey=secret token=private password=never " + "f" * 40)
    assert "secret" not in text and "private" not in text and "never" not in text and "f" * 40 not in text


@pytest.mark.parametrize("mapping", ["/data:/tr/movie", "/:/tr/movie", "/mp/movie:relative", "/mp/../movie:/tr/movie", "/mp/movie:/tr/movie\n/mp/movie/sub:/tr/sub", "/mp/movie:/tr/movie\n/mp/movie:/tr/other", "/mp/movie:/tr/movie\n/mp/other:/tr/movie", "/mp/movie:"])
def test_root_relative_ambiguous_and_nested_mappings_are_rejected(mapping):
    with pytest.raises(ValueError):
        core.parse_mappings(mapping)


def test_mapping_uses_path_boundaries_and_cross_client_references():
    mapping = core.parse_mappings("/mp/movie:/qb/movie,/tr/movie")[0]
    references = core.mapped_paths(mapping, [{"service": "QB", "paths": ["/qb/movie/Film2"]}, {"service": "TR", "paths": ["/tr/movie/Film/file.mkv"]}])
    assert references == {"/mp/movie/Film2", "/mp/movie/Film/file.mkv"}
    assert not core.overlaps("/mp/movie/Film", "/mp/movie/Film2")
    assert core.overlaps("/mp/movie/Film", "/mp/movie/Film/file.mkv")
    assert core.overlaps("/mp/movie/Film/file.mkv", "/mp/movie/Film")
    with pytest.raises(ValueError):
        core.mapped_paths(mapping, [{"service": "QB", "paths": []}])
    with pytest.raises(ValueError):
        core.mapped_paths(mapping, [])


@pytest.mark.parametrize('parent', ['/qb/Pack', '/mp'])
def test_ancestor_content_reference_alone_proves_and_protects_the_mapping(parent):
    mapping = core.parse_mappings('/mp/collection:/qb/Pack/Disc1')[0]
    assert core.mapped_paths(mapping, [{'service': 'QB', 'paths': [parent]}]) == {'/mp/collection'}
