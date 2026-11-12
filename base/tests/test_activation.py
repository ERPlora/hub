"""``base.activation``: the rules of turning a business's modules on and off, without the database (PLAN-HUB §9).

A module is ``on`` or ``off`` in a hub, and ``chosen`` when the business turned it on itself; what the closure by
``requires`` brought along is not chosen and does not count against the plan's ``max_apps``. A hub that never turned
anything on or off has every module off (round 2026-10-27): a blueprint or the Apps screen turns on what it uses. The
hubs of before it, and the developer's local hubs, have every module on, its roots chosen (:func:`every_on`).
"""

import pytest
from live.meta import module_configs

from base import activation
from base.activation import OFF, ON, Activation
from base.catalog import template_apps

#: A small graph: sale needs tax and customer, invoice needs sale (and so tax and customer), verifactu needs invoice.
GRAPH = {
    "tax": (),
    "customer": (),
    "sale": ("tax", "customer"),
    "invoice": ("tax", "sale", "customer"),
    "verifactu": ("invoice",),
    "task": (),
}


def states(**given: str) -> dict[str, Activation]:
    """``on``/``off`` per label, ``*`` marks the chosen ones (``sale="on*"``); the rest of GRAPH off."""
    out = {label: Activation(OFF, False) for label in GRAPH}
    for label, mark in given.items():
        out[label] = Activation(ON if mark.startswith("on") else OFF, mark.endswith("*"))
    return out


# ── The roots: what the existing hubs and the vertical templates count as chosen ──────────────────────────────────


def test_the_roots_are_the_modules_on_that_no_other_module_on_needs():
    assert activation.roots(["tax", "customer", "sale"], GRAPH) == {"sale"}
    assert activation.roots(["tax", "customer", "sale", "invoice", "verifactu"], GRAPH) == {"verifactu"}
    assert activation.roots(["tax", "task"], GRAPH) == {"tax", "task"}
    # Needed only by a module that is off: a root.
    assert activation.roots(["tax", "customer"], GRAPH) == {"tax", "customer"}


def test_every_module_on_has_17_roots_of_27_on_main():
    graph = activation.module_graph()
    assert len(graph) == 27
    assert sorted(activation.roots(graph, graph)) == [
        "attendance", "cart_checkout", "cash_register", "combo", "demo", "flow", "kitchen", "modifier",
        "online_booking", "payment", "pricing", "printing", "reservation", "task", "verifactu", "website",
        "whatsapp_inbox",
    ]  # fmt: skip


@pytest.mark.parametrize(("vertical", "modules", "chosen"), [("restaurant", 20, 13), ("hair_salon", 18, 10)])
def test_a_vertical_template_counts_only_its_roots_as_chosen(vertical, modules, chosen):
    """PLAN §32 point 2: the restaurant's template has 20 modules and 13 roots; the hair salon's, 18 and 10 (one module
    fewer each since VeriFactu is in no template, PLAN-HUB round 2026-11-07, hub#998: Invoicing is a root in its
    place)."""
    graph = activation.module_graph()
    apps = template_apps(vertical)
    template = activation.template(apps, graph)
    assert len(apps) == modules and sorted(label for label, row in template.items() if row.state == ON) == apps
    assert sum(row.chosen for row in template.values()) == chosen
    assert {label for label, row in template.items() if row.chosen} == activation.roots(apps, graph)
    # The rest of the modules are off in it, and none of them chosen.
    assert all(row == Activation(OFF, False) for label, row in template.items() if label not in apps)


def test_the_baseline_has_every_module_off_and_none_chosen():
    """Round 2026-10-27: a hub is born with every app off; nothing is on until the business turns it on."""
    assert activation.baseline(GRAPH) == {label: Activation(OFF, False) for label in GRAPH}
    graph = activation.module_graph()
    assert activation.baseline(graph) == {label: Activation(OFF, False) for label in graph}


