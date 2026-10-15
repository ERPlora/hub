"""The Hub's client of erplora.com's WhatsApp doors (WORKBOOK «Contrato con el SaaS», doors 5 and 6).

The WhatsApp Business account and Meta's token live in the SaaS: the Hub asks it to send and to forget
a number, and keeps what it answers. JSON, signed like every ``/internal`` call (``X-Erplora-Timestamp``
and ``X-Erplora-Signature``, HMAC-SHA256 of ``f"{timestamp}.{body}"`` with ``INTERNAL_SHARED_SECRET``;
``base.auth.sign``). Both are called OUTSIDE any transaction, after the COMMIT that queued the work
(services.py): a slow erplora.com never holds a lock of the hub.

``send`` → ``POST {SAAS_INTERNAL_URL}/internal/whatsapp/send`` with an ``Idempotency-Key``: erplora.com
never sends the same key twice, so a retry is safe. ``httpx`` (maintained since 2019, 100+
contributors): 5 s to connect, 15 s to read. How a call ended is the reply's ``kind``:

- ``sent``: 200 with Meta's ``wa_message_id``;
- ``refused``: 409 with erplora.com's code and reason (no number, allowance spent, window closed…);
- ``unreachable``: nothing left: no connection, or erplora.com refused to read it (a 4xx other than
  409);
- ``unknown``: the request left and no usable answer came back (a 5xx, a read timeout, a 200 without
  Meta's id): erplora.com may have reached Meta, so it is retried with the same key, never as new.

``erase`` → ``POST {SAAS_INTERNAL_URL}/internal/whatsapp/erase`` with the number and the WhatsApp ids of
its messages (WHATSAPP_INBOX-F10, F11); only ``200 {"erased": true}`` confirms it.
"""

import json
import time
from dataclasses import dataclass

import httpx
from django.conf import settings

from base.auth import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign

SEND_PATH = "/internal/whatsapp/send"
ERASE_PATH = "/internal/whatsapp/erase"
IDEMPOTENCY_HEADER = "Idempotency-Key"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)

SENT = "sent"
REFUSED = "refused"
UNREACHABLE = "unreachable"
UNKNOWN = "unknown"

#: The code of a 409 that did not carry erplora.com's error envelope.
GENERIC_REFUSAL = "whatsapp.refused"


class NotConfigured(Exception):
    """This server has no SaaS internal URL: nothing can be sent from it."""


@dataclass(frozen=True)
class Reply:
    kind: str
    wa_message_id: str = ""
    code: str = ""
    message: str = ""


def base_url() -> str:
    return str(getattr(settings, "SAAS_INTERNAL_URL", "") or "").strip().rstrip("/")


def configured() -> bool:
    return bool(base_url())


def _signed(payload: dict) -> tuple[bytes, dict[str, str]]:
    """The JSON body of ``payload`` and the headers that sign it, as every ``/internal`` call."""
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    timestamp = str(int(time.time()))
    return body, {
        "Content-Type": "application/json",
        TIMESTAMP_HEADER: timestamp,
        SIGNATURE_HEADER: sign(settings.INTERNAL_SHARED_SECRET, timestamp, body),
    }


def _url(path: str) -> str:
    url = base_url()
    if not url:
        raise NotConfigured("SAAS_INTERNAL_URL is not set.")
    return f"{url}{path}"


def send(
    *,
    hub: str,
    to: str,
    idempotency_key: str,
    text: str | None = None,
    template: dict | None = None,
) -> Reply:
    """Ask erplora.com to send ``text`` or ``template`` to ``to`` (E.164) for the business ``hub``."""
    url = _url(SEND_PATH)
    payload: dict = {"hub": hub, "to": to}
    if template is not None:
        payload.update(type="template", template=template)
    else:
        payload.update(type="text", text=text or "")
    body, headers = _signed(payload)
    headers[IDEMPOTENCY_HEADER] = str(idempotency_key)
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.post(url, content=body, headers=headers)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as error:
        return Reply(
            kind=UNREACHABLE, message=f"erplora.com could not be reached: {error}."
        )
    except httpx.HTTPError as error:
        return Reply(
            kind=UNKNOWN, message=f"The request left and no answer came back: {error}."
        )
    return _read(response)


def _read(response: httpx.Response) -> Reply:
    if response.status_code == 409:
        try:
            error = response.json()["error"]
            return Reply(
                kind=REFUSED,
                code=str(error["code"]),
                message=str(error.get("message", "")),
            )
        except ValueError, KeyError, TypeError:
            return Reply(
                kind=REFUSED, code=GENERIC_REFUSAL, message=response.text[:300]
            )
    if response.status_code >= 500:
        # erplora.com may have called Meta before failing: never «not sent».
        return Reply(
            kind=UNKNOWN, message=f"erplora.com answered HTTP {response.status_code}."
        )
    if response.status_code != 200:
        return Reply(
            kind=UNREACHABLE,
            message=f"erplora.com answered HTTP {response.status_code}.",
        )
    try:
        data = response.json()
    except ValueError:
        data = None
    wa_message_id = data.get("wa_message_id") if isinstance(data, dict) else None
    if not isinstance(wa_message_id, str) or not wa_message_id:
        return Reply(
            kind=UNKNOWN, message="erplora.com's answer has no WhatsApp message id."
        )
    return Reply(kind=SENT, wa_message_id=wa_message_id)


def erase(*, hub: str, phone: str, wa_message_ids: list[str]) -> bool:
    """Ask erplora.com to forget ``phone`` and those messages; ``True`` only when it confirms."""
    url = _url(ERASE_PATH)
    body, headers = _signed(
        {"hub": hub, "phone": phone, "wa_message_ids": list(wa_message_ids)}
    )
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.post(url, content=body, headers=headers)
    except httpx.HTTPError:
        return False
    if response.status_code != 200:
        return False
    try:
        data = response.json()
    except ValueError:
        return False
    return isinstance(data, dict) and data.get("erased") is True
