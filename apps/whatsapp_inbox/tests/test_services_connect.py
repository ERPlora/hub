"""Connecting, reconnecting and disconnecting the business's number from the inbox's Settings (WHATSAPP_INBOX-F01,
F02), through erplora.com's doors 10–12 (WORKBOOK «Contrato con el SaaS»).

``respx`` stands in for the transport to erplora.com only. What is checked: the business each door is asked for, what
the screen may open Meta's window with (and why not), how each refusal reads, that erplora.com's answer is the
business's number at once (its own row, never another business's), and that nothing waits for erplora.com inside a
transaction.
"""

import httpx
import psycopg
import pytest
import respx
from django.db import connection
from live.errors import OperationError, PermissionDenied
from live.models import OutboxEvent

from apps.whatsapp_inbox.models import Channel
from apps.whatsapp_inbox.tests.conftest import A, B, connect, ctx_for, run, system

pytestmark = pytest.mark.django_db

SAAS = "http://saas.test"
CONFIG = f"{SAAS}/internal/whatsapp/config"
CONNECT = f"{SAAS}/internal/whatsapp/connect"
DISCONNECT = f"{SAAS}/internal/whatsapp/disconnect"
RETURN_PAGE = "https://erplora.com/whatsapp/return"
CONFIGURED = {
    "configured": True,
    "app_id": "1481226093843982",
    "config_id": "1101452998214123",
    "graph_version": "v25.0",
    "redirect_uri": RETURN_PAGE,
}
WINDOW = {
    "code": "AQD-one-time",
    "event": "FINISH",
    "waba_id": "102290129340398",
    "phone_number_id": "106540352242922",
    "business_id": "2729063490586005",
}
CONNECTED = {"connected": True, "phone_number": "+34910000000", "display_name": "Peluquería Ana", "history_requested": False}


@pytest.fixture(autouse=True)
def popups_kept(settings):
    """A Hub whose pages keep the window they open (the COOP base sets; Django's default cuts it)."""
    settings.SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"


def events(name: str) -> list[dict]:
    return [event.payload for event in OutboxEvent.objects.filter(name=name)]


def refusal(name: str, payload: dict | None = None, ctx=None) -> OperationError:
    with pytest.raises(OperationError) as raised:
        run(name, payload, ctx)
    return raised.value


def envelope(status: int, code: str, message: str = "") -> httpx.Response:
    return httpx.Response(status, json={"error": {"code": code, "message": message}})


# ── WHATSAPP_INBOX-F01 What opens Meta's window (door 10) ───────────────────────────────────────


@respx.mock
def test_meta_s_window_opens_with_erplora_s_public_ids_for_this_business():
    route = respx.post(CONFIG).mock(return_value=httpx.Response(200, json=CONFIGURED))
    out = run("whatsapp_inbox.channel.prepare")
    assert out.model_dump() == {"available": True, "reason": None, **{k: v for k, v in CONFIGURED.items() if k != "configured"}}
    assert route.calls.last.request.content == b'{"hub":"a"}'


@respx.mock
def test_without_meta_s_app_on_erplora_there_is_nothing_to_open():
    respx.post(CONFIG).mock(
        return_value=httpx.Response(200, json={"configured": False, "app_id": "", "config_id": "", "graph_version": "v25.0"})
    )
    out = run("whatsapp_inbox.channel.prepare")
    assert (out.available, out.reason, out.app_id, out.config_id) == (False, "not_configured", "", "")


@pytest.mark.parametrize(
    "redirect",
    [
        None,  # erplora.com without its return page yet (its door 10 does not name one)
        "",
        "https://evil.example/whatsapp/return",  # never a page outside erplora.com
        "http://erplora.com/whatsapp/return",  # never over plain http
        "erplora.com/whatsapp/return",
    ],
)
@respx.mock
def test_the_code_only_comes_back_through_erplora_s_own_return_page(redirect):
    answer = {**CONFIGURED, "redirect_uri": redirect} if redirect is not None else {k: v for k, v in CONFIGURED.items() if k != "redirect_uri"}
    respx.post(CONFIG).mock(return_value=httpx.Response(200, json=answer))
    out = run("whatsapp_inbox.channel.prepare")
    assert (out.available, out.reason, out.redirect_uri) == (False, "window_unavailable", "")


@respx.mock
def test_a_hub_that_cuts_the_windows_it_opens_does_not_offer_meta_s(settings):
    # Django's default COOP (same-origin) leaves Meta's window without its opener: its answer would never arrive.
    settings.SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
    respx.post(CONFIG).mock(return_value=httpx.Response(200, json=CONFIGURED))
    out = run("whatsapp_inbox.channel.prepare")
    assert (out.available, out.reason) == (False, "popups_blocked")


