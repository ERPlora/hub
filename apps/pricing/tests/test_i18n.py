"""Every visible text of the pricing app has its Spanish translation, compiled and current."""

import gettext
import re
from pathlib import Path

from django.apps import apps
from django.utils import translation
from django.utils.functional import Promise
from live.operations import registry

from apps.pricing import queries, schemas, services
from apps.pricing.models import DiscountRule, PriceItem, PriceList

LOCALE = Path(apps.get_app_config("pricing").path) / "locale" / "es" / "LC_MESSAGES"
MODELS = (PriceList, PriceItem, DiscountRule)
_STRING = re.compile(r'^"(.*)"$')
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t"}


def _unescape(text: str) -> str:
    return _ESCAPE.sub(lambda match: _ESCAPES.get(match.group(1), match.group(1)), text)


def po_entries(path: Path) -> dict[str, tuple[str, bool]]:
    """``msgid → (msgstr, fuzzy)`` of a .po file without plurals (the header is skipped); an entry with a context
    (``pgettext``) is keyed as gettext compiles it, ``<context>\x04<msgid>``."""
    entries: dict[str, tuple[str, bool]] = {}
    parts: dict[str, list[str]] = {"msgctxt": [], "msgid": [], "msgstr": []}
    fuzzy, current = False, None

    def flush():
        msgid = _unescape("".join(parts["msgid"]))
        if msgid:
            context = _unescape("".join(parts["msgctxt"]))
            entries[f"{context}\x04{msgid}" if context else msgid] = (_unescape("".join(parts["msgstr"])), fuzzy)

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        starts = line.startswith("msgctxt ") or (line.startswith("msgid ") and current != "msgctxt")
        if starts or (line.startswith("#") and current == "msgstr"):
            flush()
            parts, fuzzy, current = {"msgctxt": [], "msgid": [], "msgstr": []}, fuzzy and current is None, None
        if line.startswith("#,") and "fuzzy" in line:
            fuzzy = True
        elif line.startswith(("msgctxt ", "msgid ", "msgstr ")):
            current, _, rest = line.partition(" ")
            parts[current].append(_STRING.match(rest).group(1))
        elif current and _STRING.match(line):
            parts[current].append(_STRING.match(line).group(1))
    flush()
    return entries


def module_texts(module) -> list[Promise]:
    """The lazy texts a module declares at its top (error and validation messages)."""
    return [value for value in vars(module).values() if isinstance(value, Promise)]


def visible_texts() -> set[str]:
    """The English source of every lazy text the app shows (menu, store, admin, choices, messages) and the titles of
    its schemas."""
    config = apps.get_app_config("pricing")
    lazies = [
        config.verbose_name,
        config.summary,
        config.description,
        *(nav.label for nav in config.navigation),
        *module_texts(queries),
        *module_texts(services),
        *module_texts(schemas),
    ]
    for model in MODELS:
        lazies += [model._meta.verbose_name, model._meta.verbose_name_plural]
        lazies += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name") and not field.auto_created and not field.primary_key
        ]
    for choices in (DiscountRule.Type, DiscountRule.Scope):
        lazies += list(choices.labels)
    with translation.override("en"):
        return {str(text) for text in lazies} | schema_titles()


def schema_titles() -> set[str]:
    """The titles pricing's operations give their input data (``gettext_noop``): the assistant's card names each datum
    by them, so each one needs its Spanish. Only the ones pricing wrote: pydantic leaves ``title`` empty otherwise."""
    return {
        field.title
        for op in registry.values()
        if op.app_label == "pricing"
        for field in op.input.model_fields.values()
        if field.title
    }


def test_every_entry_has_a_spanish_translation():
    entries = po_entries(LOCALE / "django.po")
    assert entries
    untranslated = [msgid for msgid, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy]
    assert untranslated == []


def test_every_visible_text_is_in_the_catalog():
    assert len(visible_texts()) > 60  # positive control: the collection found the app's texts
    # A text with a context (``pgettext_lazy``) is said by its source alone, as the catalog keeps it after its context.
    assert visible_texts() - {msgid.rpartition("\x04")[2] for msgid in po_entries(LOCALE / "django.po")} == set()


def test_the_compiled_catalog_is_current():
    with (LOCALE / "django.mo").open("rb") as compiled:
        catalog = gettext.GNUTranslations(compiled)._catalog
    po = {msgid: msgstr for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items()}
    assert {msgid: msgstr for msgid, msgstr in catalog.items() if msgid} == po


def test_spanish_texts_are_the_old_modules():
    with translation.override("es"):
        config = apps.get_app_config("pricing")
        assert str(config.verbose_name) == "Tarifas"
        assert [str(nav.label) for nav in config.navigation] == ["Tarifas"]
        assert [str(label) for label in DiscountRule.Type.labels] == [
            "Porcentaje",
            "Importe por unidad",
            "Compra X, llévate Y",
            "Por tramos",
        ]
        assert str(services.DUPLICATE_LIST_CODE) == "Ya existe una tarifa con ese código. Elige otro."
        assert str(services.LIST_NOT_FOR_PRICES) == (
            "Esa tarifa no está disponible: no existe en este negocio o está desactivada."
        )


def test_placeholders_survive_the_translation():
    for msgid, (msgstr, _) in po_entries(LOCALE / "django.po").items():
        assert sorted(re.findall(r"%\(\w+\)s", msgid)) == sorted(re.findall(r"%\(\w+\)s", msgstr)), msgid
