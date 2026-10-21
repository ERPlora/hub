"""The outbound call of a «Call another system» step (WORKBOOK FLOW-F27; the old hub's HUB-F94).

Only ``https`` with a plain host (no user and password in the address). Before connecting, the host is
resolved ONCE and every address it gives is checked: none may be inside the business or the cloud (private
networks, the machine itself, link-local and the cloud's metadata at 169.254.169.254, carrier-grade NAT,
multicast, reserved, IPv6 unique-local, and IPv4 dressed as IPv6: mapped, 6to4, NAT64). The call then
connects to the address that was checked — the TLS name and the ``Host`` header stay the host's — so a
second answer of the name server cannot send it elsewhere (DNS rebinding). No redirects, no proxy from the
environment, a total time limit and at most ``MAX_BYTES`` of answer (the rest is cut and said so).

``httpx`` (maintained since 2019, 100+ contributors), as the WhatsApp inbox's gateway. Two settings exist
for the tests' local server only, and are never read from the environment: ``FLOW_HTTP_TRUSTED_ADDRESSES``
(addresses let through although inside) and ``FLOW_HTTP_CA_BUNDLE`` (the certificate to trust).
"""

import ipaddress
import json
import socket
import ssl
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from django.conf import settings

from apps.flow.document import origin

#: The most of an answer that is read (the old hub's 1 MiB); the rest is cut, with ``truncated``.
MAX_BYTES = 1024 * 1024
#: The methods a step may use.
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")

OK = "ok"
STATUS = "status"
BLOCKED = "blocked"
INVALID = "invalid"
FAILED = "failed"
TIMEOUT = "timeout"


@dataclass(frozen=True)
class Reply:
    kind: str
    status: int | None = None
    body: Any = None
    truncated: bool = False
    detail: str = ""


def blocked_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Whether a call may NOT go to ``address``: anything that is not a public internet address. Python's
    own classification already sees through IPv4 dressed as IPv6 (mapped and 6to4 are private, NAT64 and
    Teredo reserved or private): the tests pin each case."""
    return not address.is_global or address.is_multicast or address.is_reserved


def _trusted() -> set[str]:
    return {str(item) for item in getattr(settings, "FLOW_HTTP_TRUSTED_ADDRESSES", None) or []}


def _literal(host: str) -> str | None:
    """``host`` as an address when it is one (``None`` for a name, which is resolved)."""
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return None


def _resolve(host: str, port: int) -> list[str]:
    """Every address ``host`` gives (an address as it is): ``OSError`` if it gives none."""
    literal = _literal(host)
    if literal is not None:
        return [literal]
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]).split("%", 1)[0] for info in infos))


def _verify() -> ssl.SSLContext | bool:
    bundle = getattr(settings, "FLOW_HTTP_CA_BUNDLE", None)
    return ssl.create_default_context(cafile=bundle) if bundle else True


def _decoded(raw: bytes, content_type: str, truncated: bool) -> Any:
    text = raw.decode("utf-8", errors="replace")
    if not truncated and "json" in content_type.lower():
        try:
            return json.loads(text)
        except ValueError:
            return text
    return text


def call(method: str, url: str, headers: dict[str, str], body: str, timeout: float, *, max_bytes: int = MAX_BYTES) -> Reply:
    """Calls ``url`` once; never raises: how it ended is the reply's ``kind``."""
    if origin(url) is None or method not in METHODS:
        return Reply(INVALID, detail="Only an https address with a plain host can be called.")
    parts = urlsplit(url.strip())
    host = parts.hostname or ""
    port = parts.port or 443
    try:
        addresses = _resolve(host, port)
    except OSError as failure:
        return Reply(FAILED, detail=f"The name could not be resolved: {failure}")
    trusted = _trusted()
    if not addresses or any(
        address not in trusted and blocked_address(ipaddress.ip_address(address)) for address in addresses
    ):
        return Reply(BLOCKED, detail="That address is inside a private network, so it is not called.")
    pinned = addresses[0]
    netloc = f"[{pinned}]:{port}" if ":" in pinned else f"{pinned}:{port}"
    target = urlunsplit(("https", netloc, parts.path or "/", parts.query, ""))
    sent = {name: value for name, value in headers.items() if name.lower() != "host"}
    sent["Host"] = parts.netloc.rsplit("@", 1)[-1]
    for name, value in sent.items():
        # A header carries ASCII only: a datum with an accent inserted in one cannot be sent (httpx would
        # raise, and a crash here would leave the run «calling» for ever).
        try:
            f"{name}: {value}".encode("ascii")
        except UnicodeEncodeError:
            return Reply(FAILED, detail=f"The header «{name}» has a character that cannot be sent: only ASCII goes in a header.")
    deadline = time.monotonic() + timeout
    try:
        with httpx.Client(verify=_verify(), trust_env=False, follow_redirects=False, timeout=httpx.Timeout(timeout)) as client:
            request = client.build_request(
                method, target, headers=sent, content=body.encode() if body else None, extensions={"sni_hostname": host}
            )
            response = client.send(request, stream=True)
            try:
                raw = bytearray()
                truncated = False
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > max_bytes:
                        raw, truncated = raw[:max_bytes], True
                        break
                    if time.monotonic() > deadline:
                        return Reply(TIMEOUT, detail=f"It did not answer within {timeout:g} seconds.")
            finally:
                response.close()
    except httpx.TimeoutException:
        return Reply(TIMEOUT, detail=f"It did not answer within {timeout:g} seconds.")
    except httpx.HTTPError as failure:
        return Reply(FAILED, detail=f"{type(failure).__name__}: {failure}")
    except Exception as failure:  # noqa: BLE001 — never raises: a crash here would leave the run «calling» for ever
        # What the wire cannot carry (a header with a datum that is not ASCII, an address httpx refuses):
        # a failure the run records and the person reads, like any other.
        return Reply(FAILED, detail=f"{type(failure).__name__}: {failure}")
    answer = _decoded(bytes(raw), response.headers.get("content-type", ""), truncated)
    kind = OK if 200 <= response.status_code < 300 else STATUS
    return Reply(kind, status=response.status_code, body=answer, truncated=truncated)
