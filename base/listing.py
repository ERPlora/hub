"""Names said together as the screens say them: in the order the browser sorts them and joined as its
``Intl.ListFormat`` joins a list, so what the server writes reads the same as what a screen writes."""

import re
import unicodedata
from collections.abc import Iterable

from babel.lists import format_list

from base.business import babel_locale

#: Spanish joins with «e», not «y», before a word that starts with the sound /i/: «Clientes e Impuestos». CLDR's data
#: (Babel) only has «y»; this is the rule ICU applies on top of it, which ``Intl.ListFormat`` follows: «i…», «hi», or
#: «hi» before any letter but «a» and «e» («Hielo» keeps «y»).
_SPANISH_E = re.compile(r"(?i)i|hi$|hi[^ae]")


def joined(names: Iterable[str], language: str) -> str:
    """«A», «A and B», «A, B, and C» in ``language``, as the browser's ``Intl.ListFormat`` writes it."""
    names = list(names)
    if not names:
        return ""
    locale = babel_locale(language)
    said = format_list(names, locale=locale)
    if locale.language == "es" and len(names) > 1 and _SPANISH_E.match(names[-1]):
        head, _, _ = said.rpartition(f" y {names[-1]}")
        said = f"{head} e {names[-1]}"
    return said


def _sort_key(name: str) -> tuple[str, str]:
    """Letters before their accents, case aside, as the browser's ``localeCompare`` sorts them first."""
    plain = "".join(char for char in unicodedata.normalize("NFD", name) if not unicodedata.combining(char))
    return plain.casefold(), name


def ordered(names: Iterable[str]) -> list[str]:
    """``names`` in the order the browser's ``localeCompare`` gives them: «Catálogo» before «Catering»."""
    return sorted(names, key=_sort_key)
