"""An open ``/api/live`` stream of a hub that stops serving the app ends (BILLING-F16 of the SaaS).

The host gate (``base.middleware``) is asked once, when the stream opens. The live executor refreshes the stream's
context before every re-run (``base.operations.HubContextBuilder.refresh``), and the refresh reads the registry with
the gate's rule: a business suspended, gone or being prepared gets no more results; the stream ends with ``bye``
and its reconnection hears the gate's envelope. Driven with the process's executor and the real demo operation.
"""

import pytest
from asgiref.sync import sync_to_async
from django.db import close_old_connections
from django.test import RequestFactory
from live.executor import BYE_FRAME, Stream, Subscription, executor
from live.operations import get

from base.models import Hub, Membership
from base.operations import HubContextBuilder

pytestmark = pytest.mark.django_db(transaction=True)


async def db(fn, *args, **kwargs):
    def call():
        try:
            return fn(*args, **kwargs)
        finally:
            close_old_connections()

    return await sync_to_async(call)()


def open_stream(django_user_model) -> Stream:
    """The stream a member of ``a`` opens on ``/demo/items``: one subscription to ``demo.item.list``."""
    user = django_user_model.objects.create_user(username="ana", password="pw")
    Membership.objects.create(user=user, host="a", role=Membership.Role.OWNER)
    request = RequestFactory().get("/api/live", HTTP_HOST="a.localhost")
    request.user = user
    request.LANGUAGE_CODE = "en"
    stream = Stream(HubContextBuilder().from_request(request))
    op = get("demo.item.list")
    stream.subs["items"] = Subscription(id="items", op=op, params=op.input.model_validate({}))
    return stream


@pytest.fixture(autouse=True)
def fresh_executor():
    executor.reset()
    yield
    executor.reset()


@pytest.mark.parametrize(
    "change",
    [
        pytest.param({"state": {"status": "suspended"}}, id="suspended"),
        pytest.param({"status": Hub.Status.CANCELLED}, id="gone"),
        pytest.param({"status": Hub.Status.REQUESTED}, id="being-prepared"),
    ],
)
async def test_the_stream_of_a_hub_that_stopped_serving_ends_without_a_result(django_user_model, change):
    stream = await db(open_stream, django_user_model)
    await executor.run_all(stream)
    assert b"event: result" in stream.queue.get_nowait()

    await db(Hub.objects.filter(slug="a").update, **change)
    await executor.run_all(stream)

    assert stream.closed
    assert stream.queue.get_nowait() == BYE_FRAME
    assert stream.queue.empty()


async def test_the_stream_of_a_hub_that_serves_goes_on(django_user_model):
    stream = await db(open_stream, django_user_model)
    await executor.run_all(stream)
    stream.queue.get_nowait()

    await db(Hub.objects.filter(slug="a").update, state={"status": "past_due"})
    await executor.run_all(stream)

    assert not stream.closed
    assert stream.queue.empty()  # the same result: nothing new to send
