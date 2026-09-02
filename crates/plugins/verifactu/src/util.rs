//! Small shared helpers: field readers, params/op builders, request context — split out of `lib.rs` verbatim (hub#1405).

use crate::*;

pub(crate) fn str_field(v: &Json, k: &str) -> String {
    v.get(k)
        .and_then(|x| x.as_str())
        .unwrap_or_default()
        .to_string()
}

pub(crate) fn num_field(v: &Json, k: &str, default: f64) -> f64 {
    match v.get(k) {
        Some(Json::Number(n)) => n.as_f64().unwrap_or(default),
        Some(Json::String(s)) => s.trim().parse().unwrap_or(default),
        _ => default,
    }
}

pub(crate) fn int_field(v: &Json, k: &str, default: i64) -> i64 {
    match v.get(k) {
        Some(Json::Number(n)) => n.as_i64().unwrap_or(default),
        Some(Json::String(s)) => s.trim().parse().unwrap_or(default),
        _ => default,
    }
}

/// Derives the **TipoImpositivo** (VAT %) of the record's `tax_rate` COLUMN from the invoice's
/// real breakdown. The row carries a single rate, so:
/// - If the breakdown declares **one single rate** → THAT exact rate is used (the normal POS case).
/// - If it declares **several distinct rates** (mixed invoice 21 %+10 %) or none at all (empty,
///   unreadable, amounts that cannot be read) → **effective rate** `tax/base*100` at 2 decimals.
///
/// The breakdown is read through `aeat::breakdown_rates`, the SAME parser the XML is built from:
/// it understands both generations of the contract with `invoice` — the old rate-keyed map
/// (`{"21.00":{base,tax}}`) and the live array with one entry per full tax key (ADR-0186). Reading
/// it through a private copy that only saw the map made EVERY real ticket fall through to the
/// effective rate, and with `invoice`'s per-line rounding the effective rate is not a Spanish rate:
/// 4 lines of 0,50 € at 21 % (base 200 / quota 44) were stored as 22,0 % (hub#1198). The XML never
/// depended on this — `aeat::desglose` emits one line per real rate — but the column the KPIs
/// group by did, and so did the module's row rule (`ck_verifactu_record_quota_matches_row_rate`),
/// which with the effective rate balanced by construction and therefore measured nothing.
///
/// **Mixed: the effective rate stays on purpose.** There is no «the rate» of such a row, and
/// taking the first entry's would invent a fiscal fact. The whole breakdown travels to the XML
/// anyway. Several entries declaring the SAME rate (the same tax key repeated, or an equivalence
/// surcharge, which travels in its own pair) do have a single rate, and that one is stored.
pub(crate) fn derive_tax_rate(tax_breakdown: &str, base_cents: f64, tax_cents: f64) -> f64 {
    let declared = aeat::breakdown_rates(tax_breakdown);
    if let Some(first) = declared.first() {
        if declared.iter().all(|rate| rate == first) {
            return *first;
        }
    }
    // Fallback (multi-rate or no readable breakdown): effective rate rounded to 2 decimals. The
    // division keeps the sign in rectifying invoices (negative base and quota → positive ratio).
    if base_cents != 0.0 {
        (tax_cents / base_cents * 10_000.0).round() / 100.0
    } else {
        0.0
    }
}

pub(crate) struct Ctx {
    pub(crate) hub_id: String,
    pub(crate) now: String,
    pub(crate) new_ids: Vec<String>,
}

pub(crate) fn split_input(input: &Json) -> Result<(Json, Ctx)> {
    let payload = input.get("payload").cloned().unwrap_or(Json::Null);
    let context = input.get("context").cloned().unwrap_or(Json::Null);
    let hub_id = str_field(&context, "hub_id");
    if hub_id.is_empty() {
        return Err(RuntimeError::Native("input sin context.hub_id".into()));
    }
    let new_ids = context
        .get("new_ids")
        .and_then(|v| v.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|x| x.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default();
    let now = chain::format_timestamp(&str_field(&context, "now"));
    Ok((
        payload,
        Ctx {
            hub_id,
            now,
            new_ids,
        },
    ))
}

pub(crate) fn params(pairs: Json) -> Params {
    pairs.as_object().cloned().unwrap_or_default()
}

pub(crate) fn op(command: &str, p: Json) -> Operation {
    Operation::sql(command, params(p))
}

/// `details` de una fila de auditoría, con su **clave de mensaje estable** delante (hub#1178).
///
/// Todo el corpus de `verifactu_event.message` que escribe este motor nace en español y en duro, y
/// la pantalla **Eventos** del módulo lo pinta tal cual: un hub que no esté en castellano lee su
/// auditoría fiscal en castellano igual. El canal para arreglarlo es el que hub#1103 abrió con
/// `details.scope` — **un código estable dentro de `details`**, con los datos que la frase necesita
/// al lado — y el catálogo `en`+`es` en quien la pinta (ADR-0055: el inglés es la fuente).
///
/// `message` sigue viajando y sigue en español **a propósito**: es lo que la pantalla lee HOY, y
/// cambiarlo antes de que exista el catálogo pondría inglés delante de un usuario español — que es
/// exactamente el defecto de hub#1190. Deja de importar el día que el módulo componga la frase.
pub(crate) fn details_for(message_key: &str, extra: Json) -> String {
    let mut details = json!({ "message_key": message_key });
    if let (Some(target), Some(source)) = (details.as_object_mut(), extra.as_object()) {
        for (key, value) in source {
            target.insert(key.clone(), value.clone());
        }
    }
    details.to_string()
}
