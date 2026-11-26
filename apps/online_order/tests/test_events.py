"""Online orders' event vocabulary: ``online_order.<entity>.<fact in the past tense>``."""

from apps.online_order import events


def declared():
    return {name: value for name, value in vars(events).items() if name.isupper() and isinstance(value, str)}


def test_the_events():
    assert declared() == {
        "QR_CODE_REGENERATED": "online_order.qr_code.regenerated",
        "ORDER_SENT": "online_order.order.sent",
    }
