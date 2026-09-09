import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";

import { MarketingShell } from "@/components/marketing-shell";
import { Button, Card } from "@/components/ui";

export const metadata: Metadata = {
  title: "How it works",
  description:
    "How Agentradez copy-trades options: connect a broker, turn on an Agentic account, pick a strategy and a risk tier, then let the agent run.",
};

export default function HowItWorksPage() {
  return (
    <MarketingShell>
      <div className="mx-auto flex max-w-2xl flex-col gap-10 px-4 py-16">
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-muted">
            Agentradez
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">
            How it works
          </h1>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            Four steps to turn the agent on. After you create an account, the
            same guide lives inside the app so you can come back to it.
          </p>
        </div>

        <ol className="flex flex-col gap-8">
          <Step n={1} title="Create an Agentradez account">
            <p>
              Register with a username, email, and password. You will need to
              agree to the Terms. Email verification is optional for trading.
            </p>
          </Step>

          <Step n={2} title="Connect a broker">
            <p>
              Link one brokerage account. Only one connection is active at a
              time. Credentials are never shown back to you.
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <Card className="p-4">
                <h3 className="text-sm font-medium text-foreground">Robinhood</h3>
                <p className="mt-2 text-sm text-muted">
                  Sign in in a new tab, then paste the localhost URL from that
                  tab’s address bar to finish. If you don’t have an Agentic
                  account yet, Robinhood will ask you to open one on desktop.
                </p>
              </Card>
              <Card className="p-4 opacity-70">
                <h3 className="text-sm font-medium text-foreground">Alpaca</h3>
                <p className="mt-2 text-sm text-muted">
                  Coming soon. Connect Robinhood for now.
                </p>
              </Card>
            </div>
          </Step>

          <Step n={3} title="Turn on an Agentic account">
            <p>
              The agent only trades in a Robinhood Agentic account — the account
              allowed to receive copy trades. Margin and other accounts stay
              hidden. Use the switch on one Agentic account. Only that account
              receives trades.
            </p>
          </Step>

          <Step n={4} title="Pick a strategy and a tier">
            <p>
              A <strong className="font-medium text-foreground">strategy</strong>{" "}
              is how trades are found. An{" "}
              <strong className="font-medium text-foreground">investment tier</strong>{" "}
              is how those trades are sized and managed. Every signal has to
              clear both.
            </p>
            <ol className="mt-4 flex flex-col gap-2 text-sm text-muted">
              <li>
                <strong className="font-medium text-foreground">Signal.</strong>{" "}
                The strategy watches its source and turns an option idea into a
                ticker, strike, and suggested price.
              </li>
              <li>
                <strong className="font-medium text-foreground">Gates.</strong>{" "}
                The tier skips the entry if live price has slipped too far, too
                many positions are open, or today’s loss limit is hit.
              </li>
              <li>
                <strong className="font-medium text-foreground">Size.</strong>{" "}
                The agent sizes from a percent of equity in the Agentic account,
                not a copy of the source’s dollar amount. Options trade in whole
                contracts. If that percent is below one contract, it still buys
                1 contract when the premium fits.
              </li>
              <li>
                <strong className="font-medium text-foreground">Manage.</strong>{" "}
                Once filled, the tier scales out at take-profit levels, cuts a
                loser at the hard stop, and flattens remaining size at the
                force-exit time or after the max hold.
              </li>
            </ol>
            <p className="mt-4">
              Turning the Agentic account off pauses new entries. Open trades
              are still managed with the same tier rules.
            </p>
          </Step>
        </ol>

        <Card className="p-5">
          <h2 className="text-base font-medium tracking-tight">
            Then let the agent run
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            When a signal comes in, Agentradez either enters or records a pass.
            Those outcomes show in Activity. Open positions and P&amp;L show on
            the dashboard.
          </p>
        </Card>

        <div className="flex flex-wrap gap-3">
          <Link href="/register">
            <Button>Create account</Button>
          </Link>
          <Link href="/login">
            <Button variant="secondary">Sign in</Button>
          </Link>
        </div>
      </div>
    </MarketingShell>
  );
}

function Step({
  n,
  title,
  children,
}: {
  n: number;
  title: string;
  children: ReactNode;
}) {
  return (
    <li className="flex gap-4">
      <span
        aria-hidden
        className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-accent text-xs font-medium text-accent"
      >
        {n}
      </span>
      <div className="min-w-0 flex-1">
        <h2 className="text-base font-medium tracking-tight">{title}</h2>
        <div className="mt-2 text-sm leading-relaxed text-muted">{children}</div>
      </div>
    </li>
  );
}
