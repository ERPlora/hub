"""The platform's Spanish never speaks for an app: a message the platform translates without context is the app's too.

Django joins every catalogue of a language in one, and the platform's apps (``control``, ``base``) come before the
modules in ``INSTALLED_APPS``: their entry for a message wins over the module's own. ``msgid "state"`` was «foto del
SaaS» (the registry's snapshot) in ``base``, so the «state» of a customer's consent or a stock line said «foto del
SaaS» in Spanish too (APP-BASE-3, review of hub#232). A label with a sense of its own goes through ``pgettext_lazy``
with its context; what is left without context must say the same as every module that also says it.
"""

import gettext
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings
from django.utils import translation

#: The platform's catalogues, before every module in ``INSTALLED_APPS``.
PLATFORM = ("control", "base")


def catalogue(path: Path) -> dict[str, str]:
    """The compiled singular entries of a ``.mo`` (what Django reads), by message; a contexted one is keyed
    ``context\\x04message``, and its header (the empty message) is left out."""
    with path.open("rb") as compiled:
        entries = gettext.GNUTranslations(compiled)._catalog
    return {key: text for key, text in entries.items() if isinstance(key, str) and key}


def module_catalogues() -> dict[str, dict[str, str]]:
    found = {path.parts[-5]: catalogue(path) for path in sorted(Path(settings.BASE_DIR, "apps").glob("*/locale/es/LC_MESSAGES/django.mo"))}
    assert found, "no module has a Spanish catalogue: the check would pass on nothing"
    return found


@pytest.mark.parametrize("label", PLATFORM)
def test_what_the_platform_translates_without_context_says_the_same_in_every_module(label):
    platform = catalogue(Path(apps.get_app_config(label).path, "locale/es/LC_MESSAGES/django.mo"))
    collisions = sorted(
        f"{message!r}: {label} «{text}», {module} «{theirs[message]}»"
        for module, theirs in module_catalogues().items()
        for message, text in platform.items()
        if "\x04" not in message and message in theirs and theirs[message] != text
    )
    assert collisions == []


def verbose_name(model: str, field: str) -> str:
    return str(apps.get_model(model)._meta.get_field(field).verbose_name)


@pytest.mark.parametrize(
    ("model", "field", "spanish"),
    [
        # A module's own word, not the platform's.
        ("customer.Consent", "state", "estado"),
        ("inventory.SaleStock", "state", "estado"),
        ("service.Redemption", "status", "estado"),
        ("flow.FlowRun", "event_name", "aviso"),
        ("flow.Flow", "trigger_event", "aviso"),
        # The platform's, in its own sense.
        ("control.Hub", "state", "foto del SaaS"),
        ("control.Hub", "slug", "dirección"),
        ("control.Hub", "ready_at", "listo el"),
        ("control.Hub", "cancelled_at", "cancelado el"),
        ("control.Hub", "created_at", "creado el"),
        ("control.Hub", "updated_at", "actualizado el"),
        ("control.Cluster", "created_at", "creado el"),
        ("base.SessionOwner", "created_at", "creado el"),
        ("base.AccessSettings", "updated_at", "actualizado el"),
        ("base.AccessSettings", "updated_by", "cambiado por"),
        ("base.Profile", "updated_at", "actualizado el"),
        ("base.EventDelivery", "event", "evento"),
    ],
)
def test_each_field_says_its_own_word_in_spanish(model, field, spanish):
    with translation.override("es"):
        assert verbose_name(model, field) == spanish
