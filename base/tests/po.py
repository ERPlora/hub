"""The one reader of ``.po`` catalogues in the Hub's tests: every app's ``test_i18n.py`` asks it what its catalogue says.

The parsing is Babel's, a dependency already; this only gives its messages the keys of the compiled catalogue, which is
what those tests compare them with. Its behaviour is tested in ``base/tests/test_po.py``.
"""

import ast
import gettext
import inspect
from collections.abc import Iterable
from pathlib import Path

from babel.messages.catalog import Message
from babel.messages.pofile import read_po
from django.utils.functional import Promise
from live.operations import registry


def po_messages(path: Path, *, strict: bool = True) -> list[Message]:
    """The live messages of a ``.po``, without its header and its obsolete (``#~``) entries. A plural message has a tuple
    for ``id`` and ``string``. What gettext would not understand raises ``PoFileError``, so a guard never passes on a
    catalogue it did not read; ``strict=False`` is for a catalogue that is not ours (Babel warns and goes on)."""
    with path.open(encoding="utf-8") as catalog:
        return [message for message in read_po(catalog, abort_invalid=strict) if message.id]


def po_entries(path: Path) -> dict[str | tuple[str, int], tuple[str, bool]]:
    """``key → (msgstr, fuzzy)`` of a ``.po``, keyed as the compiled catalogue keys it: the msgid, ``context\\x04msgid``
    for an entry with a ``msgctxt``, and ``(key, n)`` for each form of a plural entry."""
    entries: dict[str | tuple[str, int], tuple[str, bool]] = {}
    for message in po_messages(path):
        msgid = message.id[0] if message.pluralizable else message.id
        key = f"{message.context}\x04{msgid}" if message.context else msgid
        if message.pluralizable:
            entries |= {(key, n): (text, message.fuzzy) for n, text in enumerate(message.string)}
        else:
            entries[key] = (message.string, message.fuzzy)
    return entries


def untranslated(po: Path) -> list[str | tuple[str, int]]:
    """The keys of ``po`` gettext shows in English: no ``msgstr``, or a ``#, fuzzy`` one it skips. A catalogue without
    entries fails, since there would be nothing to check."""
    entries = po_entries(po)
    if not entries:
        raise AssertionError(f"{po} has no entries")
    return [key for key, (msgstr, fuzzy) in entries.items() if not msgstr or fuzzy]


def mo_entries(path: Path) -> dict[str | tuple[str, int], str]:
    """``key → text`` of a compiled catalogue, as Django reads it (the same keys as ``po_entries``), its header left
    out."""
    with path.open("rb") as compiled:
        return {key: text for key, text in gettext.GNUTranslations(compiled)._catalog.items() if key}


def compiled_differences(locale: Path) -> dict:
    """What ``django.mo`` in ``locale`` says differently from its ``django.po``, as ``key → (po, mo)`` (``None`` where
    one lacks the entry): a catalogue edited and not compiled again shows its old Spanish."""
    mo = mo_entries(locale / "django.mo")
    po = {key: msgstr for key, (msgstr, _fuzzy) in po_entries(locale / "django.po").items()}
    return {key: (po.get(key), mo.get(key)) for key in po.keys() | mo.keys() if po.get(key) != mo.get(key)}


def config_texts(config) -> list:
    """What the store and the menu say of an app: its name, summary and description, and the label of each entry of
    its menu."""
    return [config.verbose_name, config.summary, config.description, *(nav.label for nav in config.navigation)]


def module_texts(*modules) -> list:
    """The lazy texts each module keeps at its top, alone, in a tuple or as the values of a dict (a pair of a code and
    its message too): its messages, its labels and its headers. What it imports is another module's, and its own test
    checks it."""
    texts = []
    for module in modules:
        imported = {
            (alias.asname or alias.name).split(".")[0]
            for node in ast.parse(inspect.getsource(module)).body
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        for name, value in vars(module).items():
            if name in imported:
                continue
            items = value.values() if isinstance(value, dict) else value if isinstance(value, tuple) else (value,)
            for item in items:
                texts += [leaf for leaf in (item if isinstance(item, tuple) else (item,)) if isinstance(leaf, Promise)]
    return texts


def operation_titles(label: str) -> set[str]:
    """The titles the operations of app ``label`` give their input data (``gettext_noop``), and the data of the answer a
    write's preview shows (BASE-F98): the assistant's card names each datum by them, so each one needs its Spanish.
    Only the ones the app wrote: pydantic leaves ``title`` empty otherwise."""
    titles = set()
    for op in registry.values():
        if op.app_label != label:
            continue
        fields = list(op.input.model_fields.values())
        preview = op.ai.get("preview") if isinstance(op.ai, dict) else None
        if preview:
            answer = registry[preview["operation"]].output.model_fields
            fields += [answer[name] for name in preview["fields"]]
        titles |= {field.title for field in fields if field.title}
    return titles


def model_texts(models: Iterable) -> list:
    """The names each model shows (singular and plural) and those of the fields it declares: what the admin and the
    assistant's card say. The primary key and the relations Django adds on its own are not among them."""
    texts = []
    for model in models:
        texts += [model._meta.verbose_name, model._meta.verbose_name_plural]
        texts += [
            field.verbose_name
            for field in model._meta.get_fields()
            if hasattr(field, "verbose_name") and not field.auto_created and not field.primary_key
        ]
    return texts


def catalogue_key(text) -> str | tuple[str, int]:
    """How the compiled catalogue keys a lazy text (read in the source language, as the apps' tests read it): its
    English, or ``context\\x04English`` for a ``pgettext_lazy`` — so a text that goes back to ``_()`` while its entry
    keeps the context, or whose context has a typo, is missing from its catalogue: it would say another app's
    Spanish. A lazy plural (``ngettext_lazy``/``npgettext_lazy``) is keyed by its first form, ``(key, 0)``: read with
    ``str()``, one whose number comes from the formatting dict is empty."""
    plural = getattr(text, "_kw", {})
    if "plural" in plural:
        singular = plural["singular"]
        return (f"{plural['context']}\x04{singular}" if "context" in plural else singular, 0)
    args = getattr(text, "_args", ())
    return f"{args[0]}\x04{args[1]}" if len(args) == 2 else str(text)


def missing_from_catalogue(texts: set[str], po: Path, *, more_than: int, with_context: int) -> set[str]:
    """The keys of ``texts`` (each ``catalogue_key``) that the catalogue ``po`` lacks: what the business would read in
    English, or in another app's words. First the positive control: the collection found the app's texts (more than
    ``more_than``) and kept the context of its ``pgettext_lazy`` ones (at least ``with_context``), since one read with
    ``str()`` loses its context and the comparison would pass blind (hub#975)."""
    contexts = sum("\x04" in key for key in texts)
    if len(texts) <= more_than or contexts < with_context:
        raise AssertionError(
            f"the collection found {len(texts)} texts, {contexts} with a context: "
            f"expected more than {more_than}, and at least {with_context} with a context"
        )
    return texts - set(po_entries(po))
