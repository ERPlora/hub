"""The file of a template's header, as its upload answered it."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.whatsapp_inbox import samples
from apps.whatsapp_inbox.models import TemplateSample
from apps.whatsapp_inbox.schemas.template_samples import TemplateSampleOut, TemplateSampleRefIn

SAMPLE_NOT_FOUND = _("That file is not among the business's files.")


def sample_out(sample: TemplateSample | None) -> dict | None:
    if sample is None:
        return None
    return {
        "id": sample.id,
        "header_format": sample.header_format,
        "content_type": sample.content_type,
        "size": sample.size,
        "name": sample.name,
        "url": samples.sample_url(sample.key),
    }


@operation(
    "whatsapp_inbox.template_sample.detail",
    kind="query",
    # Whoever sends chooses the file (F33), so whoever sends reads it: the assistant's card names it by this read.
    permission="whatsapp_inbox.reply",
    input=TemplateSampleRefIn,
    output=TemplateSampleOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which file is the header of that template?",
                "is the template's header a photo, a video or a PDF?",
                "how big is the header file I uploaded?",
            ),
            "es": (
                "¿qué archivo lleva de cabecera la plantilla?",
                "¿la cabecera de la plantilla es una foto, un vídeo o un PDF?",
                "¿cuánto pesa el archivo de cabecera que subí?",
            ),
        },
        "description": "One file of a WhatsApp template's header by its id (the one whatsapp_inbox.template_sample."
        "upload answered): its name, whether it is a photo, a video or a document, and its size."
    },
)
def template_sample_detail(ctx: OperationContext, data: TemplateSampleRefIn) -> dict:
    """F29, F33: a header's file as its upload answered it."""
    sample = TemplateSample.objects.filter(pk=data.id).first()
    if sample is None:
        raise NotFound(str(SAMPLE_NOT_FOUND), code="whatsapp_inbox.sample_not_found")
    return sample_out(sample)
