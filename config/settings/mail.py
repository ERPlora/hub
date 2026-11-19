from decouple import config

from config.settings.core import DEBUG

# Email: the console locally; in production the SES API signed by the task role (no static keys),
# or SMTP from EMAIL_* when SES_REGION is unset. EMAIL_BACKEND overrides the choice.

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
