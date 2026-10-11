const isRate = (kind) => kind === "probability" || kind === "rate";

/** True when two (or three) decimals would print a non-zero float as zero. */
function readsAsZero(value, kind) {
  return value !== 0 && Math.abs(value) < (isRate(kind) ? 0.0005 : 0.005);
}

/** Expand a number printed in exponent form into plain decimal digits. */
function toPlain(text) {
  const match = /^(-?)(\d)(?:\.(\d+))?e([+-]\d+)$/.exec(text);
  if (!match) return text;
  const [, sign, lead, fraction = "", exponent] = match;
  const digits = lead + fraction;
  const exp = Number(exponent);
  if (exp < 0) return `${sign}0.${"0".repeat(-exp - 1)}${digits}`;
  const whole = digits.slice(0, exp + 1).padEnd(exp + 1, "0");
  const rest = digits.slice(exp + 1);
  return `${sign}${whole}${rest ? `.${rest}` : ""}`;
}

/** Two significant figures in plain decimal form, never exponent form. */
function twoSignificant(value) {
  return toPlain(value.toExponential(1));
}

/** True when a displayed value is shown to 2 significant figures. */
export function isSmall(value, kind = "float") {
  if (Array.isArray(value)) return value.some((part) => isSmall(part, kind));
  return typeof value === "number" && !Number.isInteger(value)
    && readsAsZero(value, kind);
}

/** Format a published value for compact display. */
export function formatValue(value, kind = "float") {
  if (Array.isArray(value) && value.length === 2) {
    return `${formatValue(value[0], kind)} to ${formatValue(value[1], kind)}`;
  }
  if (typeof value === "string") return value;
  if (typeof value === "number") {
    if (Number.isInteger(value)) return String(value);
    if (readsAsZero(value, kind)) return twoSignificant(value);
    return value.toFixed(isRate(kind) ? 3 : 2);
  }
  return JSON.stringify(value);
}

/** Full precision representation used in the disclosure element. */
export function formatFull(value) {
  if (Array.isArray(value) && value.length === 2) {
    return `${formatFull(value[0])} to ${formatFull(value[1])}`;
  }
  return typeof value === "number" ? toPlain(String(value)) : formatValue(value);
}
