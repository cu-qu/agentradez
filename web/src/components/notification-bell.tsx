"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotificationsQuery,
} from "@/lib/api/hooks";
import type { Notification } from "@/lib/api/types";
import { formatDateTime, titleCase } from "@/lib/format";

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const unread = useNotificationsQuery(true, true);
  const all = useNotificationsQuery(open, undefined);
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();
  const items = (open ? all.data?.results : unread.data?.results) ?? [];
  const unreadCount = unread.data?.count ?? 0;

  useEffect(() => {
    function onDoc(event: MouseEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative flex h-9 w-9 items-center justify-center rounded-md border border-border text-muted hover:text-foreground"
        aria-label="Notifications"
      >
        <BellIcon />
        {unreadCount > 0 ? (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] text-white">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="absolute right-0 z-20 mt-2 w-[22rem] overflow-hidden rounded-lg border border-border bg-surface">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <span className="text-xs font-medium uppercase tracking-wide text-muted">
              Activity
            </span>
            <div className="flex items-center gap-3">
              {unreadCount > 0 ? (
                <button
                  type="button"
                  onClick={() => markAllRead.mutate()}
                  disabled={markAllRead.isPending}
                  className="text-xs text-muted hover:text-foreground disabled:opacity-50"
                >
                  Clear all
                </button>
              ) : null}
              <Link
                href="/activity"
                onClick={() => setOpen(false)}
                className="text-xs text-muted hover:text-foreground"
              >
                View all
              </Link>
            </div>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {items.length === 0 ? (
              <p className="px-3 py-8 text-center text-sm text-muted">
                No notifications
              </p>
            ) : (
              items.map((item) => (
                <NotificationRow
                  key={item.id}
                  item={item}
                  onOpen={() => {
                    if (!item.is_read) markRead.mutate(item.id);
                    setOpen(false);
                  }}
                />
              ))
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function NotificationRow({
  item,
  onOpen,
}: {
  item: Notification;
  onOpen: () => void;
}) {
  const router = useRouter();
  return (
    <button
      type="button"
      onClick={() => {
        onOpen();
        if (item.decision_id) router.push(`/activity/${item.decision_id}`);
        else if (item.trade_id) router.push(`/trades/${item.trade_id}`);
        else router.push("/activity");
      }}
      className="flex w-full flex-col gap-0.5 border-b border-border px-3 py-2.5 text-left last:border-b-0 hover:bg-surface-2"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">{item.title}</span>
        {item.is_read ? null : (
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
        )}
      </div>
      {item.body ? (
        <span className="text-xs text-muted">{item.body}</span>
      ) : null}
      <span className="text-[11px] text-muted">
        {titleCase(item.kind)} · {formatDateTime(item.created_at)}
      </span>
    </button>
  );
}

function BellIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M8 2.5a3.5 3.5 0 0 0-3.5 3.5v1.2c0 .5-.15.98-.44 1.38L3.2 10.1A.75.75 0 0 0 3.8 11.3h8.4a.75.75 0 0 0 .6-1.2l-.86-1.52A2.4 2.4 0 0 1 11.5 7.2V6A3.5 3.5 0 0 0 8 2.5Z"
        stroke="currentColor"
        strokeWidth="1.2"
      />
      <path
        d="M6.4 12.2a1.6 1.6 0 0 0 3.2 0"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function NavLink({
  href,
  children,
  active,
}: {
  href: string;
  children: React.ReactNode;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={
        active
          ? "text-sm font-medium text-foreground"
          : "text-sm text-muted hover:text-foreground"
      }
    >
      {children}
    </Link>
  );
}
