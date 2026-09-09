"use client";

import { useState } from "react";
import Link from "next/link";

import { useTradesQuery } from "@/lib/api/hooks";
import { pageFromNext } from "@/lib/api/types";
import { formatDate, formatDateTime, formatStrike, titleCase } from "@/lib/format";
import { AppShell } from "@/components/app-shell";
import { RequireAuth } from "@/components/gates";
import { OptionLabel, PnlValue } from "@/components/pnl";
import { Button, Card, EmptyState, Input, Select, Spinner, StatusPill } from "@/components/ui";

const STATUSES = [
  { value: "", label: "All statuses" },
  { value: "pending", label: "Pending" },
  { value: "open", label: "Open" },
  { value: "partially_closed", label: "Partially closed" },
  { value: "closed", label: "Closed" },
  { value: "cancelled", label: "Cancelled" },
];

export default function TradesPage() {
  return (
    <RequireAuth>
      <AppShell>
        <TradeList />
      </AppShell>
    </RequireAuth>
  );
}

function TradeList() {
  const [status, setStatus] = useState("");
  const [ticker, setTicker] = useState("");
  const [tickerInput, setTickerInput] = useState("");
  const [page, setPage] = useState(1);
  const trades = useTradesQuery(true, {
    status: status || undefined,
    ticker: ticker || undefined,
    page,
  });

  const nextPage = pageFromNext(trades.data?.next);
  const prevPage = trades.data?.previous
    ? (pageFromNext(trades.data.previous) ?? 1)
    : null;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Trades</h1>
        <p className="mt-1 text-sm text-muted">
          History of entries, partial closes, and exits.
        </p>
      </div>

      <form
        className="flex flex-wrap gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setTicker(tickerInput.trim().toUpperCase());
          setPage(1);
        }}
      >
        <Select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
          className="w-48"
        >
          {STATUSES.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </Select>
        <Input
          placeholder="Ticker"
          value={tickerInput}
          onChange={(e) => setTickerInput(e.target.value)}
          className="w-40"
        />
        <Button type="submit" variant="secondary">
          Filter
        </Button>
      </form>

      <Card>
        {trades.isLoading ? (
          <Spinner />
        ) : (trades.data?.results.length ?? 0) === 0 ? (
          <EmptyState title="No trades yet" body="Filled and cancelled orders will show up here." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[800px] text-left text-sm">
              <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Contract</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Qty</th>
                  <th className="px-4 py-3 font-medium">Entry</th>
                  <th className="px-4 py-3 font-medium">Realized</th>
                  <th className="px-4 py-3 font-medium">Entered</th>
                </tr>
              </thead>
              <tbody>
                {trades.data?.results.map((trade) => (
                  <tr key={trade.id} className="border-b border-border last:border-b-0">
                    <td className="px-4 py-3">
                      <Link href={`/trades/${trade.id}`} className="hover:underline">
                        <OptionLabel
                          ticker={trade.ticker}
                          optionType={trade.option_type}
                          strike={formatStrike(trade.strike)}
                          expiration={formatDate(trade.expiration)}
                        />
                      </Link>
                      <p className="text-xs text-muted">{trade.signal_code}</p>
                    </td>
                    <td className="px-4 py-3">
                      <StatusPill tone={statusTone(trade.status ?? "open")}>
                        {titleCase(trade.status ?? "open")}
                      </StatusPill>
                    </td>
                    <td className="tabular px-4 py-3">
                      {trade.remaining_quantity}/{trade.entry_quantity}
                    </td>
                    <td className="tabular px-4 py-3">{trade.entry_price}</td>
                    <td className="px-4 py-3">
                      <PnlValue value={trade.realized_pnl} />
                    </td>
                    <td className="px-4 py-3 text-muted">
                      {formatDateTime(trade.entered_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {trades.data && trades.data.count > (trades.data.results.length || 0) ? (
        <div className="flex items-center justify-between text-sm text-muted">
          <span>{trades.data.count} trades</span>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              disabled={page <= 1}
              onClick={() => setPage(prevPage ?? Math.max(1, page - 1))}
            >
              Previous
            </Button>
            <Button
              variant="secondary"
              disabled={!nextPage}
              onClick={() => nextPage && setPage(nextPage)}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function statusTone(status: string): "neutral" | "gain" | "loss" | "warn" {
  if (status === "open") return "gain";
  if (status === "pending" || status === "partially_closed") return "warn";
  if (status === "cancelled") return "warn";
  return "neutral";
}
