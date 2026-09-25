//! Numbering recovery: from the AEAT and manual — split out of `lib.rs` verbatim (hub#1405).

use crate::*;

/// Consulta a la AEAT los últimos registros del emisor y vuelca un snapshot en
/// `verifactu_aeat_record` (lo que la UI muestra como "últimos N de la Agencia Tributaria").
/// No toca la cadena local — solo trae lo que la AEAT tiene confirmado.
pub(crate) async fn query_aeat_records(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;
    let (config, issuer_nif) = consult_config(host, &ctx.hub_id, &payload).await?;
    let records = run_consult(
        host,
        &ctx.hub_id,
        &config,
        &environment_of(&config),
        &issuer_nif,
        &ctx.now,
    )
    .await?;
    let (ops, limit) = aeat_snapshot_ops(&ctx, &issuer_nif, &records);
    let mut out = Output::new();
    for o in ops {
        out = out.with_operation(o);
    }
    out = out.with_operation(op(
        "verifactu._insert_event",
        json!({
            "event_id": ctx.new_ids.get(limit).cloned().unwrap_or_default(),
            "record_id": Json::Null,
            "event_type": "aeat_queried",
            "severity": "info",
            "message": format!("Consulta AEAT: {limit} registro(s) recuperados para {issuer_nif}"),
            "details": details_for("verifactu.aeat_queried", json!({ "count": limit, "issuer_nif": issuer_nif })),
            "timestamp": ctx.now,
        }),
    ));
    Ok(out)
}

/// The config a consult made BY HAND reads, and the obligado it asks for (hub#2131).
///
/// The same defaults a transmission reads ([`transmission_config`]): a business that never saved
/// its VeriFactu settings bills on them, and asking the AEAT about its records cannot demand a
/// row its sales never needed. The registered name, when no row holds it, is the one this NIF's
/// records were sealed with — the obligado their own altas declare.
async fn consult_config(
    host: &dyn NativeHost,
    hub_id: &str,
    payload: &Json,
) -> Result<(Json, String)> {
    let config = transmission_config(host, hub_id).await?;
    let issuer_nif = resolve_nif(payload, Some(&config));
    if issuer_nif.is_empty() {
        return Err(VerifactuError::Payload(
            "falta issuer_nif del obligado (config VeriFactu → identidad fiscal)".into(),
        )
        .into());
    }
    if !obligado_name(&config).trim().is_empty() {
        return Ok((config, issuer_nif));
    }
    let sealed = host
        .read(
            "SELECT issuer_name FROM verifactu_record \
             WHERE hub_id = :hub_id AND issuer_nif = :issuer_nif AND is_deleted = 0 \
             AND issuer_name <> '' ORDER BY sequence_number DESC LIMIT 1",
            &params(json!({ "hub_id": hub_id, "issuer_nif": issuer_nif })),
        )
        .await?
        .into_iter()
        .next()
        .unwrap_or_default();
    Ok((with_obligado_name_of(&config, &sealed), issuer_nif))
}

// ── recuperación de cadena (WASM-TODO §9) ─────────────────────────────────────

