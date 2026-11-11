# QA plan — Kalshi & Coinbase harness adapters

## Automated

- [ ] `python manage.py test execution` (includes `tests_kalshi_coinbase.py` mocked HTTP)

## Kalshi (demo)

- [ ] Set `KALSHI_API_KEY_ID`, `KALSHI_PRIVATE_KEY_PEM`, `KALSHI_USE_DEMO=true`
- [ ] Admin: `BrokerConnection.broker=kalshi`, execution account slug `prop-kalshi`, `dry_run=true`
- [ ] MCP `list_accounts` shows buying power
- [ ] Ingest Kalshi sample signal; beat opens dry-run position
- [ ] Live: only after `EXECUTION_DRY_RUN_DEFAULT=false` and account `dry_run=false` on demo

## Coinbase (spot)

- [ ] Set `COINBASE_ADVANCED_API_KEY_NAME`, `COINBASE_ADVANCED_API_PRIVATE_KEY_PEM` (ES256, not Ed25519)
- [ ] Admin: `broker=coinbase`, slug `prop-coinbase`, `dry_run=true`
- [ ] MCP `list_accounts` / status with `market=coinbase` ingest
- [ ] Verify limit order preview on sandbox/small size before live

## Regression

- [ ] Options/Robinhood harness path unchanged (`market=options`)
