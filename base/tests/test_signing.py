"""HMAC-SHA256 + timestamp of the internal calls (PLAN-SAAS §2), ported from the SaaS's ``accounts/tests/test_signing.py``.

The Hub signs and verifies exactly as the SaaS does (docs/plans/2026-10-17-demo-hubs-fase-1.md, §1.4): the same
functions, headers, window and secrets, so one side never refuses what the other signs.
"""

import hashlib
import hmac

import pytest

from base.signing import sign, verify

SECRET = "test-internal-secret"
BODY = b'{"code": "abc", "hub": "a"}'
NOW = 1_800_000_000


def _expected(timestamp, body=BODY, secret=SECRET):
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def test_sign_is_the_hex_hmac_sha256_of_timestamp_dot_body():
    assert sign(BODY, NOW, SECRET) == _expected(NOW)


def test_a_fresh_correct_signature_verifies():
    assert verify(BODY, str(NOW), _expected(NOW), secret=SECRET, now=NOW) is True


@pytest.mark.parametrize("skew", [-300, 300])
def test_up_to_five_minutes_of_clock_skew_is_accepted(skew):
    timestamp = NOW + skew

    assert verify(BODY, str(timestamp), _expected(timestamp), secret=SECRET, now=NOW) is True


@pytest.mark.parametrize("skew", [-301, 301])
def test_a_timestamp_more_than_five_minutes_away_is_refused(skew):
    timestamp = NOW + skew

    assert verify(BODY, str(timestamp), _expected(timestamp), secret=SECRET, now=NOW) is False


def test_another_body_is_refused():
    assert verify(b'{"code": "abd", "hub": "a"}', str(NOW), _expected(NOW), secret=SECRET, now=NOW) is False


def test_another_secret_is_refused():
    signature = _expected(NOW, secret="someone-else")

    assert verify(BODY, str(NOW), signature, secret=SECRET, now=NOW) is False


@pytest.mark.parametrize(
    ("timestamp", "signature"),
    [(None, "x"), ("", "x"), (str(NOW), None), (str(NOW), ""), ("soon", "x"), ("1.5e9", "x")],
)
def test_missing_or_malformed_headers_are_refused(timestamp, signature):
    signature = _expected(NOW) if signature == "x" else signature

    assert verify(BODY, timestamp, signature, secret=SECRET, now=NOW) is False


def test_nothing_verifies_without_a_secret():
    assert verify(BODY, str(NOW), _expected(NOW, secret=""), secret="", now=NOW) is False


@pytest.mark.parametrize(("timestamp", "signature"), [(str(NOW), "ñ" * 64), ("١٨٠٠٠٠٠٠٠٠", "x")])
def test_non_ascii_headers_are_refused_without_raising(timestamp, signature):
    signature = _expected(NOW) if signature == "x" else signature

    assert verify(BODY, timestamp, signature, secret=SECRET, now=NOW) is False


# --- Two live secrets and the signature that covers method and path (PLAN-SAAS §2.1; L1-A2) ------

from base.signing import (  # noqa: E402
    SIGNATURE_HEADER,
    SIGNATURE_V2_HEADER,
    TIMESTAMP_HEADER,
    live_secrets,
    sign_v2,
    signed_headers,
    verify_request,
    verify_signed,
)

PREVIOUS = "the-secret-before-the-rotation"
PATH = "/internal/hubs/0192c1d4-8b2a-7cde-9f00-000000000001/state"


def _expected_v2(timestamp, method="PUT", path=PATH, body=BODY, secret=SECRET):
    message = f"v2\n{timestamp}\n{method}\n{path}\n".encode() + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


