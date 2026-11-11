from django.contrib import admin

from .models import (
    ExecutionAccount,
    ExecutionAgentToken,
    ExecutionMcpAccessGrant,
    ExecutionOAuthClient,
    HarnessJournal,
    HarnessOrder,
    HarnessPosition,
    HarnessSignal,
)


@admin.register(ExecutionAccount)
class ExecutionAccountAdmin(admin.ModelAdmin):
    list_display = ("user", "slug", "label", "broker_connection", "dry_run", "is_enabled")
    list_filter = ("dry_run", "is_enabled")


@admin.register(HarnessSignal)
class HarnessSignalAdmin(admin.ModelAdmin):
    list_display = ("ref_id", "execution_account", "symbol", "status", "quantity", "created_at")
    list_filter = ("status", "market")
    search_fields = ("ref_id", "symbol")


@admin.register(HarnessPosition)
class HarnessPositionAdmin(admin.ModelAdmin):
    list_display = ("signal", "remaining_quantity", "status", "unrealized_pnl", "opened_at")


@admin.register(HarnessOrder)
class HarnessOrderAdmin(admin.ModelAdmin):
    list_display = ("signal", "purpose", "limit_price", "quantity", "status", "dry_run", "created_at")


@admin.register(HarnessJournal)
class HarnessJournalAdmin(admin.ModelAdmin):
    list_display = ("action", "user", "execution_account", "signal", "created_at")
    list_filter = ("action",)


@admin.register(ExecutionAgentToken)
class ExecutionAgentTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "label", "token_prefix", "last_used_at", "revoked_at")


@admin.register(ExecutionOAuthClient)
class ExecutionOAuthClientAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "client_id", "created_at")


@admin.register(ExecutionMcpAccessGrant)
class ExecutionMcpAccessGrantAdmin(admin.ModelAdmin):
    list_display = ("user", "client", "expires_at", "last_used_at", "revoked_at")
