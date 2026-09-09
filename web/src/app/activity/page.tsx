"use client";

import { useState } from "react";
import Link from "next/link";

import { useDecisionsQuery } from "@/lib/api/hooks";
import { pageFromNext } from "@/lib/api/types";
import { AppShell } from "@/components/app-shell";
import {
  DecisionContract,
  DecisionMeta,
  DecisionPills,
} from "@/components/decisions";
import { RequireAuth } from "@/components/gates";
import { Button, Card, EmptyState, Input, Select, Spinner } from "@/components/ui";

const OUTCOMES = [
  { value: "", label: "All outcomes" },
  { value: "acted", label: "Acted" },
  { value: "passed", label: "Passed" },
];

const ACTIONS = [
  { value: "", label: "All actions" },
  { value: "enter", label: "Enter" },
  { value: "skip", label: "Skip" },
  { value: "take_profit", label: "Take profit" },
  { value: "stop_loss", label: "Stop loss" },
  { value: "time_exit", label: "Time exit" },
  { value: "expiration_exit", label: "Expiration exit" },
  { value: "daily_pause", label: "Daily pause" },
];

export default function ActivityPage() {
  return (
    <RequireAuth>
      <AppShell>
        <ActivityList />
      </AppShell>
    </RequireAuth>
  );
}

function ActivityList() {
  const [outcome, setOutcome] = useState("");
  const [action, setAction] = useState("");
  const [ticker, setTicker] = useState("");
  const [tickerInput, setTickerInput] = useState("");
  const [page, setPage] = useState(1);
  const decisions = useDecisionsQuery(true, {
    outcome: outcome || undefined,
    action: action || undefined,
    ticker: ticker || undefined,
    page,
  });

  const nextPage = pageFromNext(decisions.data?.next);
  const prevPage = decisions.data?.previous
    ? (pageFromNext(decisions.data.previous) ?? 1)
    : null;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Activity</h1>
        <p className="mt-1 text-sm text-muted">
          Paper trail of how your strategy evaluated signals and managed
          positions — including why a trade was taken or passed under your
          investment tier.
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
          value={outcome}
          onChange={(e) => {
            setOutcome(e.target.value);
            setPage(1);
          }}
          className="w-44"
        >
          {OUTCOMES.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </Select>
        <Select
          value={action}
          onChange={(e) => {
            setAction(e.target.value);
            setPage(1);
          }}
          className="w-48"
        >
          {ACTIONS.map((opt) => (
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
        {decisions.isLoading ? (
          <Spinner />
        ) : (decisions.data?.results.length ?? 0) === 0 ? (
          <EmptyState
            title="No decisions yet"
            body="When a signal comes in, you will see why it was acted on or passed."
          />
        ) : (
          <ul className="divide-y divide-border">
            {decisions.data?.results.map((item) => (
              <li key={item.id}>
                <Link
                  href={`/activity/${item.id}`}
                  className="flex flex-col gap-2 px-4 py-4 hover:bg-surface-2 sm:flex-row sm:items-start sm:justify-between"
                >
                  <div className="min-w-0">
                    <DecisionContract item={item} />
                    <p className="mt-1 text-sm font-medium">{item.title}</p>
                    <p className="mt-1 line-clamp-2 text-sm text-muted">
                      {item.summary}
                    </p>
                    <div className="mt-2">
                      <DecisionMeta item={item} />
                    </div>
                  </div>
                  <div className="shrink-0 sm:pt-1">
                    <DecisionPills item={item} />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {decisions.data && decisions.data.count > (decisions.data.results.length || 0) ? (
        <div className="flex items-center justify-between text-sm text-muted">
          <span>{decisions.data.count} decisions</span>
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
