from django.db import migrations, models


def backfill_broker_account_ids(apps, schema_editor):
    Trade = apps.get_model("trading", "Trade")
    Notification = apps.get_model("trading", "Notification")
    for trade in Trade.objects.select_related("broker_connection").iterator():
        account_id = (trade.broker_account_id or "").strip()
        if not account_id:
            account_id = (trade.broker_connection.broker_account_id or "").strip()
            if account_id:
                trade.broker_account_id = account_id
                trade.save(update_fields=["broker_account_id"])
        if account_id:
            Notification.objects.filter(trade_id=trade.id, broker_account_id="").update(
                broker_account_id=account_id
            )


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0005_assignment_broker_account"),
    ]

    operations = [
        migrations.AddField(
            model_name="trade",
            name="broker_account_id",
            field=models.CharField(blank=True, db_index=True, max_length=128),
        ),
        migrations.AddField(
            model_name="notification",
            name="broker_account_id",
            field=models.CharField(blank=True, db_index=True, max_length=128),
        ),
        migrations.RunPython(backfill_broker_account_ids, migrations.RunPython.noop),
    ]
