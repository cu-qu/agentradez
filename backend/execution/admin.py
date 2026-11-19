from django.contrib import admin

from .models import ExecutionAccount, HarnessJournal, HarnessOrder, HarnessPosition, HarnessSignal


@admin.register(ExecutionAccount)
class ExecutionAccountAdmin(admin.ModelAdmin):
    list_display = ("slug", "label", "broker_connection", "dry_run", "is_enabled")
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
    list_display = ("action", "execution_account", "signal", "created_at")
    list_filter = ("action",)
