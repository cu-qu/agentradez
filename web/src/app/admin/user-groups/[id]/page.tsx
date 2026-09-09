"use client";

import { use } from "react";
import Link from "next/link";

import { useAdminUserGroupQuery } from "@/lib/api/hooks";
import { AdminUserGroupForm } from "@/components/admin-user-group-form";
import { Banner, Spinner } from "@/components/ui";

export default function EditAdminUserGroupPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const groupId = Number(id);

  return <EditUserGroup groupId={groupId} />;
}

function EditUserGroup({ groupId }: { groupId: number }) {
  const query = useAdminUserGroupQuery(true, groupId);

  if (query.isLoading) return <Spinner />;
  if (!query.data) {
    return <Banner tone="danger">User group not found.</Banner>;
  }

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
          {query.data.name}
        </h1>
        <p className="mt-1 text-sm text-muted">
          {query.data.slug}
          {query.data.member_count
            ? ` · ${query.data.member_count} members`
            : ""}
        </p>
      </div>
      <AdminUserGroupForm group={query.data} />
    </div>
  );
}
