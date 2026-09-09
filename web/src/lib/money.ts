/** Parse API money strings without accumulating floats. */

const DECIMAL = /^-?\d+(?:\.\d+)?$/;

export function parseDecimal(value: string | number | null | undefined): number | null {
  if (value == null || value === "") return null;
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  const trimmed = value.trim();
  if (!DECIMAL.test(trimmed)) return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}

export function formatUsd(
  value: string | number | null | undefined,
  options?: { signed?: boolean },
): string {
  const n = parseDecimal(value);
  if (n == null) return "—";
  const formatted = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(Math.abs(n));
  if (options?.signed) {
    if (n > 0) return `+${formatted}`;
    if (n < 0) return `−${formatted}`;
  }
  return n < 0 ? `−${formatted}` : formatted;
}

export function formatPct(value: string | number | null | undefined): string {
  const n = parseDecimal(value);
  if (n == null) return "—";
  return `${n}%`;
}

export function pnlTone(
  value: string | number | null | undefined,
): "gain" | "loss" | "neutral" {
  const n = parseDecimal(value);
  if (n == null || n === 0) return "neutral";
  return n > 0 ? "gain" : "loss";
}
