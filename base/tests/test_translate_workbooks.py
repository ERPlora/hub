"""translate_workbooks: each app's WORKBOOK.<language>.md (the modules' and base's), generated from its Spanish user
part, for every language of the Hub but Spanish: today English, and here a test language too.

The hash is the user part's, not the file's: touching «Para quien lo mantiene» costs nothing. With
the hash in the header unchanged, no call; otherwise one call and the header with the new hash.
``--check`` never reaches the network: it fails on a stale translation, telling to translate it by
hand with the header ``HEADER_COMMAND`` prints (ERPlora uses no API key), and on
a Spanish date placeholder left in a current one. The API is always a double here: ``translate`` (one
call to the Claude API) is replaced, and its own test fakes the SDK client. ``ANTHROPIC_API_KEY`` comes
from the environment or the checkout's ``.env``, like every setting; here only from the test's own
(``key``): without it, the command stops before the API with an error that names it.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import anthropic
import decouple
import pytest
from decouple import Config, RepositoryEmpty, RepositoryEnv
from django.apps import apps as django_apps
from django.core.management import CommandError, call_command

from base import catalog, workbook_help
from base.catalog import en_header, source_hash
from base.management.commands import translate_workbooks
from base.tests.test_catalog import USER_PART, WORKBOOK, module, translated

#: The command that prints the first line of a hand-made WORKBOOK.en.md.
HEADER_COMMAND = (
    'uv run python manage.py shell --no-imports -c "from django.apps import apps; from base import catalog; '
    "print(catalog.en_header(catalog.source_hash(catalog.workbook_translation(apps.get_app_config('{}')).source)))\""
)
ENGLISH = "## What it is for\n\nKeeps **things**. See [how to use it](#how-to-use-it).\n\n![List of things](docs/img/list.png)\n\n## How to use it\n\n### Step by step\nStatus: done\n"


class FakeTranslator:
    """Stands in for ``translate``: records each source and its language and answers ``english``, or fails if called."""

    def __init__(self, english: str = ENGLISH, *, allowed: bool = True):
        self.english, self.allowed, self.sources, self.languages = english, allowed, [], []

    def __call__(self, source: str, language: str) -> str:
        if not self.allowed:
            raise AssertionError("translate_workbooks reached the API")
        self.sources.append(source)
        self.languages.append(language)
        return self.english


@pytest.fixture
def installed(monkeypatch):
    """Make ``configs`` our installed apps: the modules (``kind == "app"``) and the platform's."""

    def install(*configs):
        monkeypatch.setattr(catalog, "module_configs", lambda: [config for config in configs if config.kind == "app"])
        monkeypatch.setattr(catalog, "all_live_app_configs", lambda: list(configs))
        return configs

    return install


@pytest.fixture
def translator(monkeypatch):
    def install(**kwargs) -> FakeTranslator:
        fake = FakeTranslator(**kwargs)
        monkeypatch.setattr(translate_workbooks, "translate", fake)
        return fake

    return install


def file_in(config, language: str) -> Path:
    return Path(config.path) / f"WORKBOOK.{language}.md"


def en_file(config) -> Path:
    return file_in(config, "en")


@pytest.fixture
def german(settings):
    """A third language of the Hub, with no other change: what adding one to ``LANGUAGES`` does."""
    settings.LANGUAGES = [*settings.LANGUAGES, ("de", "Deutsch")]
    return "de"


def test_an_up_to_date_translation_never_calls_the_api(tmp_path, installed, translator):
    [config] = installed(module(tmp_path, en=translated(USER_PART, ENGLISH)))
    before = en_file(config).read_text()
    translator(allowed=False)

    call_command("translate_workbooks")

    assert en_file(config).read_text() == before


def test_the_maintainers_part_does_not_count(tmp_path, installed, translator):
    workbook = WORKBOOK.replace("- Notas internas.", "- Otras notas internas, más largas.")
    [config] = installed(module(tmp_path, workbook=workbook, en=translated(USER_PART, ENGLISH)))
    translator(allowed=False)

    call_command("translate_workbooks")


def test_a_changed_user_part_is_translated_once_with_the_new_hash(tmp_path, installed, translator):
    [config] = installed(module(tmp_path, en=translated("una versión anterior\n", ENGLISH)))
    fake = translator()

    call_command("translate_workbooks")

    assert fake.sources == [USER_PART]
    assert en_file(config).read_text() == f"{en_header(source_hash(USER_PART))}\n\n{ENGLISH}"
    # What register_apps then accepts as current.
    assert catalog.workbook_translation(config).state == "current"


