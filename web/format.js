/** Format a published value for compact display. */
export function formatValue(value, kind = "float") {
  if (Array.isArray(value) && value.length === 2) {
    return `${formatValue(value[0], kind)} to ${formatValue(value[1], kind)}`;
  }
  if (typeof value === "string") return value;
  if (typeof value === "number") {
    if (Number.isInteger(value)) return String(value);
    return value.toFixed(kind === "probability" || kind === "rate" ? 3 : 2);
  }
  return JSON.stringify(value);
}

/** Full precision representation used in the disclosure element. */
export function formatFull(value) {
  if (Array.isArray(value) && value.length === 2) {
    return `${formatFull(value[0])} to ${formatFull(value[1])}`;
  }
  return typeof value === "number" ? String(value) : formatValue(value);
}
