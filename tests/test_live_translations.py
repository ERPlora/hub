"""What ``live`` translates without context, every app of the Hub says the same way in Spanish.

Django joins every catalogue of a language in one, and ``live`` goes first in ``INSTALLED_APPS``: its entry for a
message wins over any later app's. Customers said «Escribe un número.» and «Escribe una fecha válida.» for a custom
field of the wrong type, and the person read live's «Introduce un número.» and «Introduce una fecha válida.»
(FIX-HUB-CUSTOMER-ES-MSGIDS-SHADOWED-BY-LIVE). A message with a sense of its own goes through ``pgettext_lazy``
with its context; the same message without context says the same everywhere. The platform's own catalogues against
the modules are ``base/tests/test_locale_platform.py``.
"""

from pathlib import Path

from django.apps import apps

from base.tests.test_locale_platform import PLATFORM, catalogue, module_catalogues

SPANISH = Path("locale", "es", "LC_MESSAGES", "django.mo")


def app_catalogues() -> dict[str, dict[str, str]]:
    """The Spanish catalogue of the platform's apps (``control``, ``base``, ``shared``) and of every module."""
    platform = {
        label: catalogue(path)
        for label in (*PLATFORM, "shared")
        if (path := Path(apps.get_app_config(label).path, SPANISH)).exists()
    }
    assert set(PLATFORM) <= set(platform), "a platform catalogue is missing: the check would skip it"
    return platform | module_catalogues()


def test_what_live_translates_without_context_says_the_same_in_every_app():
    live = catalogue(Path(apps.get_app_config("live").path, SPANISH))
    collisions = sorted(
        f"{message!r}: live «{text}», {label} «{theirs[message]}»"
        for label, theirs in app_catalogues().items()
        for message, text in live.items()
        if "\x04" not in message and message in theirs and theirs[message] != text
    )
    assert collisions == []
