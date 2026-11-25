"""What is kept of whoever books without an account: a fingerprint of her address, and her link as its hash."""

from apps.online_booking.queries.visitors import hash_token, visitor_key

from .conftest import HUB_DB, public_ctx

pytestmark = HUB_DB


def test_the_visitor_is_a_fingerprint_of_the_address_the_load_balancer_adds():
    behind = public_ctx(ip="10.0.0.1")
    behind.request.META["HTTP_X_FORWARDED_FOR"] = "198.51.100.1, 203.0.113.9"
    direct = public_ctx(ip="203.0.113.9")
    assert visitor_key(behind) == visitor_key(direct)
    assert len(visitor_key(direct)) == 64
    assert "203.0.113.9" not in visitor_key(direct)
    assert visitor_key(public_ctx(ip="203.0.113.10")) != visitor_key(direct)


def test_a_link_is_kept_as_its_hash():
    assert hash_token("t" * 43) == hash_token("t" * 43)
    assert len(hash_token("t" * 43)) == 64
    assert hash_token("t" * 43) != "t" * 43
