"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useQueryClient } from "@tanstack/react-query";

import { api, refreshSession } from "@/lib/api/client";
import type { RegisterResponse, TokenPair, User } from "@/lib/api/types";
import { queryKeys } from "@/lib/api/hooks";
import { clearSession, getRefreshToken, setSession } from "@/lib/auth/store";

type Status = "loading" | "authenticated" | "anonymous";

type AuthContextValue = {
  status: Status;
  user: User | null;
  login: (username: string, password: string) => Promise<void>;
  register: (input: {
    username: string;
    email: string;
    password: string;
  }) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<User | null>(null);

  const loadUser = useCallback(async () => {
    const me = await api.get<User>("/api/auth/me/");
    setUser(me);
    queryClient.setQueryData(queryKeys.me, me);
    setStatus("authenticated");
  }, [queryClient]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!getRefreshToken()) {
        if (!cancelled) setStatus("anonymous");
        return;
      }
      const ok = await refreshSession();
      if (cancelled) return;
      if (!ok) {
        setStatus("anonymous");
        return;
      }
      try {
        await loadUser();
      } catch {
        clearSession();
        if (!cancelled) {
          setUser(null);
          setStatus("anonymous");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadUser]);

  const login = useCallback(
    async (username: string, password: string) => {
      const tokens = await api.post<TokenPair>("/api/auth/token/", {
        username,
        password,
      });
      setSession(tokens.access, tokens.refresh);
      await loadUser();
    },
    [loadUser],
  );

  const register = useCallback(
    async (input: { username: string; email: string; password: string }) => {
      const data = await api.post<RegisterResponse>("/api/auth/register/", input);
      setSession(data.access, data.refresh);
      setUser(data.user);
      queryClient.setQueryData(queryKeys.me, data.user);
      setStatus("authenticated");
    },
    [queryClient],
  );

  const logout = useCallback(() => {
    clearSession();
    setUser(null);
    setStatus("anonymous");
    queryClient.clear();
  }, [queryClient]);

  const value = useMemo(
    () => ({
      status,
      user,
      login,
      register,
      logout,
      refreshUser: loadUser,
    }),
    [status, user, login, register, logout, loadUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
