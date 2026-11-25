"""The help of an app (``base.help.get``), a module's or the Hub's own screens', read from its WORKBOOK in the person's
language."""

from collections.abc import Mapping
from dataclasses import asdict, replace
from pathlib import Path

from django.conf import settings
from django.utils import translation
from django.utils.translation import get_supported_language_variant, gettext_lazy, pgettext_lazy
from live.context import OperationContext
from live.errors import NotFound
from live.meta import Help, LiveAppConfig, all_live_app_configs
from live.operations import AI, operation

from base import platform_screens, workbook_help
from base.permissions import VIEW_HOME
from base.schemas.app_help import AppHelpIn, AppHelpOut

HELP_MISSING = gettext_lazy("This app has no help yet.")
#: The tab of a module's settings when its menu has no entry for them, at ``/<module>/settings``.
SETTINGS_TAB = "settings"
SETTINGS = pgettext_lazy("workbook", "Settings")
#: The help read so far, by app and language: an app's WORKBOOKs only change with a new image, so each one is read and
#: cut once per process. With DEBUG, on every call, so that an edited WORKBOOK shows at once.
_READ: dict[tuple[str, str], dict] = {}


def ready_apps() -> list[str]:
    """The apps whose help is ready: those that declare ``help``."""
    return [config.label for config in all_live_app_configs() if config.help is not None]


def tabs_of(config: LiveAppConfig) -> list[workbook_help.Tab]:
    """An app's tabs in the active language: the Hub's own screens for the platform; for a module, the entries of its
    menu, then its settings when the menu has none."""
    if config.kind == "platform":
        return [replace(screen, label=str(screen.label)) for screen in platform_screens.SCREENS]
    tabs = [workbook_help.Tab(nav.id, str(nav.label), nav.path) for nav in config.navigation]
    if all(tab.id != SETTINGS_TAB for tab in tabs):
        tabs.append(workbook_help.Tab(SETTINGS_TAB, str(SETTINGS), f"/{config.label}/settings"))
    return tabs


def _ready(label: str) -> LiveAppConfig | None:
    return next((config for config in all_live_app_configs() if config.label == label and config.help is not None), None)


def _language(code: str) -> str:
    """The deployment's language ``code`` names (``en-GB`` is ``en``), else the WORKBOOK's source language."""
    try:
        return get_supported_language_variant(code)
    except LookupError:
        return workbook_help.SOURCE_LANGUAGE


@operation(
    "base.help.get",
    kind="query",
    permission=VIEW_HOME,
    database=False,
    input=AppHelpIn,
    output=AppHelpOut,
    ai=AI(
        description=(
            "The help of one app of the business by its id (e.g. table, sale), as its help window shows it: what the app "
            "is for, what each of its screens shows and the steps of each task it does, in the person's language. Only "
            "the apps whose help is ready have one."
        ),
        asks={
            "en": (
                "show me the help of Tables",
                "what is each screen of Sales for?",
                "explain the floor plan screen to me",
            ),
            "es": (
                "enséñame la ayuda de las pantallas de Mesas",
                "¿para qué sirve cada pantalla de Ventas?",
                "explícame la pantalla del plano de sala",
            ),
        },
    ),
)
def help_get(ctx: OperationContext, data: AppHelpIn) -> dict:
    """An app's help in the person's language while its file is current, else in its base language's, else in the
    source's (``language`` says which); its video and each task's short videos likewise. Without the screens whose
    permission the person does not hold, nor the tasks done only on them or whose own they do not."""
    config = _ready(data.app)
    if config is None:
        with translation.override(ctx.language):
            raise NotFound(str(HELP_MISSING), code="base.help_missing")
    language = _language(ctx.language)
    read = _read(config, language)
    closed = {tab.id for tab in tabs_of(config) if not ctx.has(tab.permission)}
    return {
        **read,
        "screens": [screen for screen in read["screens"] if screen["id"] not in closed],
        "video": _in_language(config.help.videos, language),
        "flows": [
            {**flow, "screens": screens, "videos": _flow_videos(config.help, flow["id"], language)}
            for flow in read["flows"]
            if ctx.has(flow["permission"]) and (screens := [tab for tab in flow["screens"] if tab not in closed])
        ],
    }


def _read(config: LiveAppConfig, language: str) -> dict:
    """The help of ``config`` for ``language`` (``_READ``), with the name of the app in the language served and the
    permission each task asks for (none in a module: whoever opens it)."""
    key = (config.label, language)
    if key not in _READ or settings.DEBUG:
        served, read = help_of(config, language)
        platform = config.kind == "platform"
        with translation.override(served):
            name = platform_screens.NAME if platform else str(config.verbose_name)
            asked = {flow.id: platform_screens.permission_of(read.actors[flow.id]) for flow in read.flows if platform}
        _READ[key] = {
            "app": config.label,
            "name": name,
            "language": served,
            "purpose": read.purpose,
            "screens": [asdict(screen) for screen in read.screens],
            "flows": [{**asdict(flow), "permission": asked.get(flow.id)} for flow in read.flows],
        }
    return _READ[key]


def help_of(config: LiveAppConfig, language: str) -> tuple[str, workbook_help.Help]:
    """The language ``config``'s help is served in for ``language`` and what its window reads there."""
    served, markdown = workbook_help.workbook(Path(config.path), language)
    with translation.override(served):
        return served, workbook_help.parse(markdown, tabs_of(config), workbook_help.words())


def _flow_videos(declared: Help, flow: str, language: str) -> list[str]:
    """The short videos of ``flow`` in ``language`` (as ``_in_language``), none when it has no videos."""
    return list(_in_language(declared.flow_videos.get(flow, {}), language) or ())


def _in_language[T](by_language: Mapping[str, T], language: str) -> T | None:
    """What ``by_language`` holds for ``language``, else for its base language (``en`` for ``en-gb``), else for the
    source's."""
    return next(
        (
            by_language[code]
            for code in (language, language.split("-")[0], workbook_help.SOURCE_LANGUAGE)
            if by_language.get(code)
        ),
        None,
    )
