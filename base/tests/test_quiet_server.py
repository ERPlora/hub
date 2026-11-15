"""The server of the tests' doubles: a client that cuts says nothing, anything else still does (hub#840).

The harm is an interpreter that aborts on its way out, code 134 after every test has passed: ``socketserver`` prints
what a request raises to stderr from a daemon thread, and a daemon thread caught holding stderr's lock as the
interpreter closes is fatal. The Hub's assistant tests cut conversations on purpose: a turn the Hub stops reading, a
voice it stops waiting for (``test_assistant_speak.py``: the Hub waits 0.2 s, the door answers in 1 s). The SaaS had
the same harm and has the same cure (its own ``base/tests/quiet_server.py``). That every double answering in threads
runs on it is ``tests/test_guardrails.py`` (j).
"""

import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from base.tests.fake_gateway import FakeGateway

REPO = Path(__file__).resolve().parents[2]
STREAM = "/internal/assistant/chat/stream"
SYNTHESIZE = "/internal/speech/synthesize"


def handlers() -> list[threading.Thread]:
    """The request threads of any double alive in this process."""
    return [thread for thread in threading.enumerate() if "process_request_thread" in thread.name]


def wait_until(condition, what: str, seconds: float = 30) -> None:
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert condition(), what


def settle() -> None:
    """Until no request thread of a double is alive (each has said, or kept quiet about, how its request ended)."""
    wait_until(lambda: not handlers(), "a request thread of a double never ended")


def ask(fake: FakeGateway, path: str, body: bytes = b"", length: int | None = None) -> socket.socket:
    client = socket.create_connection(fake._server.server_address)
    length = len(body) if length is None else length
    client.sendall(f"POST {path} HTTP/1.0\r\nContent-Length: {length}\r\n\r\n".encode() + body)
    return client


def resets(client: socket.socket) -> socket.socket:
    """Closing it resets the connection (``ConnectionResetError`` on the double's side), as a process that dies."""
    client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    return client


# Each conversation leaves a client the caller closes: the double is then half way through it.


def mid_stream(fake: FakeGateway) -> socket.socket:
    """A turn the client stops reading half way: far more than the sockets hold, so the double is still writing."""
    fake.reply(STREAM, frames=[{"text": "x" * 1000}] * 5000)
    client = ask(fake, STREAM)
    client.recv(1)  # the answer has begun
    return resets(client)


def mid_request(fake: FakeGateway) -> socket.socket:
    """A client that goes before its request is whole: the double is still reading it."""
    client = ask(fake, STREAM, b"only a part of it", length=100)
    wait_until(handlers, "the double never took the request")
    return resets(client)


def before_the_answer(fake: FakeGateway) -> socket.socket:
    """A client that stops waiting for a slow door and closes as ``httpx`` does: the double writes to nobody
    (``BrokenPipeError``)."""
    fake.reply(SYNTHESIZE, content=b"mp3", content_type="audio/mpeg", delay=1.0)
    client = ask(fake, SYNTHESIZE)
    wait_until(lambda: fake.sent(SYNTHESIZE), "the double never had the call")  # it has it and waits to answer
    return client


CONVERSATIONS = [
    pytest.param(mid_stream, id="mid-stream"),
    pytest.param(mid_request, id="mid-request"),
    pytest.param(before_the_answer, id="before-the-answer"),
]


@pytest.mark.parametrize("conversation", CONVERSATIONS)
def test_a_client_that_cuts_leaves_no_trace_on_stderr(conversation, capsys):
    settle()  # a request of an earlier test that ends now would write here
    fake = FakeGateway()
    fake.start()
    try:
        conversation(fake).close()
        settle()
    finally:
        fake.stop()

    assert capsys.readouterr().err == ""


#: Each conversation runs in a Python of its own, which makes the race certain: the client cuts as the interpreter
#: closes, and its stderr never finishes a write, so whoever writes there keeps the lock.
CUT_AS_THE_INTERPRETER_CLOSES = """
import atexit, io, sys, threading, time

caught = threading.Event()

class NeverEnds(io.RawIOBase):
    def writable(self):
        return True

    def write(self, data):
        caught.set()
        threading.Event().wait()

def cut():
    if "client" not in globals():  # the conversation never began: its traceback is on the real stderr
        return
    sys.stderr = io.TextIOWrapper(io.BufferedWriter(NeverEnds()), line_buffering=True)
    client.close()
    deadline = time.monotonic() + 30
    while handlers() and not caught.is_set() and time.monotonic() < deadline:
        time.sleep(0.01)

atexit.register(cut)  # the first in is the last out: after logging has flushed the stderr it knows

from base.tests.fake_gateway import FakeGateway
from base.tests.test_quiet_server import handlers, {conversation}

fake = FakeGateway()
fake.start()
client = {conversation}(fake)
"""


@pytest.mark.parametrize("conversation", CONVERSATIONS)
def test_a_client_that_cuts_does_not_abort_the_interpreter(conversation):
    ended = subprocess.run(
        [sys.executable, "-c", CUT_AS_THE_INTERPRETER_CLOSES.format(conversation=conversation.__name__)],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert ended.returncode == 0, ended.stderr


@pytest.mark.parametrize("error", [ZeroDivisionError, ValueError, OSError])  # OSError: the parent of what it hushes
def test_a_double_that_breaks_still_says_so(error, capsys, monkeypatch):
    def breaks(path):
        raise error("the double broke")

    fake = FakeGateway()
    monkeypatch.setattr(fake, "_next", breaks)
    fake.start()
    try:
        with ask(fake, STREAM) as client:
            assert client.recv(1) == b""  # the double hangs up only once it has said what broke
    finally:
        fake.stop()

    assert f"{error.__name__}: the double broke" in capsys.readouterr().err


def test_a_request_still_arriving_does_not_hold_the_double_up():
    """Its request threads are daemon: stopping it never waits for a client that will not finish."""
    settle()
    fake = FakeGateway()
    fake.start()
    client = mid_request(fake)
    stopping = threading.Thread(target=fake.stop)
    stopping.start()
    stopping.join(5)
    held = stopping.is_alive()
    client.close()
    stopping.join()
    settle()

    assert not held
