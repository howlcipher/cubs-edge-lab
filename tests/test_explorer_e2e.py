"""Registry-driven checks for the static results explorer.

A new page registers itself with one ``Page(...)`` line in ``PAGES``; the
number scan, footer, network, keyboard and viewport tests then cover it.
"""

import json
import os
import re
import shutil
import subprocess
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import pytest

from cubs_edge_lab import web_export

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "web"
REQUIRE_E2E = os.environ.get("CUBS_REQUIRE_E2E") == "1"
WIDTHS = (320, 375, 1280)
MEANINGS = json.loads((WEB / "data" / "meanings.json").read_text())
SUPERSEDE = "later studies may supersede these results"
ATTRIBUTION = "MLB Advanced Media, L.P. (MLBAM)"
USAGE_QUOTE = "Only individual, non-commercial, non-bulk use"
PROVENANCE_KINDS = {
    "research-digest", "as-of", "source-hash", "prose-year", "prose-label",
    "format-note",
}
SMALL_NOTE = "small values shown to 2 significant figures"
FORMAT_NOTES = {
    "Values shown to two decimals (three for probabilities and rates); "
    f"{SMALL_NOTE}.",
    f"(shown to two decimals; {SMALL_NOTE})",
    f"(shown to three decimals; {SMALL_NOTE})",
}
ZERO_FORMS = {"0.00", "-0.00", "0.000", "-0.000", "-0"}
HIDDEN_TERMS = ("p_safe", "predicted", "flagged")


@dataclass(frozen=True)
class Page:
    path: str
    verdict: bool = False  # opens with verdict cards
    details: bool = False  # contains <details> elements
    stub: bool = False  # states "coming in a later version"


PAGES = [
    Page("/", verdict=True, details=True),
    Page("/about.html", details=True),
    Page("/sendhold.html", verdict=True, details=True),
    Page("/milbfa.html", details=True),
]
PAGE_IDS = [page.path for page in PAGES]


def load_manifest():
    return json.loads((WEB / "data" / "manifest.json").read_text())


def resolve_source(pointer):
    filename, json_pointer = pointer.split("#", 1)
    value = json.loads((REPO / "research" / filename).read_text())
    for part in json_pointer.lstrip("/").split("/"):
        if part:
            key = part.replace("~1", "/").replace("~0", "~")
            value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def is_small(value, kind="float"):
    """True when fixed decimals would print a non-zero float as zero."""
    if isinstance(value, list):
        return any(is_small(part, kind) for part in value)
    if not isinstance(value, float) or value.is_integer():
        return False
    return abs(value) < (0.0005 if kind in {"probability", "rate"} else 0.005)


def two_significant(value):
    """Two significant figures, half up, in plain decimal form."""
    exact = Decimal(abs(value))
    rounded = exact.quantize(
        Decimal(1).scaleb(exact.adjusted() - 1), rounding=ROUND_HALF_UP
    )
    if rounded.adjusted() > exact.adjusted():  # carry, e.g. 9.96e-5
        rounded = rounded.quantize(Decimal(1).scaleb(rounded.adjusted() - 1))
    return ("-" if value < 0 else "") + format(rounded, "f")


