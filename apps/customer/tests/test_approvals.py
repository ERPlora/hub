"""What a manager holds in Customers, an employee does with a manager's PIN on the spot (BASE-F84; the old customers
module's rule: «what the manager has, another profile may do with a manager's approval (PIN); what is the
administrator's only, not; export is not in this rule»): CUSTOMER-F13 (merge two cards) and CUSTOMER-F27–F29 (create
and change groups and tags, create, change and delete custom fields).

The app names those commands in its ``LiveAppConfig.approvals``; the employee who asks gets «An approval is needed»
(``requires_elevation``) instead of a flat refusal, a manager approves that very request with their PIN and it is done
once. Deleting cards, groups and tags and erasing personal data stay the administrator's: a flat refusal, never a
question. Exporting is a read, never approved. Over HTTP, as the screen asks: the approval's door sits in front of the
routes (``base.approvals``).
"""

import json

import pytest
from django.apps import apps
from django.core.cache import cache
from django.utils import translation

from apps.customer.models import Customer, CustomerGroup, CustomField, CustomerTag
from base.models import Credential
from base.tests.test_people import with_pin

pytestmark = pytest.mark.django_db

HOST = "a.localhost"

#: The commands a manager may approve, and what the dialog says is approved, in English and in Spanish.
APPROVABLE = {
    "customer.customer.merge": ("Merge two customer cards", "Fusionar dos fichas de cliente"),
    "customer.group.create": ("Create a customer group", "Crear un grupo de clientes"),
    "customer.group.update": ("Change a customer group", "Cambiar un grupo de clientes"),
    "customer.tag.create": ("Create a customer tag", "Crear una etiqueta de clientes"),
    "customer.tag.update": ("Change a customer tag", "Cambiar una etiqueta de clientes"),
    "customer.field.create": ("Create a custom field", "Crear un campo personalizado"),
    "customer.field.update": ("Change a custom field", "Cambiar un campo personalizado"),
    "customer.field.delete": ("Delete a custom field", "Eliminar un campo personalizado"),
}


def post(client, path, data, **headers):
    return client.post(f"/api{path}", json.dumps(data), content_type="application/json", HTTP_HOST=HOST, **headers)


def code(response) -> str:
    return response.json()["error"]["code"]


def asked(response) -> dict:
    """The approval's question in a refusal: 403 ``requires_elevation`` with what is approved."""
    assert response.status_code == 403, response.content
    assert code(response) == "requires_elevation", response.content
    return response.json()["error"]["approval"]


def approve(client, question: dict, person: str = "mario", pin: str = "1357") -> str:
    """``person`` approves ``question`` with their PIN on the employee's device: the pass of one use."""
    credential = str(Credential.objects.get(username=person).pk)
    body = {"operation": question["operation"], "fingerprint": question["fingerprint"], "person": credential, "pin": pin}
    response = post(client, "/approvals", body)
    assert response.status_code == 200, response.content
    return response.json()["token"]


def through_approval(client, path: str, data: dict):
    """The employee asks, the manager approves with their PIN, the employee's very request goes again with the pass."""
    question = asked(post(client, path, data))
    return post(client, path, data, HTTP_X_ELEVATION_TOKEN=approve(client, question))


@pytest.fixture(autouse=True)
def no_brakes():
    """The PIN pad's brakes live in the cache: each test starts without the attempts of another."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def employee(client, make_user):
    """Eva, an employee on the shop's device, with Mario, a manager with a PIN, there to approve."""
    make_user("mario", role="hub_manager")
    with_pin("mario", "1357")
    client.force_login(make_user("eva", role="hub_employee"))
    return client


def test_the_app_names_what_a_manager_may_approve_in_both_languages():
    config = apps.get_app_config("customer")
    assert set(config.approvals) == set(APPROVABLE)
    for name, (english, spanish) in APPROVABLE.items():
        with translation.override("en"):
            assert str(config.approvals[name]) == english
        with translation.override("es"):
            assert str(config.approvals[name]) == spanish


def test_an_employee_merges_two_cards_with_a_manager_s_pin(employee):
    stays = Customer.objects.create(name="Ana García")
    duplicate = Customer.objects.create(name="Ana Garcia")
    data = {"id": str(stays.id), "absorbed_id": str(duplicate.id)}
    question = asked(post(employee, "/customer/customers/merge", data))
    assert question["operation"] == "customer.customer.merge"
    response = post(employee, "/customer/customers/merge", data, HTTP_X_ELEVATION_TOKEN=approve(employee, question))
    assert response.status_code == 200, response.content
    duplicate.refresh_from_db()
    assert duplicate.merged_into_id == stays.id


def test_an_employee_creates_and_changes_a_group_and_a_tag_with_a_manager_s_pin(employee):
    assert through_approval(employee, "/customer/groups", {"name": "Regulars"}).status_code == 201
    group = CustomerGroup.objects.get(name="Regulars")
    response = through_approval(employee, "/customer/groups/update", {"id": str(group.id), "name": "Usuals"})
    assert response.status_code == 200, response.content
    assert through_approval(employee, "/customer/tags", {"name": "Allergic"}).status_code == 201
    tag = CustomerTag.objects.get(name="Allergic")
    assert through_approval(employee, "/customer/tags/update", {"id": str(tag.id), "name": "Nuts"}).status_code == 200
    group.refresh_from_db()
    tag.refresh_from_db()
    assert (group.name, tag.name) == ("Usuals", "Nuts")


def test_an_employee_creates_changes_and_deletes_a_custom_field_with_a_manager_s_pin(employee):
    created = through_approval(employee, "/customer/fields", {"name": "Shoe size", "field_type": "number"})
    assert created.status_code == 201, created.content
    field = CustomField.objects.get(name="Shoe size")
    assert through_approval(employee, "/customer/fields/update", {"id": str(field.id), "sort_order": 3}).status_code == 200
    assert through_approval(employee, "/customer/fields/delete", {"id": str(field.id)}).status_code == 200
    assert not CustomField.objects.filter(pk=field.pk).exists()


def test_a_pass_lets_through_one_request_only(employee):
    data = {"name": "Regulars"}
    token = approve(employee, asked(post(employee, "/customer/groups", data)))
    assert post(employee, "/customer/groups", data, HTTP_X_ELEVATION_TOKEN=token).status_code == 201
    assert code(post(employee, "/customer/groups", {"name": "Others"}, HTTP_X_ELEVATION_TOKEN=token)) == "requires_elevation"


@pytest.mark.parametrize(
    ("path", "build"),
    [
        ("/customer/customers/delete", lambda: {"id": str(Customer.objects.create(name="Ana").id)}),
        ("/customer/customers/erase", lambda: {"id": str(Customer.objects.create(name="Ana").id)}),
        ("/customer/groups/delete", lambda: {"id": str(CustomerGroup.objects.create(name="VIP").id)}),
        ("/customer/tags/delete", lambda: {"id": str(CustomerTag.objects.create(name="VIP").id)}),
    ],
)
def test_what_only_an_administrator_does_is_refused_never_asked(employee, path, build):
    response = post(employee, path, build())
    assert response.status_code == 403, response.content
    assert code(response) != "requires_elevation"


def test_exporting_is_a_read_and_is_never_approved(employee):
    response = employee.get("/api/customer/customers/export", HTTP_HOST=HOST)
    assert response.status_code == 403, response.content
    assert code(response) != "requires_elevation"


def test_a_manager_is_never_asked(client, make_user):
    client.force_login(make_user("mario", role="hub_manager"))
    assert post(client, "/customer/groups", {"name": "Regulars"}).status_code == 201