class TestTheSignatureV2:
    def test_is_the_hex_hmac_of_version_timestamp_method_path_and_body(self):
        assert sign_v2("put", PATH, BODY, NOW, SECRET) == _expected_v2(NOW)

    def test_the_headers_carry_the_timestamp_and_both_signatures_with_the_current_secret(self):
        headers = signed_headers("PUT", PATH, BODY, NOW, SECRET)

        assert headers[TIMESTAMP_HEADER] == str(NOW)
        assert headers[SIGNATURE_HEADER] == _expected(NOW)
        assert headers[SIGNATURE_V2_HEADER] == _expected_v2(NOW)

    def test_a_signed_call_verifies(self):
        headers = signed_headers("PUT", PATH, BODY, NOW, SECRET)

        assert verify_signed("PUT", PATH, BODY, headers, secrets=[SECRET], now=NOW) is True

    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("POST", PATH, BODY),
            ("PUT", "/internal/hubs/0192c1d4-8b2a-7cde-9f00-000000000002/state", BODY),
            ("PUT", PATH + "?all=1", BODY),
            ("PUT", PATH, b'{"code": "abd", "hub": "a"}'),
        ],
    )
    def test_another_method_path_or_body_is_refused_even_with_a_valid_v1(self, method, path, body):
        """With v2 in the call, v2 decides: the body-only v1 of the same body proves nothing about the route."""
        headers = signed_headers("PUT", PATH, BODY, NOW, SECRET)
        headers[SIGNATURE_HEADER] = sign(body, NOW, SECRET)

        assert verify_signed(method, path, body, headers, secrets=[SECRET], now=NOW) is False

    def test_a_call_with_only_v1_is_judged_by_v1_as_hub_next_signs_today(self):
        headers = {TIMESTAMP_HEADER: str(NOW), SIGNATURE_HEADER: _expected(NOW)}

        assert verify_signed("POST", "/internal/auth/redeem", BODY, headers, secrets=[SECRET], now=NOW) is True

    def test_a_broken_v2_is_refused_even_if_v1_passes(self):
        """No downgrade: naming v2 and failing it is a forged or a mangled call."""
        headers = {TIMESTAMP_HEADER: str(NOW), SIGNATURE_HEADER: _expected(NOW), SIGNATURE_V2_HEADER: "0" * 64}

        assert verify_signed("PUT", PATH, BODY, headers, secrets=[SECRET], now=NOW) is False

    @pytest.mark.parametrize("skew", [-301, 301])
    def test_the_replay_window_is_five_minutes(self, skew):
        timestamp = NOW + skew
        headers = signed_headers("PUT", PATH, BODY, timestamp, SECRET)

        assert verify_signed("PUT", PATH, BODY, headers, secrets=[SECRET], now=NOW) is False
        assert verify_signed("PUT", PATH, BODY, headers, secrets=[SECRET], now=timestamp) is True

    def test_header_names_are_matched_whatever_their_case(self):
        headers = {key.lower(): value for key, value in signed_headers("PUT", PATH, BODY, NOW, SECRET).items()}

        assert verify_signed("PUT", PATH, BODY, headers, secrets=[SECRET], now=NOW) is True

    @pytest.mark.parametrize("signature", ["", "ñ" * 64, None])
    def test_a_missing_or_non_ascii_v2_is_refused_without_raising(self, signature):
        headers = {TIMESTAMP_HEADER: str(NOW), SIGNATURE_V2_HEADER: signature}

        assert verify_signed("PUT", PATH, BODY, headers, secrets=[SECRET], now=NOW) is False


class TestTwoLiveSecrets:
    """Rotation (PLAN-SAAS §2): both projects accept the current and the previous secret, and sign with the current."""

    @pytest.mark.parametrize("version", ["v1", "v2"])
    def test_a_call_signed_with_the_previous_secret_verifies_during_the_rotation(self, version):
        headers = signed_headers("PUT", PATH, BODY, NOW, PREVIOUS)
        if version == "v1":
            del headers[SIGNATURE_V2_HEADER]

        assert verify_signed("PUT", PATH, BODY, headers, secrets=[SECRET, PREVIOUS], now=NOW) is True

    def test_once_the_previous_secret_is_gone_its_calls_are_refused(self):
        headers = signed_headers("PUT", PATH, BODY, NOW, PREVIOUS)

        assert verify_signed("PUT", PATH, BODY, headers, secrets=[SECRET], now=NOW) is False

    def test_v1_verify_takes_several_secrets_too(self):
        assert verify(BODY, str(NOW), _expected(NOW, secret=PREVIOUS), secret=[SECRET, PREVIOUS], now=NOW) is True
        assert verify(BODY, str(NOW), _expected(NOW, secret=PREVIOUS), secret=[SECRET, ""], now=NOW) is False

    def test_the_live_secrets_are_the_current_and_a_non_empty_previous(self, settings):
        settings.INTERNAL_SHARED_SECRET = SECRET
        settings.INTERNAL_SHARED_SECRET_PREVIOUS = ""
        assert live_secrets() == (SECRET,)

        settings.INTERNAL_SHARED_SECRET_PREVIOUS = PREVIOUS
        assert live_secrets() == (SECRET, PREVIOUS)

    def test_the_previous_secret_is_a_setting_of_its_own(self):
        """``INTERNAL_SHARED_SECRET_PREVIOUS`` (env, empty outside a rotation; ``config/settings.py``)."""
        from django.conf import settings as live_settings

        assert isinstance(live_settings.INTERNAL_SHARED_SECRET_PREVIOUS, str)

    def test_nothing_verifies_without_any_secret(self):
        headers = signed_headers("PUT", PATH, BODY, NOW, "")

        assert verify_signed("PUT", PATH, BODY, headers, secrets=["", ""], now=NOW) is False


