"use client";

import { usePathname } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { RequireAuth, RequireStaff } from "@/components/gates";
import { NavLink } from "@/components/notification-bell";

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <RequireAuth>
      <AppShell>
        <RequireStaff>
          <AdminFrame>{children}</AdminFrame>
        </RequireStaff>
      </AppShell>
    </RequireAuth>
  );
}

function AdminFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex flex-col gap-8">
      <nav className="flex items-center gap-5 border-b border-border pb-3">
        <NavLink
          href="/admin/strategies"
          active={pathname.startsWith("/admin/strategies")}
        >
          Strategies
        </NavLink>
        <NavLink
          href="/admin/user-groups"
          active={pathname.startsWith("/admin/user-groups")}
        >
          User groups
        </NavLink>
      </nav>
      {children}
    </div>
  );
}
