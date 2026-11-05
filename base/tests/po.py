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
