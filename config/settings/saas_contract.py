from decouple import config

from config.settings.core import DEBUG

# Login through the SaaS: its URL, and the secret both sign /internal calls with
# (the same value in the SaaS). Production refuses to start without them.

# The SaaS is erplora.com, locally http://localhost:8001 (hubs.localhost is the Hub admin's host):
# SAAS_URL is where the browser goes (/hub-login/, the admin's Hubs page, the logout).
SAAS_URL = config("SAAS_URL", default="http://localhost:8001") if DEBUG else config("SAAS_URL")
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
#: Where «Report a problem» tells the person to write when erplora.com could not take the report (BASE-F108): the
#: SaaS's own support mailbox.
SUPPORT_EMAIL = config("SUPPORT_EMAIL", default="support@erplora.com")
#: Whether erplora.com reads the assistant's answers aloud in its own voices (base.assistant.speak). Off until a voice
#: provider is configured there: the panel reads with the device's voice and offers no choice.
ASSISTANT_SERVER_VOICE = config("ASSISTANT_SERVER_VOICE", default=False, cast=bool)
# How far an internal call's X-Erplora-Timestamp may be from now (both ways), as in the SaaS.
INTERNAL_SIGNATURE_MAX_AGE_SECONDS = 300
# SESSION_COOKIE_SAMESITE stays "Lax": /auth/callback is a top-level POST from the SaaS (cross-site
# locally, localhost:8001 → a.localhost:8000), which carries no Lax cookie in; but the session cookie it
# SETS on its response is stored, and the redirect to `next` is a top-level GET that sends it.
