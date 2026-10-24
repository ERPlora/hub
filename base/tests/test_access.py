"""The pure rules of the way in to a hub (``base.access``, APP-BASE-3): the PIN, the badge, the device and how long
a session lasts. No database: the ORM side lives in ``base.services``/``base.queries`` and has its own tests."""

import datetime as dt

import pytest

from base import access


class TestPinProblem:
    @pytest.mark.parametrize("pin", ["4826", "9071", "135790"])
    def test_a_pin_of_the_business_length_that_is_not_guessable_is_fine(self, pin):
        assert access.pin_problem(pin, len(pin)) is None

    @pytest.mark.parametrize(("pin", "length"), [("482", 4), ("48261", 4), ("4826", 6), ("", 4)])
    def test_another_length_than_the_business_is_refused_by_its_length(self, pin, length):
        assert access.pin_problem(pin, length) == access.PIN_LENGTH

    @pytest.mark.parametrize("pin", ["48a6", "4 26", "４８２６", "48-6"])
    def test_anything_but_ascii_digits_is_refused(self, pin):
        assert access.pin_problem(pin, 4) == access.PIN_DIGITS

    @pytest.mark.parametrize("pin", ["0000", "1111", "1234", "4321", "345678", "987654", "0123", "6789"])
    def test_one_digit_repeated_or_a_straight_run_is_too_easy_to_guess(self, pin):
        assert access.pin_problem(pin, len(pin)) == access.PIN_GUESSABLE

    @pytest.mark.parametrize("pin", ["1235", "1123", "9870", "2468"])
    def test_almost_a_run_is_not_a_run(self, pin):
        assert access.pin_problem(pin, 4) is None


class TestSessionLifetime:
    def test_a_shared_device_gets_a_shift(self):
        assert access.session_lifetime(access.SHARED, access.PER_SHIFT) == dt.timedelta(hours=12)

    def test_a_personal_device_gets_thirty_days(self):
        assert access.session_lifetime(access.PERSONAL, access.PER_SHIFT) == dt.timedelta(days=30)

    def test_never_asking_for_a_pin_never_makes_a_shared_session_longer(self):
        assert access.session_lifetime(access.SHARED, access.NEVER) == dt.timedelta(hours=12)

    @pytest.mark.parametrize("mode", [access.SHARED, access.PERSONAL])
    def test_always_asking_caps_any_device_at_one_hour(self, mode):
        assert access.session_lifetime(mode, access.ALWAYS) == dt.timedelta(hours=1)

    def test_an_unknown_mode_is_treated_as_shared(self):
        assert access.session_lifetime("", access.PER_SHIFT) == dt.timedelta(hours=12)


class TestPinOffered:
    @pytest.mark.parametrize("policy", [access.ALWAYS, access.PER_SHIFT])
    def test_a_shared_device_of_a_business_that_asks_offers_the_pin(self, policy):
        assert access.pin_offered(access.SHARED, policy) is True

    def test_a_personal_device_never_offers_it(self):
        assert access.pin_offered(access.PERSONAL, access.ALWAYS) is False

    def test_a_business_that_never_asks_never_offers_it(self):
        assert access.pin_offered(access.SHARED, access.NEVER) is False


class TestPolicyValues:
    def test_a_stored_value_that_is_not_understood_goes_back_to_the_factory_one_never_to_not_asking(self):
        assert access.policy_or_default("sometimes") == access.PER_SHIFT
        assert access.policy_or_default(access.NEVER) == access.NEVER

    def test_minutes_out_of_the_stops_go_back_to_five(self):
        assert access.inactivity_or_default(7) == 5
        assert access.inactivity_or_default(15) == 15

    def test_a_length_that_is_not_four_or_six_goes_back_to_four(self):
        assert access.pin_length_or_default(5) == 4
        assert access.pin_length_or_default(6) == 6


class TestBadge:
    @pytest.mark.parametrize(("raw", "clean"), [(" 0001234567 ", "0001234567"), ("04a1b2c3", "04A1B2C3"), ("ab-12_cd", "AB-12_CD")])
    def test_the_burst_of_the_reader_is_trimmed_and_upper_cased(self, raw, clean):
        assert access.clean_badge(raw) == clean

    @pytest.mark.parametrize("raw", ["", "abc", "x" * 65, "12 34", "12;34", "12\x0034"])
    def test_what_is_no_badge_is_none(self, raw):
        assert access.clean_badge(raw) is None

    def test_its_digest_is_keyed_and_the_same_for_the_same_card(self):
        first = access.badge_digest("04A1B2C3", key=b"k1")
        assert first == access.badge_digest("04A1B2C3", key=b"k1")
        assert first != access.badge_digest("04A1B2C3", key=b"k2")
        assert first != access.badge_digest("04A1B2C4", key=b"k1")
        assert "04A1B2C3" not in first and len(first) == 64


class TestDevice:
    def test_a_new_token_is_long_random_and_only_its_digest_is_kept(self):
        token = access.new_device_token()
        assert len(token) >= 40 and token != access.new_device_token()
        digest = access.token_digest(token)
        assert len(digest) == 64 and token not in digest
        assert access.token_digest(token) == digest

    @pytest.mark.parametrize(
        ("agent", "label"),
        [
            ("Mozilla/5.0 (Linux; Android 14; SM-T220) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36", "Chrome · Android"),
            ("Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1", "Safari · iPad"),
            ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15", "Safari · Mac"),
            ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36 Edg/129.0", "Edge · Windows"),
            ("Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0", "Firefox · Linux"),
            ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/129.0 Mobile/15E148 Safari/604.1", "Chrome · iPhone"),
            ("", ""),
            ("curl/8.4.0", ""),
        ],
    )
    def test_the_agent_names_the_browser_and_the_system(self, agent, label):
        assert access.device_agent(agent) == label


class TestInitials:
    @pytest.mark.parametrize(("name", "initials"), [("Ana López", "AL"), ("ana", "A"), ("  maría  del mar ", "MD"), ("", "?")])
    def test_the_face_of_the_grid_takes_the_first_letters(self, name, initials):
        assert access.initials(name) == initials