/// Recupera la cadena consultando a la AEAT: vuelca el snapshot e inserta un **ancla de
/// recuperación** con la huella del registro más reciente confirmado, para que el siguiente
/// `create_record` encadene desde ahí. Operación sensible (admin) — emite `chain_recovered`.
pub(crate) async fn recover_from_aeat(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;
    let (config, issuer_nif) = consult_config(host, &ctx.hub_id, &payload).await?;
    let records = run_consult(
        host,
        &ctx.hub_id,
        &config,
        &environment_of(&config),
        &issuer_nif,
        &ctx.now,
    )
    .await?;
    if records.is_empty() {
        return Err(RuntimeError::Native(
            "la AEAT no devolvió registros para este emisor/periodo; nada que recuperar".into(),
        ));
    }
    let (ops, limit) = aeat_snapshot_ops(&ctx, &issuer_nif, &records);
    // Ancla = el registro MÁS RECIENTE por `FechaHoraHusoGenRegistro`, no el que caiga en una
    // posición: la AEAT devuelve del más nuevo al más viejo y aquí se cogía `records[0]`, que
    // acertaba por casualidad. Ver `aeat::pick_latest_record`.
    let latest = aeat::pick_latest_record(&records).ok_or_else(|| {
        RuntimeError::Native(
            "la AEAT devolvió registros pero ninguno con huella; no hay ancla que recuperar".into(),
        )
    })?;
    // Guard R4: the consult ran against the config environment's endpoint — the anchor joins
    // that environment's chain, with its own scoped sequence.
    let environment = environment_of(&config);
    let seq = next_sequence(host, &ctx.hub_id, &issuer_nif, &environment).await?;
    let record_hash = chain::normalize_hash(&latest.record_hash);
    let anchor_id = ctx.new_ids.get(limit).cloned().unwrap_or_default();
    let invoice_number = if latest.invoice_number.is_empty() {
        format!("AEAT-{}", short(&record_hash))
    } else {
        latest.invoice_number.clone()
    };

    let mut out = Output::new();
    for o in ops {
        out = out.with_operation(o);
    }
    out = out
        .with_operation(op(
            "verifactu._insert_recovery",
            json!({
                "record_id": anchor_id.clone(),
                "sequence_number": seq,
                "issuer_nif": issuer_nif.clone(),
                "issuer_name": obligado_name(&config),
                "environment": environment,
                "invoice_number": invoice_number,
                "invoice_date": iso_date(&latest.invoice_date),
                "description": "Ancla recuperada desde la AEAT (ConsultaFactuSistemaFacturacion)",
                "record_hash": record_hash.clone(),
                "aeat_csv": latest.csv.clone(),
            }),
        ))
        .with_operation(op(
            "verifactu._insert_event",
            json!({
                "event_id": ctx.new_ids.get(limit + 1).cloned().unwrap_or_default(),
                "record_id": anchor_id,
                "event_type": "chain_recovered",
                "severity": "warning",
                "message": format!("Cadena recuperada desde la AEAT para {issuer_nif}: huella {}…", short(&record_hash)),
                "details": details_for("verifactu.chain_recovered_from_aeat", json!({
                    "source": "aeat",
                    "issuer_nif": issuer_nif,
                    "record_hash": record_hash,
                    "sequence_number": seq,
                    "found": limit,
                })),
                "timestamp": ctx.now,
            }),
        ));
    Ok(out)
}

/// Continúa la cadena a partir de una huella aportada manualmente (migración de otra app):
/// valida que sea 64-hex, calcula el siguiente número de secuencia e inserta el ancla de
/// recuperación. El siguiente `create_record` encadenará desde esta huella. Emite `chain_recovered`.
pub(crate) async fn recover_manual(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;
    let config = read_config(host, &ctx.hub_id).await?;
    let issuer_nif = resolve_nif(&payload, config.as_ref());
    if issuer_nif.is_empty() {
        return Err(VerifactuError::Payload("falta issuer_nif".into()).into());
    }
    let raw_hash = str_field(&payload, "record_hash");
    if !chain::is_valid_hash(raw_hash.trim()) {
        return Err(VerifactuError::Payload(
            "record_hash debe ser 64 caracteres hexadecimales (SHA-256)".into(),
        )
        .into());
    }
    let record_hash = chain::normalize_hash(&raw_hash);
    // Guard R4: the imported anchor continues the chain of the hub's ACTIVE environment.
    let environment = config
        .as_ref()
        .map(environment_of)
        .unwrap_or_else(|| "testing".to_string());
    let seq = next_sequence(host, &ctx.hub_id, &issuer_nif, &environment).await?;
    let invoice_number = {
        let n = str_field(&payload, "invoice_number");
        if n.is_empty() {
            format!("RECOVERY-{}", short(&record_hash))
        } else {
            n
        }
    };
    let invoice_date = {
        let d = str_field(&payload, "invoice_date");
        if d.is_empty() {
            ctx.now.chars().take(10).collect::<String>()
        } else {
            d
        }
    };
    let issuer_name = config
        .as_ref()
        .as_ref()
        .map(|c| obligado_name(c))
        .unwrap_or_default();
    let anchor_id = ctx.new_ids.first().cloned().unwrap_or_default();

    Ok(Output::new()
        .with_operation(op(
            "verifactu._insert_recovery",
            json!({
                "record_id": anchor_id.clone(),
                "sequence_number": seq,
                "issuer_nif": issuer_nif.clone(),
                "issuer_name": issuer_name,
                "environment": environment,
                "invoice_number": invoice_number,
                "invoice_date": invoice_date,
                "description": "Ancla importada manualmente (migración de otra aplicación)",
                "record_hash": record_hash.clone(),
                "aeat_csv": "",
            }),
        ))
        .with_operation(op(
            "verifactu._insert_event",
            json!({
                "event_id": ctx.new_ids.get(1).cloned().unwrap_or_default(),
                "record_id": anchor_id,
                "event_type": "chain_recovered",
                "severity": "warning",
                "message": format!("Cadena continuada manualmente para {issuer_nif}: huella {}…", short(&record_hash)),
                "details": details_for("verifactu.chain_continued_manually", json!({
                    "source": "manual",
                    "issuer_nif": issuer_nif,
                    "record_hash": record_hash,
                    "sequence_number": seq,
                })),
                "timestamp": ctx.now,
            }),
        )))
}
