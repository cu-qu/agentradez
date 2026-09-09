import type { Metadata } from "next";
import Link from "next/link";

import { MarketingShell } from "@/components/marketing-shell";
import { Button, Card } from "@/components/ui";
import { PublicStrategies } from "./public-strategies";

export const metadata: Metadata = {
  title: "Strategies",
  description:
    "What Agentradez strategies are, how they find trades, and which public strategies you can pick.",
};

export default function StrategiesPage() {
  return (
    <MarketingShell>
      <div className="mx-auto flex max-w-2xl flex-col gap-10 px-4 py-16">
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-muted">
            Agentradez
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">
            Strategies
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            A strategy is how trades are found. You pick one per Agentic
            account. An investment tier then sizes and manages those trades.
            Every signal has to clear both.
          </p>
        </div>

        <section className="flex flex-col gap-4">
          <h2 className="text-base font-medium tracking-tight">
            How a strategy works
          </h2>
          <ol className="flex flex-col gap-3 text-sm leading-relaxed text-muted">
            <li>
              <strong className="font-medium text-foreground">Signal.</strong>{" "}
              The strategy watches its source and turns an option idea into a
              ticker, strike, and suggested price.
            </li>
            <li>
              <strong className="font-medium text-foreground">Gates.</strong>{" "}
              Your investment tier skips the entry if live price has slipped
              too far, too many positions are open, or today’s loss limit is
              hit.
            </li>
            <li>
              <strong className="font-medium text-foreground">Size.</strong>{" "}
              The agent sizes from a percent of equity in the Agentic account,
              not a copy of the source’s dollar amount. Options trade in whole
              contracts.
            </li>
            <li>
              <strong className="font-medium text-foreground">Manage.</strong>{" "}
              Once filled, the tier scales out at take-profit levels, cuts a
              loser at the hard stop, and flattens remaining size at the
              force-exit time or after the max hold.
            </li>
          </ol>
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="text-base font-medium tracking-tight">
            Types you can choose
          </h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <Card className="p-4">
              <h3 className="text-sm font-medium text-foreground">Copy Trade</h3>
              <p className="mt-2 text-sm text-muted">
                Watches a public source, usually an X account, reads option
                ideas from posts, and copies the ones that pass your
                investment tier into the Agentic account.
              </p>
            </Card>
            <Card className="p-4">
              <h3 className="text-sm font-medium text-foreground">
                Research / Breakthrough
              </h3>
              <p className="mt-2 text-sm text-muted">
                Watches headlines and catalysts, then may propose an options
                trade. It does not copy another trader’s ticket.
              </p>
            </Card>
          </div>
        </section>

        <section className="flex flex-col gap-4">
          <div>
            <h2 className="text-base font-medium tracking-tight">
              Public strategies
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              These are the active public strategies anyone with an account
              can pick. Restricted strategies only show in the app if you
              have been granted access.
            </p>
          </div>
          <PublicStrategies />
        </section>

        <div className="flex flex-wrap gap-3">
          <Link href="/register">
            <Button>Create account</Button>
          </Link>
          <Link href="/how-it-works">
            <Button variant="secondary">How it works</Button>
          </Link>
        </div>
      </div>
    </MarketingShell>
  );
}
