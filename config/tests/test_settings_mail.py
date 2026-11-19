"""Where the Hub's mail goes: the console in development, SES or SMTP in production."""

import decouple
import pytest
from django.core.mail import mailers
from django.test import override_settings

from config.tests.settings_env import DEVELOPMENT_ENV, PRODUCTION_ENV


def test_development_mail_goes_to_the_console(load_settings):
    loaded = load_settings(**DEVELOPMENT_ENV)
    assert loaded["MAILERS"] == {
        "default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}
    }
    assert loaded["DEFAULT_FROM_EMAIL"] == "noreply@erplora.com"
    # Even with the SES region of production in the environment, DEBUG never sends real mail.
    loaded = load_settings(**DEVELOPMENT_ENV, SES_REGION="eu-west-1")
    assert loaded["MAILERS"] == {
        "default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}
    }


def test_production_mail_goes_through_the_ses_api_with_the_task_role(load_settings):
    # ECS passes SES_REGION and its task role may ses:SendRawEmail: no SMTP credentials, no static keys.
    loaded = load_settings(
        **PRODUCTION_ENV, SES_REGION="eu-west-1", EMAIL_HOST="smtp.example.com"
    )
    assert loaded["MAILERS"] == {"default": {"BACKEND": "django_ses.SESBackend"}}
    assert loaded["AWS_SES_REGION_NAME"] == "eu-west-1"
    assert loaded["AWS_SES_REGION_ENDPOINT"] == "email.eu-west-1.amazonaws.com"
    # The throttle would first call ses:GetSendQuota, which the task role may not.
    assert loaded["AWS_SES_AUTO_THROTTLE"] is None
    assert (
        not {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SES_ACCESS_KEY_ID"}
        & loaded.keys()
    )


def test_the_ses_backend_builds_from_the_settings_so_its_library_is_installed(
    load_settings,
):
    # Built the way Django 6.1 builds a mailer (alias + OPTIONS); building neither connects nor signs.
    loaded = load_settings(**PRODUCTION_ENV, SES_REGION="eu-west-1")
    ses_settings = {
        key: value for key, value in loaded.items() if key.startswith("AWS_SES_")
    }
    with override_settings(MAILERS=loaded["MAILERS"], **ses_settings):
        backend = mailers.default
    assert (
        f"{type(backend).__module__}.{type(backend).__name__}"
        == "django_ses.SESBackend"
    )
    assert (backend._region_name, backend._endpoint_url) == (
        "eu-west-1",
        "https://email.eu-west-1.amazonaws.com",
    )
    assert backend._throttle is None
    # No keys of its own: boto3 signs with the task role.
    assert (backend._access_key_id, backend._access_key, backend._session_token) == (
        None,
        None,
        None,
    )


def test_a_ses_backend_named_by_the_environment_needs_its_region(load_settings):
    with pytest.raises(decouple.UndefinedValueError, match="SES_REGION"):
        load_settings(**PRODUCTION_ENV, EMAIL_BACKEND="django_ses.SESBackend")


def test_production_mail_without_ses_is_smtp_from_the_environment(load_settings):
    loaded = load_settings(**PRODUCTION_ENV)
    assert loaded["MAILERS"] == {
        "default": {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {
                "host": "localhost",
                "port": 587,
                "username": "",
                "password": "",
                "use_tls": True,
                "timeout": 10,
            },
        }
    }
    loaded = load_settings(
        **PRODUCTION_ENV,
        EMAIL_HOST="email-smtp.eu-west-1.amazonaws.com",
        EMAIL_PORT="2587",
        EMAIL_HOST_USER="smtp-user",
        EMAIL_HOST_PASSWORD="smtp-password",
        EMAIL_USE_TLS="False",
        DEFAULT_FROM_EMAIL="hub@erplora.com",
    )
    assert loaded["MAILERS"]["default"]["OPTIONS"] == {
        "host": "email-smtp.eu-west-1.amazonaws.com",
        "port": 2587,
        "username": "smtp-user",
        "password": "smtp-password",
        "use_tls": False,
        "timeout": 10,
    }
    assert loaded["DEFAULT_FROM_EMAIL"] == "hub@erplora.com"


def test_any_mail_backend_from_the_environment_takes_no_smtp_options(load_settings):
    loaded = load_settings(
        **PRODUCTION_ENV, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
    )
    assert loaded["MAILERS"] == {
        "default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}
    }
