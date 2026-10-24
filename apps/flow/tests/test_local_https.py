"""The local HTTPS server of the FLOW-F27 tests (``local_https``) takes a client that hangs up before its
answer is done as what clients do — the HTTP client gives up on a slow answer, or stops reading at
``MAX_BYTES`` — and never prints from its request threads: a request thread has no stderr of its own, and
printing there once left an unhandled thread exception (``Bad file descriptor``) in a test of another
app. Whatever is not a hang-up is kept, and stopping the server fails on it."""

import http.client
import socket
import ssl
import struct
import threading
import time

import pytest

from .local_https import Handler, start


@pytest.fixture
def escaped(monkeypatch):
    """What escapes any thread during the test (pytest would only warn about it, under another test)."""
    seen = []
    monkeypatch.setattr(threading, "excepthook", seen.append)
    return seen


@pytest.fixture
def unstarted():
    """A thread named as a request that ``threading.enumerate()`` already lists but that has not started:
    ``Thread.start()`` leaves every new thread so for a moment (in ``_limbo``), a request of this test's server
    or of another one in the same process. Waiting for the answers must not join it: ``join`` refuses a thread
    that has not started, and under xdist that turned the deploy after hub#237 red."""
    thread = threading.Thread(target=lambda: None, name="Thread-0 (process_request_thread)")
    with threading._active_limbo_lock:
        threading._limbo[thread] = thread
    yield thread
    with threading._active_limbo_lock:
        del threading._limbo[thread]


@pytest.fixture
def answering(tmp_path):
    """The server, started for this test alone; ``next(answering, None)`` stops it as the fixture of the flow
    tests does, and so says what it kept."""
    answering = start(tmp_path)
    yield answering
    answering.close()  # a test that failed before stopping it


def _answered(server):
    """Waits for the requests the server took: its own threads, all started."""
    for request in list(server["requests"]):
        request.join(timeout=10)


def _ask(server, path):
    connection = http.client.HTTPSConnection(
        "localhost", server["port"], timeout=5, context=ssl.create_default_context(cafile=server["ca"])
    )
    try:
        connection.request("GET", path)
        return connection.getresponse().status
    finally:
        connection.close()


def _hang_up_once(server, request, taken):
    """Sends ``request`` and, once ``taken()`` says the server has it, hangs up with a reset."""
    raw = socket.create_connection(("127.0.0.1", server["port"]), timeout=5)
    raw.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    with ssl.create_default_context(cafile=server["ca"]).wrap_socket(raw, server_hostname="localhost") as tls:
        tls.sendall(request)
        deadline = time.monotonic() + 5
        while not taken():
            assert time.monotonic() < deadline, "the server never took the request"
            time.sleep(0.01)


def _hang_up_while_it_writes(server):
    """Asks for ``/slow`` and hangs up once the server has read the request: the answer it writes a moment
    later meets a closed line, as when the HTTP client gives up waiting."""
    _hang_up_once(
        server,
        b"GET /slow HTTP/1.1\r\nHost: localhost\r\n\r\n",
        lambda: any(seen["path"] == "/slow" for seen in Handler.seen),
    )


def _hang_up_while_it_reads(server):
    """Announces a body that never comes and hangs up while the server waits for it."""
    taken = len(server["requests"])
    _hang_up_once(
        server,
        b"POST /orders HTTP/1.1\r\nHost: localhost\r\nContent-Length: 10\r\n\r\n",
        lambda: len(server["requests"]) > taken,
    )


@pytest.mark.parametrize(
    ("hang_up", "cuts"),
    [
        (_hang_up_while_it_writes, ([BrokenPipeError], [ConnectionResetError])),
        (_hang_up_while_it_reads, ([ConnectionResetError],)),
    ],
)
def test_a_client_that_hangs_up_is_no_error_and_the_server_answers_the_next_one(
    answering, escaped, capsys, unstarted, hang_up, cuts
):
    server = next(answering)
    Handler.seen.clear()

    hang_up(server)
    _answered(server)

    assert capsys.readouterr().err == ""  # nothing printed from its threads
    assert escaped == []
    assert _ask(server, "/ok") == 201
    assert [type(cut) for cut in server["hangups"]] in cuts
    assert server["errors"] == []
    next(answering, None)  # stopping it fails on nothing


def test_an_error_that_is_not_a_hang_up_is_kept_and_stopping_the_server_fails_on_it(
    answering, escaped, capsys, unstarted, monkeypatch
):
    def broken(handler):
        raise RuntimeError("the handler broke")

    monkeypatch.setattr(Handler, "do_GET", broken)
    server = next(answering)

    with pytest.raises(http.client.RemoteDisconnected):
        _ask(server, "/ok")
    _answered(server)

    assert capsys.readouterr().err == ""  # nothing printed from its threads
    assert escaped == []
    assert [type(error) for error in server["errors"]] == [RuntimeError]
    assert server["hangups"] == []
    with pytest.raises(AssertionError, match="the handler broke"):
        next(answering, None)


def test_stopping_the_server_waits_for_the_answers_it_is_still_writing(answering, unstarted):
    server = next(answering)
    Handler.seen.clear()

    _hang_up_while_it_writes(server)
    next(answering, None)

    assert len(server["hangups"]) == 1  # its request thread ended before the stop did: none outlives it
