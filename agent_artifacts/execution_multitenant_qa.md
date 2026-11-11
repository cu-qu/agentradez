# QA plan — Multi-tenant execution MCP

## Product positioning checks

- [ ] MCP `tools/list` descriptions state **execution only** (no advice, sizing, or signal generation)
- [ ] Settings UI “AI agent (MCP) execution” copy matches pure-execution positioning
- [ ] `execution/README.md` separates harness from copy-trade/research strategies

## Automated

- [ ] `python manage.py test execution` (includes `tests_tenant.py`)

## Auth & isolation

- [ ] User A PAT cannot read user B `status` / `list_accounts`
- [ ] `ingest_signal` rejects unknown `account_slug` for other users
- [ ] Read-only token (`execution:read` only) cannot `ingest_signal`
- [ ] Revoked PAT returns 401

## User flows

- [ ] `POST /api/execution/agent-tokens/` → copy `agz_pat_...` once
- [ ] MCP `ingest_signal` with user caps + dry-run → journal entry
- [ ] `POST /api/execution/connect/kalshi/` stores encrypted creds (never in MCP response)
- [ ] OAuth: register client → approve → token → MCP call

## Compliance review (Cuyler / counsel)

- [ ] Customer-facing terms describe Agentradez as **non-advisory execution** of user/agent instructions
- [ ] Broker ToS (Robinhood, Kalshi, Coinbase) reviewed for API/automated trading
- [ ] No harness marketing implies Agentradez “picks trades” or replaces the user’s agent
