//! Hash-chain validation — split out of `lib.rs` verbatim (hub#1405).

use crate::*;

/// Relee la cadena de `(hub_id, issuer_nif, environment)` (la del entorno ACTIVO de la config —
/// guarda R4) ordenada por secuencia, recomputa cada huella y
/// verifica el encadenamiento (`previous_hash` == huella anterior). Las filas `recovery` son
/// anclas de confianza (no se recomputan; su huella es el enlace para la siguiente). El
/// resultado se persiste como `verifactu_event` (`chain_validated`/`chain_error`) que la UI lee.
pub(crate) async fn validate_chain(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;
    let config = read_config(host, &ctx.hub_id).await?;
    let issuer_nif = resolve_nif(&payload, config.as_ref());
    if issuer_nif.is_empty() {
        return Err(VerifactuError::Payload(
            "falta issuer_nif del obligado (config VeriFactu → identidad fiscal)".into(),
        )
        .into());
    }

    // Guard R4 (hub#313): validate the ACTIVE environment's chain only. `production` and
    // `testing` are parallel chains with independent sequences — interleaving them by
    // sequence number would false-flag a break in two chains that are each intact.
    let environment = config
        .as_ref()
        .map(environment_of)
        .unwrap_or_else(|| "testing".to_string());
    let rows = host
        .read(
            "SELECT id, record_type, sequence_number, issuer_nif, invoice_number, invoice_date, \
             invoice_type, tax_amount, total_amount, previous_hash, record_hash, is_first_record, \
             generation_timestamp, status FROM verifactu_record \
             WHERE hub_id = :hub_id AND issuer_nif = :issuer_nif \
             AND environment = :environment AND is_deleted = 0 \
             ORDER BY sequence_number ASC",
            &params(json!({
                "hub_id": ctx.hub_id,
                "issuer_nif": issuer_nif,
                "environment": environment,
            })),
        )
        .await?;

    let mut prev_hash = String::new();
    let mut first_invalid: Option<(i64, String)> = None;
    for (idx, r) in rows.iter().enumerate() {
        let rtype = str_field(r, "record_type");
        let stored = str_field(r, "record_hash");
        // Un registro rechazado no es eslabón (`is_chainable_status`): el ancla de
        // `build_record_output` ya no cuelga de él, así que contarlo aquí marcaría rota una
        // cadena que es correcta. Ni valida su huella ni mueve `prev_hash`.
        if !is_chainable_status(&str_field(r, "status")) {
            continue;
        }
        if rtype == "recovery" {
            // Ancla de confianza: no se recomputa; su huella enlaza con la siguiente.
            prev_hash = stored;
            continue;
        }
        let rec_prev = str_field(r, "previous_hash");
        let is_first = int_field(r, "is_first_record", 0) != 0;
        let link_ok = if is_first && prev_hash.is_empty() {
            rec_prev.is_empty()
        } else {
            rec_prev == prev_hash
        };
        let computed = if rtype == "anulacion" {
            chain::anulacion_hash(
                &str_field(r, "issuer_nif"),
                &str_field(r, "invoice_number"),
                &str_field(r, "invoice_date"),
                &rec_prev,
                &str_field(r, "generation_timestamp"),
            )
        } else {
            chain::alta_hash(
                &str_field(r, "issuer_nif"),
                &str_field(r, "invoice_number"),
                &str_field(r, "invoice_date"),
                &str_field(r, "invoice_type"),
                num_field(r, "tax_amount", 0.0) / 100.0,
                num_field(r, "total_amount", 0.0) / 100.0,
                &rec_prev,
                &str_field(r, "generation_timestamp"),
            )
        };
        if (computed != stored || !link_ok) && first_invalid.is_none() {
            first_invalid = Some((
                int_field(r, "sequence_number", idx as i64),
                str_field(r, "id"),
            ));
        }
        prev_hash = stored;
    }

    let valid = first_invalid.is_none();
    let total = rows.len();
    let (severity, event_type) = if valid {
        ("info", "chain_validated")
    } else {
        ("error", "chain_error")
    };
    // hub#1103: **el veredicto dice QUÉ verificó.** «Cadena íntegra: 27 registro(s) verificados»
    // se leyó en un informe de QA como prueba de que 27 registros aritméticamente imposibles
    // estaban bien, y ante Hacienda «íntegra» significa una cosa concreta. Lo que se comprueba
    // aquí es el encadenado de HUELLAS, y eso es lo correcto: un registro ya sellado es inmutable
    // (RD 1007/2023), así que re-auditar sus importes informaría sin evitar nada — la guarda que
    // evita el daño es `audit_amounts`, antes de sellar. El alcance viaja además en
    // `details.scope` para que la UI lo diga en el idioma del usuario (ADR-0055) en vez de
    // parsear esta frase.
    let message = if valid {
        format!(
            "Cadena de huellas íntegra: {total} registro(s) con su encadenado SHA-256 verificado \
             ({issuer_nif}). No se re-auditan los importes"
        )
    } else {
        let seq = first_invalid.as_ref().map(|x| x.0).unwrap_or(0);
        format!("Cadena de huellas ROTA en la secuencia {seq} ({issuer_nif})")
    };
    let details = json!({
        "valid": valid,
        "total": total,
        "issuer_nif": issuer_nif,
        "environment": environment,
        "scope": CHAIN_VALIDATION_SCOPE,
        "first_invalid_seq": first_invalid.as_ref().map(|x| x.0),
        "first_invalid_id": first_invalid.as_ref().map(|x| x.1.clone()),
    });
    let record_id = first_invalid
        .as_ref()
        .map(|x| Json::String(x.1.clone()))
        .unwrap_or(Json::Null);
    Ok(Output::new().with_operation(op(
        "verifactu._insert_event",
        json!({
            "event_id": ctx.new_ids.first().cloned().unwrap_or_default(),
            "record_id": record_id,
            "event_type": event_type,
            "severity": severity,
            "message": message,
            // hub#1178: la clave sigue al veredicto, como ya hacía `event_type`.
            "details": details_for(
                if valid { "verifactu.chain_validated" } else { "verifactu.chain_broken" },
                details,
            ),
            "timestamp": ctx.now,
        }),
    )))
}

// ── query_aeat_records (issue verifactu#3) ────────────────────────────────────
