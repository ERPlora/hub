"""What else flipping an app's switch changes in a business, and how it is said before the yes: the apps that come
along when it goes on, or go with it when it goes off, by the rules that turn them (``base.activation``), in the one
sentence both the Apps screen's question (``base.app.list``) and the assistant's card (``base.app.enable``,
``base.app.disable``) show."""

from collections.abc import Iterable, Mapping

from django.utils import translation
from django.utils.translation import ngettext_lazy, pgettext_lazy
from live.meta import module_configs

from base import activation, listing

#: What the assistant's card calls the apps that go on or off with the one it turns.
ALONG = pgettext_lazy("base", "Other apps")
TURNS_ON_WITH = ngettext_lazy(
    "%(app)s needs %(apps)s: it turns on with it.", "%(app)s needs %(apps)s: they turn on with it.", "count"
)
TURNS_OFF_WITH = ngettext_lazy(
    "%(apps)s turns off with it: only %(app)s needed it.",
    "%(apps)s turn off with it: only %(app)s needed them.",
    "count",
)


def along(
    label: str,
    current: Mapping[str, activation.Activation],
    graph: activation.Graph,
    kept: Iterable[str] = (),
    *,
    on: bool,
) -> list[str]:
    """The other apps that turning ``label`` on (``on``), or off, turns too: what it needs that is off, or failed, on;
    what came along only with it off, never one of ``kept`` (``activation.mandatory_on``). None while an app on needs
    it: turning it off is refused, naming that app."""
    if on:
        changes = activation.enabling(label, current, graph)
    elif activation.required_by(label, current, graph):
        return []
    else:
        changes = activation.disabling(label, current, graph, kept)
    return [other for other in changes if other != label]


def said(label: str, others: list[str], *, on: bool, language: str) -> str:
    """The ``others`` :func:`along` gives for ``label`` as the person reads them in ``language``, before the yes:
    «Mesas se desactiva con ella: solo la necesitaba Reservas.»; ``""`` when nothing else changes."""
    if not others:
        return ""
    with translation.override(language):
        names = {config.label: str(config.verbose_name) for config in module_configs()}
        apps = listing.joined(listing.ordered(names.get(other, other) for other in others), language)
        words = TURNS_ON_WITH if on else TURNS_OFF_WITH
        return str(words % {"count": len(others), "app": names.get(label, label), "apps": apps})


def switch_said(
    label: str,
    current: Mapping[str, activation.Activation],
    graph: activation.Graph,
    kept: Iterable[str] = (),
    *,
    language: str,
) -> str:
    """What flipping ``label``'s switch in Apps also changes, as its question says it: what goes with it when the
    business wants it (on, being set up or failed), else what comes along with it."""
    on = not current[label].wanted
    return said(label, along(label, current, graph, kept, on=on), on=on, language=language)


def card_datum(sentence: str) -> list[dict]:
    """The assistant card's datum «Other apps» saying ``sentence``; none when it says nothing."""
    return [{"name": "along", "label": str(ALONG), "kind": "text", "value": sentence}] if sentence else []
