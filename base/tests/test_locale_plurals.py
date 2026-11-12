"""No server text of the Hub spells a plural with «(s)» (hub#1147): a count says «1 cart» or «2 carts».

The SPA's catalogues have the same guard in ``base/frontend/__tests__/catalogue-plurals.test.ts``. A message with a
count goes through ``ngettext``/``npgettext`` with its ``msgid_plural`` (``control/admin.py``), never «cart(s)»: the
parentheses show on screen whatever the number. Read from the compiled catalogues Django uses (``.mo``): the English
message is the key and the Spanish its translation, so both languages are checked. The ``.mo`` drops the English
plural form, so it is read from the ``.po`` beside it; and since English has no catalogue, the screen says the forms
the code hands the plural family, read from the code as ``base/tests/test_locale_modules.py`` reads its messages
(hub#1294). The readers are the ones of every catalogue test, ``base.tests.po``.
"""

import re
from pathlib import Path

import pytest
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po
from django.apps import apps
from django.conf import settings

from base.tests.po import mo_entries, po_messages
from base.tests.test_locale_modules import gettext_calls, own_code

#: A plural ending glued to a word in parentheses: «record(s)», «opción(es)», «category(ies)» (as the SPA's guard).
IN_PARENTHESES = re.compile(r"[^\W\d_]\((?:s|es|as|os|ies)\)")

def hub_catalogues() -> list[Path]:
    """Every compiled Spanish catalogue of the Hub: the platform's (``control``, ``base``) and each app's."""
    root = Path(settings.BASE_DIR)
    return sorted(
        [
            *root.glob("control/locale/es/LC_MESSAGES/django.mo"),
            *root.glob("base/locale/es/LC_MESSAGES/django.mo"),
            *root.glob("apps/*/locale/es/LC_MESSAGES/django.mo"),
        ]
    )


def english_plurals(path: Path) -> list[str]:
    """The English plural form of each plural entry of the compiled catalogue ``path``, from the ``.po`` beside it: the
    ``.mo`` keys a plural by its singular and drops this form."""
    return [message.id[1] for message in po_messages(path.with_suffix(".po")) if message.pluralizable]


def messages_with_parentheses(path: Path) -> set[str]:
    """The English messages of ``path`` that spell a plural in parentheses, in English (either form) or in their
    Spanish."""
    found = set()
    for key, text in mo_entries(path).items():
        message = key if isinstance(key, str) else key[0]  # A plural form is keyed (message, index).
        message = message.split("\x04", 1)[-1]  # A contexted one is keyed «context\x04message».
        if IN_PARENTHESES.search(message) or IN_PARENTHESES.search(text):
            found.add(message)
    return found | {plural for plural in english_plurals(path) if IN_PARENTHESES.search(plural)}


#: Where the two English forms of each plural of the gettext family sit among its arguments: after a context or not.
PLURALS = {"ngettext": 0, "ngettext_lazy": 0, "npgettext": 1, "npgettext_lazy": 1}


def plurals_in(source: str) -> list[tuple[str, str]]:
    """Both English forms of each plural ``source`` hands the gettext family as written (literals, not variables)."""
    pairs = []
    for function, texts in gettext_calls(source):
        forms = texts[PLURALS[function] :][:2] if function in PLURALS else []
        if len(forms) == 2 and None not in forms:
            pairs.append((forms[0], forms[1]))
    return pairs


def code_plurals() -> dict[str, list[tuple[str, str]]]:
    """The plurals the server code of the Hub says, by module: the platform's (``control``, ``base``) and each app's."""
    root = Path(settings.BASE_DIR)
    return {
        config.label: [pair for path in own_code(config) for pair in plurals_in(path.read_text(encoding="utf-8"))]
        for config in apps.get_app_configs()
        if Path(config.path) in (root / "control", root / "base") or Path(config.path).parent == root / "apps"
    }


def test_the_catalogues_read_are_the_platforms_and_every_apps():
    read = {path.relative_to(settings.BASE_DIR).parts[:2] for path in hub_catalogues()}
    assert {("control", "locale"), ("base", "locale"), ("apps", "service"), ("apps", "cart_checkout")} <= read
    assert len(read) > 20


def test_no_catalogue_says_a_count_with_parentheses():
    # VeriFactu's messages of the server were the last ones, left out of hub#1147 as fiscal zone (hub#1275).
    found = {
        f"{path.relative_to(settings.BASE_DIR).parts[1]}: {message}"
        for path in hub_catalogues()
        for message in messages_with_parentheses(path)
    }
    assert found == set()


def test_the_check_catches_a_plural_in_parentheses_in_either_language():
    assert IN_PARENTHESES.search("1 record(s)") and IN_PARENTHESES.search("1 opción(es)")
    assert IN_PARENTHESES.search("2 category(ies)")
    assert not IN_PARENTHESES.search("Price (€)") and not IN_PARENTHESES.search("Slug (optional)")
    assert not IN_PARENTHESES.search("Send the order (3)")


SPANISH_HEADER = 'msgid ""\nmsgstr ""\n"Language: es\\n"\n"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n'


