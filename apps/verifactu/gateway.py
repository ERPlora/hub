"""The client of ERPlora's fiscal gateway, which lives in the SaaS (PLAN §16.5; WORKBOOK «Contrato con el SaaS»).

The Hub validates everything fiscal (chain, fingerprint, schema, QR) and hands the gateway the exact bytes to
present; the gateway presents them to the AEAT with ERPlora's seal or with the customer's own certificate and
answers the AEAT's answer as it came. Three doors, ``POST`` with JSON, signed like every ``/internal`` call
(``X-Erplora-Timestamp`` and ``X-Erplora-Signature``, HMAC-SHA256 of ``f"{timestamp}.{body}"`` with
``INTERNAL_SHARED_SECRET``; ``base.auth.sign``):

- ``/internal/verifactu/submit`` → ``200 {"aeat_status", "aeat_body"}``;
- ``/internal/verifactu/query`` → the same;
- ``/internal/verifactu/probe`` → ``200 {"ready", "detail"}``, presenting nothing.

``VERIFACTU_GATEWAY_URL`` (settings, else the environment) is the SaaS's internal URL; empty means there is no
gateway: nothing is sent and nothing is ever taken as accepted. ``httpx`` (maintained since 2019, 100+
contributors): 5 s to connect, 30 s to read. How a call ended is the reply's ``kind``:

- ``answered``: the gateway answered (the AEAT's answer inside, whatever it says);
- ``refused``: the gateway could not present (a 409 with its code: no approved grant, no certificate…);
- ``unreachable``: nothing reached the AEAT (no connection, another status): to retry;
- ``unknown``: the request left and no usable answer came back: it may have reached the AEAT.
"""

import json
import time
from dataclasses import dataclass, field

import decouple
import httpx
from django.conf import settings

from base.auth import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign

SUBMIT_PATH = "/internal/verifactu/submit"
QUERY_PATH = "/internal/verifactu/query"
PROBE_PATH = "/internal/verifactu/probe"
TIMEOUT = httpx.Timeout(30.0, connect=5.0)

ANSWERED = "answered"
REFUSED = "refused"
UNREACHABLE = "unreachable"
UNKNOWN = "unknown"


class NotConfigured(Exception):
    """This server has no gateway URL: nothing can be presented to the AEAT from it."""


@dataclass(frozen=True)
class Certificate:
    """The business's own certificate as the gateway takes it on the «own» route: never shown in a ``repr``."""

    p12_base64: str = field(repr=False)
    password: str = field(repr=False)


@dataclass(frozen=True)
class Reply:
    kind: str
    aeat_status: int | None = None
    aeat_body: str = ""
    code: str = ""
    message: str = ""
    ready: bool = False


def base_url() -> str:
    url = getattr(settings, "VERIFACTU_GATEWAY_URL", None)
    if url is None:
        url = decouple.config("VERIFACTU_GATEWAY_URL", default="")
    return str(url).strip().rstrip("/")


def configured() -> bool:
    return bool(base_url())


def _post(path: str, payload: dict) -> tuple[str, httpx.Response | None, str]:
    url = base_url()
    if not url:
        raise NotConfigured("VERIFACTU_GATEWAY_URL is not set.")
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    timestamp = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        TIMESTAMP_HEADER: timestamp,
        SIGNATURE_HEADER: sign(settings.INTERNAL_SHARED_SECRET, timestamp, body),
    }
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            return "", client.post(f"{url}{path}", content=body, headers=headers), ""
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as error:
        return UNREACHABLE, None, f"The gateway could not be reached: {error}."
    except httpx.HTTPError as error:
        return UNKNOWN, None, f"The request left and no answer came back: {error}."


def _reply(path: str, payload: dict) -> Reply:
    failure, response, message = _post(path, payload)
    if response is None:
        return Reply(kind=failure, message=message)
    if response.status_code == 409:
        try:
            error = response.json()["error"]
            return Reply(
                kind=REFUSED,
                code=str(error["code"]),
                message=str(error.get("message", "")),
            )
        except (ValueError, KeyError, TypeError):
            return Reply(
                kind=REFUSED,
                code="verifactu_gateway.refused",
                message=response.text[:300],
            )
    if response.status_code != 200:
        return Reply(
            kind=UNREACHABLE,
            message=f"The gateway answered HTTP {response.status_code}.",
        )
    try:
        data = response.json()
    except ValueError:
        return Reply(
            kind=UNKNOWN, message="The gateway's answer is not the contract's JSON."
        )
    if not isinstance(data, dict):
        return Reply(
            kind=UNKNOWN, message="The gateway's answer is not the contract's JSON."
        )
    if path == PROBE_PATH:
        return Reply(
            kind=ANSWERED,
            ready=data.get("ready") is True,
            message=str(data.get("detail") or ""),
        )
    if not isinstance(data.get("aeat_status"), int) or not isinstance(
        data.get("aeat_body"), str
    ):
        return Reply(kind=UNKNOWN, message="The gateway's answer has no AEAT answer.")
    return Reply(
        kind=ANSWERED, aeat_status=data["aeat_status"], aeat_body=data["aeat_body"]
    )


def submit(*, hub: str, nif: str, environment: str, route: str, envelope: str) -> Reply:
    """Hand a submission's envelope to the gateway, which presents it to the AEAT of ``environment``."""
    return _reply(
        SUBMIT_PATH,
        {
            "hub": hub,
            "nif": nif,
            "environment": environment,
            "route": route,
            "envelope": envelope,
        },
    )


def query(*, hub: str, nif: str, environment: str, route: str, envelope: str) -> Reply:
    """Hand a query's envelope to the gateway."""
    return _reply(
        QUERY_PATH,
        {
            "hub": hub,
            "nif": nif,
            "environment": environment,
            "route": route,
            "envelope": envelope,
        },
    )


def probe(*, hub: str, nif: str, environment: str, route: str) -> Reply:
    """Ask the gateway whether it can present for this business now, presenting nothing."""
    return _reply(
        PROBE_PATH, {"hub": hub, "nif": nif, "environment": environment, "route": route}
    )
