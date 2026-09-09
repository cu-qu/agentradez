"use client";

import type { Decision } from "@/lib/api/types";
import { formatDate, formatDateTime, formatStrike, titleCase } from "@/lib/format";
import { OptionLabel } from "@/components/pnl";
import { StatusPill } from "@/components/ui";

const CONTEXT_LABELS: Record<string, string> = {
  strategy_name: "Strategy",
  tier_name: "Investment tier",
  signal_code: "Signal",
  source_excerpt: "Source",
  suggested_entry_price: "Signal price",
  live_price: "Live price",
  fill_price: "Fill price",
  limit_price: "Limit price",
  slippage_pct: "Slippage",
  max_entry_slippage_pct: "Max slippage",
  equity: "Equity",
  buying_power: "Buying power",
  contract_cost: "Contract cost",
  size_mode: "Size mode",
  risk_quantity: "Risk size (contracts)",
  max_affordable: "Affordable contracts",
  quantity: "Contracts",
  open_positions: "Open positions",
  max_open_positions: "Max open positions",
  max_risk_per_trade_pct: "Risk per trade",
  hard_stop_pct: "Hard stop",
  daily_pnl: "Daily P&L",
  daily_loss_limit_pct: "Daily loss limit",
  gain_pct: "Gain / loss",
  trigger_gain_pct: "Take-profit trigger",
  pct_of_position: "Scale-out",
  realized_pnl: "Realized P&L",
  max_hold_trading_days: "Max hold (trading days)",
  force_exit_time_et: "Expiration exit (ET)",
  remaining_quantity: "Remaining",
  notes: "Notes",
};

const PCT_KEYS = new Set([
  "slippage_pct",
  "max_entry_slippage_pct",
  "max_risk_per_trade_pct",
  "hard_stop_pct",
  "daily_loss_limit_pct",
  "gain_pct",
  "trigger_gain_pct",
  "pct_of_position",
]);

export function decisionTone(
  outcome: string | undefined,
  action?: string,
): "neutral" | "gain" | "loss" | "warn" {
  if (outcome === "passed") return "warn";
  if (action === "stop_loss") return "loss";
  if (action === "enter" || action === "take_profit") return "gain";
  return "neutral";
}

export function DecisionContract({ item }: { item: Decision }) {
  if (!item.ticker) {
    return <span className="text-sm text-muted">{item.strategy_name || "Account"}</span>;
  }
  return (
    <OptionLabel
      ticker={item.ticker}
      optionType={item.option_type || "call"}
      strike={formatStrike(item.strike)}
      expiration={item.expiration ? formatDate(item.expiration) : "—"}
    />
  );
}

export function DecisionPills({ item }: { item: Decision }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <StatusPill tone={decisionTone(item.outcome, item.action)}>
        {item.outcome_label || titleCase(item.outcome)}
      </StatusPill>
      <StatusPill>{item.action_label || titleCase(item.action)}</StatusPill>
      {item.tier_name ? <StatusPill>{item.tier_name}</StatusPill> : null}
    </div>
  );
}

export function DecisionMeta({ item }: { item: Decision }) {
  const bits = [
    item.strategy_name,
    item.signal_code,
    formatDateTime(item.created_at),
  ].filter(Boolean);
  return <p className="text-xs text-muted">{bits.join(" · ")}</p>;
}

export function contextFacts(context: unknown) {
  if (!context || typeof context !== "object" || Array.isArray(context)) return [];
  const record = context as Record<string, unknown>;
  return Object.entries(CONTEXT_LABELS)
    .map(([key, label]) => {
      const raw = record[key];
      if (raw == null || raw === "") return null;
      return { key, label, value: formatContextValue(key, raw) };
    })
    .filter((row): row is { key: string; label: string; value: string } => Boolean(row));
}

function formatContextValue(key: string, raw: unknown): string {
  if (typeof raw === "boolean") return raw ? "Yes" : "No";
  const text = String(raw);
  if (key === "size_mode") {
    if (text === "minimum_contract") return "Starter size (1 contract)";
    if (text === "cash_capped") return "Capped by buying power";
    if (text === "risk") return "Tier risk percent";
    if (text === "unaffordable") return "Not enough cash for 1 contract";
  }
  if (PCT_KEYS.has(key)) {
    const n = Number(text);
    if (Number.isFinite(n)) return `${n.toLocaleString("en-US", { maximumFractionDigits: 2 })}%`;
  }
  return text;
}
