"use client";

import { useState } from "react";

import { ApiError, fieldErrors } from "@/lib/api/client";
import {
  useAssignmentQuery,
  useBrokersQuery,
  useSaveAssignment,
  useStrategiesQuery,
  useTiersQuery,
  useUpdateMe,
} from "@/lib/api/hooks";
import { useAuth } from "@/lib/auth/provider";
import { useHideAmounts } from "@/lib/privacy";
import { AccountsPanel } from "@/components/accounts";
import { AppShell } from "@/components/app-shell";
import { RequireAuth } from "@/components/gates";
import { Banner, Button, Card, Select, Spinner, Switch, VisibilityBadge } from "@/components/ui";

export default function SettingsPage() {
  return (
    <RequireAuth>
      <AppShell>
        <Settings />
      </AppShell>
    </RequireAuth>
  );
}

function Settings() {
  const { user, refreshUser } = useAuth();
  const { hideAmounts, setHideAmounts } = useHideAmounts();
  const assignment = useAssignmentQuery(true);
  const brokers = useBrokersQuery(true);
  const strategies = useStrategiesQuery(true);
  const tiers = useTiersQuery(true);
  const save = useSaveAssignment();
  const updateMe = useUpdateMe();
  const [strategyOverride, setStrategyOverride] = useState<number | null>(null);
  const [languageOverride, setLanguageOverride] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [strategyError, setStrategyError] = useState("");

  const pickable = strategies.data ?? [];
  const assigned = assignment.data?.strategy;
  const assignedId = assigned?.id ?? null;
  const assignedInPicker =
    assignedId != null && pickable.some((strategy) => strategy.id === assignedId);
  const defaultPickableId = pickable[0]?.id ?? null;
  const strategyId = strategyOverride ?? assignedId ?? defaultPickableId;
  const selectValue =
    strategyOverride != null
      ? String(strategyOverride)
      : assignedInPicker
        ? String(assignedId)
        : assignedId != null
          ? ""
          : defaultPickableId != null
            ? String(defaultPickableId)
            : "";
  const selectedStrategy =
    pickable.find((strategy) => strategy.id === Number(selectValue || NaN)) ??
    (assignedInPicker || strategyOverride != null ? undefined : assigned);
  const tierId =
    assignment.data?.investment_tier.id ??
    tiers.data?.find((tier) => tier.is_default)?.id ??
    tiers.data?.[0]?.id ??
    null;
  const language = languageOverride ?? user?.preferred_language ?? "en";
  const connection = brokers.data?.[0];
  const boundAccountId =
    assignment.data?.broker_account_id || connection?.broker_account_id || "";

  async function saveAssignment() {
    if (strategyId == null || tierId == null) return;
    setError("");
    setStrategyError("");
    setMessage("");
    try {
      await save.mutateAsync({
        strategy_id: strategyId,
        investment_tier_id: tierId,
        ...(boundAccountId ? { broker_account_id: boundAccountId } : {}),
      });
      setStrategyOverride(null);
      setMessage("Strategy updated.");
    } catch (err) {
      const fields = fieldErrors(err);
      if (fields.strategy_id) setStrategyError(fields.strategy_id);
      setError(err instanceof ApiError ? err.message : "Could not update strategy.");
    }
  }

  async function saveLanguage() {
    setError("");
    setMessage("");
    try {
      await updateMe.mutateAsync({ preferred_language: language });
      await refreshUser();
      setMessage("Language updated.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update language.");
    }
  }

  if (!assignment.isSuccess || !strategies.isSuccess || !tiers.isSuccess) {
    return <Spinner />;
  }

  return (
    <div className="flex flex-col gap-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted">
          Change your strategy, language, or brokerage connection.
        </p>
      </div>

      {message ? <Banner tone="success">{message}</Banner> : null}
      {error ? <Banner tone="danger">{error}</Banner> : null}

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium uppercase tracking-wide text-muted">
          Profile
        </h2>
        <Card className="max-w-md p-5">
          <p className="text-sm">
            {user?.username} · {user?.email}
          </p>
          <div className="mt-4 flex items-end gap-3">
            <label className="flex flex-1 flex-col gap-1.5">
              <span className="text-xs font-medium uppercase tracking-wide text-muted">
                Language
              </span>
              <Select
                value={language}
                onChange={(e) => setLanguageOverride(e.target.value)}
              >
                <option value="en">English</option>
                <option value="es">Spanish</option>
              </Select>
            </label>
            <Button
              variant="secondary"
              onClick={saveLanguage}
              loading={updateMe.isPending}
            >
              Save
            </Button>
          </div>
          <div className="mt-5 flex items-start justify-between gap-4 border-t border-border pt-4">
            <div>
              <p className="text-sm font-medium">Hide amounts</p>
              <p className="mt-1 text-xs text-muted">
                Mask balances and P&L while you share your screen.
              </p>
            </div>
            <Switch
              label="Hide amounts"
              checked={hideAmounts}
              onCheckedChange={setHideAmounts}
            />
          </div>
        </Card>
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium uppercase tracking-wide text-muted">
          Strategy
        </h2>
        <Card className="max-w-md p-5">
          {assigned ? (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span>Assigned: {assigned.name}</span>
              <VisibilityBadge visibility={assigned.visibility} />
            </div>
          ) : (
            <p className="text-sm text-muted">No strategy assigned yet.</p>
          )}
          {assignment.data?.broker_account_id ? (
            <p className="mt-2 text-xs text-muted">
              Running on account {assignment.data.broker_account_id}. Apply a
              different strategy from that account below to move it.
            </p>
          ) : connection?.broker === "robinhood" ? (
            <p className="mt-2 text-xs text-muted">
              Pick an Agentic account below and apply a strategy there.
            </p>
          ) : null}
          {assigned && !assignedInPicker ? (
            <p className="mt-2 text-xs text-muted">
              You still receive signals from this strategy even if it is no
              longer listed for you.
            </p>
          ) : null}
          <div className="mt-4 flex items-end gap-3">
            <label className="flex flex-1 flex-col gap-1.5">
              <span className="text-xs font-medium uppercase tracking-wide text-muted">
                {assigned ? "Change strategy" : "Strategy"}
              </span>
              <Select
                value={selectValue}
                onChange={(e) =>
                  setStrategyOverride(
                    e.target.value ? Number(e.target.value) : null,
                  )
                }
                disabled={pickable.length === 0 && assignedId == null}
              >
                {assignedId != null && !assignedInPicker ? (
                  <option value="">Keep current assignment</option>
                ) : pickable.length === 0 ? (
                  <option value="">No strategies available</option>
                ) : null}
                {pickable.map((strategy) => (
                  <option key={strategy.id} value={strategy.id}>
                    {strategy.name}
                    {strategy.visibility === "restricted" ? " (restricted)" : ""}
                  </option>
                ))}
              </Select>
              {selectedStrategy?.visibility ? (
                <VisibilityBadge visibility={selectedStrategy.visibility} />
              ) : null}
              {strategyError ? (
                <span className="text-xs text-loss">{strategyError}</span>
              ) : null}
            </label>
            <Button
              onClick={saveAssignment}
              loading={save.isPending}
              disabled={strategyId == null || tierId == null}
            >
              Save
            </Button>
          </div>
        </Card>
      </section>

      <AccountsPanel />
    </div>
  );
}
