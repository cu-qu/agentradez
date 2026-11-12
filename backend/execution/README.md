# Execution harness MCP (Prop Desk watcher)

Non-LLM rule loop for AI-harness signals: the harness **only ingests intent** via MCP; Celery evaluates entries/exits every minute with **no LLM calls**.

## Endpoint

| | |
|---|---|
| URL | `POST {PUBLIC_API_URL}/api/mcp/execution/` |
| Auth | `Authorization: Bearer $EXECUTION_MCP_BEARER_TOKEN` |
| Protocol | JSON-RPC 2.0 (`initialize`, `tools/list`, `tools/call`) |

Bearer token is required; if `EXECUTION_MCP_BEARER_TOKEN` is unset, all requests are rejected.

## Tools

### `list_accounts`

Returns execution desk accounts linked to `BrokerConnection` rows (slug, broker, buying power, option level, `dry_run`).

### `ingest_signal`

Idempotent on `ref_id`. Required: `ref_id`, `account_slug`, `symbol`. Options fields: `option_type`, `strike`, `expiration`. Sizing: `size`. Risk: `stop`, `stop_loss_pct`, `targets[]`, `expiry`, `time_exit_at`.

### `set_levels`

Update `stop` / `targets` / `entry_rule` / `time_exit_at` for an existing `ref_id` (also updates an open harness position).

### `cancel_signal`

Cancel a pending/working signal by `ref_id`.

### `status`

Snapshot of open signals, positions, working orders, last ticks, and recent journal actions (optional `account_slug` filter).

## Sample signal payload

```json
{
  "ref_id": "prop-desk-aapl-2026-04-04-001",
  "account_slug": "prop-desk",
  "market": "options",
  "symbol": "AAPL",
  "option_type": "call",
  "strike": "220",
  "expiration": "2026-04-17",
  "side": "buy",
  "entry_rule": { "type": "limit", "price": "1.35" },
  "stop": "0.90",
  "targets": [
    { "price": "2.00", "quantity": 1 },
    { "price": "2.75", "pct_of_position": 50 }
  ],
  "size": 2,
  "expiry": "2026-04-04T21:00:00Z",
  "notes": "Kalshi Book K follow-on"
}
```

## Environment variables

| Variable | Purpose |
|---|---|
| `EXECUTION_MCP_BEARER_TOKEN` | MCP HTTP bearer auth (required in prod) |
| `EXECUTION_DRY_RUN_DEFAULT` | Global dry-run latch (`true` default). Live orders need this `false` **and** `ExecutionAccount.dry_run=false` |
| `EXECUTION_RULES_INTERVAL_SECONDS` | Celery beat interval for `execution.evaluate_harness_rules` (default `60`) |

Robinhood live execution still uses existing OAuth secrets (`ROBINHOOD_CLIENT_ID`, tokens on `BrokerConnection`). Never log or return credentials from MCP tools.

## Setup

1. Create a `BrokerConnection` for the desk user (Alpaca stub or Robinhood OAuth).
2. In Django admin, create an **Execution account** with slug (e.g. `prop-desk`), link the connection, set caps and `dry_run`.
3. Ensure **celery-beat** runs `evaluate-harness-rules` (included in `config/celery.py`).

## Docker / Hetzner

No new image: the harness rides in `agentradez-api` and `celery` / `celery-beat` services. Set env vars on those containers in `cuqulabs-core-services` compose.

## QA

1. `python manage.py test execution`
2. `curl -H "Authorization: Bearer $TOKEN" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' $API/api/mcp/execution/`
3. Ingest sample signal; confirm journal + beat opens position in dry-run
4. Flip `dry_run` off only in a paper account after caps review
