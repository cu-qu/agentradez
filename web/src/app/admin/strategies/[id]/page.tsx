"use client";

import { use } from "react";
import Link from "next/link";

import { useAdminStrategyQuery } from "@/lib/api/hooks";
import { AdminStrategyForm } from "@/components/admin-strategy-form";
import { StrategySignalsPanel } from "@/components/strategy-signals";
import { Banner, Spinner, VisibilityBadge } from "@/components/ui";

export default function EditAdminStrategyPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const strategyId = Number(id);

  return <EditStrategy strategyId={strategyId} />;
}

function EditStrategy({ strategyId }: { strategyId: number }) {
  const query = useAdminStrategyQuery(true, strategyId);

  if (query.isLoading) return <Spinner />;
  if (!query.data) {
    return <Banner tone="danger">Strategy not found.</Banner>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          href="/admin/strategies"
          className="text-sm text-muted hover:text-foreground"
        >
          Strategies
        </Link>
        <h1 className="mt-2 flex flex-wrap items-center gap-2 text-2xl font-semibold tracking-tight">
          {query.data.name}
          <VisibilityBadge visibility={query.data.visibility} />
        </h1>
        <p className="mt-1 text-sm text-muted">
          {query.data.slug}
          {query.data.assigned_user_count
            ? ` · ${query.data.assigned_user_count} assigned`
            : ""}
        </p>
      </div>
      <AdminStrategyForm strategy={query.data} />
      <StrategySignalsPanel
        strategyId={strategyId}
        showLookback={Boolean(query.data.x_source)}
      />
    </div>
  );
}
