"""The chains of an issuer (``verifactu.chain.status``): their last record and the last validation's verdict."""

from live.context import OperationContext
from live.operations import operation

from apps.verifactu.models import Chain
from apps.verifactu.schemas.chains import ChainOut, ChainStatusOut
from apps.verifactu.schemas.fields import IssuerIn

from .reads import VIEW
from .route import config_row, issuer_identity


def chain_out(head: Chain) -> ChainOut:
    return ChainOut(
        issuer_nif=head.issuer_nif,
        environment=head.environment,
        sequence=head.sequence,
        last_number=head.last_number,
        last_issue_date=head.last_issue_date,
        last_fingerprint=head.last_fingerprint,
        anchored_at=head.anchored_at,
        anchor_source=head.anchor_source,
        validated_at=head.validated_at,
        valid=head.validation_valid,
        total=head.validation_total,
        first_invalid_sequence=head.validation_first_invalid,
    )


@operation(
    "verifactu.chain.status",
    kind="query",
    permission=VIEW,
    input=IssuerIn,
    output=ChainStatusOut,
    ai={
        "description": "The VeriFactu chains of an issuer (Invoicing's issuer by default): last sequence, last "
        "fingerprint, anchors and the last validation's verdict.",
        "asks": {
            "en": (
                "how is the VeriFactu chain doing?",
                "what is the current fingerprint and sequence?",
            ),
            "es": (
                "¿cómo va la cadena de VeriFactu?",
                "¿cuál es la huella actual y en qué secuencia vamos?",
            ),
        },
    },
)
def chain_status(ctx: OperationContext, data: IssuerIn) -> ChainStatusOut:
    nif = data.issuer_nif or issuer_identity()[0]
    chains = Chain.objects.filter(issuer_nif=nif).order_by("environment")
    return ChainStatusOut(
        issuer_nif=nif,
        environment=config_row().environment,
        chains=[chain_out(head) for head in chains],
    )
