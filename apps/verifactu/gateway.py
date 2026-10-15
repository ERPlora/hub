"""The client of ERPlora's fiscal gateway, which lives in the SaaS (PLAN §16.5; WORKBOOK «Contrato con el SaaS»).

The Hub validates everything fiscal (chain, fingerprint, schema, QR) and hands the gateway the exact bytes to
present; the gateway (saas-next ``fiscal_gateway/``) presents them to the AEAT with ERPlora's seal or, on the
«own» route, with the business's own certificate, which travels in every call (``certificate``: the .p12 in
base64 and its password; the gateway never keeps it), and answers the AEAT's answer as it came. Three doors,
``POST`` with JSON, signed like every ``/internal`` call (``X-Erplora-Timestamp`` and ``X-Erplora-Signature``,
HMAC-SHA256 of ``f"{timestamp}.{body}"`` with ``INTERNAL_SHARED_SECRET``; ``base.auth.sign``; the gateway
also takes v2, which the Hub does not send yet):

- ``/internal/verifactu/submit`` → ``200 {"aeat_status", "aeat_body"}``;
- ``/internal/verifactu/query`` → the same;
- ``/internal/verifactu/probe`` → ``200 {"ready", "detail"}``, presenting nothing.

``VERIFACTU_GATEWAY_URL`` (settings, else the environment) is the SaaS's internal URL; empty means there is no
gateway: nothing is sent and nothing is ever taken as accepted. ``httpx`` (maintained since 2019, 100+
contributors): 5 s to connect and 45 s to read, longer than the gateway's own wait for the AEAT (5 s to connect,
30 s to read). How a call ended is the reply's ``kind``:

- ``answered``: the gateway answered (the AEAT's answer inside, whatever it says);
- ``refused``: the gateway will not present it as it is (``404`` ``hub_unknown``, the body's ``hub`` names no hub
  of the SaaS; ``409`` ``nif_mismatch``, ``representation_not_approved``, ``no_seal``, ``no_certificate``,
  ``certificate_invalid``, ``environment_not_allowed``; ``413`` ``payload_too_large``; ``422``
  ``invalid_payload``), its code and message kept to be shown;
- ``unreachable``: nothing reached the AEAT (no connection, ``502 aeat_unreachable`` with ``sent: false``,
  ``503 gateway_busy``, another status): to retry;
- ``unknown``: the request left and no usable answer came back (``502 aeat_unreachable`` with ``sent: true``,
  a read that timed out): it may have reached the AEAT.
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
TIMEOUT = httpx.Timeout(45.0, connect=5.0)
#: Statuses whose contract error says the gateway will never present this call as it is.
REFUSALS = (409, 413, 422)
#: The one 404 that is a refusal (saas#29): any other 404 is a door not there yet, tried again.
UNKNOWN_HUB = "hub_unknown"

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
        # Straight to the SaaS's internal address: a proxy of the process never sees an envelope or a certificate.
        with httpx.Client(timeout=TIMEOUT, trust_env=False) as client:
            return "", client.post(f"{url}{path}", content=body, headers=headers), ""
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as error:
        return UNREACHABLE, None, f"The gateway could not be reached: {error}."
    except httpx.HTTPError as error:
        return UNKNOWN, None, f"The request left and no answer came back: {error}."


def _error(response: httpx.Response) -> dict | None:
    """The contract's ``{"error": {...}}`` of a non-200 answer, or ``None`` when it is not there."""
    try:
        error = response.json()["error"]
    except (ValueError, KeyError, TypeError):
        return None
    return error if isinstance(error, dict) and error.get("code") else None


def _refusal(response: httpx.Response, error: dict | None) -> Reply:
    if error is None:
        return Reply(
            kind=REFUSED,
            code="verifactu_gateway.refused",
            message=f"HTTP {response.status_code}: {response.text[:300]}",
        )
    message = str(error.get("message", ""))
    fields = error.get("fields")
    if isinstance(fields, dict) and fields:
        message = f"{message} ({', '.join(f'{name}: {why}' for name, why in fields.items())})"
    return Reply(kind=REFUSED, code=str(error["code"]), message=message)


def _reply(path: str, payload: dict) -> Reply:
    failure, response, message = _post(path, payload)
    if response is None:
        return Reply(kind=failure, message=message)
    if response.status_code in REFUSALS:
        return _refusal(response, _error(response))
    if response.status_code != 200:
        error = _error(response)
        if response.status_code == 404 and error and error["code"] == UNKNOWN_HUB:
            return _refusal(response, error)
        said = f": {error.get('message', '')}" if error else "."
        if error and error["code"] == "aeat_unreachable" and error.get("sent") is True:
            return Reply(
                kind=UNKNOWN,
                message=f"The request reached the gateway and the AEAT did not answer{said}",
            )
        return Reply(
            kind=UNREACHABLE,
            message=f"The gateway answered HTTP {response.status_code}{said}",
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


def _body(
    hub: str,
    nif: str,
    environment: str,
    route: str,
    certificate: Certificate | None,
    envelope: str | None = None,
) -> dict:
    body = {"hub": hub, "nif": nif, "environment": environment, "route": route}
    if envelope is not None:
        body["envelope"] = envelope
    if certificate is not None:
        body["certificate"] = {
            "p12_base64": certificate.p12_base64,
            "password": certificate.password,
        }
    return body


def submit(
    *,
    hub: str,
    nif: str,
    environment: str,
    route: str,
    envelope: str,
    certificate: Certificate | None = None,
) -> Reply:
    """Hand a submission's envelope to the gateway, which presents it to the AEAT of ``environment``."""
    return _reply(SUBMIT_PATH, _body(hub, nif, environment, route, certificate, envelope))


def query(
    *,
    hub: str,
    nif: str,
    environment: str,
    route: str,
    envelope: str,
    certificate: Certificate | None = None,
) -> Reply:
    """Hand a query's envelope to the gateway."""
    return _reply(QUERY_PATH, _body(hub, nif, environment, route, certificate, envelope))


def probe(
    *,
    hub: str,
    nif: str,
    environment: str,
    route: str,
    certificate: Certificate | None = None,
) -> Reply:
    """Ask the gateway whether it can present for this business now, presenting nothing."""
    return _reply(PROBE_PATH, _body(hub, nif, environment, route, certificate))
