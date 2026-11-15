"""No server text of the Hub spells a plural with «(s)» (hub#1147): a count says «1 cart» or «2 carts».

The SPA's catalogues have the same guard in ``base/frontend/__tests__/catalogue-plurals.test.ts``. A message with a
count goes through ``ngettext``/``npgettext`` with its ``msgid_plural`` (``control/admin.py``), never «cart(s)»: the
parentheses show on screen whatever the number. Read from the compiled catalogues Django uses (``.mo``): the English
message is the key and the Spanish its translation, so both languages are checked. The ``.mo`` drops the English
plural form, so it is read from the ``.po`` beside it; and since English has no catalogue, the screen says the forms
the code hands the plural family, read from the code as ``base/tests/test_locale_modules.py`` reads its messages
(hub#1294), and the two forms of each ``{% blocktranslate count %}`` of its templates, read with Django's own template
parser. A text with no count is read there too, before ``makemessages`` takes it to the ``.po`` (hub#1333): the
messages the code hands ``gettext``/``pgettext`` (``said_in_code``, as ``test_locale_modules.py`` reads them), each
``{% translate %}`` and ``{% blocktranslate %}`` with no count of the templates, and each ``_("…")`` a template says
between braces or as the argument of a tag or a filter, read as ``makemessages`` reads it (hub#1353). The server is
the platform's (``control``, ``base``), each app's and ``live``'s, whose validation messages every form of the Hub
shares (hub#1318). The readers are the ones of every catalogue test, ``base.tests.po``.
"""

import re
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from babel.messages.extract import extract_python
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po
from django.apps import AppConfig, apps
from django.conf import settings
from django.template import Engine
from django.templatetags.i18n import BlockTranslateNode, TranslateNode
from django.utils.translation.template import templatize

from base.tests.po import mo_entries, po_messages
from base.tests.test_locale_modules import gettext_calls, own_code, said_in_code

#: A plural ending glued to a word in parentheses: «record(s)», «opción(es)», «category(ies)» (as the SPA's guard).
IN_PARENTHESES = re.compile(r"[^\W\d_]\((?:s|es|as|os|ies)\)")

