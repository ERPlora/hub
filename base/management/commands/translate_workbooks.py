"""``manage.py translate_workbooks [--app <id>] [--check]``: each app's ``WORKBOOK.<language>.md``.

The WORKBOOK is written in Spanish (it is the specification); its translation into each other language of
``settings.LANGUAGES`` is made from its user part (``base.catalog.user_part``), versioned next to it and marked section
by section (``base.workbook_sections``). The marks are the user part's, so editing «Para quien lo mantiene» never asks
for a new translation.

ERPlora uses no ``ANTHROPIC_API_KEY``: whoever edits a WORKBOOK translates the
change by hand, with the marks ``base.catalog.translate_by_hand`` names. ``--check`` is what runs (in
CI, through the tests): it never reaches the network nor needs the key, and fails listing, by language, the apps
whose translation exists and is out of date (a missing one is no error), telling the sections to translate
by hand, and every Spanish date placeholder (``AAAA``, ``aaaa``) a current one keeps outside its
fenced code blocks, by file and line: a translation writes the year ``YYYY``.

Without ``--check`` it translates through the Claude API, for whoever has a key; no error sends there.
The ``anthropic`` client is a development dependency, the key lives in the local ``.env`` (or the
environment) and the model is ``settings.WORKBOOK_TRANSLATION_MODEL``. Without the key, a module to
translate stops the command before any call, naming the key; an up-to-date one needs none and costs no call.
"""

import re
from pathlib import Path

import decouple
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from base import catalog
from base.workbook_help import SOURCE_LANGUAGE
from base.workbook_sections import MARK, marked, prose_lines

#: The fixed instructions of every translation, but for its language (``instructions``).
INSTRUCTIONS = """\
You translate the customer documentation of an app of ERPlora, a point-of-sale and back-office \
platform for small businesses in Spain, from Spanish into {language}.

The user message is a Markdown document. Reply with its {language} translation and nothing else: no \
preface, no notes, no code fence around it.

- Translate the prose, the headings, the text of tables and lists, and the alt text of images.
- Keep the Markdown structure exactly as it is: heading levels, lists, tables, emphasis, quotes \
and blank lines.
- Leave untouched: inline code and code blocks, identifiers such as `demo.item.created` or \
`inventory.manage`, URLs and external links, and image paths (`docs/img/...`).
- Translate the date placeholders of a pattern, even inside inline code: `AAAA` is `YYYY` and \
`aaaa` is `yyyy` (`OS-AAAAMMDD-NNNN` is `OS-YYYYMMDD-NNNN`, `DD/MM/AAAA` is `DD/MM/YYYY`); the \
rest of the pattern (`MM`, `DD`, `NNNN`, `hh:mm`) stays as it is.
- Rewrite every in-page link `(#...)` to point at its translated heading: the heading in lowercase, \
punctuation removed and spaces as hyphens (`## How to use it` is `#how-to-use-it`).
- Translate the labels of the app quoted with «...» as the {language} app shows them, in double quotes.
"""
#: Long WORKBOOKs come back whole: streamed, so the request never times out.
MAX_TOKENS = 64000
#: The Claude API key: without it no call is made.
API_KEY = "ANTHROPIC_API_KEY"
_IMAGE_PATH_RE = re.compile(r"docs/img/[^\s)\"'>]+")
#: A pattern still carrying the Spanish year placeholder (`OS-AAAAMMDD-NNNN`, `DD/MM/AAAA`).
_SPANISH_DATE_RE = re.compile(r"[\w/:-]*(?:AAAA|aaaa)[\w/:-]*")


def languages() -> list[str]:
    """The languages each WORKBOOK is translated into: the Hub's, but the one it is written in."""
    return [language for language, _name in settings.LANGUAGES if language != SOURCE_LANGUAGE]


def instructions(language: str) -> str:
    """The instructions of a translation into ``language``, by the name ``settings.LANGUAGES`` gives it."""
    return INSTRUCTIONS.format(language=dict(settings.LANGUAGES)[language])


def spanish_dates(configs, language: str) -> list[str]:
    """``<app>: <file>:<line>: <pattern>`` of each Spanish date placeholder in a current translation into ``language``.

    Its fenced code blocks are left as they are (the translation's own rule), so a pattern there is
    quoted on purpose and does not count; inline code does, as in ``OS-AAAAMMDD-NNNN``. Nor does a
    mark: its hash is hex, and may spell ``aaaa``. A stale or unreadable translation is
    ``stale_translations``'s.
    """
    found = []
    for config in configs:
        if not (Path(config.path) / catalog.WORKBOOK).is_file():
            continue
        try:
            state = catalog.workbook_translation(config, language)
        except catalog.WorkbookError:
            continue
        if state.state != "current":
            continue
        for number, line in prose_lines(state.path.read_text(encoding="utf-8")):
            if MARK.fullmatch(line):
                continue
            found += [
                f"{config.label}: {state.path.name}:{number}: {pattern}"
                for pattern in _SPANISH_DATE_RE.findall(line)
            ]
    return found