def display(value, kind="float", full=False):
    """Mirror web/format.js, including JavaScript's exact-value rounding."""
    if isinstance(value, list) and len(value) == 2:
        low = display(value[0], kind, full)
        high = display(value[1], kind, full)
        return f"{low} to {high}"
    if isinstance(value, str):
        return value
    if isinstance(value, bool) or value is None:
        return json.dumps(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if full:
            if value.is_integer():
                return str(int(value))
            return format(Decimal(repr(value)), "f")
        if value.is_integer():
            return str(int(value))
        decimals = 3 if kind in {"probability", "rate"} else 2
        if is_small(value, kind):
            return two_significant(value)
        rounded = Decimal(abs(value)).quantize(
            Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP
        )
        return ("-" if value < 0 else "") + f"{rounded:.{decimals}f}"
    return json.dumps(value)


def allowed_pointers(manifest):
    """Every pointer a page may render, visibly or inside a disclosure."""
    return set(manifest["default_visible"]) | set(manifest["disclosed_only"])


def assert_numeric_nodes(nodes, manifest):
    """Fail on any text containing a digit that is not traced to a source."""
    allowlist = allowed_pointers(manifest)
    hashes = {
        f"{name}: SHA-256 {digest}"
        for name, digest in manifest["sources"].items()
    }
    for node in nodes:
        text = node["text"]
        if node["source"]:
            assert node["source"] in allowlist, f"Hidden pointer: {text}"
            continue
        kind = node["provenance"]
        assert kind in PROVENANCE_KINDS, f"Untagged number: {text}"
        if kind == "research-digest":
            digest = manifest["research_digest"]
            assert text in {f"Research digest: {digest[:12]}", digest}, text
        elif kind == "source-hash":
            assert text in hashes, f"Unknown source hash: {text}"
        elif kind == "prose-year":
            assert re.fullmatch(r"(?:19|20)\d\d", text), f"Not a year: {text}"
        elif kind == "format-note":
            assert text in FORMAT_NOTES, f"Unknown format note: {text}"
        elif kind == "prose-label":
            assert text in {
                "v1", "v2", "v2-definition", "v3", "v2 pre-registered",
                "v3 primary", "v3 ambiguous as safe", "v3 fallback dropped",
                "95% interval", "2025", "R001", "B0", "B1", "B2",
            }, text
        else:
            raise AssertionError(f"Untagged number: {text}")


def scan_numbers(tab):
    manifest = load_manifest()
    allowlist = allowed_pointers(manifest)
    tagged = tab.evaluate(
        "() => [...document.querySelectorAll('[data-src]')].map("
        "e => ({src: e.dataset.src, text: e.textContent, "
        "format: e.dataset.format, kind: e.dataset.kind}))"
    )
    for item in tagged:
        assert item["src"] in allowlist, f"Not allowlisted: {item['src']}"
        assert item["src"].split("#")[0] in manifest["sources"]
        assert item["text"] == display(
            resolve_source(item["src"]), item["kind"] or "float",
            item["format"] == "full",
        )
        assert not any(t in item["src"].lower() for t in HIDDEN_TERMS)
    nodes = tab.evaluate("""() => {
      const walker = document.createTreeWalker(
        document.body, NodeFilter.SHOW_TEXT);
      const found = [];
      while (walker.nextNode()) {
        const text = walker.currentNode.nodeValue || '';
        if (!/\\d/.test(text)) continue;
        const parent = walker.currentNode.parentElement;
        const sourced = parent.closest('[data-src]');
        const provenance = parent.closest('[data-provenance]');
        found.push({text: text.trim(),
          source: sourced && sourced.dataset.src,
          provenance: provenance && provenance.dataset.provenance});
      }
      return found;
    }""")
    assert_numeric_nodes(nodes, manifest)


# ---- static checks (no browser) -------------------------------------------

def test_number_scan_rejects_untagged_number():
    manifest = load_manifest()
    untagged = [{"text": "2025", "source": None, "provenance": None}]
    with pytest.raises(AssertionError, match="Untagged number"):
        assert_numeric_nodes(untagged, manifest)
    unknown = [{"text": "7", "source": None, "provenance": "other"}]
    with pytest.raises(AssertionError, match="Untagged number"):
        assert_numeric_nodes(unknown, manifest)


@pytest.mark.parametrize(("value", "kind", "expected"), [
    (107, "float", "107"), (-5, "float", "-5"),
    (0.5, "float", "0.50"), (0.125, "float", "0.13"),
    (-0.125, "float", "-0.13"), (0.12345, "probability", "0.123"),
    (1, "probability", "1"), (-0.004, "float", "-0.0040"),
    ([-0.25, 0.125], "float", "-0.25 to 0.13"),
    (-0.000053, "float", "-0.000053"), (9.96e-5, "float", "0.00010"),
    (0.0049, "float", "0.0049"), (0.005, "float", "0.01"),
    (-0.005, "float", "-0.01"),
    (0.0004, "probability", "0.00040"), (0.00049, "probability", "0.00049"),
    (0.0005, "probability", "0.001"), (-0.0004, "rate", "-0.00040"),
    ([-0.00005, 0.00007], "float", "-0.000050 to 0.000070"),
    (0.0, "float", "0"), (5e-7, "float", "0.00000050"),
])
def test_display_format_vectors(value, kind, expected):
    assert display(value, kind) == expected


@pytest.mark.parametrize(("value", "expected"), [
    (0.1, "0.1"), (5e-7, "0.0000005"), (-5e-7, "-0.0000005"),
    (-6.319702746596795e-05, "-0.00006319702746596795"),
    (1.5e-10, "0.00000000015"), (2.0, "2"),
])
def test_display_full_precision(value, expected):
    assert display(value, full=True) == expected


def test_javascript_format_matches_python_mirror():
    node = shutil.which("node")
    if node is None:
        if REQUIRE_E2E:
            pytest.fail("CUBS_REQUIRE_E2E=1 but node is unavailable")
        pytest.skip("node is unavailable")
    vectors = [
        (107, "float"), (-5, "float"), (0.5, "float"),
        (0.125, "float"), (-0.125, "float"), (0.12345, "probability"),
        (1, "probability"), (-0.004, "float"),
        ([-0.25, 0.125], "float"), (0.1, "full"),
        (-0.000053, "float"), (9.96e-5, "float"), (0.0049, "float"),
        (0.005, "float"), (-0.005, "float"), (0.0, "float"),
        (0.0004, "probability"), (0.00049, "probability"),
        (0.0005, "probability"), (-0.0004, "rate"), (5e-7, "float"),
        ([-0.00005, 0.00007], "float"), (-6.3197e-05, "float"),
        (5e-7, "full"), (-5e-7, "full"), (1.5e-10, "full"),
        ([-5e-7, 5e-7], "full"), (2.0, "full"), (1e21, "full"),
    ]
    script = "import {formatValue, formatFull} from './web/format.js'; " \
        "const v = " + json.dumps(vectors) + "; " \
        "console.log(JSON.stringify(v.map(([x,k]) => " \
        "k === 'full' ? formatFull(x) : formatValue(x,k))));"
    actual = json.loads(subprocess.check_output(
        [node, "--input-type=module", "-e", script], cwd=REPO, text=True
    ))
    expected = [
        display(value, kind, kind == "full") for value, kind in vectors
    ]
    assert actual == expected


def test_number_scan_rejects_hidden_pointer_and_bad_provenance():
    manifest = load_manifest()
    hidden = [{"text": "0.4", "source": "sendhold_fit.json#/x",
               "provenance": None}]
    with pytest.raises(AssertionError, match="Hidden pointer"):
        assert_numeric_nodes(hidden, manifest)
    bad_year = [{"text": "12345", "source": None, "provenance": "prose-year"}]
    with pytest.raises(AssertionError, match="Not a year"):
        assert_numeric_nodes(bad_year, manifest)
    bad_hash = [{"text": "a.json: SHA-256 0", "source": None,
                 "provenance": "source-hash"}]
    with pytest.raises(AssertionError, match="Unknown source hash"):
        assert_numeric_nodes(bad_hash, manifest)


def test_sendhold_export_pointers_and_verbatim_lines():
    exported = json.loads((WEB / "data/sendhold.json").read_text())
    manifest = load_manifest()
    for name, item in exported.items():
        if name.startswith(("unknown_line_", "inference_line")):
            filename, line_number = item["source"].rsplit("#L", 1)
            source_path = REPO / "research" / filename
            source_lines = source_path.read_text().splitlines()
            source_line = source_lines[int(line_number) - 1]
            assert source_line == item["value"]
        else:
            assert item["source"] in allowed_pointers(manifest)
            assert item["value"] == resolve_source(item["source"])
    assert "mean_p_safe" not in json.dumps(exported)
    model_only = ("/point_2026/", "flagged_holds", "mean_predicted")
    assert not any(
        token in pointer
        for pointer in manifest["default_visible"]
        for token in model_only
    )
    assert not any(
        pointer.startswith("sendhold_fit.json#") and "/cubs_" in pointer
        for pointer in manifest["default_visible"]
    )
    assert not any(
        "flagged" in pointer for pointer in manifest["default_visible"]
    )


SENDHOLD_ANALYSES = (
    "v3_primary", "v2_preregistered", "v3_ambiguous_as_safe",
    "v3_fallback_dropped",
)
ROLE_BY_ROW = {
    "Brier vs constant": "gating",
    "Calibration slope": "gating",
    "Negative control": "control",
    "Runs left": "effect (only read when the gating criteria are met)",
}
HISTORY_URL = (
    "https://github.com/howlcipher/howl-cubs-dogfood/blob/main/"
    "experiments/R003-SENDHOLD-DESIGN.md"
)


def sendhold_data():
    return json.loads((WEB / "data/sendhold.json").read_text())


@pytest.mark.e2e
def test_sendhold_verdict_panel_content_and_order(open_page):
    data = sendhold_data()
    tab = open_page("/sendhold.html", 375)
    card = tab.locator(".card").first
    assert tab.locator(".card").count() == 1
    verdict = card.locator("[data-verdict]")
    assert verdict.locator("[data-src]").get_attribute("data-src") == (
        data["verdict"]["source"]
    )
    assert verdict.inner_text() == (
        f"Primary verdict: {data['verdict']['value']}"
    )
    meaning = card.locator("[data-meaning]")
    assert meaning.inner_text() == MEANINGS[data["verdict"]["value"]]
    secondary = card.locator("[data-secondary-verdict]")
    assert secondary.locator("[data-src]").get_attribute("data-src") == (
        data["verdict_v2"]["source"]
    )
    assert data["verdict_v2"]["value"] in secondary.inner_text()
    assert tab.evaluate(
        "([a, b]) => a.nextElementSibling === b",
        [verdict.element_handle(), meaning.element_handle()],
    )
    assert tab.evaluate(
        "([a, b]) => a.nextElementSibling === b",
        [meaning.element_handle(), secondary.element_handle()],
    )
    first_table = tab.locator("#sendhold table").first.bounding_box()
    assert secondary.bounding_box()["y"] < first_table["y"]
    assert tab.locator('[role="alert"]').count() == 0


@pytest.mark.e2e
def test_sendhold_sections_follow_the_specified_order(open_page):
    tab = open_page("/sendhold.html")
    order = tab.evaluate("""() => [...document.querySelectorAll(
      '#sendhold > section')].map(s => s.querySelector('h2, caption')
        .textContent.trim())""")
    assert order[0] == "Published verdicts"
    assert [t.endswith(("NEGATIVE", "PARTIAL")) for t in order[1:5]] == [
        True
    ] * 4
    assert order[5:] == [
        "Decision chart", "Label counts", "Feasibility",
        "Limits of this result",
    ]


@pytest.mark.e2e
def test_sendhold_unmapped_verdicts_show_alerts(open_page):
    data = sendhold_data()
    data["verdict"]["value"] = "UNMAPPED"
    data["verdict_v2"]["value"] = "UNMAPPED2"
    data["feasibility_verdict"]["value"] = "UNMAPPED3"
    tab = open_page("/sendhold.html", overrides={"data/sendhold.json": data})
    alerts = tab.locator('[role="alert"][data-error="missing-meaning"]')
    assert alerts.all_inner_texts() == [
        "No plain-language meaning is defined for verdict UNMAPPED.",
        "No plain-language meaning is defined for verdict UNMAPPED2.",
        "No plain-language meaning is defined for verdict UNMAPPED3.",
    ]
    assert MEANINGS["NEGATIVE"] not in tab.locator(".card").inner_text()
    assert tab.guard.errors == []


@pytest.mark.e2e
def test_sendhold_criteria_tables_match_published_values(open_page):
    data = sendhold_data()
    tab = open_page("/sendhold.html", 375)
    tables = tab.locator("#sendhold table")
    assert tables.count() == 6
    for index, analysis in enumerate(SENDHOLD_ANALYSES):
        table = tables.nth(index)
        verdict = data[f"{analysis}_verdict"]
        caption = table.locator("caption")
        assert caption.locator("[data-src]").get_attribute("data-src") == (
            verdict["source"]
        )
        assert caption.inner_text().endswith(f"verdict: {verdict['value']}")
        assert table.locator("th[scope='col']").count() == 5
        rows = table.locator("tbody tr").all()
        assert [r.locator("th[scope='row']").inner_text() for r in rows] == [
            "Brier vs constant", "Calibration slope", "Runs left",
            "Negative control",
        ]
        for row in rows:
            label = row.locator("th").inner_text()
            cells = row.locator("td")
            assert cells.nth(3).inner_text() == ROLE_BY_ROW[label]
            status = row.locator("[data-status-source]")
            passed = resolve_source(status.get_attribute("data-status-source"))
            assert status.text_content() == ("Met" if passed else "Not met")
            rule = cells.nth(2).locator("[data-src]")
            rule_source = rule.get_attribute("data-src")
            assert rule_source.endswith("/rule")
            assert rule.text_content() == resolve_source(rule_source)
            sources = [
                e.get_attribute("data-src")
                for e in cells.nth(0).locator("[data-src]").all()
                if e.get_attribute("data-format") == "display"
            ]
            assert len(sources) == 3, label
            assert sources[1].endswith("/interval_95/lower")
            assert sources[2].endswith("/interval_95/upper")
            runs = label == "Runs left"
            negative = verdict["value"] == "NEGATIVE"
            disclosure = cells.nth(0).locator(":scope > details")
            if runs and negative:
                assert cells.nth(0).inner_text().startswith(
                    "Not interpretable under the NEGATIVE verdict"
                )
                assert disclosure.locator(":scope > summary").inner_text() == (
                    "Failed-model value (not for decisions)"
                )
                assert disclosure.locator("[data-status-source]").count() == 1
                assert cells.nth(1).inner_text().strip() == ""
            else:
                assert "Not interpretable" not in cells.nth(0).inner_text()
                assert disclosure.filter(
                    has_text="Failed-model"
                ).count() == 0
                assert cells.nth(1).locator(
                    "[data-status-source]"
                ).count() == 1
        brier = rows[0].locator(".brier-note")
        assert brier.inner_text() == (
            "The model did not beat a constant guess; the interval includes "
            "zero, so this is no evidence of benefit, not evidence of harm. "
            "Passing diagnostic rows do not change the verdict."
        )
        assert table.locator(".brier-note").count() == 1
        footnote = table.locator("xpath=../following-sibling::p[1]")
        assert footnote.inner_text() == (
            "The verdict follows the pre-registered gating rule, not a "
            "count of passes."
        )


@pytest.mark.e2e
def test_sendhold_runs_left_row_for_a_non_negative_analysis(open_page):
    data = sendhold_data()
    data["v3_primary_verdict"]["value"] = "PARTIAL"
    tab = open_page("/sendhold.html", overrides={"data/sendhold.json": data})
    row = tab.locator("#sendhold table").first.locator("tbody tr").nth(2)
    assert "Not interpretable" not in row.inner_text()
    assert row.locator("td > details summary").filter(
        has_text="Failed-model"
    ).count() == 0
    status = row.locator("[data-status-source]")
    assert status.text_content() == "Met"


@pytest.mark.e2e
def test_sendhold_decision_table(open_page):
    data = sendhold_data()
    tab = open_page("/sendhold.html", 375)
    decision = tab.locator("#sendhold table").nth(4)
    caption = decision.locator("caption").inner_text()
    assert data["inference_line"]["value"] in caption
    assert (
        "Sends were selected by the coaches; observed success is not the "
        "success rate of held runners or of a different policy. Break-even "
        "p* is not a recommendation."
    ) in caption
    assert "derived from the 2025 run expectancy" in caption
    assert decision.locator("caption [data-quote-source]").get_attribute(
        "data-quote-source"
    ) == data["inference_line"]["source"]
    headers = decision.locator("th[scope='col']").all_inner_texts()
    assert headers == [
        "Zone group", "Hit type", "Outs", "Speed tercile", "n", "n sent",
        "Observed send success", "p* (2025 run expectancy)",
    ]
    cells = {
        int(k.split("_")[1]) for k in data
        if k.startswith("cell_") and k.endswith("_zone_group")
    }
    rows = decision.locator("tbody tr").all()
    assert len(rows) == len(cells) > 0
    low_rows = 0
    for index, row in enumerate(rows):
        sources = [
            e.get_attribute("data-src")
            for e in row.locator("[data-src][data-format='display']").all()
        ]
        assert sources == [
            data[f"cell_{index}_{field}"]["source"] for field in (
                "zone_group", "hit_type", "outs", "speed_tercile", "n",
                "n_sent", "observed_send_success", "p_star",
            )
        ]
        low = data[f"cell_{index}_low_n"]["value"]
        low_rows += bool(low)
        assert ("low n" in row.inner_text()) is bool(low)
    assert low_rows > 0
    section = decision.locator("xpath=ancestor::section[1]")
    metadata = section.locator("xpath=./p[1]")
    group = section.locator("xpath=./details[1]")
    assert tab.evaluate(
        "([p, d]) => p.nextElementSibling === d",
        [metadata.element_handle(), group.element_handle()],
    )
    # Each number appears once as display text and once in the group's
    # single disclosure.
    for key in ("min_cell_n", "speed_cut_0", "speed_cut_1"):
        selector = f'[data-src="{data[key]["source"]}"]'
        assert metadata.locator(selector).count() == 1
        assert group.locator(selector).count() == 1
    assert "mean_p_safe" not in decision.evaluate("e => e.outerHTML")
    wrap = tab.locator(".decision-table-wrap")
    assert wrap.evaluate("el => getComputedStyle(el).overflowX == 'auto'")
    assert wrap.evaluate("el => el.scrollWidth > el.clientWidth")
    assert wrap.get_attribute("tabindex") == "0"
    assert wrap.get_attribute("aria-label")


@pytest.mark.e2e
def test_sendhold_label_counts_name_version_and_season(open_page):
    data = sendhold_data()
    tab = open_page("/sendhold.html")
    table = tab.locator("#sendhold table").nth(5)
    assert table.locator("caption").inner_text() == (
        "Per-season label counts by label version"
    )
    rows = table.locator("tbody tr").all()
    assert len(rows) == 6
    expected_versions = [
        data[f"{analysis}_label_version"]["value"]
        for analysis in SENDHOLD_ANALYSES
    ] + ["v3", "v2"]
    for row, version in zip(rows, expected_versions):
        cells = row.locator("td")
        assert cells.nth(0).inner_text() == version
        assert cells.nth(1).inner_text() == "2025"
        for cell in cells.all()[2:]:
            source = cell.locator("[data-src]").first.get_attribute("data-src")
            assert resolve_source(source) == int(
                cell.locator("[data-src]").first.text_content()
            )
    fit_season = rows[4].locator("td").nth(1).locator("[data-src]").first
    assert fit_season.get_attribute("data-src") == data["fit_season"]["source"]
    assert "Total" not in table.inner_text()


@pytest.mark.e2e
def test_sendhold_feasibility_and_limits(open_page):
    data = sendhold_data()
    tab = open_page("/sendhold.html")
    feasibility = tab.locator("#sendhold section").filter(
        has=tab.locator("h2", has_text="Feasibility")
    )
    text = feasibility.inner_text()
    assert data["feasibility_verdict"]["value"] == "PARTIAL"
    assert MEANINGS["PARTIAL"] in text
    assert data["verdict_reason"]["value"] in text
    for key in ("new_requests_used", "ceiling"):
        assert feasibility.locator(
            f'[data-src="{data[key]["source"]}"]'
        ).count() >= 1
    limits = tab.locator("#limits")
    assert limits.count() == 1
    for key in ("unknown_line_0", "unknown_line_1"):
        quote = limits.locator(
            f'[data-quote-source="{data[key]["source"]}"]'
        )
        assert quote.inner_text() == data[key]["value"]
    assert data["fit_unknown_0"]["value"] in limits.inner_text()
    sent = data["covariate_sent_out"]["value"]
    required = data["covariate_required_sent_out"]["value"]
    assert (
        f"Reduced covariate set: {sent} of {required} required"
        in limits.inner_text()
    )
    for key in ("covariate_sent_out", "covariate_required_sent_out"):
        assert limits.locator(
            f'[data-src="{data[key]["source"]}"]'
        ).count() == 2
    link = limits.locator(f'a[href="{HISTORY_URL}"]')
    assert link.count() == 1
    assert limits.inner_text().count("Label history v1 to v3") == 1


@pytest.mark.e2e
def test_sendhold_hides_model_values_by_default(open_page):
    tab = open_page("/sendhold.html")
    sources = tab.evaluate(
        "() => [...document.querySelectorAll('[data-src]')]"
        ".map(e => e.dataset.src)"
    )
    assert sources
    for source in sources:
        assert "mean_p_safe" not in source
        assert "flagged" not in source
        assert "mean_predicted" not in source
        assert "/point_2026" not in source
    body = tab.locator("body").inner_text().lower()
    assert "mean_p_safe" not in body


@pytest.mark.e2e
def test_sendhold_runs_left_is_hidden_until_keyboard_disclosure(open_page):
    manifest = load_manifest()
    disclosed = set(manifest["disclosed_only"])
    tab = open_page("/sendhold.html")
    nodes = tab.locator(
        "#sendhold [data-src*='runs_left'], "
        "#sendhold [data-status-source*='runs_left']"
    )
    pointer = """el => el.dataset.src || el.dataset.statusSource"""
    hidden = [n for n in nodes.all() if n.evaluate(pointer) in disclosed]
    shown = [n for n in nodes.all() if n.evaluate(pointer) not in disclosed]
    assert hidden and shown
    # Every runs-left node under a NEGATIVE verdict is hidden on load, and
    # no hidden node is named by a pointer the manifest calls visible.
    for node in hidden:
        assert not node_is_visible(node), node.evaluate(pointer)
    # A non-negative analysis shows its displayed values (the full-value
    # copies stay inside their own closed disclosure).
    for node in shown:
        if node.get_attribute("data-format") in {"display", None}:
            assert node_is_visible(node), node.evaluate(pointer)
    summaries = tab.locator("summary").filter(
        has_text="Failed-model value (not for decisions)"
    )
    assert summaries.count() == len(
        [p for p in disclosed if p.endswith("/passed")]
    )
    for summary in summaries.all():
        summary.focus()
        tab.keyboard.press("Enter")
    for node in hidden:
        displayed = node.get_attribute("data-format") in {"display", None}
        # Opening the Failed-model disclosure reveals the display values;
        # the full-value copies sit in their own nested closed details.
        assert node_is_visible(node) == displayed, node.evaluate(pointer)


# Rendered, and not inside a closed <details> other than its own summary.
# The explicit ancestor walk does not depend on how the engine lays out a
# closed <details>; getClientRects guards the other direction.
VISIBLE_NODE = """el => {
  if (!el.getClientRects().length) return false;
  const style = getComputedStyle(el);
  if (style.visibility === 'hidden' || style.display === 'none') return false;
  let details = el.closest('details');
  while (details) {
    const summary = details.querySelector(':scope > summary');
    if (!details.open && !(summary && summary.contains(el))) return false;
    details = details.parentElement && details.parentElement.closest(
      'details');
  }
  return true;
}"""
POINTER_NODES = """() => [...document.querySelectorAll(
  '[data-src], [data-status-source]')].map(el => ({
  src: el.dataset.src || el.dataset.statusSource,
  text: el.textContent,
  visible: (""" + VISIBLE_NODE + """)(el)}))"""


def node_is_visible(node):
    """Visible with no closed <details> hiding it (summary stays visible)."""
    return node.evaluate(VISIBLE_NODE)


@pytest.mark.e2e
@pytest.mark.parametrize("page", PAGES, ids=PAGE_IDS)
def test_visible_nodes_are_default_visible_and_disclosed_are_hidden(
    page, open_page
):
    manifest = load_manifest()
    visible_pointers = set(manifest["default_visible"])
    disclosed = set(manifest["disclosed_only"])
    assert not visible_pointers & disclosed
    nodes = open_page(page.path).evaluate(POINTER_NODES)
    assert nodes
    for node in nodes:
        if node["visible"]:
            assert node["src"] in visible_pointers, node
        if node["src"] in disclosed:
            assert not node["visible"], node
    if page.path == "/sendhold.html":
        assert any(node["src"] in disclosed for node in nodes)
        assert any(node["visible"] for node in nodes)


@pytest.mark.e2e
@pytest.mark.parametrize("width", WIDTHS)
def test_sendhold_wide_tables_scroll_inside_their_containers(width, open_page):
    tab = open_page("/sendhold.html", width)
    wraps = tab.locator("#sendhold .table-wrap")
    assert wraps.count() == 6
    for wrap in wraps.all():
        assert wrap.evaluate(
            "el => getComputedStyle(el).overflowX !== 'visible'"
        )
        assert wrap.evaluate(
            "el => el.getBoundingClientRect().right <= innerWidth + 1"
        )


RANKINGS = ("B0", "B1", "B2", "P", "M")
BASELINES = ("B0", "B1", "B2", "P")
CUTOFFS = ("25", "50", "100")
FOLLOWS = """([a, b]) => !!(
  a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)"""


def milbfa_data():
    return json.loads((WEB / "data/milbfa.json").read_text())


def display_sources(scope):
    return [
        e.get_attribute("data-src")
        for e in scope.locator("[data-src][data-format='display']").all()
    ]


@pytest.mark.e2e
def test_milbfa_sections_follow_the_specified_order(open_page):
    tab = open_page("/milbfa.html")
    order = tab.evaluate("""() => [...document.querySelectorAll(
      '#milbfa > section')].map(s => s.querySelector('h2').textContent)""")
    assert order == [
        "Status", "Exploratory whole-pool results", "Cubs case",
        "Limits of this result",
    ]
    assert tab.locator('[role="alert"]').count() == 0


@pytest.mark.e2e
def test_milbfa_status_panel_precedes_the_first_table(open_page):
    tab = open_page("/milbfa.html", 375)
    status = tab.locator("#status")
    table = tab.locator("table").first
    assert tab.evaluate(
        FOLLOWS, [status.element_handle(), table.element_handle()]
    )
    assert tab.evaluate(
        "(el) => el === el.parentElement.firstElementChild",
        status.element_handle(),
    )
    s_box, t_box = status.bounding_box(), table.bounding_box()
    assert s_box["y"] + s_box["height"] <= t_box["y"] + 1


@pytest.mark.e2e
def test_milbfa_status_labels_are_distinct_and_sourced(open_page):
    data = milbfa_data()
    tab = open_page("/milbfa.html")
    method = tab.locator("#status [data-status='method']")
    assert method.inner_text() == (
        f"R001 method status: {data['method_status']['value']}"
    )
    assert method.locator("[data-src]").get_attribute("data-src") == (
        data["method_status"]["source"]
    )
    stop = tab.locator("#status [data-status='early-stop']")
    assert stop.inner_text() == (
        "Test not run (early stop): "
        f"{data['early_stop_reason']['value']}"
    )
    assert stop.locator("[data-src]").get_attribute("data-src") == (
        data["early_stop_reason"]["source"]
    )
    holdout = tab.locator("#status [data-status='holdout']")
    assert holdout.inner_text().startswith(
        f"Holdout untouched: {data['holdout_excluded']['value']}"
    )
    assert set(display_sources(holdout)) == {
        data["holdout_excluded"]["source"]
    }
    assert tab.locator("#status > p").count() == 3


@pytest.mark.e2e
def test_milbfa_missing_early_stop_meaning_shows_alert(open_page):
    meanings = dict(MEANINGS)
    del meanings["Test not run (early stop)"]
    tab = open_page(
        "/milbfa.html", overrides={"data/meanings.json": meanings}
    )
    alerts = tab.locator('[role="alert"][data-error="missing-meaning"]')
    assert alerts.all_inner_texts() == [
        "No plain-language meaning is defined for verdict "
        "Test not run (early stop)."
    ]
    # The other two status lines still render.
    assert tab.locator("#status [data-status='method']").count() == 1
    assert tab.locator("#status [data-status='holdout']").count() == 1
    assert tab.locator("table").count() == 2
    assert tab.guard.errors == []


@pytest.mark.e2e
def test_milbfa_exploratory_banner_quotes_and_precedes_table(open_page):
    data = milbfa_data()
    tab = open_page("/milbfa.html", 375)
    banner = tab.locator("#exploratory [role='note']")
    assert banner.count() == 1
    lines = (REPO / "research/EXPERIMENT.md").read_text().splitlines()
    assert lines[45].endswith("Only cohort aggregates are reported.")
    assert lines[46].endswith("no usefulness claim or recommendation.")
    quotes = banner.locator("[data-quote-source]")
    assert quotes.all_inner_texts() == [lines[45], lines[46]]
    assert [q.get_attribute("data-quote-source") for q in quotes.all()] == [
        data["banner_line_0"]["source"], data["banner_line_1"]["source"],
    ]
    assert data["banner_line_0"]["source"] == "EXPERIMENT.md#L46"
    table = tab.locator("#exploratory table").first
    assert tab.evaluate(
        FOLLOWS, [banner.element_handle(), table.element_handle()]
    )
    b_box, t_box = banner.bounding_box(), table.bounding_box()
    assert b_box["y"] + b_box["height"] <= t_box["y"] + 1


@pytest.mark.e2e
def test_milbfa_ranking_table_matches_published_values(open_page):
    data = milbfa_data()
    tab = open_page("/milbfa.html", 375)
    table = tab.locator("#exploratory table").first
    caption = table.locator("caption")
    cited = caption.locator("[data-src]").all()
    assert [e.get_attribute("data-src") for e in cited] == [
        data["validation_year"]["source"], data["comparator"]["source"],
    ]
    assert caption.inner_text() == (
        "Whole-pool ranking metrics for validation year "
        f"{data['validation_year']['value']}; comparator "
        f"{data['comparator']['value']}"
    )
    assert table.locator("th[scope='col']").all_inner_texts() == [
        "Ranking", "N", "Positives", "Base rate",
        "Top 25 hits", "Top 25 precision", "Top 50 hits",
        "Top 50 precision", "Top 100 hits", "Top 100 precision", "AUROC",
    ]
    rows = table.locator("tbody tr").all()
    assert [r.locator("th").inner_text() for r in rows] == list(RANKINGS)
    for row, ranking in zip(rows, RANKINGS):
        expected = [
            data[key]["source"] for key in ("n", "positives", "base_rate")
        ]
        for cutoff in CUTOFFS:
            expected += [
                data[f"{ranking}_top_{cutoff}_{field}"]["source"]
                for field in ("hits", "precision")
            ]
        expected.append(data[f"{ranking}_auroc"]["source"])
        assert display_sources(row) == expected
        # Every rate is shown beside its n and positives, with full values
        # in the row's single disclosure.
        assert row.locator("details").count() == 1
        assert [
            e.get_attribute("data-src")
            for e in row.locator("details [data-format='full']").all()
        ] == expected
    assert data["comparator"]["value"] in RANKINGS
    assert tab.locator("[data-src*='calibration']").count() == 0


@pytest.mark.e2e
def test_milbfa_bootstrap_table_matches_published_values(open_page):
    data = milbfa_data()
    tab = open_page("/milbfa.html", 375)
    table = tab.locator("#exploratory table").nth(1)
    assert table.locator("th[scope='col']").all_inner_texts() == [
        "Baseline", "N", "Positives", "Mean difference", "95% interval",
        "Resamples",
    ]
    rows = table.locator("tbody tr").all()
    assert [r.locator("th").inner_text() for r in rows] == list(BASELINES)
    for row, baseline in zip(rows, BASELINES):
        assert display_sources(row) == [
            data["n"]["source"], data["positives"]["source"],
            data[f"boot_{baseline}_mean"]["source"],
            data[f"boot_{baseline}_lower"]["source"],
            data[f"boot_{baseline}_upper"]["source"],
            data[f"boot_{baseline}_resamples"]["source"],
        ]
        resamples = data[f"boot_{baseline}_resamples"]["value"]
        assert row.locator("td").last.locator(
            "[data-format='display']"
        ).text_content() == str(resamples)
        interval = row.locator("td").nth(3)
        assert interval.locator("[data-format='display']").count() == 2
        lower = data[f"boot_{baseline}_lower"]["value"]
        upper = data[f"boot_{baseline}_upper"]["value"]
        # Inline "lo to hi": no line break between the numbers.
        assert interval.inner_text() == (
            f"{display(lower, 'probability')} to "
            f"{display(upper, 'probability')}"
        )


@pytest.mark.e2e
def test_milbfa_cubs_case_section_content(open_page):
    data = milbfa_data()
    tab = open_page("/milbfa.html")
    cubs = tab.locator("#cubs-case")
    first = cubs.locator("h2 + p")
    assert first.inner_text() == data["interpretation"]["value"]
    assert first.locator("[data-src]").get_attribute("data-src") == (
        data["interpretation"]["source"]
    )
    years = [data[f"cohort_year_{i}"]["value"] for i in range(4)]
    assert "Cohort years: " + ", ".join(map(str, years)) in cubs.inner_text()
    assert data["signing_window"]["value"] in cubs.inner_text()
    for key in ("threshold_pa", "threshold_ip"):
        assert cubs.locator(
            f'[data-src="{data[key]["source"]}"]'
        ).count() == 2
    items = cubs.locator("li")
    assert items.all_inner_texts() == [
        data[f"unknown_{i}"]["value"] for i in range(3)
    ]
    assert cubs.locator("table").count() == 0


@pytest.mark.e2e
def test_milbfa_shows_no_player_level_values(open_page):
    case = json.loads((REPO / "research/cubs_case.json").read_text())
    assert case["examples"]
    tab = open_page("/milbfa.html")
    sources = tab.evaluate(
        "() => [...document.querySelectorAll('[data-src]')]"
        ".map(e => e.dataset.src)"
    )
    assert sources
    assert not any(
        token in source for source in sources
        for token in ("/examples", "/cohorts", "person")
    )
    exported = (WEB / "data/milbfa.json").read_text()
    for token in ("/examples", "/cohorts", "person_id", "election_date"):
        assert token not in exported
    body = tab.locator("body").inner_text()
    for example in case["examples"]:
        assert str(example["person_id"]) not in body
        assert example["election_date"] not in body
        assert example["signing_date"] not in body
    assert "person" not in body.lower()


@pytest.mark.e2e
def test_milbfa_limits_block_is_present(open_page):
    data = milbfa_data()
    tab = open_page("/milbfa.html")
    limits = tab.locator("#limits")
    assert limits.count() == 1
    assert limits.locator("h2").inner_text() == "Limits of this result"
    lines = (REPO / "research/EXPERIMENT.md").read_text().splitlines()
    quotes = limits.locator("[data-quote-source]")
    assert quotes.all_inner_texts() == [lines[38], lines[39]]
    assert [q.get_attribute("data-quote-source") for q in quotes.all()] == [
        "EXPERIMENT.md#L39", "EXPERIMENT.md#L40",
    ]
    assert lines[38].startswith("UNKNOWN:")
    assert lines[39].startswith("INFERENCE:")
    assert limits.locator("li").all_inner_texts() == [
        data[f"unknown_{i}"]["value"] for i in range(3)
    ]


@pytest.mark.e2e
@pytest.mark.parametrize("width", WIDTHS)
def test_milbfa_wide_tables_scroll_inside_their_containers(width, open_page):
    tab = open_page("/milbfa.html", width)
    wraps = tab.locator("#milbfa .table-wrap")
    assert wraps.count() == 2
    for wrap in wraps.all():
        assert wrap.get_attribute("tabindex") == "0"
        assert wrap.get_attribute("aria-label")
        assert wrap.evaluate(
            "el => getComputedStyle(el).overflowX !== 'visible'"
        )
        assert wrap.evaluate(
            "el => el.getBoundingClientRect().right <= innerWidth + 1"
        )
    if width < 900:
        assert wraps.first.evaluate("el => el.scrollWidth > el.clientWidth")


def test_static_assets_have_no_remote_references():
    assets = [p for p in WEB.rglob("*") if p.suffix in {
        ".html", ".css", ".js"}]
    assert assets
    for path in assets:
        # The one allowed reference is a plain link; nothing fetches it.
        text = path.read_text().replace(HISTORY_URL, "")
        assert not re.search(r"https?://|//cdn|@import", text, re.I), path


def test_every_page_has_registry_entry():
    on_disk = {f"/{p.name}" for p in WEB.glob("*.html")} - {"/index.html"}
    registered = {page.path for page in PAGES}
    assert on_disk | {"/"} == registered


def test_js_files_pass_node_check():
    node = shutil.which("node")
    if node is None:
        if REQUIRE_E2E:
            pytest.fail("CUBS_REQUIRE_E2E=1 but node is unavailable")
        pytest.skip("node is unavailable")
    files = sorted(WEB.rglob("*.js"))
    assert files
    for path in files:
        subprocess.run([node, "--check", str(path)], check=True)


# ---- browser fixtures ------------------------------------------------------

@pytest.fixture(scope="session")
def browser():
    try:
        from playwright.sync_api import sync_playwright

        manager = sync_playwright().start()
    except Exception as exc:
        if REQUIRE_E2E:
            pytest.fail(f"CUBS_REQUIRE_E2E=1 but Playwright failed: {exc}")
        pytest.skip(f"Playwright unavailable: {exc}")
    try:
        instance = manager.chromium.launch(headless=True)
    except Exception as exc:
        manager.stop()
        if REQUIRE_E2E:
            pytest.fail(f"CUBS_REQUIRE_E2E=1 but Chromium failed: {exc}")
        pytest.skip(f"Chromium unavailable: {exc}")
    yield instance
    instance.close()
    manager.stop()


class Guard:
    """Records every request and console error; aborts non-local requests."""

    def __init__(self, origin):
        self.origin = origin
        self.requests = []
        self.errors = []
        self.ignored = False

    def is_local(self, url):
        parsed, local = urlparse(url), urlparse(self.origin)
        return (parsed.scheme, parsed.netloc) == (local.scheme, local.netloc)

    def route(self, route, overrides=None):
        if self.is_local(route.request.url):
            path = urlparse(route.request.url).path.lstrip("/")
            if overrides and path in overrides:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(overrides[path]),
                )
                return
            route.continue_()
        else:
            route.abort()

    def assert_clean(self):
        if self.ignored:
            return
        remote = [u for u in self.requests if not self.is_local(u)]
        assert not remote, f"Non-local requests: {remote}"
        assert not self.errors, f"Console errors: {self.errors}"