def test_a_module_without_translation_gets_one(tmp_path, installed, translator):
    [config] = installed(module(tmp_path))
    fake = translator()

    call_command("translate_workbooks")

    assert len(fake.sources) == 1
    assert en_file(config).read_text().startswith(en_header(source_hash(USER_PART)))


def test_only_the_module_asked_for(tmp_path, installed, translator):
    installed(module(tmp_path, "things"), module(tmp_path, "stock"))
    fake = translator()

    call_command("translate_workbooks", "--app", "stock")

    assert len(fake.sources) == 1
    assert not en_file(SimpleNamespace(path=tmp_path / "things")).exists()
    assert en_file(SimpleNamespace(path=tmp_path / "stock")).exists()


def test_an_unknown_module_fails(tmp_path, installed, translator):
    installed(module(tmp_path))
    translator(allowed=False)
    with pytest.raises(CommandError, match="nope"):
        call_command("translate_workbooks", "--app", "nope")


def test_image_paths_must_come_back_intact(tmp_path, installed, translator):
    [config] = installed(module(tmp_path))
    translator(english=ENGLISH.replace("docs/img/list.png", "docs/img/lista.png"))

    with pytest.raises(CommandError, match="docs/img/list.png"):
        call_command("translate_workbooks")

    assert not en_file(config).exists()


def test_a_translation_with_a_dangling_anchor_is_not_written(tmp_path, installed, translator):
    [config] = installed(module(tmp_path))
    translator(english=ENGLISH.replace("(#how-to-use-it)", "(#cómo-se-usa)"))

    with pytest.raises(CommandError, match="#cómo-se-usa"):
        call_command("translate_workbooks")

    assert not en_file(config).exists()


# ── date patterns: `OS-AAAAMMDD-NNNN` came back untouched from inline code (cart_checkout, kitchen, task) ──


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize("pattern", ["OS-AAAAMMDD-NNNN", "DD/MM/AAAA", "dd/mm/aaaa"])
def test_a_translation_that_keeps_a_spanish_date_placeholder_is_not_written(
    tmp_path, installed, translator, settings, pattern, language
):
    settings.LANGUAGES = [("es", "Español"), (language, "Any")]
    [config] = installed(module(tmp_path))
    translator(english=ENGLISH.replace("Keeps **things**.", f"Keeps **things**, numbered `{pattern}`."))

    with pytest.raises(CommandError, match=re.escape(pattern)) as raised:
        call_command("translate_workbooks")

    assert f"things: WORKBOOK.{language}.md: " in str(raised.value)
    assert not file_in(config, language).exists()


def test_a_translation_with_english_date_placeholders_is_written(tmp_path, installed, translator):
    [config] = installed(module(tmp_path))
    english = ENGLISH.replace("Keeps **things**.", "Keeps **things**, numbered `OS-YYYYMMDD-NNNN` on `DD/MM/YYYY`.")
    translator(english=english)

    call_command("translate_workbooks")

    assert en_file(config).read_text().endswith(english)


def test_the_instructions_translate_the_date_placeholders_even_in_inline_code():
    for spanish, english in (
        ("`AAAA`", "`YYYY`"),
        ("`aaaa`", "`yyyy`"),
        ("`OS-AAAAMMDD-NNNN`", "`OS-YYYYMMDD-NNNN`"),
        ("`DD/MM/AAAA`", "`DD/MM/YYYY`"),
    ):
        assert f"{spanish} is {english}" in translate_workbooks.instructions("en")


def test_check_lists_the_stale_translations_without_the_network(tmp_path, installed, translator):
    installed(
        module(tmp_path, "current", en=translated(USER_PART, ENGLISH)),
        module(tmp_path, "stale", en=translated("una versión anterior\n", ENGLISH)),
        module(tmp_path, "untranslated"),
    )
    translator(allowed=False)

    with pytest.raises(CommandError, match=r"stale") as raised:
        call_command("translate_workbooks", "--check")

    assert "current" not in str(raised.value) and "untranslated" not in str(raised.value)


