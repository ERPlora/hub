from decouple import config

# The worker's CloudWatch metrics (base.metrics; hub#488): published only where the environment turns them on, prod's
# worker, whose task role may call PutMetricData on ERPlora/Hubs and ERPlora/Fiscal (aws stacks/prod/apps.tf). pre,
# local development and the tests have no such permission: off by default, so nothing is published there.
METRICS_ENABLED = config("METRICS_ENABLED", default=False, cast=bool)
# What each business does during the day, counted by the process that serves it (base/meter.py): on wherever
# config.asgi runs; off in the tests, which write by calling meter.flush().
METER_ENABLED = config("METER_ENABLED", default=True, cast=bool)

# Logging: everything to the console (CloudWatch Logs in production), at LOG_LEVEL.

LOG_LEVEL = config("LOG_LEVEL", default="INFO").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
        "null": {"class": "logging.NullHandler"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        # Django's own logger writes once, through the same handler (not also through its DEBUG-only one).
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        # A Host outside ALLOWED_HOSTS (scanners at the balancer) is still answered 400 and stays in the access log,
        # but writes no ERROR with its traceback (hub#817; Django's documented way). Any other django.security
        # event is still an ERROR.
        "django.security.DisallowedHost": {"handlers": ["null"], "propagate": False},
    },
}
