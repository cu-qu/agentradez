"use client";

import { FormEvent, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ApiError, fieldErrors } from "@/lib/api/client";
import {
  useAdminStrategyTypesQuery,
  useCreateAdminStrategy,
  useDeactivateAdminStrategy,
  useUpdateAdminStrategy,
} from "@/lib/api/hooks";
import type {
  AccessUser,
  AdminStrategy,
  SignalSourceOption,
  StrategyTypeOption,
  StrategyWrite,
  UserGroupBrief,
  Visibility,
} from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";
import {
  Banner,
  Button,
  Card,
  Field,
  Input,
  Select,
  Spinner,
  Textarea,
} from "@/components/ui";
import { GroupPicker, UserPicker } from "@/components/user-picker";

const DEFAULT_LOOKBACK = 48;
const DEFAULT_POLL_INTERVAL = 60;
const SECONDS_PER_HOUR = 3600;

function secondsToHoursInput(seconds: number): string {
  return String(Number((seconds / SECONDS_PER_HOUR).toFixed(6)));
}

function hoursToSeconds(hoursText: string, fallback = DEFAULT_POLL_INTERVAL): number {
  const hours = Number(hoursText);
  if (!Number.isFinite(hours) || hours <= 0) return fallback;
  return Math.round(hours * SECONDS_PER_HOUR);
}

function parseLookbackHours(value: string): number {
  const hours = Number(value);
  if (!Number.isFinite(hours) || hours <= 0) return DEFAULT_LOOKBACK;
  return hours;
}

