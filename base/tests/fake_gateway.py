"""erplora.com's AI gateway on ``127.0.0.1``, for the tests of the Hub's assistant (``base/assistant.py``).

The Hub talks to it with its real network code (``httpx``, signed as every ``/internal`` call): nothing of ours is
patched. A test scripts what each door answers (``FakeGateway.reply``) in the gateway's own contract
(``saas`` ``assistant/WORKBOOK.md`` «Las puertas del Hub») and reads back what the Hub sent (``FakeGateway.requests``),
signature included. A door nothing was scripted for answers 404 ``hub_unknown``, as the gateway does for a business
it does not know.
"""

import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from base import signing

#: The shared secret of ``/internal`` in these tests.
SECRET = "test-internal-secret"


@dataclass
class Reply:
    status: int = 200
    json: Any = None
    #: A streamed answer: each item is one ``data:`` line (a dict as JSON, a string as it is, e.g. ``[DONE]``).
    frames: list[Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    #: Hang up after this many frames, without ``[DONE]`` (a connection that dies half way).
    cut_after: int | None = None


@dataclass
class Seen:
    path: str
    headers: dict[str, str]
    body: Any
    raw: bytes


class FakeGateway:
    def __init__(self) -> None:
        self._replies: dict[str, list[Reply]] = {}
        self.requests: list[Seen] = []
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def reply(self, path: str, **reply: Any) -> None:
        """Script the next answer of ``path`` (``/internal/assistant/chat/stream``…), in the order scripted."""
        with self._lock:
            self._replies.setdefault(path, []).append(Reply(**reply))

    def turn(self, *frames: Any, **reply: Any) -> None:
        """Script a streamed turn of ``/internal/assistant/chat/stream``: its frames, then ``[DONE]``."""
        self.reply("/internal/assistant/chat/stream", frames=[*frames, "[DONE]"], **reply)

    def sent(self, path: str) -> list[Seen]:
        with self._lock:
            return [seen for seen in self.requests if seen.path == path]

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _next(self, path: str) -> Reply | None:
        with self._lock:
            queued = self._replies.get(path)
            return queued.pop(0) if queued else None

    def _handler(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, format, *args):  # noqa: A002 - the stdlib's name
                return

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                try:
                    body = json.loads(raw) if raw else None
                except ValueError:
                    body = raw.decode(errors="replace")
                with fake._lock:
                    fake.requests.append(Seen(self.path, {k.lower(): v for k, v in self.headers.items()}, body, raw))
                reply = fake._next(self.path) or Reply(
                    status=404, json={"error": {"code": "hub_unknown", "message": "No such business."}}
                )
                self.send_response(reply.status)
                for name, value in reply.headers.items():
                    self.send_header(name, value)
                if reply.frames is not None:
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    for index, frame in enumerate(reply.frames):
                        if reply.cut_after is not None and index >= reply.cut_after:
                            return
                        line = frame if isinstance(frame, str) else json.dumps(frame)
                        self.wfile.write(f"data: {line}\n\n".encode())
                        self.wfile.flush()
                    return
                payload = json.dumps(reply.json).encode()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        return Handler


@pytest.fixture
def gateway(settings):
    """A started ``FakeGateway`` the Hub calls (``SAAS_INTERNAL_URL``) with the tests' secret."""
    fake = FakeGateway()
    fake.start()
    settings.SAAS_INTERNAL_URL = fake.url
    settings.INTERNAL_SHARED_SECRET = SECRET
    yield fake
    fake.stop()


def signed(seen: Seen) -> bool:
    """Whether the Hub signed ``seen`` as every ``/internal`` call (v2 over method, path and body)."""
    return signing.verify_signed("POST", seen.path, seen.raw, seen.headers, secrets=[SECRET], now=int(time.time()))
