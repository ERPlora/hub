"""What the Hub's assistant knows of the business from the start of every conversation (``block``): its country, its
clock and the moment it is there, its language and the one the person chose, its sector, its apps on, for who runs it
its plan with the apps it counts, and the settings of each app on that the person may read (``SETTINGS_HOOK``).

Each is one short line, read from what the platform already keeps: ``base.business.get``, the registry's row of the
business at work and the SaaS's last photo on it, the person's «My profile», the apps on and the reads of their
settings. Nothing is asked of erplora.com, and what it did not register (a demo's country, sector or plan) is not said.
The clock is ``base.business.business_zone``, the one every hour told to a person is on: the tools' results come on it
too.
"""

import datetime as dt
from collections.abc import Mapping

from django.utils import timezone, translation
from live.assistant import tool_name
from live.context import OperationContext
from live.errors import OperationError
from live.meta import LiveAppConfig
from live.operations import get

from base import activation, home
from base.assistant import tools
from base.business import business_zone, language_name, zone_name
from base.permissions import ADMINISTER_HUB
from base.tenancy.context import current_hub

#: The attribute of an app's ``LiveAppConfig`` that names the reads of its settings, each a read of its own that needs
#: no data (``assistant_settings = ("cash_register.settings.get",)``): what each answers, as the tool would, is told in
#: every turn of a business where the app is on, to whoever may run it, so the model need not read them to answer.
SETTINGS_HOOK = "assistant_settings"


def block(ctx: OperationContext, business: Mapping, apps: Mapping[str, LiveAppConfig], *, now: dt.datetime) -> str:
    """The lines of the instructions on the business ``ctx`` works in, ``now``: ``business`` is what
    ``base.business.get`` read (empty when it could not), ``apps`` the apps on (``base.assistant.tools.active_apps``)."""
    hub = current_hub()
    zone = business_zone()
    local = timezone.localtime(now, zone)
    lines = ["The business, read now:"]
    if business.get("country"):
        lines.append(f"- Country: {business.get('country_name') or business['country']} ({business['country']}).")
    lines.append(
        f"- Time zone: {zone_name(zone)}. Now there: {local:%A %Y-%m-%d %H:%M} (UTC{local.isoformat()[-6:]}).\n"
        "  Tell every date and time on this clock: your tools give them on it."
    )
    lines += _languages(ctx, business)
    if hub is not None and hub.vertical:
        lines.append(f"- Sector: {hub.vertical}.")
    names = _names_on(ctx, apps, demo=hub is not None and hub.is_demo)
    if names:
        lines.append(f"- Apps on: {', '.join(names)}.")
    plan = _plan(hub) if ctx.has(ADMINISTER_HUB) else ""
    if plan:
        lines.append(f"- Plan: {plan}. {_apps_counted(ctx, hub)}")
    lines += _settings(ctx, apps)
    return "\n".join(lines)


def _languages(ctx: OperationContext, business: Mapping) -> list[str]:
    """The business's language and, for a person, the one they chose in «My profile» (none: they see the business's)."""
    if not business.get("language"):
        return []
    line = f"- Language of the business: {business.get('language_name')} ({business['language']})."
    own = _own_language(ctx)
    if own is not None:
        chosen = f"{language_name(own, ctx.language)} ({own})" if own else "none, so the business's"
        line += f" This person's own, in My profile: {chosen}."
    return [line]


def _own_language(ctx: OperationContext) -> str | None:
    """The language ``ctx``'s person chose in «My profile» ("" for none), or ``None`` when no person asks."""
    op = get("base.profile.get")
    try:
        return op(ctx, op.input()).language
    except OperationError:
        return None


def _settings(ctx: OperationContext, apps: Mapping[str, LiveAppConfig]) -> list[str]:
    """The settings of each app on that the person may read (its ``SETTINGS_HOOK``), by the app's name in the chat's
    language, as each read answers them now: on the business's clock and in its currency."""
    lines = []
    with translation.override(ctx.language):
        for config in apps.values():
            for name in getattr(config, SETTINGS_HOOK, ()):
                told = tools.run(ctx, get(name), "{}")
                if told.outcome == "ok":
                    lines.append(
                        f"- Settings of {config.verbose_name}, read now with `{tool_name(name)}` (no need to read them "
                        f"again): {told.content}"
                    )
    return lines


def _names_on(ctx: OperationContext, apps: Mapping[str, LiveAppConfig], *, demo: bool) -> list[str]:
    """The apps of the store on in the business, by the names its menu gives them in the chat's language."""
    with translation.override(ctx.language):
        return sorted((str(config.verbose_name) for config in home.shown_modules.home_modules(apps, demo_hub=demo)), key=str.casefold)


def _apps_counted(ctx: OperationContext, hub) -> str:
    """How many apps the plan counts against its limit, as Apps says it («14 of 40 of your plan»): the ones the
    business chose, never one that came with another app or was on from the start."""
    shown = {config.label for config in home.shown_modules.shown_modules(demo_hub=hub.is_demo)}
    used = activation.chosen_on(activation.states_of(ctx.scope), among=shown)
    limit = activation.plan_limit(hub.state)
    counted = f"{used} of {limit}" if limit else f"{used}, with no limit"
    return (
        f"Apps it counts: {counted} (only those the business chose, not one that came with another app or was on "
        "from the start)."
    )


def _plan(hub) -> str:
    """The plan the SaaS's last photo names (``plan.slug``), or "" when it names none."""
    state = hub.state if hub is not None and isinstance(hub.state, dict) else {}
    plan = state.get("plan")
    slug = plan.get("slug") if isinstance(plan, dict) else None
    return slug if isinstance(slug, str) else ""
