"""The Hub admin's site (``hubs.erplora.com/admin``, PLAN §18): Django's, but a hub's model only where a business is.

Since S5 every business keeps its data in its own database and there is no shared one: on the platform host, without a
business chosen for the session (``/admin/hub/<slug>/``, ``base.admin.open_hub``), the admin works on control
(``base.middleware.HubDatabaseMiddleware``), where only control's models live. There the index and every app's page list
control's models alone (the registry, the accounts, the sessions); a hub's model (``base.tenancy.inventory``) appears
once a business is chosen, in its database. A hub's page reached without one goes back to the index, saying so
(``HubDatabaseMiddleware.process_exception``). It is the default site (``AdminConfig.default_site``), so every
``@admin.register`` of the apps lands here.
"""

from django.contrib import admin
from django.contrib.admin.apps import AdminConfig as DjangoAdminConfig

from base.tenancy import context, inventory


def _on_control() -> bool:
    """Whether the admin works on control now: no business chosen (its context is the platform's)."""
    try:
        return context.current().kind == context.CONTROL
    except context.HubContextMissing:
        return True


class AdminSite(admin.AdminSite):
    """Django's admin site; a model of a hub's database has no page while the admin works on control."""

    def register(self, model_or_iterable, admin_class=None, **options):
        super().register(model_or_iterable, admin_class, **options)
        models = model_or_iterable if isinstance(model_or_iterable, (list, tuple, set)) else [model_or_iterable]
        for model in models:
            if not model._meta.abstract and inventory.classify(model) == inventory.HUB:
                _only_with_a_business(self._registry[model])


def _only_with_a_business(model_admin) -> None:
    """Hide ``model_admin``'s model from the index and its app's page while the admin works on control: its rows are a
    business's, in that business's own database."""
    has_module_permission = model_admin.has_module_permission

    def guarded(request) -> bool:
        return not _on_control() and has_module_permission(request)

    model_admin.has_module_permission = guarded


class AdminConfig(DjangoAdminConfig):
    """``django.contrib.admin`` with this site as its default (``INSTALLED_APPS``)."""

    default_site = "base.admin_site.AdminSite"
