"""The names of the secrets the automations' calls use (``flow.secret.list``, FLOW-F26); never their
values."""

from typing import Any

from live.context import OperationContext
from live.operations import operation

from apps.flow import vault
from apps.flow.models import Secret
from apps.flow.schemas import SecretListIn, SecretPageOut

from .reads import MANAGE


def secret_row(secret: Secret) -> dict[str, Any]:
    """What is ever shown of a secret: its name and who changed it when; never its value."""
    return {
        "id": secret.id,
        "name": secret.name,
        "created_at": secret.created_at,
        "updated_at": secret.updated_at,
        "updated_by": secret.updated_by,
    }


@operation(
    "flow.secret.list",
    kind="query",
    permission=MANAGE,
    input=SecretListIn,
    output=SecretPageOut,
    ai={
        "asks": {
            "en": (
                "which secrets can my automations use?",
                "what secret names are saved for automations?",
            ),
            "es": (
                "¿qué secretos tienen guardados las automatizaciones?",
                "dime los nombres de los secretos de las automatizaciones",
            ),
        },
        "description": "The NAMES of the secrets the automations' calls to other systems can use (never their "
        "values, which nothing gives back), and whether this server can keep secrets."
    },
)
def list_secrets(ctx: OperationContext, data: SecretListIn) -> dict:
    return {
        "rows": [secret_row(secret) for secret in Secret.objects.order_by("name", "id")[:100]],
        "available": vault.available(),
    }
