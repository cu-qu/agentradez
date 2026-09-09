"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { ApiError, fieldErrors } from "@/lib/api/client";
import {
  useAssignmentQuery,
  useBrokerAccountsQuery,
  useBrokerAgentToolsQuery,
  useBrokersQuery,
  useConnectBroker,
  useDisconnectBroker,
  useSaveAssignment,
  useSelectBrokerAccount,
  useCompleteRobinhoodOAuth,
  useStartRobinhoodOAuth,
  useStrategiesQuery,
  useTiersQuery,
} from "@/lib/api/hooks";
import type { AgentTool, BrokerConnection, RobinhoodAccount } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import { useHiddenAccountBalances } from "@/lib/privacy";
import { HideAccountBalanceToggle } from "@/components/hide-amounts-toggle";
import { UsdValue } from "@/components/pnl";
import {
  Banner,
  Button,
  Card,
  Field,
  Input,
  Select,
  StatusPill,
  Switch,
  Textarea,
} from "@/components/ui";

type BrokerKind = "alpaca" | "robinhood";

const ALPACA_AVAILABLE = false;

export function accountPath(connectionId: number, accountNumber: string) {
  return `/accounts/${connectionId}/${encodeURIComponent(accountNumber || "default")}`;
}

function brokerStatusTone(
  status: BrokerConnection["status"],
): "gain" | "loss" | "warn" | "neutral" {
  if (status === "connected") return "gain";
  if (status === "error") return "loss";
  if (status === "disconnected") return "warn";
  return "neutral";
}

export function AccountsPanel() {
  return (
    <Suspense
      fallback={
        <Card className="px-4 py-8 text-center text-sm text-muted">
          Loading accounts…
        </Card>
      }
    >
      <AccountsPanelInner />
    </Suspense>
  );
}

function AccountsPanelInner() {
  const brokers = useBrokersQuery(true);
  const disconnect = useDisconnectBroker();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [noticeTone, setNoticeTone] = useState<"info" | "success" | "warning">("info");

  const connections = brokers.data ?? [];
  const hasConnection = connections.length > 0;
  const formOpen = showForm || !hasConnection;

  useEffect(() => {
    const status = searchParams.get("robinhood");
    if (!status) return;
    const message = searchParams.get("message") || "";
    if (status === "connected") {
      setNoticeTone("success");
      setNotice("Robinhood connected. Toggle an Agentic account below to allow trades.");
    } else if (status === "needs_account") {
      setNoticeTone("warning");
      setNotice(
        message ||
          "Robinhood is linked. Toggle an Agentic account below to allow trades.",
      );
    } else {
      setError(message || "Robinhood connect failed.");
    }
    router.replace(pathname);
  }, [pathname, router, searchParams]);

  async function onDisconnect(id: number) {
    if (!window.confirm("Disconnect this brokerage account?")) return;
    setError("");
    setNotice("");
    try {
      await disconnect.mutateAsync(id);
      setShowForm(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not disconnect.");
    }
  }

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h2 className="text-sm font-medium uppercase tracking-wide text-muted">
            Accounts
          </h2>
          <p className="mt-1 text-sm text-muted">
            One active brokerage connection at a time. Credentials are never
            echoed back.
          </p>
        </div>
        {hasConnection && !formOpen ? (
          <Button variant="secondary" onClick={() => setShowForm(true)}>
            Connect account
          </Button>
        ) : null}
      </div>

      {notice ? <Banner tone={noticeTone}>{notice}</Banner> : null}
      {error ? <Banner tone="danger">{error}</Banner> : null}

      {brokers.isLoading ? (
        <Card className="px-4 py-8 text-center text-sm text-muted">
          Loading accounts…
        </Card>
      ) : brokers.isError ? (
        <Banner tone="danger">Could not load brokerage accounts.</Banner>
      ) : (
        <>
          {hasConnection ? (
            <div className="grid gap-3">
              {connections.map((connection) => (
                <AccountCard
                  key={connection.id}
                  connection={connection}
                  disconnecting={disconnect.isPending}
                  onDisconnect={() => onDisconnect(connection.id)}
                />
              ))}
            </div>
          ) : (
            <Card className="px-4 py-8 text-center">
              <p className="text-sm font-medium">No accounts connected</p>
              <p className="mt-1 text-sm text-muted">
                Connect Robinhood to copy trades. Alpaca is coming soon.
              </p>
            </Card>
          )}

          {formOpen ? (
            <ConnectBrokerForm
              replacing={hasConnection}
              onCancel={hasConnection ? () => setShowForm(false) : undefined}
              onSuccess={() => setShowForm(false)}
            />
          ) : null}
        </>
      )}
    </section>
  );
}

