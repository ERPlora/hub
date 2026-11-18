from decouple import config

from config.settings.core import DEBUG

# The demo hubs, which the SaaS's /demo/ asks for: how many may be live at once (503
# base.demo_full beyond), how long each lives, and how many days a
# purged one still answers 410 before its host is 404. Defaults for every environment; the variables only tune them.
MAX_CONCURRENT_DEMOS = config("MAX_CONCURRENT_DEMOS", default=50, cast=int)
DEMO_TTL_MINUTES = config("DEMO_TTL_MINUTES", default=60, cast=int)
DEMO_TOMBSTONE_DAYS = config("DEMO_TOMBSTONE_DAYS", default=7, cast=int)
# Whether a module kept out of the store (``listed = False``: today only apps/demo, the platform's reference) shows:
# in the menu, in «My apps» and with its example steps, panels and counters on the Home (base.home.shown_modules).
# On with DEBUG (development, the tests and the e2e), off in prod and pre: a customer never sees the reference app;
# a demo's hub shows it whatever this says.
SHOW_UNLISTED_MODULES = config("SHOW_UNLISTED_MODULES", default=DEBUG, cast=bool)
# The Fernet key (32 bytes, URL-safe base64; Secrets Manager in AWS) that seals a business's own VeriFactu
# certificate in its hub database (apps/verifactu/certificates.py). Empty: the Hub starts, and uploading a
# certificate is refused visibly (verifactu.certificate_storage_unavailable).
FISCAL_CERTIFICATE_KEY = config("FISCAL_CERTIFICATE_KEY", default="")
# The Fernet key (32 bytes, URL-safe base64; Secrets Manager in AWS) that seals the secrets the automations
# use to call other systems (apps/flow/vault.py, FLOW-F26). Empty: the Hub starts, and saving or using a secret
# is refused visibly (flow.secrets_key_missing).
FLOW_SECRETS_KEY = config("FLOW_SECRETS_KEY", default="")
# The platform's key of Google's Places API (New), with which the Hub reads the rating and reviews of a business's
# place for its website (apps/website/reviews.py; Place Details and Text Search, from the server only). Secrets Manager
# and the task definition in AWS. Empty: the reviews section asks nothing and shows only what was read before.
GOOGLE_PLACES_API_KEY = config("GOOGLE_PLACES_API_KEY", default="")
# Whether a business may go live with VeriFactu on this server (VERIFACTU-F08): ERPlora opens it by hand,
# and only the prod deployment honours it (apps.verifactu.queries.production_open; pre files in testing).
VERIFACTU_PRODUCTION_ENABLED = config("VERIFACTU_PRODUCTION_ENABLED", default=False, cast=bool)
# Whether a business may take ERPlora's route, ERPlora filing for it with its seal (apps/verifactu/erplora_route.py).
VERIFACTU_ERPLORA_ROUTE_ENABLED = config("VERIFACTU_ERPLORA_ROUTE_ENABLED", default=True, cast=bool)
