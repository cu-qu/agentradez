"use client";

import { ApiError } from "@/lib/api/client";
import { useStrategiesQuery } from "@/lib/api/hooks";
import type { Strategy } from "@/lib/api/types";
import { titleCase } from "@/lib/format";
import { Card, StatusPill } from "@/components/ui";

export function PublicStrategies() {
  const strategies = useStrategiesQuery(true);
  const rows = (strategies.data ?? []).filter(
    (strategy) => strategy.visibility !== "restricted" && strategy.is_active !== false,
  );

  if (strategies.isLoading) {
    return <p className="text-sm text-muted">Loading public strategies…</p>;
  }

  if (strategies.isError) {
    const needsAccount =
      strategies.error instanceof ApiError &&
      (strategies.error.status === 401 || strategies.error.status === 403);
    return (
      <Card className="p-4">
        <p className="text-sm text-muted">
          {needsAccount
            ? "Create an account or sign in to see the public strategies you can pick."
            : "Could not load public strategies right now. Try again in a moment."}
        </p>
      </Card>
    );
  }

  if (rows.length === 0) {
    return (
      <Card className="p-4">
        <p className="text-sm text-muted">
          No public strategies are listed right now. Copy Trade and Research /
          Breakthrough are the types you can choose when one is published.
        </p>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {rows.map((strategy) => (
        <StrategyCard key={strategy.id} strategy={strategy} />
      ))}
    </div>
  );
}

function StrategyCard({ strategy }: { strategy: Strategy }) {
  const typeLabel = strategyTypeLabel(strategy.strategy_type);
  const sourceLabel =
    strategy.strategy_type === "copy_trade"
      ? strategy.signal_source === "chat_group"
        ? "Chat group"
        : "X"
      : null;

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-medium text-foreground">{strategy.name}</h3>
        {typeLabel ? <StatusPill>{typeLabel}</StatusPill> : null}
        {sourceLabel ? <StatusPill>{sourceLabel}</StatusPill> : null}
      </div>
      <p className="mt-2 text-sm text-muted">
        {strategy.description || strategyTypeFallback(strategy.strategy_type)}
      </p>
      {strategy.source_handle ? (
        <p className="mt-2 text-xs text-muted">
          Watches @{strategy.source_handle}
        </p>
      ) : null}
    </Card>
  );
}

function strategyTypeLabel(value: string | undefined): string | null {
  if (!value) return null;
  if (value === "copy_trade") return "Copy Trade";
  if (value === "research_breakthrough") return "Research / Breakthrough";
  return titleCase(value);
}

function strategyTypeFallback(value: string | undefined): string {
  if (value === "research_breakthrough") {
    return "Watches headlines and catalysts, then may propose an options trade. It does not copy another trader’s ticket.";
  }
  return "Watches a source, reads option ideas, and copies the ones that pass your investment tier into the Agentic account.";
}