@pytest.fixture
def open_page(browser, explorer_server):
    """Open a registry page at a width, guarded against remote requests."""
    contexts = []
    guards = []

    def opener(path, width=1280, overrides=None):
        context = browser.new_context(viewport={"width": width, "height": 900})
        contexts.append(context)
        guard = Guard(explorer_server)
        guards.append(guard)
        tab = context.new_page()
        tab.on("request", lambda request: guard.requests.append(request.url))
        tab.on("pageerror", lambda exc: guard.errors.append(str(exc)))
        tab.on(
            "console",
            lambda msg: guard.errors.append(msg.text)
            if msg.type == "error" else None,
        )
        tab.route("**/*", lambda route: guard.route(route, overrides))
        tab.goto(explorer_server + path)
        tab.wait_for_load_state("networkidle")
        tab.guard = guard
        return tab

    yield opener
    for context in contexts:
        context.close()
    for guard in guards:
        guard.assert_clean()


# ---- registry-driven browser tests -----------------------------------------

@pytest.mark.e2e
@pytest.mark.parametrize("page", PAGES, ids=PAGE_IDS)
def test_numbers_are_tagged_and_match_sources(page, open_page):
    scan_numbers(open_page(page.path))


@pytest.mark.e2e
@pytest.mark.parametrize("page", PAGES, ids=PAGE_IDS)
def test_page_provenance_and_stub_guards(page, open_page):
    tab = open_page(page.path)
    manifest = load_manifest()
    assert tab.locator(".skip-link").count() == 1
    footer = tab.locator("footer").inner_text()
    digest = web_export.research_digest(REPO)
    assert manifest["research_digest"] == digest
    assert f"Research digest: {digest[:12]}" in footer
    disclosure = tab.locator("footer details")
    assert disclosure.count() == 1
    assert disclosure.evaluate("el => el.open") is False
    assert disclosure.locator(
        "[data-provenance='research-digest']"
    ).text_content() == digest
    assert manifest["as_of_date"] in footer
    assert SUPERSEDE in footer
    assert ATTRIBUTION in footer
    assert USAGE_QUOTE in footer
    body = tab.locator("body").inner_text()
    assert ("coming in a later version" in body) == page.stub
    assert ("Failed-model value" in body) == (page.path == "/sendhold.html")


