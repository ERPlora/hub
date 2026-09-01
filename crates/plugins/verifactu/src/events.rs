//! Event names, reason codes and the failure payload — split out of `lib.rs` verbatim (hub#1405).

use crate::*;

/// Transmite un registro a la AEAT: XML SOAP + identidad PKCS#12 + POST TLS-mutua al
/// endpoint del entorno configurado (`testing` = default). Respuesta → UPDATE del
/// registro (accepted/rejected/error) + evento; fallo de red → cola de contingencia
/// con backoff exponencial (5,10,20,40,60 min cap).
/// **The public event a failed outcome emits** (verifactu#42).
///
/// One name for «this invoice did not get through and somebody has to look at it», whichever way
/// it failed — the AEAT refusing it, the wire never carrying it, the record not knowing which tax
/// agency owns it, the XML not passing the schema. `reason` tells them apart.
///
/// **One and not four**, because a trigger picks ONE event: an owner who builds «warn me when
/// something fiscal fails» and gets only the AEAT half has built the silent version of the alarm
/// they asked for. An operator who wants a single flavour filters on `reason`, which is a
/// condition step; an owner who wants all of them does nothing, which is the right default for
/// the person who loses money when it goes unnoticed.
pub const EVENT_RECORD_REJECTED: &str = "verifactu.record.rejected";

/// **Registered at the AEAT, with an error noted on it** (ADR-0189) — deliberately NOT a rejection.
///
/// Resending it is a duplicate and the AEAT refuses it (3000), so calling it a failure would send
/// the owner chasing an invoice that is already filed. But nobody opens the VeriFactu screen, and
/// an accepted-with-errors that nobody reads is a latent problem — so it gets its own word.
pub const EVENT_RECORD_ACCEPTED_WITH_ERRORS: &str = "verifactu.record.accepted_with_errors";

/// The AEAT answered, and its answer was no.
pub const REASON_AEAT_REJECTED: &str = "aeat_rejected";

/// The message never reached the AEAT (TLS, DNS, the agency down). It is queued for contingency.
pub const REASON_TRANSMISSION_FAILED: &str = "transmission_failed";

/// The record cannot say which tax agency owns it, so nothing was built and nothing was sent.
/// Same key as `Refusal::environment_unknown`, and on purpose: the refusal's stable code IS the
/// event's reason, so the panel and the automation never disagree about what went wrong.
pub const REASON_ENVIRONMENT_UNKNOWN: &str = "record_environment_unknown";

/// The envelope could not be built — an amount is missing or unreadable (hub#324). Retryable: the
/// fix is upstream data, and the record keeps its place in the queue.
pub const REASON_RECORD_NOT_DECLARABLE: &str = "record_not_declarable";

/// The XML does not meet the AEAT schema; refused locally rather than burning a chain number.
pub const REASON_XSD_INVALID: &str = "xsd_invalid";

// ── hub#1104 · la degradación de tipo deja de ser muda ────────────────────────

/// `verifactu_event.event_type` of the row that records a **downgrade of the invoice type**
/// (hub#1104).
///
/// The downgrade itself is right: an `F1` with no identified recipient travels without the
/// `Destinatarios` block and the AEAT refuses it with **1189** — after the chain number has been
/// spent. Doing it in silence is not: the document the customer took away says `F1` and the record
/// filed with the tax agency says `F2`, and nothing on any screen tells the business the two
/// disagree. ADR-0140 says fiscal state is derived, never mutated without a trace.
pub const EVENT_TYPE_INVOICE_TYPE_DOWNGRADED: &str = "invoice_type_downgraded";

/// Why the type was downgraded. Stable machine code so the screen and any automation agree, and
/// so the UI can translate the sentence instead of parsing prose (ADR-0055).
pub const REASON_MISSING_RECIPIENT: &str = "missing_recipient_aeat_1189";

/// `details.scope` of the `chain_validated`/`chain_error` event (hub#1103).
///
/// `chain.validate` recomputes SHA-256 fingerprints and verifies the chaining — and **nothing
/// else**. That is deliberate: a sealed record is immutable (RD 1007/2023), so re-auditing its
/// amounts there would inform, not prevent. What WAS a defect is a verdict that read like a
/// judgement on the amounts; the scope now travels as a stable field the UI can translate
/// (the module's `ui.recChainScope`, `en` + `es`).
pub const CHAIN_VALIDATION_SCOPE: &str = "hash_chain";

/// The public payload of a failed outcome. **Closed set, and nothing fiscal in it**: it ends up in
/// somebody's task list and in a message, so it carries what is needed to say «check invoice X»
/// and no more — never the signed XML, the chain hash, the NIF, the amounts or the CSV.
pub(crate) fn failure_payload(
    record: &Json,
    reason: &str,
    status: &str,
    code: &str,
    message: &str,
    environment: &str,
) -> Json {
    json!({
        "record_id": str_field(record, "id"),
        "invoice_number": str_field(record, "invoice_number"),
        "status": status,
        "reason": reason,
        "error_code": code,
        "error_message": message,
        "environment": environment,
    })
}
