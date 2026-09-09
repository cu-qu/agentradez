"use client";

import type { ReactNode } from "react";
import Link from "next/link";

import { useStrategiesQuery, useTiersQuery } from "@/lib/api/hooks";
import type { InvestmentTier, Strategy } from "@/lib/api/types";
import { titleCase } from "@/lib/format";
import { AppShell } from "@/components/app-shell";
import { RequireAuth } from "@/components/gates";
import { Button, Card, StatusPill } from "@/components/ui";

export default function GetStartedPage() {
  return (
    <RequireAuth>
      <AppShell>
        <GetStarted />
      </AppShell>
    </RequireAuth>
  );
}

function GetStarted() {
  const strategies = useStrategiesQuery(true);
  const tiers = useTiersQuery(true);
  const strategyRows = strategies.data ?? [];
  const tierRows = [...(tiers.data ?? [])].sort(
    (a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0),
  );

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-10">
      <div>
        <p className="text-xs uppercase tracking-[0.16em] text-muted">
          Welcome
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">
          Get started
        </h1>
        <p className="mt-2 text-sm text-muted">
          Four steps to turn on your agent. You can come back to this page
          anytime.
        </p>
      </div>

      <ol className="flex flex-col gap-6">
        <Step n={1} title="Connect a broker">
          <p>
            Link one brokerage account. Only one connection is active at a
            time. Credentials are never shown back to you.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <BrokerCard name="Robinhood">
              Choose Robinhood and stay on this page. Sign in in the new tab,
              then copy the localhost URL from that tab’s address bar and
              paste it here to finish. The page may look like it failed to
              load — that is expected. If you don’t have an Agentic account
              yet, Robinhood will ask you to open one on desktop.
            </BrokerCard>
            <BrokerCard name="Alpaca" comingSoon>
              Alpaca API keys are not wired up yet. Connect Robinhood for now;
              Alpaca will ship in a later release.
            </BrokerCard>
          </div>
        </Step>

        <Step n={2} title="Turn on an Agentic account">
          <p>
            The agent only trades in an Agentic account — the account that is
            allowed to receive copy trades.
          </p>
          <ul className="mt-3 flex flex-col gap-2 text-sm text-muted">
            <li>
              <strong className="font-medium text-foreground">Robinhood.</strong>{" "}
              Only Agentic accounts are listed — margin and other accounts
              stay hidden. Use the switch on one Agentic account to allow
              trades. Only that account receives copy trades.
            </li>
            <li>
              <strong className="font-medium text-foreground">Alpaca.</strong>{" "}
              Coming soon. When it ships, the account you connect is the one
              the agent uses — no extra toggle.
            </li>
          </ul>
        </Step>

        <Step n={3} title="Pick a strategy and a tier">
          <p>
            Apply both on the Agentic account you turned on. The agent uses
            this pair until you change it.
          </p>
          <p className="mt-3">
            A <strong className="font-medium text-foreground">strategy</strong>{" "}
            is how trades are found. An{" "}
            <strong className="font-medium text-foreground">investment tier</strong>{" "}
            is how those trades are sized and managed. Every signal has to
            clear both: the strategy produces the idea, then the tier decides
            whether to enter, how large to go, and when to take profit or
            get out.
          </p>

          <h3 className="mt-6 text-sm font-medium text-foreground">
            How they work together
          </h3>
          <ol className="mt-3 flex flex-col gap-2 text-sm text-muted">
            <li>
              <strong className="font-medium text-foreground">1. Signal.</strong>{" "}
              The strategy watches its source and turns a posted option idea
              (or a research catalyst) into a signal with a ticker, strike,
              and suggested price.
            </li>
            <li>
              <strong className="font-medium text-foreground">2. Gates.</strong>{" "}
              The tier skips the entry if live price has slipped too far, if
              too many positions are already open, or if today’s loss limit
              is hit.
            </li>
            <li>
              <strong className="font-medium text-foreground">3. Size.</strong>{" "}
              If it passes, the agent sizes from the tier’s risk per trade — a
              percent of equity in the Agentic account, not a copy of the
              source’s dollar amount. Options only trade in whole contracts.
              If that percent is below one contract, the agent still buys{" "}
              <strong className="font-medium text-foreground">1 contract</strong>{" "}
              when the premium fits in cash. If one contract costs more than
              buying power, it passes and records why. Size then scales with
              the same risk percent as the account grows.
            </li>
            <li>
              <strong className="font-medium text-foreground">4. Manage.</strong>{" "}
              Once filled, the tier runs the trade: scale out at take-profit
              levels, cut a loser at the hard stop, and flatten remaining
              size at the force-exit time or after the max hold.
            </li>
          </ol>
          <p className="mt-3">
            Turning the Agentic account off pauses new entries. Open trades
            are still managed with the same tier rules.
          </p>

          <h3 className="mt-6 text-sm font-medium text-foreground">
            Strategies
          </h3>
          <p className="mt-2">
            You pick one strategy per Agentic account. That is the only
            source the agent copies into that account.
          </p>
          {strategies.isLoading ? (
            <p className="mt-3 text-sm text-muted">Loading strategies…</p>
          ) : strategies.isError ? (
            <p className="mt-3 text-sm text-loss">
              Could not load strategies. Check Settings after you connect.
            </p>
          ) : strategyRows.length === 0 ? (
            <Card className="mt-3 p-4">
              <p className="text-sm text-muted">
                No strategies are available to you yet. Copy Trade watches an
                X account, reads option ideas from posts, and copies the ones
                that fit. Research / Breakthrough watches headlines for
                catalysts instead of copying another trader.
              </p>
            </Card>
          ) : (
            <div className="mt-3 flex flex-col gap-3">
              {strategyRows.map((strategy) => (
                <StrategyCard key={strategy.id} strategy={strategy} />
              ))}
            </div>
          )}

          <h3 className="mt-6 text-sm font-medium text-foreground">
            Investment tiers
          </h3>
          <p className="mt-2">
            Tiers do not change which signals the strategy watches. They
            cap how much of the Agentic account is at risk, how many trades
            can be open, and how the agent takes profit or cuts a loser.
            A $100 account can still take 1 contract when the premium is
            affordable; at $1,000, $10,000, and $100,000 the same risk
            percent buys more size. Pick the profile that matches how you
            want the agent to behave.
          </p>
          {tiers.isLoading ? (
            <p className="mt-3 text-sm text-muted">Loading investment tiers…</p>
          ) : tiers.isError ? (
            <p className="mt-3 text-sm text-loss">
              Could not load investment tiers. They will show in Settings
              after you connect.
            </p>
          ) : tierRows.length === 0 ? (
            <Card className="mt-3 p-4">
              <p className="text-sm text-muted">
                No investment tiers are published yet. When they are, each
                one will list its risk-per-trade, position limit, daily loss
                pause, hard stop, and exit times here.
              </p>
            </Card>
          ) : (
            <div className="mt-3 flex flex-col gap-3">
              {tierRows.map((tier) => (
                <TierSection key={tier.id} tier={tier} />
              ))}
            </div>
          )}
        </Step>

        <Step n={4} title="Let the agent run">
          <p>
            When a signal comes in, the agent either enters or records a
            pass — including not enough cash for one contract, slippage, or
            a daily loss pause. Those outcomes show on the account and in
            Activity. Open positions and P&L show on the dashboard.
          </p>
          <p className="mt-3 text-sm text-muted">
            You can pause new entries by turning the Agentic account off, or
            change strategy and tier later in Settings.
          </p>
        </Step>
      </ol>

      <div className="flex flex-wrap gap-3">
        <Link href="/settings">
          <Button>Connect a broker</Button>
        </Link>
        <Link href="/dashboard">
          <Button variant="secondary">Go to dashboard</Button>
        </Link>
      </div>
    </div>
  );
}

