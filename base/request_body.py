"""A route that takes a larger body than Django's ``DATA_UPLOAD_MAX_MEMORY_SIZE`` (2.5 MB, for every other view).

``request.body`` refuses any body longer than that setting (``RequestDataTooBig``, a 400 nobody can explain). An
upload that legitimately weighs more (the signed authorisation and its identity documents, four PDFs of 5 MB in
base64) goes through a route decorated with ``decorate_view(accept_body_up_to(limit))``: the body is read here, from
the stream, up to one byte past ``limit`` (so a ``Content-Length`` understated or absent is caught by what arrives),
and kept as the request's body before ninja parses it. Beyond ``limit``: 413 ``payload_too_large`` in the single
envelope, without reading further. Every other view keeps Django's ceiling.
"""

import inspect
from collections.abc import Callable
from functools import wraps

from django.http import HttpRequest, JsonResponse
from django.utils.translation import gettext_lazy as _

NOT_A_LENGTH = _("Content-Length must be a length.")
TOO_LARGE = _("The request may weigh %(mb)s MB at most.")


def _refusal(status: int, code: str, message: str) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def _take_body(request: HttpRequest, limit: int) -> JsonResponse | None:
    """Read the body into the request, or the refusal when it is no length or beyond ``limit``."""
    if hasattr(request, "_body"):
        return None
    stated = request.META.get("CONTENT_LENGTH") or "0"
    try:
        length = int(stated)
    except ValueError:
        length = -1
    if length < 0:
        return _refusal(400, "invalid_request", str(NOT_A_LENGTH))
    too_large = str(TOO_LARGE) % {
        "mb": limit // (1024 * 1024) or 1
    }
    if length > limit:
        return _refusal(413, "payload_too_large", too_large)
    body = request.read(limit + 1)
    if len(body) > limit:
        return _refusal(413, "payload_too_large", too_large)
    request._body = body
    return None


def accept_body_up_to(limit: int) -> Callable:
    """A view decorator (for ninja's ``decorate_view``) that lets the route's body weigh up to ``limit`` bytes."""

    def decorate(view: Callable) -> Callable:
        if inspect.iscoroutinefunction(view):

            @wraps(view)
            async def guarded_async(request: HttpRequest, *args, **kwargs):
                refused = _take_body(request, limit)
                if refused is not None:
                    return refused
                return await view(request, *args, **kwargs)

            return guarded_async

        @wraps(view)
        def guarded(request: HttpRequest, *args, **kwargs):
            refused = _take_body(request, limit)
            if refused is not None:
                return refused
            return view(request, *args, **kwargs)

        return guarded

    return decorate
