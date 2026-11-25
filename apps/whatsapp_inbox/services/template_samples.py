"""The file a template's header carries (WHATSAPP_INBOX-F29, F33): uploaded to the business's
file store, checked for a type and a size Meta takes."""

import base64
import binascii
import hashlib

from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload, OperationError
from live.operations import operation
from live.outbox import record_event

from apps.whatsapp_inbox import events, samples
from apps.whatsapp_inbox.models import TemplateSample
from apps.whatsapp_inbox.queries.template_samples import sample_out
from apps.whatsapp_inbox.schemas.template_samples import TemplateSampleOut, TemplateSampleUploadIn
from base.files.store import STORE_ERRORS
from base.operations import hub_id
from base.queries.files import refuse_past_the_plans_space

SAMPLE_NOT_WHOLE = _("The file did not arrive whole. Choose it again.")
SAMPLE_WRONG_TYPE = {
    "IMAGE": _("Choose a JPEG or PNG photo."),
    "VIDEO": _("Choose an MP4 video."),
    "DOCUMENT": _("Choose a PDF document."),
}
SAMPLE_TOO_HEAVY = _("This file weighs more than %(mb)s MB: choose a lighter one.")
SAMPLE_NOT_KEPT = _("The file could not be kept: the business's file store did not answer. Try again in a moment.")


def _sample_bytes(data: TemplateSampleUploadIn) -> tuple[bytes, str]:
    """The file and its type, if it is one Meta takes for its header; else the refusal under its field."""

    def refuse(message) -> InvalidPayload:
        return InvalidPayload(str(message), fields={"content_base64": str(message)})

    try:
        content = base64.b64decode(data.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise refuse(SAMPLE_NOT_WHOLE) from None
    kind = samples.sniff(content[:16])
    if kind is None or kind[0] != data.header_format:
        raise refuse(SAMPLE_WRONG_TYPE[data.header_format])
    limit = samples.MAX_BYTES[data.header_format]
    if len(content) > limit:
        raise refuse(SAMPLE_TOO_HEAVY % {"mb": limit // samples.MB})
    return content, kind[1]


@operation(
    "whatsapp_inbox.template_sample.upload",
    kind="command",
    # Whoever sends chooses the file (F33: a template from WhatsApp Manager asks for it), not only who configures.
    permission="whatsapp_inbox.reply",
    input=TemplateSampleUploadIn,
    output=TemplateSampleOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "use this photo as a WhatsApp template header",
                "upload this PDF for the template's header",
                "keep this video for the header of the template",
            ),
            "es": (
                "esta foto es para la cabecera de la plantilla de WhatsApp",
                "sube este PDF para la cabecera de la plantilla",
                "quiero este vídeo arriba en la plantilla de WhatsApp",
            ),
        },
        "description": "Keeps the file of a WhatsApp template's header the person attached (a JPEG or PNG photo up "
        "to 5 MB, an MP4 video up to 16 MB or a PDF up to 25 MB) and answers its id, to give as header_sample when "
        "creating or changing the template: Meta reviews the template with it.",
        "risk": "normal",
    },
)
def upload_sample(ctx: OperationContext, data: TemplateSampleUploadIn) -> dict:
    """F29: keep the header's file in the hub's store, named by its content (``samples.sample_key``)."""
    content, content_type = _sample_bytes(data)
    sha = hashlib.sha256(content).hexdigest()
    key = samples.sample_key(hub_id(ctx.scope), sha, content_type)
    store = storages["hub_files"]
    try:
        if not store.exists(key):
            # A new file takes the plan's space through Files' own check (the same file again is the same object).
            refuse_past_the_plans_space(ctx, store, len(content))
            key = store.save(key, ContentFile(content))
    except STORE_ERRORS as exc:
        raise OperationError(str(SAMPLE_NOT_KEPT), code="whatsapp_inbox.sample_not_kept", status=503) from exc
    row = TemplateSample.objects.create(
        header_format=data.header_format,
        key=key,
        sha256=sha,
        content_type=content_type,
        size=len(content),
        name=data.name,
    )
    record_event(ctx, events.TEMPLATE_SAMPLE_UPLOADED, {"id": str(row.id)})
    return sample_out(row)
