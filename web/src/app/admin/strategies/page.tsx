"use client";

import { FormEvent, Fragment, useState } from "react";
import Link from "next/link";

import {
  useAdminStrategiesQuery,
  useAdminStrategyTypesQuery,
} from "@/lib/api/hooks";
import { pageFromNext } from "@/lib/api/types";
import { formatDateTime, titleCase } from "@/lib/format";
import { StrategySignalsPanel } from "@/components/strategy-signals";
import { Button, Card, EmptyState, Input, Select, Spinner, StatusPill, VisibilityBadge } from "@/components/ui";

const ORDERING = [
  { value: "name", label: "Name" },
  { value: "-name", label: "Name (Z–A)" },
  { value: "-updated_at", label: "Recently updated" },
  { value: "updated_at", label: "Oldest updated" },
  { value: "-created_at", label: "Newest" },
  { value: "created_at", label: "Oldest" },
];

export default function AdminStrategiesPage() {
  return <StrategyList />;
}

function StrategyList() {
  const types = useAdminStrategyTypesQuery(true);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [isActive, setIsActive] = useState("");
  const [strategyType, setStrategyType] = useState("");
  const [visibility, setVisibility] = useState("");
  const [ordering, setOrdering] = useState("name");
  const [page, setPage] = useState(1);
  const list = useAdminStrategiesQuery(true, {
    search: search || undefined,
    is_active: isActive === "" ? undefined : isActive === "true",
    strategy_type: strategyType || undefined,
    visibility: visibility || undefined,
    ordering,
    page,
  });

  const typeLabel = (value: string) =>
    types.data?.find((type) => type.value === value)?.label ?? titleCase(value);

  const nextPage = pageFromNext(list.data?.next);
  const prevPage = list.data?.previous
    ? (pageFromNext(list.data.previous) ?? 1)
    : null;

  function onFilter(event: FormEvent) {
    event.preventDefault();
    setSearch(searchInput.trim());
    setPage(1);
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Strategies</h1>
          <p className="mt-1 text-sm text-muted">
            Create and configure strategies shown to users.
          </p>
        </div>
        <Link href="/admin/strategies/new">
          <Button>New strategy</Button>
        </Link>
      </div>

      <form className="flex flex-wrap gap-3" onSubmit={onFilter}>
        <Input
          placeholder="Search"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="w-48"
        />
        <Select
          value={isActive}
          onChange={(e) => {
            setIsActive(e.target.value);
            setPage(1);
          }}
          className="w-40"
        >
          <option value="">All statuses</option>
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </Select>
        <Select
          value={strategyType}
          onChange={(e) => {
            setStrategyType(e.target.value);
            setPage(1);
          }}
          className="w-48"
        >
          <option value="">All types</option>
          {(types.data ?? []).map((type) => (
            <option key={type.value} value={type.value}>
              {type.label}
            </option>
          ))}
        </Select>
        <Select
          value={visibility}
          onChange={(e) => {
            setVisibility(e.target.value);
            setPage(1);
          }}
          className="w-44"
        >
          <option value="">All visibility</option>
          <option value="public">Public</option>
          <option value="restricted">Restricted</option>
        </Select>
        <Select
          value={ordering}
          onChange={(e) => {
            setOrdering(e.target.value);
            setPage(1);
          }}
          className="w-48"
        >
          {ORDERING.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </Select>
        <Button type="submit" variant="secondary">
          Filter
        </Button>
      </form>

      <Card>
        {list.isLoading ? (
          <Spinner />
        ) : (list.data?.results.length ?? 0) === 0 ? (
          <EmptyState
            title="No strategies"
            body="Create a strategy to show it on the user picker."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-left text-sm">
              <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 font-medium">Visibility</th>
                  <th className="px-4 py-3 font-medium">Source</th>
                  <th className="px-4 py-3 font-medium">Users</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Updated</th>
                </tr>
              </thead>
              <tbody>
                {list.data?.results.map((row) => (
                  <Fragment key={row.id}>
                    <tr className="border-b border-border">
                      <td className="px-4 py-3">
                        <Link
                          href={`/admin/strategies/${row.id}`}
                          className="hover:underline"
                        >
                          {row.name}
                        </Link>
                        <p className="text-xs text-muted">{row.slug}</p>
                      </td>
                      <td className="px-4 py-3">{typeLabel(row.strategy_type)}</td>
                      <td className="px-4 py-3">
                        <VisibilityBadge visibility={row.visibility} />
                      </td>
                      <td className="px-4 py-3 text-muted">
                        {row.strategy_type === "copy_trade" ? (
                          <>
                            {row.signal_source === "chat_group" ? "Chat group" : "X"}
                            {row.x_source ? (
                              <>
                                {" "}
                                · @{row.x_source.handle}
                                <p className="text-xs">
                                  every {row.x_source.poll_interval_seconds ?? 60}s
                                </p>
                              </>
                            ) : null}
                          </>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="tabular px-4 py-3">
                        {row.assigned_user_count}
                      </td>
                      <td className="px-4 py-3">
                        <StatusPill tone={row.is_active ? "gain" : "neutral"}>
                          {row.is_active ? "Active" : "Inactive"}
                        </StatusPill>
                      </td>
                      <td className="px-4 py-3 text-muted">
                        {formatDateTime(row.updated_at)}
                      </td>
                    </tr>
                    <tr className="border-b border-border last:border-b-0">
                      <td colSpan={7} className="px-4 pb-6 pt-1">
                        <StrategySignalsPanel
                          strategyId={row.id}
                          showLookback={Boolean(row.x_source)}
                        />
                      </td>
                    </tr>
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {list.data && list.data.count > (list.data.results.length || 0) ? (
        <div className="flex items-center justify-between text-sm text-muted">
          <span>{list.data.count} strategies</span>
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
