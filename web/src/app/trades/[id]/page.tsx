"use client";

import { use } from "react";
import Link from "next/link";

import { useTradeQuery } from "@/lib/api/hooks";
import { formatDate, formatDateTime, formatStrike, titleCase } from "@/lib/format";
import { AppShell } from "@/components/app-shell";
import {
  DecisionMeta,
  DecisionPills,
} from "@/components/decisions";
import { RequireAuth } from "@/components/gates";
import { OptionLabel, PnlValue } from "@/components/pnl";
import { Banner, Card, Spinner, StatusPill } from "@/components/ui";

export default function TradeDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const tradeId = Number(id);

  return (
    <RequireAuth>
      <AppShell>
        <TradeDetail tradeId={tradeId} />
      </AppShell>
    </RequireAuth>
  );
}

function TradeDetail({ tradeId }: { tradeId: number }) {
  const tradeQuery = useTradeQuery(true, tradeId);

  if (tradeQuery.isLoading) return <Spinner />;
  if (!tradeQuery.data) {
    return <Banner tone="danger">Trade not found.</Banner>;
  }

  const trade = tradeQuery.data;
  const events = trade.events ?? [];
  const orders = trade.orders ?? [];
  const decisionLogs = trade.decision_logs ?? [];

  return (
    <div className="flex flex-col gap-8">
      <div>
        <Link href="/trades" className="text-sm text-muted hover:text-foreground">
          Trades
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">
          <OptionLabel
            ticker={trade.ticker}
            optionType={trade.option_type}
            strike={formatStrike(trade.strike)}
            expiration={formatDate(trade.expiration)}
          />
        </h1>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <StatusPill tone={statusTone(trade.status ?? "open")}>
            {titleCase(trade.status ?? "open")}
          </StatusPill>
          <span className="text-sm text-muted">{trade.signal_code}</span>
          <span className="text-sm text-muted">{trade.strategy_name}</span>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-4">
        <Metric label="Entry" value={trade.entry_price} />
        <Metric
          label="Qty remaining"
          value={`${trade.remaining_quantity} / ${trade.entry_quantity}`}
        />
        <Metric label="Avg exit" value={trade.average_exit_price ?? "—"} />
        <div className="rounded-lg border border-border bg-surface px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-muted">
            Realized P&L
          </p>
          <PnlValue value={trade.realized_pnl} className="mt-1 block text-lg font-medium" />
        </div>
      </div>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">
          Broker orders
        </h2>
        <Card>
          {orders.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-muted">
              No broker orders recorded.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {orders.map((order) => (
                <li key={order.id} className="flex items-start justify-between gap-4 px-4 py-3">
                  <div>
                    <p className="text-sm font-medium">{titleCase(order.status)}</p>
                    <p className="mt-0.5 text-sm text-muted">
                      {titleCase(order.side)} · {order.broker_order_id || "no order id"}
                    </p>
                    <p className="mt-1 text-xs text-muted">
                      {formatDateTime(order.submitted_at)}
                    </p>
                  </div>
                  <div className="text-right text-sm">
                    <p className="tabular">
                      {order.filled_quantity}/{order.quantity}
                    </p>
                    <p className="text-xs text-muted">
                      {order.filled_avg_price ?? "—"}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">
          Events
        </h2>
        <Card>
          {events.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-muted">
              No events recorded.
            </p>
          ) : (
            <ol className="divide-y divide-border">
              {events.map((event) => (
                <li key={event.id} className="flex items-start justify-between gap-4 px-4 py-3">
                  <div>
                    <p className="text-sm font-medium">{titleCase(event.event_type)}</p>
                    {event.notes ? (
                      <p className="mt-0.5 text-sm text-muted">{event.notes}</p>
                    ) : null}
                    <p className="mt-1 text-xs text-muted">
                      {formatDateTime(event.created_at)}
                    </p>
                  </div>
                  <div className="text-right text-sm">
                    <p className="tabular">
                      {event.quantity} @ {event.price}
                    </p>
                    <PnlValue value={event.realized_pnl} className="text-xs" />
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">
          Strategy decisions
        </h2>
        <Card>
          {decisionLogs.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-muted">
              No strategy decisions recorded for this trade.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {decisionLogs.map((item) => (
                <li key={item.id}>
                  <Link
                    href={`/activity/${item.id}`}
                    className="flex flex-col gap-2 px-4 py-3 hover:bg-surface-2 sm:flex-row sm:items-start sm:justify-between"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{item.title}</p>
                      <p className="mt-1 text-sm text-muted">{item.summary}</p>
                      <div className="mt-2">
                        <DecisionMeta item={item} />
                      </div>
                    </div>
                    <div className="shrink-0">
                      <DecisionPills item={item} />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-4 py-3">
      <p className="text-[11px] uppercase tracking-wide text-muted">{label}</p>
      <p className="tabular mt-1 text-lg font-medium">{value}</p>
    </div>
  );
}

function statusTone(status: string): "neutral" | "gain" | "loss" | "warn" {
  if (status === "open") return "gain";
  if (status === "pending" || status === "partially_closed") return "warn";
  if (status === "cancelled") return "warn";
  return "neutral";
}
