"""What the assistant offers of Website: which tools, to whom, and the requests the real-model QA found unreachable
(hub#1093).

Every ask of every tool of website bringing its tool among the first ten, role by role, in English and in Spanish, out
of the catalogue of a business with every app on and ranked as a turn ranks, is ``base/tests/test_assistant_asks.py``'s
(website is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over its asks.
"""

import json
from pathlib import Path

import pytest
from django.conf import settings
from live.operations import AI, registry

from base.models import Membership
from base.tests.test_assistant_asks import comparable, place_of_no_ask
from base.tests.test_assistant_asks import catalog_of  # noqa: F401 (a fixture: the tests below take it by name)

#: Website's assistant tools: what the page is, the categories its catalog can show, and the draft's save, publication
#: and taking offline.
TOOLS = {
    "website.site.get",
    "website.catalog.categories",
    "website.site.save",
    "website.site.publish",
    "website.site.unpublish",
}
#: What a manager's assistant is offered of Website: the page as it is (``website.view``), never its changes.
THE_MANAGERS = {"website.site.get"}
#: The probes of layer 2 (``tests/e2e/qa/assistant-probes.spec.ts``) that hub#1093's QA ran on Website.
PROBES = Path(settings.BASE_DIR) / "tests" / "e2e" / "qa" / "probes"


def test_website_offers_its_five_tools():
    """Website's assistant tools (``AI``, never ``INTERNAL``): a silent drop of a tool fails."""
    tools = {name for name, op in registry.items() if op.app_label == "website" and isinstance(op.ai_spec(), AI)}
    assert tools == TOOLS


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation) and of the person's role
def test_only_who_runs_the_business_is_offered_the_websites_changes(catalog_of):
    """The page speaks for the business (``WebsiteConfig.role_permissions``): the owner and the admin hold every tool,
    a manager only reads the page and an employee's assistant is offered nothing of it."""
    for role in (Membership.Role.OWNER, Membership.Role.ADMIN):
        assert {name for name in catalog_of(role, "es") if name.startswith("website.")} == TOOLS
    assert {name for name in catalog_of(Membership.Role.MANAGER, "es") if name.startswith("website.")} == THE_MANAGERS
    employee = catalog_of(Membership.Role.EMPLOYEE, "es")
    assert not {name for name in employee if name.startswith("website.")}
    assert "base.profile.update" in employee  # positive control: the employee's catalogue is not merely empty


#: The requests of hub#1093's QA as the owner said them (``tests/e2e/qa/probes/owner-es-website-2026-11-08.json``), and
#: nothing of the tools' ``asks``: without Website's asks, neither the save nor the taking offline would be among the
#: tools a turn offers (``MAX_TOOLS``), and the model would answer it has no tool. The reads and the publication, which
#: the QA found reachable, stay so. Their words stay the person's, never the asks'
#: (``test_no_ask_copies_a_qa_probe_or_names_a_qa_record``).
REPORTED = [
    (
        "website.site.save",
        "lee primero todo el borrador actual y, sin perder ninguna sección, cambia solo el título principal a "
        "«Restaurante QA, cocina de mercado»",
    ),  # qa20261108.owner.es.website.site.save
    (
        "website.site.unpublish",
        "deja la web fuera de línea temporalmente sin borrar el borrador ni el contenido publicado",
    ),  # qa20261108.owner.es.website.site.unpublish
    (
        "website.site.get",
        "enséñame cómo está quedando la web, qué versión hay publicada y si tengo cambios sin publicar",
    ),  # qa20261108.owner.es.website.site.get
    (
        "website.site.publish",
        "publica el borrador de la web para que los visitantes vean ya los cambios y el catálogo actual",
    ),  # qa20261108.owner.es.website.site.publish
    (
        "website.catalog.categories",
        "¿qué familias de productos de Inventario puedo elegir para el catálogo de la web?",
    ),  # qa20261108.owner.es.website.catalog.categories
]


def test_the_reported_requests_are_the_owners_probes_of_layer_2():
    """Each phrase above is word for word the owner's probe of its tool: the test measures what layer 2 measures."""
    probes = {
        comparable(probe["phrase"]): probe["id"]
        for path in sorted(PROBES.glob("*-es-website-*.json"))
        for probe in json.loads(path.read_text(encoding="utf-8"))["probes"]
    }
    assert len(probes) >= len(REPORTED)  # positive control: the probes of Website are read
    assert [probes.get(comparable(phrase)) for _, phrase in REPORTED] == [
        f"qa20261108.owner.es.{name}" for name, _ in REPORTED
    ]


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("name", "phrase"), REPORTED)
def test_the_reported_website_request_is_offered_its_tool_without_being_its_asks(catalog_of, name, phrase):
    assert place_of_no_ask(catalog_of(Membership.Role.OWNER, "es"), name, phrase) is not None
