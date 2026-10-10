"""Unit and drift checks for the research-to-web export boundary."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from cubs_edge_lab import web_export

REPO = Path(__file__).resolve().parents[1]
HIDDEN_TERMS = ("sendhold_fit", "p_safe", "predicted", "flagged", "runs_left")
APPROVED_NEGATIVE_MEANING = (
    "No measurable improvement over a simple baseline was shown. "
    "This does not show the opposite."
)


@pytest.fixture
def mini_root(tmp_path, monkeypatch):
    """A scratch repository with one tiny research file and one selection."""
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "cubs_case.json").write_text(
        '{"as_of_date": "2026-10-09"}'
    )
    (tmp_path / "research" / "source.json").write_text(
        '{"key": null, "a/b": {"~k": 1}, "secret": 3}'
    )
    monkeypatch.setattr(web_export, "SELECTIONS", {
        "test.json": {
            "v": ("source.json", "/key"),
            "esc": ("source.json", "/a~1b/~0k"),
        },
    })
    return tmp_path


def test_resolve_pointer_handles_escapes_and_null():
    document = {"a/b": {"~key": None}}
    assert web_export.resolve_pointer(document, "/a~1b/~0key") is None


def test_resolve_pointer_indexes_arrays_and_root():
    assert web_export.resolve_pointer({"a": [5, 6]}, "/a/1") == 6
    assert web_export.resolve_pointer([1], "") == [1]


def test_resolve_pointer_rejects_invalid_array_index():
    with pytest.raises(ValueError):
        web_export.resolve_pointer(["value"], "/01")


def test_resolve_pointer_rejects_missing_object_key():
    with pytest.raises(KeyError):
        web_export.resolve_pointer({"present": True}, "/missing")


def test_resolve_pointer_rejects_pointer_without_leading_slash():
    with pytest.raises(ValueError):
        web_export.resolve_pointer({"a": 1}, "a")


def test_resolve_pointer_rejects_descending_into_scalar():
    with pytest.raises(ValueError):
        web_export.resolve_pointer({"a": 1}, "/a/b")


def test_export_copies_only_selected_values(mini_root):
    assert not web_export.export_data(mini_root)
    result = json.loads((mini_root / "web/data/test.json").read_text())
    assert result["v"] == {"value": None, "source": "source.json#/key"}
    assert result["esc"] == {"value": 1, "source": "source.json#/a~1b/~0k"}
    assert "secret" not in json.dumps(result)
    written = {p.name for p in (mini_root / "web").rglob("*") if p.is_file()}
    assert written == {"test.json", "manifest.json", "meanings.json"}


def test_export_is_idempotent_and_check_does_not_write(mini_root):
    assert not web_export.export_data(mini_root, check=True)
    assert not (mini_root / "web").exists()
    web_export.export_data(mini_root)
    first = (mini_root / "web/data/manifest.json").read_bytes()
    assert web_export.export_data(mini_root, check=True)
    assert web_export.export_data(mini_root)
    assert (mini_root / "web/data/manifest.json").read_bytes() == first


def test_export_check_detects_stale_output(mini_root):
    web_export.export_data(mini_root)
    (mini_root / "research" / "source.json").write_text(
        '{"key": 2, "a/b": {"~k": 1}}'
    )
    assert not web_export.export_data(mini_root, check=True)


def test_export_rejects_names_outside_research(mini_root, monkeypatch):
    monkeypatch.setattr(web_export, "SELECTIONS", {
        "test.json": {"v": ("../data/secret.json", "/key")},
    })
    with pytest.raises(ValueError, match="research JSON"):
        web_export.export_data(mini_root)
    assert not (mini_root / "web").exists()


def test_export_fails_on_missing_pointer(mini_root, monkeypatch):
    monkeypatch.setattr(web_export, "SELECTIONS", {
        "test.json": {"v": ("source.json", "/absent")},
    })
    with pytest.raises(KeyError):
        web_export.export_data(mini_root)
    assert not (mini_root / "web").exists()


def test_manifest_records_hashes_and_allowlist(mini_root):
    web_export.export_data(mini_root)
    manifest = json.loads((mini_root / "web/data/manifest.json").read_text())
    expected = hashlib.sha256(
        (mini_root / "research/source.json").read_bytes()
    ).hexdigest()
    assert manifest["sources"]["source.json"] == expected
    assert manifest["commit"] == "unavailable"
    assert manifest["default_visible"] == sorted([
        "cubs_case.json#/as_of_date",
        "source.json#/a~1b/~0k",
        "source.json#/key",
    ])


def test_selections_read_only_research_files():
    for group in web_export.SELECTIONS.values():
        for filename, pointer in group.values():
            assert "/" not in filename and filename.endswith(".json")
            assert (REPO / "research" / filename).is_file()
            assert pointer.startswith("/")


def test_committed_export_is_current():
    assert web_export.export_data(check=True), (
        "web/data is stale; run python3 -m cubs_edge_lab.web_export"
    )


def test_web_data_is_not_ignored_by_git():
    files = [p for p in (REPO / "web/data").rglob("*") if p.is_file()]
    assert files
    for path in files:
        result = subprocess.run(
            ["git", "check-ignore", "-q", str(path.relative_to(REPO))],
            cwd=REPO,
        )
        assert result.returncode == 1, f"web data ignored: {path}"


def test_local_data_remains_ignored_by_git():
    paths = ["data/raw", "data/processed", "data/cache"]
    for path in paths:
        result = subprocess.run(
            ["git", "check-ignore", "-q", path], cwd=REPO
        )
        assert result.returncode == 0, f"local data not ignored: {path}"


def test_exported_meaning_map_covers_verdicts():
    meanings = json.loads((REPO / "web/data/meanings.json").read_text())
    expected = {
        "NEGATIVE", "PARTIAL", "EXPLORATORY", "Test not run (early stop)"
    }
    assert set(meanings) == expected
    assert meanings["NEGATIVE"] == APPROVED_NEGATIVE_MEANING
    overview = json.loads((REPO / "web/data/overview.json").read_text())
    verdicts = {overview[name]["value"] for name in (
        "sendhold_verdict", "sendhold_v2_verdict"
    )}
    assert verdicts <= set(meanings)


def test_manifest_hashes_and_allowlist():
    manifest = json.loads((REPO / "web/data/manifest.json").read_text())
    for name, expected in manifest["sources"].items():
        digest = hashlib.sha256(
            (REPO / "research" / name).read_bytes()
        ).hexdigest()
        assert digest == expected
    visible = manifest["default_visible"]
    assert visible == sorted(set(visible))
    assert visible == web_export.default_visible(web_export.SELECTIONS)
    assert not any(p.startswith("data/") for p in visible)
    assert not any(t in p.lower() for p in visible for t in HIDDEN_TERMS)
    assert {p.split("#")[0] for p in visible} <= set(manifest["sources"])
