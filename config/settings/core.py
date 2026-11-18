from pathlib import Path

from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parents[2]

# Off by default: a missing variable must never run production with DEBUG.
DEBUG = config("DEBUG", default=False, cast=bool)
# The deployment: prod, or pre (the team's pre-production, pre.erplora.com). Both run in one cluster on one Valkey,
# so the cache keys carry it.
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
# How many proxies stand in front of the Hub, each appending the address that connected to it to
# X-Forwarded-For: the ALB in AWS (1), nothing in local development (0). base.throttle.client_address
# counts a public caller by that entry from the end, never by one the client wrote.
TRUSTED_PROXY_HOPS = config("TRUSTED_PROXY_HOPS", default=0 if DEBUG else 1, cast=int)
if TRUSTED_PROXY_HOPS < 0:
    raise ImproperlyConfigured(f"TRUSTED_PROXY_HOPS must be 0 or more (got {TRUSTED_PROXY_HOPS}).")
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
# The windows a page opens keep it as their opener: Meta's window to connect a WhatsApp number (Embedded Signup)
# and the SaaS's return page post back to it. Django's default, same-origin, cuts them; a page of another origin
# that opens the Hub is still cut off. Never unsafe-none.
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"
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
