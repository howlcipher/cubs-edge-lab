/** @typedef {{value: unknown, source: string}} SourcedValue */
/** @typedef {{commit: string, as_of_date: string, as_of_source: string, sources: Record<string, string>, default_visible: string[]}} Manifest */
import { formatFull, formatValue } from "./format.js";

const ATTRIBUTION = 'Attribution: MLB Advanced Media, L.P. (MLBAM), via the public MLB Stats API. “Only individual, non-commercial, non-bulk use of the Materials is permitted.”';

/** @param {string} path */
async function load(path) {
  const response = await fetch(`data/${path}`);
  if (!response.ok) throw new Error(`Could not load ${path}`);
  return response.json();
}

/** @param {string} text @param {string} source */
function sourced(text, source, format = "display", kind = "float") {
  const span = document.createElement("span");
  span.textContent = text;
  span.dataset.src = source;
  span.dataset.format = format;
  span.dataset.kind = kind;
  return span;
}

/**
 * Build a paragraph of authored prose; calendar years are explicitly tagged
 * so the untagged-number scan can tell them from data values.
 * @param {string} text
 */
function prose(text) {
  const p = document.createElement("p");
  for (const part of text.split(/\b((?:19|20)\d\d)\b/)) {
    if (/^(?:19|20)\d\d$/.test(part)) {
      const year = document.createElement("span");
      year.textContent = part;
      year.dataset.provenance = "prose-year";
      p.append(year);
    } else {
      p.append(part);
    }
  }
  return p;
}

/** @param {HTMLElement} root @param {string} text */
function proseLabel(root, text) {
  const span = document.createElement("span");
  span.textContent = text;
  span.dataset.provenance = "prose-label";
  root.append(span);
}

/** @param {HTMLElement} root @param {string} label @param {SourcedValue} item */
function line(root, label, item) {
  const p = document.createElement("p");
  const kind = item.kind || "float";
  const hasFloat = (value) => Array.isArray(value)
    ? value.some(hasFloat)
    : typeof value === "number" && !Number.isInteger(value);
  const numericFloat = hasFloat(item.value);
  p.append(`${label}: `, sourced(formatValue(item.value, kind), item.source, "display", kind));
  if (numericFloat) {
    const note = document.createElement("span");
    note.textContent = ` (shown to ${kind === "probability" || kind === "rate" ? "three" : "two"} decimals)`;
    p.append(note);
  }
  root.append(p);
  if (typeof item.value === "number" || Array.isArray(item.value)) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Full published value";
    const full = document.createElement("p");
    full.append(sourced(formatFull(item.value), item.source, "full", kind));
    details.append(summary, full);
    root.append(details);
  }
}

/** @param {HTMLElement} root @param {SourcedValue} item @param {string} kind */
function appendNumber(root, item, kind = "float") {
  root.append(sourced(formatValue(item.value, kind), item.source, "display", kind));
  const details = document.createElement("details");
  const summary = document.createElement("summary"); summary.textContent = "Full published value";
  const full = document.createElement("p");
  full.append(sourced(formatFull(item.value), item.source, "full", kind));
  details.append(summary, full); root.append(details);
}

/** @param {Manifest} manifest */
function renderFooter(manifest) {
  const footer = document.querySelector("#footer");
  if (!footer) return;
  const commit = document.createElement("p");
  commit.textContent = `cubs-edge-lab commit: ${manifest.commit}`;
  commit.dataset.provenance = "commit";
  const date = document.createElement("p");
  date.dataset.provenance = "as-of";
  date.append("As of ", sourced(manifest.as_of_date, manifest.as_of_source));
  const later = document.createElement("p");
  later.textContent = "later studies may supersede these results";
  const attribution = document.createElement("p");
  attribution.textContent = ATTRIBUTION;
  footer.append(commit, date, later, attribution);
}