def test_check_passes_when_every_translation_is_current_or_missing(tmp_path, installed, translator):
    installed(module(tmp_path, "current", en=translated(USER_PART, ENGLISH)), module(tmp_path, "untranslated"))
    translator(allowed=False)

    call_command("translate_workbooks", "--check")


def test_check_tells_to_translate_each_stale_one_by_hand_with_its_header_never_through_the_api(tmp_path, installed, translator):
    """ERPlora uses no ANTHROPIC_API_KEY: whoever reads the error translates by hand."""
    installed(
        module(tmp_path, "current", en=translated(USER_PART, ENGLISH)),
        module(tmp_path, "stale", en=translated("una versión anterior\n", ENGLISH)),
        module(tmp_path, "stock", en="## What it is for\n"),
    )
    translator(allowed=False)

    with pytest.raises(CommandError) as raised:
        call_command("translate_workbooks", "--check")

    message = str(raised.value)
    assert message.startswith("Out of date WORKBOOK.en.md: stale, stock.")
    assert "translate_workbooks --app" not in message
    for label in ("stale", "stock"):
        assert (
            f"{label}: translate by hand the part of WORKBOOK.md that changed into WORKBOOK.en.md "
            f"and make its first line the header this prints: {HEADER_COMMAND.format(label)}"
        ) in message
    assert HEADER_COMMAND.format("current") not in message


def test_the_real_modules_are_up_to_date(translator):
    translator(allowed=False)
    call_command("translate_workbooks", "--check")


# ── --check and the Spanish date placeholders a hand-made translation keeps (hub#225's guard) ──────


def body_with(line: str) -> str:
    """``ENGLISH`` with ``line`` in place of its first paragraph."""
    return ENGLISH.replace("Keeps **things**. See [how to use it](#how-to-use-it).", line)


def line_of(text: str, needle: str) -> int:
    [number] = [number for number, line in enumerate(text.splitlines(), start=1) if needle in line]
    return number


@pytest.mark.parametrize("language", ["en", "de"])
@pytest.mark.parametrize(
    "line",
    [
        "Numbered `OS-AAAAMMDD-NNNN`.",
        "Born on DD/MM/AAAA.",
        "Born on dd/mm/aaaa, see [how to use it](#how-to-use-it).",
    ],
    ids=["inline-code", "prose", "lowercase"],
)
def test_check_fails_naming_the_file_and_line_of_a_spanish_date_in_a_current_translation(
    tmp_path, installed, translator, german, line, language
):
    text = translated(USER_PART, body_with(line))
    current, things = installed(module(tmp_path, "current"), module(tmp_path))
    for code in ("en", "de"):
        file_in(current, code).write_text(translated(USER_PART, ENGLISH))
        file_in(things, code).write_text(text if code == language else translated(USER_PART, ENGLISH))
    translator(allowed=False)

    with pytest.raises(CommandError) as raised:
        call_command("translate_workbooks", "--check")

    [pattern] = translate_workbooks._SPANISH_DATE_RE.findall(line)
    [other] = {"en", "de"} - {language}
    message = str(raised.value)
    assert f"Spanish date placeholders left in WORKBOOK.{language}.md" in message
    assert f"things: WORKBOOK.{language}.md:{line_of(text, pattern)}: {pattern}" in message
    assert f"WORKBOOK.{other}.md" not in message
    assert "current:" not in message and "Out of date" not in message


def test_check_ignores_a_spanish_date_quoted_in_a_fenced_code_block_and_counts_the_one_after_it(tmp_path, installed, translator):
    """A fenced block is left as it is (the translation's rules): a pattern there is quoted on purpose."""
    quoted = "Numbered as the Spanish ticket shows it:\n\n```\nOS-AAAAMMDD-NNNN\n```\n\n~~~~text\nDD/MM/AAAA\n~~~~"
    en = translated(USER_PART, body_with(quoted))
    [config] = installed(module(tmp_path, en=en))
    translator(allowed=False)

    call_command("translate_workbooks", "--check")

    en = translated(USER_PART, body_with(f"{quoted}\n\nBorn on dd/mm/aaaa."))
    Path(config.path, "WORKBOOK.en.md").write_text(en)
    with pytest.raises(CommandError) as raised:
        call_command("translate_workbooks", "--check")

    message = str(raised.value)
    assert f"things: WORKBOOK.en.md:{line_of(en, 'dd/mm/aaaa')}: dd/mm/aaaa" in message
    assert "OS-AAAAMMDD-NNNN" not in message and "DD/MM/AAAA" not in message