@pytest.mark.parametrize(
    "field_value",
    [("app_id", "abc"), ("config_id", ""), ("graph_version", "25"), ("configured", "yes")],
)
@respx.mock
def test_an_answer_the_hub_does_not_understand_opens_nothing(field_value):
    field, value = field_value
    respx.post(CONFIG).mock(return_value=httpx.Response(200, json={**CONFIGURED, field: value}))
    error = refusal("whatsapp_inbox.channel.prepare")
    assert (error.status, error.code) == (503, "whatsapp_inbox.saas_unreachable")


@respx.mock
def test_erplora_out_of_reach_is_said_with_the_old_hub_s_words():
    respx.post(CONFIG).mock(side_effect=httpx.ConnectError("refused"))
    error = refusal("whatsapp_inbox.channel.prepare")
    assert (error.status, error.code) == (503, "whatsapp_inbox.saas_unreachable")
    assert error.message == "Your hub could not reach erplora.com. Check the connection and try again."


@respx.mock
def test_a_demo_or_a_business_erplora_does_not_know_cannot_connect_a_number():
    # gh:saas#2604: a demo connected a number it could never send from.
    respx.post(CONFIG).mock(return_value=envelope(404, "hub_unknown", "No such business."))
    error = refusal("whatsapp_inbox.channel.prepare")
    assert (error.status, error.code) == (409, "whatsapp_inbox.hub_unknown")


def test_a_server_without_erplora_s_address_says_so(settings):
    settings.SAAS_INTERNAL_URL = ""
    error = refusal("whatsapp_inbox.channel.prepare")
    assert (error.status, error.code) == (409, "whatsapp_inbox.saas_unconfigured")


# ── WHATSAPP_INBOX-F01 Connecting the number Meta's window chose (door 11) ──────────────────────


@respx.mock
def test_the_number_meta_s_window_chose_is_the_business_s_at_once():
    route = respx.post(CONNECT).mock(return_value=httpx.Response(200, json=CONNECTED))
    system("whatsapp_inbox.channel.sync", {"version": 9, "status": "not_connected", "monthly_limit": 150}, B)

    out = run("whatsapp_inbox.channel.connect", WINDOW)

    assert out.model_dump() == CONNECTED
    assert route.calls.last.request.content == (
        b'{"hub":"a","code":"AQD-one-time","event":"FINISH","waba_id":"102290129340398",'
        b'"phone_number_id":"106540352242922","business_id":"2729063490586005"}'
    )
    a = run("whatsapp_inbox.channel.get", {}, ctx_for(scope=A))
    assert (a.status, a.phone_number, a.display_name) == ("connected", "+34910000000", "Peluquería Ana")
    # B's number is B's: connecting A's never touches it.
    b = run("whatsapp_inbox.channel.get", {}, ctx_for(scope=B))
    assert (b.status, b.phone_number, b.monthly_limit) == ("not_connected", "", 150)
    assert events("whatsapp_inbox.channel.connected") == [{"history_requested": False}]


@respx.mock
def test_erplora_s_next_photo_still_wins_over_its_answer():
    respx.post(CONNECT).mock(return_value=httpx.Response(200, json=CONNECTED))
    connect(version=5, status="not_connected", phone_number="", display_name="")
    run("whatsapp_inbox.channel.connect", WINDOW)
    assert Channel.objects.get(host="a").version == 5  # the answer is no photo: its version stays
    assert connect(version=6, status="reconnect_needed").applied is True
    assert run("whatsapp_inbox.channel.get").status == "reconnect_needed"


@pytest.mark.parametrize(
    ("answer", "status", "code", "message"),
    [
        (
            envelope(409, "whatsapp.meta_rejected", "This authorization code has expired."),
            409,
            "whatsapp_inbox.meta_rejected",
            "Meta did not accept the connection: This authorization code has expired.",
        ),
        (
            envelope(409, "whatsapp.number_not_in_account"),
            409,
            "whatsapp_inbox.number_not_in_account",
            "The number chosen in Meta's window is not in that WhatsApp Business account: nothing was connected.",
        ),
        (
            envelope(409, "whatsapp.number_not_chosen"),
            409,
            "whatsapp_inbox.number_not_chosen",
            "That WhatsApp Business account has several numbers: choose one in Meta's window.",
        ),
        (
            envelope(429, "whatsapp.meta_rate_limited"),
            409,
            "whatsapp_inbox.meta_rate_limited",
            "Meta asks to wait before trying again. Try again in a few minutes.",
        ),
        (
            envelope(503, "whatsapp.meta_unreachable"),
            503,
            "whatsapp_inbox.meta_unreachable",
            "Meta did not answer: nothing was connected. Try again.",
        ),
        (
            envelope(502, "whatsapp.meta_no_token"),
            503,
            "whatsapp_inbox.meta_unreachable",
            "Meta did not answer: nothing was connected. Try again.",
        ),
        (
            envelope(503, "whatsapp.not_configured"),
            409,
            "whatsapp_inbox.whatsapp_unavailable",
            "WhatsApp is not available in ERPlora yet.",
        ),
        (
            envelope(404, "hub_unknown"),
            409,
            "whatsapp_inbox.hub_unknown",
            "erplora.com does not know this business: a demo cannot connect a WhatsApp number.",
        ),
        (
            envelope(401, "unauthorized"),
            503,
            "whatsapp_inbox.saas_refused",
            "erplora.com did not take the request (unauthorized). Try again later.",
        ),
    ],
)
@respx.mock
def test_each_refusal_says_why_and_connects_nothing(answer, status, code, message):
    respx.post(CONNECT).mock(return_value=answer)
    error = refusal("whatsapp_inbox.channel.connect", WINDOW)
    assert (error.status, error.code, error.message) == (status, code, message)
    assert not Channel.objects.exists() and not events("whatsapp_inbox.channel.connected")