async function renderOverview() {
  /** @type {Record<string, SourcedValue>} */
  const data = await load("overview.json");
  const meanings = await load("meanings.json");
  const root = document.querySelector("#overview");
  if (!root) return;
  const cards = [
    {
      title: "Send / hold decisions",
      verdict: data.sendhold_verdict,
      secondaryVerdict: data.sendhold_v2_verdict,
      meaning: meanings[data.sendhold_verdict.value],
    },
    {
      title: "Free-agent triage",
      verdict: data.triage_status,
      meaning: data.triage_meaning,
      meaningFromSource: true,
      earlyStop: data.early_stop,
      earlyStopReason: data.early_stop_reason,
    },
  ];
  for (const card of cards) {
    const section = document.createElement("section");
    section.className = "card";
    const heading = document.createElement("h2");
    heading.textContent = card.title;
    const verdict = document.createElement("p");
    verdict.className = "verdict";
    verdict.append("Published verdict: ", sourced(String(card.verdict.value), card.verdict.source));
    verdict.dataset.verdict = "true";
    const meaning = document.createElement("div");
    meaning.dataset.meaning = "true";
    if (card.meaningFromSource) {
      meaning.append(sourced(String(card.meaning.value), card.meaning.source));
    } else if (typeof card.meaning === "string") {
      meaning.textContent = card.meaning;
    } else {
      const alert = document.createElement("p");
      alert.setAttribute("role", "alert");
      alert.dataset.error = "missing-meaning";
      alert.textContent = `No plain-language meaning is defined for verdict ${String(card.verdict.value)}.`;
      meaning.append(alert);
    }
    section.append(heading, verdict, meaning);
    if (card.secondaryVerdict) {
      const previous = document.createElement("p");
      if (typeof meanings[String(card.secondaryVerdict.value)] === "string") {
        previous.dataset.secondaryVerdict = "true";
        previous.textContent = "Verdict under the earlier pre-registered definition: ";
        previous.append(sourced(String(card.secondaryVerdict.value), card.secondaryVerdict.source));
      } else {
        previous.setAttribute("role", "alert");
        previous.dataset.error = "missing-meaning";
        previous.textContent = `No plain-language meaning is defined for verdict ${String(card.secondaryVerdict.value)}.`;
      }
      section.append(previous);
    }
    if (card.earlyStop && card.earlyStop.value === true) {
      if (typeof meanings["Test not run (early stop)"] !== "string") {
        const alert = document.createElement("p");
        alert.setAttribute("role", "alert");
        alert.dataset.error = "missing-meaning";
        alert.textContent = "No plain-language meaning is defined for verdict Test not run (early stop).";
        section.append(alert);
      } else {
        const stop = document.createElement("p");
        stop.textContent = `${meanings["Test not run (early stop)"]}: `;
        stop.append(sourced(String(card.earlyStopReason.value), card.earlyStopReason.source));
        section.append(stop);
      }
    }
    root.append(section);
  }
}

async function renderAbout() {
  /** @type {Record<string, SourcedValue>} */
  const data = await load("about.json");
  /** @type {Manifest} */
  const manifest = await load("manifest.json");
  const root = document.querySelector("#about");
  if (!root) return;
  const sources = document.createElement("section");
  sources.className = "panel";
  sources.innerHTML = "<h2>Sources and request counts</h2>";
  line(sources, "Data source", data.source_names);
  line(sources, "Free-agent source", data.triage_source);
  line(sources, "New requests used", data.request_count);
  line(sources, "Request ceiling", data.request_ceiling);
  line(sources, "Full retrieval request estimate", data.full_request_estimate);
  root.append(sources);
  const termsOfUse = document.createElement("section");
  termsOfUse.className = "panel";
  termsOfUse.innerHTML = "<h2>Terms of use</h2>";
  termsOfUse.append(prose(ATTRIBUTION));
  root.append(termsOfUse);
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "Source manifest";
  details.append(summary);
  const list = document.createElement("ul");
  for (const [file, hash] of Object.entries(manifest.sources)) {
    const item = document.createElement("li");
    item.textContent = `${file}: SHA-256 ${hash}`;
    item.dataset.provenance = "source-hash";
    list.append(item);
  }
  details.append(list);
  root.append(details);
  const glossary = document.createElement("section");
  glossary.innerHTML = "<h2>Glossary</h2>";
  const terms = [
    ["Flagged", "A case selected by a study rule for review."],
    ["Assessed", "A case for which the study could evaluate its recorded outcome."],
    ["Support threshold", "The minimum support level used to decide whether a category is represented well enough."],
    ["Runs left", "The study's estimate of run value left unrealized; it is not interpretable under a NEGATIVE verdict."],
    ["p*", "The break-even probability derived from the 2025 run expectancy."],
    ["Brier", "A score comparing probability predictions with observed outcomes."],
    ["Calibration slope", "A measure of whether predicted differences align with observed differences."],
  ];
  for (const [term, definition] of terms) {
    const detail = document.createElement("details");
    const label = document.createElement("summary");
    label.textContent = term;
    detail.append(label, prose(definition));
    glossary.append(detail);
  }
  root.append(glossary);
}

