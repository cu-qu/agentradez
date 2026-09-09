"use client";

import Link from "next/link";

import { AdminStrategyForm } from "@/components/admin-strategy-form";

export default function NewAdminStrategyPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          href="/admin/strategies"
          className="text-sm text-muted hover:text-foreground"
        >
          Strategies
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">
          New strategy
        </h1>
        <p className="mt-1 text-sm text-muted">
          Choose a type from the catalog, then fill in the fields it needs.
        </p>
      </div>
      <AdminStrategyForm />
    </div>
  );
}