@respx.mock
def test_a_lost_answer_is_neither_connected_nor_not():
    respx.post(CONNECT).mock(side_effect=httpx.ReadTimeout("slow"))
    error = refusal("whatsapp_inbox.channel.connect", WINDOW)
    assert (error.status, error.code) == (503, "whatsapp_inbox.connect_unknown")
    respx.post(CONNECT).mock(return_value=httpx.Response(200, json={"connected": True, "phone_number": 34}))
    assert refusal("whatsapp_inbox.channel.connect", WINDOW).code == "whatsapp_inbox.connect_unknown"
    assert not Channel.objects.exists()


# ── WHATSAPP_INBOX-F02 Disconnecting (door 12) ──────────────────────────────────────────────────


@respx.mock
def test_disconnecting_leaves_the_business_without_its_number_and_keeps_the_month():
    connect(version=3)
    route = respx.post(DISCONNECT).mock(return_value=httpx.Response(200, json={"disconnected": True}))

    assert run("whatsapp_inbox.channel.disconnect").model_dump() == {"disconnected": True}

    assert route.calls.last.request.content == b'{"hub":"a"}'
    now = run("whatsapp_inbox.channel.get")
    assert (now.status, now.phone_number, now.display_name, now.monthly_limit) == ("not_connected", "", "", 150)
    assert Channel.objects.get(host="a").version == 3
    assert events("whatsapp_inbox.channel.disconnected") == [{}]


@respx.mock
def test_erplora_without_a_number_leaves_the_business_not_connected_and_says_so_once():
    respx.post(DISCONNECT).mock(return_value=httpx.Response(200, json={"disconnected": False}))
    connect(version=3)  # the Hub still believed it connected
    assert run("whatsapp_inbox.channel.disconnect").disconnected is False
    assert run("whatsapp_inbox.channel.get").status == "not_connected"
    run("whatsapp_inbox.channel.disconnect")
    assert len(events("whatsapp_inbox.channel.disconnected")) == 1


@respx.mock
def test_a_disconnection_erplora_did_not_confirm_changes_nothing_here():
    connect(version=3)
    respx.post(DISCONNECT).mock(side_effect=httpx.ReadTimeout("slow"))
    assert refusal("whatsapp_inbox.channel.disconnect").code == "whatsapp_inbox.disconnect_unknown"
    respx.post(DISCONNECT).mock(side_effect=httpx.ConnectError("refused"))
    assert refusal("whatsapp_inbox.channel.disconnect").code == "whatsapp_inbox.saas_unreachable"
    assert run("whatsapp_inbox.channel.get").status == "connected"


# ── Who may, and nothing held while erplora.com answers ─────────────────────────────────────────


@pytest.mark.parametrize("role", ["hub_manager", "hub_employee"])
@pytest.mark.parametrize(
    ("name", "payload"),
    [("whatsapp_inbox.channel.prepare", {}), ("whatsapp_inbox.channel.connect", WINDOW), ("whatsapp_inbox.channel.disconnect", {})],
)
def test_only_the_owner_and_the_administrators_connect_or_disconnect(role, name, payload):
    # gh:saas#2538: an employee could disconnect the business's WhatsApp.
    with pytest.raises(PermissionDenied):
        run(name, payload, ctx_for(role))


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    ("name", "url", "payload", "answer"),
    [
        ("whatsapp_inbox.channel.prepare", CONFIG, {}, CONFIGURED),
        ("whatsapp_inbox.channel.connect", CONNECT, WINDOW, CONNECTED),
        ("whatsapp_inbox.channel.disconnect", DISCONNECT, {}, {"disconnected": True}),
    ],
)
@respx.mock
def test_no_transaction_is_open_while_erplora_answers(name, url, payload, answer):
    seen = []

    def answering(request):
        seen.append(connection.connection.info.transaction_status if connection.connection else None)
        return httpx.Response(200, json=answer)

    respx.post(url).mock(side_effect=answering)
    run(name, payload)
    assert seen and seen[0] in (None, psycopg.pq.TransactionStatus.IDLE)
