"""translate_workbooks: each module's WORKBOOK.en.md, generated from its Spanish user part (spec §4.5).

The hash is the user part's, not the file's: touching «Para quien lo mantiene» costs nothing. With
the hash in the header unchanged, no call; otherwise one call and the header with the new hash.
``--check`` never reaches the network. The API is always a double here: ``translate`` (one call to
the Claude API) is replaced, and its own test fakes the SDK client.
"""

from pathlib import Path
from types import SimpleNamespace

import anthropic
import pytest
from django.core.management import CommandError, call_command

from base import catalog
from base.catalog import en_header, source_hash
from base.management.commands import translate_workbooks
from base.tests.test_catalog import USER_PART, WORKBOOK, module, translated

ENGLISH = "## What it is for\n\nKeeps **things**. See [how to use it](#how-to-use-it).\n\n![List of things](docs/img/list.png)\n\n## How to use it\n\n### Step by step\nStatus: done\n"


class FakeTranslator:
    """Stands in for ``translate``: records each source and answers ``english``, or fails if called."""

    def __init__(self, english: str = ENGLISH, *, allowed: bool = True):
        self.english, self.allowed, self.sources = english, allowed, []

    def __call__(self, source: str) -> str:
        if not self.allowed:
            raise AssertionError("translate_workbooks reached the API")
        self.sources.append(source)
        return self.english


@pytest.fixture
def installed(monkeypatch):
    """Make ``configs`` the installed modules."""

    def install(*configs):
        monkeypatch.setattr(catalog, "module_configs", lambda: list(configs))
        return configs

    return install


@pytest.fixture
def translator(monkeypatch):
    def install(**kwargs) -> FakeTranslator:
        fake = FakeTranslator(**kwargs)
        monkeypatch.setattr(translate_workbooks, "translate", fake)
        return fake

    return install


def en_file(config) -> Path:
    return Path(config.path) / "WORKBOOK.en.md"


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


def test_the_real_modules_are_up_to_date(translator):
    translator(allowed=False)
    call_command("translate_workbooks", "--check")


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
        calls = []

        class Messages:
            def stream(self, **kwargs):
                calls.append(kwargs)
                if error is not None:
                    raise error
                content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)]
                return FakeStream(SimpleNamespace(stop_reason=stop_reason, content=content))

        monkeypatch.setattr(anthropic, "Anthropic", lambda: SimpleNamespace(messages=Messages()))
        return calls

    return install


def test_translate_sends_the_user_part_with_the_fixed_instructions_to_the_configured_model(fake_client, settings):
    settings.WORKBOOK_TRANSLATION_MODEL = "claude-test-model"
    calls = fake_client()

    assert translate_workbooks.translate(USER_PART) == ENGLISH

    [call] = calls
    assert call["model"] == "claude-test-model"
    assert call["system"] == translate_workbooks.INSTRUCTIONS
    assert call["messages"] == [{"role": "user", "content": USER_PART}]
    for rule in ("image paths", "code", "identifiers", "#"):
        assert rule in translate_workbooks.INSTRUCTIONS


@pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal"])
def test_translate_never_returns_a_cut_or_refused_answer(fake_client, stop_reason):
    fake_client(stop_reason=stop_reason)
    with pytest.raises(CommandError, match=stop_reason):
        translate_workbooks.translate(USER_PART)


def test_translate_reports_an_api_failure(fake_client):
    fake_client(error=anthropic.APIConnectionError(request=None))
    with pytest.raises(CommandError, match="Claude API"):
        translate_workbooks.translate(USER_PART)
