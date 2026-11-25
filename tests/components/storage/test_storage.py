"""Tests for the storage component. Rules R1-R12 are defined in SPEC.md.

Most tests run against both a local folder (tmp_path) and fsspec's in-memory filesystem (R11).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

from agents_playground.components.storage import PathEscapesRootError, Storage


@pytest.fixture(params=["local", "memory"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Storage:
    if request.param == "local":
        return Storage(tmp_path / "root")
    return Storage(f"memory://{uuid.uuid4().hex}")


# R1: paths are relative to the root


def test_r1_paths_are_relative_to_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    Storage(root).write_text("research/a.md", "hi")
    assert (root / "research" / "a.md").read_text(encoding="utf-8") == "hi"


def test_r1_root_accepts_str_pathlike_and_file_url(tmp_path: Path) -> None:
    Storage(str(tmp_path)).write_text("a.txt", "x")
    assert Storage(tmp_path).read_text("a.txt") == "x"
    assert Storage(tmp_path.as_uri()).read_text("a.txt") == "x"


def test_r1_relative_root_resolves_against_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    Storage("data").write_text("a.txt", "x")
    assert (tmp_path / "data" / "a.txt").read_text(encoding="utf-8") == "x"


def test_r1_root_property_returns_root_as_given(tmp_path: Path) -> None:
    assert Storage(str(tmp_path)).root == str(tmp_path)
    assert Storage("memory://abc").root == "memory://abc"


# R2: escaping the root is rejected


@pytest.mark.parametrize("bad", ["../x", "a/../../x", "..", "/etc/passwd", "a/../.."])
def test_r2_escaping_paths_are_rejected_everywhere(store: Storage, bad: str) -> None:
    for call in (
        lambda: store.read_text(bad),
        lambda: store.read_bytes(bad),
        lambda: store.write_text(bad, "x"),
        lambda: store.write_bytes(bad, b"x"),
        lambda: store.exists(bad),
        lambda: store.list(bad),
        lambda: store.latest(bad),
    ):
        with pytest.raises(PathEscapesRootError):
            call()


def test_r2_nothing_is_written_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    with pytest.raises(PathEscapesRootError):
        Storage(root).write_text("../outside.txt", "x")
    assert not (tmp_path / "outside.txt").exists()


def test_r2_dotdot_that_stays_inside_is_allowed(store: Storage) -> None:
    store.write_text("a/../b.txt", "x")
    assert store.read_text("b.txt") == "x"


def test_r2_error_is_a_value_error() -> None:
    assert issubclass(PathEscapesRootError, ValueError)


# R3: empty / root-itself paths


@pytest.mark.parametrize("bad", ["", ".", "a/.."])
def test_r3_root_itself_is_not_a_file_path(store: Storage, bad: str) -> None:
    with pytest.raises(PathEscapesRootError):
        store.read_text(bad)
    with pytest.raises(PathEscapesRootError):
        store.write_text(bad, "x")
    with pytest.raises(PathEscapesRootError):
        store.exists(bad)


# R4: writes create parents and overwrite


def test_r4_write_creates_parent_folders(store: Storage) -> None:
    store.write_text("data/snapshots/vc/firm_2026-11-20.md", "x")
    store.write_bytes("bin/deep/er/f.bin", b"\x00")
    assert store.exists("data/snapshots/vc/firm_2026-11-20.md")
    assert store.exists("bin/deep/er/f.bin")


def test_r4_write_overwrites(store: Storage) -> None:
    store.write_text("a.txt", "one")
    store.write_text("a.txt", "two")
    assert store.read_text("a.txt") == "two"


# R5: missing file


def test_r5_read_missing_raises_clear_error(store: Storage) -> None:
    with pytest.raises(FileNotFoundError, match="nope/missing.md"):
        store.read_text("nope/missing.md")
    with pytest.raises(FileNotFoundError, match="nope/missing.md"):
        store.read_bytes("nope/missing.md")


def test_r5_error_message_names_the_root(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="root-marker"):
        Storage(tmp_path / "root-marker").read_text("a.txt")


def test_r5_reading_a_directory_raises_file_not_found(store: Storage) -> None:
    store.write_text("dir/a.txt", "x")
    with pytest.raises(FileNotFoundError):
        store.read_text("dir")


# R6: UTF-8 text


def test_r6_non_ascii_round_trips(store: Storage) -> None:
    text = "Café — 健康 🩺\nline2\r\nline3"
    store.write_text("a.md", text)
    assert store.read_text("a.md") == text


def test_r6_text_is_stored_as_utf8_without_newline_translation(store: Storage) -> None:
    store.write_text("a.md", "é\r\n")
    assert store.read_bytes("a.md") == "é\r\n".encode()


def test_r6_invalid_utf8_raises_decode_error(store: Storage) -> None:
    store.write_bytes("a.bin", b"\xff\xfe\x00")
    with pytest.raises(UnicodeDecodeError):
        store.read_text("a.bin")


# R7: bytes


def test_r7_bytes_round_trip(store: Storage) -> None:
    data = bytes(range(256))
    store.write_bytes("a.bin", data)
    assert store.read_bytes("a.bin") == data


# R8: exists


def test_r8_exists(store: Storage) -> None:
    store.write_text("dir/a.txt", "x")
    assert store.exists("dir/a.txt") is True
    assert store.exists("dir/missing.txt") is False
    assert store.exists("dir") is False


# R9: list


def test_r9_list_returns_sorted_relative_files(store: Storage) -> None:
    for p in ["research/b.md", "research/a.md", "snapshots/vc/z.md", "top.txt"]:
        store.write_text(p, "x")
    assert store.list("research/*.md") == ["research/a.md", "research/b.md"]
    assert store.list() == ["research/a.md", "research/b.md", "snapshots/vc/z.md", "top.txt"]


def test_r9_list_recursive_glob(store: Storage) -> None:
    store.write_text("snapshots/vc/a.md", "x")
    store.write_text("snapshots/vc/deep/b.md", "x")
    store.write_text("snapshots/other.txt", "x")
    assert store.list("snapshots/**/*.md") == ["snapshots/vc/a.md", "snapshots/vc/deep/b.md"]


def test_r9_list_excludes_directories(store: Storage) -> None:
    store.write_text("dir/sub/a.txt", "x")
    assert store.list("*") == []
    assert store.list("dir/*") == []


def test_r9_list_no_match_is_empty(store: Storage) -> None:
    store.write_text("a.txt", "x")
    assert store.list("*.md") == []


def test_r9_list_on_root_that_does_not_exist_is_empty(tmp_path: Path) -> None:
    assert Storage(tmp_path / "not-created").list() == []
    assert Storage(f"memory://{uuid.uuid4().hex}").list() == []


def test_r9_list_does_not_include_root_prefix(tmp_path: Path) -> None:
    root = tmp_path / "root"
    Storage(root).write_text("a.txt", "x")
    assert Storage(root).list() == ["a.txt"]


# R10: latest


def test_r10_latest_picks_newest_date(store: Storage) -> None:
    for d in ["2026-09-01", "2026-11-20", "2026-10-15"]:
        store.write_text(f"research/incumbents_{d}.md", d)
    assert store.latest("research/incumbents_*.md") == "research/incumbents_2026-11-20.md"


def test_r10_latest_compares_dates_not_strings_of_other_text(store: Storage) -> None:
    store.write_text("r/a_2026-12-01.md", "x")
    store.write_text("r/z_2026-01-01.md", "x")
    assert store.latest("r/*.md") == "r/a_2026-12-01.md"


def test_r10_latest_none_when_no_match(store: Storage) -> None:
    store.write_text("research/other.md", "x")
    assert store.latest("research/incumbents_*.md") is None


def test_r10_latest_ignores_files_without_valid_date(store: Storage) -> None:
    store.write_text("r/notes.md", "x")
    store.write_text("r/bad_2026-13-45.md", "x")
    assert store.latest("r/*.md") is None
    store.write_text("r/ok_2026-01-02.md", "x")
    assert store.latest("r/*.md") == "r/ok_2026-01-02.md"


def test_r10_latest_uses_filename_not_folder_dates(store: Storage) -> None:
    store.write_text("2030-01-01/a_2026-01-01.md", "x")
    store.write_text("2020-01-01/b_2026-06-01.md", "x")
    assert store.latest("*/*.md") == "2020-01-01/b_2026-06-01.md"


def test_r10_latest_tie_goes_to_last_sorted_path(store: Storage) -> None:
    store.write_text("v/a_2026-01-01.md", "x")
    store.write_text("v/b_2026-01-01.md", "x")
    assert store.latest("v/*.md") == "v/b_2026-01-01.md"


# R11: backends are interchangeable


def test_r11_local_and_memory_give_identical_results(tmp_path: Path) -> None:
    stores = [Storage(tmp_path / "root"), Storage(f"memory://{uuid.uuid4().hex}")]
    results = []
    for s in stores:
        s.write_text("research/incumbents_2026-11-20.md", "é")
        s.write_bytes("snapshots/vc/a_2026-01-01.md", b"b")
        results.append(
            (
                s.list(),
                s.latest("research/incumbents_*.md"),
                s.exists("snapshots/vc/a_2026-01-01.md"),
                s.read_text("research/incumbents_2026-11-20.md"),
            )
        )
    assert results[0] == results[1]


# R12: fsspec missing


def test_r12_missing_fsspec_gives_helpful_import_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setitem(sys.modules, "fsspec", None)
    with pytest.raises(ImportError, match="storage"):
        Storage(tmp_path)
