"""The Hub's client of erplora.com's WhatsApp doors (WORKBOOK «Contrato con el SaaS», doors 5, 6, 8, 9 and 10–12).

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

``submit_template`` → ``POST {SAAS_INTERNAL_URL}/internal/whatsapp/templates`` (door 8, WHATSAPP_INBOX-F29,
F30) with an ``Idempotency-Key``: erplora.com registers (or edits) the template at Meta once per key (a header with a
file carries it in ``header_sample``, which erplora.com uploads to Meta first: waited for 90 s, still within
``services.STUCK_AFTER``) and
answers ``200 {"meta_id", "status"}`` (``accepted``: Meta took it for review); a 409 carries its code and
Meta's reason (``refused``); the rest reads as for ``send``. ``delete_template`` → ``POST …/templates/delete``
(door 9, F31): ``200 {"deleted": true}`` or its 404 ``whatsapp.template_not_found`` (Meta no longer has
it) is ``accepted``; any other 404 is «nothing left».

``config`` / ``connect`` / ``disconnect`` → ``POST …/internal/whatsapp/{config,connect,disconnect}`` (doors 10–12,
WHATSAPP_INBOX-F01, F02): what opens Meta's window (Embedded Signup), the number that window chose with its one-time
code, and disconnecting it. A 200 is ``accepted`` with erplora.com's body (``data``); erplora.com's error envelope at
any status is ``refused`` with that status, its code and its reason (nothing was done); a 4xx without the envelope
(a door not served, a proxy) is «nothing left» and a 5xx without it, or a 200 that is no JSON object, ``unknown``.

No call ever raises past its caller: ``httpx`` also raises errors that are not ``HTTPError`` (an URL it
cannot parse, a header it cannot encode), and they read as «nothing left» (``unreachable``).
"""

import json
import time
from dataclasses import dataclass, field

import httpx
from django.conf import settings

from base.auth import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign

SEND_PATH = "/internal/whatsapp/send"
ERASE_PATH = "/internal/whatsapp/erase"
TEMPLATES_PATH = "/internal/whatsapp/templates"
TEMPLATES_DELETE_PATH = "/internal/whatsapp/templates/delete"
CONFIG_PATH = "/internal/whatsapp/config"
CONNECT_PATH = "/internal/whatsapp/connect"
DISCONNECT_PATH = "/internal/whatsapp/disconnect"
IDEMPOTENCY_HEADER = "Idempotency-Key"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)
#: Door 8 with a header's file: erplora.com uploads it to Meta (up to 25 MB) before registering the template.
SAMPLE_TIMEOUT = httpx.Timeout(90.0, connect=5.0)

SENT = "sent"
REFUSED = "refused"
UNREACHABLE = "unreachable"
UNKNOWN = "unknown"
ACCEPTED = "accepted"

#: Meta's verdicts erplora.com may report for a template it registered.
VERDICTS = frozenset({"APPROVED", "PENDING", "REJECTED", "PAUSED", "DISABLED"})

#: The code of a 409 that did not carry erplora.com's error envelope.
GENERIC_REFUSAL = "whatsapp.refused"
#: erplora.com's 404 code at door 9: Meta has no such template (so it is deleted).
TEMPLATE_NOT_FOUND = "whatsapp.template_not_found"


class NotConfigured(Exception):
    """This server has no SaaS internal URL: nothing can be sent from it."""


@dataclass(frozen=True)
class Reply:
    kind: str
    wa_message_id: str = ""
    code: str = ""
    message: str = ""
    meta_id: str = ""
    status: str = ""
    #: Doors 10–12: erplora.com's body of a 200; the HTTP status of a refusal.
    data: dict = field(default_factory=dict)
    http_status: int = 0


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


def _post(
    path: str, payload: dict, idempotency_key: str | None = None, timeout: httpx.Timeout = TIMEOUT
) -> httpx.Response | Reply:
    """POST ``payload`` signed to erplora.com's ``path``: its response, or the ``Reply`` of a call that
    ended without one (never an exception)."""
    url = _url(path)
    body, headers = _signed(payload)
    if idempotency_key is not None:
        headers[IDEMPOTENCY_HEADER] = str(idempotency_key)
    try:
        with httpx.Client(timeout=timeout) as client:
            return client.post(url, content=body, headers=headers)
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as error:
        return Reply(kind=UNREACHABLE, message=f"erplora.com could not be reached: {error}.")
    except httpx.HTTPError as error:
        return Reply(kind=UNKNOWN, message=f"The request left and no answer came back: {error}.")
    except (httpx.InvalidURL, ValueError) as error:
        # Not an HTTPError (an URL httpx cannot parse, a header it cannot encode): nothing left.
        return Reply(kind=UNREACHABLE, message=f"The request to erplora.com could not be made: {error}.")