def test_check_reports_a_stale_translation_and_a_spanish_date_together(tmp_path, installed, translator):
    installed(
        module(tmp_path, "stale", en=translated("una versión anterior\n", ENGLISH)),
        module(tmp_path, en=translated(USER_PART, body_with("Born on DD/MM/AAAA."))),
    )
    translator(allowed=False)

    with pytest.raises(CommandError) as raised:
        call_command("translate_workbooks", "--check")

    message = str(raised.value)
    assert "Out of date WORKBOOK.en.md: stale." in message and "things: WORKBOOK.en.md:" in message


def test_a_stale_translation_is_told_to_be_made_again_its_dates_are_checked_once_current(tmp_path, installed, translator):
    installed(module(tmp_path, en=translated("una versión anterior\n", body_with("Born on DD/MM/AAAA."))))
    translator(allowed=False)

    with pytest.raises(CommandError) as raised:
        call_command("translate_workbooks", "--check")

    assert str(raised.value).startswith("Out of date WORKBOOK.en.md: things.")
    assert "DD/MM/AAAA" not in str(raised.value)


def test_check_of_one_app_looks_at_its_dates_only(tmp_path, installed, translator):
    installed(module(tmp_path, en=translated(USER_PART, body_with("Born on DD/MM/AAAA."))), module(tmp_path, "stock"))
    translator(allowed=False)

    call_command("translate_workbooks", "--check", "--app", "stock")


def test_check_reads_no_date_in_the_header_though_its_hash_spells_aaaa(tmp_path, installed, translator):
    """The header's sha256 is hex: about one in a thousand spells «aaaa», and that is no Spanish date."""
    workbook = WORKBOOK.replace("Guarda **cosas**.", "Guarda **cosas** (1028).")
    source = catalog.user_part(workbook)
    assert "aaaa" in source_hash(source)
    installed(module(tmp_path, workbook=workbook, en=translated(source, ENGLISH)))
    translator(allowed=False)

    call_command("translate_workbooks", "--check")


# ── every language of the Hub but the one the WORKBOOK is written in ─────────────────────────────


def test_a_language_added_to_the_hub_gets_its_translation_next_to_the_others(tmp_path, installed, translator, german):
    [config] = installed(module(tmp_path))
    fake = translator()

    call_command("translate_workbooks")

    assert fake.sources == [USER_PART, USER_PART]
    assert fake.languages == ["en", "de"]
    for language in ("en", "de"):
        assert file_in(config, language).read_text() == f"{en_header(source_hash(USER_PART))}\n\n{ENGLISH}"
        # What the help then serves in that language.
        assert workbook_help.workbook(Path(config.path), language) == (language, ENGLISH)
    call_command("translate_workbooks", "--check")


def test_only_the_language_that_is_not_current_is_translated(tmp_path, installed, translator, german, capsys):
    [config] = installed(module(tmp_path, en=translated(USER_PART, ENGLISH)))
    file_in(config, "de").write_text(translated("una versión anterior\n", ENGLISH))
    before = en_file(config).read_text()
    fake = translator(english=ENGLISH.replace("things", "Sachen"))

    call_command("translate_workbooks")

    assert fake.languages == ["de"]
    assert en_file(config).read_text() == before
    assert "Sachen" in file_in(config, "de").read_text()
    assert capsys.readouterr().out == "things: wrote WORKBOOK.de.md; review the diff before committing it.\n"


def test_an_app_is_told_up_to_date_once_when_it_is_in_every_language(tmp_path, installed, translator, german, capsys):
    [config] = installed(module(tmp_path, en=translated(USER_PART, ENGLISH)))
    file_in(config, "de").write_text(translated(USER_PART, ENGLISH))
    translator(allowed=False)

    call_command("translate_workbooks")

    assert capsys.readouterr().out == "things: up to date.\n"


