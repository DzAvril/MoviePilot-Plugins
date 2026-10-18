import os
import time
from pathlib import Path

import pytest

from conftest import core, files


def source(tmp_path):
    root = (tmp_path / "movie").resolve()
    root.mkdir()
    used, orphan = root / "Used", root / "Orphan"
    used.mkdir(); orphan.mkdir()
    (used / "a.mkv").write_bytes(b"used")
    (orphan / "b.mkv").write_bytes(b"orphan")
    mapping = {"root": str(root), "aliases": ["/qb/movie", "/tr/movie"]}
    tasks = [{"service": "TR", "paths": ["/tr/movie/Used/a.mkv"]}]
    return root, used, orphan, mapping, tasks


def test_shared_nested_file_is_protected_and_orphan_is_reviewed_without_mutation(tmp_path):
    root, used, orphan, mapping, tasks = source(tmp_path)
    rows, warnings = files.inspect_sources([mapping], tasks, core.config_values({}), time.time() + 11 * 86400)
    assert [r["name"] for r in rows] == ["Orphan"] and not warnings
    assert (used / "a.mkv").read_bytes() == b"used" and (orphan / "b.mkv").read_bytes() == b"orphan"
    assert not (root / files.TRASH).exists()


def test_parent_task_protects_entire_mapped_subdirectory_even_with_another_child_task(tmp_path):
    root, used, orphan, mapping, _ = source(tmp_path)
    mapping['aliases'] = ['/qb/Pack/Disc1']
    tasks = [{'service': 'QB', 'paths': ['/qb/Pack']},
             {'service': 'QB', 'paths': ['/qb/Pack/Disc1/Used/a.mkv']}]
    rows, warnings = files.inspect_sources([mapping], tasks, core.config_values({}), time.time() + 11 * 86400)
    assert not rows and not warnings
    assert (orphan / 'b.mkv').read_bytes() == b'orphan'


def test_recent_directory_descendant_and_partial_download_protect_source(tmp_path):
    root, used, orphan, mapping, tasks = source(tmp_path)
    rows, _ = files.inspect_sources([mapping], tasks, core.config_values({}), time.time())
    assert not rows
    (orphan / "unfinished.!qB").touch()
    rows, warnings = files.inspect_sources([mapping], tasks, core.config_values({}), time.time() + 11 * 86400)
    assert not rows and warnings


def test_symlinked_roots_and_descendants_never_follow_or_move_external_files(tmp_path):
    root, used, orphan, mapping, tasks = source(tmp_path)
    outside = tmp_path / "outside"; outside.write_bytes(b"protected")
    (orphan / "link").symlink_to(outside)
    rows, warnings = files.inspect_sources([mapping], tasks, core.config_values({}), time.time() + 11 * 86400)
    assert not rows and warnings and outside.read_bytes() == b"protected"
    alias = tmp_path / "alias"; alias.symlink_to(root)
    with pytest.raises(ValueError):
        files.root_stat(alias)


def test_quarantine_and_restore_preserve_all_bytes_and_other_hardlink(tmp_path):
    root, used, orphan, mapping, tasks = source(tmp_path)
    library = tmp_path / "library.mkv"; os.link(orphan / "b.mkv", library)
    rows, _ = files.inspect_sources([mapping], tasks, core.config_values({}), time.time() + 11 * 86400)
    row = rows[0]
    entry = {**row, "id": "entry001"}
    entry["trash_path"] = files.move_to_trash(row, entry["id"])
    assert not orphan.exists() and library.read_bytes() == b"orphan"
    assert (Path(entry["trash_path"]) / "b.mkv").read_bytes() == b"orphan"
    files.restore_entry(entry)
    assert (orphan / "b.mkv").read_bytes() == b"orphan" and library.read_bytes() == b"orphan"


def test_changed_content_or_replaced_root_never_moves(tmp_path):
    root, used, orphan, mapping, tasks = source(tmp_path)
    rows, _ = files.inspect_sources([mapping], tasks, core.config_values({}), time.time() + 11 * 86400)
    (orphan / "b.mkv").write_bytes(b"changed")
    with pytest.raises(ValueError):
        files.move_to_trash(rows[0], "changed")
    assert orphan.exists()
    old = root.with_name("original"); root.rename(old); root.mkdir()
    with pytest.raises(ValueError):
        files.move_to_trash(rows[0], "changed")


def test_trash_symlink_is_rejected_and_restore_never_overwrites(tmp_path):
    root, used, orphan, mapping, tasks = source(tmp_path)
    rows, _ = files.inspect_sources([mapping], tasks, core.config_values({}), time.time() + 11 * 86400)
    outside = tmp_path / "external"; outside.mkdir()
    trash = root / files.TRASH; trash.symlink_to(outside)
    with pytest.raises(OSError):
        files.move_to_trash(rows[0], "item")
    assert orphan.exists() and not list(outside.iterdir())
    trash.unlink()
    entry = {**rows[0], "id": "item"}; entry["trash_path"] = files.move_to_trash(rows[0], "item")
    orphan.mkdir(); (orphan / "new.mkv").write_bytes(b"new")
    with pytest.raises(ValueError):
        files.restore_entry(entry)
    assert (orphan / "new.mkv").read_bytes() == b"new"
    assert (Path(entry["trash_path"]) / "b.mkv").read_bytes() == b"orphan"


def test_atomic_move_refuses_a_destination_created_after_the_prior_absence_check(tmp_path):
    root = tmp_path.resolve()
    (root / "source").write_bytes(b"source")
    (root / "destination").write_bytes(b"new concurrent content")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(FileExistsError):
            files._move_no_replace(fd, "source", fd, "destination")
    finally:
        os.close(fd)
    assert (root / "source").read_bytes() == b"source"
    assert (root / "destination").read_bytes() == b"new concurrent content"


def test_cancelled_file_move_preserves_source(tmp_path):
    root, used, orphan, mapping, tasks = source(tmp_path)
    rows, _ = files.inspect_sources([mapping], tasks, core.config_values({}), time.time() + 11 * 86400)
    with pytest.raises(ValueError):
        files.move_to_trash(rows[0], "cancelled", stopped=lambda: True)
    assert (orphan / "b.mkv").read_bytes() == b"orphan"


@pytest.mark.parametrize('change', ['symlink', 'foreign_target', 'missing_both', 'root_replaced'])
def test_reconciliation_preserves_uncertain_entries_without_following_or_mutating_them(tmp_path, change):
    root, used, orphan, mapping, tasks = source(tmp_path)
    rows, _ = files.inspect_sources([mapping], tasks, core.config_values({}), time.time() + 11 * 86400)
    entry = {**rows[0], 'id': 'pending', 'trash_path': str(root / files.TRASH / 'pending')}
    trash = root / files.TRASH
    if change == 'symlink':
        outside = tmp_path / 'outside'; outside.mkdir()
        trash.symlink_to(outside)
    elif change == 'foreign_target':
        trash.mkdir(); (trash / 'pending').write_bytes(b'foreign')
    elif change == 'missing_both':
        orphan.rename(root / 'elsewhere')
    else:
        root.rename(tmp_path / 'previous-root'); root.mkdir()
    assert files.reconcile_entry(entry) == 'uncertain'
    if change == 'foreign_target':
        assert (trash / 'pending').read_bytes() == b'foreign'
        assert (orphan / 'b.mkv').read_bytes() == b'orphan'
