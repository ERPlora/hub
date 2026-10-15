"""A route that takes a larger body than Django's ``DATA_UPLOAD_MAX_MEMORY_SIZE`` (2.5 MB for every other view).

``accept_body_up_to(limit)`` goes on a ninja operation with ``decorate_view``: it reads the body itself, up to one
byte past ``limit`` (a ``Content-Length`` understated or absent is caught by what arrives), before ninja parses it;
beyond ``limit`` it answers 413 ``payload_too_large`` in the single envelope without reading further. The ceiling
of every other view stays as it is.
"""

import asyncio
import inspect
import io
import json

import pytest
from django.core.handlers.asgi import ASGIRequest
from django.test import RequestFactory

from base.request_body import accept_body_up_to

LIMIT = 10


def seen(request, **kwargs):
    return request.body


async def seen_async(request, **kwargs):
    return request.body


def post(body: bytes, **extra):
    return RequestFactory().generic(
        "POST", "/api/x", data=body, content_type="application/json", **extra
    )


def refused(response) -> tuple[int, str]:
    return response.status_code, json.loads(response.content)["error"]["code"]


def test_a_body_within_the_limit_reaches_the_route_whole(settings):
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 4
    assert accept_body_up_to(LIMIT)(seen)(post(b"0123456789")) == b"0123456789"


def test_a_body_beyond_the_limit_is_refused_by_its_stated_length():
    response = accept_body_up_to(LIMIT)(seen)(post(b"0123456789A"))
    assert refused(response) == (413, "payload_too_large")


def asgi_post(body: bytes, length: str | None):
    """A request as daphne hands it: the body as it arrived, its length as the client stated it (or not)."""
    headers = [(b"content-type", b"application/json")]
    if length is not None:
        headers.append((b"content-length", length.encode()))
    scope = {"type": "http", "method": "POST", "path": "/api/x", "headers": headers}
    return ASGIRequest(scope, io.BytesIO(body))


@pytest.mark.parametrize("length", ["3", None])
def test_a_length_understated_or_absent_is_caught_by_what_arrives(length):
    request = asgi_post(b"0123456789ABCDEF", length)
    assert refused(accept_body_up_to(LIMIT)(seen)(request)) == (413, "payload_too_large")


def test_an_absent_length_within_the_limit_still_reaches_the_route():
    assert accept_body_up_to(LIMIT)(seen)(asgi_post(b"0123", None)) == b"0123"


def test_a_length_that_is_no_length_is_a_bad_request():
    request = post(b"{}", CONTENT_LENGTH="many")
    assert refused(accept_body_up_to(LIMIT)(seen)(request)) == (400, "invalid_request")


def test_other_views_keep_djangos_ceiling(settings):
    from django.core.exceptions import RequestDataTooBig

    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 4
    with pytest.raises(RequestDataTooBig):
        seen(post(b"0123456789"))


def test_an_async_route_is_wrapped_as_async(settings):
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 4
    wrapped = accept_body_up_to(LIMIT)(seen_async)
    assert inspect.iscoroutinefunction(wrapped)
    assert asyncio.run(wrapped(post(b"0123456789"))) == b"0123456789"
    assert refused(asyncio.run(wrapped(post(b"0123456789AB")))) == (
        413,
        "payload_too_large",
    )
