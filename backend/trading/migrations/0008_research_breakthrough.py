import decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0007_unfilled_trade_records"),
    ]

    operations = [
        migrations.CreateModel(
            name="ResearchWatchConfig",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "poll_interval_seconds",
                    models.PositiveIntegerField(
                        default=60,
                        help_text="How often to pull company news, in seconds.",
                        validators=[
                            django.core.validators.MinValueValidator(15),
                            django.core.validators.MaxValueValidator(86400),
                        ],
                    ),
                ),
                (
                    "lookback_hours",
                    models.PositiveSmallIntegerField(
                        default=24,
                        help_text="Ignore headlines older than this on ingest.",
                    ),
                ),
                (
                    "min_catalyst_score",
                    models.PositiveSmallIntegerField(
                        default=70,
                        help_text="Minimum classification score (0-100) required to emit a signal.",
                        validators=[
                            django.core.validators.MinValueValidator(0),
                            django.core.validators.MaxValueValidator(100),
                        ],
                    ),
                ),
                (
                    "otm_pct",
                    models.DecimalField(
                        decimal_places=2,
                        default=decimal.Decimal("5.00"),
                        help_text="How far out-of-the-money to select the strike, as a percent of spot.",
                        max_digits=6,
                    ),
                ),
                ("min_dte", models.PositiveSmallIntegerField(default=14)),
                ("max_dte", models.PositiveSmallIntegerField(default=45)),
                (
                    "signal_cooldown_hours",
                    models.PositiveSmallIntegerField(
                        default=6,
                        help_text="Skip a second signal on the same ticker within this window.",
                    ),
                ),
                ("last_polled_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "strategy",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="research_config",
                        to="trading.strategy",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="WatchedCompany",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("ticker", models.CharField(max_length=16)),
                ("name", models.CharField(max_length=128)),
                (
                    "aliases",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Alternate names used to match headlines.",
                    ),
                ),
                ("sector", models.CharField(default="biotech", max_length=32)),
                (
                    "rss_url",
                    models.URLField(
                        blank=True,
                        help_text="Optional company IR / press RSS feed.",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "strategy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="watched_companies",
                        to="trading.strategy",
                    ),
                ),
            ],
            options={
                "ordering": ["ticker"],
            },
        ),
        migrations.CreateModel(
            name="ResearchEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("external_id", models.CharField(max_length=128)),
                ("source", models.CharField(max_length=32)),
                ("source_url", models.URLField(blank=True, max_length=1024)),
                ("headline", models.CharField(max_length=512)),
                ("summary", models.TextField(blank=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("catalyst", "Catalyst"),
                            ("noise", "Noise"),
                            ("skipped", "Skipped"),
                            ("error", "Error"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                (
                    "event_type",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("clinical_result", "Clinical result"),
                            ("fda_decision", "FDA decision"),
                            ("breakthrough", "Breakthrough / vaccine"),
                            ("partnership", "Partnership / license"),
                            ("acquisition", "Acquisition / deal"),
                            ("other", "Other"),
                        ],
                        default="other",
                        max_length=32,
                    ),
                ),
                (
                    "direction",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("bullish", "Bullish"),
                            ("bearish", "Bearish"),
                            ("unknown", "Unknown"),
                        ],
                        default="unknown",
                        max_length=16,
                    ),
                ),
                ("score", models.PositiveSmallIntegerField(default=0)),
                ("rationale", models.CharField(blank=True, max_length=255)),
                ("skip_reason", models.CharField(blank=True, max_length=255)),
                ("option_suggestion", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "company",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="events",
                        to="trading.watchedcompany",
                    ),
                ),
                (
                    "strategy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="research_events",
                        to="trading.strategy",
                    ),
                ),
            ],
            options={
                "ordering": ["-published_at", "-id"],
            },
        ),
        migrations.AddField(
            model_name="signal",
            name="research_event",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="signals",
                to="trading.researchevent",
            ),
        ),
        migrations.AddConstraint(
            model_name="watchedcompany",
            constraint=models.UniqueConstraint(
                fields=("strategy", "ticker"),
                name="unique_watched_company_per_strategy",
            ),
        ),
        migrations.AddConstraint(
            model_name="researchevent",
            constraint=models.UniqueConstraint(
                fields=("strategy", "external_id"),
                name="unique_research_event_per_strategy",
            ),
        ),
        migrations.AddConstraint(
            model_name="signal",
            constraint=models.UniqueConstraint(
                condition=models.Q(("research_event__isnull", False)),
                fields=("research_event",),
                name="one_signal_per_research_event",
            ),
        ),
    ]
