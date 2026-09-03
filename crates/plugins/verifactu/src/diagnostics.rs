//! Diagnostics run and AEAT consult snapshot — split out of `lib.rs` verbatim (hub#1405).

use crate::*;

/// Prueba de extremo a extremo SIN tocar la cadena: verifica que el certificado carga con su
/// contraseña, genera una huella + QR de un registro de **muestra** y (si el cert es válido) hace
/// un envío de prueba a la AEAT, devolviendo la respuesta. Persiste SOLO un evento `diagnostic`
/// (no inserta ningún `verifactu_record`); la UI lo lee con `verifactu.diagnostics.last`.
pub(crate) async fn run_diagnostics(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;
    let config = read_config(host, &ctx.hub_id).await?.ok_or_else(|| {
        RuntimeError::Native("VeriFactu sin configurar (verifactu.config.save)".into())
    })?;

    // OBLIGADO tributario (emisor) = el NIF que la AEAT valida y que representa el certificado.
    // NO es el productor del software (software_*). Para la prueba viene de la config (issuer_*).
    let issuer_nif = str_field(&config, "issuer_nif");
    let issuer_name = {
        let n = str_field(&config, "issuer_name");
        if n.is_empty() {
            issuer_nif.clone()
        } else {
            n
        }
    };
    let environment = environment_of(&config);
    let gen_ts = chain::format_timestamp(&ctx.now);
    let sample_date: String = ctx.now.chars().take(10).collect();
    let sample_number = format!("PRUEBA-{sample_date}");

    // Tipo de factura de la prueba (lo elige la UI). Default **F2** = tiquet simplificado, que NO
    // requiere destinatario. F1/F3/R1-R4 SÍ exigen el bloque Destinatarios (error AEAT 1189): para
    // esos tipos se usa un cliente de muestra si la UI no manda uno.
    let invoice_type = {
        let t = str_field(&payload, "invoice_type");
        if INVOICE_TYPES.contains(&t.as_str()) {
            t
        } else {
            "F2".to_string()
        }
    };
    let needs_recipient = matches!(
        invoice_type.as_str(),
        "F1" | "F3" | "R1" | "R2" | "R3" | "R4"
    );
    let recipient_nif = {
        let n = str_field(&payload, "recipient_nif");
        if !n.is_empty() {
            n
        } else if needs_recipient {
            "12345678Z".to_string()
        } else {
            String::new()
        }
    };
    let recipient_name = {
        let n = str_field(&payload, "recipient_name");
        if !n.is_empty() {
            n
        } else if needs_recipient {
            "Cliente de Prueba".to_string()
        } else {
            String::new()
        }
    };

    // Importes de muestra (céntimos): base 100,00 € · IVA 21% · total 121,00 €.
    let huella = chain::alta_hash(
        &issuer_nif,
        &sample_number,
        &sample_date,
        &invoice_type,
        21.0,
        121.0,
        "",
        &gen_ts,
    );
    let qr_url = chain::qr_url(
        &issuer_nif,
        &sample_number,
        &sample_date,
        121.0,
        &environment,
    );

    let mut cert_ok = false;
    let cert_message;
    let mut aeat = Json::Null;

    // Identity mTLS vía `build_identity`: cert del core (opaca, la cripto vive en el core) o
    // legacy. Para el cert del core NO se cargan los bytes del `.p12` en el módulo (ADR-0079).
    match build_identity(host, &ctx.hub_id, &config).await {
        Ok(identity) => {
            cert_ok = true;
            cert_message = "Certificado cargado correctamente.".into();
            if issuer_nif.is_empty() {
                // Sin NIF del obligado no se puede enviar (la AEAT lo rechazaría por formato).
                aeat = json!({ "ok": false, "error": "Configura el NIF del obligado tributario (emisor) antes de enviar la prueba." });
            } else {
                // Envío de prueba real al endpoint AEAT del entorno configurado.
                let sample = json!({
                    "record_type": "alta",
                    "issuer_nif": issuer_nif,
                    "issuer_name": issuer_name,
                    "invoice_number": sample_number,
                    "invoice_date": sample_date,
                    "invoice_type": invoice_type,
                    "description": "Factura de PRUEBA (diagnóstico VeriFactu)",
                    "tax_rate": 21,
                    "tax_breakdown": r#"{"21.00":{"base":10000,"tax":2100}}"#,
                    "base_amount": 10000,
                    "tax_amount": 2100,
                    "total_amount": 12100,
                    "recipient_nif": recipient_nif,
                    "recipient_name": recipient_name,
                    "record_hash": huella,
                    "is_first_record": 1,
                    "generation_timestamp": gen_ts,
                });
                // Mismo gate que la transmisión real: la prueba tiene que fallar donde falla el
                // envío de verdad, no ir a la AEAT a que lo diga con un 4102. Y si el sobre ni
                // siquiera se puede construir (hub#324), el diagnóstico lo dice aquí.
                let built = aeat::build_soap(&sample, &config, None, &ctx.hub_id);
                let checked = built.as_ref().map_err(ToString::to_string).and_then(|xml| {
                    xsd::validate_registro(xml)
                        .map(|()| xml.as_str())
                        .map_err(|e| format!("XML no conforme al esquema: {e}"))
                });
                match checked {
                    Err(error) => aeat = json!({ "ok": false, "error": error }),
                    Ok(xml) => {
                        match aeat::post_soap(transmission_endpoint(&config), identity, xml).await {
                            Ok(body) => {
                                let r = aeat::parse_response(&body);
                                let accepted = r.estado_registro == "Correcto"
                                    || r.estado_registro == "AceptadoConErrores"
                                    || r.estado_envio == "Correcto";
                                aeat = json!({
                                    "ok": accepted,
                                    "estado_envio": r.estado_envio,
                                    "estado_registro": r.estado_registro,
                                    "csv": r.csv,
                                    "codigo_error": r.codigo_error,
                                    "descripcion_error": r.descripcion_error,
                                });
                            }
                            Err(e) => {
                                aeat = json!({ "ok": false, "error": e.to_string() });
                            }
                        }
                    }
                }
            }
        }
        Err(e) => {
            cert_message = format!("El certificado no carga o no está configurado: {e}");
        }
    }

    let details = json!({
        "cert_ok": cert_ok,
        "cert_message": cert_message,
        "issuer_nif": issuer_nif,
        "invoice_type": invoice_type,
        "recipient_nif": recipient_nif,
        "environment": environment,
        "sample_number": sample_number,
        "huella": huella,
        "qr_url": qr_url,
        "aeat": aeat,
    });
    Ok(Output::new().with_operation(op(
        "verifactu._insert_event",
        json!({
            "event_id": ctx.new_ids.first().cloned().unwrap_or_default(),
            "record_id": Json::Null,
            "event_type": "diagnostic",
            "severity": if cert_ok { "info" } else { "warning" },
            "message": if cert_ok {
                format!("Prueba VeriFactu ejecutada ({environment})")
            } else {
                "Prueba VeriFactu: certificado no válido".to_string()
            },
            // hub#1178: dos hechos distintos, dos claves — «la prueba corrió» y «el certificado no
            // vale» piden cosas distintas de quien lo lee.
            "details": details_for(
                if cert_ok { "verifactu.diagnostic_ran" } else { "verifactu.diagnostic_certificate_invalid" },
                details,
            ),
            "timestamp": ctx.now,
        }),
    )))
}

