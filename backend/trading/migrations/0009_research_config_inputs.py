from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0008_research_breakthrough"),
    ]

    operations = [
        migrations.AddField(
            model_name="researchwatchconfig",
            name="sectors",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="If set, only poll watched companies in these sectors. Empty means all.",
            ),
        ),
        migrations.AddField(
            model_name="researchwatchconfig",
            name="enabled_event_types",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Catalyst types to trade. Empty means all types.",
            ),
        ),
        migrations.AddField(
            model_name="researchwatchconfig",
            name="news_keywords",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Google News search terms. Empty uses a generic or event-type pack.",
            ),
        ),
        migrations.AddField(
            model_name="researchwatchconfig",
            name="require_confirmation",
            field=models.BooleanField(
                default=True,
                help_text="Ignore rumor/speculation unless the company or a regulator confirmed it.",
            ),
        ),
        migrations.AlterField(
            model_name="watchedcompany",
            name="sector",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional tag used with research_config.sectors (e.g. healthcare, tech).",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="researchevent",
            name="event_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("clinical_result", "Clinical / trial result"),
                    ("fda_decision", "Regulatory decision"),
                    ("breakthrough", "Research breakthrough"),
                    ("partnership", "Partnership / license"),
                    ("acquisition", "Acquisition / deal"),
                    ("product_launch", "Product launch"),
                    ("contract_win", "Contract / award"),
                    ("earnings", "Earnings / guidance"),
                    ("other", "Other"),
                ],
                default="other",
                max_length=32,
            ),
        ),
    ]
