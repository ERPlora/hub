"""A price said as what the business charges for something is a price of a price list (PRICING-F07).

With a price list «Terraza», the owner said «En la terraza la caña la cobro a 2,50 y el refresco a 3 euros.». The turn
read «cobro» only as charging a sale and offered no tool of Price lists, so the model looked the drinks up in the menu
and asked about them. Price lists says that «la cobro a», «lo cobramos a» and their likes name a price, and adding a
price says it is what the list charges.

In English «I charge» is also how a check is charged («should I charge again?»), so Price lists does not claim it: the
turn reads «On the terrace I charge 2.50 for a draught beer…» as charging, and the search finds the price of a list.
"""

import pytest
from django.apps import apps
from live import assistant as shared

from base.models import Membership
from base.tests.test_assistant_asks import assert_its_words_name, assert_offered_or_found

from .conftest import HUB_DB

#: The owner's words in the QA of the restaurant, and the same request in English.
REPORTED = "En la terraza la caña la cobro a 2,50 y el refresco a 3 euros."
REPORTED_EN = "On the terrace I charge 2.50 for a draught beer and 3 for a soft drink"
#: Adding the price when the list has none for the drink yet, changing it when it has.
WRITES = ["pricing.price_item.add", "pricing.price_item.update"]
#: A price said as what is charged for it, one for each phrase Price lists declares.
SAID = [
    "la caña la cobro a 2,50",
    "el café lo cobro a 1,20",
    "las tostadas las cobro a 2",
    "los zumos los cobro a 3",
    "la caña la cobramos a 2,50",
    "el café lo cobramos a 1,20",
    "las tostadas las cobramos a 2",
    "los zumos los cobramos a 3",
]
#: Charging a check, and raising the menu's price: no price of a list.
NO_LIST_PRICE = [
    "cóbrale la caña a la mesa 4",
    "cobra la mesa 4 con tarjeta",
    "sube la caña a 2,50",
    "can I charge table 4 now?",
    "did that payment get recorded or should I charge again?",
]


def test_price_lists_reads_a_price_said_as_charged_as_a_price():
    """Price lists says it itself: the platform's words do not, and live alone does not either (positive control)."""
    assert_its_words_name("pricing", [(phrase, shared.stem("price")) for phrase in SAID])


def test_charging_a_check_or_raising_the_menu_price_names_no_price():
    own = apps.get_app_config("pricing").assistant_synonyms
    price = shared.stem("price")
    assert [said for said in NO_LIST_PRICE if any(price in one for one in shared.asked([said], own).concepts)] == []


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("name", WRITES)
def test_the_reported_request_offers_the_price_of_a_list(catalog_of, name):
    assert_offered_or_found(catalog_of(Membership.Role.OWNER, "es"), name, REPORTED)


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_in_english_the_search_finds_where_to_add_the_price(catalog_of):
    tools = catalog_of(Membership.Role.OWNER, "en")
    assert_offered_or_found(tools, "pricing.price_item.add", REPORTED_EN, "add a price to a price list", "en")
