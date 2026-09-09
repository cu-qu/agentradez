from __future__ import annotations

from decimal import Decimal, InvalidOperation

from trading.constants import CONTRACT_MULTIPLIER
from trading.models import Decision, Notification, Signal, SignalDecision
from trading.services.notifications import notify
from trading.services.tier_rules import (
    SIZE_MODE_CASH_CAPPED,
    SIZE_MODE_MINIMUM_CONTRACT,
    snapshot_tier,
)


def _dec(value, default=None) -> Decimal | None:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _num(value, places=2) -> str:
    number = _dec(value)
    if number is None:
        return "—"
    quantized = number.quantize(Decimal("1").scaleb(-places))
    text = format(quantized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _pct(value) -> str:
    return f"{_num(value, 2)}%"


def _money(value) -> str:
    number = _dec(value)
    if number is None:
        return "—"
    return f"${_num(number, 2)}"


def contract_label(ticker="", option_type="", strike=None, expiration=None) -> str:
    parts = [str(ticker or "").upper()]
    if option_type:
        parts.append(str(option_type).upper())
    if strike not in (None, ""):
        parts.append(_num(strike, 2))
    if expiration:
        parts.append(str(expiration))
    return " ".join(part for part in parts if part).strip()


def signal_source_excerpt(signal: Signal | None) -> str:
    if signal is None:
        return ""
    post = getattr(signal, "ingested_post", None)
    if post is not None and getattr(post, "text", ""):
        return post.text[:240]
    event = getattr(signal, "research_event", None)
    if event is not None and getattr(event, "headline", ""):
        return event.headline[:240]
    return (signal.notes or signal.source or "")[:240]


def entry_context(
    *,
    signal: Signal,
    assignment,
    quote=None,
    equity=None,
    buying_power=None,
    open_count=None,
    state=None,
    quantity=None,
    extra=None,
) -> dict:
    tier = assignment.investment_tier
    suggested = _dec(signal.suggested_entry_price)
    live = _dec(quote)
    slippage = None
    if suggested is not None and live is not None and suggested > 0:
        slippage = (live - suggested) / suggested * Decimal("100")
    daily_pnl = None
    if state is not None:
        daily_pnl = getattr(state, "daily_realized_pnl", None)
    payload = {
        "strategy_name": assignment.strategy.name,
        "strategy_slug": assignment.strategy.slug,
        "tier_name": tier.name,
        "tier_slug": tier.slug,
        "signal_code": signal.code or "",
        "suggested_entry_price": str(suggested) if suggested is not None else "",
        "live_price": str(live) if live is not None else "",
        "slippage_pct": str(slippage) if slippage is not None else "",
        "max_entry_slippage_pct": str(tier.max_entry_slippage_pct),
        "equity": str(equity) if equity is not None else "",
        "buying_power": str(buying_power) if buying_power is not None else "",
        "open_positions": open_count,
        "max_open_positions": tier.max_open_positions,
        "quantity": quantity,
        "max_risk_per_trade_pct": str(tier.max_risk_per_trade_pct),
        "hard_stop_pct": str(tier.hard_stop_pct),
        "daily_loss_limit_pct": str(tier.daily_loss_limit_pct),
        "daily_pnl": str(daily_pnl) if daily_pnl is not None else "",
        "source_excerpt": signal_source_excerpt(signal),
        "tier_rules": snapshot_tier(tier),
    }
    if extra:
        payload.update(extra)
    return payload


def summarize_entry(outcome: str, skip_reason: str, context: dict) -> tuple[str, str]:
    contract = contract_label(
        context.get("ticker") or "",
        context.get("option_type") or "",
        context.get("strike"),
        context.get("expiration"),
    ) or context.get("signal_code") or "this signal"
    tier = context.get("tier_name") or "your investment tier"
    strategy = context.get("strategy_name") or "the strategy"
    if outcome == SignalDecision.Outcome.ENTERED:
        qty = context.get("quantity") or 0
        price = _num(context.get("fill_price") or context.get("live_price") or context.get("limit_price"))
        available = context.get("buying_power") or context.get("equity") or 0
        size_mode = context.get("size_mode") or ""
        if context.get("awaiting_fill"):
            title = f"Placed {context.get('ticker') or contract}"
            summary = (
                f"Acted. Limit buy for {qty} {contract} at {price} was placed "
                f"and is waiting to fill."
            )
            return title[:128], summary
        title = f"Entered {context.get('ticker') or contract}"
        if size_mode == SIZE_MODE_MINIMUM_CONTRACT:
            summary = (
                f"Acted. {tier} entered {qty} {contract} at {price}. "
                f"Starter size: 1 contract because {_pct(context.get('max_risk_per_trade_pct'))} of "
                f"{_money(context.get('equity') or 0)} is below one contract. "
                f"Premium cost {_money(context.get('contract_cost'))} of {_money(available)} available."
            )
        elif size_mode == SIZE_MODE_CASH_CAPPED:
            summary = (
                f"Acted. {tier} entered {qty} {contract} at {price}. "
                f"{_pct(context.get('max_risk_per_trade_pct'))} of {_money(context.get('equity') or 0)} "
                f"would be {context.get('risk_quantity') or 0} contracts; "
                f"buying power allowed {qty}."
            )
        else:
            summary = (
                f"Acted. {tier} entered {qty} {contract} at {price}. "
                f"Size used { _pct(context.get('max_risk_per_trade_pct')) } of "
                f"{_money(context.get('equity') or 0)} equity with a "
                f"{_pct(context.get('hard_stop_pct'))} hard stop."
            )
        return title[:128], summary

    title = f"Passed {context.get('ticker') or contract}"
    if skip_reason == SignalDecision.SkipReason.NO_BROKER:
        if context.get("trading_off"):
            summary = (
                f"Passed. Trading is off for the account {strategy} is assigned to, "
                f"so {contract} was not opened."
            )
        else:
            summary = (
                f"Passed. No brokerage account is connected, so {strategy} "
                f"could not place {contract}."
            )
    elif skip_reason == SignalDecision.SkipReason.PAUSED:
        summary = (
            f"Passed. {tier} already paused new entries after the daily loss limit, "
            f"so {contract} was not opened."
        )
    elif skip_reason == SignalDecision.SkipReason.DAILY_LOSS_LIMIT:
        summary = (
            f"Passed. Daily P&L of {_money(context.get('daily_pnl'))} reached "
            f"{tier}'s {_pct(context.get('daily_loss_limit_pct'))} daily loss limit "
            f"on {_money(context.get('equity'))} equity, so {contract} was not opened."
        )
    elif skip_reason == SignalDecision.SkipReason.MAX_OPEN_POSITIONS:
        summary = (
            f"Passed. You already have {context.get('open_positions')}/"
            f"{context.get('max_open_positions')} open positions, which is {tier}'s cap, "
            f"so {contract} was not opened."
        )
    elif skip_reason == SignalDecision.SkipReason.SLIPPAGE:
        summary = (
            f"Passed. Live price {_num(context.get('live_price'))} is "
            f"{_pct(context.get('slippage_pct'))} above the signal price of "
            f"{_num(context.get('suggested_entry_price'))}. {tier} skips entries above "
            f"{_pct(context.get('max_entry_slippage_pct'))} slippage."
        )
    elif skip_reason == SignalDecision.SkipReason.SIZE_ZERO:
        available = context.get("buying_power") or context.get("equity")
        cost = context.get("contract_cost")
        if not cost:
            live = _dec(context.get("live_price"))
            if live is not None:
                cost = live * CONTRACT_MULTIPLIER
        summary = (
            f"Passed. One {contract} at {_num(context.get('live_price'))} costs "
            f"{_money(cost)}, which is more than {_money(available)} available, "
            f"so {contract} was not opened."
        )
    elif skip_reason == SignalDecision.SkipReason.BROKER_ERROR:
        notes = context.get("notes") or "the broker returned an error"
        summary = f"Passed. The broker could not open {contract}: {notes}."
    elif skip_reason == SignalDecision.SkipReason.UNFILLED:
        qty = context.get("quantity") or 0
        summary = (
            f"Passed. The buy order for {qty} {contract} at "
            f"{_num(context.get('live_price') or context.get('limit_price'))} "
            f"was accepted but never filled."
        )
    elif skip_reason == SignalDecision.SkipReason.WRONG_ACCOUNT:
        summary = (
            f"Passed. {strategy} is assigned to a different brokerage account, "
            f"so {contract} was not opened."
        )
    elif skip_reason == SignalDecision.SkipReason.SUBSCRIPTION_REQUIRED:
        summary = (
            f"Passed. An active paid subscription is required, so {strategy} "
            f"did not open {contract}."
        )
    else:
        summary = f"Passed. {strategy} did not open {contract}."
    return title[:128], summary


def summarize_exit(reason: str, context: dict) -> tuple[str, str]:
    ticker = context.get("ticker") or ""
    contract = contract_label(
        ticker,
        context.get("option_type") or "",
        context.get("strike"),
        context.get("expiration"),
    ) or ticker or "the position"
    tier = context.get("tier_name") or "your investment tier"
    qty = context.get("quantity") or 0
    price = _num(context.get("fill_price") or context.get("price"))
    pnl = context.get("realized_pnl")
    pnl_bit = f" (P&L {_money(pnl)})" if pnl not in (None, "") else ""
    if reason == "take_profit":
        title = f"Took profit on {ticker or contract}"
        summary = (
            f"Acted. {tier} take-profit {int(context.get('tp_stage') or 0) + 1} sells "
            f"{_pct(context.get('pct_of_position'))} of the position at "
            f"+{_pct(context.get('trigger_gain_pct'))}. Sold {qty} {contract} at "
            f"{price} ({_pct(context.get('gain_pct'))}{pnl_bit})."
        )
    elif reason == "stop_loss":
        title = f"Stopped out of {ticker or contract}"
        summary = (
            f"Acted. {tier} hard stop is -{_pct(context.get('hard_stop_pct'))}. "
            f"Sold remaining {qty} {contract} at {price} "
            f"({_pct(context.get('gain_pct'))}{pnl_bit})."
        )
    elif reason == "time_exit":
        title = f"Time exit {ticker or contract}"
        summary = (
            f"Acted. {tier} max hold is {context.get('max_hold_trading_days') or '—'} "
            f"trading days. Sold remaining {qty} {contract} at {price}{pnl_bit}."
        )
    elif reason == "expiration_exit":
        title = f"Expiration exit {ticker or contract}"
        time_et = context.get("force_exit_time_et") or "15:45"
        summary = (
            f"Acted. {tier} force-exits on expiration day at {time_et} ET. "
            f"Sold remaining {qty} {contract} at {price}{pnl_bit}."
        )
    else:
        title = f"Exited {ticker or contract}"
        summary = f"Acted. Sold {qty} {contract} at {price}{pnl_bit}."
    return title[:128], summary


def summarize_daily_pause(context: dict) -> tuple[str, str]:
    tier = context.get("tier_name") or "your investment tier"
    title = "Daily loss limit reached"
    summary = (
        f"Acted. Daily P&L of {_money(context.get('daily_pnl'))} reached "
        f"{tier}'s {_pct(context.get('daily_loss_limit_pct'))} loss limit on "
        f"{_money(context.get('equity'))} equity. New entries are paused until the next session."
    )
    return title, summary


def _notification_kind(action: str, outcome: str) -> str:
    if action == Decision.Action.ENTER:
        return Notification.Kind.ENTRY
    if action == Decision.Action.SKIP:
        return Notification.Kind.SKIP
    if action == Decision.Action.TAKE_PROFIT:
        return Notification.Kind.TAKE_PROFIT
    if action == Decision.Action.STOP_LOSS:
        return Notification.Kind.STOP_LOSS
    if action == Decision.Action.DAILY_PAUSE:
        return Notification.Kind.DAILY_PAUSE
    if outcome == Decision.Outcome.PASSED:
        return Notification.Kind.SKIP
    return Notification.Kind.EXIT


def _reason_for_skip(skip_reason: str) -> str:
    mapping = {
        SignalDecision.SkipReason.NO_BROKER: Decision.Reason.NO_BROKER,
        SignalDecision.SkipReason.PAUSED: Decision.Reason.PAUSED,
        SignalDecision.SkipReason.DAILY_LOSS_LIMIT: Decision.Reason.DAILY_LOSS_LIMIT,
        SignalDecision.SkipReason.MAX_OPEN_POSITIONS: Decision.Reason.MAX_OPEN_POSITIONS,
        SignalDecision.SkipReason.SLIPPAGE: Decision.Reason.SLIPPAGE,
        SignalDecision.SkipReason.SIZE_ZERO: Decision.Reason.SIZE_ZERO,
        SignalDecision.SkipReason.BROKER_ERROR: Decision.Reason.BROKER_ERROR,
        SignalDecision.SkipReason.UNFILLED: Decision.Reason.UNFILLED,
        SignalDecision.SkipReason.WRONG_ACCOUNT: Decision.Reason.WRONG_ACCOUNT,
        SignalDecision.SkipReason.SUBSCRIPTION_REQUIRED: Decision.Reason.SUBSCRIPTION_REQUIRED,
    }
    return mapping.get(skip_reason, "")


def record_activity(
    *,
    user,
    action: str,
    outcome: str,
    title: str,
    summary: str,
    reason_code: str = "",
    strategy=None,
    investment_tier=None,
    signal=None,
    signal_decision=None,
    trade=None,
    trade_event=None,
    context=None,
    ticker="",
    option_type="",
    strike=None,
    expiration=None,
    quantity=None,
    price=None,
    broker_account_id="",
    notify_user: bool = True,
) -> Decision:
    existing = None
    if signal_decision is not None:
        existing = Decision.objects.filter(signal_decision=signal_decision).first()
    if existing:
        return existing

    account_id = (broker_account_id or "").strip()
    if not account_id and trade is not None:
        account_id = (getattr(trade, "broker_account_id", None) or "").strip()
    if signal is not None:
        ticker = ticker or signal.ticker
        option_type = option_type or signal.option_type
        strike = strike if strike is not None else signal.strike
        expiration = expiration if expiration is not None else signal.expiration
        strategy = strategy or signal.strategy
    if trade is not None:
        ticker = ticker or trade.ticker
        option_type = option_type or trade.option_type
        strike = strike if strike is not None else trade.strike
        expiration = expiration if expiration is not None else trade.expiration
        strategy = strategy or trade.strategy
        investment_tier = investment_tier or trade.investment_tier

    payload = dict(context or {})
    payload.setdefault("ticker", ticker)
    payload.setdefault("option_type", option_type)
    payload.setdefault("strike", str(strike) if strike is not None else "")
    payload.setdefault("expiration", str(expiration) if expiration else "")

    decision = Decision.objects.create(
        user=user,
        strategy=strategy,
        investment_tier=investment_tier,
        signal=signal,
        signal_decision=signal_decision,
        trade=trade,
        trade_event=trade_event,
        action=action,
        outcome=outcome,
        reason_code=reason_code,
        title=title[:128],
        summary=summary,
        context=payload,
        ticker=ticker or "",
        option_type=option_type or "",
        strike=strike,
        expiration=expiration,
        quantity=quantity,
        price=_dec(price),
        broker_account_id=account_id,
    )
    if notify_user:
        notify(
            user,
            _notification_kind(action, outcome),
            title[:128],
            summary[:255],
            trade=trade,
            signal=signal,
            broker_account_id=account_id,
            decision=decision,
        )
    return decision


def record_signal_activity(signal_decision: SignalDecision, *, signal: Signal, assignment, context=None) -> Decision:
    ctx = dict(context or {})
    ctx.setdefault("ticker", signal.ticker)
    ctx.setdefault("option_type", signal.option_type)
    ctx.setdefault("strike", str(signal.strike))
    ctx.setdefault("expiration", str(signal.expiration))
    title, summary = summarize_entry(
        signal_decision.outcome, signal_decision.skip_reason, ctx
    )
    if signal_decision.outcome == SignalDecision.Outcome.ENTERED:
        action = Decision.Action.ENTER
        outcome = Decision.Outcome.ACTED
        reason = Decision.Reason.TIER_SIZE
    else:
        action = Decision.Action.SKIP
        outcome = Decision.Outcome.PASSED
        reason = _reason_for_skip(signal_decision.skip_reason)
    price = ctx.get("fill_price") or ctx.get("live_price") or ctx.get("limit_price")
    return record_activity(
        user=signal_decision.user,
        action=action,
        outcome=outcome,
        title=title,
        summary=summary,
        reason_code=reason,
        strategy=assignment.strategy,
        investment_tier=assignment.investment_tier,
        signal=signal,
        signal_decision=signal_decision,
        trade=signal_decision.trade,
        context=ctx,
        quantity=ctx.get("quantity"),
        price=price,
        broker_account_id=ctx.get("broker_account_id") or "",
    )


def record_exit_activity(*, trade, trade_event, reason: str, context=None) -> Decision:
    ctx = dict(context or {})
    ctx.setdefault("ticker", trade.ticker)
    ctx.setdefault("option_type", trade.option_type)
    ctx.setdefault("strike", str(trade.strike))
    ctx.setdefault("expiration", str(trade.expiration))
    ctx.setdefault("tier_name", trade.investment_tier.name)
    ctx.setdefault("tier_slug", trade.investment_tier.slug)
    ctx.setdefault("strategy_name", trade.strategy.name)
    title, summary = summarize_exit(reason, ctx)
    action = {
        "take_profit": Decision.Action.TAKE_PROFIT,
        "stop_loss": Decision.Action.STOP_LOSS,
        "time_exit": Decision.Action.TIME_EXIT,
        "force_exit": Decision.Action.FORCE_EXIT,
        "expiration_exit": Decision.Action.EXPIRATION_EXIT,
    }.get(reason, Decision.Action.FORCE_EXIT)
    reason_code = {
        "take_profit": Decision.Reason.TAKE_PROFIT,
        "stop_loss": Decision.Reason.STOP_LOSS,
        "time_exit": Decision.Reason.TIME_EXIT,
        "force_exit": Decision.Reason.FORCE_EXIT,
        "expiration_exit": Decision.Reason.EXPIRATION_EXIT,
    }.get(reason, Decision.Reason.FORCE_EXIT)
    return record_activity(
        user=trade.user,
        action=action,
        outcome=Decision.Outcome.ACTED,
        title=title,
        summary=summary,
        reason_code=reason_code,
        strategy=trade.strategy,
        investment_tier=trade.investment_tier,
        signal=trade.signal,
        trade=trade,
        trade_event=trade_event,
        context=ctx,
        quantity=trade_event.quantity if trade_event else ctx.get("quantity"),
        price=trade_event.price if trade_event else ctx.get("fill_price"),
        broker_account_id=trade.broker_account_id,
    )


def record_daily_pause_activity(*, user, assignment, context=None) -> Decision:
    ctx = dict(context or {})
    ctx.setdefault("tier_name", assignment.investment_tier.name)
    ctx.setdefault("tier_slug", assignment.investment_tier.slug)
    ctx.setdefault("strategy_name", assignment.strategy.name)
    title, summary = summarize_daily_pause(ctx)
    return record_activity(
        user=user,
        action=Decision.Action.DAILY_PAUSE,
        outcome=Decision.Outcome.ACTED,
        title=title,
        summary=summary,
        reason_code=Decision.Reason.DAILY_PAUSE,
        strategy=assignment.strategy,
        investment_tier=assignment.investment_tier,
        context=ctx,
        broker_account_id=(assignment.broker_account_id or "").strip(),
    )
