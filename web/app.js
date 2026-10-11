/** @typedef {{value: unknown, source: string}} SourcedValue */
/** @typedef {{research_digest: string, as_of_date: string, as_of_source: string, sources: Record<string, string>, default_visible: string[], disclosed_only: string[]}} Manifest */
import { formatFull, formatValue, isSmall } from "./format.js";

const NOTE_SMALL = "small values shown to 2 significant figures";
const PAGE_NOTE = `Values shown to two decimals (three for probabilities and rates); ${NOTE_SMALL}.`;

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
 * A displayed number: its text is tagged with its source, and marked when it
 * is shown to 2 significant figures so the page can say so.
 * @param {SourcedValue} item @param {string} kind
 */
function numberSpan(item, kind = "float") {
  const span = sourced(formatValue(item.value, kind), item.source, "display", kind);
  if (isSmall(item.value, kind)) span.dataset.small = "true";
  return span;
}

/**
 * One disclosure listing the full published value of every number in a table
 * row or value group, each with its own source pointer.
 * Labels must not contain digits.
 * @param {HTMLElement} root @param {[string, SourcedValue, string?][]} entries
 */
function fullValues(root, entries) {
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "Full published value";
  details.append(summary);
  for (const [label, entry, kind = "float"] of entries) {
    const p = document.createElement("p");
    p.append(`${label}: `, sourced(formatFull(entry.value), entry.source, "full", kind));
    details.append(p);
  }
  root.append(details);
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
  p.append(`${label}: `, numberSpan(item, kind));
  if (numericFloat) {
    const note = document.createElement("span");
    const small = isSmall(item.value, kind) ? `; ${NOTE_SMALL}` : "";
    note.textContent = ` (shown to ${kind === "probability" || kind === "rate" ? "three" : "two"} decimals${small})`;
    note.dataset.provenance = "format-note";
    p.append(note);
  }
  root.append(p);
  if (typeof item.value === "number" || Array.isArray(item.value)) {
    fullValues(root, [["Value", item, kind]]);
  }
}

/**
 * Say, once per panel or card, that small values are shown to 2 significant
 * figures, unless a line() note in that panel already says so.
 */
function addSmallValueNotes() {
  const scopes = [...document.querySelectorAll(".panel, .card")];
  const targets = scopes.length ? scopes : [document.querySelector("main")];
  for (const scope of targets) {
    if (!scope || !scope.querySelector('[data-src][data-small]')) continue;
    const noted = [...scope.querySelectorAll('[data-provenance="format-note"]')]
      .some((note) => note.textContent.includes(NOTE_SMALL));
    if (noted) continue;
    const note = document.createElement("p");
    note.textContent = PAGE_NOTE;
    note.dataset.provenance = "format-note";
    scope.append(note);
  }
}

