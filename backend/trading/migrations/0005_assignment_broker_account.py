from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0004_strategy_visibility_and_user_groups"),
    ]

    operations = [
        migrations.AddField(
            model_name="userstrategyassignment",
            name="broker_account_id",
            field=models.CharField(
                blank=True,
                help_text="Brokerage account this strategy runs on. Empty means the connection default.",
                max_length=128,
            ),
        ),
    ]
