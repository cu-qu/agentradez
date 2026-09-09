"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ApiError, fieldErrors } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/provider";
import { AuthFrame } from "@/components/app-shell";
import { GuestOnly } from "@/components/gates";
import { Banner, Button, Field, Input } from "@/components/ui";

export default function RegisterPage() {
  return (
    <GuestOnly>
      <RegisterForm />
    </GuestOnly>
  );
}

function RegisterForm() {
  const { register } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setFormError("");
    setErrors({});
    if (!agreedToTerms) {
      setErrors({
        terms: "You must agree to the Terms and Conditions to create an account.",
      });
      setLoading(false);
      return;
    }
    try {
      await register({ username, email, password });
      router.replace("/get-started");
    } catch (error) {
      setErrors(fieldErrors(error));
      setFormError(
        error instanceof ApiError ? error.message : "Could not create the account.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthFrame
      title="Create account"
      subtitle="After this you’ll get a short guide, then you can connect a brokerage account."
    >
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
        <Field label="Email" error={errors.email}>
          <Input
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </Field>
        <Field label="Password" error={errors.password}>
          <Input
            type="password"
            autoComplete="new-password"
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Field>
        <div className="flex flex-col gap-1.5">
          <label className="flex items-start gap-3 text-sm leading-5 text-muted">
            <input
              id="agree-terms"
              type="checkbox"
              className="mt-0.5 h-4 w-4 shrink-0"
              checked={agreedToTerms}
              onChange={(e) => setAgreedToTerms(e.target.checked)}
              required
            />
            <span>
              I have read and agree to the{" "}
              <Link
                href="/terms"
                className="text-foreground hover:underline"
                target="_blank"
                rel="noopener noreferrer"
              >
                Terms and Conditions
              </Link>
              . I understand this is not financial advice and that I am solely
              responsible for any losses.
            </span>
          </label>
          {errors.terms ? (
            <span className="text-xs text-loss">{errors.terms}</span>
          ) : null}
        </div>
        <Button type="submit" loading={loading} className="w-full">
          Register
        </Button>
      </form>
      <p className="mt-6 text-sm text-muted">
        Already have an account?{" "}
        <Link href="/login" className="text-foreground hover:underline">
          Sign in
        </Link>
      </p>
    </AuthFrame>
  );
}
