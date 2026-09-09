import { API_URL } from "@/lib/env";
import {
  clearSession,
  getAccessToken,
  getRefreshToken,
  setAccessToken,
  setSession,
} from "@/lib/auth/store";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    super(messageFromBody(body, status));
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function collectErrorMessages(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (typeof value === "number" || typeof value === "boolean") return [String(value)];
  if (Array.isArray(value)) return value.flatMap(collectErrorMessages);
  if (value && typeof value === "object") {
    return Object.values(value as Record<string, unknown>).flatMap(collectErrorMessages);
  }
  return [];
}

function messageFromBody(body: unknown, status: number): string {
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    if (typeof record.detail === "string") return record.detail;
    if (typeof record.error === "string") return record.error;
    if (Array.isArray(record.non_field_errors)) {
      return record.non_field_errors.map(String).join(" ");
    }
    const fieldMessages = Object.entries(record)
      .filter(([key]) => key !== "detail")
      .flatMap(([, value]) => collectErrorMessages(value))
      .filter(Boolean);
    if (fieldMessages.length) return fieldMessages.join(" ");
  }
  return `Request failed (${status})`;
}

export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || !error.body || typeof error.body !== "object") {
    return {};
  }
  const out: Record<string, string> = {};
  function walk(record: Record<string, unknown>, prefix: string) {
    for (const [key, value] of Object.entries(record)) {
      if (key === "detail" || key === "non_field_errors") continue;
      const path = prefix ? `${prefix}.${key}` : key;
      if (value && typeof value === "object" && !Array.isArray(value)) {
        walk(value as Record<string, unknown>, path);
        continue;
      }
      const message = collectErrorMessages(value).join(" ");
      if (message) out[path] = message;
    }
  }
  walk(error.body as Record<string, unknown>, "");
  return out;
}

type Query = Record<string, string | number | boolean | undefined | null>;

type RequestOptions = {
  method?: string;
  body?: unknown;
  query?: Query;
  auth?: boolean;
  retry?: boolean;
};

function buildUrl(path: string, query?: Query): string {
  const url = new URL(path, API_URL);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value == null || value === "") continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

const AUTH_FREE = [
  "/api/auth/token/",
  "/api/auth/token/refresh/",
  "/api/auth/register/",
  "/api/auth/password-reset/",
  "/api/auth/password-reset/confirm/",
  "/api/auth/verify-email/",
];

function shouldAttachAuth(path: string, auth: boolean): boolean {
  if (!auth) return false;
  return !AUTH_FREE.some((prefix) => path.startsWith(prefix));
}

let refreshInFlight: Promise<boolean> | null = null;

export async function refreshSession(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    const refresh = getRefreshToken();
    if (!refresh) return false;
    const res = await fetch(buildUrl("/api/auth/token/refresh/"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh }),
    });
    if (!res.ok) {
      clearSession();
      return false;
    }
    const data = (await res.json()) as { access: string; refresh?: string };
    if (data.refresh) {
      setSession(data.access, data.refresh);
    } else {
      setAccessToken(data.access);
    }
    return true;
  })();
  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
}

async function parseBody(res: Response): Promise<unknown> {
  const text = await res.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, auth = true, retry = true } = options;
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (shouldAttachAuth(path, auth) && getAccessToken()) {
    headers.Authorization = `Bearer ${getAccessToken()}`;
  }

  const res = await fetch(buildUrl(path, query), {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (res.status === 401 && retry && shouldAttachAuth(path, auth) && getRefreshToken()) {
    const refreshed = await refreshSession();
    if (refreshed) {
      return request<T>(path, { ...options, retry: false });
    }
    clearSession();
  }

  const parsed = await parseBody(res);
  if (!res.ok) {
    throw new ApiError(res.status, parsed);
  }
  return parsed as T;
}

export const api = {
  get<T>(path: string, query?: Query) {
    return request<T>(path, { method: "GET", query });
  },
  post<T>(path: string, body?: unknown) {
    return request<T>(path, { method: "POST", body });
  },
  put<T>(path: string, body?: unknown) {
    return request<T>(path, { method: "PUT", body });
  },
  patch<T>(path: string, body?: unknown) {
    return request<T>(path, { method: "PATCH", body });
  },
  delete<T>(path: string) {
    return request<T>(path, { method: "DELETE" });
  },
};
