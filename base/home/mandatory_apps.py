"""The apps a business must have on in its country, as each app declares it (``mandatory``)."""

import re
from collections.abc import Iterable, Mapping
from typing import Any

from django.core import checks
from django.utils import translation
from django.utils.translation import gettext
from live.meta import all_live_app_configs, LiveAppConfig

from base.business import country_name, country_or_market
from base.home.setup_steps import STATE_PENDING, applies_to_country, item, level_of
from base.home.shown_modules import shell_icon

#: Where an app declares the countries where a business must have it on (:func:`mandatory_steps`, hub#997): its
#: ``countries`` (:data:`EVERY_COUNTRY`, or the ISO 3166-1 alpha-2 codes) and whether the platform turns it on by itself
#: at sign-up (``platform_turns_on``: never one that binds the business to a tax authority).
MANDATORY_ATTRIBUTE = "mandatory"
MANDATORY_FIELDS = frozenset({"countries", "platform_turns_on"})
#: The ``countries`` of an app mandatory wherever the business is.
EVERY_COUNTRY = "all"
COUNTRY_CODE = re.compile(r"[A-Z]{2}")
#: Where the step that asks to turn a mandatory app on goes: right after «Your apps» (10), before any app's own step.
MANDATORY_ORDER = 15
#: Apps, on «Add apps»: the tab where an app off is (the default one lists the business's own).
CATALOGUE_ROUTE = "/apps#all"


def mandatory_in(config: LiveAppConfig, hub_country: str) -> bool:
    """Whether a business of ``hub_country`` must have ``config``'s app on, as the app declares it in
    :data:`MANDATORY_ATTRIBUTE`; a business without a country is in ERPlora's market, Spain (:func:`applies_to_country`)."""
    declared = getattr(config, MANDATORY_ATTRIBUTE, None)
    if not isinstance(declared, Mapping):
        return False
    countries = declared.get("countries")
    return countries == EVERY_COUNTRY or bool(countries) and applies_to_country(countries, hub_country)


def mandatory_steps(configs: Iterable[LiveAppConfig], on: frozenset[str], hub_country: str) -> list[dict]:
    """A step of the platform for each app of ``configs`` a business of ``hub_country`` must have on and does not (hub#997):
    important, it leads to Apps and goes once the app is on, when the app's own steps follow. Base names no app: each
    one says where it is mandatory (:data:`MANDATORY_ATTRIBUTE`). The texts in the language active now."""
    country = country_name(country_or_market(hub_country), translation.get_language())
    return [
        item(
            f"base.mandatory.{config.label}",
            "base",
            state=STATE_PENDING,
            required=True,
            level=level_of(f"base.mandatory.{config.label}", True),
            actionable=True,
            title=gettext("Turn on %(app)s") % {"app": config.verbose_name},
            description=gettext("It is mandatory for businesses in %(country)s.") % {"country": country},
            icon=shell_icon(config),
            route=CATALOGUE_ROUTE,
            order=MANDATORY_ORDER,
        )
        for config in configs
        if config.label not in on and mandatory_in(config, hub_country)
    ]


def mandatory_problems(declared: Any) -> list[str]:
    """What is wrong with an app's :data:`MANDATORY_ATTRIBUTE`."""
    if not isinstance(declared, Mapping):
        return [f"is {declared!r}, not a mapping"]
    problems = [f"has {field!r}, which it does not take" for field in sorted(set(declared) - MANDATORY_FIELDS)]
    countries = declared.get("countries")
    if countries != EVERY_COUNTRY:
        if not isinstance(countries, list | tuple) or not countries:
            problems.append(f"says countries {countries!r}, neither {EVERY_COUNTRY!r} nor a list of country codes")
        else:
            problems += [
                f"names {code!r}, which is no upper-case ISO 3166-1 alpha-2 code"
                for code in countries
                if not isinstance(code, str) or not COUNTRY_CODE.fullmatch(code)
            ]
            if len(set(countries)) != len(countries):
                problems.append(f"names a country twice in {countries!r}")
    if not isinstance(declared.get("platform_turns_on"), bool):
        problems.append("does not say whether the platform turns it on by itself (platform_turns_on: True or False)")
    return problems


def mandatory_errors(configs: Iterable[LiveAppConfig]) -> list[checks.CheckMessage]:
    """``base.E016``: ``mandatory`` says the countries (``"all"`` or their codes, never an empty list, which would read as
    «nowhere» or «everywhere») and whether the platform turns the app on by itself: a slip would ask every business for
    an app, or none."""
    hint = (
        f'Declare {MANDATORY_ATTRIBUTE} = {{"countries": "{EVERY_COUNTRY}" or ["ES", …], "platform_turns_on": True or '
        "False} on the LiveAppConfig of the module."
    )
    errors = []
    for config in configs:
        declared = getattr(config, MANDATORY_ATTRIBUTE, None)
        if declared is None:
            continue
        errors += [
            checks.Error(f"{config.label}'s {MANDATORY_ATTRIBUTE} {problem}.", hint=hint, obj=config, id="base.E016")
            for problem in mandatory_problems(declared)
        ]
    return errors


@checks.register("base")
def check_mandatory_apps(app_configs: Any, **kwargs: Any) -> list[checks.CheckMessage]:
    return mandatory_errors(all_live_app_configs())
