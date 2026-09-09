from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0006_trade_notification_broker_account"),
    ]

    operations = [
        migrations.AlterField(
            model_name="trade",
            name="status",
            field=models.CharField(
                choices=[
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
                    ("unfilled", "Unfilled"),
                    ("sync_adjust", "Broker sync"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="signaldecision",
            name="skip_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("no_broker", "No brokerage connection"),
                    ("paused", "Daily loss pause"),
                    ("daily_loss_limit", "Daily loss limit"),
                    ("max_open_positions", "Max open positions"),
                    ("slippage", "Entry slippage"),
                    ("size_zero", "Position size rounded to zero"),
                    ("broker_error", "Broker error"),
                    ("unfilled", "Order did not fill"),
                    (
                        "wrong_account",
                        "Strategy is assigned to a different brokerage account",
                    ),
                ],
                max_length=32,
            ),
        ),
    ]
