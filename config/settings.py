"""Django settings of hub-next (phase 1: one Postgres database, scope = first label of the Host).

Configuration comes from the environment (or a ``.env`` file) through python-decouple. ``DEBUG`` is
off unless set: local development opts in with ``DEBUG=True`` in ``.env`` and then gets defaults for
``compose.yaml`` and the local SaaS; without it the settings demand ``SECRET_KEY``, ``SAAS_URL`` and
``INTERNAL_SHARED_SECRET``.
"""

from pathlib import Path

from decouple import Csv, config
from live.csp import base_policy, debug_policy

BASE_DIR = Path(__file__).resolve().parent.parent

# Off by default: a missing variable must never run production with DEBUG.
DEBUG = config("DEBUG", default=False, cast=bool)
# Only local development may fall back to a known key; production refuses to start without one.
SECRET_KEY = config("SECRET_KEY", default="django-insecure-local-only") if DEBUG else config("SECRET_KEY")
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default=".localhost,127.0.0.1,localhost", cast=Csv())

VITE_DEV_SERVER = "http://localhost:5173"

# Application definition

INSTALLED_APPS = [
    # Before daphne: its runserver (daphne + Vite) must win.
    "live",
    "daphne",
    # Before the admin: base/templates/admin/ overrides its templates (the chosen hub's banner).
    "base",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "ninja",
    "apps.demo",
]

MIDDLEWARE = [
    # First: answers /healthz before the Host is validated.
    "base.health.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    # A host that is no hub (reserved or invalid first label, live.slugs) answers 404 on hub paths.
    "base.middleware.HubHostRequiredMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # The platform host (hubs.localhost) is only the Hub admin for the staff (PLAN §18.1).
    "base.middleware.PlatformHostMiddleware",
    # No login of its own: a browser without a session on a SPA route goes to the SaaS's login.
    "base.middleware.SaasLoginRequiredMiddleware",
    # API 404/405 that never reach a route (unknown path, wrong method) answer the JSON envelope.
    "live.api_errors.ApiErrorEnvelopeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.csp",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # The hub chosen for the admin (deep link /admin/hub/<slug>/), shown in its banner.
                "base.admin.admin_hub_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database: Postgres only, also locally (compose.yaml). Django's native pool, never
# CONN_MAX_AGE > 0 with it.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="hub"),
        "USER": config("DB_USER", default="hub"),
        "PASSWORD": config("DB_PASSWORD", default="hub"),
        "HOST": config("DB_HOST", default="127.0.0.1"),
        "PORT": config("DB_PORT", default=5432, cast=int),
        "OPTIONS": {"pool": {"min_size": 1, "max_size": 8}},
        # Not test_hub: that one belongs to the packages/live suite, which may run at the same time.
        "TEST": {"NAME": "test_hub_next"},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Login through the SaaS (PLAN-SAAS §2.1): its URL, and the secret both sign /internal calls with
# (the same value in saas-next). Production refuses to start without them.

# The SaaS is erplora.com, locally http://localhost:8001 (hubs.localhost is the Hub admin's host).
SAAS_URL = config("SAAS_URL", default="http://localhost:8001") if DEBUG else config("SAAS_URL")
INTERNAL_SHARED_SECRET = (
    config("INTERNAL_SHARED_SECRET", default="local-internal-shared-secret") if DEBUG else config("INTERNAL_SHARED_SECRET")
)
# First label of the platform host: hubs.erplora.com, locally hubs.localhost:8000, only the Hub admin
# for the staff (round 13, PLAN §18.1). `hub` stays a reserved slug but is not the platform host.
PLATFORM_HOST_LABEL = "hubs"
# SESSION_COOKIE_SAMESITE stays "Lax": /auth/callback is a top-level POST from the SaaS (cross-site
# locally, localhost:8001 → a.localhost:8000), which carries no Lax cookie in; but the session cookie it
# SETS on its response is stored, and the redirect to `next` is a top-level GET that sends it.

# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
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

# Content Security Policy (Django's native middleware, with a nonce per response).

SECURE_CSP = debug_policy(VITE_DEV_SERVER) if DEBUG else base_policy()

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

# Operations, live queries and the SPA (packages/live).

LIVE = {
    "context_builder": "base.operations.HubContextBuilder",
    "control_alias": "default",
    "apps_dirs": [BASE_DIR / "apps"],
    # Hub slugs (live.slugs): 3–63 characters in production; local development also opens the
    # one-letter demo hubs a and b (a.localhost:8000, b.localhost:8000).
    "hub_slug_min_length": 1 if DEBUG else 3,
    "spa": {
        "entry": "frontend/main.ts",
        "manifest": SPA_DIST / ".vite" / "manifest.json",
        "dev_server": VITE_DEV_SERVER if DEBUG else None,
        "palette_default": "erplora",
        "palettes": ["erplora"],
    },
    # The repo is its own pnpm workspace (packages/ui is a submodule), so Vite runs from here.
    "vite": {"command": ["pnpm", "run", "dev"], "cwd": str(BASE_DIR)},
}

# Email

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.console.EmailBackend",
    },
}
