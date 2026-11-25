"""Which modules a scope shows, and so which bring their steps, panels and counters to its Home."""

from collections.abc import Iterable

from django.conf import settings
from live.meta import LiveAppConfig, module_configs


def shown_modules(*, demo_hub: bool = False) -> list[LiveAppConfig]:
    """The modules a scope shows anywhere: its menu, «My apps» (``base.session.me``) and the Home's hooks.

    Every module of the store; one kept out of it (the reference app) only where ``SHOW_UNLISTED_MODULES`` says
    (development, the tests and the e2e) or on a demo's hub: never on a customer's.
    """
    return [config for config in module_configs() if config.listed or settings.SHOW_UNLISTED_MODULES or demo_hub]


def home_modules(on: Iterable[str], *, demo_hub: bool = False) -> list[LiveAppConfig]:
    """The modules whose steps, panels and counters reach the Home of a scope where the apps ``on`` are on."""
    on = set(on)
    return [config for config in shown_modules(demo_hub=demo_hub) if config.label in on]


def business_apps() -> list[str]:
    """The modules a business may turn on: every module but those out of the store (the reference app)."""
    return [config.label for config in module_configs() if config.listed]


def shell_icon(config: LiveAppConfig) -> str:
    """The icon the shell paints for a module: its first menu entry's, as the launcher and «My apps»; without a menu,
    the shell's own for an app. The module's ``icon`` is the store's, baked apart (``base.catalog``): HubIcon refuses
    a name the shell has not registered."""
    return config.navigation[0].icon if config.navigation else "ion:apps-outline"
