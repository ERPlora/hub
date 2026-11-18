from decouple import config

from config.settings.core import DEBUG

# ERPlora's own hub: it issues ERPlora's invoices to its customers, which the SaaS posts to
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
# The hub base.scheduler.run_due runs the apps' scheduled tasks on when it is given no scope; the worker
# itself loops over the hubs whose hub_due has come.
WORKER_SCOPE_SLUG = config("WORKER_SCOPE_SLUG", default=PLATFORM_HUB_SLUG)
# First label of the platform host: hubs.erplora.com, locally hubs.localhost:8000, only the Hub admin
# for the staff. `hub` stays a reserved slug but is not the platform host.
PLATFORM_HOST_LABEL = "hubs"
# The domain the hubs live under: a hub is <slug>.<HUB_BASE_DOMAIN> and the platform host
# hubs.<HUB_BASE_DOMAIN>; any other host is no hub (base.operations). erplora.com in prod,
# pre.erplora.com in pre, localhost locally. Empty: no base domain, the hub is the Host's first label
# wherever it is.
HUB_BASE_DOMAIN = (
    config("HUB_BASE_DOMAIN", default="localhost" if DEBUG else "erplora.com")
    .strip()
    .strip(".")
    .lower()
)
