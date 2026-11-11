# QA plan — Execution harness MCP

## Automated

- [ ] `cd backend && DJANGO_SETTINGS_MODULE=config.settings.test python manage.py test execution`

## Local MCP smoke

- [ ] Set `EXECUTION_MCP_BEARER_TOKEN` in `backend/.env`
- [ ] Migrate: `python manage.py migrate`
- [ ] Admin: create `ExecutionAccount` → slug `prop-desk`, link Alpaca/Robinhood connection, `dry_run=true`
- [ ] `tools/list` via POST `/api/mcp/execution/` with bearer header
- [ ] `ingest_signal` with sample payload; verify idempotent second call
- [ ] Wait 60s (or run `evaluate_harness_rules` task) — journal shows `entry_dry_run_filled`
- [ ] `status` returns open position and recent actions

## Caps / safety

- [ ] Ingest over `max_dollar_exposure` → rejected at ingest
- [ ] With `EXECUTION_DRY_RUN_DEFAULT=true`, live Robinhood token does not place orders
- [ ] Set global dry-run off + account dry-run off only on paper stub; confirm limit entry path

## Docker Compose

- [ ] `docker compose up` — beat log shows `evaluate_harness_rules`

## Production (cuqulabs-core-services)

- [ ] Add env vars to API + worker + beat containers
- [ ] Run migrations on deploy
- [ ] Robinhood OAuth: complete on localhost, paste callback to prod API (existing limitation)

## Out of scope (follow-up PR)

- [ ] Kalshi RSA-PSS REST adapter
- [ ] Coinbase Advanced Trade spot adapter
