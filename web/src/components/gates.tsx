"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth/provider";
import { Spinner } from "@/components/ui";

export function GuestOnly({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated") router.replace("/dashboard");
  }, [status, router]);

  if (status === "loading") return <Spinner />;
  if (status === "authenticated") return <Spinner />;
  return children;
}

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "anonymous") router.replace("/login");
  }, [status, router]);

  if (status !== "authenticated") return <Spinner />;
  return children;
}

export function RequireStaff({ children }: { children: React.ReactNode }) {
  const { status, user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "anonymous") router.replace("/login");
  }, [status, router]);

  if (status !== "authenticated") return <Spinner />;
  if (!user?.is_staff) {
    return (
      <div className="mx-auto max-w-md py-16">
        <p className="text-sm text-muted">Staff access required.</p>
      </div>
    );
  }
  return children;
}
