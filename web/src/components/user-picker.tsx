"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import {
  useAdminUserGroupsQuery,
  useAdminUsersQuery,
} from "@/lib/api/hooks";
import type { AccessUser, UserGroupBrief } from "@/lib/api/types";
import { Input } from "@/components/ui";

function useDebounced(value: string, ms = 250) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

function Chip({
  label,
  hint,
  onRemove,
}: {
  label: string;
  hint?: string;
  onRemove: () => void;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-border bg-surface-2 py-0.5 pl-2 pr-1 text-xs">
      <span>
        {label}
        {hint ? <span className="text-muted"> · {hint}</span> : null}
      </span>
      <button
        type="button"
        onClick={onRemove}
        className="flex h-4 w-4 items-center justify-center rounded-full text-muted hover:text-foreground"
        aria-label={`Remove ${label}`}
      >
        ×
      </button>
    </span>
  );
}

export function UserPicker({
  selected,
  onChange,
  error,
}: {
  selected: AccessUser[];
  onChange: (users: AccessUser[]) => void;
  error?: string;
}) {
  const [search, setSearch] = useState("");
  const debounced = useDebounced(search.trim());
  const query = useAdminUsersQuery(true, {
    search: debounced || undefined,
  });
  const selectedIds = useMemo(
    () => new Set(selected.map((user) => user.id)),
    [selected],
  );
  const results = (query.data?.results ?? []).filter(
    (user) => !selectedIds.has(user.id),
  );

  function add(user: AccessUser) {
    onChange([...selected, user]);
    setSearch("");
  }

  return (
    <div className="flex flex-col gap-2">
      {selected.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {selected.map((user) => (
            <Chip
              key={user.id}
              label={user.username}
              hint={user.email}
              onRemove={() =>
                onChange(selected.filter((item) => item.id !== user.id))
              }
            />
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted">No users selected.</p>
      )}
      <Input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search users"
      />
      {search.trim() || results.length > 0 ? (
        <div className="max-h-48 overflow-y-auto rounded-md border border-border bg-background">
          {query.isFetching ? (
            <p className="px-3 py-2 text-xs text-muted">Searching…</p>
          ) : results.length === 0 ? (
            <p className="px-3 py-2 text-xs text-muted">No matching users.</p>
          ) : (
            results.map((user) => (
              <button
                key={user.id}
                type="button"
                onClick={() => add(user)}
                className="flex w-full flex-col px-3 py-2 text-left text-sm hover:bg-surface-2"
              >
                <span>{user.username}</span>
                <span className="text-xs text-muted">{user.email}</span>
              </button>
            ))
          )}
        </div>
      ) : null}
      {error ? <span className="text-xs text-loss">{error}</span> : null}
    </div>
  );
}

export function GroupPicker({
  selected,
  onChange,
  error,
}: {
  selected: UserGroupBrief[];
  onChange: (groups: UserGroupBrief[]) => void;
  error?: string;
}) {
  const [search, setSearch] = useState("");
  const debounced = useDebounced(search.trim());
  const query = useAdminUserGroupsQuery(true, {
    search: debounced || undefined,
    is_active: true,
    ordering: "name",
  });
  const selectedIds = useMemo(
    () => new Set(selected.map((group) => group.id)),
    [selected],
  );
  const results = (query.data?.results ?? []).filter(
    (group) => !selectedIds.has(group.id),
  );

  function add(group: {
    id: number;
    slug?: string;
    name: string;
    is_active?: boolean;
  }) {
    onChange([
      ...selected,
      {
        id: group.id,
        slug: group.slug ?? "",
        name: group.name,
        is_active: group.is_active,
      },
    ]);
    setSearch("");
  }

  return (
    <div className="flex flex-col gap-2">
      {selected.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {selected.map((group) => (
            <Chip
              key={group.id}
              label={group.name}
              hint={group.is_active === false ? "inactive" : group.slug}
              onRemove={() =>
                onChange(selected.filter((item) => item.id !== group.id))
              }
            />
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted">No groups selected.</p>
      )}
      <Input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search groups"
      />
      {search.trim() || results.length > 0 ? (
        <div className="max-h-48 overflow-y-auto rounded-md border border-border bg-background">
          {query.isFetching ? (
            <p className="px-3 py-2 text-xs text-muted">Searching…</p>
          ) : results.length === 0 ? (
            <p className="px-3 py-2 text-xs text-muted">No matching groups.</p>
          ) : (
            results.map((group) => (
              <button
                key={group.id}
                type="button"
                onClick={() => add(group)}
                className="flex w-full flex-col px-3 py-2 text-left text-sm hover:bg-surface-2"
              >
                <span>{group.name}</span>
                <span className="text-xs text-muted">{group.slug}</span>
              </button>
            ))
          )}
        </div>
      ) : null}
      <p className="text-xs text-muted">
        Need a group?{" "}
        <Link href="/admin/user-groups/new" className="hover:text-foreground">
          Create one
        </Link>
        .
      </p>
      {error ? <span className="text-xs text-loss">{error}</span> : null}
    </div>
  );
}