@pytest.mark.e2e
@pytest.mark.parametrize("page", PAGES, ids=PAGE_IDS)
def test_network_stays_local(page, open_page):
    tab = open_page(page.path)
    assert tab.guard.requests
    assert all(tab.guard.is_local(u) for u in tab.guard.requests)


@pytest.mark.e2e
def test_network_guard_detects_remote_request(open_page):
    tab = open_page("/sendhold.html")
    tab.evaluate("() => fetch('http://example.invalid/x').catch(() => 0)")
    tab.wait_for_timeout(200)
    with pytest.raises(AssertionError, match="Non-local requests"):
        tab.guard.assert_clean()
    # The probe was deliberate. Ignore later console noise from the abort.
    tab.guard.ignored = True


@pytest.mark.e2e
@pytest.mark.parametrize("page", PAGES, ids=PAGE_IDS)
@pytest.mark.parametrize("width", WIDTHS)
def test_no_horizontal_scroll(page, width, open_page):
    tab = open_page(page.path, width)
    assert tab.evaluate(
        "() => document.documentElement.scrollWidth"
        " <= document.documentElement.clientWidth"
    )


@pytest.mark.e2e
@pytest.mark.parametrize(
    "page", [p for p in PAGES if p.verdict], ids=lambda p: p.path
)
def test_verdict_and_meaning_precede_tables(page, open_page):
    tab = open_page(page.path, 375)
    follows = """([a, b]) => !!(
      a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)"""
    cards = tab.locator(".card").all()
    assert cards
    for card in cards:
        verdict = card.locator("[data-verdict]")
        meaning = card.locator("[data-meaning]")
        assert verdict.count() == 1 and meaning.count() == 1
        handles = [verdict.element_handle(), meaning.element_handle()]
        assert tab.evaluate(follows, handles)
        v_box, m_box = verdict.bounding_box(), meaning.bounding_box()
        assert v_box["y"] + v_box["height"] <= m_box["y"] + 1
        if "NEGATIVE" in verdict.inner_text():
            assert meaning.inner_text() == MEANINGS["NEGATIVE"]
        for table in card.locator("table").all():
            assert tab.evaluate(follows, [
                meaning.element_handle(), table.element_handle()])
            t_box = table.bounding_box()
            assert m_box["y"] + m_box["height"] <= t_box["y"] + 1
    first_table = tab.locator("table")
    if first_table.count():
        handles = [
            tab.locator("[data-verdict]").first.element_handle(),
            first_table.first.element_handle(),
        ]
        assert tab.evaluate(follows, handles)


