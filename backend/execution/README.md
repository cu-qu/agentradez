# Execution harness MCP (user-owned agents)

Agentradez is **pure execution** for end users: your own AI agent (Grok, Claude, ChatGPT, Cursor, or any MCP client) sends **your** trade instructions; Agentradez watches the market and works **limit orders** and exits against **your connected brokerage**, within **caps you set**. Agentradez does **not** generate signals, recommend trades, select instruments, size positions, or give investment advice.

The rule loop runs on Celery with **no LLM calls** — only your agent uses an LLM if you choose.

## Product boundary

| In scope (execution harness) | Out of scope |
|------------------------------|--------------|
| Ingest user/agent-supplied entry, stop, target, size, expiry | Strategy pickers, copy-trade, research signals, tier sizing |
| Limit entries and rule-based exits (stop, target, time, expiry) | Agentradez-initiated trade ideas or recommendations |
| Per-user caps, dry-run, journal of fills | Agentradez choosing position size or symbols |

Existing Agentradez **strategies / copy-trade / research** remain separate product flows and are **not** exposed via this MCP.

## Endpoint

| | |
|---|---|
| URL | `POST {PUBLIC_API_URL}/api/mcp/execution/` |
| Auth | Per-user **personal access token** or **OAuth access token** (create/revoke in the web app under Settings → AI agent access) |
| Ops only | Optional `EXECUTION_MCP_ADMIN_BEARER` for platform staff (not end users) |
| Protocol | JSON-RPC 2.0 (`initialize`, `tools/list`, `tools/call`) |
| OAuth metadata | `GET /api/mcp/execution/.well-known/oauth-authorization-server` |

## Tools

### `list_accounts`

Your execution accounts (slug, broker, buying power, option level, `dry_run`). No cross-user data.

### `ingest_signal`

Idempotent on `ref_id` **per user**. You supply all trade fields; Agentradez only validates caps and places limit orders.

### `set_levels` / `cancel_signal` / `status`

Update or cancel **your** instructions; read **your** positions and journal.

## Connect your agent (end user)

1. **Agentradez account** with trading access — connect brokers in Settings (Robinhood OAuth, Kalshi/Coinbase keys via API).
2. Create an **execution account** — `POST /api/execution/accounts/` or auto-created when connecting Kalshi/Coinbase.
3. Set **caps** and keep **dry-run on** until you trust the wiring — `PATCH /api/execution/accounts/{slug}/`.
4. **Create MCP token** — Settings → “AI agent (MCP) access” or `POST /api/execution/agent-tokens/` (scopes: `execution:read`, `execution:trade`).
5. Point your MCP client at `POST {API}/api/mcp/execution/` with `Authorization: Bearer agz_pat_...`.

**OAuth (third-party agents):** register client `POST /api/execution/oauth/clients/`, user approves via `GET/POST /api/execution/oauth/authorize/` + `approve/`, exchange code at `POST /api/execution/oauth/token/` (PKCE).

## Sample instruction payload (from your agent)

```json
{
  "ref_id": "my-agent-aapl-001",
  "account_slug": "main",
  "market": "options",
  "symbol": "AAPL",
  "option_type": "call",
  "strike": "220",
  "expiration": "2026-04-17",
  "side": "buy",
  "entry_rule": { "type": "limit", "price": "1.35" },
  "stop": "0.90",
  "targets": [{ "price": "2.00", "quantity": 1 }],
  "size": 2,
  "expiry": "2026-04-04T21:00:00Z"
}
```

## Environment variables (platform operators)

| Variable | Purpose |
|---|---|
| `EXECUTION_DRY_RUN_DEFAULT` | Global dry-run latch (default `true`) |
| `EXECUTION_RULES_INTERVAL_SECONDS` | Beat interval (default `60`) |
| `EXECUTION_PLATFORM_MAX_*` | Platform ceilings on user caps |
| `EXECUTION_MCP_ADMIN_BEARER` | Ops-only override (not for customers) |

**Per-user broker secrets** live in `BrokerConnection.encrypted_credentials` (Kalshi/Coinbase keys from the app). Optional **dev fallback**: `KALSHI_*` and `COINBASE_ADVANCED_*` env vars on the server.

## Robinhood production OAuth

Robinhood Agentic OAuth today only completes for **loopback** redirect URIs. For ordinary users without localhost paste:

1. Register the production callback with Robinhood:  
   `https://api.agentradez.com/api/broker-connections/robinhood/oauth/callback/`  
   (or your `PUBLIC_API_URL` + that path).
2. Set `ROBINHOOD_OAUTH_REDIRECT_URI` to that **HTTPS** URL and ensure `PUBLIC_API_URL` matches.
3. If Robinhood’s app registration still rejects non-loopback redirects, Cuyler must open a Robinhood developer/support request to allow the production redirect for the Agentic Trading MCP client — until then, users complete OAuth on localhost and paste the callback URL into the app (existing flow).

## Compliance notes (for operators — not legal advice)

- Agentradez acts as a **technical execution layer** on **accounts the user connected**; instructions come from **the user’s agent**, not from Agentradez.
- You are responsible for **disclosures**, **customer agreements**, and whether your service constitutes **investment advice**, **broker-dealer**, or **introducing broker** activity in your jurisdictions.
- **Robinhood / Kalshi / Coinbase** terms may restrict automated or third-party trading; users connect **their own** API keys/OAuth; review each broker’s ToS and API policies.
- **Dry-run defaults** and **user caps** reduce accidental live risk but do not replace regulatory compliance.
- **No custody**: keys/tokens are stored encrypted for execution only; MCP tools do not return secrets.

## QA

1. `python manage.py test execution`
2. PAT auth smoke on `/api/mcp/execution/`
3. Tenant isolation: two users cannot read each other’s `status`

See [agent_artifacts/execution_multitenant_qa.md](../../agent_artifacts/execution_multitenant_qa.md).
