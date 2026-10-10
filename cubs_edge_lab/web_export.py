"""Export the read-only explorer's selected research values."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RESEARCH = ROOT / "research"
OUTPUT = ROOT / "web" / "data"

# Values are copied by pointer only. Display copy is deliberately outside this
# map so the export cannot silently derive or reinterpret a research value.
SELECTIONS = {
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


def default_visible(selections: dict[str, dict[str, Any]]) -> list[str]:
    """Return the sorted, de-duplicated pointers a page may display."""
    pointers = {
        f"{filename}#{pointer}"
        for group in selections.values()
        for filename, pointer in group.values()
    }
    pointers.add(f"{FOOTER_SOURCE[0]}#{FOOTER_SOURCE[1]}")
    return sorted(pointers)


DEFAULT_VISIBLE = default_visible(SELECTIONS)


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


def research_path(root: Path, filename: str) -> Path:
    """Return one research JSON file, never a path outside research/."""
    if Path(filename).name != filename or not filename.endswith(".json"):
        raise ValueError(f"Not a research JSON name: {filename}")
    return root / "research" / filename


def export_data(root: Path = ROOT, *, check: bool = False) -> bool:
    """Write selected source values and a reproducible provenance manifest."""
    sources: dict[str, dict[str, Any]] = {}
    outputs: dict[str, dict[str, Any]] = {}
    for output_name, selections in SELECTIONS.items():
        entries = {}
        for name, (filename, pointer) in selections.items():
            source_path = research_path(root, filename)
            if filename not in sources:
                sources[filename] = json.loads(source_path.read_text())
            value = resolve_pointer(sources[filename], pointer)
            entries[name] = {"value": value, "source": f"{filename}#{pointer}"}
        outputs[output_name] = entries

    footer_file, footer_pointer = FOOTER_SOURCE
    if footer_file not in sources:
        source_path = research_path(root, footer_file)
        sources[footer_file] = json.loads(source_path.read_text())

    hashes = {}
    for filename in sorted(sources):
        source_bytes = research_path(root, filename).read_bytes()
        hashes[filename] = hashlib.sha256(source_bytes).hexdigest()
    # The last commit touching research/, not HEAD: committing the derived
    # web/data must not make the committed export look stale.
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(root), "log", "-1", "--format=%H",
             "--", "research"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip() or "unavailable"
    except (OSError, subprocess.CalledProcessError):
        commit = "unavailable"
    outputs["manifest.json"] = {
        "commit": commit,
        "as_of_date": resolve_pointer(sources[footer_file], footer_pointer),
        "as_of_source": f"{footer_file}#{footer_pointer}",
        "sources": hashes,
        "default_visible": default_visible(SELECTIONS),
    }
    outputs["meanings.json"] = MEANINGS

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
