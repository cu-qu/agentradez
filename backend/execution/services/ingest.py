"""Idempotent signal ingest and level updates."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from execution.constants import (
    MARKET_OPTIONS,
    SIGNAL_CANCELLED,
    SIGNAL_PENDING,
)
from execution.models import ExecutionAccount, HarnessPosition, HarnessSignal
from execution.services.caps import CapViolation, check_caps, check_stop_within_max_loss
from execution.services.journal import journal


class IngestError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _parse_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise IngestError("invalid_decimal", str(exc)) from exc


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        if timezone.is_naive(value):
            return timezone.make_aware(value, timezone.get_current_timezone())
        return value
    parsed = parse_datetime(str(value))
    if parsed is None:
        raise IngestError("invalid_datetime", f"Could not parse datetime: {value}")
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _resolve_account(account_slug: str | None, account_id: int | None) -> ExecutionAccount:
    if account_slug:
        try:
            return ExecutionAccount.objects.select_related("broker_connection").get(
                slug=account_slug, is_enabled=True
            )
        except ExecutionAccount.DoesNotExist as exc:
            raise IngestError("unknown_account", f"Unknown execution account: {account_slug}") from exc
    if account_id:
        try:
            return ExecutionAccount.objects.select_related("broker_connection").get(
                pk=account_id, is_enabled=True
            )
        except ExecutionAccount.DoesNotExist as exc:
            raise IngestError("unknown_account", f"Unknown execution account id: {account_id}") from exc
    raise IngestError("account_required", "Provide account_slug or account_id.")


def ingest_signal(payload: dict) -> dict:
    ref_id = (payload.get("ref_id") or "").strip()
    if not ref_id:
        raise IngestError("ref_id_required", "ref_id is required.")

    existing = HarnessSignal.objects.filter(ref_id=ref_id).first()
    if existing:
        return {"ref_id": ref_id, "signal_id": existing.pk, "status": existing.status, "idempotent": True}

    account = _resolve_account(payload.get("account_slug"), payload.get("account_id"))
    market = (payload.get("market") or MARKET_OPTIONS).lower()
    symbol = (payload.get("symbol") or payload.get("ticker") or "").upper().strip()
    if not symbol:
        raise IngestError("symbol_required", "symbol/ticker is required.")

    entry_rule = payload.get("entry_rule") or {}
    if not entry_rule.get("type"):
        entry_rule = {"type": "limit", "price": entry_rule.get("price") or payload.get("entry_price")}
    entry_price = _parse_decimal(entry_rule.get("price"))
    stop_price = _parse_decimal(payload.get("stop") or payload.get("stop_price"))
    stop_loss_pct = _parse_decimal(payload.get("stop_loss_pct"))
    quantity = int(payload.get("size") or payload.get("quantity") or 1)
    if quantity < 1:
        raise IngestError("invalid_quantity", "size must be >= 1.")

    try:
        check_caps(
            account,
            market=market,
            additional_contracts=1,
            entry_limit_price=entry_price,
            quantity=quantity,
        )
        if entry_price is not None and stop_price is not None:
            check_stop_within_max_loss(
                account, entry_price, stop_price, quantity, market=market
            )
    except CapViolation as exc:
        raise IngestError(exc.code, str(exc)) from exc

    option_type = (payload.get("option_type") or "").lower()
    strike = _parse_decimal(payload.get("strike"))
    expiration = payload.get("expiration")
    if expiration and not isinstance(expiration, datetime):
        from datetime import date as date_cls

        if isinstance(expiration, str):
            expiration = date_cls.fromisoformat(expiration[:10])

    with transaction.atomic():
        signal = HarnessSignal.objects.create(
            ref_id=ref_id,
            execution_account=account,
            market=market,
            symbol=symbol,
            side=(payload.get("side") or "buy").lower(),
            option_type=option_type,
            strike=strike,
            expiration=expiration,
            entry_rule=entry_rule,
            stop_price=stop_price,
            stop_loss_pct=stop_loss_pct,
            targets=payload.get("targets") or [],
            quantity=quantity,
            signal_expires_at=_parse_dt(payload.get("expiry") or payload.get("signal_expires_at")),
            time_exit_at=_parse_dt(payload.get("time_exit_at")),
            notes=(payload.get("notes") or "")[:2000],
            status=SIGNAL_PENDING,
        )
        journal(
            "signal_ingested",
            execution_account=account,
            signal=signal,
            detail={"ref_id": ref_id, "dry_run": account.dry_run},
        )

    return {
        "ref_id": ref_id,
        "signal_id": signal.pk,
        "status": signal.status,
        "idempotent": False,
        "dry_run": account.dry_run,
    }


def set_levels(payload: dict) -> dict:
    ref_id = (payload.get("ref_id") or "").strip()
    if not ref_id:
        raise IngestError("ref_id_required", "ref_id is required.")
    signal = HarnessSignal.objects.filter(ref_id=ref_id).first()
    if signal is None:
        raise IngestError("not_found", f"No signal for ref_id={ref_id}")

    updated: list[str] = []
    if "stop" in payload or "stop_price" in payload:
        stop = _parse_decimal(payload.get("stop") or payload.get("stop_price"))
        signal.stop_price = stop
        updated.append("stop_price")
    if "targets" in payload:
        signal.targets = payload["targets"] or []
        updated.append("targets")
    if "entry_rule" in payload:
        signal.entry_rule = payload["entry_rule"] or {}
        updated.append("entry_rule")
    if "time_exit_at" in payload:
        signal.time_exit_at = _parse_dt(payload.get("time_exit_at"))
        updated.append("time_exit_at")
    if updated:
        signal.save(update_fields=updated + ["updated_at"])

    position = HarnessPosition.objects.filter(signal=signal).first()
    if position:
        pos_fields: list[str] = []
        if "stop" in payload or "stop_price" in payload:
            position.stop_price = signal.stop_price
            pos_fields.append("stop_price")
        if "targets" in payload:
            position.targets = signal.targets
            pos_fields.append("targets")
        if pos_fields:
            position.save(update_fields=pos_fields + ["updated_at"])

    journal(
        "levels_updated",
        execution_account=signal.execution_account,
        signal=signal,
        detail={"fields": updated},
    )
    return {"ref_id": ref_id, "updated": updated, "status": signal.status}


def cancel_signal(payload: dict) -> dict:
    ref_id = (payload.get("ref_id") or "").strip()
    if not ref_id:
        raise IngestError("ref_id_required", "ref_id is required.")
    signal = HarnessSignal.objects.filter(ref_id=ref_id).first()
    if signal is None:
        raise IngestError("not_found", f"No signal for ref_id={ref_id}")
    if signal.status in (SIGNAL_CANCELLED,):
        return {"ref_id": ref_id, "status": signal.status, "idempotent": True}
    signal.status = SIGNAL_CANCELLED
    signal.save(update_fields=["status", "updated_at"])
    journal(
        "signal_cancelled",
        execution_account=signal.execution_account,
        signal=signal,
        detail={"reason": payload.get("reason", "")},
    )
    return {"ref_id": ref_id, "status": signal.status, "idempotent": False}