def test_check_lists_the_stale_translations_of_each_language_with_its_file(tmp_path, installed, translator, german):
    things, stock = installed(
        module(tmp_path, "things", en=translated("una versión anterior\n", ENGLISH)),
        module(tmp_path, "stock", en=translated(USER_PART, ENGLISH)),
    )
    file_in(things, "de").write_text(translated(USER_PART, ENGLISH))
    file_in(stock, "de").write_text(translated("una versión anterior\n", ENGLISH))
    translator(allowed=False)

    with pytest.raises(CommandError) as raised:
        call_command("translate_workbooks", "--check")

    def by_hand(label: str, language: str) -> str:
        return (
            f"{label}: translate by hand the part of WORKBOOK.md that changed into WORKBOOK.{language}.md "
            f"and make its first line the header this prints: {HEADER_COMMAND.format(label)}"
        )

    assert str(raised.value).splitlines() == [
        "Out of date WORKBOOK.en.md: things.",
        by_hand("things", "en"),
        "Out of date WORKBOOK.de.md: stock.",
        by_hand("stock", "de"),
    ]


def test_check_names_the_files_of_every_language_when_they_are_current_or_missing(
    tmp_path, installed, translator, german, capsys
):
    current, _untranslated = installed(
        module(tmp_path, "current", en=translated(USER_PART, ENGLISH)), module(tmp_path, "untranslated")
    )
    file_in(current, "de").write_text(translated(USER_PART, ENGLISH))
    translator(allowed=False)

    call_command("translate_workbooks", "--check")

    assert capsys.readouterr().out == "Every WORKBOOK.en.md, WORKBOOK.de.md is up to date.\n"


def test_with_english_as_the_only_translation_the_check_names_only_its_file(tmp_path, installed, translator, settings, capsys):
    settings.LANGUAGES = [("en", "English"), ("es", "Español")]
    installed(module(tmp_path, en=translated(USER_PART, ENGLISH)))
    translator(allowed=False)

    call_command("translate_workbooks", "--check")

    assert capsys.readouterr().out == "Every WORKBOOK.en.md is up to date.\n"


def test_the_language_the_workbook_is_written_in_has_no_translation(tmp_path, installed, translator):
    """Spanish is read from WORKBOOK.md: a WORKBOOK.es.md is neither checked nor written."""
    [config] = installed(module(tmp_path, en=translated(USER_PART, ENGLISH)))
    file_in(config, "es").write_text("## Para qué sirve\n")
    translator(allowed=False)

    call_command("translate_workbooks", "--check")
    call_command("translate_workbooks")

    assert file_in(config, "es").read_text() == "## Para qué sirve\n"


def test_a_file_in_a_language_the_hub_does_not_offer_is_not_checked(tmp_path, installed, translator, settings):
    assert "de" not in dict(settings.LANGUAGES)
    [config] = installed(module(tmp_path, en=translated(USER_PART, ENGLISH)))
    file_in(config, "de").write_text(translated("una versión anterior\n", ENGLISH))
    translator(allowed=False)

    call_command("translate_workbooks", "--check")


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        (ENGLISH.replace("docs/img/list.png", "docs/img/lista.png"), "docs/img/list.png"),
        (ENGLISH.replace("(#how-to-use-it)", "(#cómo-se-usa)"), "#cómo-se-usa"),
    ],
    ids=["image", "anchor"],
)
def test_a_wrong_translation_into_an_added_language_is_not_written_and_names_its_file(
    tmp_path, installed, translator, german, answer, said
):
    [config] = installed(module(tmp_path, en=translated(USER_PART, ENGLISH)))
    translator(english=answer)

    with pytest.raises(CommandError, match=said) as raised:
        call_command("translate_workbooks")

    assert str(raised.value).startswith("things: WORKBOOK.de.md: ")
    assert not file_in(config, "de").exists()


# ── base: the platform's WORKBOOK is translated too, though it is no module of the store ─────────


def platform(root: Path, label: str = "base", **kwargs) -> SimpleNamespace:
    """A platform app of ours on disk (``base``): no module, never in the store's catalogue."""
    return module(root, label, kind="platform", **kwargs)


def test_check_covers_the_platforms_workbook_though_it_is_no_module(tmp_path, installed, translator):
    installed(
        module(tmp_path, "things", en=translated(USER_PART, ENGLISH)),
        platform(tmp_path, en=translated("una versión anterior\n", ENGLISH)),
    )
    translator(allowed=False)

    with pytest.raises(CommandError, match=r"Out of date WORKBOOK\.en\.md: base\.") as raised:
        call_command("translate_workbooks", "--check")

    assert "things" not in str(raised.value)


