"""The outbound call of «Call another system» (WORKBOOK FLOW-F27; old hub HUB-F94), against a real local
HTTPS server (``local_https``: a certificate made here for ``localhost`` and ``127.0.0.1``), never a patched
client.

Only ``https``; never to the business's own network, the machine itself or the cloud's metadata (SSRF):
the name is resolved once and the call connects only to what was checked. No redirects; a time limit and
a size limit on the answer.
"""

import ipaddress
import socket
import time

import pytest

from apps.flow import http

from .local_https import Handler


def test_it_calls_and_reads_the_json_answer(trusted):
    reply = http.call("POST", f"{trusted}/orders?x=1", {"Idempotency-Key": "k-1", "Content-Type": "application/json"}, '{"a": 1}', 5)
    assert (reply.kind, reply.status, reply.truncated) == ("ok", 201, False)
    assert reply.body == {"ok": True, "method": "POST", "body": '{"a": 1}'}
    seen = Handler.seen[-1]
    assert (seen["path"], seen["headers"]["Idempotency-Key"], seen["headers"]["Host"]) == (
        "/orders?x=1",
        "k-1",
        f"localhost:{trusted.rsplit(':', 1)[1]}",
    )


def test_a_text_answer_stays_text(trusted):
    reply = http.call("GET", f"{trusted}/text", {}, "", 5)
    assert (reply.kind, reply.body) == ("ok", "plain words")


def test_an_answer_that_is_not_2xx_is_a_failure_with_its_status(trusted):
    reply = http.call("GET", f"{trusted}/status/503", {}, "", 5)
    assert (reply.kind, reply.status) == ("status", 503)


def test_a_redirect_is_not_followed(trusted):
    reply = http.call("GET", f"{trusted}/redirect", {}, "", 5)
    assert (reply.kind, reply.status) == ("status", 302)
    assert [seen["path"] for seen in Handler.seen] == ["/redirect"]


def test_an_answer_too_big_is_cut(trusted):
    reply = http.call("GET", f"{trusted}/big", {}, "", 5)
    assert (reply.kind, reply.truncated, len(reply.body)) == ("ok", True, http.MAX_BYTES)


def test_a_slow_answer_runs_out_of_time(trusted):
    started = time.monotonic()
    reply = http.call("GET", f"{trusted}/slow", {}, "", 1)
    assert reply.kind == "timeout"
    assert time.monotonic() - started < 2.4


def test_a_certificate_it_cannot_trust_fails(settings, server):
    settings.FLOW_HTTP_TRUSTED_ADDRESSES = ["127.0.0.1", "::1"]
    settings.FLOW_HTTP_CA_BUNDLE = None
    reply = http.call("GET", f"https://localhost:{server['port']}/ok", {}, "", 5)
    assert reply.kind == "failed"


# SSRF: never inside the business, the machine or the cloud — against the real server too.


def test_the_machine_itself_is_blocked_even_with_a_real_server_there(settings, server):
    settings.FLOW_HTTP_CA_BUNDLE = server["ca"]
    settings.FLOW_HTTP_TRUSTED_ADDRESSES = []
    Handler.seen.clear()
    for url in (f"https://localhost:{server['port']}/ok", f"https://127.0.0.1:{server['port']}/ok"):
        assert http.call("GET", url, {}, "", 5).kind == "blocked", url
    assert Handler.seen == []  # nothing reached it


def test_it_connects_to_the_address_it_checked_never_to_a_second_answer(trusted, server, monkeypatch):
    # DNS rebinding: the name answers once with an address that passes, then with anything else. The call
    # goes to the address that was checked; it never asks the name again.
    real = socket.getaddrinfo
    answers = []

    def resolver(host, *args, **kwargs):
        if host != "api.test":
            return real(host, *args, **kwargs)
        answers.append(host)
        if len(answers) > 1:
            raise socket.gaierror("a second answer, never asked for")
        return real("127.0.0.1", *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    reply = http.call("GET", f"https://api.test:{server['port']}/ok", {}, "", 5)
    assert (reply.kind, reply.status) == ("ok", 201)
    assert answers == ["api.test"]
    assert Handler.seen[-1]["headers"]["Host"] == f"api.test:{server['port']}"


def test_a_name_that_gives_one_address_inside_is_blocked_whole(trusted, monkeypatch):
    # A public address next to a private one: the name is not called at all.
    def resolver(host, port, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    assert http.call("GET", "https://mixed.test/ok", {}, "", 1).kind == "blocked"


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.3.4",
        "192.168.1.10",
        "169.254.169.254",  # the cloud's metadata
        "100.64.0.1",  # carrier-grade NAT
        "0.0.0.0",
        "::1",
        "fd00::1",
        "fe80::1",
        "::ffff:127.0.0.1",  # IPv4 dressed as IPv6
        "64:ff9b::a9fe:a9fe",  # NAT64 of 169.254.169.254
        "2002:7f00:1::",  # 6to4 of 127.0.0.1
        "224.0.0.1",
    ],
)
def test_an_address_inside_is_blocked(address):
    assert http.blocked_address(ipaddress.ip_address(address)) is True


def test_a_public_address_is_not_blocked():
    assert http.blocked_address(ipaddress.ip_address("8.8.8.8")) is False
    assert http.blocked_address(ipaddress.ip_address("2001:4860:4860::8888")) is False


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/x",  # not https
        "https://user:pw@example.com/x",  # credentials in the address
        "https://",  # no host
        "ftp://example.com",
        "example.com/x",
    ],
)
def test_an_address_that_is_not_plain_https_is_refused(url):
    assert http.call("GET", url, {}, "", 5).kind == "invalid"


def test_the_origin_of_an_address():
    assert http.origin("https://API.Example.com/v1/orders?x=1") == "https://api.example.com"
    assert http.origin("https://api.example.com:8443/x") == "https://api.example.com:8443"
    assert http.origin("https://api.example.com:443/x") == "https://api.example.com"
    assert http.origin("http://api.example.com/x") is None
    assert http.origin("https://u:p@api.example.com/x") is None
