"""Export the read-only explorer's selected research values."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RESEARCH = ROOT / "research"
OUTPUT = ROOT / "web" / "data"

# Values are copied by pointer only. Display copy is deliberately outside this
# map so the export cannot silently derive or reinterpret a research value.
SELECTIONS = {
    "sendhold.json": {},
    "overview.json": {
        "sendhold_verdict": ("sendhold_experiment.json", "/verdict"),
        "sendhold_v2_verdict": (
            "sendhold_experiment.json", "/verdict_v2_preregistered_definition"
        ),
        "triage_status": ("cubs_case.json", "/method_status"),
        "triage_meaning": ("cubs_case.json", "/interpretation"),
        "early_stop": ("validation.json", "/early_stop"),
        "early_stop_reason": ("validation.json", "/early_stop_reason"),
    },
    "milbfa.json": {},
    "about.json": {
        "request_count": ("sendhold_feasibility.json", "/new_requests_used"),
        "request_ceiling": ("sendhold_feasibility.json", "/ceiling"),
        "full_request_estimate": (
            "sendhold_feasibility.json", "/full_retrieval_request_estimate"
        ),
        "source_names": ("exploratory_whole_pool.json", "/config/source"),
        "triage_source": ("cubs_case.json", "/source"),
    },
}
# The dynamic groups below are expanded from research files at import time for
# the checked-in root. Keep their unexpanded templates for exports from other
# roots.
SELECTION_TEMPLATES = {
    name: dict(group) for name, group in SELECTIONS.items()
}

ANALYSES = (
    "v3_primary", "v2_preregistered", "v3_ambiguous_as_safe",
    "v3_fallback_dropped",
)
CRITERIA = {
    "brier_beats_constant": ("Brier vs constant", "difference"),
    "calibration_slope": ("Calibration slope", "slope"),
    "runs_left_excludes_zero": ("Runs left", "estimate"),
    "negative_control": ("Negative control", "realized_success"),
}


def add_sendhold_selections(
    root: Path = ROOT, selected: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Declare the exact numeric and verdict pointers shown on Send / hold.

    Label and cell lists are enumerated from the research files under
    ``root``, never from the module-level checkout.
    """
    if selected is None:
        selected = SELECTIONS["sendhold.json"]

    def add(name: str, filename: str, pointer: str) -> None:
        selected[name] = (filename, pointer)

    add("verdict", "sendhold_experiment.json", "/verdict")
    add(
        "verdict_v2", "sendhold_experiment.json",
        "/verdict_v2_preregistered_definition",
    )
    add("feasibility_verdict", "sendhold_feasibility.json", "/verdict")
    for field in ("verdict_reason", "new_requests_used", "ceiling"):
        add(field, "sendhold_feasibility.json", f"/{field}")
    experiment = json.loads(
        research_path(root, "sendhold_experiment.json").read_text()
    )
    for analysis in ANALYSES:
        base = f"/analyses/{analysis}"
        add(
            f"{analysis}_verdict", "sendhold_experiment.json",
            f"{base}/verdict",
        )
        for criterion, (_, estimate) in CRITERIA.items():
            path = f"{base}/criteria/{criterion}"
            for field, pointer in (
                ("estimate", f"{path}/{estimate}"),
                ("passed", f"{path}/passed"), ("rule", f"{path}/rule"),
                ("lower", f"{path}/interval_95/lower"),
                ("upper", f"{path}/interval_95/upper"),
            ):
                add(
                    f"{analysis}_{criterion}_{field}",
                    "sendhold_experiment.json", pointer,
                )
        add(
            f"{analysis}_label_version", "sendhold_experiment.json",
            f"{base}/label_version",
        )
        for label in experiment["analyses"][analysis]["label_counts_2025"]:
            add(
                f"{analysis}_labels_2025_{label}", "sendhold_experiment.json",
                f"{base}/label_counts_2025/{label}",
            )
    for field in ("sent_out", "required_sent_out"):
        add(
            f"covariate_{field}", "sendhold_experiment.json",
            f"/analyses/v3_primary/covariate_choice/{field}",
        )
    fit = json.loads(research_path(root, "sendhold_fit.json").read_text())
    add("fit_season", "sendhold_fit.json", "/fit_season")
    # Label counts are published maps; each count is selected independently.
    for version, value in fit["versions"].items():
        for label in value["label_counts"]:
            add(
                f"fit_{version}_label_{label}", "sendhold_fit.json",
                f"/versions/{version}/label_counts/{label}",
            )
    for index, _ in enumerate(fit["unknown"]):
        add(f"fit_unknown_{index}", "sendhold_fit.json", f"/unknown/{index}")
    chart = fit["versions"]["v3"]["decision_chart"]
    add(
        "min_cell_n", "sendhold_fit.json",
        "/versions/v3/decision_chart/min_cell_n",
    )
    for index, _ in enumerate(chart["speed_tercile_cuts"]):
        add(
            f"speed_cut_{index}", "sendhold_fit.json",
            f"/versions/v3/decision_chart/speed_tercile_cuts/{index}",
        )
    columns = (
        "zone_group", "hit_type", "outs", "speed_tercile", "n", "n_sent",
        "observed_send_success", "p_star", "low_n",
    )
    for index, _ in enumerate(chart["cells"]):
        for column in columns:
            add(
                f"cell_{index}_{column}", "sendhold_fit.json",
                f"/versions/v3/decision_chart/cells/{index}/{column}",
            )
    return selected