function AccountCard({
  connection,
  disconnecting,
  onDisconnect,
}: {
  connection: BrokerConnection;
  disconnecting: boolean;
  onDisconnect: () => void;
}) {
  const robinhoodAccounts = useBrokerAccountsQuery(
    connection.broker === "robinhood" ? connection.id : null,
  );
  const selectedAccount = robinhoodAccounts.data?.find(
    (account) => account.account_number === connection.broker_account_id,
  );
  const { isHidden } = useHiddenAccountBalances();
  const equity = selectedAccount?.equity ?? connection.last_equity;
  const hideEquity = selectedAccount
    ? isHidden(connection.id, selectedAccount.account_number)
    : false;
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium capitalize">{connection.broker}</p>
            <StatusPill tone={brokerStatusTone(connection.status)}>
              {connection.status}
            </StatusPill>
            {connection.is_paper ? <StatusPill>Paper</StatusPill> : null}
            {connection.broker === "robinhood" && connection.agentic_ready ? (
              <StatusPill tone="gain">Trading on</StatusPill>
            ) : connection.broker === "robinhood" ? (
              <StatusPill tone="warn">Trading off</StatusPill>
            ) : null}
          </div>
          {connection.broker_account_id ? (
            <p className="mt-1 text-xs text-muted">
              Trading in {connection.broker_account_id}
            </p>
          ) : null}
          {connection.broker !== "robinhood" ? (
            <Link
              href={accountPath(
                connection.id,
                connection.broker_account_id || "default",
              )}
              className="mt-2 inline-block text-xs text-accent hover:underline"
            >
              View account
            </Link>
          ) : null}
        </div>
        <Button
          variant="danger"
          onClick={onDisconnect}
          loading={disconnecting}
        >
          Disconnect
        </Button>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-muted">
            Equity
          </dt>
          <dd className="tabular mt-0.5">
            <UsdValue value={equity} hide={hideEquity} />
          </dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-muted">
            Last synced
          </dt>
          <dd className="mt-0.5 text-muted">
            {connection.last_synced_at
              ? formatDateTime(connection.last_synced_at)
              : "—"}
          </dd>
        </div>
      </dl>
      {connection.broker === "robinhood" ? (
        <RobinhoodAccountList connection={connection} />
      ) : connection.last_error ? (
        <p className="mt-3 text-xs text-loss">{connection.last_error}</p>
      ) : null}
      <p className="mt-3 text-xs text-muted">
        Connected {formatDateTime(connection.created_at)}
      </p>
    </Card>
  );
}

function accountLabel(account: RobinhoodAccount) {
  return (
    account.nickname ||
    (account.agentic_allowed ? "Agentic" : account.type || "Account")
  );
}

