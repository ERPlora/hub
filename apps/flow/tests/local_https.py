"""A real local HTTPS server for the tests of «Call another system» (FLOW-F27): a certificate made here for
``localhost``, ``api.test`` and ``127.0.0.1``, IPv4 and IPv6, recording what it receives. The other system
of a test is this server, never a patched client.

A client that hangs up before its answer is done is what clients do (the HTTP client gives up on
``/slow`` and stops reading ``/big`` at ``MAX_BYTES``): the server counts it in ``hangups``. Any other
error of a request is kept in ``errors``, never printed — a request thread has no stderr of its own, and
printing there once left an unhandled thread exception in a test of another app — and stopping the server
fails on it."""

import datetime as dt
import ipaddress
import json
import socket
import ssl
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from apps.flow import http


def _certificate(directory):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.DNSName("api.test"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_file, key_file = directory / "cert.pem", directory / "key.pem"
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    return cert_file, key_file


class Handler(BaseHTTPRequestHandler):
    seen: list[dict] = []
    timeout = 10  # a client that stalls ends its request, so stopping the server never waits for ever

    def log_message(self, *args):  # quiet test server
        pass

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError) as cut:
            self.server.hangups.append(cut)

    def _answer(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode() if length else ""
        Handler.seen.append({"method": self.command, "path": self.path, "headers": dict(self.headers), "body": body})
        if self.path.startswith("/status/"):
            code = int(self.path.rsplit("/", 1)[1])
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            payload = json.dumps({"error": "nope"}).encode()
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/slow":
            time.sleep(2.5)
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "https://localhost/ok")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path == "/big":
            payload = b"x" * (http.MAX_BYTES + 10)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/text":
            payload = "plain words".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        payload = json.dumps({"ok": True, "method": self.command, "body": body}).encode()
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _answer


class DualStack(ThreadingHTTPServer):
    """``localhost`` gives ::1 and 127.0.0.1: the server answers on both. Its request threads are waited for
    when it stops: none outlives it. Each one, once running, is in ``requests``: a test waits there for its own
    answers, never for whatever ``threading.enumerate()`` lists (a thread not started yet among them)."""

    address_family = socket.AF_INET6
    daemon_threads = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.requests: list[threading.Thread] = []
        self.hangups: list[OSError] = []
        self.errors: list[BaseException] = []

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()

    def process_request_thread(self, request, client_address):
        self.requests.append(threading.current_thread())  # from inside: it has started, so it can be joined
        super().process_request_thread(request, client_address)

    def handle_error(self, request, client_address):
        self.errors.append(sys.exception())


def start(directory):
    """Starts the server; yields ``{"port", "ca", "requests", "hangups", "errors"}`` until it is stopped, and
    stopping it fails on the errors its requests kept."""
    cert_file, key_file = _certificate(directory)
    httpd = DualStack(("::", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield {
            "port": httpd.server_address[1],
            "ca": str(cert_file),
            "requests": httpd.requests,
            "hangups": httpd.hangups,
            "errors": httpd.errors,
        }
    finally:
        httpd.shutdown()
        httpd.server_close()
    if httpd.errors:
        raise AssertionError(
            "The local HTTPS server failed answering:\n"
            + "\n".join("".join(traceback.format_exception(error)) for error in httpd.errors)
        )
