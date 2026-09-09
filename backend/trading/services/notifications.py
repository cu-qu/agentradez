from trading.models import Notification


def notify(
    user,
    kind,
    title,
    body="",
    trade=None,
    signal=None,
    broker_account_id="",
    decision=None,
) -> Notification:
    account_id = (broker_account_id or "").strip()
    if not account_id and trade is not None:
        account_id = (getattr(trade, "broker_account_id", None) or "").strip()
    return Notification.objects.create(
        user=user,
        kind=kind,
        title=title,
        body=body,
        trade=trade,
        signal=signal,
        decision=decision,
        broker_account_id=account_id,
    )
