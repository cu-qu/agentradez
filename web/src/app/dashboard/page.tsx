"use client";

import type { ReactNode } from "react";
import Link from "next/link";

import {
  useBrokersQuery,
  usePerformanceQuery,
  usePositionsQuery,
} from "@/lib/api/hooks";
import { formatDate, formatStrike } from "@/lib/format";
import { AccountsPanel, connectedBroker } from "@/components/accounts";
import { AppShell } from "@/components/app-shell";
import { RequireAuth } from "@/components/gates";
import { OptionLabel, PnlValue } from "@/components/pnl";
import { Banner, Card, EmptyState, Spinner } from "@/components/ui";

export default function DashboardPage() {
  return (
    <RequireAuth>
      <AppShell>
        <Dashboard />
      </AppShell>
    </RequireAuth>
  );
}

function Dashboard() {
  const brokers = useBrokersQuery(true);
  const performance = usePerformanceQuery(true);
  const positions = usePositionsQuery(true);

  const broker = connectedBroker(brokers.data);
  const hasBroker = Boolean(broker);
  const robinhoodNeedsAccount = Boolean(
    brokers.data?.some(
      (connection) =>
        connection.broker === "robinhood" &&
        connection.status === "connected" &&
        !connection.agentic_ready,
    ),
  );

  return (
    <div className="flex flex-col gap-8">
      <AccountsPanel />

      {performance.data?.is_paused_daily_loss ? (
        <Banner tone="warning">
          New entries are paused after today’s loss limit. Open positions are
          still managed.
        </Banner>
      ) : null}

      {performance.isLoading || positions.isLoading ? (
        <Spinner />
      ) : !performance.data ? (
        <Banner tone="danger">Could not load performance.</Banner>
      ) : (
        <>
          <section>
            <p className="text-xs uppercase tracking-[0.16em] text-muted">
              Lifetime P&L
            </p>
            <PnlValue
              value={performance.data.lifetime_total_pnl}
              className="mt-2 block text-4xl font-semibold tracking-tight"
            />
            <div className="mt-4 grid gap-3 sm:grid-cols-4">
              <Stat
                label="Realized"
                value={<PnlValue value={performance.data.lifetime_realized_pnl} />}
              />
              <Stat
                label="Unrealized"
                value={
                  <PnlValue value={performance.data.lifetime_unrealized_pnl} />
                }
              />
              <Stat
                label="Today"
                value={<PnlValue value={performance.data.daily_realized_pnl} />}
              />
              <Stat
                label="This week"
                value={<PnlValue value={performance.data.weekly_realized_pnl} />}
              />
            </div>
          </section>

          <section>
            <div className="mb-3 flex items-end justify-between">
              <h2 className="text-sm font-medium uppercase tracking-wide text-muted">
                Open positions
              </h2>
              <p className="text-xs text-muted">
                {performance.data.open_positions} open ·{" "}
                {performance.data.closed_trades} closed
              </p>
            </div>
            <Card>
              {(positions.data?.length ?? 0) === 0 ? (
                <EmptyState
                  title={
                    robinhoodNeedsAccount
                      ? "Turn on an Agentic account"
                      : hasBroker
                        ? "Waiting for the next signal"
                        : "No open positions"
                  }
                  body={
                    robinhoodNeedsAccount
                      ? "Robinhood is connected. Toggle an Agentic account above so copy trades can run."
                      : hasBroker
                        ? "Automation will enter when a Copy Trade signal is a fit."
                        : "Connect an account to start copy-trading."
                  }
                />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[640px] text-left text-sm">
                    <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
                      <tr>
                        <th className="px-4 py-3 font-medium">Contract</th>
                        <th className="px-4 py-3 font-medium">Qty</th>
                        <th className="px-4 py-3 font-medium">Entry</th>
                        <th className="px-4 py-3 font-medium">Mark</th>
                        <th className="px-4 py-3 font-medium">Unrealized</th>
                      </tr>
                    </thead>
                    <tbody>
                      {positions.data?.map((pos) => (
                        <tr
                          key={pos.id}
                          className="border-b border-border last:border-b-0"
                        >
                          <td className="px-4 py-3">
                            <Link
                              href={`/trades/${pos.trade_id}`}
                              className="hover:underline"
                            >
                              <OptionLabel
                                ticker={pos.ticker}
                                optionType={pos.option_type}
                                strike={formatStrike(pos.strike)}
                                expiration={formatDate(pos.expiration)}
                              />
                            </Link>
                          </td>
                          <td className="tabular px-4 py-3">{pos.quantity}</td>
                          <td className="tabular px-4 py-3">
                            {pos.average_entry_price}
                          </td>
                          <td className="tabular px-4 py-3">
                            {pos.current_price ?? "—"}
                          </td>
                          <td className="px-4 py-3">
                            <PnlValue value={pos.unrealized_pnl} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </section>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-4 py-3">
      <p className="text-[11px] uppercase tracking-wide text-muted">{label}</p>
      <div className="mt-1 text-lg font-medium">{value}</div>
    </div>
  );
}
