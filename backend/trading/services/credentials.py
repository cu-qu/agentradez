from django.core import signing

_SALT = "trading.broker-credentials"


def encrypt_credentials(data: dict) -> str:
    return signing.dumps(data, salt=_SALT)


def decrypt_credentials(payload: str) -> dict:
    if not payload:
        return {}
    try:
        loaded = signing.loads(payload, salt=_SALT)
    except signing.BadSignature:
        return {}
    return loaded if isinstance(loaded, dict) else {}