const ANALYSIS_ORDER = [
  ["v3_primary", "v3 primary"],
  ["v2_preregistered", "v2 pre-registered"],
  ["v3_ambiguous_as_safe", "v3 ambiguous as safe"],
  ["v3_fallback_dropped", "v3 fallback dropped"],
];
const CRITERIA_ORDER = [
  ["brier_beats_constant", "Brier vs constant", "float"],
  ["calibration_slope", "Calibration slope", "float"],
  ["runs_left_excludes_zero", "Runs left", "float"],
  ["negative_control", "Negative control", "probability"],
];
const item = (data, key) => data[key];

/**
 * Wrap a wide table in its own keyboard-reachable scroll container so the
 * page itself never scrolls horizontally.
 * @param {HTMLTableElement} table @param {string} label @param {string} extra
 */
function scrollWrap(table, label, extra = "") {
  const wrap = document.createElement("div");
  wrap.className = `table-wrap ${extra}`.trim();
  wrap.tabIndex = 0;
  wrap.setAttribute("role", "region");
  wrap.setAttribute("aria-label", label);
  wrap.append(table);
  return wrap;
}

/** @param {HTMLElement} root @param {string} text */
function missingMeaning(root, text) {
  root.setAttribute("role", "alert");
  root.dataset.error = "missing-meaning";
  root.textContent = `No plain-language meaning is defined for verdict ${text}.`;
}

function verdictMeaning(root, data, meanings, field) {
  const section = document.createElement("section");
  section.className = "card";
  const heading = document.createElement("h2");
  heading.textContent = "Published verdicts";
  const verdict = document.createElement("p");
  verdict.className = "verdict";
  verdict.dataset.verdict = "true";
  verdict.append("Primary verdict: ", sourced(String(data[field].value), data[field].source));
  const meaning = document.createElement("div");
  meaning.dataset.meaning = "true";
  const mapped = meanings[String(data[field].value)];
  if (typeof mapped === "string") meaning.textContent = mapped;
  else {
    const alert = document.createElement("p");
    missingMeaning(alert, String(data[field].value));
    meaning.append(alert);
  }
  section.append(heading, verdict, meaning);
  const secondary = document.createElement("p");
  secondary.dataset.secondaryVerdict = "true";
  secondary.append("Pre-registered "); proseLabel(secondary, "v2-definition"); secondary.append(" verdict: ");
  secondary.append(sourced(String(data.verdict_v2.value), data.verdict_v2.source));
  if (typeof meanings[String(data.verdict_v2.value)] !== "string") {
    delete secondary.dataset.secondaryVerdict;
    missingMeaning(secondary, String(data.verdict_v2.value));
  }
  section.append(secondary);
  root.append(section);
}

