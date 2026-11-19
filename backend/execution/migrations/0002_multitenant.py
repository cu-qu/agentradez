import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_users(apps, schema_editor):
    ExecutionAccount = apps.get_model("execution", "ExecutionAccount")
    HarnessSignal = apps.get_model("execution", "HarnessSignal")
    HarnessPosition = apps.get_model("execution", "HarnessPosition")
    HarnessJournal = apps.get_model("execution", "HarnessJournal")
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    admin = User.objects.order_by("id").first()
    for row in ExecutionAccount.objects.select_related("broker_connection").iterator():
        uid = getattr(row.broker_connection, "user_id", None) or (admin.id if admin else None)
        if uid:
            row.user_id = uid
            row.save(update_fields=["user_id"])
    for row in HarnessSignal.objects.select_related("execution_account").iterator():
        if row.execution_account_id:
            row.user_id = row.execution_account.user_id
            row.save(update_fields=["user_id"])
    for row in HarnessPosition.objects.select_related("signal").iterator():
        if row.signal_id:
            row.user_id = row.signal.user_id
            row.save(update_fields=["user_id"])
    for row in HarnessJournal.objects.select_related("execution_account", "signal").iterator():
        if row.execution_account_id:
            row.user_id = row.execution_account.user_id
        elif row.signal_id:
            row.user_id = row.signal.user_id
        row.save(update_fields=["user_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("execution", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("trading", "0015_allow_multiple_broker_connections"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExecutionAgentToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=128)),
                ("token_prefix", models.CharField(db_index=True, max_length=16)),
                ("token_hash", models.CharField(max_length=64)),
                ("scopes", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="execution_agent_tokens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ExecutionOAuthClient",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=128)),
                ("client_id", models.CharField(db_index=True, max_length=64, unique=True)),
                ("client_secret_hash", models.CharField(max_length=64)),
                ("redirect_uris", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="execution_oauth_clients",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ExecutionMcpAccessGrant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("access_token_hash", models.CharField(db_index=True, max_length=64)),
                ("scopes", models.JSONField(default=list)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="grants",
                        to="execution.executionoauthclient",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="execution_mcp_grants",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ExecutionOAuthCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(db_index=True, max_length=64, unique=True)),
                ("scopes", models.JSONField(default=list)),
                ("code_challenge", models.CharField(max_length=128)),
                ("code_challenge_method", models.CharField(default="S256", max_length=16)),
                ("redirect_uri", models.URLField(max_length=512)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="codes",
                        to="execution.executionoauthclient",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="execution_oauth_codes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="executionaccount",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="execution_accounts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="harnesssignal",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="harness_signals",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="harnessposition",
            name="user",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="harness_positions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="harnessjournal",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="harness_journal",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(backfill_users, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="executionaccount",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="execution_accounts",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="harnesssignal",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="harness_signals",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="harnessposition",
            name="user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="harness_positions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="harnesssignal",
            name="ref_id",
            field=models.CharField(db_index=True, max_length=128),
        ),
        migrations.AlterField(
            model_name="executionaccount",
            name="slug",
            field=models.SlugField(max_length=64),
        ),
        migrations.AddConstraint(
            model_name="executionaccount",
            constraint=models.UniqueConstraint(
                fields=("user", "slug"),
                name="unique_execution_account_slug_per_user",
            ),
        ),
        migrations.AddConstraint(
            model_name="harnesssignal",
            constraint=models.UniqueConstraint(
                fields=("user", "ref_id"),
                name="unique_harness_ref_id_per_user",
            ),
        ),
    ]
