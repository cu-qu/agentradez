from accounts.models import User
from execution.models import ExecutionAccount, HarnessJournal, HarnessSignal


def journal(
    action: str,
    *,
    user: User | None = None,
    execution_account: ExecutionAccount | None = None,
    signal: HarnessSignal | None = None,
    detail: dict | None = None,
) -> HarnessJournal:
    if user is None and signal is not None:
        user = signal.user
    if user is None and execution_account is not None:
        user = execution_account.user
    return HarnessJournal.objects.create(
        user=user,
        execution_account=execution_account,
        signal=signal,
        action=action,
        detail=detail or {},
    )
