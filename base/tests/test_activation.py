"""``base.activation``: the rules of turning a business's modules on and off, without the database (PLAN-HUB §9).

A module is ``on`` or ``off`` in a hub, and ``chosen`` when the business turned it on itself; what the closure by
``requires`` brought along is not chosen and does not count against the plan's ``max_apps``. A hub that never turned
anything on or off has every module on, its roots chosen (the modules on that no other module on needs).
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


@pytest.mark.parametrize(("vertical", "modules", "chosen"), [("restaurant", 21, 13), ("hair_salon", 19, 10)])
def test_a_vertical_template_counts_only_its_roots_as_chosen(vertical, modules, chosen):
    """PLAN §32 point 2: the restaurant's template has 21 modules and 13 roots; the hair salon's, 19 and 10."""
    graph = activation.module_graph()
    apps = template_apps(vertical)
    template = activation.template(apps, graph)
    assert len(apps) == modules and sorted(label for label, row in template.items() if row.state == ON) == apps
    assert sum(row.chosen for row in template.values()) == chosen
    assert {label for label, row in template.items() if row.chosen} == activation.roots(apps, graph)
    # The rest of the modules are off in it, and none of them chosen.
    assert all(row == Activation(OFF, False) for label, row in template.items() if label not in apps)


def test_the_baseline_has_every_module_on_and_its_roots_chosen():
    baseline = activation.baseline(GRAPH)
    assert baseline == {
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


def test_a_hub_without_rows_has_the_baseline():
    assert activation.effective({}, GRAPH) == activation.baseline(GRAPH)


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
    def __init__(self, label, veto=None):
        self.label = label
        if veto is not None:
            self.can_disable = veto


def test_an_app_without_a_veto_never_refuses():
    assert activation.veto(["task"], ctx=None, configs=[Config("task")]) is None


def test_the_first_app_that_refuses_says_why():
    configs = [Config("sale"), Config("invoice", lambda ctx: None), Config("verifactu", lambda ctx: f"pending {ctx}")]
    assert activation.veto(["sale", "invoice", "verifactu"], ctx="x", configs=configs) == ("verifactu", "pending x")


def test_a_blank_reason_is_no_refusal():
    assert activation.veto(["task"], ctx=None, configs=[Config("task", lambda ctx: "  ")]) is None
