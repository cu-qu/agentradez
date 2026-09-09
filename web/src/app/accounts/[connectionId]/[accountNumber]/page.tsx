"use client";

import type { ReactNode } from "react";
import { use, useState } from "react";
import Link from "next/link";

import { ApiError } from "@/lib/api/client";
import {
  useBrokerAccountDetailQuery,
  useDecisionsQuery,
  useNotificationsQuery,
  usePositionsQuery,
  useSelectBrokerAccount,
  useTradesQuery,
} from "@/lib/api/hooks";
import type { InvestmentTier } from "@/lib/api/types";
import { formatDate, formatDateTime, formatStrike, titleCase } from "@/lib/format";
import { useHiddenAccountBalances } from "@/lib/privacy";
import { AccountAssignmentForm } from "@/components/accounts";
import { AppShell } from "@/components/app-shell";
import {
  DecisionContract,
  DecisionMeta,
  DecisionPills,
} from "@/components/decisions";
import { RequireAuth } from "@/components/gates";
import { HideAccountBalanceToggle } from "@/components/hide-amounts-toggle";
import { OptionLabel, PnlValue, UsdValue } from "@/components/pnl";
import {
  Banner,
  Card,
  EmptyState,
  Spinner,
  StatusPill,
  Switch,
  VisibilityBadge,
} from "@/components/ui";

export default function AccountDetailPage({
  params,
}: {
  params: Promise<{ connectionId: string; accountNumber: string }>;
}) {
  const { connectionId, accountNumber } = use(params);

  return (
    <RequireAuth>
      <AppShell>
        <AccountDetail
          connectionId={Number(connectionId)}
          accountNumber={decodeURIComponent(accountNumber)}
        />
      </AppShell>
    </RequireAuth>
  );
}

