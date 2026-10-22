"""Every test starts in the Hub's default language (``settings.LANGUAGE_CODE``), whatever ran before it.

A request of the test client with ``Accept-Language: es`` goes through ``LocaleMiddleware``, which activates
Spanish in the thread and leaves it there: Django never deactivates it after the response. Without the root
conftest's ``default_language`` fixture, the next tests of the same worker read their lazy labels and messages
in Spanish, and what they assert depends on the order the worker ran them in.

The tests run in this order (pytest keeps a module's order; the suite has no random-order plugin). The first
two only prove something when one worker runs them one after the other, as a run of this file does; the third
holds under any scheduling.
"""

import pytest
from django.conf import settings
from django.utils import translation


@pytest.fixture(scope="module")
def language_when_set_up():
    """The language active when a fixture wider than a test is set up: before any fixture of the test runs."""
    return translation.get_language()


@pytest.fixture(scope="module")
def spanish_for_the_module():
    """A fixture wider than a test that leaves Spanish active, as a request of an earlier test does."""
    translation.activate("es")
    yield
    translation.deactivate()


def test_a_request_in_spanish_leaves_spanish_active_after_the_response(client):
    response = client.get("/api/me", HTTP_HOST="www.localhost:8000", HTTP_ACCEPT_LANGUAGE="es")

    assert response.json()["error"]["message"] == "No encontrado."
    assert translation.get_language() == "es"


def test_the_next_test_and_its_wider_fixtures_start_in_the_default_language(language_when_set_up):
    assert language_when_set_up == settings.LANGUAGE_CODE
    assert translation.get_language() == settings.LANGUAGE_CODE


def test_a_test_starts_in_the_default_language_even_if_a_wider_fixture_changed_it(spanish_for_the_module):
    assert translation.get_language() == settings.LANGUAGE_CODE