/** @param {Manifest} manifest */
function renderFooter(manifest) {
  const footer = document.querySelector("#footer");
  if (!footer) return;
  const digest = document.createElement("p");
  digest.textContent = `Research digest: ${manifest.research_digest.slice(0, 12)}`;
  digest.dataset.provenance = "research-digest";
  const fullDigest = document.createElement("details");
  const digestSummary = document.createElement("summary");
  digestSummary.textContent = "Full research digest";
  const digestValue = document.createElement("p");
  digestValue.textContent = manifest.research_digest;
  digestValue.dataset.provenance = "research-digest";
  fullDigest.append(digestSummary, digestValue);
  const date = document.createElement("p");
  date.dataset.provenance = "as-of";
  date.append("As of ", sourced(manifest.as_of_date, manifest.as_of_source));
  const later = document.createElement("p");
  later.textContent = "later studies may supersede these results";
  const attribution = document.createElement("p");
  attribution.textContent = ATTRIBUTION;
  footer.append(digest, fullDigest, date, later, attribution);
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

const criteriaFull = (estimate, interval, kind) => [
  ["Estimate", estimate, kind], ["Interval lower", interval[0], kind], ["Interval upper", interval[1], kind],
];

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
        disclosure.append("Estimate: ", numberSpan(estimate, kind));
        disclosure.append("; "); proseLabel(disclosure, "95% interval"); disclosure.append(": ", numberSpan(interval[0], kind), " to ", numberSpan(interval[1], kind));
        const passed = item(data, `${prefix}passed`);
        const statusText = document.createElement("span");
        statusText.textContent = passed.value ? "Met" : "Not met";
        statusText.dataset.statusSource = passed.source;
        disclosure.append("; Status: ", statusText);
        details.append(summary, disclosure); valueCell.append(details);
        fullValues(details, criteriaFull(estimate, interval, kind));
      } else {
        valueCell.append(numberSpan(estimate, kind));
        valueCell.append(" ("); proseLabel(valueCell, "95% interval"); valueCell.append(": ", numberSpan(interval[0], kind), " to ", numberSpan(interval[1], kind), ")");
        fullValues(valueCell, criteriaFull(estimate, interval, kind));
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

const DECISION_LABELS = {
  outs: "Outs", speed_tercile: "Speed tercile", n: "Cell size", n_sent: "Sent",
  observed_send_success: "Observed send success", p_star: "Break-even",
  zone_group: "Zone group", hit_type: "Hit type",
};

function renderDecisionChart(root, data) {
  const section = document.createElement("section"); section.className = "panel";
  const heading = document.createElement("h2"); heading.textContent = "Decision chart"; section.append(heading);
  const cuts = [0, 1].map(i => data[`speed_cut_${i}`]);
  const metadata = document.createElement("p"); metadata.append("Minimum cell n: ", numberSpan(data.min_cell_n), ". Speed tercile cuts: ", numberSpan(cuts[0]), " and ", numberSpan(cuts[1]), "."); section.append(metadata);
  fullValues(section, [["Minimum cell size", data.min_cell_n], ["First cut", cuts[0]], ["Second cut", cuts[1]]]);
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
    const full = [];
    let last = null;
    for (const field of ["zone_group", "hit_type", "outs", "speed_tercile", "n", "n_sent", "observed_send_success", "p_star"]) {
      const td = document.createElement("td"), entry = data[`cell_${i}_${field}`];
      if (typeof entry.value === "number") {
        const kind = field === "observed_send_success" || field === "p_star" ? "probability" : "float";
        td.append(numberSpan(entry, kind));
        full.push([DECISION_LABELS[field], entry, kind]);
      } else td.append(sourced(formatValue(entry.value), entry.source));
      if (field === "n") {
        const low = data[`cell_${i}_low_n`];
        if (low.value) td.append(" (low n)");
      }
      row.append(td);
      last = td;
    }
    if (full.length) fullValues(last, full);
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
  reduced.append(numberSpan(data.covariate_sent_out), " of ");
  reduced.append(numberSpan(data.covariate_required_sent_out), " required"); limits.append(reduced);
  fullValues(limits, [["Sent out", data.covariate_sent_out], ["Required sent out", data.covariate_required_sent_out]]);
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
    const full = [];
    if (row.season) {
      seasonCell.append(numberSpan(row.season));
      full.push(["Season", row.season]);
    } else {
      proseLabel(seasonCell, "2025");
    }
    tr.append(versionCell, seasonCell);
    for (const label of labels) {
      const td = document.createElement("td"); const entry = row.pointer(label);
      if (entry) { td.append(numberSpan(entry)); full.push([label, entry]); }
      tr.append(td);
    }
    if (full.length) fullValues(tr.lastElementChild, full);
    body.append(tr);
  }
  table.append(body); section.append(scrollWrap(table, "Label counts")); root.append(section);
}

const POOL_RANKINGS = ["B0", "B1", "B2", "P", "M"];
const POOL_BASELINES = ["B0", "B1", "B2", "P"];
const POOL_CUTOFFS = ["25", "50", "100"];
const CUTOFF_WORDS = ["First", "Second", "Third"];

/** @param {HTMLElement} root @param {string} id @param {string} title */
function panelSection(root, id, title) {
  const section = document.createElement("section");
  section.className = "panel"; section.id = id;
  const heading = document.createElement("h2"); heading.textContent = title; section.append(heading);
  root.append(section);
  return section;
}

/** Append a verbatim research line as its own quoted paragraph. */
function quoteParagraph(root, entry) {
  const p = document.createElement("p");
  p.textContent = entry.value; p.dataset.quoteSource = entry.source;
  root.append(p);
}