@pytest.mark.e2e
def test_meaning_selected_by_verdict_value(open_page):
    data = json.loads((WEB / "data/overview.json").read_text())
    data["sendhold_verdict"]["value"] = "PARTIAL"
    tab = open_page("/", overrides={"data/overview.json": data})
    meaning = tab.locator(".card").first.locator("[data-meaning]")
    assert meaning.inner_text() == MEANINGS["PARTIAL"]


@pytest.mark.e2e
def test_unmapped_verdict_shows_alert_without_console_error(open_page):
    data = json.loads((WEB / "data/overview.json").read_text())
    data["sendhold_verdict"]["value"] = "UNMAPPED"
    tab = open_page("/", overrides={"data/overview.json": data})
    alert = tab.locator('.card [role="alert"][data-error="missing-meaning"]')
    assert alert.count() == 1
    assert alert.inner_text() == (
        "No plain-language meaning is defined for verdict UNMAPPED."
    )
    assert MEANINGS["NEGATIVE"] not in tab.locator(".card").first.inner_text()
    meaning = tab.locator(".card").first.locator("[data-meaning]")
    alert = meaning.locator('[role="alert"][data-error="missing-meaning"]')
    assert alert.count() == 1
    assert tab.guard.errors == []


@pytest.mark.e2e
def test_earlier_definition_verdict_renders_when_mapped(open_page):
    tab = open_page("/")
    secondary = tab.locator(".card").first.locator("[data-secondary-verdict]")
    assert secondary.count() == 1
    assert (
        "Verdict under the earlier pre-registered definition: NEGATIVE"
        in secondary.inner_text()
    )
    assert tab.locator('.card [role="alert"]').count() == 0
    assert tab.guard.errors == []