def test_every_on_has_every_module_on_and_its_roots_chosen():
    """What the hubs of before round 2026-10-27 had without rows (the migration writes it down for them), and the
    developer's local hubs ``a`` and ``b``: every module on, its roots chosen."""
    assert activation.every_on(GRAPH) == {
        "tax": Activation(ON, False),
        "customer": Activation(ON, False),
        "sale": Activation(ON, False),
        "invoice": Activation(ON, False),
        "verifactu": Activation(ON, True),
        "task": Activation(ON, True),
    }


def test_the_graph_is_the_modules_and_their_requires():
    graph = activation.module_graph()
    assert graph == {config.label: tuple(config.requires) for config in module_configs()}
    assert "base" not in graph


# ── What a hub has: its rows, or the baseline while it has none ──────────────────────────────────────────────────


def test_a_hub_without_rows_has_the_baseline_every_module_off():
    assert activation.effective({}, GRAPH) == activation.baseline(GRAPH)
    assert not any(row.on for row in activation.effective({}, GRAPH).values())


def test_a_hub_with_rows_has_them_and_a_module_without_its_row_is_off():
    rows = {"task": Activation(ON, True), "gone": Activation(ON, True)}
    current = activation.effective(rows, GRAPH)
    assert current["task"] == Activation(ON, True)
    assert current["sale"] == Activation(OFF, False)
    assert "gone" not in current  # a module no longer in the code is no module


# ── Turning one on ──────────────────────────────────────────────────────────────────────────────────────────────


def test_turning_one_on_turns_on_what_it_needs_without_choosing_it():
    changes = activation.enabling("invoice", states(), GRAPH)
    assert changes == {
        "invoice": Activation(ON, True),
        "sale": Activation(ON, False),
        "tax": Activation(ON, False),
        "customer": Activation(ON, False),
    }


def test_what_it_needs_and_is_already_on_keeps_whether_it_was_chosen():
    changes = activation.enabling("invoice", states(sale="on*", tax="on", customer="on"), GRAPH)
    assert changes == {"invoice": Activation(ON, True)}


def test_one_already_on_and_chosen_changes_nothing():
    assert activation.enabling("task", states(task="on*"), GRAPH) == {}


def test_one_on_because_another_needs_it_becomes_chosen():
    assert activation.enabling("tax", states(sale="on*", tax="on", customer="on"), GRAPH) == {"tax": Activation(ON, True)}


def test_turning_on_an_unknown_module_is_a_programming_error():
    with pytest.raises(KeyError):
        activation.enabling("nope", states(), GRAPH)


# ── Turning one off ─────────────────────────────────────────────────────────────────────────────────────────────


def test_the_apps_on_that_need_one_are_named_direct_or_not():
    current = states(verifactu="on*", invoice="on", sale="on", tax="on", customer="on", task="on*")
    assert activation.required_by("tax", current, GRAPH) == ["invoice", "sale", "verifactu"]
    assert activation.required_by("invoice", current, GRAPH) == ["verifactu"]
    assert activation.required_by("verifactu", current, GRAPH) == []
    # An app that needs it but is off does not count.
    assert activation.required_by("tax", states(tax="on*", sale="off"), GRAPH) == []


def test_turning_one_off_turns_off_what_came_with_it_and_nothing_else_needs():
    current = states(sale="on*", tax="on", customer="on", task="on*")
    assert activation.disabling("sale", current, GRAPH) == {
        "sale": Activation(OFF, False),
        "tax": Activation(OFF, False),
        "customer": Activation(OFF, False),
    }


def test_what_another_app_on_needs_stays_on():
    # customer was brought by sale; tax was chosen by the business itself.
    current = states(invoice="on*", sale="on", tax="on*", customer="on")
    assert activation.disabling("invoice", current, GRAPH) == {
        "invoice": Activation(OFF, False),
        "sale": Activation(OFF, False),
        "customer": Activation(OFF, False),
    }


def test_a_chain_brought_along_goes_off_with_the_one_that_brought_it():
    current = states(verifactu="on*", invoice="on", sale="on", tax="on", customer="on")
    assert set(activation.disabling("verifactu", current, GRAPH)) == {"verifactu", "invoice", "sale", "tax", "customer"}


