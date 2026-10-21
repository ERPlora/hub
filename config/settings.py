"""Django settings of hub-next (phase 1: one Postgres database, scope = the Host's label on HUB_BASE_DOMAIN).

Configuration comes from the environment (or a ``.env`` file) through python-decouple. ``DEBUG`` is
off unless set: local development opts in with ``DEBUG=True`` in ``.env`` and then gets defaults for
``compose.yaml`` and the local SaaS; without it the settings demand ``SECRET_KEY``, ``SAAS_URL`` and
``INTERNAL_SHARED_SECRET``. The production variables are the contract of ``aws-next/stacks/prod/apps.tf``
(``aws-next/README.md``, «Contrato app ↔ infra»).
"""

from pathlib import Path
from urllib.parse import urlsplit

from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured
from django.utils.csp import CSP
from live.csp import base_policy, debug_policy

BASE_DIR = Path(__file__).resolve().parent.parent

# Off by default: a missing variable must never run production with DEBUG.
DEBUG = config("DEBUG", default=False, cast=bool)
# The deployment: prod, or pre (the team's pre-production, pre.erplora.com; plan
# 2026-10-14-entorno-pre). Both run in one cluster on one Valkey, so the cache keys carry it.
ERPLORA_ENVIRONMENTS = ("prod", "pre")
ERPLORA_ENVIRONMENT = config("ERPLORA_ENVIRONMENT", default="prod")
if ERPLORA_ENVIRONMENT not in ERPLORA_ENVIRONMENTS:
    raise ImproperlyConfigured(
        f"ERPLORA_ENVIRONMENT must be one of {', '.join(ERPLORA_ENVIRONMENTS)}, "
        f"not {ERPLORA_ENVIRONMENT!r}."
    )
# Only local development may fall back to a known key; production refuses to start without one.
SECRET_KEY = (
    config("SECRET_KEY", default="django-insecure-local-only")
    if DEBUG
    else config("SECRET_KEY")
)
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS", default=".localhost,127.0.0.1,localhost", cast=Csv()
)

# HTTPS: the ALB terminates TLS, redirects HTTP to HTTPS and sets X-Forwarded-Proto (daphne
# --proxy-headers reads it as well). Django does not redirect: the SaaS calls /internal over plain
# HTTP on the private name (saas → hub.erplora.internal), never through the ALB.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
# HSTS on the hub's own hosts (<slug>.erplora.com, hubs.erplora.com). Subdomains and the preload list
# are the apex's domain-wide decision (erplora.com, the SaaS): opt-in here.
SECURE_HSTS_SECONDS = config(
    "SECURE_HSTS_SECONDS", default=0 if DEBUG else 31536000, cast=int
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False, cast=bool
)
SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=False, cast=bool)
# What the platform answers elsewhere: the ALB redirects to HTTPS (W008); HSTS for subdomains and the
# preload list is the apex's (W005, W021).
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W008", "security.W021"]

# Vite's dev server (`vite.config.ts` reads the same VITE_DEV_PORT): 5173 unless a second checkout runs
# beside another one, as the e2e of a branch does. `runserver` hands the port it read to the Vite it
# starts (LIVE["vite"]); `pnpm run dev` or the e2e on their own read the process environment only, not
# this repo's .env.
VITE_DEV_PORT = config("VITE_DEV_PORT", default=5173, cast=int)
if not 0 < VITE_DEV_PORT < 65536:
    raise ImproperlyConfigured(f"VITE_DEV_PORT must be a TCP port, not {VITE_DEV_PORT}.")
VITE_DEV_SERVER = f"http://localhost:{VITE_DEV_PORT}"

# Application definition