def test_a_changed_user_part_of_the_real_base_workbook_fails_the_check(tmp_path, installed, translator):
    """The positive the CI has to catch: base's own WORKBOOK with its user part edited and no new translation."""
    real = Path(django_apps.get_app_config("base").path)
    spanish = (real / "WORKBOOK.md").read_text(encoding="utf-8")
    [base] = installed(platform(tmp_path, workbook=spanish, en=(real / "WORKBOOK.en.md").read_text(encoding="utf-8")))
    translator(allowed=False)
    call_command("translate_workbooks", "--check")  # as committed: up to date

    edited = spanish.replace("\n## Flujos\n", "\n## Flujos\n\nUna frase nueva para quien usa el Hub.\n", 1)
    assert edited != spanish
    (Path(base.path) / "WORKBOOK.md").write_text(edited, encoding="utf-8")

    with pytest.raises(CommandError, match=r"Out of date WORKBOOK\.en\.md: base\.") as raised:
        call_command("translate_workbooks", "--check")

    assert HEADER_COMMAND.format("base") in str(raised.value)


def test_the_platforms_workbook_is_translated_when_asked_for(tmp_path, installed, translator):
    things, base = installed(module(tmp_path, "things"), platform(tmp_path))
    fake = translator()

    call_command("translate_workbooks", "--app", "base")

    assert fake.sources == [USER_PART]
    assert en_file(base).read_text().startswith(en_header(source_hash(USER_PART)))
    assert not en_file(things).exists()


def test_a_platform_app_without_workbook_is_no_app_to_translate_and_base_stays_out_of_the_store(tmp_path, installed, translator):
    things, base, control = installed(module(tmp_path, "things"), platform(tmp_path), platform(tmp_path, "control", workbook=None))
    translator(allowed=False)

    with pytest.raises(CommandError, match=r"No app 'control' with a WORKBOOK to translate; the apps are: base, things\."):
        call_command("translate_workbooks", "--app", "control")

    assert catalog.catalog_modules() == [things]


def test_check_fails_on_a_platform_workbook_it_cannot_read(tmp_path, installed, translator):
    """No registry reads base's WORKBOOK (it is no module): a broken user part must not pass the check in silence."""
    broken = WORKBOOK.replace("Ver [cómo se usa](#cómo-se-usa).", "Ver [cómo se usa](#no-existe).")
    assert broken != WORKBOOK
    installed(platform(tmp_path, workbook=broken, en=translated(USER_PART, ENGLISH)))
    translator(allowed=False)

    with pytest.raises(CommandError, match=r"Out of date WORKBOOK\.en\.md: base\."):
        call_command("translate_workbooks", "--check")
    with pytest.raises(CommandError, match="base: WORKBOOK.md: .*#no-existe"):
        call_command("translate_workbooks", "--app", "base")


# ── the key: ANTHROPIC_API_KEY, from the environment or the checkout's .env ────────────────────


@pytest.fixture
def key(monkeypatch, tmp_path):
    """Where ``translate`` looks for the key, this test's only: nowhere until ``environment`` or ``dotenv``."""
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(name, raising=False)
    # python-decouple's config, as config.settings loaded it: the checkout's .env stays out.
    monkeypatch.setattr(decouple.config, "config", Config(RepositoryEmpty()))

    def install(*, environment: str | None = None, dotenv: str | None = None) -> None:
        if environment is not None:
            monkeypatch.setenv("ANTHROPIC_API_KEY", environment)
        if dotenv is not None:
            path = tmp_path / ".env"
            path.write_text(dotenv, encoding="utf-8")
            monkeypatch.setattr(decouple.config, "config", Config(RepositoryEnv(str(path))))

    return install


@pytest.mark.parametrize(
    "dotenv",
    [None, "DEBUG=True\n", "ANTHROPIC_API_KEY=\n"],
    ids=["no-env-file", "env-file-without-it", "empty-in-env-file"],
)
def test_without_a_key_it_stops_before_the_api_naming_the_key_and_where_it_goes(tmp_path, installed, key, dotenv):
    [config] = installed(module(tmp_path))
    key(dotenv=dotenv)

    # The real translate and SDK client: the SDK's own TypeError never gets out.
    with pytest.raises(CommandError) as raised:
        call_command("translate_workbooks")

    message = str(raised.value)
    assert "ANTHROPIC_API_KEY" in message and ".env" in message and "--check" in message
    assert not en_file(config).exists()


