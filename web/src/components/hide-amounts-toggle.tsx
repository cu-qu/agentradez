"use client";

import { useHiddenAccountBalances, useHideAmounts } from "@/lib/privacy";

export function HideAmountsToggle() {
  const { hideAmounts, setHideAmounts } = useHideAmounts();

  return (
    <button
      type="button"
      onClick={() => setHideAmounts(!hideAmounts)}
      className="relative flex h-9 w-9 items-center justify-center rounded-md border border-border text-muted hover:text-foreground"
      aria-pressed={hideAmounts}
      aria-label={hideAmounts ? "Show amounts" : "Hide amounts"}
      title={hideAmounts ? "Show amounts" : "Hide amounts"}
    >
      {hideAmounts ? <EyeOffIcon /> : <EyeIcon />}
    </button>
  );
}

export function HideAccountBalanceToggle({
  connectionId,
  accountNumber,
  label,
}: {
  connectionId: number;
  accountNumber: string;
  label: string;
}) {
  const { isHidden, setHidden } = useHiddenAccountBalances();
  const hidden = isHidden(connectionId, accountNumber);

  return (
    <button
      type="button"
      onClick={() => setHidden(connectionId, accountNumber, !hidden)}
      className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:text-foreground"
      aria-pressed={hidden}
      aria-label={hidden ? `Show ${label} balance` : `Hide ${label} balance`}
      title={hidden ? "Show this account's balance" : "Hide this account's balance"}
    >
      {hidden ? <EyeOffIcon /> : <EyeIcon />}
    </button>
  );
}

function EyeIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M2.2 8s2.1-4 5.8-4 5.8 4 5.8 4-2.1 4-5.8 4-5.8-4-5.8-4Z"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <circle cx="8" cy="8" r="1.6" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
      <path
        d="M2.2 8s2.1-4 5.8-4c.7 0 1.4.15 2 .42M13.8 8s-2.1 4-5.8 4c-.7 0-1.4-.15-2-.42"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="8" cy="8" r="1.6" stroke="currentColor" strokeWidth="1.2" />
      <path
        d="M3 3.5 13 12.5"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
    </svg>
  );
}
