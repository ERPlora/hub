"""The secrets the automations' calls use (``flow.secret.*``, FLOW-F26): saved sealed, by name, and
deleted."""

from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.flow import events, vault
from apps.flow.models import Secret
from apps.flow.queries import MANAGE, secret_row
from apps.flow.schemas import DeletedOut, SecretOut, SecretRefIn, SecretSetIn

from .writes import _actor

SECRETS_KEY_MISSING = _(
    "This server cannot keep secrets yet: its encryption key is missing. Nothing was saved."
)
SECRET_NOT_FOUND = _("There is no secret called «%(name)s».")


@operation(
    "flow.secret.set",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE,
    input=SecretSetIn,
    output=SecretOut,
    ai={
        "description": "Not an assistant tool: saves a secret (an API key, a token) by name for the automations' "
        "calls to other systems; saving a name again replaces its value. NEVER ask anybody for a secret's value in a "
        "conversation: the person types it in the automation's step, on the screen. Its value is never shown again.",
        "risk": "high",
    },
)
def set_secret(ctx: OperationContext, data: SecretSetIn) -> dict:
    try:
        sealed = vault.seal(data.value.get_secret_value())
    except vault.Unavailable:
        with translation.override(ctx.language):
            raise Conflict(str(SECRETS_KEY_MISSING), code="flow.secrets_key_missing") from None
    secret = Secret.objects.select_for_update().filter(name=data.name).first()
    if secret is None:
        secret = Secret(name=data.name, created_by=_actor(ctx))
    secret.ciphertext = sealed
    secret.updated_by = _actor(ctx)
    secret.save()
    record_event(ctx, events.SECRET_SAVED, {"id": str(secret.id)})
    return secret_row(secret)


@operation(
    "flow.secret.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE,
    input=SecretRefIn,
    output=DeletedOut,
    ai={
        "asks": {
            "en": (
                "delete the secret called SHOP_TOKEN",
                "remove the old API key secret",
            ),
            "es": (
                "borra el secreto SHOP_TOKEN",
                "elimina el secreto de la clave antigua",
            ),
        },
        "description": "Delete a secret by its name: the automations whose calls use it will fail with "
        "`flow.secret_not_found` until it is saved again.",
        "risk": "high",
    },
)
def delete_secret(ctx: OperationContext, data: SecretRefIn) -> dict:
    secret = Secret.objects.select_for_update().filter(name=data.name).first()
    if secret is None:
        with translation.override(ctx.language):
            raise NotFound(str(SECRET_NOT_FOUND) % {"name": data.name})
    gone = secret.id
    secret.delete()
    record_event(ctx, events.SECRET_DELETED, {"id": str(gone)})
    return {"id": gone}
