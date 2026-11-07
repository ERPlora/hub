"""The one reader of ``.po`` catalogues in the Hub's tests: every app's ``test_i18n.py`` asks it what its catalogue says.

The parsing is Babel's, a dependency already; this only gives its messages the keys of the compiled catalogue, which is
what those tests compare them with. Its behaviour is tested in ``base/tests/test_po.py``.
"""

from pathlib import Path

from babel.messages.catalog import Message
from babel.messages.pofile import read_po


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


def catalogue_key(text) -> str:
    """How the compiled catalogue keys a lazy text (read in the source language, as the apps' tests read it): its
    English, or ``context\\x04English`` for a ``pgettext_lazy`` — so a text that goes back to ``_()`` while its entry
    keeps the context, or whose context has a typo, is missing from its catalogue: it would say another app's
    Spanish."""
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