def hub_catalogues() -> list[Path]:
    """Every compiled Spanish catalogue of the Hub: the platform's (``control``, ``base``), ``live``'s and each
    app's."""
    root = Path(settings.BASE_DIR)
    return sorted(
        [
            *root.glob("control/locale/es/LC_MESSAGES/django.mo"),
            *root.glob("base/locale/es/LC_MESSAGES/django.mo"),
            *root.glob("packages/live/live/locale/es/LC_MESSAGES/django.mo"),
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


def template_plurals_in(source: str) -> list[tuple[str, str]]:
    """Both English forms of each ``{% blocktranslate count %}`` of the template ``source``, its text and its
    ``{% plural %}``, as ``makemessages`` keeps them (a variable as ``%(name)s``)."""
    nodes = Engine.get_default().from_string(source).nodelist.get_nodes_by_type(BlockTranslateNode)
    counted = [node for node in nodes if node.plural]
    return [(node.render_token_list(node.singular)[0], node.render_token_list(node.plural)[0]) for node in counted]


def template_messages_in(source: str) -> list[str]:
    """The English text of each ``{% translate %}`` of the template ``source`` with a literal message and of each
    ``{% blocktranslate %}`` with no count, in its order, as ``makemessages`` keeps them (a variable as
    ``%(name)s``)."""
    nodes = Engine.get_default().from_string(source).nodelist.get_nodes_by_type((TranslateNode, BlockTranslateNode))
    said = []
    for node in nodes:
        if isinstance(node, BlockTranslateNode):
            if not node.plural:  # one with a count is template_plurals_in's
                said.append(node.render_token_list(node.singular)[0])
        elif node.filter_expression.var.literal is not None:  # a message that is a variable is no text written here
            said.append(node.filter_expression.var.literal)
    return said


def template_underscored_in(source: str) -> list[str]:
    """The English text of each ``_("…")`` the template ``source`` says between braces or as the argument of a tag or
    a filter, in its order, read as ``makemessages`` reads it: Django's ``templatize`` turns it into a call, and Babel's
    extractor reads that call as xgettext does."""
    # Babel tokenizes as Python and trips on the template's indentation, which xgettext ignores; no call that templatize
    # writes spans two lines, since Django reads a tag within one.
    written = "\n".join(line.lstrip() for line in templatize(source).splitlines())
    calls = extract_python(BytesIO(written.encode()), {"_": None}, [], {})
    return [message for _line, _function, message, _comments in calls]


def own_templates(config) -> list[Path]:
    """The templates of the module ``config``: the files of its ``templates/``, where Django loads them from."""
    return sorted(path for path in Path(config.path, "templates").rglob("*") if path.is_file())


def server_modules() -> list[AppConfig]:
    """The modules of the Hub's server: the platform's (``control``, ``base``), ``live`` and each app."""
    root = Path(settings.BASE_DIR)
    return [
        config
        for config in apps.get_app_configs()
        if config.label == "live"
        or Path(config.path) in (root / "control", root / "base")
        or Path(config.path).parent == root / "apps"
    ]


def code_plurals() -> dict[str, list[tuple[str, str]]]:
    """The plurals the server of the Hub says, by module: in its Python code and in its templates."""
    return {
        config.label: [
            *(pair for path in own_code(config) for pair in plurals_in(path.read_text(encoding="utf-8"))),
            *(pair for path in own_templates(config) for pair in template_plurals_in(path.read_text(encoding="utf-8"))),
        ]
        for config in server_modules()
    }


def code_messages() -> dict[str, list[str]]:
    """The texts with no count the server of the Hub says, by module: the messages of its Python code (as
    ``base/tests/test_locale_modules.py`` reads them; a contexted one without its context, which the screen does not
    show) and those of its templates, said by a tag or as a ``_("…")``."""
    return {
        config.label: [
            *sorted(message.rpartition("\x04")[2] for message in said_in_code(config)),
            *(
                text
                for path in own_templates(config)
                for source in [path.read_text(encoding="utf-8")]
                for text in [*template_messages_in(source), *template_underscored_in(source)]
            ),
        ]
        for config in server_modules()
    }


def test_the_catalogues_read_are_the_platforms_and_every_apps():
    read = {path.relative_to(settings.BASE_DIR).parts[:2] for path in hub_catalogues()}
    assert {("control", "locale"), ("base", "locale"), ("packages", "live")} <= read
    assert {("apps", "service"), ("apps", "cart_checkout")} <= read
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
    found = {module for module, plurals in read.items() if plurals}
    assert {"control", "base", "live", "verifactu", "cart_checkout"} <= found
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
    """Positive control: the plurals of ``control``, ``base``, ``live`` and the apps' code are found, VeriFactu's among
    them, and ``live``'s validation messages every form shares (hub#1318)."""
    said = code_plurals()
    found = {label for label, pairs in said.items() if pairs}
    assert {"control", "base", "live", "verifactu", "cart_checkout"} <= found
    assert sum(len(pairs) for pairs in said.values()) > 20


TEMPLATE_SOURCE = """{% extends "base.html" %}{% load i18n %}
{% block body %}
  {% blocktranslate count minutes=minutes trimmed %}
    Try again in {{ minutes }} minute.
  {% plural %}
    Try again in {{ minutes }} minutes.
  {% endblocktranslate %}
  {% if carts %}
    {% blocktrans count counter=carts|length %}{{ counter }} cart{% plural %}{{ counter }} carts{% endblocktrans %}
    {% trans "Clear the cart." context "cart" as cleared %}
  {% endif %}
  {% for till in tills %}
    {% blocktranslate context "cash" count n=till.count %}{{ n }} till{% plural %}{{ n }} tills{% endblocktranslate %}
    {% blocktrans with name=till.name trimmed %}
      Close {{ name }}
    {% endblocktrans %}
  {% endfor %}
  {% blocktranslate %}Hello {{ name }}{% endblocktranslate %}
  {% translate "one record" %}
  {% translate title %}
{% endblock %}
"""


def test_the_templates_plurals_are_read_in_english():
    """Both English forms of each ``{% blocktranslate count %}`` of a template, as ``makemessages`` keeps them (a
    variable as ``%(name)s``), under either tag name, with a context or inside a block, an ``if`` or a ``for``; a text
    with no ``{% plural %}`` is not read."""
    assert template_plurals_in(TEMPLATE_SOURCE) == [
        ("Try again in %(minutes)s minute.", "Try again in %(minutes)s minutes."),
        ("%(counter)s cart", "%(counter)s carts"),
        ("%(n)s till", "%(n)s tills"),
    ]


#: A ``{% plural %}`` tag of a template, as Django's lexer reads it.
PLURAL_TAG = re.compile(r"\{%\s*plural\s*%\}")


def test_every_plural_of_the_server_templates_is_read():
    """Positive control: each ``{% plural %}`` of the templates of the platform, ``live`` and the apps gives its pair to
    the guard, ``base``'s «too many attempts» page among them (hub#1318)."""
    said = code_plurals()
    tags, read = {}, {}
    for config in server_modules():
        texts = [path.read_text(encoding="utf-8") for path in own_templates(config)]
        tags[config.label] = sum(len(PLURAL_TAG.findall(text)) for text in texts)
        read[config.label] = [pair for text in texts for pair in template_plurals_in(text)]
    assert {label: len(pairs) for label, pairs in read.items()} == tags
    assert tags["base"] >= 1
    assert all(pair in said[label] for label, pairs in read.items() for pair in pairs)


def test_the_templates_texts_without_a_count_are_read_in_english():
    """The English text of each ``{% translate %}`` of a template with a literal message and of each
    ``{% blocktranslate %}`` with no count, in the template's order, as ``makemessages`` keeps them (a variable as
    ``%(name)s``), under either tag name, with a context, kept ``as`` a variable or inside a block, an ``if`` or a
    ``for``; a message that is a variable, or a text with a ``{% plural %}``, is not read here."""
    said = template_messages_in(TEMPLATE_SOURCE)
    assert said == ["Clear the cart.", "Close %(name)s", "Hello %(name)s", "one record"]


UNDERSCORE_SOURCE = """{% load i18n %}
<p>{{ _("Clear the field(s).") }}</p>
{% if answer %}
    <p>{{ answer|yesno:_("yes,no,maybe") }}</p>
  {% firstof nickname _('Nobody — yet') %}
{% endif %}
{% include "base/gate.html" with title=_("Signed out") only %}
{% blocktranslate with name=_("guest") %}Hello {{ name }}{% endblocktranslate %}
{{ title|default:_("Untitled")|upper }}
<p>Write _("Hello") between braces to translate it.</p>
{# Translators: no message, _("a comment") #}
{% translate heading %}
"""


def test_the_templates_texts_said_with_an_underscore_are_read_in_english():
    """Each ``_("…")`` of a template as ``makemessages`` reads it, in the template's order: between braces, as the
    argument of a filter or of a tag, in either quotes and however indented; a tag's own text is the tags' reader's,
    and the page's text and a translator's comment say none."""
    assert template_underscored_in(UNDERSCORE_SOURCE) == [
        "Clear the field(s).",
        "yes,no,maybe",
        "Nobody — yet",
        "Signed out",
        "guest",
        "Untitled",
    ]


#: A tag of a template that says a text with no count, as Django's lexer reads it: a ``{% translate %}`` of a literal
#: message, or a ``{% blocktranslate %}`` with no ``count``.
TEXT_TAG = re.compile(
    r"\{%\s*(?:translate|trans)\s+[\"']|\{%\s*(?:blocktranslate|blocktrans)\b(?:(?!%\})(?!\bcount\b).)*%\}", re.DOTALL
)


def test_every_text_without_a_count_of_the_server_templates_is_read():
    """Positive control: each ``{% translate %}`` and ``{% blocktranslate %}`` with no count of the templates of the
    platform, ``live`` and the apps gives its text to the guard, ``base``'s «too many attempts» page among them
    (hub#1333)."""
    said = code_messages()
    tags, read = {}, {}
    for config in server_modules():
        texts = [path.read_text(encoding="utf-8") for path in own_templates(config)]
        tags[config.label] = sum(len(TEXT_TAG.findall(text)) for text in texts)
        read[config.label] = [message for text in texts for message in template_messages_in(text)]
    assert {label: len(messages) for label, messages in read.items()} == tags
    assert {"control", "base", "website"} <= {label for label, count in tags.items() if count}
    assert sum(tags.values()) > 50
    assert "Too many sign-in attempts" in read["base"]
    assert all(message in said[label] for label, messages in read.items() for message in messages)


def test_a_text_said_with_an_underscore_leaves_the_count_of_the_tags_right(tmp_path, monkeypatch):
    """A template that says a text only as ``_("…")`` has no tag for the control of the tags to count, and its text
    still reaches the guard."""
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "form.html").write_text('<p>{{ _("Clear the fields.") }}</p>\n', encoding="utf-8")
    modules = [*server_modules(), SimpleNamespace(label="probe", path=str(tmp_path))]
    monkeypatch.setitem(globals(), "server_modules", lambda: modules)
    test_every_text_without_a_count_of_the_server_templates_is_read()
    assert code_messages()["probe"] == ["Clear the fields."]


def test_the_server_codes_texts_without_a_count_are_read():
    """Positive control: the messages ``control``, ``base``, ``live`` and the apps hand the gettext family in their code
    are read with ``said_in_code``, a contexted one as the screen shows it, without its context (pricing's
    ``pgettext_lazy("pricing", "active")``)."""
    said = code_messages()
    found = {label for label, messages in said.items() if messages}
    assert {"control", "base", "live", "pricing", "verifactu"} <= found
    assert sum(len(messages) for messages in said.values()) > 1000
    assert "0 = no limit." in said["control"] and "Check the highlighted details." in said["live"]
    assert {"Price list", "active"} <= set(said["pricing"])
    assert not any("\x04" in message for messages in said.values() for message in messages)


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("probe.py", 'from django.utils.translation import gettext_lazy as _\n\nPROBE = _("Clear the field(s).")\n'),
        ("templates/probe/form.html", '{% load i18n %}<p>{% translate "Clear the field(s)." %}</p>\n'),
        (
            "templates/probe/form.txt",
            "{% load i18n %}{% blocktranslate with form=name %}Clear the field(s) of {{ form }}."
            "{% endblocktranslate %}\n",
        ),
        ("templates/probe/braces.html", '<p>{{ _("Clear the field(s).") }}</p>\n'),
        ("templates/probe/filter.html", '<p>{{ answer|default:_("Clear the field(s).") }}</p>\n'),
        ("templates/probe/tag.html", '{% firstof nickname _("Clear the field(s).") %}\n'),
    ],
    ids=["code", "translate", "blocktranslate", "braces", "filter", "tag"],
)
def test_the_check_catches_a_text_with_parentheses_the_catalogue_does_not_keep_yet(
    name, content, tmp_path, monkeypatch
):
    """«Clear the field(s).» said with no count in a module's code or in one of its templates, by a tag or as a
    ``_("…")``, before ``makemessages`` takes it to the ``.po``, turns the guard red (hub#1333, hub#1353)."""
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    modules = [*server_modules(), SimpleNamespace(label="probe", path=str(tmp_path))]
    monkeypatch.setitem(globals(), "server_modules", lambda: modules)
    with pytest.raises(AssertionError, match=re.escape("probe: Clear the field(s)")):
        test_no_code_says_a_count_with_parentheses()


def test_no_code_says_a_count_with_parentheses():
    """In English there is no catalogue: the screen says the forms the code hands ``ngettext`` and the templates'
    ``{% blocktranslate count %}``, whatever the ``.po`` keeps (hub#1294, hub#1318), and the texts with no count they
    say, before ``makemessages`` takes them to the ``.po`` (hub#1333)."""
    plurals, messages = code_plurals(), code_messages()
    found = {
        f"{label}: {text}"
        for label in plurals.keys() | messages.keys()
        for text in [*(form for pair in plurals.get(label, []) for form in pair), *messages.get(label, [])]
        if IN_PARENTHESES.search(text)
    }
    assert found == set()
