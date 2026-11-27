"""The words read out to a customer before their marketing consent is recorded, and their version: the card screen and
the assistant's card show them, and a new consent stores them as its proof (CUSTOMER-F14)."""

from django.utils import translation
from django.utils.translation import gettext_lazy as _

#: Bump it when the words change: the proof says which wording the customer agreed to.
VERSION = "counter-v1"
WORDS = _(
    "I want to receive offers and news from this business through this channel. I can unsubscribe whenever I want."
)


def words(language: str) -> str:
    with translation.override(language):
        return str(WORDS)
