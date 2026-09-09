"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/lib/auth/provider";
import { HideAmountsToggle } from "@/components/hide-amounts-toggle";
import { NavLink, NotificationBell } from "@/components/notification-bell";
import { Wordmark } from "@/components/ui";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-10 border-b border-border bg-background/95 backdrop-blur-sm">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <div className="flex items-center gap-8">
            <Link href="/dashboard">
              <Wordmark />
            </Link>
            <nav className="flex items-center gap-5">
              <NavLink href="/dashboard" active={pathname === "/dashboard"}>
                Dashboard
              </NavLink>
              <NavLink
                href="/trades"
                active={pathname.startsWith("/trades")}
              >
                Trades
              </NavLink>
              <NavLink
                href="/activity"
                active={pathname.startsWith("/activity")}
              >
                Activity
              </NavLink>
              <NavLink
                href="/get-started"
                active={pathname.startsWith("/get-started")}
              >
                Get started
              </NavLink>
              {user?.is_staff ? (
                <NavLink
                  href="/admin/strategies"
                  active={pathname.startsWith("/admin")}
                >
                  Admin
                </NavLink>
              ) : null}
              <NavLink href="/settings" active={pathname.startsWith("/settings") || pathname.startsWith("/accounts")}>
                Settings
              </NavLink>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <HideAmountsToggle />
            <NotificationBell />
            <span className="hidden text-sm text-muted sm:inline">
              {user?.username}
            </span>
            <button
              type="button"
              onClick={logout}
              className="text-sm text-muted hover:text-foreground"
            >
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
    </div>
  );
}

export function AuthFrame({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-full items-center justify-center px-4 py-16">
      <div className="w-full max-w-md">
        <div className="mb-8">
          <Link href="/">
            <Wordmark compact />
          </Link>
          <h1 className="mt-6 text-2xl font-semibold tracking-tight">{title}</h1>
          {subtitle ? (
            <p className="mt-2 text-sm text-muted">{subtitle}</p>
          ) : null}
        </div>
        {children}
      </div>
    </div>
  );
}

