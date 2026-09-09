"use client";

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Button({
  children,
  variant = "primary",
  loading,
  className,
  disabled,
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  loading?: boolean;
}) {
  const styles = {
    primary: "bg-accent text-white hover:bg-accent-hover",
    secondary:
      "border border-border bg-surface-2 text-foreground hover:bg-surface",
    danger: "border border-loss/40 text-loss hover:bg-loss/10",
    ghost: "text-muted hover:text-foreground",
  }[variant];

  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={cx(
        "inline-flex h-10 items-center justify-center rounded-md px-4 text-sm font-medium transition-colors disabled:opacity-50",
        styles,
        className,
      )}
      {...props}
    >
      {loading ? "Please wait…" : children}
    </button>
  );
}

export function Switch({
  checked,
  disabled,
  label,
  onCheckedChange,
}: {
  checked: boolean;
  disabled?: boolean;
  label: string;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cx(
        "relative h-6 w-11 shrink-0 rounded-full border transition-colors disabled:opacity-40",
        checked
          ? "border-accent bg-accent"
          : "border-border bg-surface-2",
      )}
    >
      <span
        className={cx(
          "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow-sm transition-[left]",
          checked ? "left-[22px]" : "left-0.5",
        )}
      />
    </button>
  );
}

export function Input({
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cx(
        "h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground outline-none placeholder:text-muted focus:border-accent",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({
  className,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cx(
        "min-h-24 w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted focus:border-accent",
        className,
      )}
      {...props}
    />
  );
}

export function Select({
  className,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cx(
        "h-10 w-full rounded-md border border-border bg-background px-3 text-sm text-foreground outline-none focus:border-accent",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}

export function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium uppercase tracking-wide text-muted">
        {label}
      </span>
      {children}
      {error ? <span className="text-xs text-loss">{error}</span> : null}
    </label>
  );
}

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("rounded-lg border border-border bg-surface", className)}>
      {children}
    </div>
  );
}

export function Banner({
  tone = "info",
  children,
}: {
  tone?: "info" | "warning" | "danger" | "success";
  children: ReactNode;
}) {
  const styles = {
    info: "border-border bg-surface-2 text-foreground",
    warning: "border-warn/40 bg-warn/10 text-warn",
    danger: "border-loss/40 bg-loss/10 text-loss",
    success: "border-gain/40 bg-gain/10 text-gain",
  }[tone];
  return (
    <div className={cx("rounded-md border px-4 py-3 text-sm", styles)}>
      {children}
    </div>
  );
}

export function Spinner() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <div className="h-5 w-5 animate-pulse rounded-full bg-accent" />
    </div>
  );
}

export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-base font-semibold tracking-tight">Agentradez</span>
      {compact ? null : (
        <span className="text-xs uppercase tracking-[0.16em] text-muted">
          Copy trade
        </span>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  body,
}: {
  title: string;
  body?: string;
}) {
  return (
    <div className="px-4 py-12 text-center">
      <p className="text-sm font-medium">{title}</p>
      {body ? <p className="mt-1 text-sm text-muted">{body}</p> : null}
    </div>
  );
}

export function StatusPill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "gain" | "loss" | "warn";
}) {
  const styles = {
    neutral: "border-border text-muted",
    gain: "border-gain/40 text-gain",
    loss: "border-loss/40 text-loss",
    warn: "border-warn/40 text-warn",
  }[tone];
  return (
    <span
      className={cx(
        "inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide",
        styles,
      )}
    >
      {children}
    </span>
  );
}

export function VisibilityBadge({
  visibility,
}: {
  visibility?: string | null;
}) {
  const restricted = visibility === "restricted";
  return (
    <StatusPill tone={restricted ? "warn" : "gain"}>
      {restricted ? "Restricted" : "Public"}
    </StatusPill>
  );
}