function columnHeader(...parts) {
  const th = document.createElement("th"); th.scope = "col";
  for (const part of parts) {
    if (part && part.label) proseLabel(th, part.label); else th.append(part);
  }
  return th;
}

function numberCell(entry, kind) {
  const td = document.createElement("td");
  td.append(numberSpan(entry, kind));
  return td;
}

/** Give a table row its one full-value disclosure, in its last cell. */
function rowFullValues(row, entries) {
  fullValues(row.lastElementChild, entries);
}

function renderMilbfaStatus(root, data, meanings) {
  const section = panelSection(root, "status", "Status");
  const method = document.createElement("p"); method.dataset.status = "method";
  proseLabel(method, "R001"); method.append(" method status: ", sourced(String(data.method_status.value), data.method_status.source));
  section.append(method);
  // The line is tied to the recorded stop flag, so it cannot outlive a test that ran.
  if (data.early_stop.value === true) {
    const stop = document.createElement("p"); stop.dataset.status = "early-stop";
    const label = "Test not run (early stop)";
    if (typeof meanings[label] !== "string") {
      stop.setAttribute("role", "alert"); stop.dataset.error = "missing-meaning";
      stop.textContent = `No plain-language meaning is defined for verdict ${label}.`;
    } else {
      stop.append(`${label}: `);
      if (meanings[label] !== label) stop.append(`${meanings[label]} `);
      stop.append(sourced(String(data.early_stop_reason.value), data.early_stop_reason.source));
    }
    section.append(stop);
  }
  const holdout = document.createElement("p"); holdout.dataset.status = "holdout";
  holdout.append("Holdout untouched: ");
  holdout.append(numberSpan(data.holdout_excluded));
  section.append(holdout);
  fullValues(section, [["Holdout excluded", data.holdout_excluded]]);
}

function renderMilbfaRankings(section, data) {
  const table = document.createElement("table"), caption = document.createElement("caption");
  caption.append("Whole-pool ranking metrics for validation year ", sourced(formatValue(data.validation_year.value), data.validation_year.source), "; comparator ", sourced(String(data.comparator.value), data.comparator.source));
  table.classList.add("ranking-table"); table.append(caption);
  const head = document.createElement("tr");
  head.append(columnHeader("Ranking"), columnHeader("N"), columnHeader("Positives"), columnHeader("Base rate"));
  POOL_CUTOFFS.forEach((cutoff, index) => {
    const k = data[`top_k_${index}`];
    head.append(columnHeader("Top ", sourced(formatValue(k.value), k.source), " hits"), columnHeader("Top ", sourced(formatValue(k.value), k.source), " precision"));
  });
  head.append(columnHeader("AUROC"));
  const thead = document.createElement("thead"); thead.append(head); table.append(thead);
  const body = document.createElement("tbody");
  for (const ranking of POOL_RANKINGS) {
    const row = document.createElement("tr");
    const rowHead = document.createElement("th"); rowHead.scope = "row"; proseLabel(rowHead, ranking); row.append(rowHead);
    row.append(numberCell(data.n), numberCell(data.positives), numberCell(data.base_rate, "probability"));
    const full = [["N", data.n], ["Positives", data.positives], ["Base rate", data.base_rate, "probability"]];
    for (const [index, cutoff] of POOL_CUTOFFS.entries()) {
      const name = CUTOFF_WORDS[index];
      const hits = data[`${ranking}_top_${cutoff}_hits`], precision = data[`${ranking}_top_${cutoff}_precision`];
      row.append(numberCell(hits), numberCell(precision, "probability"));
      full.push([`${name} cutoff hits`, hits], [`${name} cutoff precision`, precision, "probability"]);
    }
    row.append(numberCell(data[`${ranking}_auroc`], "probability"));
    full.push(["AUROC", data[`${ranking}_auroc`], "probability"]);
    rowFullValues(row, full);
    body.append(row);
  }
  table.append(body); section.append(scrollWrap(table, "Whole-pool ranking metrics"));
}