function AccountDetail({
  connectionId,
  accountNumber,
}: {
  connectionId: number;
  accountNumber: string;
}) {
  const detail = useBrokerAccountDetailQuery(connectionId, accountNumber);
  const positions = usePositionsQuery(detail.isSuccess, accountNumber);
  const trades = useTradesQuery(detail.isSuccess, {
    broker_account_id: accountNumber,
  });
  const updates = useNotificationsQuery(detail.isSuccess, undefined, accountNumber);
  const decisions = useDecisionsQuery(detail.isSuccess, {
    broker_account_id: accountNumber,
  });
  const select = useSelectBrokerAccount();
  const { isHidden } = useHiddenAccountBalances();
  const [toggleError, setToggleError] = useState("");

  if (detail.isLoading) return <Spinner />;
  if (detail.isError || !detail.data) {
    return (
      <div className="flex flex-col gap-4">
        <Link href="/settings" className="text-sm text-muted hover:text-foreground">
          Accounts
        </Link>
        <Banner tone="danger">
          {detail.error instanceof ApiError
            ? detail.error.message
            : "Could not load this account."}
        </Banner>
      </div>
    );
  }

  const { connection, account, trading_enabled, assignment, performance } =
    detail.data;
  const label =
    account.nickname ||
    (account.agentic_allowed ? "Agentic" : account.type || "Account");
  const hideBalance = isHidden(connection.id, account.account_number);

  async function setTrading(enabled: boolean) {
    setToggleError("");
    try {
      await select.mutateAsync({
        id: connection.id,
        account_number: enabled ? account.account_number : "",
      });
    } catch (err) {
      setToggleError(
        err instanceof ApiError ? err.message : "Could not update trading.",
      );
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <Link href="/settings" className="text-sm text-muted hover:text-foreground">
          Accounts
        </Link>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{label}</h1>
            <p className="mt-1 text-sm text-muted">
              {account.account_number}
              {account.type ? ` · ${account.type}` : ""}
              {account.state ? ` · ${account.state}` : ""}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <StatusPill tone={connection.status === "connected" ? "gain" : "warn"}>
                {connection.status}
              </StatusPill>
              {account.agentic_allowed ? (
                <StatusPill tone="gain">Agentic</StatusPill>
              ) : (
                <StatusPill>Read only</StatusPill>
              )}
              {trading_enabled ? (
                <StatusPill tone="gain">Trading on</StatusPill>
              ) : (
                <StatusPill tone="warn">Trading off</StatusPill>
              )}
              {connection.is_paper ? <StatusPill>Paper</StatusPill> : null}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <HideAccountBalanceToggle
              connectionId={connection.id}
              accountNumber={account.account_number}
              label={label}
            />
            {connection.broker === "robinhood" && account.agentic_allowed ? (
              <>
                <span className="text-sm text-muted">Allow trades</span>
                <Switch
                  label="Allow trades on this account"
                  checked={trading_enabled}
                  disabled={select.isPending}
                  onCheckedChange={(checked) => void setTrading(checked)}
                />
              </>
            ) : null}
          </div>
        </div>
        {toggleError ? <p className="mt-2 text-xs text-loss">{toggleError}</p> : null}
      </div>

      <div className="grid gap-3 sm:grid-cols-4">
        <Metric
          label="Equity"
          value={
            <UsdValue
              value={account.equity ?? connection.last_equity}
              hide={hideBalance}
            />
          }
        />
        <Metric
          label="Cash"
          value={
            account.cash ? (
              <UsdValue value={account.cash} hide={hideBalance} />
            ) : (
              "—"
            )
          }
        />
        <Metric
          label="Buying power"
          value={
            account.buying_power ? (
              <UsdValue value={account.buying_power} hide={hideBalance} />
            ) : (
              "—"
            )
          }
        />
        <div className="rounded-lg border border-border bg-surface px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-muted">
            Account P&L
          </p>
          <PnlValue
            value={performance.lifetime_total_pnl}
            className="mt-1 block text-lg font-medium"
          />
        </div>
      </div>

      <section className="grid gap-3 sm:grid-cols-4">
        <Stat
          label="Realized"
          value={<PnlValue value={performance.lifetime_realized_pnl} />}
        />
        <Stat
          label="Unrealized"
          value={<PnlValue value={performance.lifetime_unrealized_pnl} />}
        />
        <Stat
          label="Today"
          value={<PnlValue value={performance.daily_realized_pnl} />}
        />
        <Stat
          label="This week"
          value={<PnlValue value={performance.weekly_realized_pnl} />}
        />
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium uppercase tracking-wide text-muted">
          Strategy and tier
        </h2>
        <Card className="p-5">
          {assignment ? (
            <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">{assignment.strategy.name}</span>
              <VisibilityBadge visibility={assignment.strategy.visibility} />
              <StatusPill>{assignment.investment_tier.name}</StatusPill>
            </div>
          ) : (
            <p className="mb-4 text-sm text-muted">
              No strategy is assigned to this account yet.
            </p>
          )}
          <AccountAssignmentForm accountNumber={account.account_number} />
        </Card>
        {assignment ? (
          <div className="grid gap-3 lg:grid-cols-2">
            <Card className="p-5">
              <h3 className="text-sm font-medium">Strategy</h3>
              <p className="mt-2 text-sm text-muted">
                {assignment.strategy.description || "No description."}
              </p>
              <p className="mt-3 text-xs text-muted">
                {titleCase(assignment.strategy.strategy_type ?? "")}
                {assignment.strategy.strategy_type === "copy_trade"
                  ? ` · ${assignment.strategy.signal_source === "chat_group" ? "Chat group" : "X"}`
                  : ""}
                {assignment.strategy.source_handle
                  ? ` · @${assignment.strategy.source_handle}`
                  : ""}
              </p>
            </Card>
            <Card className="p-5">
              <h3 className="text-sm font-medium">
                {assignment.investment_tier.name} rules
              </h3>
              <p className="mt-2 text-sm text-muted">
                {assignment.investment_tier.description ||
                  "Risk per trade is a percent of equity. Below one options contract, the agent still buys 1 contract when the premium fits in cash, then scales with that percent as the account grows."}
              </p>
              <TierRules tier={assignment.investment_tier} />
            </Card>
          </div>
        ) : null}
      </section>

      <section>
        <div className="mb-3 flex items-end justify-between">
          <h2 className="text-sm font-medium uppercase tracking-wide text-muted">
            Open positions
          </h2>
          <p className="text-xs text-muted">
            {performance.open_positions} open · {performance.closed_trades} closed
          </p>
        </div>
        <Card>
          {positions.isLoading ? (
            <Spinner />
          ) : (positions.data?.length ?? 0) === 0 ? (
            <EmptyState
              title="No open positions"
              body="Filled copy trades for this account will show here."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th className="px-4 py-3 font-medium">Contract</th>
                    <th className="px-4 py-3 font-medium">Qty</th>
                    <th className="px-4 py-3 font-medium">Entry</th>
                    <th className="px-4 py-3 font-medium">Mark</th>
                    <th className="px-4 py-3 font-medium">Unrealized</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.data?.map((pos) => (
                    <tr
                      key={pos.id}
                      className="border-b border-border last:border-b-0"
                    >
                      <td className="px-4 py-3">
                        <Link
                          href={`/trades/${pos.trade_id}`}
                          className="hover:underline"
                        >
                          <OptionLabel
                            ticker={pos.ticker}
                            optionType={pos.option_type}
                            strike={formatStrike(pos.strike)}
                            expiration={formatDate(pos.expiration)}
                          />
                        </Link>
                      </td>
                      <td className="tabular px-4 py-3">{pos.quantity}</td>
                      <td className="tabular px-4 py-3">
                        {pos.average_entry_price}
                      </td>
                      <td className="tabular px-4 py-3">
                        {pos.current_price ?? "—"}
                      </td>
                      <td className="px-4 py-3">
                        <PnlValue value={pos.unrealized_pnl} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </section>

      <section>
        <div className="mb-3 flex items-end justify-between gap-3">
          <h2 className="text-sm font-medium uppercase tracking-wide text-muted">
            Activity
          </h2>
          <Link
            href="/activity"
            className="text-xs text-muted hover:text-foreground"
          >
            All activity
          </Link>
        </div>
        <Card>
          {decisions.isLoading ? (
            <Spinner />
          ) : (decisions.data?.results.length ?? 0) === 0 ? (
            <EmptyState
              title="No activity yet"
              body="When a copy-trade signal hits this account, you will see the entry or the reason it was passed — including not enough cash for one contract."
            />
          ) : (
            <ul className="divide-y divide-border">
              {decisions.data?.results.slice(0, 8).map((item) => (
                <li key={item.id}>
                  <Link
                    href={`/activity/${item.id}`}
                    className="flex flex-col gap-2 px-4 py-4 hover:bg-surface-2 sm:flex-row sm:items-start sm:justify-between"
                  >
                    <div className="min-w-0">
                      <DecisionContract item={item} />
                      <p className="mt-1 text-sm font-medium">{item.title}</p>
                      <p className="mt-1 line-clamp-2 text-sm text-muted">
                        {item.summary}
                      </p>
                      <div className="mt-2">
                        <DecisionMeta item={item} />
                      </div>
                    </div>
                    <div className="shrink-0 sm:pt-1">
                      <DecisionPills item={item} />
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">
          Updates
        </h2>
        <Card>
          {updates.isLoading ? (
            <Spinner />
          ) : (updates.data?.results.length ?? 0) === 0 ? (
            <EmptyState
              title="No updates yet"
              body="Entries, skips, take-profits, and exits for this account appear here."
            />
          ) : (
            <ol className="divide-y divide-border">
              {updates.data?.results.map((item) => (
                <li key={item.id} className="flex items-start justify-between gap-4 px-4 py-3">
                  <div>
                    <p className="text-sm font-medium">{item.title}</p>
                    {item.body ? (
                      <p className="mt-0.5 text-sm text-muted">{item.body}</p>
                    ) : null}
                    <p className="mt-1 text-xs text-muted">
                      {titleCase(item.kind)} · {formatDateTime(item.created_at)}
                    </p>
                  </div>
                  {item.decision_id ? (
                    <Link
                      href={`/activity/${item.decision_id}`}
                      className="text-xs text-accent hover:underline"
                    >
                      Why
                    </Link>
                  ) : item.trade_id ? (
                    <Link
                      href={`/trades/${item.trade_id}`}
                      className="text-xs text-accent hover:underline"
                    >
                      Trade
                    </Link>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
        </Card>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">
          Trade history
        </h2>
        <Card>
          {trades.isLoading ? (
            <Spinner />
          ) : (trades.data?.results.length ?? 0) === 0 ? (
            <EmptyState
              title="No trades yet"
              body="When this account takes a copy trade, it will show in this history."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[800px] text-left text-sm">
                <thead className="border-b border-border text-xs uppercase tracking-wide text-muted">
                  <tr>
                    <th className="px-4 py-3 font-medium">Contract</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Qty</th>
                    <th className="px-4 py-3 font-medium">Entry</th>
                    <th className="px-4 py-3 font-medium">Realized</th>
                    <th className="px-4 py-3 font-medium">Entered</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.data?.results.map((trade) => (
                    <tr
                      key={trade.id}
                      className="border-b border-border last:border-b-0"
                    >
                      <td className="px-4 py-3">
                        <Link
                          href={`/trades/${trade.id}`}
                          className="hover:underline"
                        >
                          <OptionLabel
                            ticker={trade.ticker}
                            optionType={trade.option_type}
                            strike={formatStrike(trade.strike)}
                            expiration={formatDate(trade.expiration)}
                          />
                        </Link>
                        <p className="text-xs text-muted">
                          {trade.signal_code}
                          {trade.strategy_name ? ` · ${trade.strategy_name}` : ""}
                        </p>
                      </td>
                      <td className="px-4 py-3">
                        <StatusPill tone={statusTone(trade.status ?? "open")}>
                          {titleCase(trade.status ?? "open")}
                        </StatusPill>
                      </td>
                      <td className="tabular px-4 py-3">
                        {trade.remaining_quantity}/{trade.entry_quantity}
                      </td>
                      <td className="tabular px-4 py-3">{trade.entry_price}</td>
                      <td className="px-4 py-3">
                        <PnlValue value={trade.realized_pnl} />
                      </td>
                      <td className="px-4 py-3 text-muted">
                        {formatDateTime(trade.entered_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        {trades.data && trades.data.count > (trades.data.results.length || 0) ? (
          <p className="mt-2 text-xs text-muted">
            Showing {trades.data.results.length} of {trades.data.count}. See{" "}
            <Link href="/trades" className="text-accent hover:underline">
              all trades
            </Link>
            .
          </p>
        ) : null}
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-4 py-3">
      <p className="text-[11px] uppercase tracking-wide text-muted">{label}</p>
      <div className="tabular mt-1 text-lg font-medium">{value}</div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-4 py-3">
      <p className="text-[11px] uppercase tracking-wide text-muted">{label}</p>
      <div className="mt-1 text-lg font-medium">{value}</div>
    </div>
  );
}

function TierRules({ tier }: { tier: InvestmentTier }) {
  return (
    <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
      <div>
        <dt className="text-[11px] uppercase tracking-wide text-muted">
          Risk / trade
        </dt>
        <dd className="mt-0.5">{tier.max_risk_per_trade_pct}%</dd>
        <p className="mt-1 text-xs text-muted">
          Below 1 contract, still enter 1 if the premium fits in cash.
        </p>
      </div>
      <div>
        <dt className="text-[11px] uppercase tracking-wide text-muted">
          Max open
        </dt>
        <dd className="mt-0.5">{tier.max_open_positions}</dd>
      </div>
      <div>
        <dt className="text-[11px] uppercase tracking-wide text-muted">
          Daily loss limit
        </dt>
        <dd className="mt-0.5">{tier.daily_loss_limit_pct}%</dd>
      </div>
      <div>
        <dt className="text-[11px] uppercase tracking-wide text-muted">
          Hard stop
        </dt>
        <dd className="mt-0.5">{tier.hard_stop_pct}%</dd>
      </div>
      <div>
        <dt className="text-[11px] uppercase tracking-wide text-muted">
          Slippage
        </dt>
        <dd className="mt-0.5">{tier.max_entry_slippage_pct}%</dd>
      </div>
      <div>
        <dt className="text-[11px] uppercase tracking-wide text-muted">
          Force exit
        </dt>
        <dd className="mt-0.5">{tier.force_exit_time_et || "—"}</dd>
      </div>
    </dl>
  );
}

function statusTone(status: string): "neutral" | "gain" | "loss" | "warn" {
  if (status === "open") return "gain";
  if (status === "pending" || status === "partially_closed") return "warn";
  if (status === "cancelled") return "warn";
  return "neutral";
}
