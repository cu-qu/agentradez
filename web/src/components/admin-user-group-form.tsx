"use client";

import { FormEvent, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ApiError, fieldErrors } from "@/lib/api/client";
import {
  useCreateAdminUserGroup,
  useDeactivateAdminUserGroup,
  useUpdateAdminUserGroup,
} from "@/lib/api/hooks";
import type { AccessUser, UserGroup, UserGroupWrite } from "@/lib/api/types";
import { Banner, Button, Card, Field, Input, Textarea } from "@/components/ui";
import { UserPicker } from "@/components/user-picker";

type FormValues = {
  name: string;
  description: string;
  isActive: boolean;
  members: AccessUser[];
};

function valuesFromGroup(group: UserGroup | undefined): FormValues {
  return {
    name: group?.name ?? "",
    description: group?.description ?? "",
    isActive: group?.is_active ?? true,
    members: group?.members ?? [],
  };
}

function buildPayload(values: FormValues): UserGroupWrite {
  return {
    name: values.name.trim(),
    description: values.description.trim(),
    is_active: values.isActive,
    member_ids: values.members.map((user) => user.id),
  };
}

export function AdminUserGroupForm({ group }: { group?: UserGroup }) {
  const router = useRouter();
  const mode = group ? "edit" : "create";
  const create = useCreateAdminUserGroup();
  const update = useUpdateAdminUserGroup();
  const deactivate = useDeactivateAdminUserGroup();
  const [values, setValues] = useState<FormValues | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");
  const [message, setMessage] = useState("");
  const [confirmDeactivate, setConfirmDeactivate] = useState(false);

  const form = useMemo(
    () => values ?? valuesFromGroup(group),
    [values, group],
  );
  const saving = create.isPending || update.isPending;

  function setField<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    setValues((current) => ({
      ...(current ?? valuesFromGroup(group)),
      [key]: value,
    }));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setErrors({});
    setFormError("");
    setMessage("");
    const payload = buildPayload(form);
    try {
      if (mode === "create") {
        const created = await create.mutateAsync(payload);
        router.replace(`/admin/user-groups/${created.id}`);
        return;
      }
      if (!group) return;
      const updated = await update.mutateAsync({ id: group.id, body: payload });
      setValues(valuesFromGroup(updated));
      setMessage("User group saved.");
      setConfirmDeactivate(false);
    } catch (error) {
      setErrors(fieldErrors(error));
      setFormError(
        error instanceof ApiError ? error.message : "Could not save the group.",
      );
    }
  }

  async function onDeactivate() {
    if (!group) return;
    setErrors({});
    setFormError("");
    setMessage("");
    try {
      const updated = await deactivate.mutateAsync(group.id);
      setValues(valuesFromGroup(updated));
      setMessage(
        "Group deactivated. Strategies that used it no longer grant access through this group.",
      );
      setConfirmDeactivate(false);
    } catch (error) {
      setFormError(
        error instanceof ApiError
          ? error.message
          : "Could not deactivate the group.",
      );
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex max-w-xl flex-col gap-6">
      {message ? <Banner tone="success">{message}</Banner> : null}
      {formError ? <Banner tone="danger">{formError}</Banner> : null}
      {group && group.is_active === false ? (
        <Banner tone="warning">
          This group is inactive. Check Active and save to restore it.
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
        <div className="flex flex-col gap-1.5">
          <span className="text-xs font-medium uppercase tracking-wide text-muted">
            Members
          </span>
          <p className="text-sm text-muted">
            Members can pick restricted strategies that include this group.
          </p>
          <UserPicker
            selected={form.members}
            onChange={(members) => setField("members", members)}
            error={errors.member_ids}
          />
        </div>
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" loading={saving}>
          {mode === "create" ? "Create group" : "Save"}
        </Button>
        <Link
          href="/admin/user-groups"
          className="text-sm text-muted hover:text-foreground"
        >
          Cancel
        </Link>
        {group && group.is_active !== false ? (
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
