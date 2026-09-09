from django.db import migrations, models


def rename_copy_trade_strategy(apps, schema_editor):
    Strategy = apps.get_model("trading", "Strategy")
    Strategy.objects.filter(slug="copy-trade", name="Copy Trade from X").update(
        name="Copy Trade"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0009_research_config_inputs"),
    ]

    operations = [
        migrations.AddField(
            model_name="strategy",
            name="signal_source",
            field=models.CharField(
                blank=True,
                default="x",
                help_text="Where copy-trade signals are pulled from. Ignored for other strategy types.",
                max_length=32,
            ),
        ),
        migrations.RunPython(rename_copy_trade_strategy, migrations.RunPython.noop),
    ]