function StrategyCard({ strategy }: { strategy: Strategy }) {
  const typeLabel = strategyTypeLabel(strategy.strategy_type);
  const sourceLabel =
    strategy.strategy_type === "copy_trade"
      ? strategy.signal_source === "chat_group"
        ? "Chat group"
        : "X"
      : null;

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-medium text-foreground">{strategy.name}</h4>
        {typeLabel ? <StatusPill>{typeLabel}</StatusPill> : null}
        {sourceLabel ? <StatusPill>{sourceLabel}</StatusPill> : null}
      </div>
      <p className="mt-2 text-sm text-muted">
        {strategy.description || strategyTypeFallback(strategy.strategy_type)}
      </p>
      {strategy.source_handle ? (
        <p className="mt-2 text-xs text-muted">
          Watches @{strategy.source_handle}
        </p>
      ) : null}
    </Card>
  );
}

function TierSection({ tier }: { tier: InvestmentTier }) {
  const legs = takeProfitLegs(tier.take_profit_rules);

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="text-sm font-medium text-foreground">{tier.name}</h4>
        {tier.is_default ? <StatusPill tone="gain">Default</StatusPill> : null}
      </div>
      <p className="mt-2 text-sm text-muted">
        {tier.description ||
          "This tier sets size, open-position limits, and exit rules for every signal the strategy produces."}
      </p>
      <dl className="mt-4 grid gap-3 sm:grid-cols-2">
        <Rule
          label="Risk / trade"
          value={`${tier.max_risk_per_trade_pct}%`}
          hint="Target percent of Agentic-account equity at risk on one entry. If that is below one options contract, the agent still buys 1 contract when the premium is affordable, then scales with this percent as the account grows."
        />
        <Rule
          label="Max open"
          value={String(tier.max_open_positions)}
          hint="How many trades can be open at once. New signals are skipped after that."
        />
        <Rule
          label="Daily loss limit"
          value={`${tier.daily_loss_limit_pct}%`}
          hint="If today’s loss reaches this percent of equity, new entries pause. Open trades are still managed."
        />
        <Rule
          label="Hard stop"
          value={`${tier.hard_stop_pct}%`}
          hint="Close remaining size if the position is down this much."
        />
        <Rule
          label="Slippage"
          value={`${tier.max_entry_slippage_pct}%`}
          hint="Skip the entry if live price is this percent worse than the signal price."
        />
        <Rule
          label="Force exit"
          value={formatEtTime(tier.force_exit_time_et)}
          hint="On expiration day, flatten remaining size at this Eastern time."
        />
        <Rule
          label="Max hold"
          value={
            tier.max_hold_trading_days === 1
              ? "1 trading day"
              : `${tier.max_hold_trading_days} trading days`
          }
          hint="Close remaining size after this many trading days even if a target has not been hit."
        />
      </dl>
      <div className="mt-4 border-t border-border pt-3">
        <p className="text-[11px] font-medium uppercase tracking-wide text-muted">
          Take profit
        </p>
        {legs.length === 0 ? (
          <p className="mt-1 text-sm text-muted">
            No scale-out levels. Remaining size still follows the hard stop,
            force exit, and max hold.
          </p>
        ) : (
          <ul className="mt-2 flex flex-col gap-1.5 text-sm text-muted">
            {legs.map((leg, index) => (
              <li key={`${leg.gain_pct}-${index}`}>
                {formatTakeProfitLeg(leg, index)}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

function Rule({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium text-foreground">{value}</dd>
      <p className="mt-0.5 text-xs text-muted">{hint}</p>
    </div>
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
        <div className="mt-2 text-sm text-muted">{children}</div>
      </div>
    </li>
  );
}

function BrokerCard({
  name,
  comingSoon,
  children,
}: {
  name: string;
  comingSoon?: boolean;
  children: ReactNode;
}) {
  return (
    <Card className={comingSoon ? "p-4 opacity-70" : "p-4"}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-medium">{name}</h3>
        {comingSoon ? <StatusPill>Coming soon</StatusPill> : null}
      </div>
      <p className="mt-2 text-sm text-muted">{children}</p>
    </Card>
  );
}

function strategyTypeLabel(value: string | undefined): string | null {
  if (!value) return null;
  if (value === "copy_trade") return "Copy Trade";
  if (value === "research_breakthrough") return "Research / Breakthrough";
  return titleCase(value);
}

function strategyTypeFallback(value: string | undefined): string {
  if (value === "research_breakthrough") {
    return "Watches headlines and catalysts, then may propose an options trade. It does not copy another trader’s ticket.";
  }
  return "Watches a source, reads option ideas, and copies the ones that pass your investment tier into the Agentic account.";
}

type TakeProfitLeg = {
  pct_of_position?: string | number;
  gain_pct?: string | number;
  gain_pct_min?: string | number | null;
  gain_pct_max?: string | number | null;
  is_runner?: boolean;
};

function takeProfitLegs(rules: unknown): TakeProfitLeg[] {
  if (!Array.isArray(rules)) return [];
  return rules.filter(
    (leg): leg is TakeProfitLeg => Boolean(leg) && typeof leg === "object",
  );
}

function formatTakeProfitLeg(leg: TakeProfitLeg, index: number): string {
  const size = formatPct(leg.pct_of_position);
  const gain = formatPct(leg.gain_pct);
  const range =
    leg.gain_pct_min != null || leg.gain_pct_max != null
      ? ` (target ${formatPct(leg.gain_pct_min)}–${formatPct(leg.gain_pct_max)})`
      : "";
  if (leg.is_runner) {
    return size
      ? `Runner: leave ${size} of the position on after earlier scale-outs.`
      : "Runner: leftover size can keep running until the hard stop, force exit, or max hold.";
  }
  if (size && gain) {
    return `Scale out ${size} of the position once it is up ${gain}${range}.`;
  }
  if (gain) {
    return `Take profit when the position is up ${gain}${range}.`;
  }
  return `Take-profit level ${index + 1}.`;
}

function formatPct(value: string | number | null | undefined): string {
  if (value == null || value === "") return "";
  return `${value}%`;
}

function formatEtTime(value: string | null | undefined): string {
  if (!value) return "—";
  const [hours, minutes] = value.split(":").map(Number);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return value;
  const date = new Date();
  date.setHours(hours, minutes, 0, 0);
  return `${new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
  }).format(date)} ET`;
}