def test_one_already_off_changes_nothing():
    assert activation.disabling("task", states(), GRAPH) == {}


def test_turning_off_one_another_app_on_needs_is_a_programming_error():
    with pytest.raises(ValueError, match="sale"):
        activation.disabling("tax", states(sale="on*", tax="on", customer="on"), GRAPH)


# ── The plan's limit ────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("photo", "limit"),
    [
        ({"plan": {"max_apps": 20}}, 20),
        ({"plan": {"max_apps": 0}}, None),  # 0 = no limit, as max_devices
        ({"plan": {"slug": "free"}}, None),  # a photo from before saas#117
        ({"plan": None}, None),
        ({}, None),
        (None, None),
        ({"plan": {"max_apps": -3}}, None),
        ({"plan": {"max_apps": True}}, None),
        ({"plan": {"max_apps": "20"}}, None),
    ],
)
def test_the_limit_is_the_plans_max_apps_and_zero_or_none_is_no_limit(photo, limit):
    assert activation.plan_limit(photo) == limit


def test_only_the_chosen_modules_on_count():
    current = states(invoice="on*", sale="on", tax="on*", customer="on", task="off")
    assert activation.chosen_on(current) == 2
    assert activation.chosen_on(current, among={"invoice", "sale"}) == 1


# ── An app's veto ───────────────────────────────────────────────────────────────────────────────────────────────


class Config:
    def __init__(self, label, veto=None, on_veto=None):
        self.label = label
        if veto is not None:
            self.can_disable = veto
        if on_veto is not None:
            self.can_enable = on_veto


def test_an_app_without_a_veto_never_refuses():
    assert activation.veto(["task"], ctx=None, configs=[Config("task")]) is None


def test_the_first_app_that_refuses_says_why():
    configs = [Config("sale"), Config("invoice", lambda ctx: None), Config("verifactu", lambda ctx: f"pending {ctx}")]
    assert activation.veto(["sale", "invoice", "verifactu"], ctx="x", configs=configs) == ("verifactu", "pending x")


def test_a_blank_reason_is_no_refusal():
    assert activation.veto(["task"], ctx=None, configs=[Config("task", lambda ctx: "  ")]) is None


def test_refusals_says_what_each_app_that_refuses_says():
    configs = [Config("sale"), Config("invoice", lambda ctx: None), Config("verifactu", lambda ctx: f"never {ctx}")]
    assert activation.refusals(["sale", "invoice", "verifactu"], ctx="x", configs=configs) == {"verifactu": "never x"}


def test_an_app_may_refuse_to_go_on_by_its_own_hook():
    configs = [Config("verifactu", lambda ctx: "never off", lambda ctx: "only in Spain"), Config("task")]
    asked = {"ctx": None, "configs": configs, "hook": activation.CAN_ENABLE}
    assert activation.veto(["task", "verifactu"], **asked) == ("verifactu", "only in Spain")
    assert activation.refusals(["task", "verifactu"], **asked) == {"verifactu": "only in Spain"}


# ── What a business must have on in its country (hub#997, PLAN-HUB round 2026-11-07) ─────────────────────────────
# An app says where it is mandatory (``mandatory`` on its LiveAppConfig, ``base.home.mandatory_in``). Once on in a
# business of one of those countries it never goes off there: base refuses it, with a reason of its own when the app
# gives none, and turning off another app it came along with leaves it on.


class Declared:
    """A module that says where a business must have it on, and maybe a reason of its own not to go off."""

    def __init__(self, label, name, countries=None, veto=None, turns_on=False):
        self.label = label
        self.verbose_name = name
        if countries is not None:
            self.mandatory = {"countries": countries, "platform_turns_on": turns_on}
        if veto is not None:
            self.can_disable = veto


DECLARED = [Declared("tax", "Taxes", "all"), Declared("verifactu", "VeriFactu", ["ES"]), Declared("task", "Tasks")]