INSTALLED_APPS = [
    # Before daphne: its runserver (daphne + Vite) must win.
    "live",
    "daphne",
    # Before the admin: base/templates/admin/ overrides its templates (the chosen hub's banner).
    "base",
    # The mirror of the SaaS's `shared` schema (round 16): only base/catalog.py writes it.
    "shared",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "ninja",
    "apps.demo",
    "apps.customer",
    "apps.staff",
    "apps.tax",
    "apps.inventory",
    "apps.sale",
    "apps.service",
    "apps.schedule",
    "apps.cash_register",
    "apps.invoice",
    "apps.appointment",
    "apps.online_booking",
    "apps.reservation",
    "apps.pricing",
    "apps.combo",
    "apps.attendance",
    "apps.table",
    "apps.kitchen",
    "apps.task",
    "apps.whatsapp_inbox",
    "apps.flow",
    "apps.verifactu",
    "apps.payment",
    "apps.printing",
    "apps.cart_checkout",
    "apps.modifier",
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
# CONN_MAX_AGE > 0 with it. In production every connection verifies Aurora's certificate and host
# name (DB_SSLMODE=verify-full, DB_SSLROOTCERT = the RDS bundle in the image) and names its task
# (DB_APPLICATION_NAME, pg_stat_activity); each option only when set. A dead database fails within
# DB_CONNECT_TIMEOUT seconds, both waiting for a pooled connection and per connection attempt
# (psycopg: 30 s and 130 s), so /readyz answers 503 before its probes give up. The pool keeps one
# connection and gives back the rest of a burst one per minute (max_idle; psycopg's 600 s held a
# scanner's 8 for over an hour): PLAN-DB «Conexiones», round 2026-10-18.

db_optional_options = {
    "DB_SSLMODE": "sslmode",
    "DB_SSLROOTCERT": "sslrootcert",
    "DB_APPLICATION_NAME": "application_name",
}
db_connect_timeout = config("DB_CONNECT_TIMEOUT", default=5, cast=int)
# Not test_hub: that one belongs to the packages/live suite, which may run at the same time. Two runs
# of this suite at once (two sessions, two checkouts) each set their own TEST_DB_NAME, as saas-next.
TEST_DB_NAME = config("TEST_DB_NAME", default="test_hub_next")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="hub"),
        "USER": config("DB_USER", default="hub"),
        "PASSWORD": config("DB_PASSWORD", default="hub"),
        "HOST": config("DB_HOST", default="127.0.0.1"),
        "PORT": config("DB_PORT", default=5432, cast=int),
        "OPTIONS": {
            "pool": {
                "min_size": 1,
                "max_size": 8,
                "max_idle": 60,
                "timeout": db_connect_timeout,
            },
            "connect_timeout": db_connect_timeout,
            **{
                option: value
                for env, option in db_optional_options.items()
                if (value := config(env, default=""))
            },
        },
        "TEST": {"NAME": TEST_DB_NAME},
    }
}

# The SaaS's `saas` database, schema `shared`, only for register_apps (round 16, PLAN §21; spec §3.3).
# Declared only where its credentials exist: in production the worker task (SHARED_DB_USER, role
# hub_shared), locally always (compose.yaml's user). Straight to Aurora's writer (the PgBouncer
# sidecar only knows hub_app) with the TLS and timeout of every direct connection; one short
# connection when the worker starts, no pool.
SHARED_DB_USER = config("SHARED_DB_USER", default="hub" if DEBUG else "")
if SHARED_DB_USER:
    DATABASES["shared"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("SHARED_DB_NAME", default="saas"),
        "USER": SHARED_DB_USER,
        "PASSWORD": config("SHARED_DB_PASSWORD", default="hub")
        if DEBUG
        else config("SHARED_DB_PASSWORD"),
        "HOST": config("DB_HOST", default="127.0.0.1"),
        "PORT": config("DB_PORT", default=5432, cast=int),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {
            option: value
            for option, value in DATABASES["default"]["OPTIONS"].items()
            if option != "pool"
        },
        "TEST": {"NAME": f"{TEST_DB_NAME}_shared"},
    }