class TestVerifyRequest:
    """``verify_request``: what the Hub's ``/internal`` door calls, with the live secrets of the settings."""

    def _request(self, rf, headers, *, method="post", path="/internal/auth/redeem", body=BODY):
        return getattr(rf, method)(path, data=body, content_type="application/json", headers=headers)

    def test_takes_method_full_path_body_and_headers_from_the_request(self, rf, settings):
        settings.INTERNAL_SHARED_SECRET = SECRET
        settings.INTERNAL_SHARED_SECRET_PREVIOUS = PREVIOUS
        now = 1_800_000_000
        headers = signed_headers("POST", "/internal/auth/redeem?x=1", BODY, now, PREVIOUS)

        assert verify_request(self._request(rf, headers, path="/internal/auth/redeem?x=1"), now=now) is True
        assert verify_request(self._request(rf, headers, path="/internal/auth/redeem"), now=now) is False

    def test_uses_the_max_age_of_the_settings(self, rf, settings):
        settings.INTERNAL_SHARED_SECRET = SECRET
        settings.INTERNAL_SIGNATURE_MAX_AGE_SECONDS = 10
        headers = signed_headers("POST", "/internal/auth/redeem", BODY, NOW - 11, SECRET)

        assert verify_request(self._request(rf, headers), now=NOW) is False


# --- A timestamp no clock writes, and the headers alone (T7b) ---------------------------------------

from base.signing import may_be_signed  # noqa: E402


@pytest.mark.parametrize("timestamp", ["9" * 5000, "1" * 21], ids=["beyond Python's 4300 digits", "21 digits"])
def test_a_timestamp_of_too_many_digits_is_refused_without_raising(timestamp):
    """``int()`` raises beyond 4300 digits: such a header would be a 500 on every ``/internal`` door."""
    assert verify(BODY, timestamp, _expected(NOW), secret=SECRET, now=NOW) is False
    headers = {TIMESTAMP_HEADER: timestamp, SIGNATURE_V2_HEADER: _expected_v2(NOW)}
    assert verify_signed("PUT", PATH, BODY, headers, secrets=[SECRET], now=NOW) is False


FRESH = str(NOW)
SIGNATURE = "0" * 64


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({TIMESTAMP_HEADER: FRESH, SIGNATURE_HEADER: SIGNATURE}, True),
        ({TIMESTAMP_HEADER: FRESH, SIGNATURE_V2_HEADER: SIGNATURE}, True),
        ({"x-erplora-timestamp": FRESH, "x-erplora-signature-v2": SIGNATURE}, True),
        ({TIMESTAMP_HEADER: str(NOW - 300), SIGNATURE_HEADER: SIGNATURE}, True),
        ({}, False),
        ({TIMESTAMP_HEADER: FRESH}, False),
        ({TIMESTAMP_HEADER: FRESH, SIGNATURE_HEADER: ""}, False),
        ({SIGNATURE_HEADER: SIGNATURE, SIGNATURE_V2_HEADER: SIGNATURE}, False),
        ({TIMESTAMP_HEADER: str(NOW - 301), SIGNATURE_HEADER: SIGNATURE}, False),
        ({TIMESTAMP_HEADER: str(NOW + 301), SIGNATURE_HEADER: SIGNATURE}, False),
        ({TIMESTAMP_HEADER: "soon", SIGNATURE_HEADER: SIGNATURE}, False),
        ({TIMESTAMP_HEADER: "١٨٠٠٠٠٠٠٠٠", SIGNATURE_HEADER: SIGNATURE}, False),
        ({TIMESTAMP_HEADER: "9" * 5000, SIGNATURE_HEADER: SIGNATURE}, False),
    ],
    ids=[
        "v1",
        "v2",
        "any case",
        "at the edge of the window",
        "nothing",
        "no signature",
        "an empty signature",
        "no timestamp",
        "stale",
        "future",
        "not a time",
        "non-ascii digits",
        "too many digits",
    ],
)
def test_may_be_signed_judges_the_headers_alone(headers, expected):
    """Whether a body is worth reading: only it can prove the signature, but the headers can rule it out."""
    assert may_be_signed(headers, now=NOW, max_age=300) is expected
