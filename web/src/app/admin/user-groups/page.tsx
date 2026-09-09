"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";

import { useAdminUserGroupsQuery } from "@/lib/api/hooks";
import { pageFromNext } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { Button, Card, EmptyState, Input, Select, Spinner, StatusPill } from "@/components/ui";

const ORDERING = [
  { value: "name", label: "Name" },
  { value: "-name", label: "Name (Z–A)" },
  { value: "-updated_at", label: "Recently updated" },
  { value: "updated_at", label: "Oldest updated" },
  { value: "-created_at", label: "Newest" },
  { value: "created_at", label: "Oldest" },
];

export default function AdminUserGroupsPage() {
  return <UserGroupList />;
}

function UserGroupList() {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [isActive, setIsActive] = useState("");
  const [ordering, setOrdering] = useState("name");
  const [page, setPage] = useState(1);
  const list = useAdminUserGroupsQuery(true, {
    search: search || undefined,
    is_active: isActive === "" ? undefined : isActive === "true",
    ordering,
    page,
  });

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
          <h1 className="text-2xl font-semibold tracking-tight">User groups</h1>
          <p className="mt-1 text-sm text-muted">
            Restrict strategies to a set of users.
          </p>
        </div>
        <Link href="/admin/user-groups/new">
          <Button>New group</Button>
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
            title="No user groups"
            body="Create a group to restrict a strategy to its members."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Members</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Updated</th>
                </tr>
              </thead>
              <tbody>
                {list.data?.results.map((row) => (
                  <tr
                    key={row.id}
                    className="border-b border-border last:border-b-0"
                  >
                    <td className="px-4 py-3">
                      <Link
                        href={`/admin/user-groups/${row.id}`}
                        className="hover:underline"
                      >
                        {row.name}
                      </Link>
                      <p className="text-xs text-muted">{row.slug}</p>
                    </td>
                    <td className="tabular px-4 py-3">{row.member_count}</td>
                    <td className="px-4 py-3">
                      <StatusPill tone={row.is_active ? "gain" : "neutral"}>
                        {row.is_active ? "Active" : "Inactive"}
                      </StatusPill>
                    </td>
                    <td className="px-4 py-3 text-muted">
                      {formatDateTime(row.updated_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {list.data && list.data.count > (list.data.results.length || 0) ? (
        <div className="flex items-center justify-between text-sm text-muted">
          <span>{list.data.count} groups</span>
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