@pytest.mark.parametrize(
    ("country", "kept"),
    [("PL", {"tax"}), ("ES", {"tax", "verifactu"}), ("es", {"tax", "verifactu"}), ("", {"tax", "verifactu"})],
)
def test_the_apps_a_business_must_keep_on_are_those_on_mandatory_in_its_country(country, kept):
    """Without a country (a demo) a business is in Spain; one off is not kept on: it is asked for on the Home."""
    current = states(tax="on", verifactu="on*", task="on*", invoice="on", sale="on", customer="on")
    assert activation.mandatory_on(current, country, DECLARED) == kept
    assert activation.mandatory_on(states(task="on*"), country, DECLARED) == set()


@pytest.mark.parametrize("state", ["creating", "failed"])
def test_one_whose_tables_are_not_made_yet_is_not_kept_on(state):
    """Only an app on binds: one being set up, or that could not be, can still be given up on (BASE-F23)."""
    current = {label: Activation(OFF, False) for label in GRAPH} | {"tax": Activation(state, True)}
    assert activation.mandatory_on(current, "ES", DECLARED) == set()


def test_one_kept_on_never_goes_off_along_with_the_app_it_came_with():
    current = states(sale="on*", tax="on", customer="on")
    assert activation.disabling("sale", current, GRAPH, kept={"tax"}) == {
        "sale": Activation(OFF, False),
        "customer": Activation(OFF, False),
    }
    assert activation.keeping_on("sale", current, GRAPH, kept={"tax"}) == ["sale", "customer"]
    # Nor down a chain: what it needs that came along with it stays on with it.
    current = states(verifactu="on*", invoice="on", sale="on", tax="on", customer="on")
    assert set(activation.disabling("verifactu", current, GRAPH, kept={"sale"})) == {"verifactu", "invoice"}


class Asker:
    """Who asks, in ``language``: what ``refusals`` reads of the operation's context."""

    def __init__(self, language="en"):
        self.language = language


def test_one_kept_on_says_base_s_reason_in_the_language_of_who_asks():
    asked = {"configs": DECLARED, "kept": {"tax"}, "country": "PL"}
    assert activation.refusals(["tax", "task"], ctx=Asker(), **asked) == {
        "tax": "Taxes is mandatory for businesses in Poland: it can't be turned off."
    }
    assert activation.refusals(["tax"], ctx=Asker("es"), **asked) == {
        "tax": "Taxes es obligatoria para los negocios de Polonia: no se puede desactivar."
    }


def test_without_a_country_base_s_reason_names_spain():
    assert activation.refusals(["tax"], ctx=Asker(), configs=DECLARED, kept={"tax"}, country="") == {
        "tax": "Taxes is mandatory for businesses in Spain: it can't be turned off."
    }


def test_the_app_s_own_reason_comes_before_base_s():
    configs = [Declared("verifactu", "VeriFactu", ["ES"], veto=lambda ctx: "never once on")]
    asked = {"ctx": Asker(), "configs": configs, "kept": {"verifactu"}, "country": "ES"}
    assert activation.refusals(["verifactu"], **asked) == {"verifactu": "never once on"}


def test_base_s_reason_is_only_to_go_off():
    asked = {"ctx": Asker(), "configs": DECLARED, "kept": {"tax"}, "country": "ES", "hook": activation.CAN_ENABLE}
    assert activation.refusals(["tax"], **asked) == {}


# ── What a business is born with (hub#997, PLAN-HUB round 2026-11-07) ────────────────────────────────────────────
# At sign-up the platform turns on, by itself, the apps the business's country requires that say it may
# (``platform_turns_on``: Taxes, in every country), with what they need, none chosen: they take nothing of the plan's
# limit. Never one that binds the business to a tax authority (VeriFactu): its owner turns it on, asked by the Home.

BORN = [
    Declared("tax", "Taxes", "all", turns_on=True),
    Declared("verifactu", "VeriFactu", ["ES"]),
    Declared("customer", "Customers", ["PT"], turns_on=True),
    Declared("task", "Tasks"),
]


