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

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "web"
REQUIRE_E2E = os.environ.get("CUBS_REQUIRE_E2E") == "1"
WIDTHS = (320, 375, 1280)
MEANINGS = json.loads((WEB / "data" / "meanings.json").read_text())
SUPERSEDE = "later studies may supersede these results"
ATTRIBUTION = "MLB Advanced Media, L.P. (MLBAM)"
USAGE_QUOTE = "Only individual, non-commercial, non-bulk use"
PROVENANCE_KINDS = {"commit", "as-of", "source-hash", "prose-year"}
HIDDEN_TERMS = ("sendhold_fit", "p_safe", "predicted", "flagged", "runs_left")


@dataclass(frozen=True)
class Page:
    path: str
    verdict: bool = False  # opens with verdict cards
    details: bool = False  # contains <details> elements
    stub: bool = False  # states "coming in a later version"


PAGES = [
    Page("/", verdict=True),
    Page("/about.html", details=True),
    Page("/sendhold.html", stub=True),
    Page("/milbfa.html", stub=True),
]
PAGE_IDS = [page.path for page in PAGES]


def load_manifest():
    return json.loads((WEB / "data" / "manifest.json").read_text())


def resolve_source(pointer):
    filename, json_pointer = pointer.split("#", 1)
    value = json.loads((REPO / "research" / filename).read_text())
    for part in json_pointer.lstrip("/").split("/"):
        if part:
            value = value[part.replace("~1", "/").replace("~0", "~")]
    return value


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
            return str(int(value)) if value.is_integer() else repr(value)
        if value.is_integer():
            return str(int(value))
        decimals = 3 if kind in {"probability", "rate"} else 2
        rounded = Decimal(abs(value)).quantize(
            Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP
        )
        return ("-" if value < 0 else "") + f"{rounded:.{decimals}f}"
    return json.dumps(value)


def assert_numeric_nodes(nodes, manifest):
    """Fail on any text containing a digit that is not traced to a source."""
    allowlist = set(manifest["default_visible"])
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
        if kind == "commit":
            assert text == f"cubs-edge-lab commit: {manifest['commit']}"
        elif kind == "source-hash":
            assert text in hashes, f"Unknown source hash: {text}"
        elif kind == "prose-year":
            assert re.fullmatch(r"(?:19|20)\d\d", text), f"Not a year: {text}"
        else:
            raise AssertionError(f"Untagged number: {text}")


def scan_numbers(tab):
    manifest = load_manifest()
    allowlist = set(manifest["default_visible"])
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
    (1, "probability", "1"), (-0.004, "float", "-0.00"),
    ([-0.25, 0.125], "float", "-0.25 to 0.13"),
])
def test_display_format_vectors(value, kind, expected):
    assert display(value, kind) == expected


def test_display_full_precision():
    assert display(0.1, full=True) == "0.1"


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


def test_static_assets_have_no_remote_references():
    assets = [p for p in WEB.rglob("*") if p.suffix in {
        ".html", ".css", ".js"}]
    assert assets
    for path in assets:
        text = path.read_text()
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
    assert tab.locator("h1").count() == 1
    footer = tab.locator("footer").inner_text()
    assert f"cubs-edge-lab commit: {manifest['commit']}" in footer
    assert manifest["as_of_date"] in footer
    assert SUPERSEDE in footer
    assert ATTRIBUTION in footer
    assert USAGE_QUOTE in footer
    body = tab.locator("body").inner_text()
    assert ("coming in a later version" in body) == page.stub
    assert "Failed-model value" not in body


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
        tab.keyboard.press("Enter")
        assert not tab.evaluate(is_open), "Enter should close"
        if len(reached) == total:
            break
    assert len(reached) == total
