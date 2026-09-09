"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/lib/auth/provider";
import { NavLink } from "@/components/notification-bell";
import { Button, Wordmark } from "@/components/ui";

export function MarketingShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { status } = useAuth();
  const signedIn = status === "authenticated";

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-10 border-b border-border bg-background/95 backdrop-blur-sm">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <div className="flex items-center gap-8">
            <Link href="/">
              <Wordmark />
            </Link>
            <nav className="flex items-center gap-5">
              <NavLink href="/" active={pathname === "/"}>
                Home
              </NavLink>
              <NavLink
                href="/how-it-works"
                active={pathname.startsWith("/how-it-works")}
              >
                How it works
              </NavLink>
              <NavLink
                href="/strategies"
                active={pathname.startsWith("/strategies")}
              >
                Strategies
              </NavLink>
            </nav>
          </div>
          <div className="flex items-center gap-3">
            {signedIn ? (
              <Link href="/dashboard">
                <Button>Dashboard</Button>
              </Link>
            ) : (
              <>
                <Link
                  href="/login"
                  className="text-sm text-muted hover:text-foreground"
                >
                  Sign in
                </Link>
                <Link href="/register">
                  <Button>Create account</Button>
                </Link>
              </>
            )}
          </div>
        </div>
      </header>
      <main>{children}</main>
      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-8 text-sm text-muted sm:flex-row sm:items-center sm:justify-between">
          <p>Agentradez</p>
          <p>
            <Link href="/how-it-works" className="hover:text-foreground">
              How it works
            </Link>
            <span className="mx-2">·</span>
            <Link href="/strategies" className="hover:text-foreground">
              Strategies
            </Link>
            <span className="mx-2">·</span>
            <Link href="/terms" className="hover:text-foreground">
              Terms
            </Link>
          </p>
        </div>
      </footer>
    </div>
  );
}