def translate(source: str, language: str) -> str:
    """The translation into ``language`` of ``source`` (a Spanish user part), in one call to the Claude API."""
    try:
        import anthropic
    except ModuleNotFoundError as error:
        raise CommandError(
            "translate_workbooks needs the anthropic client, a development dependency: run `uv sync`."
        ) from error
    # Read as every setting (environment, then this checkout's .env) and handed to the client, which
    # only looks at the environment: python-decouple exports nothing.
    api_key = decouple.config(API_KEY, default="")
    if not api_key:
        raise CommandError(
            f"translate_workbooks needs {API_KEY} to call the Claude API: set it in this checkout's .env "
            "(or the environment) and run it again. translate_workbooks --check needs no key."
        )
    try:
        with anthropic.Anthropic(api_key=api_key).messages.stream(
            model=settings.WORKBOOK_TRANSLATION_MODEL,
            max_tokens=MAX_TOKENS,
            system=instructions(language),
            messages=[{"role": "user", "content": source}],
        ) as stream:
            message = stream.get_final_message()
    except anthropic.APIError as error:
        raise CommandError(
            f"The Claude API failed, nothing written: {error}"
        ) from error
    if message.stop_reason != "end_turn":
        raise CommandError(
            f"The Claude API stopped with {message.stop_reason!r} instead of finishing: nothing written."
        )
    return "".join(block.text for block in message.content if block.type == "text")


class Command(BaseCommand):
    help = (
        "Check each app's WORKBOOK.<language>.md (the modules' and base's), translated by hand from the user part "
        "of its WORKBOOK.md (--check); without --check, generate it through the Claude API."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--app", help="Only this app (its label, e.g. inventory or base)."
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Fail when a translation is out of date or keeps a Spanish date; never reaches the network.",
        )

    def handle(self, *args, app: str | None = None, check: bool = False, **options):
        # The modules and base (the platform's WORKBOOK): base is no module of the store, but its
        # translations are generated and checked like theirs.
        configs = catalog.workbook_configs()
        if app is not None:
            known = ", ".join(sorted(config.label for config in configs))
            configs = [config for config in configs if config.label == app]
            if not configs:
                raise CommandError(f"No app {app!r} with a WORKBOOK to translate; the apps are: {known}.")
        if check:
            self._check(configs)
            return
        for config in configs:
            if (Path(config.path) / catalog.WORKBOOK).is_file():
                self._translate(config)

    def _check(self, configs) -> None:
        files = {language: catalog.WORKBOOK_TRANSLATION.format(language) for language in languages()}
        problems = []
        for language, file in files.items():
            stale = catalog.stale_translations(configs, language)
            if stale:
                problems += [f"Out of date {file}: {', '.join(stale)}."]
                problems += [f"{label}: {what_to_do}" for label, what_to_do in stale.items()]
            dates = spanish_dates(configs, language)
            if dates:
                problems += [f"Spanish date placeholders left in {file} (a translation writes the year YYYY, or yyyy):"]
                problems += dates
        if problems:
            raise CommandError("\n".join(problems))
        self.stdout.write(f"Every {', '.join(files.values())} is up to date.")

    def _translate(self, config) -> None:
        written = [language for language in languages() if self._translate_into(config, language)]
        if not written:
            self.stdout.write(f"{config.label}: up to date.")

    def _translate_into(self, config, language: str) -> bool:
        """Write ``config``'s translation into ``language``; ``False`` when it was already current."""
        try:
            state = catalog.workbook_translation(config, language)
        except catalog.WorkbookError as error:
            raise CommandError(
                f"{config.label}: {catalog.WORKBOOK}: {error}"
            ) from error
        if state.state == "current":
            return False
        translated = translate(state.source, language).strip() + "\n"
        file = f"{config.label}: {state.path.name}"
        lost = sorted(
            set(_IMAGE_PATH_RE.findall(state.source))
            - set(_IMAGE_PATH_RE.findall(translated))
        )
        if lost:
            raise CommandError(
                f"{file}: the translation changed the image paths {', '.join(lost)}: nothing written."
            )
        spanish_dates = sorted(set(_SPANISH_DATE_RE.findall(translated)))
        if spanish_dates:
            raise CommandError(
                f"{file}: the translation kept the Spanish date placeholders {', '.join(spanish_dates)}: nothing written."
            )
        try:
            catalog.check_anchors(translated)
        except catalog.WorkbookError as error:
            raise CommandError(
                f"{file}: the translation {error} Nothing written."
            ) from error
        text = marked(state.source, translated)
        if text is None:
            raise CommandError(f"{file}: the translation has other headings than {catalog.WORKBOOK}: nothing written.")
        state.path.write_text(text, encoding="utf-8")
        self.stdout.write(
            f"{config.label}: wrote {state.path.name}; review the diff before committing it."
        )
        return True
