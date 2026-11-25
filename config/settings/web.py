from pathlib import Path
from urllib.parse import urlsplit

from decouple import config
from django.utils.csp import CSP
from live.csp import YOUTUBE_NOCOOKIE, base_policy, debug_policy, with_frames

from base.storage import hub_files_storage
from config.settings.core import BASE_DIR, DEBUG, VITE_DEV_SERVER
from config.settings.saas_contract import SAAS_URL

# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization: English is the source, Spanish the translation.

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("es", "Español")]
TIME_ZONE = "Europe/Madrid"
USE_I18N = True
USE_TZ = True

# Content Security Policy (Django's native middleware, with a nonce per response). A page frames its own origin and
# YouTube's privacy-enhanced player, where a module's help video plays.
SECURE_CSP = with_frames(debug_policy(VITE_DEV_SERVER) if DEBUG else base_policy(), YOUTUBE_NOCOOKIE)
# form-action filters the whole redirect chain of a form post: the SPA's logout POSTs to /auth/logout,
# which answers 302 to the SaaS's logout (one hop, no page of our own in between).
saas_origin = "{0.scheme}://{0.netloc}".format(urlsplit(SAAS_URL))
SECURE_CSP["form-action"] = [*SECURE_CSP["form-action"], saas_origin]
# The SaaS serves a WhatsApp conversation's photos and voice notes (/whatsapp/media/<id>): the inbox's thread
# shows and plays them from its origin, and from no other (never Meta's CDN). The assistant plays an answer read
# aloud in the server's voice from a blob: the page made of /api/assistant/speak's mp3.
SECURE_CSP["img-src"] = [*SECURE_CSP["img-src"], saas_origin]
SECURE_CSP["media-src"] = [CSP.SELF, "blob:", saas_origin]

# Static files: WhiteNoise. Vite already hashes its build, so no Manifest storage; the SPA build
# is served under /static/spa/ (Vite's `base`) and its hashed assets are immutable.

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
SPA_DIST = BASE_DIR / "frontend" / "dist"
STATICFILES_DIRS = [("spa", SPA_DIST)] if SPA_DIST.is_dir() else []
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
WHITENOISE_IMMUTABLE_FILE_TEST = r"^/static/spa/assets/"
# Django's two finders plus the modules' documentation images: apps/<id>/docs/img/ is published as
# /static/catalog/<id>/img/, on hubs.erplora.com and on every hub.
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "base.catalog.static_files.AppImagesFinder",
]

# The hub's file store (base.storage): the S3 bucket Terraform names, with the task role's
# credentials, or MEDIA_ROOT on disk without one. Every module reaches it as storages["hub_files"].

MEDIA_ROOT = config("MEDIA_ROOT", default=BASE_DIR / "media", cast=Path)
STORAGES["hub_files"] = hub_files_storage(
    {
        "AWS_STORAGE_BUCKET_NAME": config("AWS_STORAGE_BUCKET_NAME", default=""),
        "AWS_REGION": config("AWS_REGION", default=""),
    },
    MEDIA_ROOT,
)
# The shared image library (base.image_catalog): ERPlora/blueprints' img/. With a bucket, its copy
# under shared/catalog/ in it (publish.yml writes it); without one, the ERPlora/blueprints checkout beside this repo.
# CATALOG_DIR names a folder that wins over the bucket.
CATALOG_DIR = config(
    "CATALOG_DIR",
    default="" if config("AWS_STORAGE_BUCKET_NAME", default="") else str(BASE_DIR.parent / "blueprints" / "img"),
)
