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

try {
  const manifest = await load("manifest.json");
  renderFooter(manifest);
  if (document.body.dataset.page === "overview") await renderOverview();
  if (document.body.dataset.page === "about") await renderAbout();
} catch (error) {
  const main = document.querySelector("main");
  if (main) main.append("Explorer data could not be loaded.");
  console.error(error);
}
