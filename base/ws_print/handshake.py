"""The handshake of the print channel: only a page of the hub's own host opens it, and the hub's gate says
whether it serves."""

import io
import json
from urllib.parse import urlsplit

from django.core.exceptions import SuspiciousOperation
from django.core.handlers.asgi import ASGIRequest
from django.http import Http404, HttpRequest
from django.utils import translation
from django.utils.translation import gettext

from base import middleware
from base.ws_print.refusals import Refusal


class HandshakeMixin:
    """The handshake of a ``PrintSocket`` (``base.ws_print.protocol``), which keeps the scope and the request."""

    def _admit(self) -> Refusal | bool:
        """``False``: refuse the handshake (a foreign origin, a host Django refuses); a ``Refusal``: accept it and
        say why it ends at once (no hub); ``True``: a hub's own page is calling."""
        request = _http_request(self.scope)
        try:
            if not _same_origin(request):
                return False
        except SuspiciousOperation:
            return False
        self.language = translation.get_language_from_request(request)
        with translation.override(self.language):
            try:
                answer = middleware.HubHostRequiredMiddleware(_no_view).process_request(request)
            except Http404:
                return Refusal("not_found", gettext("Not found"), status=404)
            if getattr(request, "platform_host", False):
                return Refusal("not_found", gettext("Not found"), status=404)
            if answer is not None:
                error = json.loads(answer.content)["error"]
                return Refusal(error["code"], error["message"], status=answer.status_code)
        request.LANGUAGE_CODE = self.language
        self.request = request
        return True


def _http_request(scope: dict) -> HttpRequest:
    """The handshake as a Django request: the Host, the cookies and the headers the HTTP doors read."""
    scheme = "https" if scope.get("scheme") == "wss" else "http"
    return ASGIRequest({**scope, "type": "http", "method": "GET", "scheme": scheme}, io.BytesIO())


def _same_origin(request: HttpRequest) -> bool:
    """Whether the handshake comes from a page of this very host (a browser always sends ``Origin``)."""
    origin = request.headers.get("Origin")
    if not origin:
        return False
    parts = urlsplit(origin)
    scheme = "https" if request.is_secure() else "http"
    return parts.scheme == scheme and parts.netloc.lower() == request.get_host().lower()


def _no_view(request: HttpRequest) -> None:
    """The gate is asked for its decision only; nothing comes after it."""
    raise AssertionError("The print channel runs no view.")
