"use client";

import { useState } from "react";

import {
  useAdminStrategySignalsQuery,
  useStrategyLookback,
} from "@/lib/api/hooks";
import type { Signal } from "@/lib/api/types";
import { pageFromNext } from "@/lib/api/types";
import { formatDate, formatDateTime, formatStrike, titleCase } from "@/lib/format";
import { ApiError } from "@/lib/api/client";
import { OptionLabel } from "@/components/pnl";
import { Banner, Button, Card, EmptyState, Select, Spinner, StatusPill } from "@/components/ui";

const LOOKBACK_DAYS = [7, 14, 30, 60, 90];

export function StrategySignalsPanel({
  strategyId,
  showLookback = false,
}: {
  strategyId: number;
  showLookback?: boolean;
}) {
  const [page, setPage] = useState(1);
  const signals = useAdminStrategySignalsQuery(true, strategyId, page);
  const lookback = useStrategyLookback();
  const [days, setDays] = useState(30);
  const [result, setResult] = useState<string>("");
  const [error, setError] = useState("");

  const nextPage = pageFromNext(signals.data?.next);
  const prevPage = signals.data?.previous
    ? (pageFromNext(signals.data.previous) ?? 1)
    : null;

  async function runLookback() {
    setError("");
    setResult("");
    try {
      const payload = await lookback.mutateAsync({ id: strategyId, days });
      setResult(
        `Looked back ${payload.days} days on @${payload.handle}: ${payload.tweets_seen} posts, ${payload.signals_created} new signals, ${payload.tweets_duplicate} already stored.`,
      );
      setPage(1);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not run lookback parse.",
      );
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-sm font-medium uppercase tracking-wide text-muted">
            Parsed signals
          </h2>
          <p className="mt-1 text-sm text-muted">
            Option trades parsed from this strategy. Recent posts in the
            live window are copied to assigned accounts — a pass (for
            example not enough cash) is recorded even when no trade is
            opened.
          </p>
        </div>
        {showLookback ? (
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">
              <span className="text-[11px] font-medium uppercase tracking-wide text-muted">
                Look back
              </span>
              <Select
                className="w-36"
                value={String(days)}
                onChange={(e) => setDays(Number(e.target.value))}
              >
                {LOOKBACK_DAYS.map((value) => (
                  <option key={value} value={value}>
                    {value} days
                  </option>
                ))}
              </Select>
            </label>
            <Button
              onClick={() => void runLookback()}
              loading={lookback.isPending}
            >
              Parse posts
            </Button>
          </div>
        ) : null}
      </div>
      {error ? <Banner tone="danger">{error}</Banner> : null}
      {result ? <Banner tone="success">{result}</Banner> : null}
      <Card>
        {signals.isLoading ? (
          <Spinner />
        ) : (signals.data?.results.length ?? 0) === 0 ? (
          <EmptyState
            title="No signals yet"
            body={
              showLookback
                ? "Run a lookback parse to pull option trades from X into signals."
                : "Signals appear here after posts are parsed."
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Contract</th>
                  <th className="px-4 py-3 font-medium">Entry</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Source</th>
                  <th className="px-4 py-3 font-medium">Parsed</th>
                </tr>
              </thead>
              <tbody>
                {signals.data?.results.map((signal) => (
                  <SignalRow key={signal.id} signal={signal} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {signals.data && signals.data.count > (signals.data.results.length || 0) ? (
        <div className="flex items-center justify-between text-sm text-muted">
          <span>{signals.data.count} signals</span>
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
    </section>
  );
}

function SignalRow({ signal }: { signal: Signal }) {
  return (
    <tr className="border-b border-border last:border-b-0">
      <td className="px-4 py-3">
        <OptionLabel
          ticker={signal.ticker}
          optionType={signal.option_type}
          strike={formatStrike(signal.strike)}
          expiration={formatDate(signal.expiration)}
        />
        <p className="text-xs text-muted">{signal.code}</p>
      </td>
      <td className="tabular px-4 py-3">{signal.suggested_entry_price}</td>
      <td className="px-4 py-3">
        <StatusPill tone={signal.status === "processed" ? "gain" : "neutral"}>
          {titleCase(signal.status)}
        </StatusPill>
      </td>
      <td className="px-4 py-3">
        {signal.tweet_id ? (
          <p className="text-xs text-muted">
            Tweet {signal.tweet_id}
            {signal.tweet_text ? (
              <span className="mt-1 block max-w-xs truncate">{signal.tweet_text}</span>
            ) : null}
          </p>
        ) : (
          <p className="text-xs text-muted">{signal.source || "—"}</p>
        )}
      </td>
      <td className="px-4 py-3 text-muted">
        {formatDateTime(signal.tweet_posted_at || signal.created_at)}
      </td>
    </tr>
  );
}