@pytest.mark.e2e
def test_unmapped_earlier_definition_verdict_shows_alert(open_page):
    data = json.loads((WEB / "data/overview.json").read_text())
    data["sendhold_v2_verdict"]["value"] = "UNMAPPED2"
    tab = open_page("/", overrides={"data/overview.json": data})
    alert = tab.locator('.card [role="alert"][data-error="missing-meaning"]')
    assert alert.count() == 1
    assert alert.inner_text() == (
        "No plain-language meaning is defined for verdict UNMAPPED2."
    )
    first = tab.locator(".card").first
    assert first.locator("[data-secondary-verdict]").count() == 0
    meaning = first.locator("[data-meaning]")
    assert meaning.inner_text() == MEANINGS["NEGATIVE"]
    assert meaning.locator('[role="alert"]').count() == 0
    assert tab.guard.errors == []


@pytest.mark.e2e
def test_meaning_directly_follows_primary_verdict(open_page):
    tab = open_page("/")
    follows = """([a, b]) => !!(
      a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)"""
    adjacent = "([a, b]) => a.nextElementSibling === b"
    cards = tab.locator(".card").all()
    assert cards
    for card in cards:
        handles = [
            card.locator("[data-verdict]").element_handle(),
            card.locator("[data-meaning]").element_handle(),
        ]
        assert tab.evaluate(adjacent, handles)
    first = cards[0]
    secondary = first.locator("[data-secondary-verdict]")
    assert tab.evaluate(follows, [
        first.locator("[data-meaning]").element_handle(),
        secondary.element_handle(),
    ])


@pytest.mark.e2e
def test_missing_early_stop_meaning_shows_alert(open_page):
    meanings = dict(MEANINGS)
    del meanings["Test not run (early stop)"]
    tab = open_page("/", overrides={"data/meanings.json": meanings})
    alerts = tab.locator('.card [role="alert"][data-error="missing-meaning"]')
    assert alerts.count() == 1
    assert alerts.inner_text() == (
        "No plain-language meaning is defined for verdict "
        "Test not run (early stop)."
    )
    assert tab.guard.errors == []


@pytest.mark.e2e
def test_float_format_note_is_visible(open_page):
    data = json.loads((WEB / "data/about.json").read_text())
    data["request_count"]["value"] = 0.5
    tab = open_page("/about.html", overrides={"data/about.json": data})
    assert "shown to two decimals" in tab.locator("body").inner_text()


@pytest.mark.e2e
def test_probability_format_note_is_visible(open_page):
    data = json.loads((WEB / "data/about.json").read_text())
    data["request_count"]["value"] = 0.12345
    data["request_count"]["kind"] = "probability"
    tab = open_page("/about.html", overrides={"data/about.json": data})
    assert "shown to three decimals" in tab.locator("body").inner_text()


@pytest.mark.e2e
@pytest.mark.parametrize(
    "page", [p for p in PAGES if p.details], ids=lambda p: p.path
)
def test_every_details_opens_by_keyboard(page, open_page):
    tab = open_page(page.path)
    total = tab.locator("details").count()
    assert total
    tab.evaluate("() => document.activeElement.blur()")
    reached = set()
    for _ in range(40 + 4 * total):
        tab.keyboard.press("Tab")
        index = tab.evaluate("""() => {
          const el = document.activeElement;
          if (!el || el.tagName !== 'SUMMARY') return -1;
          return [...document.querySelectorAll('details')]
            .indexOf(el.parentElement);
        }""")
        if index < 0 or index in reached:
            continue
        reached.add(index)
        is_open = "() => document.activeElement.parentElement.open"
        assert not tab.evaluate(is_open)
        tab.keyboard.press("Enter")
        assert tab.evaluate(is_open), "Enter should open"
        tab.keyboard.press("Space")
        assert not tab.evaluate(is_open), "Space should close"
        tab.keyboard.press("Space")
        assert tab.evaluate(is_open), "Space should open"
        has_nested = tab.evaluate(
            "() => document.activeElement.parentElement."
            "querySelector('details') !== null"
        )
        if not has_nested:
            tab.keyboard.press("Enter")
            assert not tab.evaluate(is_open), "Enter should close"
        if len(reached) == total:
            break
    assert len(reached) == total


# ---- accessibility ---------------------------------------------------------

MIN_CONTRAST = 4.5
FOCUSABLE = "a[href], summary, .table-wrap"
OPEN_ALL_DETAILS = (
    "() => document.querySelectorAll('details').forEach(d => d.open = true)"
)


def channel(value):
    value /= 255
    if value <= 0.03928:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    red, green, blue = (channel(c) for c in rgb[:3])
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(first, second):
    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def parse_color(text):
    """Parse a computed rgb()/rgba() string into (r, g, b, alpha)."""
    match = re.fullmatch(r"rgba?\((.+)\)", text.strip())
    assert match, f"Unsupported computed color: {text}"
    parts = [float(p) for p in re.split(r"[\s,/]+", match.group(1)) if p]
    alpha = parts[3] if len(parts) > 3 else 1.0
    return (parts[0], parts[1], parts[2], alpha)


