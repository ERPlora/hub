"""The apps a business must have on in its country (hub#997)."""

from types import SimpleNamespace

import pytest
from django.utils.translation import override

from base import home


def obliged(label="fiscal", countries=("PT",), platform_turns_on=False, **more):
    """A stand-in app that declares where it is mandatory, as tax and verifactu do; base never names a real one. Its
    store icon is not the shell's: the shell paints an app with its first menu entry's."""
    from live.meta import Nav

    declared = {"countries": countries if countries == "all" else list(countries), "platform_turns_on": platform_turns_on}
    more.setdefault("navigation", [Nav("records", "Records", "ion:list-outline", f"/{label}/records")])
    return SimpleNamespace(label=label, verbose_name=label.capitalize(), icon="ion:calculator-outline", mandatory=declared, **more)


@pytest.mark.parametrize(
    ("countries", "hub_country", "mandatory"),
    [
        ("all", "PT", True),
        ("all", "JP", True),
        ("all", "", True),
        (["PT"], "PT", True),
        (["pt"], "PT", True),
        (["PT", "ES"], "ES", True),
        (["PT"], "FR", False),
        ([], "PT", False),  # a slip the check refuses (base.E016) never reads as «every country»
        # A business without a country (a demo, ERPlora's own) is in ERPlora's market, Spain (hub#682).
        (["ES"], "", True),
        (["PT"], "", False),
    ],
)
def test_an_app_is_mandatory_in_the_countries_it_declares(countries, hub_country, mandatory):
    assert home.mandatory_apps.mandatory_in(obliged(countries=countries), hub_country) is mandatory


def test_an_app_that_declares_nothing_is_mandatory_nowhere():
    assert home.mandatory_apps.mandatory_in(SimpleNamespace(label="things"), "ES") is False


def test_a_mandatory_app_off_is_a_step_of_the_platform_to_turn_it_on():
    with override("en"):
        steps = home.mandatory_apps.mandatory_steps([obliged()], on=frozenset(), hub_country="PT")

    assert steps == [
        {
            "key": "base.mandatory.fiscal",
            "app": "base",
            "state": "pending",
            "required": True,
            "level": "functional",
            "actionable": True,
            "title": "Turn on Fiscal",
            "description": "It is mandatory for businesses in Portugal.",
            "icon": "ion:list-outline",
            "route": "/apps#all",
            "order": 15,
        }
    ]


def test_the_step_says_the_app_and_the_country_in_the_persons_language():
    from django.utils.translation import gettext_lazy

    app = obliged(countries=["ES"])
    app.verbose_name = gettext_lazy("Taxes")

    with override("es"):
        (step,) = home.mandatory_apps.mandatory_steps([app], on=frozenset(), hub_country="")

    assert (step["title"], step["description"]) == ("Activa Impuestos", "Es obligatoria para los negocios de España.")


def test_the_step_goes_once_the_app_is_on_and_never_comes_for_another_country():
    apps = [obliged("fiscal", ["PT"]), obliged("ledger", "all"), obliged("seal", ["FR"]), SimpleNamespace(label="things")]

    assert [step["key"] for step in home.mandatory_apps.mandatory_steps(apps, on=frozenset(), hub_country="PT")] == [
        "base.mandatory.fiscal",
        "base.mandatory.ledger",
    ]
    assert [step["key"] for step in home.mandatory_apps.mandatory_steps(apps, on=frozenset({"fiscal"}), hub_country="PT")] == [
        "base.mandatory.ledger"
    ]
    assert home.mandatory_apps.mandatory_steps(apps, on=frozenset({"fiscal", "ledger"}), hub_country="PT") == []


def test_the_step_has_the_icon_the_shell_paints_for_the_app_never_its_store_one():
    """The store's icon is baked apart, and HubIcon refuses a name the shell has not registered: the step paints the
    app as «My apps» and the launcher do, by its first menu entry, or the shell's own for an app without a menu."""
    assert home.mandatory_apps.mandatory_steps([obliged()], on=frozenset(), hub_country="PT")[0]["icon"] == "ion:list-outline"
    assert home.mandatory_apps.mandatory_steps([obliged(navigation=[])], on=frozenset(), hub_country="PT")[0]["icon"] == "ion:apps-outline"


@pytest.mark.parametrize(
    ("declared", "errors"),
    [
        (None, 0),
        ({"countries": "all", "platform_turns_on": True}, 0),
        ({"countries": ["ES"], "platform_turns_on": False}, 0),
        ({"countries": ("ES", "PT"), "platform_turns_on": False}, 0),
        (["ES"], 1),  # the countries alone, not what the platform may do
        ({"countries": [], "platform_turns_on": False}, 1),  # mandatory nowhere: an empty list must not read as «all»
        ({"countries": "ES", "platform_turns_on": False}, 1),  # a code, not a list of them
        ({"countries": ["Spain"], "platform_turns_on": False}, 1),  # ISO 3166-1 alpha-2, never a name
        ({"countries": ["es"], "platform_turns_on": False}, 1),  # upper-case, as the business's country comes
        ({"countries": ["ES", "ES"], "platform_turns_on": False}, 1),
        ({"countries": "all"}, 1),  # it must say whether the platform turns it on by itself
        ({"countries": "all", "platform_turns_on": "yes"}, 1),
        ({"countries": "all", "platform_turns_on": True, "verticals": ["restaurant"]}, 1),  # a field misspelt or not ours
    ],
)
def test_what_an_app_declares_as_mandatory_is_checked_at_start(declared, errors):
    app = SimpleNamespace(label="things")
    if declared is not None:
        app.mandatory = declared

    found = home.mandatory_apps.mandatory_errors([app])

    assert len(found) == errors
    assert all(error.id == "base.E016" for error in found)


def test_the_check_of_the_mandatory_apps_runs_with_the_others(monkeypatch):
    from django.core import checks

    monkeypatch.setattr("base.home.mandatory_apps.all_live_app_configs", lambda: [SimpleNamespace(label="things", mandatory=["ES"])])

    assert [message.id for message in checks.run_checks(tags=["base"]) if message.id == "base.E016"] == ["base.E016"]


def test_base_names_no_app_where_it_reads_the_mandatory_ones():
    """Modularity (hub#997): which apps are mandatory, and where, only their own ``LiveAppConfig`` says. No literal of the
    code that reads it names an app, nor one of its operations or steps (``"verifactu"``, ``"tax.rules"``)."""
    import ast
    import inspect

    from live.meta import module_configs
    from live.operations import get

    from base import queries

    labels = {config.label for config in module_configs()}
    readers = [
        home.mandatory_apps.mandatory_in,
        home.mandatory_apps.mandatory_steps,
        home.mandatory_apps.mandatory_problems,
        home.mandatory_apps.mandatory_errors,
        get("base.setup.status").fn,
        queries.home._platform_steps,
    ]
    named = sorted(
        node.value
        for reader in readers
        for node in ast.walk(ast.parse(inspect.getsource(inspect.unwrap(reader)).lstrip()))
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and (node.value in labels or node.value.split(".")[0] in labels)
    )
    assert labels and named == []