function renderCriteria(root, data, roles) {
  for (const [analysis, title] of ANALYSIS_ORDER) {
    const section = document.createElement("section");
    section.className = "panel";
    const table = document.createElement("table");
    const caption = document.createElement("caption");
    proseLabel(caption, title); caption.append(" analysis, verdict: ");
    caption.append(sourced(String(data[`${analysis}_verdict`].value), data[`${analysis}_verdict`].source));
    table.append(caption);
    const head = document.createElement("tr");
    for (const text of ["Criterion", "Estimate and 95% interval", "Status", "Rule", "Role"]) {
      const th = document.createElement("th"); th.scope = "col";
      if (text.includes("95%")) { th.append("Estimate and "); proseLabel(th, "95% interval"); }
      else th.textContent = text;
      head.append(th);
    }
    const thead = document.createElement("thead"); thead.append(head); table.append(thead);
    const tbody = document.createElement("tbody");
    for (const [key, label, kind] of CRITERIA_ORDER) {
      const role = roles[key];
      const row = document.createElement("tr");
      const titleCell = document.createElement("th"); titleCell.scope = "row"; titleCell.textContent = label; row.append(titleCell);
      const prefix = `${analysis}_${key}_`;
      const estimate = item(data, `${prefix}estimate`);
      const interval = [item(data, `${prefix}lower`), item(data, `${prefix}upper`)];
      const valueCell = document.createElement("td");
      const isRuns = key === "runs_left_excludes_zero";
      if (isRuns && data[`${analysis}_verdict`].value === "NEGATIVE") {
        valueCell.append("Not interpretable under the NEGATIVE verdict");
        const details = document.createElement("details");
        const summary = document.createElement("summary"); summary.textContent = "Failed-model value (not for decisions)";
        const disclosure = document.createElement("p");
        disclosure.append("Estimate: "); appendNumber(disclosure, estimate, kind);
        disclosure.append("; "); proseLabel(disclosure, "95% interval"); disclosure.append(": "); appendNumber(disclosure, interval[0], kind); disclosure.append(" to "); appendNumber(disclosure, interval[1], kind);
        const passed = item(data, `${prefix}passed`);
        const statusText = document.createElement("span");
        statusText.textContent = passed.value ? "Met" : "Not met";
        statusText.dataset.statusSource = passed.source;
        disclosure.append("; Status: ", statusText);
        details.append(summary, disclosure); valueCell.append(details);
      } else {
        appendNumber(valueCell, estimate, kind);
        valueCell.append(" ("); proseLabel(valueCell, "95% interval"); valueCell.append(": "); appendNumber(valueCell, interval[0], kind); valueCell.append(" to "); appendNumber(valueCell, interval[1], kind); valueCell.append(")");
      }
      row.append(valueCell);
      const statusCell = document.createElement("td");
      if (!isRuns || data[`${analysis}_verdict`].value !== "NEGATIVE") {
        const passed = item(data, `${prefix}passed`);
        const statusText = document.createElement("span");
        statusText.textContent = passed.value ? "Met" : "Not met";
        statusText.dataset.statusSource = passed.source;
        statusCell.append(statusText);
      }
      row.append(statusCell);
      const rule = document.createElement("td"); rule.append(sourced(String(item(data, `${prefix}rule`).value), item(data, `${prefix}rule`).source)); row.append(rule);
      const roleCell = document.createElement("td"); roleCell.textContent = role; row.append(roleCell);
      tbody.append(row);
      if (key === "brier_beats_constant") {
        const note = document.createElement("p");
        note.className = "brier-note";
        note.textContent = "The model did not beat a constant guess; the interval includes zero, so this is no evidence of benefit, not evidence of harm. Passing diagnostic rows do not change the verdict.";
        valueCell.append(note);
      }
    }
    table.append(tbody); section.append(scrollWrap(table, `${title} analysis criteria`));
    const footnote = document.createElement("p"); footnote.textContent = "The verdict follows the pre-registered gating rule, not a count of passes."; section.append(footnote);
    root.append(section);
  }
}

