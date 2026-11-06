"""The HTTP server of the tests' doubles (``base/tests/fake_gateway.py``), as saas#283 left the SaaS's.

Importable without Django.
"""

import sys
from http.server import ThreadingHTTPServer


class QuietServer(ThreadingHTTPServer):
    """A client that cuts the conversation is what these tests do, not a failure of the double.

    Its request threads are daemon, as ``ThreadingHTTPServer``'s: stopping the double never waits for a client that
    will not finish. ``socketserver`` prints what a request raises to stderr from such a thread, and a daemon thread
    caught holding stderr's lock as the interpreter closes aborts it: code 134 after every test has passed (hub#840). A
    client gone (``BrokenPipeError``, ``ConnectionResetError``) says nothing; anything else a handler raises is a real
    failure and is still printed.
    """

    def handle_error(self, request, client_address):
        if isinstance(sys.exception(), ConnectionError):
            return
        super().handle_error(request, client_address)