def composite(top, bottom):
    """Source-over of ``top`` on an opaque ``bottom``; both are RGBA."""
    alpha = top[3]
    return tuple(
        top[i] * alpha + bottom[i] * (1 - alpha) for i in range(3)
    ) + (1.0,)


def effective_background(chain):
    """Flatten computed backgrounds, innermost first, onto white canvas."""
    result = (255.0, 255.0, 255.0, 1.0)
    for layer in reversed(chain):
        result = composite(parse_color(layer), result)
    return result


def text_contrast(color, chain):
    background = effective_background(chain)
    text = composite(parse_color(color), background)
    return contrast_ratio(text, background)


def test_contrast_helpers():
    black, white = (0, 0, 0), (255, 255, 255)
    assert contrast_ratio(black, white) == pytest.approx(21)
    assert contrast_ratio(white, black) == pytest.approx(21)
    assert contrast_ratio(white, white) == pytest.approx(1)
    assert contrast_ratio((0x77, 0x77, 0x77), white) < MIN_CONTRAST
    assert contrast_ratio((0x76, 0x76, 0x76), white) >= MIN_CONTRAST


def test_background_compositing_walks_the_ancestor_chain():
    clear = "rgba(0, 0, 0, 0)"
    assert effective_background([clear, clear]) == (255, 255, 255, 1)
    assert effective_background(
        [clear, "rgb(10, 20, 30)", "rgb(1, 2, 3)"]
    ) == (10, 20, 30, 1)
    half = effective_background(["rgba(0, 0, 0, 0.5)", "rgb(255, 255, 255)"])
    assert half[:3] == pytest.approx((127.5, 127.5, 127.5))
    assert text_contrast("rgb(0, 0, 0)", ["rgb(255, 255, 255)"]) == (
        pytest.approx(21)
    )
    assert text_contrast("rgb(24, 35, 45)", [clear, "rgb(18, 48, 71)"]) < 2


CONTRAST_TEXT = """() => {
  document.querySelectorAll('details').forEach(d => d.open = true);
  const found = [];
  const walker = document.createTreeWalker(document.body,
    NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const text = walker.currentNode.nodeValue.trim();
    const el = walker.currentNode.parentElement;
    if (!text || !el.getClientRects().length) continue;
    const chain = [];
    for (let e = el; e; e = e.parentElement) {
      chain.push(getComputedStyle(e).backgroundColor);
    }
    let category = 'body';
    if (el.closest('.verdict, [data-verdict]')) category = 'verdict';
    else if (el.closest('a')) category = 'link';
    else if (el.closest('td, th, caption')) category = 'table';
    found.push({text: text.slice(0, 40), category, chain,
      color: getComputedStyle(el).color});
  }
  return found;
}"""
SKIP_LINK_COLORS = """() => {
  const el = document.querySelector('.skip-link');
  const chain = [];
  for (let e = el; e; e = e.parentElement) {
    chain.push(getComputedStyle(e).backgroundColor);
  }
  return {text: 'skip link (focused)', category: 'link', chain,
    color: getComputedStyle(el).color};
}"""


def contrast_samples(tab):
    samples = tab.evaluate(CONTRAST_TEXT)
    tab.focus(".skip-link")
    samples.append(tab.evaluate(SKIP_LINK_COLORS))
    return samples


def contrast_failures(samples):
    failures = []
    for sample in samples:
        ratio = text_contrast(sample["color"], sample["chain"])
        if ratio < MIN_CONTRAST:
            failures.append(
                f"{sample['category']} {sample['text']!r}: {ratio:.2f}"
            )
    return failures


@pytest.mark.e2e
@pytest.mark.parametrize("page", PAGES, ids=PAGE_IDS)
def test_text_contrast_meets_wcag_aa(page, open_page):
    samples = contrast_samples(open_page(page.path))
    categories = {sample["category"] for sample in samples}
    assert {"body", "link"} <= categories
    if page.verdict:
        assert "verdict" in categories
    if page.path in {"/sendhold.html", "/milbfa.html"}:
        assert "table" in categories
    assert contrast_failures(samples) == []


@pytest.mark.e2e
def test_contrast_check_flags_low_contrast_text(open_page):
    tab = open_page("/")
    tab.add_style_tag(content="p { color: #999; }")
    assert any("body" in f for f in contrast_failures(contrast_samples(tab)))


FOCUS_STATE = """selector => {
  const el = document.activeElement;
  const index = [...document.querySelectorAll(selector)].indexOf(el);
  if (index < 0) return null;
  const style = getComputedStyle(el);
  return {index, tag: el.tagName, visible: el.matches(':focus-visible'),
    outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth,
    boxShadow: style.boxShadow};
}"""


def focus_failures(tab):
    """Tab through every link, summary and scroll region; report problems."""
    tab.evaluate(OPEN_ALL_DETAILS)
    total = tab.locator(FOCUSABLE).count()
    assert total
    tab.evaluate("() => document.activeElement.blur()")
    visited, failures = set(), []
    for _ in range(total + 10):
        tab.keyboard.press("Tab")
        state = tab.evaluate(FOCUS_STATE, FOCUSABLE)
        if state is None or state["index"] in visited:
            continue
        visited.add(state["index"])
        outlined = (
            state["outlineStyle"] != "none"
            and float(state["outlineWidth"].removesuffix("px")) > 0
        )
        shadowed = state["boxShadow"] != "none"
        if not (state["visible"] and (outlined or shadowed)):
            failures.append(f"{state['tag']} #{state['index']} no focus ring")
    failures += [
        f"element #{i} never received keyboard focus"
        for i in sorted(set(range(total)) - visited)
    ]
    return failures


@pytest.mark.e2e
@pytest.mark.parametrize("page", PAGES, ids=PAGE_IDS)
def test_focus_is_visible_on_every_focusable_element(page, open_page):
    assert focus_failures(open_page(page.path)) == []


@pytest.mark.e2e
def test_focus_check_flags_removed_outlines(open_page):
    tab = open_page("/sendhold.html")
    tab.add_style_tag(
        content="a:focus-visible, summary:focus-visible { outline: none; }"
    )
    failures = focus_failures(tab)
    assert any(f.startswith("A ") for f in failures)
    assert any(f.startswith("SUMMARY ") for f in failures)


@pytest.mark.e2e
@pytest.mark.parametrize("page", PAGES, ids=PAGE_IDS)
def test_page_language_and_single_h1(page, open_page):
    tab = open_page(page.path)
    assert tab.evaluate("() => document.documentElement.lang").strip()
    assert tab.locator("h1").count() == 1


@pytest.mark.e2e
@pytest.mark.parametrize("page", PAGES, ids=PAGE_IDS)
def test_skip_link_target_exists_and_receives_focus(page, open_page):
    tab = open_page(page.path)
    tab.evaluate("() => document.activeElement.blur()")
    tab.keyboard.press("Tab")
    assert tab.evaluate(
        "() => document.activeElement.classList.contains('skip-link')"
    )
    href = tab.locator(".skip-link").get_attribute("href")
    assert href.startswith("#") and len(href) > 1
    target = href[1:]
    assert tab.locator(f"[id='{target}']").count() == 1
    tab.keyboard.press("Enter")
    assert tab.evaluate("() => document.activeElement.id") == target


@pytest.mark.e2e
@pytest.mark.parametrize("page", PAGES, ids=PAGE_IDS)
def test_tables_have_captions_and_scoped_headers(page, open_page):
    tab = open_page(page.path)
    tables = tab.evaluate("""() => [...document.querySelectorAll('table')]
      .map(t => ({caption: t.caption ? t.caption.textContent.trim() : '',
        scopes: [...t.querySelectorAll('th')].map(
          th => th.getAttribute('scope'))}))""")
    if page.path in {"/sendhold.html", "/milbfa.html"}:
        assert tables
    for table in tables:
        assert table["caption"]
        assert table["scopes"]
        assert set(table["scopes"]) <= {"col", "row"}


@pytest.mark.e2e
@pytest.mark.parametrize("page", PAGES, ids=PAGE_IDS)
def test_every_details_has_one_leading_summary(page, open_page):
    tab = open_page(page.path)
    shapes = tab.evaluate("""() => [...document.querySelectorAll('details')]
      .map(d => ({
        first: d.firstElementChild && d.firstElementChild.tagName,
        summaries: d.querySelectorAll(':scope > summary').length,
        label: d.querySelector(':scope > summary').textContent.trim()}))""")
    assert shapes
    for shape in shapes:
        assert shape["first"] == "SUMMARY" and shape["summaries"] == 1
        assert shape["label"]


@pytest.mark.e2e
@pytest.mark.parametrize("page", PAGES, ids=PAGE_IDS)
def test_alerts_have_text_on_default_pages(page, open_page):
    texts = open_page(page.path).locator('[role="alert"]').all_inner_texts()
    assert all(text.strip() for text in texts)


