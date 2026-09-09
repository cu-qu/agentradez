"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { api, ApiError } from "@/lib/api/client";
import { AuthFrame } from "@/components/app-shell";
import { Banner, Spinner } from "@/components/ui";

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <VerifyEmailInner />
    </Suspense>
  );
}

function VerifyEmailInner() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [state, setState] = useState<"pending" | "ok" | "error">(
    token ? "pending" : "error",
  );
  const [message, setMessage] = useState(
    token ? "Confirming your email…" : "This link is missing a verification token.",
  );

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await api.get<{ detail: string }>("/api/auth/verify-email/", {
          token,
        });
        if (cancelled) return;
        setState("ok");
        setMessage(data.detail || "Email verified.");
      } catch (error) {
        if (cancelled) return;
        setState("error");
        setMessage(
          error instanceof ApiError
            ? error.message
            : "Invalid or expired verification token.",
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <AuthFrame title="Verify email">
      <Banner tone={state === "ok" ? "success" : state === "error" ? "danger" : "info"}>
        {message}
      </Banner>
      <p className="mt-6 text-sm">
        <Link href="/login" className="text-foreground hover:underline">
          Continue to sign in
        </Link>
      </p>
    </AuthFrame>
  );
}
