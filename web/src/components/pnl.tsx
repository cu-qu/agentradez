"use client";

import { formatUsd, pnlTone } from "@/lib/money";
import { HIDDEN_AMOUNT, useHideAmounts } from "@/lib/privacy";

function maskAmount(formatted: string, hide: boolean): string {
  return hide && formatted !== "—" ? HIDDEN_AMOUNT : formatted;
}

export function PnlValue({
  value,
  signed = true,
  className = "",
}: {
  value: string | number | null | undefined;
  signed?: boolean;
  className?: string;
}) {
  const { hideAmounts } = useHideAmounts();
  const formatted = formatUsd(value, { signed });
  const hidden = hideAmounts && formatted !== "—";
  const tone = hidden ? "neutral" : pnlTone(value);
  const color =
    tone === "gain" ? "text-gain" : tone === "loss" ? "text-loss" : "text-foreground";
  return (
    <span className={`tabular ${color} ${className}`}>
      {maskAmount(formatted, hideAmounts)}
    </span>
  );
}

export function UsdValue({
  value,
  signed = false,
  className = "",
  hide = false,
}: {
  value: string | number | null | undefined;
  signed?: boolean;
  className?: string;
  hide?: boolean;
}) {
  const { hideAmounts } = useHideAmounts();
  return (
    <span className={`tabular ${className}`}>
      {maskAmount(formatUsd(value, { signed }), hideAmounts || hide)}
    </span>
  );
}

export function OptionLabel({
  ticker,
  optionType,
  strike,
  expiration,
}: {
  ticker: string;
  optionType: string;
  strike: string;
  expiration: string;
}) {
  const kind = optionType === "put" ? "Put" : "Call";
  return (
    <span>
      <span className="font-medium">{ticker}</span>{" "}
      <span className="text-muted">
        {strike} {kind} · {expiration}
      </span>
    </span>
  );
}
