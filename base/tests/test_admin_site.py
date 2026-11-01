"""The Hub admin's site (``base.admin_site``): without a business chosen it works on control and shows only control's
models; a hub's model lives in a business's own database (S5: there is no shared one), so its pages appear once one
is chosen (``/admin/hub/<slug>/``)."""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model

from base.admin_site import AdminSite
from base.tenancy import context
from base.tenancy.tests import hubs

PLATFORM_HOST = "hubs.localhost"

pytestmark = pytest.mark.usefixtures("no_test_fallback")


def superuser(client):
    client.force_login(get_user_model().objects.create_superuser("root", "root@example.com", "pw"))


def test_the_admin_runs_on_the_hub_s_own_site():
    assert isinstance(admin.site._wrapped if hasattr(admin.site, "_wrapped") else admin.site, AdminSite)


@pytest.mark.django_db
def test_without_a_business_chosen_the_index_lists_control_s_models_only(client):
    superuser(client)

    page = client.get("/admin/", HTTP_HOST=PLATFORM_HOST)

    assert page.status_code == 200
    listed = {model["object_name"] for app in page.context["app_list"] for model in app["models"]}
    assert {"Hub", "Membership", "User"} <= listed
    assert not {"TaxSettings", "Item", "AppActivation"} & listed


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
def test_with_a_business_chosen_its_models_are_listed_too(client, hub_a):
    superuser(client)
    client.get(f"/admin/hub/{hub_a.slug}/", HTTP_HOST=PLATFORM_HOST)

    page = client.get("/admin/", HTTP_HOST=PLATFORM_HOST)

    assert page.status_code == 200
    listed = {model["object_name"] for app in page.context["app_list"] for model in app["models"]}
    assert {"Hub", "TaxSettings", "Item"} <= listed
    assert context.serves_hubs_without_database() is False