@pytest.mark.parametrize(
    ("country", "born"),
    [("ES", {"tax"}), ("", {"tax"}), ("PL", {"tax"}), ("PT", {"tax", "customer"}), ("pt", {"tax", "customer"})],
)
def test_a_business_is_born_with_the_apps_its_country_requires_that_the_platform_turns_on(country, born):
    """Without a country (a demo) a business is in Spain; one mandatory there that the platform never turns on, never."""
    assert activation.born_on(country, BORN) == born


def test_what_a_business_is_born_with_is_on_with_what_it_needs_and_none_of_it_chosen():
    born = activation.born({"sale"}, GRAPH)
    assert born == states(sale="on", tax="on", customer="on")
    assert activation.chosen_on(born) == 0
    # Born with nothing on, it is the baseline: every module off.
    assert activation.born(set(), GRAPH) == activation.baseline(GRAPH)


# ── Its tables being made (S3; PLAN-DB §7): «creating» and «failed» ───────────────────────────────────────────────
# In a hub with its own database an app's tables are made the first time it is turned on: meanwhile it is
# ``creating``, and ``failed`` if making them failed (tried again). Both are wanted on: the closure by ``requires``, the
# plan's limit and what goes off count them as on; only ``on`` is active (its operations, the relay, the menu).

from base.activation import CREATING, FAILED  # noqa: E402


def wanted(**given: str) -> dict[str, Activation]:
    """Like :func:`states`, with ``creating``/``failed`` (``*`` chosen too)."""
    out = {label: Activation(OFF, False) for label in GRAPH}
    for label, mark in given.items():
        out[label] = Activation(mark.rstrip("*"), mark.endswith("*"))
    return out


def test_the_states_are_on_off_creating_and_failed():
    assert activation.STATES == (ON, OFF, CREATING, FAILED)
    assert (CREATING, FAILED) == ("creating", "failed")


@pytest.mark.parametrize(("state", "on", "is_wanted"), [(ON, True, True), (CREATING, False, True), (FAILED, False, True), (OFF, False, False)])
def test_only_on_is_active_and_creating_or_failed_are_wanted_on(state, on, is_wanted):
    assert Activation(state, True).on is on
    assert Activation(state, True).wanted is is_wanted


def test_one_being_created_and_chosen_changes_nothing_when_turned_on_again():
    assert activation.enabling("sale", wanted(sale="creating*", tax="creating", customer="on"), GRAPH) == {}


def test_one_that_failed_is_turned_on_again_and_what_it_needs_that_failed_too():
    changes = activation.enabling("sale", wanted(sale="failed*", tax="failed", customer="on"), GRAPH)
    assert changes == {"sale": Activation(ON, True), "tax": Activation(ON, False)}


def test_what_it_needs_being_created_is_left_as_it_is():
    changes = activation.enabling("invoice", wanted(sale="creating*", tax="creating", customer="creating"), GRAPH)
    assert changes == {"invoice": Activation(ON, True)}


def test_an_app_being_created_that_needs_one_keeps_it_from_going_off():
    current = wanted(sale="creating*", tax="on", customer="on")
    assert activation.required_by("tax", current, GRAPH) == ["sale"]
    with pytest.raises(ValueError, match="sale"):
        activation.disabling("tax", current, GRAPH)


def test_turning_off_one_being_created_or_failed_turns_it_off_with_what_came_along():
    assert activation.disabling("sale", wanted(sale="creating*", tax="creating", customer="on"), GRAPH) == {
        "sale": Activation(OFF, False),
        "tax": Activation(OFF, False),
        "customer": Activation(OFF, False),
    }
    assert activation.disabling("task", wanted(task="failed*"), GRAPH) == {"task": Activation(OFF, False)}


def test_the_chosen_ones_being_created_or_failed_count_against_the_limit():
    assert activation.chosen_on(wanted(sale="creating*", task="failed*", invoice="on*", tax="creating")) == 3