function RobinhoodAccountList({
  connection,
}: {
  connection: BrokerConnection;
}) {
  const accounts = useBrokerAccountsQuery(connection.id);
  const select = useSelectBrokerAccount();
  const { isHidden } = useHiddenAccountBalances();
  const [error, setError] = useState("");
  const [pendingNumber, setPendingNumber] = useState<string | null>(null);

  const rows = (accounts.data ?? []).filter((account) => account.agentic_allowed);

  async function setTradingAccount(accountNumber: string) {
    setError("");
    setPendingNumber(accountNumber || "off");
    try {
      await select.mutateAsync({
        id: connection.id,
        account_number: accountNumber,
      });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not update trading account.",
      );
    } finally {
      setPendingNumber(null);
    }
  }

  return (
    <div className="mt-4 border-t border-border pt-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium">Robinhood Agentic accounts</p>
          <p className="mt-1 text-xs text-muted">
            Only Agentic accounts are listed. Trades run in the one you turn
            on. Apply one strategy to a single Agentic account — only that
            account receives copy trades.
          </p>
        </div>
        <Button
          variant="ghost"
          className="h-8 px-2 text-xs"
          onClick={() => void accounts.refetch()}
          loading={accounts.isFetching && !accounts.isLoading}
        >
          Refresh
        </Button>
      </div>
      {error ? <p className="mt-2 text-xs text-loss">{error}</p> : null}
      {connection.status === "error" && connection.last_error ? (
        <p className="mt-2 text-xs text-loss">{connection.last_error}</p>
      ) : connection.last_error && !connection.agentic_ready ? (
        <p className="mt-2 text-xs text-muted">{connection.last_error}</p>
      ) : null}
      {accounts.isLoading ? (
        <p className="mt-3 text-xs text-muted">Loading Robinhood accounts…</p>
      ) : accounts.isError ? (
        <p className="mt-3 text-xs text-loss">
          Could not load Robinhood accounts. Try refresh, or reconnect.
        </p>
      ) : rows.length === 0 ? (
        <p className="mt-3 text-xs text-muted">
          {accounts.data?.length
            ? "No Agentic accounts came back from Robinhood. Margin and other accounts are hidden."
            : "No Agentic accounts came back from Robinhood yet."}
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-border rounded-md border border-border">
          {rows.map((account) => {
            const trading =
              account.account_number === connection.broker_account_id;
            const busy = select.isPending && pendingNumber != null;
            return (
              <li key={account.account_number} className="flex flex-col gap-3 px-3 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-sm font-medium">
                        {accountLabel(account)}
                      </p>
                      <StatusPill tone="gain">Agentic</StatusPill>
                      {account.is_default ? <StatusPill>Primary</StatusPill> : null}
                      {trading ? <StatusPill tone="gain">Trading</StatusPill> : null}
                    </div>
                    <p className="mt-1 truncate text-xs text-muted">
                      {account.account_number}
                      {account.type ? ` · ${account.type}` : ""}
                      {account.state ? ` · ${account.state}` : ""}
                      {account.option_level ? ` · ${account.option_level}` : ""}
                    </p>
                    <Link
                      href={accountPath(connection.id, account.account_number)}
                      className="mt-2 inline-block text-xs text-accent hover:underline"
                    >
                      View details
                    </Link>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <p className="tabular text-sm font-medium">
                      <UsdValue
                        value={account.equity}
                        hide={isHidden(
                          connection.id,
                          account.account_number,
                        )}
                      />
                    </p>
                    <HideAccountBalanceToggle
                      connectionId={connection.id}
                      accountNumber={account.account_number}
                      label={accountLabel(account)}
                    />
                    <Switch
                      label={`Trade in ${accountLabel(account)}`}
                      checked={trading}
                      disabled={busy}
                      onCheckedChange={(checked) => {
                        void setTradingAccount(
                          checked ? account.account_number : "",
                        );
                      }}
                    />
                  </div>
                </div>
                <div className="rounded-md bg-background/60 px-2 py-2">
                  <AccountAssignmentForm
                    accountNumber={account.account_number}
                    compact
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <RobinhoodAgentTools connectionId={connection.id} />
    </div>
  );
}

export function AccountAssignmentForm({
  accountNumber,
  compact = false,
}: {
  accountNumber: string;
  compact?: boolean;
}) {
  const assignment = useAssignmentQuery(true);
  const strategies = useStrategiesQuery(true);
  const tiers = useTiersQuery(true);
  const save = useSaveAssignment();
  const [strategyOverride, setStrategyOverride] = useState<number | null>(null);
  const [tierOverride, setTierOverride] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const pickable = strategies.data ?? [];
  const tierOptions = tiers.data ?? [];
  const boundHere =
    assignment.data?.broker_account_id === accountNumber ||
    (accountNumber === "default" && !assignment.data?.broker_account_id);
  const assignedId = boundHere ? (assignment.data?.strategy.id ?? null) : null;
  const defaultId = pickable[0]?.id ?? null;
  const strategyId = strategyOverride ?? assignedId ?? defaultId;
  const assignedTierId = boundHere
    ? (assignment.data?.investment_tier.id ?? null)
    : null;
  const defaultTierId =
    assignedTierId ??
    assignment.data?.investment_tier.id ??
    tierOptions.find((tier) => tier.is_default)?.id ??
    tierOptions[0]?.id ??
    null;
  const tierId = tierOverride ?? defaultTierId;
  const selectedStrategy = pickable.find((row) => row.id === strategyId);
  const selectedTier = tierOptions.find((row) => row.id === tierId);

  async function apply() {
    if (strategyId == null || tierId == null) return;
    setError("");
    setMessage("");
    try {
      await save.mutateAsync({
        strategy_id: strategyId,
        investment_tier_id: tierId,
        broker_account_id: accountNumber,
      });
      setMessage("Strategy and tier applied to this account.");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not apply this strategy.",
      );
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex min-w-[10rem] flex-1 flex-col gap-1">
          <span className="text-[11px] font-medium uppercase tracking-wide text-muted">
            Strategy
          </span>
          <Select
            value={strategyId != null ? String(strategyId) : ""}
            onChange={(e) =>
              setStrategyOverride(e.target.value ? Number(e.target.value) : null)
            }
            disabled={pickable.length === 0}
          >
            {pickable.length === 0 ? (
              <option value="">No strategies available</option>
            ) : null}
            {pickable.map((strategy) => (
              <option key={strategy.id} value={strategy.id}>
                {strategy.name}
              </option>
            ))}
          </Select>
        </label>
        <label className="flex min-w-[10rem] flex-1 flex-col gap-1">
          <span className="text-[11px] font-medium uppercase tracking-wide text-muted">
            Investment tier
          </span>
          <Select
            value={tierId != null ? String(tierId) : ""}
            onChange={(e) =>
              setTierOverride(e.target.value ? Number(e.target.value) : null)
            }
            disabled={tierOptions.length === 0}
          >
            {tierOptions.length === 0 ? (
              <option value="">No tiers available</option>
            ) : null}
            {tierOptions.map((tier) => (
              <option key={tier.id} value={tier.id}>
                {tier.name}
              </option>
            ))}
          </Select>
        </label>
        <Button
          className="h-10"
          onClick={() => void apply()}
          loading={save.isPending}
          disabled={strategyId == null || tierId == null}
        >
          Apply
        </Button>
      </div>
      {!compact && selectedStrategy?.description ? (
        <p className="text-sm text-muted">{selectedStrategy.description}</p>
      ) : null}
      {!compact && selectedTier?.description ? (
        <p className="text-sm text-muted">{selectedTier.description}</p>
      ) : null}
      {boundHere && assignment.data ? (
        <p className="text-xs text-muted">
          Running {assignment.data.strategy.name} ·{" "}
          {assignment.data.investment_tier.name} on this account.
        </p>
      ) : (
        <p className="text-xs text-muted">
          Apply a strategy and tier here to copy trades into this account.
          Signals still leave a pass on this page when cash cannot cover
          one contract.
        </p>
      )}
      {message ? <p className="text-xs text-gain">{message}</p> : null}
      {error ? <p className="text-xs text-loss">{error}</p> : null}
    </div>
  );
}

function RobinhoodAgentTools({ connectionId }: { connectionId: number }) {
  const tools = useBrokerAgentToolsQuery(connectionId);
  const [open, setOpen] = useState(false);
  const rows = tools.data ?? [];
  const groups = rows.reduce<Record<string, AgentTool[]>>((acc, tool) => {
    const category = tool.category || "Other";
    acc[category] = acc[category] ?? [];
    acc[category].push(tool);
    return acc;
  }, {});

  return (
    <div className="mt-4 border-t border-border pt-4">
      <button
        type="button"
        className="flex w-full items-center justify-between text-left"
        onClick={() => setOpen((value) => !value)}
      >
        <div>
          <p className="text-sm font-medium">Robinhood agent API</p>
          <p className="mt-1 text-xs text-muted">
            MCP tools on this Agentic account. Writes only work on the Agentic
            account you turn on.
          </p>
        </div>
        <span className="text-xs text-muted">{open ? "Hide" : "Show"}</span>
      </button>
      {open ? (
        tools.isLoading ? (
          <p className="mt-3 text-xs text-muted">Loading agent tools…</p>
        ) : tools.isError ? (
          <p className="mt-3 text-xs text-loss">
            Could not load live tools. The documented catalog is listed in API
            docs.
          </p>
        ) : (
          <div className="mt-3 flex flex-col gap-3">
            {Object.entries(groups).map(([category, categoryTools]) => (
              <div key={category}>
                <p className="text-[11px] font-medium uppercase tracking-wide text-muted">
                  {category}
                </p>
                <ul className="mt-1 divide-y divide-border rounded-md border border-border">
                  {categoryTools.map((tool) => (
                    <li key={tool.name} className="px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <code className="text-xs">{tool.name}</code>
                        {tool.available ? (
                          <StatusPill tone="gain">Live</StatusPill>
                        ) : (
                          <StatusPill>Catalog</StatusPill>
                        )}
                      </div>
                      {tool.description ? (
                        <p className="mt-1 text-xs text-muted">
                          {tool.description}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )
      ) : null}
    </div>
  );
}

function ConnectBrokerForm({
  replacing,
  onCancel,
  onSuccess,
}: {
  replacing: boolean;
  onCancel?: () => void;
  onSuccess: () => void;
}) {
  const connect = useConnectBroker();
  const robinhoodOAuth = useStartRobinhoodOAuth();
  const robinhoodComplete = useCompleteRobinhoodOAuth();
  const [broker, setBroker] = useState<BrokerKind>("robinhood");
  const [isPaper, setIsPaper] = useState(true);
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");
  const [callbackUrl, setCallbackUrl] = useState("");
  const [robinhoodAuthUrl, setRobinhoodAuthUrl] = useState("");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError("");
    setErrors({});
    if (broker === "alpaca" && !ALPACA_AVAILABLE) {
      setFormError("Alpaca is coming soon. Connect Robinhood for now.");
      return;
    }
    if (broker === "robinhood") {
      if (robinhoodAuthUrl) {
        try {
          await robinhoodComplete.mutateAsync(callbackUrl);
          onSuccess();
        } catch (error) {
          setErrors(fieldErrors(error));
          setFormError(
            error instanceof ApiError
              ? error.message
              : "Could not finish Robinhood connect. Paste the full URL from the address bar.",
          );
        }
        return;
      }
      try {
        const started = await robinhoodOAuth.mutateAsync();
        setRobinhoodAuthUrl(started.authorization_url);
        const popup = window.open(started.authorization_url, "_blank");
        if (!popup) {
          setFormError(
            "Allow popups, then click Reopen Robinhood. Stay on this page to paste the URL.",
          );
        }
      } catch (error) {
        setFormError(
          error instanceof ApiError
            ? error.message
            : "Could not start Robinhood login.",
        );
      }
      return;
    }
    try {
      await connect.mutateAsync({
        broker,
        api_key: apiKey,
        api_secret: apiSecret,
        is_paper: isPaper,
      });
      onSuccess();
    } catch (error) {
      setErrors(fieldErrors(error));
      setFormError(
        error instanceof ApiError ? error.message : "Could not connect the broker.",
      );
    }
  }

  return (
    <Card className="max-w-lg p-5">
      <h3 className="text-sm font-medium">
        {replacing ? "Replace brokerage account" : "Connect a brokerage account"}
      </h3>
      {replacing ? (
        <p className="mt-1 text-sm text-muted">
          Connecting a new account disconnects the current one.
        </p>
      ) : null}

      <div className="mt-4 flex gap-2">
        <Button
          variant={broker === "alpaca" ? "primary" : "secondary"}
          className="gap-2"
          disabled={!ALPACA_AVAILABLE}
          onClick={() => setBroker("alpaca")}
        >
          Alpaca
          {!ALPACA_AVAILABLE ? <StatusPill>Coming soon</StatusPill> : null}
        </Button>
        <Button
          variant={broker === "robinhood" ? "primary" : "secondary"}
          onClick={() => setBroker("robinhood")}
        >
          Robinhood
        </Button>
      </div>

      <form onSubmit={onSubmit} className="mt-4 flex flex-col gap-4">
        {formError ? <Banner tone="danger">{formError}</Banner> : null}
        {broker === "alpaca" ? (
          <>
            <Field label="API key" error={errors.api_key}>
              <Input
                autoComplete="off"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                required
              />
            </Field>
            <Field label="API secret" error={errors.api_secret}>
              <Input
                type="password"
                autoComplete="off"
                value={apiSecret}
                onChange={(e) => setApiSecret(e.target.value)}
                required
              />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={isPaper}
                onChange={(e) => setIsPaper(e.target.checked)}
              />
              Paper trading
              <StatusPill>Recommended</StatusPill>
            </label>
          </>
        ) : robinhoodAuthUrl ? (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-muted">
              Finish in the Robinhood tab, then come back here. That tab will
              say localhost failed to load — that is expected. Copy the full
              URL from its address bar and paste it below.
            </p>
            <a
              href={robinhoodAuthUrl}
              target="_blank"
              rel="noreferrer"
              className="text-sm text-accent hover:underline"
            >
              Reopen Robinhood
            </a>
            <Field label="Paste localhost URL" error={errors.callback_url}>
              <Textarea
                value={callbackUrl}
                onChange={(e) => setCallbackUrl(e.target.value)}
                placeholder="http://localhost:8001/api/broker-connections/robinhood/oauth/callback/?code=…&state=…"
                required
              />
            </Field>
          </div>
        ) : (
          <p className="text-sm text-muted">
            You’ll sign in at Robinhood. After you allow access, copy the
            localhost URL from the address bar and paste it back here. If you
            don’t have an Agentic account yet, Robinhood will prompt you to
            open one on desktop.
          </p>
        )}
        <div className="flex gap-2">
          <Button
            type="submit"
            loading={
              connect.isPending ||
              robinhoodOAuth.isPending ||
              robinhoodComplete.isPending
            }
            disabled={broker === "robinhood" && Boolean(robinhoodAuthUrl) && !callbackUrl.trim()}
          >
            {broker === "robinhood"
              ? robinhoodAuthUrl
                ? "Finish connect"
                : "Continue with Robinhood"
              : "Connect"}
          </Button>
          {onCancel ? (
            <Button variant="ghost" onClick={onCancel}>
              Cancel
            </Button>
          ) : null}
        </div>
      </form>
    </Card>
  );
}

export function connectedBroker(connections: BrokerConnection[] | undefined) {
  return connections?.find((connection) => {
    if (connection.status !== "connected") return false;
    if (connection.broker === "robinhood") return Boolean(connection.agentic_ready);
    return true;
  });
}