def send(
    *,
    hub: str,
    to: str,
    idempotency_key: str,
    text: str | None = None,
    template: dict | None = None,
) -> Reply:
    """Ask erplora.com to send ``text`` or ``template`` to ``to`` (E.164) for the business ``hub``."""
    payload: dict = {"hub": hub, "to": to}
    if template is not None:
        payload.update(type="template", template=template)
    else:
        payload.update(type="text", text=text or "")
    with_file = template is not None and template.get("header_sample")
    response = _post(SEND_PATH, payload, idempotency_key, SAMPLE_TIMEOUT if with_file else TIMEOUT)
    if isinstance(response, Reply):
        return response
    reply = _read(response)
    if reply.kind == UNKNOWN and _error_code(response) == "whatsapp.meta_unreachable":
        # erplora.com says Meta did not answer and nothing left: Meta's silence, never ERPlora's (gh:hub#2731).
        return Reply(kind=UNREACHABLE, code="whatsapp.meta_unreachable", message=reply.message)
    return reply


def _settled(response: httpx.Response) -> Reply | None:
    """How a response that is not a 200 ends: a 409 refusal, «unknown» for a 5xx, «nothing left» for
    any other 4xx; ``None`` for a 200, which its caller reads."""
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
    return None


def _error_code(response: httpx.Response) -> str:
    """The code of erplora.com's error envelope, or ``""``."""
    error = _json(response).get("error")
    return str(error.get("code", "")) if isinstance(error, dict) else ""


def _json(response: httpx.Response) -> dict:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _read(response: httpx.Response) -> Reply:
    settled = _settled(response)
    if settled is not None:
        return settled
    wa_message_id = _json(response).get("wa_message_id")
    if not isinstance(wa_message_id, str) or not wa_message_id:
        return Reply(
            kind=UNKNOWN, message="erplora.com's answer has no WhatsApp message id."
        )
    return Reply(kind=SENT, wa_message_id=wa_message_id)


def erase(*, hub: str, phone: str, wa_message_ids: list[str]) -> bool:
    """Ask erplora.com to forget ``phone`` and those messages; ``True`` only when it confirms."""
    response = _post(ERASE_PATH, {"hub": hub, "phone": phone, "wa_message_ids": list(wa_message_ids)})
    if isinstance(response, Reply) or response.status_code != 200:
        return False
    return _json(response).get("erased") is True


def submit_template(*, hub: str, idempotency_key: str, template: dict) -> Reply:
    """Ask erplora.com to register ``template`` at Meta for ``hub`` (new, or an edit of its ``meta_id``)."""
    timeout = SAMPLE_TIMEOUT if template.get("header_sample") else TIMEOUT
    response = _post(TEMPLATES_PATH, {"hub": hub, **template}, idempotency_key, timeout)
    if isinstance(response, Reply):
        return response
    settled = _settled(response)
    if settled is not None:
        return settled
    data = _json(response)
    meta_id, status = data.get("meta_id"), data.get("status")
    if not isinstance(meta_id, str) or not meta_id or status not in VERDICTS:
        return Reply(kind=UNKNOWN, message="erplora.com's answer has no Meta id or verdict for the template.")
    return Reply(kind=ACCEPTED, meta_id=meta_id, status=status)


def delete_template(*, hub: str, name: str, language: str, meta_id: str) -> Reply:
    """Ask erplora.com to delete that one template at Meta. Its 404 saying ``whatsapp.template_not_found``
    (Meta no longer has it) is a deletion; any other 404 (a door it does not serve, a wrong address) is
    «nothing left», never a deletion (gh:whatsapp_inbox#296)."""
    response = _post(
        TEMPLATES_DELETE_PATH, {"hub": hub, "name": name, "language": language, "meta_id": meta_id}
    )
    if isinstance(response, Reply):
        return response
    if response.status_code == 404 and _error_code(response) == TEMPLATE_NOT_FOUND:
        return Reply(kind=ACCEPTED)
    settled = _settled(response)
    if settled is not None:
        return settled
    if _json(response).get("deleted") is not True:
        return Reply(kind=UNKNOWN, message="erplora.com did not confirm the deletion.")
    return Reply(kind=ACCEPTED)


def config(*, hub: str) -> Reply:
    """Door 10: what the business's screen opens Meta's window with (public ids only)."""
    return _door(CONFIG_PATH, {"hub": hub})


def connect(*, hub: str, code: str, event: str, waba_id: str, phone_number_id: str, business_id: str) -> Reply:
    """Door 11: connect the number Meta's window chose, with what the window gave, as it came."""
    window = {"code": code, "event": event, "waba_id": waba_id, "phone_number_id": phone_number_id, "business_id": business_id}
    return _door(CONNECT_PATH, {"hub": hub, **window})


def disconnect(*, hub: str) -> Reply:
    """Door 12: disconnect the business's number."""
    return _door(DISCONNECT_PATH, {"hub": hub})


def _door(path: str, payload: dict) -> Reply:
    response = _post(path, payload)
    if isinstance(response, Reply):
        return response
    error = _json(response).get("error")
    if response.status_code != 200 and isinstance(error, dict) and error.get("code"):
        return Reply(
            kind=REFUSED,
            http_status=response.status_code,
            code=str(error["code"]),
            message=str(error.get("message", "")),
        )
    if response.status_code >= 500:
        return Reply(kind=UNKNOWN, message=f"erplora.com answered HTTP {response.status_code}.")
    if response.status_code != 200:
        return Reply(kind=UNREACHABLE, message=f"erplora.com answered HTTP {response.status_code}.")
    try:
        data = response.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return Reply(kind=UNKNOWN, message="erplora.com's answer is not the door's.")
    return Reply(kind=ACCEPTED, data=data)