function renderDecisionChart(root, data) {
  const section = document.createElement("section"); section.className = "panel";
  const heading = document.createElement("h2"); heading.textContent = "Decision chart"; section.append(heading);
  const cuts = [0, 1].map(i => data[`speed_cut_${i}`]);
  const metadata = document.createElement("p"); metadata.append("Minimum cell n: "); appendNumber(metadata, data.min_cell_n); metadata.append(". Speed tercile cuts: "); appendNumber(metadata, cuts[0]); metadata.append(" and "); appendNumber(metadata, cuts[1]); metadata.append("."); section.append(metadata);
  const table = document.createElement("table"); const caption = document.createElement("caption");
  proseLabel(caption, "v3"); caption.append(" decision chart cells; p* is derived from the "); proseLabel(caption, "2025"); caption.append(" run expectancy. ");
  const caveat = document.createElement("span"); caveat.className = "decision-caveat";
  const quote = document.createElement("span");
  quote.textContent = data.inference_line.value;
  quote.dataset.quoteSource = data.inference_line.source;
  caveat.append(quote);
  caption.append(caveat, " Sends were selected by the coaches; observed success is not the success rate of held runners or of a different policy. Break-even p* is not a recommendation."); table.append(caption);
  const headers = ["Zone group", "Hit type", "Outs", "Speed tercile", "n", "n sent", "Observed send success", "p* (2025 run expectancy)"];
  const tr = document.createElement("tr"); headers.forEach(text => { const th = document.createElement("th"); th.scope = "col"; if (text.includes("2025")) { th.append("p* ("); proseLabel(th, "2025"); th.append(" run expectancy)"); } else th.textContent = text; tr.append(th); });
  const thead = document.createElement("thead"); thead.append(tr); table.append(thead);
  const body = document.createElement("tbody");
  const count = Object.keys(data).filter(k => /^cell_\d+_zone_group$/.test(k)).length;
  for (let i = 0; i < count; i++) {
    const row = document.createElement("tr");
    for (const field of ["zone_group", "hit_type", "outs", "speed_tercile", "n", "n_sent", "observed_send_success", "p_star"]) {
      const td = document.createElement("td"), entry = data[`cell_${i}_${field}`];
      if (typeof entry.value === "number") appendNumber(td, entry, field === "observed_send_success" || field === "p_star" ? "probability" : "float");
      else td.append(sourced(formatValue(entry.value), entry.source));
      if (field === "n") {
        const low = data[`cell_${i}_low_n`];
        if (low.value) td.append(" (low n)");
      }
      row.append(td);
    }
    body.append(row);
  }
  table.append(body); section.append(scrollWrap(table, "v3 decision chart cells", "decision-table-wrap")); root.append(section);
}

function renderSendhold(data, meanings, roles) {
  const root = document.querySelector("#sendhold"); if (!root) return;
  verdictMeaning(root, data, meanings, "verdict");
  renderCriteria(root, data, roles);
  renderDecisionChart(root, data);
  renderLabelCounts(root, data);
  const feasibility = document.createElement("section"); feasibility.className = "panel";
  const h2 = document.createElement("h2"); h2.textContent = "Feasibility"; feasibility.append(h2);
  const feasible = document.createElement("p");
  feasible.append("Feasibility verdict: ", sourced(String(data.feasibility_verdict.value), data.feasibility_verdict.source));
  feasibility.append(feasible);
  const feasibleMeaning = document.createElement("p");
  if (typeof meanings[String(data.feasibility_verdict.value)] === "string") feasibleMeaning.textContent = meanings[String(data.feasibility_verdict.value)];
  else missingMeaning(feasibleMeaning, String(data.feasibility_verdict.value));
  feasibility.append(feasibleMeaning);
  line(feasibility, "Reason", data.verdict_reason);
  line(feasibility, "New requests used", data.new_requests_used);
  line(feasibility, "Ceiling", data.ceiling); root.append(feasibility);
  const limits = document.createElement("section"); limits.className = "panel"; limits.id = "limits";
  const limitsHeading = document.createElement("h2"); limitsHeading.textContent = "Limits of this result"; limits.append(limitsHeading);
  for (const key of ["unknown_line_0", "unknown_line_1"]) { const p = document.createElement("p"); p.append(data[key].value); p.dataset.quoteSource = data[key].source; limits.append(p); }
  for (const key of Object.keys(data).filter(k => k.startsWith("fit_unknown_"))) {
    const fitUnknown = document.createElement("p");
    fitUnknown.append(sourced(String(data[key].value), data[key].source)); limits.append(fitUnknown);
  }
  const reduced = document.createElement("p"); reduced.append("Reduced covariate set: ");
  reduced.append(sourced(formatValue(data.covariate_sent_out.value), data.covariate_sent_out.source, "display", "float"), " of ");
  reduced.append(sourced(formatValue(data.covariate_required_sent_out.value), data.covariate_required_sent_out.source, "display", "float"), " required"); limits.append(reduced);
  for (const [label, entry] of [["sent out", data.covariate_sent_out], ["required sent out", data.covariate_required_sent_out]]) {
    const full = document.createElement("details"), summary = document.createElement("summary"), value = document.createElement("p");
    summary.textContent = `Full published value (${label})`;
    value.append(sourced(formatFull(entry.value), entry.source, "full", "float")); full.append(summary, value); limits.append(full);
  }
  const history = document.createElement("p"); history.append("Label history "); proseLabel(history, "v1"); history.append(" to "); proseLabel(history, "v3"); history.append(": ");
  const link = document.createElement("a"); link.href = "https://github.com/howlcipher/howl-cubs-dogfood/blob/main/experiments/R003-SENDHOLD-DESIGN.md"; link.rel = "noopener noreferrer"; link.textContent = "design record (external link)"; history.append(link); limits.append(history); root.append(limits);
}

