"""The hub's OpenAPI document, every schema named after the app that owns it: ``table.SettingsOut``.

django-ninja writes the schemas of every route into one ``components/schemas`` by class name, and a second class with
a name already taken replaces the first: two apps' ``SettingsOut`` would be one, shown on the routes of both.
"""

from django.apps import apps
from ninja import NinjaAPI
from ninja.openapi.schema import OpenAPISchema
from ninja.schema import NinjaGenerateJsonSchema
from pydantic.json_schema import CoreModeRef, DefsRef


def schema_owner(path: str) -> str:
    """The label of the app a class's dotted path is in or, outside every app, its top package (``pydantic``)."""
    config = apps.get_containing_app_config(path)
    return config.label if config else path.split(".")[0]


class OwnerNamedJsonSchema(NinjaGenerateJsonSchema):
    """ninja's JSON schema, whose definitions are named ``<owner>.<class>``."""

    def get_defs_ref(self, core_mode_ref: CoreModeRef) -> DefsRef:
        defs_ref = super().get_defs_ref(core_mode_ref)
        owner = schema_owner(core_mode_ref[0].split(":")[0])
        # pydantic picks the first of these choices that no other class of the same schema takes: the first two are
        # the class's bare name and that name with its mode; the rest spell out its module and stay as they are.
        choices = self._prioritized_defsref_choices[defs_ref]
        choices[:2] = [DefsRef(f"{owner}.{choice}") for choice in choices[:2]]
        return defs_ref


class _OwnerNamedModel:
    """One of the models ninja builds for a route, its JSON schema written by ``OwnerNamedJsonSchema``."""

    def __init__(self, model) -> None:
        self.model = model

    def __getattr__(self, name: str):
        return getattr(self.model, name)

    def model_json_schema(self, **options) -> dict:
        return self.model.model_json_schema(**{**options, "schema_generator": OwnerNamedJsonSchema})


class OwnerNamedOpenAPISchema(OpenAPISchema):
    """ninja's OpenAPI document, the schemas of its routes written by ``OwnerNamedJsonSchema``."""

    def _extract_parameters(self, model) -> list:
        return super()._extract_parameters(_OwnerNamedModel(model))

    def _create_schema_from_model(self, model, *args, **kwargs) -> tuple:
        return super()._create_schema_from_model(_OwnerNamedModel(model), *args, **kwargs)


class OwnerNamedNinjaAPI(NinjaAPI):
    """A NinjaAPI whose OpenAPI document names every schema after the app that owns it."""

    def get_openapi_schema(self, *, path_prefix: str | None = None, path_params: dict | None = None) -> OpenAPISchema:
        if path_prefix is None:
            path_prefix = self.get_root_path(path_params or {})
        return OwnerNamedOpenAPISchema(self, path_prefix)
