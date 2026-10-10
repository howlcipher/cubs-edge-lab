"""Unit and drift checks for the research-to-web export boundary."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from cubs_edge_lab import web_export

REPO = Path(__file__).resolve().parents[1]
HIDDEN_TERMS = ("p_safe", "predicted", "flagged")
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
    assert not any("mean_p_safe" in p for p in visible)
    assert {p.split("#")[0] for p in visible} <= set(manifest["sources"])


def test_sendhold_default_visible_allowlist_is_narrow():
    """Model values stay hidden except in the elements the spec names."""
    visible = web_export.DEFAULT_VISIBLE
    fit = [p for p in visible if p.startswith("sendhold_fit.json#")]
    assert fit
    allowed_fit = (
        "#/fit_season", "#/unknown/",
        "#/versions/v2/label_counts/", "#/versions/v3/label_counts/",
        "#/versions/v3/decision_chart/",
    )
    assert all(any(token in p for token in allowed_fit) for p in fit)
    cell_fields = {
        "zone_group", "hit_type", "outs", "speed_tercile", "n", "n_sent",
        "observed_send_success", "p_star", "low_n",
    }
    for pointer in fit:
        if "/decision_chart/cells/" in pointer:
            assert pointer.rsplit("/", 1)[1] in cell_fields, pointer
    # Runs left is shown only as the four gating-dependent criteria rows.
    runs = [p for p in visible if "runs_left" in p]
    assert runs and all(
        p.startswith("sendhold_experiment.json#/analyses/")
        and "/criteria/runs_left_excludes_zero/" in p
        for p in runs
    )
    forbidden = ("/point_2026", "/cubs", "flagged", "mean_predicted")
    assert not any(t in p for p in visible for t in forbidden)
    negative_control = [p for p in visible if "/negative_control/" in p]
    assert {p.rsplit("/", 1)[1] for p in negative_control} <= {
        "realized_success", "passed", "rule", "lower", "upper",
    }


def test_sendhold_roles_are_fixed_display_copy():
    assert web_export.ROLES == {
        "brier_beats_constant": "gating",
        "calibration_slope": "gating",
        "negative_control": "control",
        "runs_left_excludes_zero": (
            "effect (only read when the gating criteria are met)"
        ),
    }
    assert set(web_export.ROLES) == set(web_export.CRITERIA)


def test_verbatim_quotes_are_exact_lines():
    for filename, number, expected in web_export.VERBATIM_LINES.values():
        lines = (REPO / "research" / filename).read_text().splitlines()
        assert lines[number - 1] == expected


def test_export_fails_when_a_quoted_line_drifts(tmp_path, monkeypatch):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "cubs_case.json").write_text(
        '{"as_of_date": "2026-10-09"}'
    )
    (tmp_path / "research" / "source.json").write_text('{"key": 1}')
    (tmp_path / "research" / "QUOTE.md").write_text(
        "INFERENCE: moved\nUNKNOWN: a line\n"
    )
    monkeypatch.setattr(web_export, "SELECTIONS", {
        "sendhold.json": {"v": ("source.json", "/key")},
    })
    monkeypatch.setattr(web_export, "VERBATIM_LINES", {
        "quote": ("QUOTE.md", 2, "UNKNOWN: a line"),
    })
    assert not web_export.export_data(tmp_path)
    copied = json.loads((tmp_path / "web/data/sendhold.json").read_text())
    assert copied["quote"] == {
        "value": "UNKNOWN: a line", "source": "QUOTE.md#L2",
    }
    monkeypatch.setattr(web_export, "VERBATIM_LINES", {
        "quote": ("QUOTE.md", 2, "UNKNOWN: a changed line"),
    })
    with pytest.raises(ValueError, match="Research line changed"):
        web_export.export_data(tmp_path)
    monkeypatch.setattr(web_export, "VERBATIM_LINES", {
        "quote": ("QUOTE.md", 3, "UNKNOWN: a line"),
    })
    with pytest.raises(ValueError, match="Research line changed"):
        web_export.export_data(tmp_path)


def test_milbfa_lines_are_exact_research_lines():
    assert {n for _, n, _ in web_export.MILBFA_LINES.values()} == {
        39, 40, 46, 47
    }
    for filename, number, expected in web_export.MILBFA_LINES.values():
        lines = (REPO / "research" / filename).read_text().splitlines()
        assert lines[number - 1] == expected
    exported = json.loads((REPO / "web/data/milbfa.json").read_text())
    for name, (filename, number, expected) in (
        web_export.MILBFA_LINES.items()
    ):
        assert exported[name] == {
            "value": expected, "source": f"{filename}#L{number}",
        }


def test_export_fails_when_a_milbfa_line_drifts(tmp_path, monkeypatch):
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "cubs_case.json").write_text(
        '{"as_of_date": "2026-10-09"}'
    )
    (tmp_path / "research" / "source.json").write_text('{"key": 1}')
    (tmp_path / "research" / "QUOTE.md").write_text("first\nsecond\n")
    monkeypatch.setattr(web_export, "SELECTIONS", {
        "milbfa.json": {"v": ("source.json", "/key")},
    })
    monkeypatch.setattr(web_export, "MILBFA_LINES", {
        "quote": ("QUOTE.md", 2, "second"),
    })
    assert not web_export.export_data(tmp_path)
    copied = json.loads((tmp_path / "web/data/milbfa.json").read_text())
    assert copied["quote"] == {"value": "second", "source": "QUOTE.md#L2"}
    for line in ((2, "second changed"), (3, "second")):
        monkeypatch.setattr(web_export, "MILBFA_LINES", {
            "quote": ("QUOTE.md", *line),
        })
        with pytest.raises(ValueError, match="Research line changed"):
            web_export.export_data(tmp_path)


def test_milbfa_json_is_not_written_when_unselected(mini_root):
    web_export.export_data(mini_root)
    assert not (mini_root / "web/data/milbfa.json").exists()


def test_milbfa_selections_expose_no_player_level_pointers():
    selected = web_export.SELECTIONS["milbfa.json"]
    pointers = [pointer for _, pointer in selected.values()]
    assert pointers
    for pointer in pointers:
        assert "/examples" not in pointer
        assert "/cohorts" not in pointer
        assert "person" not in pointer
        assert "/calibration" not in pointer
    exported = json.loads((REPO / "web/data/milbfa.json").read_text())
    for entry in exported.values():
        assert "/examples" not in entry["source"]
        assert "person" not in entry["source"]


def test_milbfa_pointers_are_default_visible_and_resolve():
    visible = set(web_export.DEFAULT_VISIBLE)
    exported = json.loads((REPO / "web/data/milbfa.json").read_text())
    for name, (filename, pointer) in (
        web_export.SELECTIONS["milbfa.json"].items()
    ):
        assert f"{filename}#{pointer}" in visible
        document = json.loads((REPO / "research" / filename).read_text())
        assert exported[name]["value"] == web_export.resolve_pointer(
            document, pointer
        )
    selected = web_export.SELECTIONS["milbfa.json"]
    assert selected["method_status"] == (
        "cubs_case.json", "/method_status"
    )
    assert selected["early_stop_reason"] == (
        "validation.json", "/early_stop_reason"
    )
    assert selected["holdout_excluded"] == (
        "exploratory_whole_pool.json", "/config/holdout_excluded"
    )
    assert selected["comparator"] == (
        "exploratory_whole_pool.json", "/comparator"
    )
    assert selected["validation_year"] == (
        "exploratory_whole_pool.json", "/config/validation_year"
    )


def test_method_status_wording_is_the_early_stop_label():
    case = json.loads((REPO / "research/cubs_case.json").read_text())
    validation = json.loads((REPO / "research/validation.json").read_text())
    assert validation["early_stop"] is True
    assert validation["validation"] is None
    assert case["method_status"] == (
        "was not tested (pre-registered early stop)"
    )


def test_sendhold_selections_cover_each_analysis_and_label_version():
    selected = web_export.SELECTIONS["sendhold.json"]
    for analysis in web_export.ANALYSES:
        assert selected[f"{analysis}_verdict"][1].endswith(
            f"/{analysis}/verdict"
        )
        assert selected[f"{analysis}_label_version"][1].endswith(
            f"/{analysis}/label_version"
        )
        for criterion in web_export.CRITERIA:
            for field in ("estimate", "passed", "rule", "lower", "upper"):
                assert f"{analysis}_{criterion}_{field}" in selected
    assert selected["fit_season"] == ("sendhold_fit.json", "/fit_season")