// ── helpers de recuperación / consulta ────────────────────────────────────────

/// NIF del **obligado tributario** a usar: el del payload o, si falta, el `issuer_nif` de la
/// config.
///
/// Ya **no** cae a `software_nif`: ese es el NIF del PRODUCTOR del software (ERPlora), y usarlo
/// como emisor anclaría la cadena de un cliente a la identidad fiscal de ERPlora. Sin NIF del
/// obligado la operación falla, que es lo correcto: no hay cadena que consultar ni recuperar.
pub(crate) fn resolve_nif(payload: &Json, config: Option<&Json>) -> String {
    let n = str_field(payload, "issuer_nif");
    if !n.is_empty() {
        return n;
    }
    config
        .map(|c| str_field(c, "issuer_nif"))
        .unwrap_or_default()
}

/// Entorno AEAT efectivo (`testing` por defecto).
pub(crate) fn environment_of(config: &Json) -> String {
    let e = str_field(config, "environment");
    if e.is_empty() {
        "testing".to_string()
    } else {
        e
    }
}

/// (Ejercicio=YYYY, Periodo=MM) del `now` RFC3339 para el filtro de consulta AEAT.
pub(crate) fn year_month(now: &str) -> (String, String) {
    match chrono::DateTime::parse_from_rfc3339(now) {
        Ok(dt) => (dt.format("%Y").to_string(), dt.format("%m").to_string()),
        Err(_) => (String::new(), String::new()),
    }
}

