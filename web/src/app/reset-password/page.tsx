"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { api, ApiError, fieldErrors } from "@/lib/api/client";
import { AuthFrame } from "@/components/app-shell";
import { Banner, Button, Field, Input, Spinner } from "@/components/ui";

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <ResetForm />
    </Suspense>
  );
}

function ResetForm() {
  const searchParams = useSearchParams();
  const uid = searchParams.get("uid") ?? "";
  const token = searchParams.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [formError, setFormError] = useState(
    uid && token ? "" : "This reset link is missing uid or token.",
  );
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setFormError("");
    setErrors({});
    try {
      const data = await api.post<{ detail: string }>(
        "/api/auth/password-reset/confirm/",
        { uid, token, new_password: password },
      );
      setMessage(data.detail);
    } catch (error) {
      setErrors(fieldErrors(error));
      setFormError(
        error instanceof ApiError ? error.message : "Could not reset password.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthFrame title="Choose a new password">
      {message ? (
        <div className="flex flex-col gap-4">
          <Banner tone="success">{message}</Banner>
          <Link href="/login" className="text-sm hover:underline">
            Sign in
          </Link>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          {formError ? <Banner tone="danger">{formError}</Banner> : null}
          <Field label="New password" error={errors.new_password}>
            <Input
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </Field>
          <Button
            type="submit"
            loading={loading}
            disabled={!uid || !token}
            className="w-full"
          >
            Update password
          </Button>
        </form>
      )}
    </AuthFrame>
  );
}
