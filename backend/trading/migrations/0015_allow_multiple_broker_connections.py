from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0014_broker_kalshi_coinbase"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="brokerconnection",
            name="one_active_broker_connection_per_user",
        ),
    ]