function renderMilbfaBootstrap(section, data) {
  const table = document.createElement("table"), caption = document.createElement("caption");
  caption.append("Paired bootstrap, M minus each baseline, validation year ", sourced(formatValue(data.validation_year.value), data.validation_year.source));
  table.classList.add("ranking-table"); table.append(caption);
  const head = document.createElement("tr");
  head.append(columnHeader("Baseline"), columnHeader("N"), columnHeader("Positives"), columnHeader("Mean difference"), columnHeader({ label: "95% interval" }), columnHeader("Resamples"));
  const thead = document.createElement("thead"); thead.append(head); table.append(thead);
  const body = document.createElement("tbody");
  for (const baseline of POOL_BASELINES) {
    const row = document.createElement("tr");
    const rowHead = document.createElement("th"); rowHead.scope = "row"; proseLabel(rowHead, baseline); row.append(rowHead);
    const interval = document.createElement("td");
    const lower = data[`boot_${baseline}_lower`], upper = data[`boot_${baseline}_upper`];
    const mean = data[`boot_${baseline}_mean`], resamples = data[`boot_${baseline}_resamples`];
    interval.append(numberSpan(lower, "probability"), " to ", numberSpan(upper, "probability"));
    row.append(numberCell(data.n), numberCell(data.positives), numberCell(mean, "probability"), interval, numberCell(resamples));
    rowFullValues(row, [["N", data.n], ["Positives", data.positives], ["Mean difference", mean, "probability"], ["Interval lower", lower, "probability"], ["Interval upper", upper, "probability"], ["Resamples", resamples]]);
    body.append(row);
  }
  table.append(body); section.append(scrollWrap(table, "Paired bootstrap, M minus baseline"));
}

function unknownList(root, data) {
  const list = document.createElement("ul");
  for (const key of Object.keys(data).filter(k => /^unknown_\d+$/.test(k))) {
    const item = document.createElement("li");
    item.append(sourced(String(data[key].value), data[key].source));
    list.append(item);
  }
  root.append(list);
}

function renderMilbfa(data, meanings) {
  const root = document.querySelector("#milbfa"); if (!root) return;
  renderMilbfaStatus(root, data, meanings);
  const exploratory = panelSection(root, "exploratory", "Exploratory whole-pool results");
  const banner = document.createElement("p"); banner.setAttribute("role", "note"); banner.className = "notice";
  const first = document.createElement("span"); first.textContent = data.banner_line_0.value; first.dataset.quoteSource = data.banner_line_0.source;
  const second = document.createElement("span"); second.textContent = data.banner_line_1.value; second.dataset.quoteSource = data.banner_line_1.source;
  banner.append(first, " ", second); exploratory.append(banner);
  renderMilbfaRankings(exploratory, data);
  renderMilbfaBootstrap(exploratory, data);
  const cubs = panelSection(root, "cubs-case", "Cubs case");
  const meaning = document.createElement("p"); meaning.append(sourced(String(data.interpretation.value), data.interpretation.source)); cubs.append(meaning);
  const years = document.createElement("p"); years.append("Cohort years: ");
  Object.keys(data).filter(k => /^cohort_year_\d+$/.test(k)).forEach((key, index) => {
    if (index) years.append(", ");
    years.append(sourced(formatValue(data[key].value), data[key].source));
  });
  const thresholds = document.createElement("p"); thresholds.append("Outcome thresholds: PA ");
  thresholds.append(numberSpan(data.threshold_pa), " and IP ", numberSpan(data.threshold_ip));
  const signing = document.createElement("p"); signing.append("Signing window: ", sourced(String(data.signing_window.value), data.signing_window.source));
  const unknownLabel = document.createElement("p"); unknownLabel.textContent = "Unknowns recorded by the source:";
  cubs.append(years, thresholds);
  fullValues(cubs, [["Plate appearance threshold", data.threshold_pa], ["Innings pitched threshold", data.threshold_ip]]);
  cubs.append(signing, unknownLabel); unknownList(cubs, data);
  const limits = panelSection(root, "limits", "Limits of this result");
  quoteParagraph(limits, data.limit_unknown_line); quoteParagraph(limits, data.limit_inference_line);
  unknownList(limits, data);
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
  if (document.body.dataset.page === "milbfa") {
    renderMilbfa(await load("milbfa.json"), await load("meanings.json"));
  }
  addSmallValueNotes();
} catch (error) {
  const main = document.querySelector("main");
  if (main) main.append("Explorer data could not be loaded.");
  console.error(error);
}
