"use client";

import { use } from "react";
import Link from "next/link";

import { useDecisionQuery } from "@/lib/api/hooks";
import type { Decision } from "@/lib/api/types";
import { AppShell } from "@/components/app-shell";
import {
  DecisionContract,
  DecisionMeta,
  DecisionPills,
  contextFacts,
} from "@/components/decisions";
import { RequireAuth } from "@/components/gates";
import { Banner, Card, Spinner } from "@/components/ui";

export default function ActivityDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const decisionId = Number(id);

  return (
    <RequireAuth>
      <AppShell>
        <ActivityDetail decisionId={decisionId} />
      </AppShell>
    </RequireAuth>
  );
}

function ActivityDetail({ decisionId }: { decisionId: number }) {
  const query = useDecisionQuery(true, decisionId);

  if (query.isLoading) return <Spinner />;
  if (!query.data) {
    return <Banner tone="danger">Decision not found.</Banner>;
  }

  const item = query.data;
  const facts = contextFacts(item.context);

  return (
    <div className="flex flex-col gap-8">
      <div>
        <Link href="/activity" className="text-sm text-muted hover:text-foreground">
          Activity
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">
          <DecisionContract item={item} />
        </h1>
        <div className="mt-3">
          <DecisionPills item={item} />
        </div>
        <div className="mt-2">
          <DecisionMeta item={item} />
        </div>
      </div>

      <Card>
        <div className="px-4 py-4">
          <p className="text-sm font-medium">{item.title}</p>
          <p className="mt-2 text-sm leading-6 text-muted">{item.summary}</p>
        </div>
      </Card>

      {facts.length > 0 ? (
        <section>
          <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">
            Why this decision
          </h2>
          <Card>
            <dl className="divide-y divide-border">
              {facts.map((fact) => (
                <div
                  key={fact.key}
                  className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:justify-between sm:gap-8"
                >
                  <dt className="text-sm text-muted">{fact.label}</dt>
                  <dd className="text-sm sm:text-right">
                    {fact.key === "source_excerpt" ? (
                      <span className="whitespace-pre-wrap">{fact.value}</span>
                    ) : (
                      <span className="tabular">{fact.value}</span>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          </Card>
        </section>
      ) : null}

      <RelatedLinks item={item} />
    </div>
  );
}

function RelatedLinks({ item }: { item: Decision }) {
  const links = [
    item.trade_id ? { href: `/trades/${item.trade_id}`, label: "View trade" } : null,
  ].filter((row): row is { href: string; label: string } => Boolean(row));
  if (links.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-3 text-sm">
      {links.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className="text-muted hover:text-foreground"
        >
          {link.label}
        </Link>
      ))}
    </div>
  );
}