/// AEAT devuelve fechas en `DD-MM-YYYY`; la BD usa ISO `YYYY-MM-DD`.
pub(crate) fn iso_date(aeat_date: &str) -> String {
    let p: Vec<&str> = aeat_date.split('-').collect();
    if p.len() == 3 && p[0].len() == 2 {
        format!("{}-{}-{}", p[2], p[1], p[0])
    } else {
        aeat_date.to_string()
    }
}

/// Primeros 8 caracteres de una huella (para mensajes).
pub(crate) fn short(hash: &str) -> String {
    hash.chars().take(8).collect()
}

/// Next internal sequence number for `(hub_id, issuer_nif, environment)` = max + 1.
/// Scoped per AEAT environment (guard R4): each chain numbers its own records.
pub(crate) async fn next_sequence(
    host: &dyn NativeHost,
    hub_id: &str,
    issuer_nif: &str,
    environment: &str,
) -> Result<i64> {
    let rows = host
        .read(
            "SELECT sequence_number FROM verifactu_record \
             WHERE hub_id = :hub_id AND issuer_nif = :issuer_nif \
             AND environment = :environment AND is_deleted = 0 \
             ORDER BY sequence_number DESC LIMIT 1",
            &params(json!({
                "hub_id": hub_id,
                "issuer_nif": issuer_nif,
                "environment": environment,
            })),
        )
        .await?;
    Ok(rows
        .first()
        .map(|r| int_field(r, "sequence_number", 0))
        .unwrap_or(0)
        + 1)
}

/// Razón social del **OBLIGADO tributario** (el negocio del hub), que es lo que la AEAT valida
/// contra el NIF del certificado.
///
/// No es `software_name`: ese es el PRODUCTOR del software (ERPlora), fijo para todos los hubs.
/// El envelope de consulta llevaba el nombre del productor junto al NIF del negocio — dos
/// identidades distintas en el mismo `ObligadoEmision`, que la AEAT rechaza.
pub(crate) fn obligado_name(config: &Json) -> String {
    str_field(config, "issuer_name")
}

/// Consulta a la AEAT los registros del emisor en el periodo actual y los parsea, **por la vía
/// que este hub tenga** (ADR-0320, hub#1436). Red real — sin vía ni red devuelve error, nunca
/// silencioso.
///
/// El `environment` es un parámetro y no se deriva aquí: una consulta en nombre del HUB pregunta
/// por el entorno en el que el hub está ahora, mientras que una consulta en nombre de UN registro
/// pregunta por el entorno en el que vive la cadena de ese registro (hub#471, guarda R4). Misma
/// llamada, dos dueños. Antes el parámetro era la URL ya resuelta; ahora es el entorno, porque la
/// celda deriva ella misma la puerta AEAT del par (entorno, tipo del certificado que presenta) y
/// pasarle una URL sería pedirle que enrutara — que es justo lo que su contrato no hace.
pub(crate) async fn run_consult(
    host: &dyn NativeHost,
    hub_id: &str,
    config: &Json,
    environment: &str,
    issuer_nif: &str,
    now: &str,
) -> Result<Vec<aeat::ConsultRecord>> {
    let route = resolve_route(host, hub_id, config).await?;
    run_consult_via(host, hub_id, config, &route, environment, issuer_nif, now).await
}

