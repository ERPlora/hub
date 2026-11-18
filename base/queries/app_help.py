"""The help window of a module (``base.help.get``), read from its WORKBOOK in the person's language."""

from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path

from django.conf import settings
from django.utils import translation
from django.utils.translation import get_supported_language_variant, gettext_lazy, pgettext_lazy
from live.context import OperationContext
from live.errors import NotFound
from live.meta import LiveAppConfig, module_configs
from live.operations import AI, operation

from base import workbook_help
from base.permissions import VIEW_HOME
from base.schemas.app_help import AppHelpIn, AppHelpOut

HELP_MISSING = gettext_lazy("This app has no help yet.")
#: The tab of a module's settings when its menu has no entry for them, at ``/<module>/settings``.
SETTINGS_TAB = "settings"
SETTINGS = pgettext_lazy("workbook", "Settings")
#: The help read so far, by module and language: a module's WORKBOOKs only change with a new image, so each one is read
#: and cut once per process. With DEBUG, on every call, so that an edited WORKBOOK shows at once.
_READ: dict[tuple[str, str], dict] = {}


def ready_apps() -> list[str]:
    """The modules whose help is ready: those that declare ``help``."""
    return [config.label for config in module_configs() if config.help is not None]


def tabs_of(config: LiveAppConfig) -> list[workbook_help.Tab]:
    """A module's tabs in the active language: the entries of its menu, then its settings when the menu has none."""
    tabs = [workbook_help.Tab(nav.id, str(nav.label), nav.path) for nav in config.navigation]
    if all(tab.id != SETTINGS_TAB for tab in tabs):
        tabs.append(workbook_help.Tab(SETTINGS_TAB, str(SETTINGS), f"/{config.label}/settings"))
    return tabs


def _ready(label: str) -> LiveAppConfig | None:
    return next((config for config in module_configs() if config.label == label and config.help is not None), None)


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
    """A module's help in the person's language while its file is current, else in its base language's, else in the
    source's (``language`` says which); its video likewise."""
    config = _ready(data.app)
    if config is None:
        with translation.override(ctx.language):
            raise NotFound(str(HELP_MISSING), code="base.help_missing")
    language = _language(ctx.language)
    return {**_read(config, language), "video": _video(config.help.videos, language)}


def _read(config: LiveAppConfig, language: str) -> dict:
    """The help of ``config`` for ``language`` (``_READ``), with the name of the module in the language served."""
    key = (config.label, language)
    if key not in _READ or settings.DEBUG:
        served, markdown = workbook_help.workbook(Path(config.path), language)
        with translation.override(served):
            read = workbook_help.parse(markdown, tabs_of(config), workbook_help.words())
            name = str(config.verbose_name)
        _READ[key] = {
            "app": config.label,
            "name": name,
            "language": served,
            "purpose": read.purpose,
            "screens": [asdict(screen) for screen in read.screens],
            "flows": [asdict(flow) for flow in read.flows],
        }
    return _READ[key]


def _video(videos: Mapping[str, str], language: str) -> str | None:
    """The module's video in ``language``, else in its base language (``en`` for ``en-gb``), else in the source's."""
    return next(
        (videos[code] for code in (language, language.split("-")[0], workbook_help.SOURCE_LANGUAGE) if videos.get(code)),
        None,
    )