def test_an_up_to_date_module_needs_no_key(tmp_path, installed, key):
    [config] = installed(module(tmp_path, en=translated(USER_PART, ENGLISH)))
    before = en_file(config).read_text()
    key()

    call_command("translate_workbooks")

    assert en_file(config).read_text() == before


def test_check_needs_no_key(tmp_path, installed, key):
    installed(
        module(tmp_path, "current", en=translated(USER_PART, ENGLISH)),
        module(tmp_path, "stale", en=translated("una versión anterior\n", ENGLISH)),
    )
    key()

    with pytest.raises(CommandError, match=r"stale") as raised:
        call_command("translate_workbooks", "--check")

    assert "ANTHROPIC_API_KEY" not in str(raised.value)


# ── translate: one call to the Claude API, with fixed instructions ────────────────────────────


class FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


@pytest.fixture
def fake_client(monkeypatch):
    def install(*, stop_reason="end_turn", text=ENGLISH, error: Exception | None = None):
        """The fake SDK; its ``clients`` are the client's arguments, its ``streams`` each request's."""
        fake = SimpleNamespace(clients=[], streams=[])

        class Messages:
            def stream(self, **kwargs):
                fake.streams.append(kwargs)
                if error is not None:
                    raise error
                content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)]
                return FakeStream(SimpleNamespace(stop_reason=stop_reason, content=content))

        def client(**kwargs):
            fake.clients.append(kwargs)
            return SimpleNamespace(messages=Messages())

        monkeypatch.setattr(anthropic, "Anthropic", client)
        return fake

    return install


def test_translate_sends_the_user_part_with_the_fixed_instructions_to_the_configured_model(fake_client, key, settings):
    settings.WORKBOOK_TRANSLATION_MODEL = "claude-test-model"
    key(environment="sk-ant-test-environment")
    fake = fake_client()

    assert translate_workbooks.translate(USER_PART, "en") == ENGLISH

    [call] = fake.streams
    assert call["model"] == "claude-test-model"
    assert call["system"] == translate_workbooks.instructions("en")
    assert call["messages"] == [{"role": "user", "content": USER_PART}]
    for rule in ("image paths", "code", "identifiers", "#", "from Spanish into English", "its English translation"):
        assert rule in call["system"]


def test_translate_asks_for_the_language_by_its_name_in_the_hub(fake_client, key, german):
    key(environment="sk-ant-test-environment")
    fake = fake_client()

    translate_workbooks.translate(USER_PART, german)

    [call] = fake.streams
    for asked in ("from Spanish into Deutsch", "its Deutsch translation", "as the Deutsch app shows them"):
        assert asked in call["system"]
    assert "English" not in call["system"] and "{" not in call["system"]


@pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal"])
def test_translate_never_returns_a_cut_or_refused_answer(fake_client, key, stop_reason):
    key(environment="sk-ant-test-environment")
    fake_client(stop_reason=stop_reason)
    with pytest.raises(CommandError, match=stop_reason):
        translate_workbooks.translate(USER_PART, "en")


def test_translate_reports_an_api_failure(fake_client, key):
    key(environment="sk-ant-test-environment")
    fake_client(error=anthropic.APIConnectionError(request=None))
    with pytest.raises(CommandError, match="Claude API"):
        translate_workbooks.translate(USER_PART, "en")


@pytest.mark.parametrize(
    ("sources", "expected"),
    [
        ({"dotenv": "DEBUG=True\nANTHROPIC_API_KEY=sk-ant-test-dotenv\n"}, "sk-ant-test-dotenv"),
        ({"environment": "sk-ant-test-environment"}, "sk-ant-test-environment"),
        (
            {"environment": "sk-ant-test-environment", "dotenv": "ANTHROPIC_API_KEY=sk-ant-test-dotenv\n"},
            "sk-ant-test-environment",
        ),
    ],
    ids=["env-file", "environment", "environment-wins"],
)
def test_the_key_reaches_the_client_from_the_environment_or_the_checkouts_env_file(fake_client, key, sources, expected):
    """The SDK reads only the environment: a key only in .env would never reach it (python-decouple exports nothing)."""
    key(**sources)
    fake = fake_client()

    translate_workbooks.translate(USER_PART, "en")

    assert fake.clients == [{"api_key": expected}]
