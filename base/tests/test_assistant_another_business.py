"""Asked to take the menu or the business to another venue, the assistant says where that file is made and what it takes.

Asked «Voy a abrir otro bar y quiero llevarme solo la carta y los clientes, sin las ventas. ¿Me lo sacas en un archivo?
¿Las fotos de los platos van dentro?», the model answered that the photos could not go and never named the export of
Settings › Data and backups, which packs the apps chosen with their data and the products' own photos. That export is
never done from the chat (``NOT_FROM_CHAT``), so the model only knows it by what the tools it is offered say: the
products' CSV export for the menu, the loading of a template or a copy for the business. Their descriptions say where
the file is made, as the screens name it in both languages, and what it takes, as the export does it.
"""

import json
from pathlib import Path

import pytest
from django.conf import settings
from live import assistant as shared
from live.context import OperationContext
from live.operations import get

from base import assistant
from base.assistant.tools import NOT_FROM_CHAT
from base.blueprint.datasets import dataset
from base.blueprint.photos import IMAGE_OPERATIONS
from base.models import Membership
from base.permissions import permissions_for
from base.tenancy.tests.business import HUB_DB, A, in_business_a

__all__ = ["in_business_a"]

LOCALES = Path(settings.BASE_DIR) / "base" / "frontend" / "locale"
#: Where the export is, as the screens name it: Settings › Data and backups › Export, and its two purposes.
SCREEN_KEYS = (
    ("settings", "title"),
    ("settings", "tabs", "data"),
    ("data", "sections", "export"),
    ("data", "export", "template"),
    ("data", "export", "backup"),
)


def screen_labels(language: str) -> list[str]:
    names = json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))["base"]
    labels = []
    for keys in SCREEN_KEYS:
        label = names
        for key in keys:
            label = label[key]
        labels.append(label)
    return labels


def tells_where_to_export(said: str) -> bool:
    """Whether ``said`` names the export's screen by its link and by its labels in English and Spanish, says the own
    photos go inside and that the file is never made in the chat."""
    labels = [*screen_labels("en"), *screen_labels("es")]
    return all(part in said for part in ["(/settings)", *labels, "own photos", "never in the chat"])


@pytest.fixture
def owner(make_user):
    user = make_user("olga", host=A.key, role=Membership.Role.OWNER)
    return OperationContext(scope=A, actor="olga", permissions=permissions_for(user, A), language="es")


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(
    "asked",
    [
        "Voy a abrir otro bar y quiero llevarme solo la carta y los clientes, sin las ventas. ¿Me lo sacas en un "
        "archivo? ¿Las fotos de los platos van dentro?",
        "quiero llevarme el negocio a otro local",
    ],
)
def test_asked_to_take_the_menu_or_the_business_elsewhere_the_turn_offers_a_tool_that_says_where(owner, asked):
    offered = assistant.relevance.relevant(assistant.tools.catalog(owner), [asked], owner.language)

    assert [op.name for op in offered if tells_where_to_export(shared.description(op))]


@pytest.mark.parametrize("name", ["inventory.product.export", "base.blueprint.import"])
def test_what_the_tool_says_of_the_export_is_what_the_export_does(name):
    said = shared.description(get(name))

    assert tells_where_to_export(said)
    assert "base.blueprint.export" in NOT_FROM_CHAT
    assert {"inventory.product", "service.service"} <= set(IMAGE_OPERATIONS)
    assert "products and services go with their own photos" in said
    assert dataset("customer.customer").personal
    assert "never the customers" in said
