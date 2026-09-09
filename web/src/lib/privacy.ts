"use client";

import { useCallback, useSyncExternalStore } from "react";

const STORAGE_KEY = "agentic.hideAmounts";
const CHANGE_EVENT = "agentic-hide-amounts";
const ACCOUNT_STORAGE_KEY = "agentic.hiddenAccountBalances";
const ACCOUNT_CHANGE_EVENT = "agentic-hidden-account-balances";

export const HIDDEN_AMOUNT = "$••••";

const EMPTY_HIDDEN_ACCOUNTS: string[] = [];
let hiddenAccountSnapshot = EMPTY_HIDDEN_ACCOUNTS;
let hiddenAccountSnapshotRaw = "";

function readHideAmounts(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(STORAGE_KEY) === "1";
}

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

export function setHideAmounts(hide: boolean) {
  window.localStorage.setItem(STORAGE_KEY, hide ? "1" : "0");
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function useHideAmounts() {
  const hideAmounts = useSyncExternalStore(
    subscribe,
    readHideAmounts,
    () => false,
  );
  const setHide = useCallback((hide: boolean) => {
    setHideAmounts(hide);
  }, []);
  return { hideAmounts, setHideAmounts: setHide };
}

export function accountBalanceKey(connectionId: number, accountNumber: string) {
  return `${connectionId}:${accountNumber}`;
}

function parseHiddenAccounts(raw: string): string[] {
  if (!raw) return EMPTY_HIDDEN_ACCOUNTS;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return EMPTY_HIDDEN_ACCOUNTS;
    const ids = parsed.filter((id): id is string => typeof id === "string");
    return ids.length > 0 ? ids : EMPTY_HIDDEN_ACCOUNTS;
  } catch {
    return EMPTY_HIDDEN_ACCOUNTS;
  }
}

function readHiddenAccounts(): string[] {
  if (typeof window === "undefined") return EMPTY_HIDDEN_ACCOUNTS;
  const raw = window.localStorage.getItem(ACCOUNT_STORAGE_KEY) ?? "";
  if (raw === hiddenAccountSnapshotRaw) return hiddenAccountSnapshot;
  hiddenAccountSnapshotRaw = raw;
  hiddenAccountSnapshot = parseHiddenAccounts(raw);
  return hiddenAccountSnapshot;
}

function subscribeHiddenAccounts(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(ACCOUNT_CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(ACCOUNT_CHANGE_EVENT, onChange);
  };
}

export function setAccountBalanceHidden(key: string, hidden: boolean) {
  const next = new Set(readHiddenAccounts());
  if (hidden) next.add(key);
  else next.delete(key);
  const serialized = JSON.stringify([...next]);
  window.localStorage.setItem(ACCOUNT_STORAGE_KEY, serialized);
  hiddenAccountSnapshotRaw = serialized;
  hiddenAccountSnapshot = parseHiddenAccounts(serialized);
  window.dispatchEvent(new Event(ACCOUNT_CHANGE_EVENT));
}

export function useHiddenAccountBalances() {
  const hidden = useSyncExternalStore(
    subscribeHiddenAccounts,
    readHiddenAccounts,
    () => EMPTY_HIDDEN_ACCOUNTS,
  );
  const isHidden = useCallback(
    (connectionId: number, accountNumber: string) =>
      hidden.includes(accountBalanceKey(connectionId, accountNumber)),
    [hidden],
  );
  const setHidden = useCallback(
    (connectionId: number, accountNumber: string, hide: boolean) => {
      setAccountBalanceHidden(
        accountBalanceKey(connectionId, accountNumber),
        hide,
      );
    },
    [],
  );
  return { isHidden, setHidden };
}