# First: the models of `shared` go to that alias only (phase 2's TenantRouter goes after it).
DATABASE_ROUTERS = ["base.routers.SharedRouter"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Cache: the shared Valkey (TLS, rediss://) when VALKEY_URL is set, with a prefix per project and
# environment (hub, pre-hub: pre shares prod's Valkey), a TTL on every key (never TIMEOUT=None) and
# 2 s socket timeouts (a Valkey that hangs fails the call, not the request; Django hands OPTIONS to
# redis-py); otherwise this process's memory.

VALKEY_URL = config("VALKEY_URL", default="")
CACHE_KEY_PREFIX = "hub" if ERPLORA_ENVIRONMENT == "prod" else f"{ERPLORA_ENVIRONMENT}-hub"
CACHES = {
    "default": (
        {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": VALKEY_URL,
            "KEY_PREFIX": CACHE_KEY_PREFIX,
            "TIMEOUT": 300,
            "OPTIONS": {"socket_connect_timeout": 2, "socket_timeout": 2},
        }
        if VALKEY_URL
        else {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    )
}

# Login through the SaaS (PLAN-SAAS §2.1): its URL, and the secret both sign /internal calls with
# (the same value in saas-next). Production refuses to start without them.

# The SaaS is erplora.com, locally http://localhost:8001 (hubs.localhost is the Hub admin's host):
# SAAS_URL is where the browser goes (/hub-login/, the admin's Hubs page, the logout).
SAAS_URL = (
    config("SAAS_URL", default="http://localhost:8001") if DEBUG else config("SAAS_URL")
)
# Where the Hub calls the SaaS's /internal/*: the ALB answers 404 to it, so production uses the private
# name (http://saas.erplora.internal:8000); without it, the public URL (local development).
SAAS_INTERNAL_URL = config("SAAS_INTERNAL_URL", default=SAAS_URL)
INTERNAL_SHARED_SECRET = (
    config("INTERNAL_SHARED_SECRET", default="local-internal-shared-secret")
    if DEBUG
    else config("INTERNAL_SHARED_SECRET")
)
# During a rotation of the shared secret, the one a call of the SaaS may still be signed with (base.internal; the
# SaaS's accounts/signing.py has the same steps); empty otherwise.
INTERNAL_SHARED_SECRET_PREVIOUS = config("INTERNAL_SHARED_SECRET_PREVIOUS", default="")
# How far an internal call's X-Erplora-Timestamp may be from now (both ways), as in the SaaS.
INTERNAL_SIGNATURE_MAX_AGE_SECONDS = 300
# The demo hubs (plan 2026-10-17, §1.11), which the SaaS's /demo/ asks for: how many may be live at once (503
# base.demo_full beyond; the final figure after measuring, PLAN-SAAS §3.5), how long each lives, and how many days a
# purged one still answers 410 before its host is 404. Defaults for every environment; the variables only tune them.
MAX_CONCURRENT_DEMOS = config("MAX_CONCURRENT_DEMOS", default=50, cast=int)
DEMO_TTL_MINUTES = config("DEMO_TTL_MINUTES", default=60, cast=int)
DEMO_TOMBSTONE_DAYS = config("DEMO_TOMBSTONE_DAYS", default=7, cast=int)
# The Fernet key (32 bytes, URL-safe base64; Secrets Manager in AWS) that seals a business's own VeriFactu
# certificate in its hub database (apps/verifactu/certificates.py). Empty: the Hub starts, and uploading a
# certificate is refused visibly (verifactu.certificate_storage_unavailable).
FISCAL_CERTIFICATE_KEY = config("FISCAL_CERTIFICATE_KEY", default="")
# The Fernet key (32 bytes, URL-safe base64; Secrets Manager in AWS) that seals the secrets the automations
# use to call other systems (apps/flow/vault.py, FLOW-F26). Empty: the Hub starts, and saving or using a secret
# is refused visibly (flow.secrets_key_missing).
FLOW_SECRETS_KEY = config("FLOW_SECRETS_KEY", default="")
# Whether a business may go live with VeriFactu on this server (VERIFACTU-F08): ERPlora opens it under Ioan's
# supervision, and only the prod deployment honours it (apps.verifactu.queries.production_open; pre files in testing).
VERIFACTU_PRODUCTION_ENABLED = config("VERIFACTU_PRODUCTION_ENABLED", default=False, cast=bool)
# ERPlora's own hub (PLAN-SAAS §4): it issues ERPlora's invoices to its customers, which the SaaS posts to
# /internal/platform/invoices (base.internal). A reserved slug, so no business can ever take it; it files in the
# AEAT's environment of the deployment (prod: production; pre: testing), never by its own switch.
PLATFORM_HUB_SLUG = config("PLATFORM_HUB_SLUG", default="erplora")
# Its issuer, set by `manage.py create_platform_hub`: ERPlora's tax identity (the old SaaS's seed_company_036).
PLATFORM_ISSUER_LEGAL_NAME = config("PLATFORM_ISSUER_LEGAL_NAME", default="ERPLORA CLOUD SL")
PLATFORM_ISSUER_TAX_ID = config("PLATFORM_ISSUER_TAX_ID", default="B27593136")
PLATFORM_ISSUER_ADDRESS = config("PLATFORM_ISSUER_ADDRESS", default="Avda. de Lisboa, 17, 2º C")
PLATFORM_ISSUER_POSTAL_CODE = config("PLATFORM_ISSUER_POSTAL_CODE", default="28822")
PLATFORM_ISSUER_CITY = config("PLATFORM_ISSUER_CITY", default="Coslada")
PLATFORM_ISSUER_PROVINCE = config("PLATFORM_ISSUER_PROVINCE", default="Madrid")
PLATFORM_ISSUER_COUNTRY = config("PLATFORM_ISSUER_COUNTRY", default="ES")
# The hub the worker runs the apps' scheduled tasks on (base.scheduler). Phase 1 has no registry of hubs, so
# it is one fixed scope; phase 2 replaces it with the loop over the hubs whose hub_due has come.
WORKER_SCOPE_SLUG = config("WORKER_SCOPE_SLUG", default=PLATFORM_HUB_SLUG)
# First label of the platform host: hubs.erplora.com, locally hubs.localhost:8000, only the Hub admin
# for the staff (round 13, PLAN §18.1). `hub` stays a reserved slug but is not the platform host.
PLATFORM_HOST_LABEL = "hubs"
# The domain the hubs live under: a hub is <slug>.<HUB_BASE_DOMAIN> and the platform host
# hubs.<HUB_BASE_DOMAIN>; any other host is no hub (base.operations). erplora.com in prod,
# pre.erplora.com in pre, localhost locally. Empty: no base domain, the hub is the Host's first label
# wherever it is (the behaviour before 2026-10-14).
HUB_BASE_DOMAIN = (
    config("HUB_BASE_DOMAIN", default="localhost" if DEBUG else "erplora.com")
    .strip()
    .strip(".")
    .lower()
)
# SESSION_COOKIE_SAMESITE stays "Lax": /auth/callback is a top-level POST from the SaaS (cross-site
# locally, localhost:8001 → a.localhost:8000), which carries no Lax cookie in; but the session cookie it
# SETS on its response is stored, and the redirect to `next` is a top-level GET that sends it.

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

# Content Security Policy (Django's native middleware, with a nonce per response).

SECURE_CSP = debug_policy(VITE_DEV_SERVER) if DEBUG else base_policy()
# form-action filters the whole redirect chain of a form post: the SPA's logout POSTs to /auth/logout,
# which answers 302 to the SaaS's logout (one hop, no page of our own in between).
saas_origin = "{0.scheme}://{0.netloc}".format(urlsplit(SAAS_URL))
SECURE_CSP["form-action"] = [*SECURE_CSP["form-action"], saas_origin]
# The SaaS serves a WhatsApp conversation's photos and voice notes (/whatsapp/media/<id>): the inbox's thread
# shows and plays them from its origin, and from no other (never Meta's CDN).
SECURE_CSP["img-src"] = [*SECURE_CSP["img-src"], saas_origin]
SECURE_CSP["media-src"] = [CSP.SELF, saas_origin]

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
# /static/catalog/<id>/img/ (round 16, spec §4.4), on hubs.erplora.com and on every hub.
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "base.catalog.AppImagesFinder",
]

# The apps' registry in the SaaS (round 16, PLAN §21; spec §4). The image's build fixes the release:
# APP_VERSION (the commit's sha) and APP_RELEASED_AT (its time, ISO 8601), which register_apps
# demands in production and which decide that an older release never overwrites a newer one.
APP_VERSION = config("APP_VERSION", default="")
APP_RELEASED_AT = config("APP_RELEASED_AT", default="")
# translate_workbooks (development only: the anthropic client is a dev dependency; ANTHROPIC_API_KEY
# in the local .env) writes each module's WORKBOOK.en.md with this model.
WORKBOOK_TRANSLATION_MODEL = config(
    "WORKBOOK_TRANSLATION_MODEL", default="claude-haiku-5-5"
)

# Operations, live queries and the SPA (packages/live).

LIVE = {
    "context_builder": "base.operations.HubContextBuilder",
    "control_alias": "default",
    # Hub slugs (live.slugs): 3–63 characters in production; local development also opens the
    # one-letter demo hubs a and b (a.localhost:8000, b.localhost:8000).
    "hub_slug_min_length": 1 if DEBUG else 3,
    "spa": {
        "entry": "frontend/main.ts",
        "manifest": SPA_DIST / ".vite" / "manifest.json",
        "dev_server": VITE_DEV_SERVER if DEBUG else None,
        "palette_default": "erplora",
        # THEME_PALETTES of packages/ui/src/shell/theme.ts: the ep_palette cookie may name any of them.
        "palettes": [
            "erplora",
            "terracotta",
            "corporate",
            "minimal",
            "forest",
            "ocean",
            "violet",
        ],
    },
    # The repo is its own pnpm workspace (packages/ui is a submodule), so Vite runs from here, with the
    # port Django read (environment or .env): vite.config.ts reads VITE_DEV_PORT from the process
    # environment only, and a Vite on another port than the page's leaves a page that never loads.
    "vite": {
        "command": ["env", f"VITE_DEV_PORT={VITE_DEV_PORT}", "pnpm", "run", "dev"],
        "cwd": str(BASE_DIR),
    },
}

# Email: the console locally; in production the SES API signed by the task role (no static keys,
# PLAN-AWS §3), or SMTP from EMAIL_* when SES_REGION is unset. EMAIL_BACKEND overrides the choice.

smtp_email_backend = "django.core.mail.backends.smtp.EmailBackend"
ses_email_backend = "django_ses.SESBackend"
if DEBUG:
    default_email_backend = "django.core.mail.backends.console.EmailBackend"
else:
    default_email_backend = (
        ses_email_backend if config("SES_REGION", default="") else smtp_email_backend
    )
email_backend = config("EMAIL_BACKEND", default=default_email_backend)
MAILERS = {"default": {"BACKEND": email_backend}}
if email_backend == ses_email_backend:
    AWS_SES_REGION_NAME = config("SES_REGION")
    AWS_SES_REGION_ENDPOINT = f"email.{AWS_SES_REGION_NAME}.amazonaws.com"
    # The throttle first calls ses:GetSendQuota, which the task role may not (only SendEmail/SendRawEmail).
    AWS_SES_AUTO_THROTTLE = None
elif email_backend == smtp_email_backend:
    MAILERS["default"]["OPTIONS"] = {
        "host": config("EMAIL_HOST", default="localhost"),
        "port": config("EMAIL_PORT", default=587, cast=int),
        "username": config("EMAIL_HOST_USER", default=""),
        "password": config("EMAIL_HOST_PASSWORD", default=""),
        "use_tls": config("EMAIL_USE_TLS", default=True, cast=bool),
        "timeout": 10,
    }
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@erplora.com")

# Logging: everything to the console (CloudWatch Logs in production), at LOG_LEVEL.

LOG_LEVEL = config("LOG_LEVEL", default="INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    # Django's own logger writes once, through the same handler (not also through its DEBUG-only one).
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False}
    },
}