/// La consulta sobre una vía **ya resuelta**.
///
/// Existe para el auto-rechain (`transmission::auto_rechain_and_retry`), que resolvió la vía al
/// transmitir: volver a resolverla ahí sería la SEGUNDA lectura de la misma pregunta que
/// `config.rs` documenta como el origen de hub#317/#318/#319/#470 — y además podría consultar por
/// una vía y re-transmitir por otra, anclando la cadena desde una puerta que no es la que emitió.
pub(crate) async fn run_consult_via(
    host: &dyn NativeHost,
    hub_id: &str,
    config: &Json,
    route: &TransmitRoute,
    environment: &str,
    issuer_nif: &str,
    now: &str,
) -> Result<Vec<aeat::ConsultRecord>> {
    let issuer_name = obligado_name(config);
    let (ejercicio, periodo) = year_month(now);
    // Quién consulta. Por la celda es ERPlora con el Sello, y el par sale del token FIRMADO, igual
    // que el `Representante` del alta (hub#1460) — pero aquí viaja como FLAG, no como bloque: el
    // esquema de consulta no admite `Representante`. Ver `aeat::build_consult_soap`.
    let presenter = match route {
        TransmitRoute::Gateway(access) => Some(access.presenter()),
        TransmitRoute::Direct(_) => None,
    };
    // Se construye ANTES de abrir la conexión: si falta la razón social del obligado, el sobre
    // no es válido y no tiene sentido hablar con Hacienda para llevarse un 4102.
    let xml = aeat::build_consult_soap(issuer_nif, &issuer_name, &ejercicio, &periodo, presenter)?;
    let body = match route {
        // Vía propia: TLS mutua con el certificado del core (opaca) o legacy. Ver ADR-0079.
        TransmitRoute::Direct(identity) => {
            aeat::post_soap(
                aeat::consult_endpoint(environment, &signing_type(config)),
                identity.clone(),
                &xml,
            )
            .await?
        }
        // Por la celda: los MISMOS bytes, y vuelve el SOAP crudo de la AEAT — el parser de abajo
        // no distingue el camino. La consulta viaja por la ruta de transmisión de la celda porque
        // la AEAT publica la consulta en el MISMO `VerifactuSOAP` que el alta (hub#287): a la
        // celda le llega un sobre opaco hacia la puerta que ya deriva del entorno.
        TransmitRoute::Gateway(access) => {
            crate::gateway::transmit_via_gateway(
                host,
                hub_id,
                access,
                &crate::gateway::GatewayEnvelope {
                    hub_id,
                    obligado_nif: issuer_nif,
                    environment,
                    transmission_id: &consult_correlation_id(issuer_nif, now),
                    xml: &xml,
                },
            )
            .await?
        }
    };
    Ok(aeat::parse_consult_response(&body)?)
}

/// El identificador de correlación de UNA consulta, que la celda copia a `Idempotency-Key`.
///
/// 🔴 Lleva el instante dentro **a propósito**. Para un alta la clave es el id del registro y su
/// gracia es que se repita: reenviar los mismos bytes tras un 504 tiene que ser el mismo envío.
/// Una consulta es lo contrario — pregunta por un estado que cambia—, así que una clave repetida
/// serviría una foto vieja el día que la celda implemente la idempotencia que hoy tiene
/// reservada, y una recuperación de cadena que ancla sobre datos rancios es exactamente el fallo
/// mudo que `recover_from_aeat` existe para evitar. El prefijo `consult-` además la hace
/// reconocible en los logs de la celda, donde todo lo demás son altas.
fn consult_correlation_id(issuer_nif: &str, now: &str) -> String {
    let safe = |value: &str| -> String {
        value
            .chars()
            .filter(|c| c.is_ascii_alphanumeric())
            .collect()
    };
    format!("consult-{}-{}", safe(issuer_nif), safe(now))
}

/// Intenciones para volcar el snapshot de consulta AEAT: limpia el anterior de este emisor +
/// inserta hasta 10 registros (usa `ctx.new_ids[0..N]`). Devuelve (ops, nº insertados).
pub(crate) fn aeat_snapshot_ops(
    ctx: &Ctx,
    issuer_nif: &str,
    records: &[aeat::ConsultRecord],
) -> (Vec<Operation>, usize) {
    let mut ops = vec![op(
        "verifactu._clear_aeat_records",
        json!({ "issuer_nif": issuer_nif.to_string() }),
    )];
    let limit = records.len().min(10);
    for (i, r) in records.iter().take(limit).enumerate() {
        let nif_val = if r.issuer_nif.is_empty() {
            issuer_nif.to_string()
        } else {
            r.issuer_nif.clone()
        };
        ops.push(op(
            "verifactu._insert_aeat_record",
            json!({
                "rec_id": ctx.new_ids.get(i).cloned().unwrap_or_default(),
                "issuer_nif": nif_val,
                "invoice_number": r.invoice_number.clone(),
                "invoice_date": iso_date(&r.invoice_date),
                "record_type": "alta",
                "record_hash": chain::normalize_hash(&r.record_hash),
                "aeat_csv": r.csv.clone(),
                "estado": r.estado.clone(),
                "query_timestamp": ctx.now.clone(),
            }),
        ));
    }
    (ops, limit)
}

// ── validate_chain (issue verifactu#4) ────────────────────────────────────────
