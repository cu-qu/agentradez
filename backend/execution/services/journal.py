from execution.models import ExecutionAccount, HarnessJournal, HarnessSignal


def journal(
    action: str,
    *,
    execution_account: ExecutionAccount | None = None,
    signal: HarnessSignal | None = None,
    detail: dict | None = None,
) -> HarnessJournal:
    return HarnessJournal.objects.create(
        execution_account=execution_account,
        signal=signal,
        action=action,
        detail=detail or {},
    )
