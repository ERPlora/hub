"""What the Hub reports on itself: the worker's metrics, the logs and the meter."""

from config.tests.settings_env import DEVELOPMENT_ENV, PRODUCTION_ENV


def test_the_worker_publishes_its_metrics_only_where_the_environment_turns_them_on(load_settings):
    """hub#488: CloudWatch's PutMetricData only where the task role may call it (prod's worker, aws stacks/prod); pre,
    local development and the tests have no such permission, so a missing variable publishes nothing."""
    assert load_settings(**PRODUCTION_ENV)["METRICS_ENABLED"] is False
    assert load_settings(**DEVELOPMENT_ENV)["METRICS_ENABLED"] is False
    assert load_settings(**PRODUCTION_ENV, METRICS_ENABLED="true")["METRICS_ENABLED"] is True
    assert load_settings(**PRODUCTION_ENV, METRICS_ENABLED="false")["METRICS_ENABLED"] is False


def test_logs_go_to_the_console_at_the_level_of_the_environment(load_settings):
    logging = load_settings(**PRODUCTION_ENV)["LOGGING"]
    assert logging["handlers"]["console"]["class"] == "logging.StreamHandler"
    assert logging["root"] == {"handlers": ["console"], "level": "INFO"}
    # Django's own logger writes once, through the same handler.
    assert logging["loggers"]["django"] == {
        "handlers": ["console"],
        "level": "INFO",
        "propagate": False,
    }
    logging = load_settings(**PRODUCTION_ENV, LOG_LEVEL="warning")["LOGGING"]
    assert (
        logging["root"]["level"] == logging["loggers"]["django"]["level"] == "WARNING"
    )


def test_the_meter_is_on_where_requests_are_served_unless_the_environment_says(load_settings):
    assert load_settings(**PRODUCTION_ENV)["METER_ENABLED"] is True
    assert load_settings(**DEVELOPMENT_ENV)["METER_ENABLED"] is True
    assert load_settings(**PRODUCTION_ENV, METER_ENABLED="false")["METER_ENABLED"] is False