def compiled(tmp_path: Path, entries: str) -> Path:
    """A Spanish ``django.po`` with ``entries`` and its ``django.mo`` beside it, as ``compilemessages`` leaves them."""
    po = tmp_path / "django.po"
    po.write_text(SPANISH_HEADER + entries, encoding="utf-8")
    with po.open(encoding="utf-8") as source, (tmp_path / "django.mo").open("wb") as mo:
        write_mo(mo, read_po(source))
    return tmp_path / "django.mo"


def test_the_check_reads_the_english_plural_the_catalogue_keeps(tmp_path):
    """The ``.mo`` keys a plural by its singular and drops its English plural: that form is read from the ``.po``
    beside it (hub#1294), and the singular and the Spanish forms are still seen."""
    mo = compiled(
        tmp_path,
        '\nmsgid "%(count)s chain goes out."\nmsgid_plural "%(count)s chain(s) go out."\n'
        'msgstr[0] "%(count)s cadena sale."\nmsgstr[1] "%(count)s cadenas salen."\n'
        '\nmsgid "%(count)s record(s) left."\nmsgid_plural "%(count)s records left."\n'
        'msgstr[0] "Queda %(count)s registro."\nmsgstr[1] "Quedan %(count)s registros."\n'
        '\nmsgid "%(count)s cart."\nmsgid_plural "%(count)s carts."\n'
        'msgstr[0] "%(count)s carrito."\nmsgstr[1] "%(count)s carrito(s)."\n'
        '\nmsgid "%(count)s order."\nmsgid_plural "%(count)s orders."\n'
        'msgstr[0] "%(count)s pedido."\nmsgstr[1] "%(count)s pedidos."\n',
    )
    assert messages_with_parentheses(mo) == {
        "%(count)s chain(s) go out.",  # its English plural, which the .mo drops
        "%(count)s record(s) left.",  # its English singular
        "%(count)s cart.",  # its Spanish plural
    }


def test_the_english_plurals_of_every_catalogue_are_read():
    """Positive control: the plurals of the platform's catalogues and of the apps' are found beside their ``.mo``."""
    read = {path.parents[3].name: english_plurals(path) for path in hub_catalogues()}  # <module>/locale/es/LC_MESSAGES
    assert {"control", "base", "verifactu", "cart_checkout"} <= {module for module, plurals in read.items() if plurals}
    assert sum(len(plurals) for plurals in read.values()) > 20


PLURAL_SOURCE = """
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext, npgettext, npgettext_lazy
from django.utils.translation import ngettext_lazy as plural

ONE = ngettext("%(count)s cart", "%(count)s carts", 2)
LAZY = plural("%(count)s chain goes out", "%(count)s chains go out", "count")
SAID = npgettext("cash", "%(count)s till", "%(count)s tills", 3)
LATER = npgettext_lazy("table", "%(count)s seat", "%(count)s seats", "count")
CALLED = translation.ngettext("%(count)s hub", "%(count)s hubs", 4)
NAMED = ngettext(SINGULAR, "%(count)s things", 2)
SINGLE = _("one record")
"""


def test_the_codes_plurals_are_read_in_english():
    """Both English forms of each plural the code says as written, under any name it imports the family or on
    ``translation``; one with a variable form, or no plural, is not read."""
    assert plurals_in(PLURAL_SOURCE) == [
        ("%(count)s cart", "%(count)s carts"),
        ("%(count)s chain goes out", "%(count)s chains go out"),
        ("%(count)s till", "%(count)s tills"),
        ("%(count)s seat", "%(count)s seats"),
        ("%(count)s hub", "%(count)s hubs"),
    ]


@pytest.mark.parametrize(
    "pair",
    [
        ("%(count)s chain goes out", "%(count)s chain(s) go out"),
        ("%(count)s chain(s) goes out", "%(count)s chains go out"),
    ],
    ids=["plural", "singular"],
)
def test_the_check_catches_a_count_with_parentheses_in_either_english_form_of_the_code(pair, monkeypatch):
    """A plural of VeriFactu's code with «(s)» in its English plural, or in its singular, turns the guard red."""
    said = code_plurals()
    monkeypatch.setitem(globals(), "code_plurals", lambda: said | {"verifactu": [*said["verifactu"], pair]})
    with pytest.raises(AssertionError, match=re.escape("verifactu: %(count)s chain(s)")):
        test_no_code_says_a_count_with_parentheses()


def test_the_server_code_of_the_platform_and_the_apps_is_read():
    """Positive control: the plurals of ``control``, ``base`` and the apps' code are found, VeriFactu's among them."""
    said = code_plurals()
    assert {"control", "base", "verifactu", "cart_checkout"} <= {label for label, pairs in said.items() if pairs}
    assert sum(len(pairs) for pairs in said.values()) > 20


def test_no_code_says_a_count_with_parentheses():
    """In English there is no catalogue: the screen says the forms the code hands ``ngettext``, whatever the ``.po``
    keeps (hub#1294)."""
    found = {
        f"{label}: {form}"
        for label, pairs in code_plurals().items()
        for singular, plural in pairs
        for form in (singular, plural)
        if IN_PARENTHESES.search(form)
    }
    assert found == set()
