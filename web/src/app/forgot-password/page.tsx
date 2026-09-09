"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";

import { api, ApiError } from "@/lib/api/client";
import { AuthFrame } from "@/components/app-shell";
import { GuestOnly } from "@/components/gates";
import { Banner, Button, Field, Input } from "@/components/ui";

export default function ForgotPasswordPage() {
  return (
    <GuestOnly>
      <ForgotForm />
    </GuestOnly>
  );
}

function ForgotForm() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setMessage("");
    try {
      const data = await api.post<{ detail: string }>("/api/auth/password-reset/", {
        email,
      });
      setMessage(data.detail);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send reset email.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthFrame
      title="Reset password"
      subtitle="We’ll email a reset link if that address has an account."
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        {message ? <Banner tone="success">{message}</Banner> : null}
        {error ? <Banner tone="danger">{error}</Banner> : null}
        <Field label="Email">
          <Input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </Field>
        <Button type="submit" loading={loading} className="w-full">
          Send reset link
        </Button>
      </form>
      <p className="mt-6 text-sm text-muted">
        <Link href="/login" className="hover:text-foreground">
          Back to sign in
        </Link>
      </p>
    </AuthFrame>
  );
}
