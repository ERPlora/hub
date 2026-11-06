"""The labels of the closed lists the website keeps inside its JSON, where no field of its models holds them: the palette
and the background of the theme, what the catalog shows and the days of the opening hours (``schemas``). The app
declares them (``WebsiteConfig.choices``) so the assistant's card says each value by the word the editor shows, never
by its code; the public page says the days with the same ones (``render``). Each with the website's own context: a word
another app translates its way never reaches them (hub#661).
"""

from django.utils.translation import pgettext_lazy

PALETTE_LABELS = (
    ("ocean", pgettext_lazy("website", "Ocean")),
    ("forest", pgettext_lazy("website", "Forest")),
    ("terracotta", pgettext_lazy("website", "Terracotta")),
    ("slate", pgettext_lazy("website", "Slate")),
    ("rose", pgettext_lazy("website", "Rose")),
    ("sand", pgettext_lazy("website", "Sand")),
    ("midnight", pgettext_lazy("website", "Midnight")),
    ("olive", pgettext_lazy("website", "Olive")),
)
MODE_LABELS = (
    ("light", pgettext_lazy("website", "Light")),
    ("dark", pgettext_lazy("website", "Dark")),
    ("auto", pgettext_lazy("website", "Auto")),
)
SOURCE_LABELS = (
    ("inventory", pgettext_lazy("website", "Products")),
    ("service", pgettext_lazy("website", "Services")),
)
DAY_LABELS = (
    ("mon", pgettext_lazy("website", "Monday")),
    ("tue", pgettext_lazy("website", "Tuesday")),
    ("wed", pgettext_lazy("website", "Wednesday")),
    ("thu", pgettext_lazy("website", "Thursday")),
    ("fri", pgettext_lazy("website", "Friday")),
    ("sat", pgettext_lazy("website", "Saturday")),
    ("sun", pgettext_lazy("website", "Sunday")),
)

#: Each closed list by the name of its datum in the schemas, as ``LiveAppConfig.choices`` takes them.
CHOICES = {"palette": PALETTE_LABELS, "mode": MODE_LABELS, "source": SOURCE_LABELS, "day": DAY_LABELS}
