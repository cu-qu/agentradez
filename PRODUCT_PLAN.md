---
product_name: Agentradez
product_slug: agentradez
product_domain: agentradez.com
setup_web_client: yes
setup_mobile_client: no
stripe_payments: yes
stripe_mode: subscription
one_liner: AI agent trading made easy. Connect your broker, set up your strategies, and Agentradez submits the orders for you.
primary_users: traders connecting Alpaca or Robinhood, staff configuring strategies tiers and copy-trade sources
---

# Product plan

Combined product folder copied from `agentic_trading/agentic_trading_backend` and `agentic_trading/agentic_trading_web`, rebranded to **Agentradez**. Original repos are unchanged.

This is not an empty `new_product_app` scaffold. Domain, APIs, Celery jobs, Stripe billing, and the marketing site already exist.

## Problem and v1 outcome

When v1 ships a user can:

- Open the marketing site, read how it works, browse public strategies, and accept terms.
- Register, sign in, and connect Alpaca (API keys) or Robinhood (OAuth / Agentic Trading MCP).
- Pick one strategy and one investment tier for a connected account.
- Let the agent enter and manage option trades under that tier’s rules.
- Watch positions, trades, decisions, notifications, and lifetime P&L in the app.
- Subscribe (monthly/yearly) to unlock trading, or receive a staff grant.

## Marketing (keep)

| Path | Role |
|---|---|
| `/` | Live homepage |
| `/how-it-works` | Four-step explainer |
| `/strategies` | Public strategy list + copy |
| `/terms` | Terms, risk, marketing licenses |
| `/home-pages`, `/home-page-1`…`/home-page-5` | Homepage drafts for review (noindex) |
| `MarketingShell`, `HomeNav` | Public chrome |

Do not drop these when iterating on the authenticated app.

## Domain models (already in this repo)

Integer PKs only (`BigAutoField`). User FKs point at `settings.AUTH_USER_MODEL`.

Trading: InvestmentTier, UserGroup, Strategy, XAccountSource, IngestedPost, ResearchWatchConfig, WatchedCompany, ResearchEvent, BrokerConnection (soft-delete), UserStrategyAssignment, AccountTradingState, Signal, Trade, TradeEvent, Position, SignalDecision, Decision, BrokerOrder, PerformanceSnapshot, PlatformStats, Notification.

Billing: Feature, Plan, BillingCustomer, Subscription, SubscriptionGrant, StripeEvent.

Auth stays in `accounts` (User, UserProfile).

## API surface (v1)

Prefix under `/api/`. Reuse existing JWT. See `backend/README.md` and `/api/docs/` for the full table (auth, billing, broker, strategies, assignment, positions, trades, decisions, performance, notifications, staff admin).

## Celery

Keep `accounts.ping` if present. Trading jobs stay on queue `"main"` / beat as in `backend/config/celery.py` (signals, X poll, research poll, position monitor, daily/weekly P&L, cleanup).

## Non-goals for this copy

- Do not rewrite accounts migrations or switch to UUID PKs.
- Do not strip auth, Celery, Docker, or Railway.
- Do not replace Robinhood’s **Agentic Trading MCP** product name.
- Do not implement this product back into `agentic_trading_*` or `new_product_app`.
