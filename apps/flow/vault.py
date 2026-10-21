"""The automations' secrets box (WORKBOOK FLOW-F26; the old hub's ``secret_box.rs``).

A secret's value is sealed with Fernet (AES-128-CBC + HMAC-SHA256, from ``cryptography``) under
``settings.FLOW_SECRETS_KEY`` (Secrets Manager in AWS; never in the code) and is only opened to make a call
of a «Call another system» step. Nothing gives it back: no route, live query, history, «Try it» or log.
What a call leaves (its answer, its error) goes through ``mask``/``mask_any``, which hide every value it
used; the hiding is by exact match, so a value the other system sends back encoded (base64, URL) is not
hidden (the old hub's documented limit).
"""

import binascii
from collections.abc import Iterable
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

#: What a secret's value becomes wherever it would show.
MASK = "••••"


class Unavailable(Exception):
    """This server has no usable ``FLOW_SECRETS_KEY``: no secret can be kept or used."""


class Unreadable(Exception):
    """A kept value this server's key cannot open (the key changed)."""


def _fernet() -> Fernet | None:
    key = str(getattr(settings, "FLOW_SECRETS_KEY", "") or "").strip()
    if not key:
        return None
    try:
        return Fernet(key)
    except ValueError, TypeError, binascii.Error:
        return None


def available() -> bool:
    """Whether this server can keep and use secrets."""
    return _fernet() is not None


def seal(value: str) -> str:
    """``value`` encrypted, as text; ``Unavailable`` without a usable key."""
    fernet = _fernet()
    if fernet is None:
        raise Unavailable("FLOW_SECRETS_KEY is not set or is not a Fernet key.")
    return fernet.encrypt(value.encode()).decode()


def open_value(token: str) -> str:
    """The value ``seal`` kept; ``Unavailable`` without a key, ``Unreadable`` if this key cannot open it."""
    fernet = _fernet()
    if fernet is None:
        raise Unavailable("FLOW_SECRETS_KEY is not set or is not a Fernet key.")
    try:
        return fernet.decrypt(token.encode()).decode()
    except InvalidToken, ValueError, UnicodeDecodeError:
        raise Unreadable("The kept secret cannot be opened with this server's key.") from None


def mask(text: str, values: Iterable[str]) -> str:
    """``text`` with every one of ``values`` replaced by ``MASK``, the longest first."""
    for value in sorted({value for value in values if value}, key=len, reverse=True):
        text = text.replace(value, MASK)
    return text


def mask_any(data: Any, values: Iterable[str]) -> Any:
    """``data`` (text, a list, a dict, keys included) with every one of ``values`` hidden."""
    values = list(values)
    if isinstance(data, str):
        return mask(data, values)
    if isinstance(data, list):
        return [mask_any(item, values) for item in data]
    if isinstance(data, dict):
        return {mask_any(key, values): mask_any(item, values) for key, item in data.items()}
    return data
