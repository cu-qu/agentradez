"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ApiError, fieldErrors } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/provider";
import { AuthFrame } from "@/components/app-shell";
import { GuestOnly } from "@/components/gates";
import { Banner, Button, Field, Input } from "@/components/ui";

export default function LoginPage() {
  return (
    <GuestOnly>
      <LoginForm />
    </GuestOnly>
  );
}

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setFormError("");
    setErrors({});
    try {
      await login(username, password);
      router.replace("/get-started");
    } catch (error) {
      setErrors(fieldErrors(error));
      setFormError(
        error instanceof ApiError ? error.message : "Could not sign in.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthFrame title="Sign in" subtitle="Use your username and password.">
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        {formError ? <Banner tone="danger">{formError}</Banner> : null}
        <Field label="Username" error={errors.username}>
          <Input
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </Field>
        <Field label="Password" error={errors.password}>
          <Input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Field>
        <Button type="submit" loading={loading} className="w-full">
          Sign in
        </Button>
      </form>
      <div className="mt-6 flex flex-col gap-2 text-sm text-muted">
        <Link href="/forgot-password" className="hover:text-foreground">
          Forgot password
        </Link>
        <p>
          No account?{" "}
          <Link href="/register" className="text-foreground hover:underline">
            Create one
          </Link>
        </p>
      </div>
    </AuthFrame>
  );
}
