"""The hub's OpenAPI document names every schema after the app that owns it, so two apps' schemas never collide."""

from ninja import Router

from apps.appointment.schemas.settings import SettingsIn as AppointmentSettingsIn
from apps.cart_checkout.schemas import ItemRefIn as CartItemRefIn
from apps.demo.schemas import ItemRefIn as DemoItemRefIn
from apps.printing.schemas import DeviceOut as PrintingDeviceOut
from apps.printing.schemas import JobCreateIn
from apps.sale.schemas.settings import SettingsOut as SaleSettingsOut
from apps.table.schemas import SettingsIn as TableSettingsIn
from apps.table.schemas import SettingsOut as TableSettingsOut
from base.schemas.devices import DeviceOut as BaseDeviceOut
from config.api import build_api

REF = "#/components/schemas/"

router = Router()


@router.get("/table", response=TableSettingsOut)
def table_settings(request):
    return None


@router.get("/sale", response=SaleSettingsOut)
def sale_settings(request):
    return None


@router.get("/base-device", response=BaseDeviceOut)
def base_device(request):
    return None


@router.get("/printing-device", response=PrintingDeviceOut)
def printing_device(request):
    return None


@router.post("/cart")
def cart_item_remove(request, payload: CartItemRefIn):
    return None


@router.post("/demo")
def demo_item_delete(request, payload: DemoItemRefIn):
    return None


@router.post("/job")
def job_create(request, payload: JobCreateIn):
    return None


@router.post("/both")
def both_settings(request, table: TableSettingsIn, appointment: AppointmentSettingsIn):
    return None


probe = build_api(urls_namespace="config-test-openapi")
probe.add_router("", router)


def document() -> dict:
    return probe.get_openapi_schema(path_prefix="")


def response_ref(path: str) -> str:
    return document()["paths"][path]["get"]["responses"][200]["content"]["application/json"]["schema"]["$ref"]


def body_ref(path: str) -> str:
    return document()["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]


def test_each_route_cites_the_schema_of_its_own_app():
    assert response_ref("/table") == f"{REF}table.SettingsOut"
    assert response_ref("/sale") == f"{REF}sale.SettingsOut"
    assert body_ref("/cart") == f"{REF}cart_checkout.ItemRefIn"
    assert body_ref("/demo") == f"{REF}demo.ItemRefIn"


def test_two_apps_schemas_of_the_same_name_keep_their_own_fields():
    schemas = document()["components"]["schemas"]
    assert "timer_warning_minutes" in schemas["table.SettingsOut"]["properties"]
    assert "receipt_copies" not in schemas["table.SettingsOut"]["properties"]
    assert "item_id" in schemas["cart_checkout.ItemRefIn"]["properties"]
    assert set(schemas["demo.ItemRefIn"]["properties"]) == {"id", "called"}


def test_one_route_taking_two_apps_schemas_of_the_same_name_names_both_after_their_app():
    body = document()["paths"]["/both"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert {field["$ref"] for field in body["properties"].values()} == {
        f"{REF}table.SettingsIn",
        f"{REF}appointment.SettingsIn",
    }


def test_the_platforms_schemas_are_named_after_base_and_a_libraries_after_its_package():
    assert response_ref("/base-device") == f"{REF}base.DeviceOut"
    assert response_ref("/printing-device") == f"{REF}printing.DeviceOut"
    assert "pydantic.JsonValue" in document()["components"]["schemas"]
