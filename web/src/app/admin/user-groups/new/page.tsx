"use client";

import Link from "next/link";

import { AdminUserGroupForm } from "@/components/admin-user-group-form";

export default function NewAdminUserGroupPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          href="/admin/user-groups"
          className="text-sm text-muted hover:text-foreground"
        >
          User groups
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">
          New user group
        </h1>
        <p className="mt-1 text-sm text-muted">
          Add members, then attach the group to a restricted strategy.
        </p>
      </div>
      <AdminUserGroupForm />
    </div>
  );
}
