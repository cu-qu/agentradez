"use client";

import { useCallback, useState } from "react";

import { apiFetch } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/provider";
import { Banner, Button, Card, Spinner } from "@/components/ui";

type AgentToken = {
  id: number;
  label: string;
  token_prefix: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
};

export function ExecutionAgentsPanel() {
  const { token } = useAuth();
  const [tokens, setTokens] = useState<AgentToken[]>([]);
  const [loading, setLoading] = useState(false);
  const [label, setLabel] = useState("My AI agent");
  const [minted, setMinted] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const rows = await apiFetch<AgentToken[]>("/api/execution/agent-tokens/", { token });
      setTokens(rows);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [token]);

  async function createToken() {
    if (!token) return;
    setError("");
    setMinted(null);
    try {
      const res = await apiFetch<{ token: string; agent_token: AgentToken; mcp_url: string }>(
        "/api/execution/agent-tokens/",
        { method: "POST", token, body: { label, scopes: ["execution:read", "execution:trade"] } }
      );
      setMinted(res.token);
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  async function revoke(id: number) {
    if (!token) return;
    await apiFetch(`/api/execution/agent-tokens/${id}/revoke/`, { method: "POST", token });
    await load();
  }

  return (
    <Card className="mt-6 space-y-3">
      <h2 className="text-lg font-semibold">AI agent (MCP) execution</h2>
      <p className="text-sm text-muted-foreground">
        Connect your own AI agent (Grok, Claude, ChatGPT, Cursor, etc.) to execute <strong>your</strong> trade
        instructions on <strong>your</strong> linked brokerage. Agentradez only places and manages limit orders
        from rules your agent sends — it does not pick trades, size positions, or give advice. Tokens are scoped
        to your account only.
      </p>
      {error ? <Banner tone="error">{error}</Banner> : null}
      {minted ? (
        <Banner tone="success">
          Copy this token now — it will not be shown again: <code className="break-all">{minted}</code>
        </Banner>
      ) : null}
      <div className="flex flex-wrap gap-2 items-end">
        <label className="text-sm">
          Label
          <input
            className="mt-1 block rounded border px-2 py-1"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
        </label>
        <Button type="button" onClick={() => void createToken()}>
          Create token
        </Button>
        <Button type="button" variant="secondary" onClick={() => void load()}>
          Refresh list
        </Button>
      </div>
      {loading ? <Spinner /> : null}
      <ul className="text-sm space-y-2">
        {tokens.map((row) => (
          <li key={row.id} className="flex justify-between gap-2 border-b pb-2">
            <span>
              {row.label} ({row.token_prefix}…) — {row.scopes.join(", ")}
              {row.last_used_at ? ` · last used ${row.last_used_at}` : ""}
            </span>
            <Button type="button" variant="secondary" onClick={() => void revoke(row.id)}>
              Revoke
            </Button>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">
        MCP URL: POST /api/mcp/execution/ with header Authorization: Bearer &lt;token&gt;. OAuth consent:
        /api/execution/oauth/authorize/ (see API docs).
      </p>
    </Card>
  );
}
