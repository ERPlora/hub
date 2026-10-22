"""Live queries of the website app and the events that re-run them after the COMMIT.

The editor follows the site: another editor's save, a publication or the site going offline reach it. An upload
changes no site until a save names it.
"""

from live.live_registry import live

from apps.website.events import SITE_PUBLISHED, SITE_UNPUBLISHED, SITE_UPDATED

live("website.site.get", on=[SITE_UPDATED, SITE_PUBLISHED, SITE_UNPUBLISHED])
