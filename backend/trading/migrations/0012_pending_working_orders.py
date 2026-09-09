from django.db import migrations, models


def repair_misclassified_working_orders(apps, schema_editor):
    Trade = apps.get_model("trading", "Trade")
    BrokerOrder = apps.get_model("trading", "BrokerOrder")
    TradeEvent = apps.get_model("trading", "TradeEvent")
    SignalDecision = apps.get_model("trading", "SignalDecision")
    Decision = apps.get_model("trading", "Decision")
    Notification = apps.get_model("trading", "Notification")

    for order in BrokerOrder.objects.filter(status="submitted", side="buy").select_related(
        "trade"
    ):
        trade = order.trade
        if trade.status != "cancelled":
            continue
        trade.status = "pending"
        trade.closed_at = None
        if trade.remaining_quantity == 0:
            trade.remaining_quantity = trade.entry_quantity
        trade.save(update_fields=["status", "closed_at", "remaining_quantity", "updated_at"])
        for event in TradeEvent.objects.filter(trade=trade, event_type="unfilled"):
            event.event_type = "submitted"
            event.quantity = trade.entry_quantity
            event.notes = "Limit order is live at the broker."
            event.save(update_fields=["event_type", "quantity", "notes"])
        for decision in SignalDecision.objects.filter(trade=trade, outcome="skipped"):
            decision.outcome = "entered"
            decision.skip_reason = ""
            decision.notes = "Limit order placed; waiting for fill."
            decision.save(update_fields=["outcome", "skip_reason", "notes"])
            title = f"Placed {trade.ticker}"
            summary = (
                f"Acted. Limit buy for {trade.entry_quantity} {trade.ticker} at "
                f"{trade.entry_price} was placed and is waiting to fill."
            )
            for log in Decision.objects.filter(signal_decision=decision):
                log.action = "enter"
                log.outcome = "acted"
                log.reason_code = "tier_size"
                log.title = title[:128]
                log.summary = summary
                log.save(
                    update_fields=["action", "outcome", "reason_code", "title", "summary"]
                )
                for note in Notification.objects.filter(decision=log):
                    note.kind = "entry"
                    note.title = title[:128]
                    note.body = summary[:255]
                    note.save(update_fields=["kind", "title", "body"])


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0011_decision_paper_trail"),
    ]

    operations = [
        migrations.AlterField(
            model_name="trade",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("open", "Open"),
                    ("partially_closed", "Partially closed"),
                    ("closed", "Closed"),
                    ("cancelled", "Cancelled"),
                ],
                db_index=True,
                default="open",
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name="tradeevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("entry", "Entry"),
                    ("take_profit", "Take profit"),
                    ("stop_loss", "Stop loss"),
                    ("time_exit", "Time exit"),
                    ("force_exit", "Force exit"),
                    ("expiration_exit", "Expiration exit"),
                    ("submitted", "Submitted"),
                    ("unfilled", "Unfilled"),
                    ("sync_adjust", "Broker sync"),
                ],
                max_length=32,
            ),
        ),
        migrations.RunPython(
            repair_misclassified_working_orders, migrations.RunPython.noop
        ),
    ]