function formatSavedAt(date: Date): string {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

const FALLBACK_X_SOURCE: SignalSourceOption = {
  value: "x",
  label: "X",
  description: "Pull option trades posted by a watched X account.",
  config_fields: ["x_source"],
  available: true,
};

function signalSourcesFor(type: StrategyTypeOption | undefined): SignalSourceOption[] {
  if (type?.signal_sources?.length) return type.signal_sources;
  if (type?.config_fields.includes("x_source")) return [FALLBACK_X_SOURCE];
  return [];
}

function firstAvailableSource(type: StrategyTypeOption | undefined): string {
  return signalSourcesFor(type).find((source) => source.available)?.value ?? "x";
}

function selectedSignalSource(
  type: StrategyTypeOption | undefined,
  value: string,
): SignalSourceOption | undefined {
  return signalSourcesFor(type).find((source) => source.value === value);
}

function typeHasXSource(type: StrategyTypeOption | undefined, sourceValue: string): boolean {
  const source = selectedSignalSource(type, sourceValue);
  if (source) return source.config_fields.includes("x_source");
  return Boolean(type?.config_fields.includes("x_source"));
}

function stripHandle(value: string): string {
  return value.trim().replace(/^@+/, "");
}

function buildPayload(
  values: FormValues,
  type: StrategyTypeOption | undefined,
  mode: "create" | "edit",
): StrategyWrite {
  const payload: StrategyWrite = {
    name: values.name.trim(),
    description: values.description.trim(),
    strategy_type: values.strategyType,
    visibility: values.visibility,
    is_active: values.isActive,
    allowed_user_ids: values.allowedUsers.map((user) => user.id),
    allowed_group_ids: values.allowedGroups.map((group) => group.id),
  };
  if (signalSourcesFor(type).length > 0) {
    payload.signal_source = values.signalSource;
  }
  if (typeHasXSource(type, values.signalSource) || values.signalSource === "x") {
    const handle = stripHandle(values.handle);
    if (handle || mode === "edit") {
      payload.x_source = {
        handle,
        display_name: values.displayName.trim(),
        is_active: values.watcherActive,
        lookback_hours: parseLookbackHours(values.lookbackHours),
        poll_interval_seconds: hoursToSeconds(values.pollIntervalHours),
      };
    }
  }
  return payload;
}

type FormValues = {
  name: string;
  description: string;
  strategyType: string;
  signalSource: string;
  visibility: Visibility;
  isActive: boolean;
  handle: string;
  displayName: string;
  lookbackHours: string;
  pollIntervalHours: string;
  watcherActive: boolean;
  allowedUsers: AccessUser[];
  allowedGroups: UserGroupBrief[];
};

function valuesFromStrategy(
  strategy: AdminStrategy | undefined,
  types: StrategyTypeOption[],
): FormValues {
  const source = strategy?.x_source;
  const strategyType = strategy?.strategy_type ?? types[0]?.value ?? "";
  const selectedType = types.find((type) => type.value === strategyType);
  return {
    name: strategy?.name ?? "",
    description: strategy?.description ?? "",
    strategyType,
    signalSource: strategy?.signal_source || firstAvailableSource(selectedType),
    visibility: strategy?.visibility ?? "public",
    isActive: strategy?.is_active ?? true,
    handle: source?.handle ?? "",
    displayName: source?.display_name ?? "",
    lookbackHours: String(source?.lookback_hours ?? DEFAULT_LOOKBACK),
    pollIntervalHours: secondsToHoursInput(
      source?.poll_interval_seconds ?? DEFAULT_POLL_INTERVAL,
    ),
    watcherActive: source?.is_active ?? true,
    allowedUsers: strategy?.allowed_users ?? [],
    allowedGroups: strategy?.allowed_groups ?? [],
  };
}

export function AdminStrategyForm({
  strategy,
}: {
  strategy?: AdminStrategy;
}) {
  const router = useRouter();
  const mode = strategy ? "edit" : "create";
  const typesQuery = useAdminStrategyTypesQuery(true);
  const create = useCreateAdminStrategy();
  const update = useUpdateAdminStrategy();
  const deactivate = useDeactivateAdminStrategy();
  const types = typesQuery.data;
  const [values, setValues] = useState<FormValues | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");
  const [message, setMessage] = useState("");
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [dirty, setDirty] = useState(false);
  const [confirmDeactivate, setConfirmDeactivate] = useState(false);

  const form = useMemo(() => {
    if (values) return values;
    if (!typesQuery.isSuccess || !types) return null;
    return valuesFromStrategy(strategy, types);
  }, [values, typesQuery.isSuccess, strategy, types]);

  const selectedType = types?.find((type) => type.value === form?.strategyType);
  const sourceOptions = signalSourcesFor(selectedType);
  const selectedSource = selectedSignalSource(selectedType, form?.signalSource ?? "");
  const showXSource = typeHasXSource(selectedType, form?.signalSource ?? "");
  const saving = create.isPending || update.isPending;

  function setField<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    setDirty(true);
    setMessage("");
    setValues((current) => ({
      ...(current ?? valuesFromStrategy(strategy, types ?? [])),
      [key]: value,
    }));
  }

  function setStrategyType(nextType: string) {
    const type = types?.find((row) => row.value === nextType);
    setDirty(true);
    setMessage("");
    setValues((current) => ({
      ...(current ?? valuesFromStrategy(strategy, types ?? [])),
      strategyType: nextType,
      signalSource: firstAvailableSource(type),
    }));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!form) return;
    setErrors({});
    setFormError("");
    setMessage("");
    const payload = buildPayload(form, selectedType, mode);
    try {
      if (mode === "create") {
        const created = await create.mutateAsync(payload);
        router.replace(`/admin/strategies/${created.id}`);
        return;
      }
      if (!strategy) return;
      const updated = await update.mutateAsync({ id: strategy.id, body: payload });
      setValues(valuesFromStrategy(updated, types ?? []));
      setDirty(false);
      setSavedAt(new Date());
      setMessage("Strategy saved");
      setConfirmDeactivate(false);
    } catch (error) {
      setErrors(fieldErrors(error));
      setFormError(
        error instanceof ApiError ? error.message : "Could not save the strategy.",
      );
    }
  }

  async function onDeactivate() {
    if (!strategy) return;
    setErrors({});
    setFormError("");
    setMessage("");
    try {
      const updated = await deactivate.mutateAsync(strategy.id);
      setValues(valuesFromStrategy(updated, types ?? []));
      setDirty(false);
      setSavedAt(null);
      setMessage("Strategy deactivated. It is hidden from users until you restore it.");
      setConfirmDeactivate(false);
    } catch (error) {
      setFormError(
        error instanceof ApiError
          ? error.message
          : "Could not deactivate the strategy.",
      );
    }
  }

  if (typesQuery.isLoading) return <Spinner />;
  if (typesQuery.isError) {
    return (
      <Banner tone="danger">
        {typesQuery.error instanceof ApiError
          ? typesQuery.error.message
          : "Could not load strategy types."}
      </Banner>
    );
  }
  if (!form || !types) return <Spinner />;
  if (types.length === 0) {
    return (
      <Banner tone="warning">No strategy types are available to create.</Banner>
    );
  }

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      className="flex max-w-xl flex-col gap-6"
    >
      {message ? (
        <Banner tone="success">
          {savedAt ? `${message} at ${formatSavedAt(savedAt)}.` : message}
        </Banner>
      ) : null}
      {formError ? <Banner tone="danger">{formError}</Banner> : null}
      {strategy && strategy.is_active === false ? (
        <Banner tone="warning">
          This strategy is inactive. Check Active and save to restore it on the
          user picker.
        </Banner>
      ) : null}

      <Card className="flex flex-col gap-4 p-5">
        <Field label="Name" error={errors.name}>
          <Input
            value={form.name}
            onChange={(e) => setField("name", e.target.value)}
            required
          />
        </Field>
        <Field label="Description" error={errors.description}>
          <Textarea
            value={form.description}
            onChange={(e) => setField("description", e.target.value)}
            rows={3}
          />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.isActive}
            onChange={(e) => setField("isActive", e.target.checked)}
          />
          Active
        </label>
      </Card>

      <Card className="flex flex-col gap-4 p-5">
        <Field label="Visibility" error={errors.visibility}>
          <Select
            value={form.visibility}
            onChange={(e) =>
              setField("visibility", e.target.value as Visibility)
            }
          >
            <option value="public">Public</option>
            <option value="restricted">Restricted</option>
          </Select>
        </Field>
        <p className="text-sm text-muted">
          {form.visibility === "restricted"
            ? "Only the users and group members below can pick this strategy. Empty lists mean staff-only. Existing assignments keep receiving signals if access is later revoked."
            : "Every authenticated user can pick this strategy."}
        </p>
        {form.visibility === "restricted" ? (
          <>
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-medium uppercase tracking-wide text-muted">
                Allowed users
              </span>
              <UserPicker
                selected={form.allowedUsers}
                onChange={(users) => setField("allowedUsers", users)}
                error={errors.allowed_user_ids}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-medium uppercase tracking-wide text-muted">
                Allowed groups
              </span>
              <GroupPicker
                selected={form.allowedGroups}
                onChange={(groups) => setField("allowedGroups", groups)}
                error={errors.allowed_group_ids}
              />
            </div>
          </>
        ) : null}
      </Card>

      <Card className="flex flex-col gap-4 p-5">
        <Field label="Type" error={errors.strategy_type}>
          <Select
            value={form.strategyType}
            onChange={(e) => setStrategyType(e.target.value)}
            required
          >
            {types.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </Select>
        </Field>
        {selectedType?.description ? (
          <p className="text-sm text-muted">{selectedType.description}</p>
        ) : null}

        {sourceOptions.length > 0 ? (
          <>
            <Field label="Source" error={errors.signal_source}>
              <Select
                value={form.signalSource}
                onChange={(e) => setField("signalSource", e.target.value)}
                required
              >
                {sourceOptions.map((source) => (
                  <option
                    key={source.value}
                    value={source.value}
                    disabled={!source.available}
                  >
                    {source.available
                      ? source.label
                      : `${source.label} (coming soon)`}
                  </option>
                ))}
              </Select>
            </Field>
            {selectedSource?.description ? (
              <p className="text-sm text-muted">{selectedSource.description}</p>
            ) : null}
          </>
        ) : null}

        {showXSource ? (
          <div className="flex flex-col gap-4 border-t border-border pt-4">
            <p className="text-xs font-medium uppercase tracking-wide text-muted">
              X account
            </p>
            <Field label="Handle" error={errors["x_source.handle"]}>
              <Input
                value={form.handle}
                onChange={(e) => setField("handle", e.target.value)}
                placeholder="handle"
                required={mode === "edit" || Boolean(form.handle)}
              />
            </Field>
            <Field label="Display name" error={errors["x_source.display_name"]}>
              <Input
                value={form.displayName}
                onChange={(e) => setField("displayName", e.target.value)}
              />
            </Field>
            <Field label="Lookback hours" error={errors["x_source.lookback_hours"]}>
              <Input
                type="text"
                inputMode="decimal"
                value={form.lookbackHours}
                onChange={(e) => setField("lookbackHours", e.target.value)}
              />
            </Field>
            <Field
              label="How often to pull from X (hours)"
              error={errors["x_source.poll_interval_seconds"]}
            >
              <Input
                type="text"
                inputMode="decimal"
                value={form.pollIntervalHours}
                onChange={(e) => setField("pollIntervalHours", e.target.value)}
                placeholder="1"
              />
              <span className="text-xs text-muted">
                {Number(form.pollIntervalHours) > 0
                  ? `Saves as ${hoursToSeconds(form.pollIntervalHours).toLocaleString()} seconds.`
                  : "Enter hours, for example 1 or 0.5."}
              </span>
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.watcherActive}
                onChange={(e) => setField("watcherActive", e.target.checked)}
              />
              Watcher active
            </label>
            {strategy?.x_source ? (
              <dl className="grid gap-2 text-xs text-muted sm:grid-cols-2">
                <div>
                  <dt className="uppercase tracking-wide">Last polled</dt>
                  <dd>{formatDateTime(strategy.x_source.last_polled_at)}</dd>
                </div>
                <div>
                  <dt className="uppercase tracking-wide">Last error</dt>
                  <dd>{strategy.x_source.last_error || "—"}</dd>
                </div>
              </dl>
            ) : null}
          </div>
        ) : null}
      </Card>

      <div className="sticky bottom-0 z-10 flex flex-wrap items-center gap-3 border-t border-border bg-background/95 py-3">
        <Button type="submit" loading={saving}>
          {mode === "create"
            ? "Create strategy"
            : dirty
              ? "Save changes"
              : savedAt
                ? "Saved"
                : "Save"}
        </Button>
        {saving ? (
          <span className="text-sm text-muted">Saving…</span>
        ) : formError ? (
          <span className="text-sm text-loss">Couldn’t save. See the error above.</span>
        ) : dirty ? (
          <span className="text-sm text-warn">Unsaved changes</span>
        ) : savedAt ? (
          <span className="text-sm text-gain">
            Strategy saved · {formatSavedAt(savedAt)}
          </span>
        ) : null}
        <Link href="/admin/strategies" className="text-sm text-muted hover:text-foreground">
          Cancel
        </Link>
        {strategy && strategy.is_active !== false ? (
          confirmDeactivate ? (
            <span className="ml-auto flex items-center gap-2">
              <Button
                variant="danger"
                loading={deactivate.isPending}
                onClick={onDeactivate}
              >
                Deactivate
              </Button>
              <Button variant="ghost" onClick={() => setConfirmDeactivate(false)}>
                Cancel
              </Button>
            </span>
          ) : (
            <Button
              variant="danger"
              className="ml-auto"
              onClick={() => setConfirmDeactivate(true)}
            >
              Deactivate
            </Button>
          )
        ) : null}
      </div>
    </form>
  );
}