function renderLabelCounts(root, data) {
  const section = document.createElement("section"); section.className = "panel";
  const heading = document.createElement("h2"); heading.textContent = "Label counts"; section.append(heading);
  const labels = Object.keys(data).filter(k => k.startsWith("v3_primary_labels_2025_")).map(k => k.slice("v3_primary_labels_2025_".length));
  const rows = [];
  for (const [analysis, title] of ANALYSIS_ORDER) {
    rows.push({ name: title, kind: "analysis", version: data[`${analysis}_label_version`], season: null, pointer: label => data[`${analysis}_labels_2025_${label}`] });
  }
  for (const version of ["v3", "v2"]) {
    rows.push({ name: version, kind: "fit", version, season: data.fit_season, pointer: label => data[`fit_${version}_label_${label}`] });
  }
  const table = document.createElement("table"), caption = document.createElement("caption");
  caption.append("Per-season label counts by label version"); table.append(caption);
  const head = document.createElement("tr");
  for (const text of ["Source", "Label version", "Season", ...labels]) { const th = document.createElement("th"); th.scope = "col"; th.textContent = text; head.append(th); }
  const thead = document.createElement("thead"); thead.append(head); table.append(thead);
  const body = document.createElement("tbody");
  for (const row of rows) {
    const tr = document.createElement("tr");
    const rowHead = document.createElement("th"); rowHead.scope = "row"; proseLabel(rowHead, row.name); rowHead.append(` ${row.kind}`); tr.append(rowHead);
    const versionCell = document.createElement("td");
    if (typeof row.version === "string") proseLabel(versionCell, row.version); else versionCell.append(sourced(String(row.version.value), row.version.source));
    const seasonCell = document.createElement("td");
    if (row.season) {
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.append(sourced(
        formatValue(row.season.value), row.season.source, "display", "float"
      ));
      const full = document.createElement("p");
      full.append(sourced(
        formatFull(row.season.value), row.season.source, "full", "float"
      ));
      details.append(summary, full);
      seasonCell.append(details);
    } else {
      proseLabel(seasonCell, "2025");
    }
    tr.append(versionCell, seasonCell);
    for (const label of labels) { const td = document.createElement("td"); const entry = row.pointer(label); if (entry) appendNumber(td, entry); tr.append(td); }
    body.append(tr);
  }
  table.append(body); section.append(scrollWrap(table, "Label counts")); root.append(section);
}

try {
  const manifest = await load("manifest.json");
  renderFooter(manifest);
  if (document.body.dataset.page === "overview") await renderOverview();
  if (document.body.dataset.page === "about") await renderAbout();
  if (document.body.dataset.page === "sendhold") {
    const data = await load("sendhold.json");
    const meanings = await load("meanings.json");
    const roles = await load("roles.json");
    renderSendhold(data, meanings, roles);
  }
} catch (error) {
  const main = document.querySelector("main");
  if (main) main.append("Explorer data could not be loaded.");
  console.error(error);
}
