"""Events of the website app (``<app>.<entity>.<fact>``): recorded by services.py, cited by live.py.

The website reacts to no event of another app: its catalog is read when it publishes and refreshed by the visitor's
browser, so this module only names its own.
"""

SITE_UPDATED = "website.site.updated"
SITE_PUBLISHED = "website.site.published"
SITE_UNPUBLISHED = "website.site.unpublished"
IMAGE_UPLOADED = "website.image.uploaded"

ALL = [SITE_UPDATED, SITE_PUBLISHED, SITE_UNPUBLISHED, IMAGE_UPLOADED]