def alert_scenarios():
    overview = json.loads((WEB / "data/overview.json").read_text())
    overview["sendhold_verdict"]["value"] = "UNMAPPED"
    overview["sendhold_v2_verdict"]["value"] = "UNMAPPED2"
    sendhold = sendhold_data()
    sendhold["verdict"]["value"] = "UNMAPPED"
    sendhold["verdict_v2"]["value"] = "UNMAPPED2"
    sendhold["feasibility_verdict"]["value"] = "UNMAPPED3"
    meanings = dict(MEANINGS)
    del meanings["Test not run (early stop)"]
    return [
        ("/", {"data/overview.json": overview}, 2),
        ("/sendhold.html", {"data/sendhold.json": sendhold}, 3),
        ("/milbfa.html", {"data/meanings.json": meanings}, 1),
    ]


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("path", "overrides", "expected"), alert_scenarios(),
    ids=["/", "/sendhold.html", "/milbfa.html"],
)
def test_rendered_alerts_have_text(path, overrides, expected, open_page):
    tab = open_page(path, overrides=overrides)
    texts = tab.locator('[role="alert"]').all_inner_texts()
    assert len(texts) == expected
    assert all(text.strip() for text in texts)


# ---- readability: small values, one disclosure per row, header words -------

NEGATIVE_ZERO = re.compile(r"(?<![\w.])-0(?:\.0+)?(?![\d.])")
DISPLAY_TAGS = """() => [...document.querySelectorAll(
  '[data-src][data-format="display"]')].map(
  e => ({src: e.dataset.src, text: e.textContent,
         small: e.dataset.small === 'true'}))"""


def reads_as_zero(text, value):
    """True when ``text`` is a zero form but the source ``value`` is not."""
    if isinstance(value, list) and len(value) == 2:
        parts = text.split(" to ")
        return len(parts) == 2 and any(
            reads_as_zero(t, v) for t, v in zip(parts, value)
        )
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool)
        and value != 0 and text in ZERO_FORMS
    )


def test_zero_form_helper_flags_only_nonzero_sources():
    assert reads_as_zero("-0.00", -0.00005)
    assert reads_as_zero("0.000", 0.0004)
    assert reads_as_zero("-0.00 to 0.00", [-0.00005, 0.00004])
    assert reads_as_zero("0.50 to 0.00", [0.5, 0.00004])
    assert not reads_as_zero("-0.000053", -0.000053)
    assert not reads_as_zero("0", 0)
    assert not reads_as_zero("0.00", "0.00")
    assert not reads_as_zero("-0.00 to 0.00", [0.0, 0])


def test_negative_zero_pattern():
    for text in ("-0", "-0.00", "x -0.000 y", "(-0)"):
        assert NEGATIVE_ZERO.search(text), text
    for text in ("-0.000053", "2026-03-04", "a1-0b", "-0.5", "1.-0", "0.00"):
        assert not NEGATIVE_ZERO.search(text), text


@pytest.mark.e2e
@pytest.mark.parametrize("page", PAGES, ids=PAGE_IDS)
def test_no_number_reads_as_zero_while_its_source_is_not(page, open_page):
    tab = open_page(page.path)
    tags = tab.evaluate(DISPLAY_TAGS)
    assert tags
    failures = [
        t for t in tags if reads_as_zero(t["text"], resolve_source(t["src"]))
    ]
    assert failures == []
    body = tab.evaluate("() => document.body.textContent")
    assert NEGATIVE_ZERO.findall(body) == []


@pytest.mark.e2e
def test_small_value_override_is_shown_to_two_significant_figures(open_page):
    data = json.loads((WEB / "data/about.json").read_text())
    data["request_count"]["value"] = -0.000053
    tab = open_page("/about.html", overrides={"data/about.json": data})
    shown = tab.locator(
        f'[data-src="{data["request_count"]["source"]}"]'
        "[data-format='display']"
    )
    assert shown.text_content() == "-0.000053"
    full = tab.locator(
        f'[data-src="{data["request_count"]["source"]}"]'
        "[data-format='full']"
    )
    assert full.text_content() == "-0.000053"
    assert SMALL_NOTE in tab.locator("body").inner_text()
    assert NEGATIVE_ZERO.findall(tab.evaluate(
        "() => document.body.textContent")) == []


@pytest.mark.e2e
def test_ordinary_float_does_not_claim_small_values(open_page):
    data = json.loads((WEB / "data/about.json").read_text())
    data["request_count"]["value"] = 0.5
    tab = open_page("/about.html", overrides={"data/about.json": data})
    body = tab.locator("body").inner_text()
    assert "shown to two decimals" in body
    assert SMALL_NOTE not in body


@pytest.mark.e2e
@pytest.mark.parametrize("page", PAGES, ids=PAGE_IDS)
def test_pages_with_small_values_say_so_in_the_panel(page, open_page):
    tab = open_page(page.path)
    has_small = any(t["small"] for t in tab.evaluate(DISPLAY_TAGS))
    assert (SMALL_NOTE in tab.locator("body").inner_text()) is has_small
    if page.path == "/sendhold.html":
        assert has_small
    unnoted = tab.evaluate("""note => [...document.querySelectorAll(
      '.panel, .card')].filter(s => s.querySelector('[data-small]')
        && ![...s.querySelectorAll('[data-provenance="format-note"]')]
          .some(n => n.textContent.includes(note))).length""", SMALL_NOTE)
    assert unnoted == 0


FULL_GROUPS = """() => {
  const label = d => d.querySelector(':scope > summary').textContent.trim();
  const full = d => label(d) === 'Full published value';
  const srcs = (el, fmt) => [...el.querySelectorAll(
    `[data-src][data-format="${fmt}"]`)].map(e => e.dataset.src);
  const rows = [...document.querySelectorAll('tbody tr')].map(tr => ({
    details: [...tr.querySelectorAll('details')].filter(full).length,
    full: srcs(tr, 'full'), display: srcs(tr, 'display')}));
  const groups = [...document.querySelectorAll('details')]
    .filter(d => full(d) && !d.closest('table')).map(d => {
      const before = d.previousElementSibling;
      return {inParagraph: !!d.closest('p'),
        previous: before && before.tagName,
        stacked: [d.previousElementSibling, d.nextElementSibling].some(
          n => n && n.tagName === 'DETAILS' && full(n)),
        full: srcs(d, 'full'), display: before ? srcs(before, 'display') : []};
    });
  return {rows, groups};
}"""


def numeric_source(pointer):
    value = resolve_source(pointer)
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@pytest.mark.e2e
@pytest.mark.parametrize("page", PAGES, ids=PAGE_IDS)
def test_one_full_value_disclosure_per_row_or_group(page, open_page):
    shapes = open_page(page.path).evaluate(FULL_GROUPS)
    for row in shapes["rows"]:
        assert row["details"] <= 1, row
        numbers = [s for s in row["display"] if numeric_source(s)]
        if numbers:
            assert row["details"] == 1, row
        assert set(numbers) <= set(row["full"]), row
    for group in shapes["groups"]:
        assert not group["inParagraph"] and not group["stacked"], group
        assert group["previous"] == "P", group
        numbers = [s for s in group["display"] if numeric_source(s)]
        assert numbers and set(numbers) <= set(group["full"]), group
    if page.path in {"/sendhold.html", "/milbfa.html"}:
        assert shapes["rows"] and shapes["groups"]


WORDS_BREAK = """() => [...document.querySelectorAll('th')].flatMap(th => {
  const walker = document.createTreeWalker(th, NodeFilter.SHOW_TEXT);
  const broken = [];
  while (walker.nextNode()) {
    const node = walker.currentNode;
    // A hyphen is a normal break point, so each hyphenated part is a word.
    for (const match of node.nodeValue.matchAll(/[^\\s-]+/g)) {
      const range = document.createRange();
      range.setStart(node, match.index);
      range.setEnd(node, match.index + match[0].length);
      const tops = [...range.getClientRects()].map(r => r.top);
      if (tops.length && Math.max(...tops) - Math.min(...tops) > 2) {
        broken.push(match[0]);
      }
    }
  }
  return broken;
})"""


@pytest.mark.e2e
@pytest.mark.parametrize("page", PAGES, ids=PAGE_IDS)
@pytest.mark.parametrize("width", WIDTHS)
def test_table_headers_never_break_inside_a_word(page, width, open_page):
    tab = open_page(page.path, width)
    assert tab.evaluate(WORDS_BREAK) == []
    wraps = tab.locator(".table-wrap")
    assert wraps.count() == tab.locator("table").count()
    for wrap in wraps.all():
        assert wrap.evaluate(
            "el => getComputedStyle(el).overflowX == 'auto'"
        )
        assert wrap.evaluate(
            "el => el.getBoundingClientRect().right <= innerWidth + 1"
        )
    if width < 900:
        for wrap in wraps.all():
            assert wrap.locator("table").evaluate(
                "table => table.scrollWidth > table.parentElement.clientWidth"
            )
    assert tab.evaluate(
        "() => document.documentElement.scrollWidth"
        " <= document.documentElement.clientWidth"
    )


@pytest.mark.e2e
def test_header_word_break_check_detects_a_broken_word(open_page):
    tab = open_page("/sendhold.html", 375)
    tab.add_style_tag(content=(
        "table { min-width: 0 !important; table-layout: fixed; } "
        "th { overflow-wrap: anywhere; }"
    ))
    assert tab.evaluate(WORDS_BREAK)