def research_path(root: Path, filename: str) -> Path:
    """Return one research JSON file, never a path outside research/."""
    if Path(filename).name != filename or not filename.endswith(".json"):
        raise ValueError(f"Not a research JSON name: {filename}")
    return root / "research" / filename


add_sendhold_selections()

WHOLE_POOL = "exploratory_whole_pool.json"
POOL_BASE = "/validation/whole_pool"
RANKINGS = ("B0", "B1", "B2", "P", "M")
BASELINES = ("B0", "B1", "B2", "P")
TOP_K = ("25", "50", "100")


def add_milbfa_selections(
    root: Path = ROOT, selected: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Declare the pointers shown on Free-agent triage. No player rows."""
    if selected is None:
        selected = SELECTIONS["milbfa.json"]

    def add(name: str, filename: str, pointer: str) -> None:
        selected[name] = (filename, pointer)

    add("method_status", "cubs_case.json", "/method_status")
    add("early_stop", "validation.json", "/early_stop")
    add("early_stop_reason", "validation.json", "/early_stop_reason")
    add("holdout_excluded", WHOLE_POOL, "/config/holdout_excluded")
    add("validation_year", WHOLE_POOL, "/config/validation_year")
    add("comparator", WHOLE_POOL, "/comparator")
    for index in range(len(TOP_K)):
        add(f"top_k_{index}", WHOLE_POOL, f"/config/top_k/{index}")
    for field in ("n", "positives", "base_rate"):
        add(field, WHOLE_POOL, f"{POOL_BASE}/{field}")
    for ranking in RANKINGS:
        path = f"{POOL_BASE}/rankings/{ranking}"
        add(f"{ranking}_auroc", WHOLE_POOL, f"{path}/auroc")
        for cutoff in TOP_K:
            for field in ("hits", "precision"):
                add(
                    f"{ranking}_top_{cutoff}_{field}", WHOLE_POOL,
                    f"{path}/top_k/{cutoff}/{field}",
                )
    for baseline in BASELINES:
        path = f"{POOL_BASE}/bootstrap_m_minus_baseline/{baseline}"
        add(f"boot_{baseline}_mean", WHOLE_POOL, f"{path}/mean_difference")
        add(f"boot_{baseline}_lower", WHOLE_POOL, f"{path}/percentile_95/0")
        add(f"boot_{baseline}_upper", WHOLE_POOL, f"{path}/percentile_95/1")
        add(f"boot_{baseline}_resamples", WHOLE_POOL, f"{path}/resamples")
    add("interpretation", "cubs_case.json", "/interpretation")
    add("signing_window", "cubs_case.json", "/signing_window")
    add("threshold_pa", "cubs_case.json", "/thresholds/pa")
    add("threshold_ip", "cubs_case.json", "/thresholds/ip")
    case = json.loads(research_path(root, "cubs_case.json").read_text())
    # Lists are selected element by element so each item keeps its own source.
    for index, _ in enumerate(case["cohort_years"]):
        add(f"cohort_year_{index}", "cubs_case.json", f"/cohort_years/{index}")
    for index, _ in enumerate(case["unknowns"]):
        add(f"unknown_{index}", "cubs_case.json", f"/unknowns/{index}")
    return selected


def build_selections(root: Path) -> dict[str, dict[str, Any]]:
    """Return every selection group, enumerated from ``root``'s research."""
    built = {
        name: dict(group) for name, group in SELECTION_TEMPLATES.items()
    }
    built["sendhold.json"] = add_sendhold_selections(root, {})
    built["milbfa.json"] = add_milbfa_selections(root, {})
    return built


add_milbfa_selections()

# Quoted by exact line match: the export fails if the line moved or changed.
VERBATIM_LINES = {
    "unknown_line_0": (
        "SENDHOLD_EXPERIMENT.md", 90,
        "UNKNOWN: Whether held runners would have been safe if sent; the "
        "feed does not record the coach's sign, the runner's jump, or the "
        "counterfactual.",
    ),
    "unknown_line_1": (
        "SENDHOLD_EXPERIMENT.md", 91,
        "UNKNOWN: Trailing runners and later events are ignored in the "
        "run-value accounting.",
    ),
    "inference_line": (
        "SENDHOLD_EXPERIMENT.md", 6,
        "INFERENCE: Any positive estimate is upper-bound-style: sends are "
        "selected and the counterfactual for holds is extrapolated.",
    ),
}

MILBFA_LINES = {
    "banner_line_0": (
        "EXPERIMENT.md", 46,
        "EXPLORATORY FACT: Source attribution: MLBAM, MLB Stats API. Only "
        "cohort aggregates are reported.",
    ),
    "banner_line_1": (
        "EXPERIMENT.md", 47,
        "EXPLORATORY FACT: This section supports no usefulness claim or "
        "recommendation.",
    ),
    "limit_unknown_line": (
        "EXPERIMENT.md", 39,
        "UNKNOWN: Validation metrics, bootstrap intervals, and comparator "
        "selection are null after early stop.",
    ),
    "limit_inference_line": (
        "EXPERIMENT.md", 40,
        "INFERENCE: The persistence ranking can be nearly degenerate in the "
        "primary segment because players in that segment had no MLB "
        "appearance in season Y.",
    ),
}

FOOTER_SOURCE = ("cubs_case.json", "/as_of_date")
MEANINGS = {
    "NEGATIVE": (
        "No measurable improvement over a simple baseline was shown. "
        "This does not show the opposite."
    ),
    "PARTIAL": (
        "Some evidence supports the approach, but the result is incomplete."
    ),
    "EXPLORATORY": (
        "This result is exploratory and does not establish a confirmed effect."
    ),
    "Test not run (early stop)": "Test not run (early stop)",
}
ROLES = {
    "brier_beats_constant": "gating",
    "calibration_slope": "gating",
    "negative_control": "control",
    "runs_left_excludes_zero": (
        "effect (only read when the gating criteria are met)"
    ),
}


def default_visible(
    selections: dict[str, dict[str, Any]], disclosed: Iterable[str] = ()
) -> list[str]:
    """Return the sorted pointers rendered visibly by default.

    Pointers shown only inside a closed disclosure are excluded.
    """
    pointers = {
        f"{filename}#{pointer}"
        for group in selections.values()
        for filename, pointer in group.values()
    }
    pointers.add(f"{FOOTER_SOURCE[0]}#{FOOTER_SOURCE[1]}")
    return sorted(pointers - set(disclosed))


def disclosed_only(
    selections: dict[str, dict[str, Any]], root: Path = ROOT
) -> list[str]:
    """Return the sorted pointers rendered only inside a closed <details>.

    Under a NEGATIVE analysis verdict the Runs left estimate, interval and
    Met / Not met are shown only after the reader opens the disclosure.
    """
    group = selections.get("sendhold.json", {})
    hidden = set()
    for analysis in ANALYSES:
        if f"{analysis}_verdict" not in group:
            continue
        filename, pointer = group[f"{analysis}_verdict"]
        document = json.loads(research_path(root, filename).read_text())
        if resolve_pointer(document, pointer) != "NEGATIVE":
            continue
        for field in ("estimate", "lower", "upper", "passed"):
            entry = group.get(f"{analysis}_runs_left_excludes_zero_{field}")
            if entry:
                hidden.add(f"{entry[0]}#{entry[1]}")
    return sorted(hidden)


def resolve_pointer(document: Any, pointer: str) -> Any:
    """Resolve an RFC 6901 JSON pointer, including escaped object keys."""
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError(f"Invalid JSON pointer: {pointer}")
    value = document
    for raw_part in pointer[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            if not part.isdigit() or (len(part) > 1 and part.startswith("0")):
                message = f"Invalid array index in JSON pointer: {pointer}"
                raise ValueError(message)
            value = value[int(part)]
        elif isinstance(value, dict):
            value = value[part]
        else:
            raise ValueError(f"Cannot resolve JSON pointer: {pointer}")
    return value


DISCLOSED_ONLY = disclosed_only(SELECTIONS)
DEFAULT_VISIBLE = default_visible(SELECTIONS, DISCLOSED_ONLY)


def read_verbatim_lines(
    root: Path, quoted: dict[str, tuple[str, int, str]]
) -> dict[str, dict[str, str]]:
    """Copy research Markdown lines, failing if one moved or changed."""
    entries = {}
    for name, (filename, line_number, expected) in quoted.items():
        if Path(filename).name != filename or not filename.endswith(".md"):
            raise ValueError(f"Not a research Markdown name: {filename}")
        lines = (root / "research" / filename).read_text().splitlines()
        if line_number > len(lines) or lines[line_number - 1] != expected:
            message = f"Research line changed: {filename}:{line_number}"
            raise ValueError(message)
        entries[name] = {
            "value": lines[line_number - 1],
            "source": f"{filename}#L{line_number}",
        }
    return entries


def research_digest(root: Path = ROOT) -> str:
    """SHA-256 over every file under research/, read from the working tree.

    The digest covers the sorted lines "<path relative to research/> <sha256
    of the file's bytes>\\n". It needs no git and excludes nothing, so any
    change to any research file changes it.
    """
    base = root / "research"
    lines = sorted(
        f"{path.relative_to(base).as_posix()} "
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}\n"
        for path in base.rglob("*") if path.is_file()
    )
    return hashlib.sha256("".join(lines).encode()).hexdigest()


def export_data(
    root: Path = ROOT, *, check: bool = False,
    selections: dict[str, dict[str, Any]] | None = None,
) -> bool:
    """Write selected source values and a reproducible provenance manifest.

    By default, selection lists are enumerated from ``root``. Pass
    ``selections`` only when a caller needs an explicit selection map.
    """
    if selections is None:
        selections = build_selections(root)
    sources: dict[str, dict[str, Any]] = {}
    outputs: dict[str, dict[str, Any]] = {}
    for output_name, group in selections.items():
        entries = {}
        for name, (filename, pointer) in group.items():
            source_path = research_path(root, filename)
            if filename not in sources:
                sources[filename] = json.loads(source_path.read_text())
            value = resolve_pointer(sources[filename], pointer)
            entries[name] = {"value": value, "source": f"{filename}#{pointer}"}
        outputs[output_name] = entries

    markdown = set()
    for output_name, quoted in (
        ("sendhold.json", VERBATIM_LINES), ("milbfa.json", MILBFA_LINES),
    ):
        if output_name in outputs:
            outputs[output_name].update(read_verbatim_lines(root, quoted))
            markdown.update(filename for filename, _, _ in quoted.values())

    footer_file, footer_pointer = FOOTER_SOURCE
    if footer_file not in sources:
        source_path = research_path(root, footer_file)
        sources[footer_file] = json.loads(source_path.read_text())

    hashes = {}
    # Quoted Markdown is hashed too, so an edit to an unquoted line shows.
    for filename in sorted(set(sources) | markdown):
        source_bytes = (root / "research" / filename).read_bytes()
        hashes[filename] = hashlib.sha256(source_bytes).hexdigest()
    disclosed = disclosed_only(selections, root)
    outputs["manifest.json"] = {
        "research_digest": research_digest(root),
        "as_of_date": resolve_pointer(sources[footer_file], footer_pointer),
        "as_of_source": f"{footer_file}#{footer_pointer}",
        "sources": hashes,
        "default_visible": default_visible(selections, disclosed),
        "disclosed_only": disclosed,
    }
    outputs["meanings.json"] = MEANINGS
    if "sendhold.json" in selections:
        outputs["roles.json"] = ROLES

    changed = False
    for filename, data in outputs.items():
        path = root / "web" / "data" / filename
        rendered = (
            json.dumps(
                data, ensure_ascii=False, indent=2, sort_keys=True
            ) + "\n"
        )
        if not path.exists() or path.read_text() != rendered:
            changed = True
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(rendered)
    return not changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="fail if export is stale"
    )
    args = parser.parse_args()
    current = export_data(check=args.check)
    if args.check and not current:
        raise SystemExit(
            "web/data is out of date; run python3 -m cubs_edge_lab.web_export"
        )


if __name__ == "__main__":
    main()
