//! Transmission to the AEAT: retries, refusals, contingency drain — split out of `lib.rs` verbatim (hub#1405).

use crate::*;

pub(crate) async fn transmit_record(input: &Json, host: &dyn NativeHost) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;
    let record_id = str_field(&payload, "record_id");
    if record_id.is_empty() {
        return Err(VerifactuError::Payload("falta record_id".into()).into());
    }
    if ctx.new_ids.len() < 2 {
        return Err(RuntimeError::Native("context.new_ids insuficientes".into()));
    }

    let rows = host
        .read(
            "SELECT * FROM verifactu_record WHERE id = :record_id AND hub_id = :hub_id \
             AND is_deleted = 0 LIMIT 1",
            &params(json!({ "record_id": record_id, "hub_id": ctx.hub_id })),
        )
        .await?;
    let record = rows
        .into_iter()
        .next()
        .ok_or_else(|| RuntimeError::Native(format!("registro `{record_id}` no encontrado")))?;
    if str_field(&record, "status") == "accepted" {
        return Err(RuntimeError::Native(
            "el registro ya fue aceptado por la AEAT".into(),
        ));
    }

    let config = read_config(host, &ctx.hub_id).await?.ok_or_else(|| {
        RuntimeError::Native("VeriFactu sin configurar (verifactu.config.save)".into())
    })?;
    // Gate: sin NINGUNA vía (certificado del core o pasarela fiscal) no se puede transmitir.
    if !can_transmit(host, &ctx.hub_id, &config).await? {
        return Err(VerifactuError::Certificate(
            "sin vía de transmisión: ni certificado PKCS#12 (sube el .p12 en Ajustes → Negocio) \
             ni pasarela fiscal disponible"
                .into(),
        )
        .into());
    }

    let (ops, events, _success) = transmit_one(
        host,
        &ctx,
        &record,
        &config,
        &ctx.new_ids[0],
        &ctx.new_ids[1],
        // Id reservado para el ancla si la AEAT rechaza por encadenamiento y hay que re-anclar.
        &ctx.new_ids[2],
        // Envío puntual: `verifactu.record.transmit` remite un registro, no drena la cola.
        Remission::Punctual,
    )
    .await?;
    let mut out = Output::new();
    for o in ops {
        out = out.with_operation(o);
    }
    // El evento `verifactu.record.transmitted` lo emite el `emit` declarado del command — sale
    // pase lo que pase, porque describe el INTENTO. Lo que decide el desenlace es esto (verifactu#42).
    for e in events {
        out = out.with_event(e);
    }
    Ok(out)
}

/// Núcleo de transmisión de **un** registro: lee el registro anterior (encadenamiento), construye
/// el XML SOAP, firma con el PKCS#12 y hace POST TLS-mutua a la AEAT. Devuelve las intenciones
/// (UPDATE registro + evento + resolver/encolar contingencia) y `true` si la AEAT lo aceptó.
/// Reutilizado por `transmit_record` (uno) y `process_contingency_queue` (lote).
#[allow(clippy::too_many_arguments)]
pub(crate) async fn transmit_one(
    host: &dyn NativeHost,
    ctx: &Ctx,
    record: &Json,
    config: &Json,
    event_id: &str,
    queue_id: &str,
    recovery_id: &str,
    remission: Remission,
) -> Result<(Vec<Operation>, Vec<Event>, bool)> {
    let record_id = str_field(record, "id");
    // WHERE this goes is settled BEFORE anything else happens — before the chain read, before
    // the XML, before the archive (hub#471). If the record cannot say which of the two tax
    // agencies owns it, nothing is built and nothing is sent.
    let destination = match destination_of(record, config) {
        Ok(destination) => destination,
        Err(reason) => {
            return refuse_transmission(
                host,
                ctx,
                record,
                event_id,
                queue_id,
                config,
                &Refusal::environment_unknown(reason),
            )
            .await
        }
    };
    let is_first = int_field(record, "is_first_record", 0) != 0;
    let prev = if is_first {
        None
    } else {
        // Guard R4 (hub#313): sequence numbers repeat across environments, so the previous
        // link comes from the RECORD's own environment — a retried testing record must keep
        // linking inside testing even after the hub switched its config to production.
        host.read(
            "SELECT issuer_nif, invoice_number, invoice_date, record_hash FROM verifactu_record \
             WHERE hub_id = :hub_id AND issuer_nif = :issuer_nif \
             AND environment = :environment AND sequence_number = :prev_seq \
             AND is_deleted = 0 LIMIT 1",
            &params(json!({
                "hub_id": ctx.hub_id,
                "issuer_nif": str_field(record, "issuer_nif"),
                "environment": str_field(record, "environment"),
                "prev_seq": int_field(record, "sequence_number", 1) - 1,
            })),
        )
        .await?
        .into_iter()
        .next()
    };

    // En un reintento se usa EXACTAMENTE el XML del intento anterior (si ya quedó en BD), no se
    // regenera con una configuración que podría haber cambiado mientras la AEAT estaba caída.
    //
    // **Si el sobre no se puede construir, no se transmite** (hub#324): un importe ausente o
    // ilegible ya no se convierte en `0,00`. Se trata como la negativa de hub#471 —evento con
    // motivo + entrada en la cola—, NO como un rechazo: el registro se queda donde está, con su
    // XML anterior intacto, y vuelve a intentarse cuando el dato esté arreglado (FAQ §5: ningún
    // RF generado puede quedarse sin remitir).
    let xml = match record
        .get("xml_content")
        .and_then(Json::as_str)
        .filter(|value| !value.trim().is_empty())
        .map(ToString::to_string)
    {
        Some(previous) => previous,
        None => match aeat::build_soap(record, config, prev.as_ref(), &ctx.hub_id) {
            Ok(xml) => xml,
            Err(e) => {
                return refuse_transmission(
                    host,
                    ctx,
                    record,
                    event_id,
                    queue_id,
                    config,
                    &Refusal::undeclarable(e.to_string()),
                )
                .await
            }
        },
    };

    // `Cabecera/Incidencia=S` cuando el envío sale de la cola de contingencia (hub#322). Se
    // estampa AQUÍ, sobre el sobre ya resuelto, y no dentro del constructor: el XML reutilizado
    // de un intento anterior se construyó cuando nadie sabía todavía que este registro acabaría
    // en la cola, y ese es justamente el caso normal de la cola. Es marca del SOBRE: el bloque
    // `RegistroAlta`/`RegistroAnulacion` —el que cubre la huella— no cambia ni un byte.
    let xml = match remission {
        Remission::Punctual => xml,
        Remission::FromContingency => aeat::stamp_contingency_incidence(&xml),
    };

    // La vía se resuelve AQUÍ, antes de validar y archivar, porque el `Representante` viaja DENTRO
    // del sobre (hub#1460): quién presenta estos bytes es un hecho de la vía, y el XML que se
    // valida, se archiva y cuyo sha256 compara el canario (hub#1461) tiene que ser el que sale por
    // el cable — no una versión anterior a estamparlo.
    //
    // **Su error se difiere a propósito.** Antes de hub#1460 la ruta se resolvía después de la
    // validación, así que un sobre que no cumple el esquema se marcaba `rejected` LOCALMENTE aun
    // sin vía. Propagar aquí ese error invertiría el orden: el registro volvería a la cola a
    // reintentarse para siempre con un XML que no puede validar nunca. Se resuelve ahora, se
    // estampa, y el `?` se cobra más abajo, exactamente donde estaba.
    let route = resolve_route(host, &ctx.hub_id, config).await;
    let obligado_nif = str_field(record, "issuer_nif");
    let xml = match &route {
        // Por la celda presenta ERPlora con el Sello, y quién es lo dice el token FIRMADO — el hub
        // nunca ve ese certificado, así que no puede leerlo de ningunos bytes suyos.
        Ok(TransmitRoute::Gateway(access)) => {
            aeat::set_representative(&xml, Some(access.presenter()), &obligado_nif)
        }
        // Vía propia: firma el certificado del negocio, el titular ES el obligado y no se inventa
        // representación (ADR-0268 §4). El `None` además LIMPIA: un sobre congelado en la cola
        // pudo estamparse cuando el hub todavía iba por la celda, y re-presentarlo con la
        // identidad de ERPlora sería una representación falsa.
        _ => aeat::set_representative(&xml, None, &obligado_nif),
    };

    // Validación contra el esquema ANTES de tocar la red (`xsd::validate_registro`). Cuando la
    // AEAT contesta 4102 el número de cadena ya está gastado, así que un XML que no cumple no
    // puede llegar a salir. No corta el proceso: marca el registro como rechazado LOCALMENTE con
    // el motivo, para que se vea en la UI y para que un fallo de configuración no bloquee la cola
    // de contingencia entera.
    if let Err(e) = xsd::validate_registro(&xml) {
        let reason = e.to_string();
        return Ok((
            vec![
                apply_transmission(
                    &record_id,
                    "rejected",
                    "XSD",
                    &reason,
                    "",
                    &xml,
                    "",
                    &record_id,
                    0,
                ),
                op(
                    "verifactu._insert_event",
                    json!({
                        "event_id": event_id,
                        "record_id": record_id,
                        "event_type": "transmission_failure",
                        "severity": "error",
                        "message": format!("XML no conforme al esquema de la AEAT; no se ha transmitido: {reason}"),
                        "details": details_for("verifactu.xsd_invalid", json!({ "validation_error": reason })),
                        "timestamp": ctx.now,
                    }),
                ),
            ],
            vec![Event::new(
                EVENT_RECORD_REJECTED,
                failure_payload(
                    record,
                    REASON_XSD_INVALID,
                    "rejected",
                    "XSD",
                    &reason,
                    &destination.environment,
                ),
            )],
            false,
        ));
    }

    // Archivo duradero ANTES de tocar la red. Si el backend Local/S3 no confirma la escritura, no
    // se envía: nunca aceptamos una transmisión fiscal sin conservar su XML para auditoría/reenvío.
    let xml_storage_path = archive_transmission_xml(host, &record_id, &xml).await?;
    // Las dos vías de ADR-0320, resueltas en UN sitio (`resolve_route`): certificado del core →
    // directo a la AEAT, como siempre; sin certificado → la pasarela fiscal transmite LOS MISMOS
    // bytes con el Sello como canal (hub#1432). Aguas abajo nadie distingue el camino: las dos
    // devuelven el SOAP crudo de la AEAT y la cadena parse/classify/persistencia es una.
    //
    // Aquí se cobra el error diferido de arriba: sin vía, el registro se queda como siempre.
    let route = route?;
    let transport = match &route {
        TransmitRoute::Direct(identity) => {
            aeat::post_soap(destination.endpoint, identity.clone(), &xml).await
        }
        TransmitRoute::Gateway(access) => crate::gateway::transmit_via_gateway(
            host,
            &ctx.hub_id,
            access,
            &crate::gateway::GatewayEnvelope {
                hub_id: &ctx.hub_id,
                obligado_nif: &str_field(record, "issuer_nif"),
                environment: &destination.environment,
                transmission_id: &record_id,
                xml: &xml,
            },
        )
        .await,
    };

    // Un cuerpo entregado que NO es un veredicto (un SOAP Fault de la AEAT, o HTML de un
    // intermediario) parseaba a un `AeatResponse` con todos los campos vacíos y se archivaba como
    // «AEAT (testing): » — un fallo mudo (regla: un fallo que no se ve no existe). Se vio en vivo
    // el 2026-09-02: el NIF demo inválido volvía como Fault 4116 y el registro moría sin motivo
    // visible. Un no-veredicto lleva el motivo del otro lado a bordo (`faultstring`): se normaliza
    // AQUÍ a la misma rama que un fallo de conexión — contingencia con backoff y el motivo en el
    // evento — en vez de inventarle un veredicto.
    let transport = transport.and_then(|body| match fault_reason(&body) {
        Some(reason) => Err(VerifactuError::Transmission(reason)),
        None => Ok(body),
    });

    match transport {
        Ok(body) => {
            let resp = aeat::parse_response(&body);

            // ── Recuperación automática: SOLO si la AEAT rechazó de verdad ─────────────────
            // El caso que se quería cubrir es **restaurar un backup**: la cadena local retrocede
            // y el envío sale con `PrimerRegistro=S` cuando la AEAT ya tiene registros de ese
            // obligado y sistema informático. Se asumió que eso llegaba como rechazo. El ensayo
            // contra preproducción (2026-08-02, ADR-0189) demostró que no, y que re-enviar es lo
            // peor que se puede hacer:
            //
            //   1. La AEAT contesta `EstadoRegistro=AceptadoConErrores` + `2007` — un ACEPTADO:
            //      el registro **ya está en la AEAT** con la huella que se le calculó.
            //   2. Reenviarlo re-anclado devuelve **3000 «Registro de facturación duplicado»**, y
            //      la consulta posterior sigue mostrando una sola aparición. Ni duplica ni
            //      sustituye: rechaza.
            //
            // Por eso el disparo cuelga de `should_retransmit()` —es decir, de que el registro NO
            // esté aceptado—, y no de una lista de códigos. Un 2007 se cierra abajo como aceptado
            // **con aviso**: la cadena sigue desde él, que es lo que la AEAT tiene por último.
            // Re-anclar ANTES de emitir sigue siendo una acción explícita (`recover_from_aeat`).
            let verdict = aeat::classify(&resp);
            // Las DOS vías recuperan (hub#1436). El auto-rechain se saltaba en la vía gateway
            // porque consultaba a la AEAT con la identity del core, que un hub sin certificado no
            // tiene; desde hub#1436 la consulta viaja por la misma vía que la transmisión, así que
            // un hub por la celda que restaura un backup se re-ancla como cualquier otro. Se le
            // pasa la vía YA RESUELTA: consultar por una puerta y re-transmitir por otra anclaría
            // la cadena desde una puerta que no la emitió (guarda R4).
            if verdict.should_retransmit()
                && aeat::is_chaining_rejection(&resp.codigo_error, &resp.descripcion_error)
                && !recovery_id.is_empty()
            {
                match auto_rechain_and_retry(
                    host,
                    ctx,
                    record,
                    config,
                    &route,
                    &destination,
                    &resp,
                    recovery_id,
                    event_id,
                    remission,
                )
                .await
                {
                    // Re-anclado y reintentado: ese es el resultado que vale.
                    Ok(Some(result)) => return Ok(result),
                    // La AEAT no dio ancla utilizable → se registra el rechazo original.
                    Ok(None) => {}
                    // La recuperación falló (consulta caída, sin certificado…). El rechazo
                    // original se registra igual, con el motivo del fallo anotado: nunca se
                    // traga en silencio.
                    Err(e) => {
                        return Ok(response_ops(
                            record,
                            &resp,
                            &destination,
                            &xml,
                            &xml_storage_path,
                            event_id,
                            &ctx.now,
                            &record_id,
                            Some(&format!("recuperación automática fallida: {e}")),
                        ))
                    }
                }
            }

            Ok(response_ops(
                record,
                &resp,
                &destination,
                &xml,
                &xml_storage_path,
                event_id,
                &ctx.now,
                &record_id,
                None,
            ))
        }
        Err(err) => {
            // 🪦 Aquí iba el **tercer disparador de refetch del certificado** (ADR-0202 §2 punto 4,
            // hub#318): un fallo TLS pedía al plano de control el certificado DELEGADO vigente. Se
            // fue con el slot que bajaba (hub#1435) y no se sustituye por nada, a propósito.
            //
            // Solo disparaba cuando quien se identificó era el certificado de ERPlora, porque bajar
            // el delegado no arregla un `own` roto: el propio gana el fallback y el intento
            // siguiente falla igual. Sin slot delegado no queda ningún caso — un fallo TLS por aquí
            // es siempre del certificado del NEGOCIO, y ese no lo puede refrescar ERPlora: lo
            // renueva su dueño. Lo que sí queda es lo que ya hacía la línea de abajo, y es lo
            // correcto: el registro se encola en contingencia con backoff y el error se ve.
            //
            // Fallo de conexión/transporte → contingencia con backoff (WASM-TODO §5).
            let reason = err.to_string();
            let retry = enqueue_retry(host, ctx, &record_id, queue_id, config, &reason).await?;
            let environment = &destination.environment;
            let backoff_minutes = retry.backoff_minutes;
            let ops = vec![
                apply_transmission(
                    &record_id,
                    "error",
                    "",
                    &reason,
                    "",
                    &xml,
                    &xml_storage_path,
                    &record_id,
                    1,
                ),
                op(
                    "verifactu._insert_event",
                    json!({
                        "event_id": event_id,
                        "record_id": record_id.clone(),
                        "event_type": "transmission_failure",
                        "severity": "error",
                        "message": format!("Fallo de transmisión AEAT ({environment}); reintento en {backoff_minutes} min"),
                        "details": details_for("verifactu.transmission_retry", json!({
                            "environment": environment,
                            "backoff_minutes": backoff_minutes,
                            "error": reason.clone(),
                            "attempts": retry.attempts,
                        })),
                        "timestamp": ctx.now,
                    }),
                ),
                retry.operation,
            ];
            Ok((
                ops,
                // For the owner this is the same problem as a refusal — the invoice is not at the
                // AEAT. `reason` is what tells an operator that the wire failed, not the filing.
                vec![Event::new(
                    EVENT_RECORD_REJECTED,
                    failure_payload(
                        record,
                        REASON_TRANSMISSION_FAILED,
                        "error",
                        "",
                        &reason,
                        environment,
                    ),
                )],
                false,
            ))
        }
    }
}

/// Contingency entry for a record that could NOT be remitted: attempt count + the 5/10/20/40/60
/// minute backoff (WASM-TODO §5).
///
/// Shared by the transport failure and by the hub#471 refusal, so a record that cannot be sent
/// is queued the same way whatever stopped it — the FAQ §5 invariant is that no RF may stay
/// generated and never remitted, and the queue is what makes that true.
pub(crate) struct Retry {
    operation: Operation,
    attempts: i64,
    backoff_minutes: i64,
}

/// The reason a delivered body is NOT an AEAT verdict — `None` when it is one.
///
/// The parser is namespace-driven and yields an all-empty [`aeat::AeatResponse`] for anything
/// that is not a `RespuestaRegFactuSistemaFacturacion`: a SOAP `Fault` (the AEAT's own refusal —
/// measured live on 2026-09-02: `4116` for a malformed obligado NIF, `4112` for a holder the
/// Sello may not present for), or an intermediary's HTML. Filing that as a verdict buries the
/// other side's message; this surfaces it, `faultstring` first.
pub(crate) fn fault_reason(body: &str) -> Option<String> {
    let resp = aeat::parse_response(body);
    let is_verdict = !resp.estado_envio.is_empty()
        || !resp.estado_registro.is_empty()
        || !resp.csv.is_empty();
    if is_verdict {
        return None;
    }
    let fault = body
        .split("<faultstring>")
        .nth(1)
        .and_then(|rest| rest.split("</faultstring>").next())
        .map(str::trim)
        .filter(|s| !s.is_empty());
    Some(match fault {
        Some(text) => {
            let mut snippet: String = text.chars().take(300).collect();
            if text.chars().count() > 300 {
                snippet.push('…');
            }
            format!("la AEAT respondió un Fault, no un veredicto: {snippet}")
        }
        None => "la AEAT no devolvió un veredicto reconocible (cuerpo sin \
                 RespuestaRegFactuSistemaFacturacion ni faultstring)"
            .to_owned(),
    })
}

pub(crate) async fn enqueue_retry(
    host: &dyn NativeHost,
    ctx: &Ctx,
    record_id: &str,
    queue_id: &str,
    config: &Json,
    reason: &str,
) -> Result<Retry> {
    let queue = host
        .read(
            "SELECT attempts FROM verifactu_contingencyqueue \
             WHERE record_id = :record_id AND is_deleted = 0 LIMIT 1",
            &params(json!({ "record_id": record_id })),
        )
        .await?;
    let attempts = queue
        .first()
        .map(|q| int_field(q, "attempts", 0))
        .unwrap_or(0)
        + 1;
    let interval = config
        .get("retry_interval_minutes")
        .and_then(|v| v.as_i64())
        .filter(|v| *v > 0)
        .unwrap_or(5);
    let backoff_minutes = (interval * 2_i64.pow((attempts - 1).min(8) as u32)).min(60);
    let next_attempt_at = chrono::DateTime::parse_from_rfc3339(&ctx.now)
        .map(|dt| {
            (dt + chrono::Duration::minutes(backoff_minutes))
                .to_rfc3339_opts(chrono::SecondsFormat::Secs, false)
        })
        .unwrap_or_else(|_| ctx.now.clone());
    Ok(Retry {
        operation: op(
            "verifactu._enqueue_contingency",
            json!({
                "queue_id": queue_id,
                "record_id": record_id,
                "priority": 2,
                "attempts": attempts,
                "last_attempt_at": ctx.now,
                "last_error": reason,
                "next_attempt_at": next_attempt_at,
                "queue_status": "retrying",
            }),
        ),
        attempts,
        backoff_minutes,
    })
}

/// **Where this send comes from**, which is what decides whether the envelope declares an
/// incidence (`Cabecera/RemisionVoluntaria/Incidencia`, hub#322).
///
/// It is passed in and not derived from the record on purpose: the caller is the only one that
/// knows. `process_contingency_queue` is draining the queue; `transmit_record` and the inline
/// transmission of `create_record` are remitting an invoice as it happens.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Remission {
    /// The record is being remitted as it is generated — the ordinary sale.
    Punctual,
    /// The record waited in the contingency queue and is going out now. This is what `Incidencia`
    /// exists for, and what makes the deferred remission legal instead of merely late.
    FromContingency,
}

/// Why a record was NOT handed to the AEAT, in the two channels the operator reads: a stable code
/// the UI can program against, and the sentence a human sees.
///
/// The code used to be the literal `record_environment_unknown`, written inside the event — which
/// worked while there was exactly one way to refuse. There are two now (hub#324 added «the record
/// cannot be declared»), and two refusals wearing the same code would have the panel telling
/// somebody to fix an environment when what is broken is an amount.
pub(crate) struct Refusal {
    /// Stable domain key, `<what_is_wrong>` in the module's own namespace. Never translated.
    code: &'static str,
    /// The reason as a human reads it. Also what goes into `contingencyqueue.last_error`.
    reason: String,
}

impl Refusal {
    /// The record does not say which of the two tax agencies owns it (hub#471).
    fn environment_unknown(reason: String) -> Self {
        Self {
            code: REASON_ENVIRONMENT_UNKNOWN,
            reason,
        }
    }

    /// The envelope could not be built at all: an amount is missing or unreadable (hub#324).
    /// **Retryable on purpose** — the fix is upstream data, and the record must keep its place.
    fn undeclarable(reason: String) -> Self {
        Self {
            code: REASON_RECORD_NOT_DECLARABLE,
            reason,
        }
    }
}

/// **The record does not say which AEAT owns it, so nothing is transmitted** (hub#471).
///
/// The row is deliberately left UNTOUCHED: `_apply_transmission` overwrites `xml_content` and
/// `xml_storage_path` unconditionally, and the archived XML of a record that was never sent is
/// fiscal evidence. What the refusal leaves is an `error` event with a stable reason key and a
/// contingency entry, so the record is retried once the cause is fixed and never disappears.
///
/// It returns an outcome and not an `Err` on purpose: `process_contingency_queue` propagates
/// errors with `?`, so one unresolvable row would abort the whole batch and strand every other
/// record behind it.
pub(crate) async fn refuse_transmission(
    host: &dyn NativeHost,
    ctx: &Ctx,
    record: &Json,
    event_id: &str,
    queue_id: &str,
    config: &Json,
    refusal: &Refusal,
) -> Result<(Vec<Operation>, Vec<Event>, bool)> {
    let reason = refusal.reason.as_str();
    let record_id = &str_field(record, "id");
    let retry = enqueue_retry(host, ctx, record_id, queue_id, config, reason).await?;
    Ok((
        vec![
            op(
                "verifactu._insert_event",
                json!({
                    "event_id": event_id,
                    "record_id": record_id,
                    "event_type": "transmission_failure",
                    "severity": "error",
                    "message": format!("No se ha transmitido a la AEAT: {reason}"),
                    "details": details_for("verifactu.not_transmitted", json!({
                        "reason": refusal.code,
                        "error": reason,
                        "attempts": retry.attempts,
                    })),
                    "timestamp": ctx.now,
                }),
            ),
            retry.operation,
        ],
        // Nothing was handed to the AEAT — the same problem for the owner as a refusal, under the
        // reason that tells an operator the two apart. The key is `Refusal::code` and not a
        // literal: hub#324 added a second way to refuse (an envelope that cannot be built), and
        // two refusals wearing the same reason would have the alarm telling somebody to fix an
        // environment when what is broken is an amount.
        vec![Event::new(
            EVENT_RECORD_REJECTED,
            failure_payload(record, refusal.code, "error", "", reason, ""),
        )],
        false,
    ))
}

/// Intenciones que aplican una respuesta de la AEAT sobre el registro: UPDATE + evento (+ salida
/// de la cola de contingencia si fue aceptado). Compartido por el primer intento y por el
/// reintento tras re-anclar.
#[allow(clippy::too_many_arguments)]
#[allow(clippy::too_many_arguments)]
pub(crate) fn response_ops(
    record: &Json,
    resp: &aeat::AeatResponse,
    destination: &Destination,
    xml: &str,
    xml_storage_path: &str,
    event_id: &str,
    now: &str,
    transmission_id: &str,
    note: Option<&str>,
) -> (Vec<Operation>, Vec<Event>, bool) {
    let record_id = &str_field(record, "id");
    let verdict = aeat::classify(resp);
    let success = verdict.status == "accepted";
    // A record whose chain is not the hub's current environment went to the OTHER tax agency.
    // That is CORRECT — the chain owns the record — but it is never routine: it is what a
    // go-live with a non-empty queue looks like, and the owner has to be able to find it
    // (hub#471). Filed as `info`, nobody would.
    let drifted = destination.hub_environment.is_some();
    // Un `AceptadoConErrores` está registrado en la AEAT (no se reenvía), pero no puede pasar por
    // un éxito limpio: se persiste el código de la AEAT y el evento sale como aviso, no como info.
    let (event_type, severity) = match (success, verdict.accepted_with_errors || drifted) {
        (true, false) => ("transmission_success", "info"),
        (true, true) => ("transmission_warning", "warning"),
        (false, _) => ("transmission_failure", "error"),
    };
    let environment = &destination.environment;
    // The note of the caller (an automatic re-anchor, a failed recovery) and the drift note
    // travel together: both are things the operator has to read next to the AEAT verdict.
    let notes: Vec<String> = note
        .map(ToString::to_string)
        .into_iter()
        .chain(destination.drift_note())
        .collect();
    let note = (!notes.is_empty()).then(|| notes.join(" · "));
    let mut ops = vec![
        apply_transmission(
            record_id,
            verdict.status,
            &verdict.code,
            &verdict.message,
            &resp.csv,
            xml,
            xml_storage_path,
            transmission_id,
            0,
        ),
        op(
            "verifactu._insert_event",
            json!({
                "event_id": event_id,
                "record_id": record_id,
                "event_type": event_type,
                "severity": severity,
                "message": match &note {
                    Some(n) => format!("AEAT ({environment}): {} {} — {n}", resp.estado_envio, resp.estado_registro),
                    None => format!("AEAT ({environment}): {} {}", resp.estado_envio, resp.estado_registro),
                },
                "details": details_for("verifactu.aeat_verdict", json!({
                    "environment": environment,
                    "estado_envio": resp.estado_envio,
                    "estado_registro": resp.estado_registro,
                    "csv": resp.csv,
                    "codigo_error": resp.codigo_error,
                    "descripcion_error": resp.descripcion_error,
                    "note": note,
                })),
                "timestamp": now,
            }),
        ),
    ];
    if success {
        // Si el registro estaba en la cola de contingencia, sale de ella.
        ops.push(op(
            "verifactu._resolve_contingency",
            json!({ "record_id": record_id }),
        ));
    }
    // ── What LEAVES the module (verifactu#42) ────────────────────────────────────────────────
    //
    // The `_insert_event` row above is the audit trail: it is on a screen somebody has to open,
    // and the bar that closes at two in the morning does not open it. This is the outbox event an
    // automation can hang off — and it is emitted only for the two outcomes a person has to act
    // on. A clean acceptance says nothing: `verifactu.record.transmitted` already covers «it went
    // out», and one more row per successful invoice would be the till's whole day in the outbox.
    //
    // The drift note is NOT one of them. A record remitted to the other tax agency is correct
    // (the chain owns it) and it is already a `warning` in the audit trail; raising it here would
    // make «something went wrong fiscally» fire on a go-live, which is the fastest way to teach
    // an owner to ignore the alarm.
    let events = if !success {
        vec![Event::new(
            EVENT_RECORD_REJECTED,
            failure_payload(
                record,
                REASON_AEAT_REJECTED,
                verdict.status,
                &verdict.code,
                &verdict.message,
                environment,
            ),
        )]
    } else if verdict.accepted_with_errors {
        vec![Event::new(
            EVENT_RECORD_ACCEPTED_WITH_ERRORS,
            failure_payload(
                record,
                REASON_AEAT_REJECTED,
                verdict.status,
                &verdict.code,
                &verdict.message,
                environment,
            ),
        )]
    } else {
        Vec::new()
    };
    (ops, events, success)
}

/// El eslabón anterior en la forma que espera `aeat::build_soap`, a partir del ancla que devolvió
/// la AEAT. `invoice_date` llega en formato AEAT (`DD-MM-YYYY`) y `build_soap` lo re-formatea, así
/// que se normaliza a ISO aquí igual que en el resto de la recuperación.
pub(crate) fn anchor_as_prev(anchor: &aeat::ConsultRecord) -> Json {
    json!({
        "issuer_nif": anchor.issuer_nif,
        "invoice_number": anchor.invoice_number,
        "invoice_date": iso_date(&anchor.invoice_date),
        "record_hash": chain::normalize_hash(&anchor.record_hash),
    })
}

/// Re-ancla el registro desde lo que la AEAT tiene y lo **reintenta una vez**.
///
/// Es la recuperación automática de hub#287. Devuelve `Ok(None)` si la AEAT no dio un ancla
/// utilizable (no hay de dónde recuperar → se registra el rechazo original) y `Err` si la propia
/// recuperación falló (consulta caída, sin certificado…) — nunca en silencio.
///
/// Un solo reintento, a propósito: si el segundo envío también se rechaza, el problema no era el
/// eslabón y reintentar en bucle solo quemaría números de cadena.
#[allow(clippy::too_many_arguments)]
pub(crate) async fn auto_rechain_and_retry(
    host: &dyn NativeHost,
    ctx: &Ctx,
    record: &Json,
    config: &Json,
    // The road the rejected send took. Passed in for the same reason as the destination: the
    // consult that recovers the anchor and the retry that uses it must go through the SAME door
    // that issued the chain, and re-resolving would be the second reading of one question
    // (hub#317/#318/#319/#470).
    route: &TransmitRoute,
    // Passed in, never recomputed: resolving the destination twice is how the endpoint got out
    // of step with the record in the first place (hub#320's rule, hub#471's bug).
    destination: &Destination,
    rejection: &aeat::AeatResponse,
    recovery_id: &str,
    event_id: &str,
    // El re-anclado hereda el origen del envío que lo disparó (hub#322): un registro que salió
    // de la cola sigue saliendo de la cola cuando se reintenta sobre el ancla que dio la AEAT.
    remission: Remission,
) -> Result<Option<(Vec<Operation>, Vec<Event>, bool)>> {
    let issuer_nif = str_field(record, "issuer_nif");
    // Both legs of the recovery go to the record's OWN destination (hub#471): asking the wrong
    // tax agency for the anchor would re-chain this record onto a link from the other chain,
    // which is precisely the crossing that guard R4 exists to prevent.
    let records = run_consult_via(
        host,
        &ctx.hub_id,
        config,
        route,
        &destination.environment,
        &issuer_nif,
        &ctx.now,
    )
    .await?;
    let Some(anchor) = aeat::pick_latest_record(&records) else {
        return Ok(None);
    };

    // The consult ran against the RECORD's environment, so the recovered anchor belongs to
    // THAT environment's chain (guard R4).
    let environment = &destination.environment;
    // The anchor takes the next number; the rechained record, the one after.
    let anchor_seq = next_sequence(host, &ctx.hub_id, &issuer_nif, environment).await?;
    let anchor_hash = chain::normalize_hash(&anchor.record_hash);
    let anchor_op = op(
        "verifactu._insert_recovery",
        json!({
            "record_id": recovery_id,
            "sequence_number": anchor_seq,
            "issuer_nif": issuer_nif,
            "issuer_name": obligado_name(config),
            "environment": environment,
            "invoice_number": if anchor.invoice_number.is_empty() {
                format!("AEAT-{}", short(&anchor_hash))
            } else {
                anchor.invoice_number.clone()
            },
            "invoice_date": iso_date(&anchor.invoice_date),
            "description": "Ancla recuperada automáticamente tras un rechazo de encadenamiento",
            "record_hash": anchor_hash,
            "aeat_csv": anchor.csv,
        }),
    );

    let (rechained, rechain_op) = rechain_record(record, anchor, anchor_seq + 1);
    let record_id = str_field(record, "id");
    let xml = aeat::build_soap(
        &rechained,
        config,
        Some(&anchor_as_prev(anchor)),
        &ctx.hub_id,
    )?;
    let xml = match remission {
        Remission::Punctual => xml,
        Remission::FromContingency => aeat::stamp_contingency_incidence(&xml),
    };
    // Quién presenta ESTOS bytes, con la misma regla que el envío que los provocó (hub#1460): el
    // sobre se acaba de reconstruir con `build_soap`, así que no trae `Representante` ninguno y
    // sin estamparlo la celda lo mandaría con el Sello de ERPlora declarando que presenta el
    // cliente — el fault 4112 medido contra prewww el 2026-09-02.
    let xml = match route {
        TransmitRoute::Gateway(access) => {
            aeat::set_representative(&xml, Some(access.presenter()), &issuer_nif)
        }
        TransmitRoute::Direct(_) => aeat::set_representative(&xml, None, &issuer_nif),
    };
    let xml_storage_path = archive_transmission_xml(host, &record_id, &xml).await?;
    // Se calcula UNA vez y se usa dos: en el sobre que ve la celda y en la fila que lo recuerda.
    // Derivarlo dos veces es cómo el registro acabaría diciendo que salió bajo una clave que la
    // celda nunca vio (verifactu#75).
    let delivery_id = rechain_delivery_id(&record_id, &anchor_hash);
    let body = match route {
        TransmitRoute::Direct(identity) => {
            aeat::post_soap(destination.endpoint, identity.clone(), &xml).await?
        }
        // El id de correlación NO es el del registro: el re-anclado manda bytes DISTINTOS para el
        // mismo registro, y reutilizar la clave es justo el `409 transmission_digest_mismatch`
        // que la celda tiene reservado. Lleva el ancla dentro, que es lo que cambió: mismo ancla
        // ⇒ mismos bytes ⇒ misma clave, que es la idempotencia que sí se quiere.
        TransmitRoute::Gateway(access) => {
            crate::gateway::transmit_via_gateway(
                host,
                &ctx.hub_id,
                access,
                &crate::gateway::GatewayEnvelope {
                    hub_id: &ctx.hub_id,
                    obligado_nif: &issuer_nif,
                    environment: &destination.environment,
                    transmission_id: &delivery_id,
                    xml: &xml,
                },
            )
            .await?
        }
    };
    let resp = aeat::parse_response(&body);

    let note = format!(
        "re-anclado automáticamente tras {} ({}) y reintentado sobre la huella {}…",
        if rejection.codigo_error.is_empty() {
            "rechazo de encadenamiento"
        } else {
            &rejection.codigo_error
        },
        rejection.descripcion_error.trim(),
        short(&chain::normalize_hash(&anchor.record_hash)),
    );
    let (mut ops, events, success) = response_ops(
        record,
        &resp,
        destination,
        &xml,
        &xml_storage_path,
        event_id,
        &ctx.now,
        &delivery_id,
        Some(&note),
    );
    // El ancla y el re-encadenado se aplican ANTES del resultado del reintento (orden del Output).
    ops.insert(0, rechain_op);
    ops.insert(0, anchor_op);
    Ok(Some((ops, events, success)))
}

/// Guarda el XML con una clave estable por registro. Los reintentos sobrescriben atómicamente el
/// mismo objeto con el mismo contenido; el estado/contador de intentos vive en la BD.
pub(crate) async fn archive_transmission_xml(
    host: &dyn NativeHost,
    record_id: &str,
    xml: &str,
) -> Result<String> {
    if record_id.is_empty()
        || !record_id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    {
        return Err(RuntimeError::Storage(
            "id de registro no válido para archivar XML".to_string(),
        ));
    }
    host.write_static_file(
        &format!("xml/{record_id}.xml"),
        xml.as_bytes(),
        "application/xml",
    )
    .await
}

/// El id con el que se presenta UNA entrega re-anclada.
///
/// No es el del registro, y esa diferencia es el motivo de que la columna `transmission_id` no
/// sea redundante con `id` (verifactu#75): el re-anclado manda bytes DISTINTOS para el mismo
/// registro, así que reutilizar la clave sería el `409 transmission_digest_mismatch` que la celda
/// tiene reservado. Lleva el ancla dentro, que es lo que cambió — mismo ancla ⇒ mismos bytes ⇒
/// misma clave, que es la idempotencia que sí se quiere.
pub(crate) fn rechain_delivery_id(record_id: &str, anchor_hash: &str) -> String {
    format!("{record_id}-rechain-{}", short(anchor_hash))
}

/// Intención UPDATE del registro tras un intento de transmisión.
///
/// `transmission_id` es el id con el que salió ESTA entrega — la `Idempotency-Key` por la que
/// indexa la celda fiscal cuando la vía es la pasarela. Se persiste junto al digest de los bytes
/// que se archivan aquí mismo, que es lo que permite a un lector posterior decidir si el XML
/// guardado sigue siendo el que viajó (verifactu#75).
#[allow(clippy::too_many_arguments)]
pub(crate) fn apply_transmission(
    record_id: &str,
    status: &str,
    code: &str,
    message: &str,
    csv: &str,
    xml: &str,
    xml_storage_path: &str,
    transmission_id: &str,
    retry_increment: i64,
) -> Operation {
    op(
        "verifactu._apply_transmission",
        json!({
            "record_id": record_id,
            "status": status,
            "aeat_response_code": code,
            "aeat_response_message": message,
            "aeat_csv": csv,
            "xml_content": xml,
            "xml_storage_path": xml_storage_path,
            // La huella de la entrega. El digest sale de la MISMA función que el sobre del
            // gateway, así que lo que la fila guarda y lo que la celda tiene que devolver como
            // `request_sha256` no pueden ser dos números distintos.
            "xml_sha256": crate::gateway::xml_sha256(xml),
            "transmission_id": transmission_id,
            "retry_increment": retry_increment,
        }),
    )
}

// ── process_contingency_queue (issue verifactu#7) ─────────────────────────────

/// Procesa por lotes la cola de contingencia (tarea programada cada 5 min o trigger manual):
/// lee las entradas elegibles (`pending`/`retrying` con `next_attempt_at <= now`) por prioridad y
/// antigüedad, y reintenta la transmisión de cada una vía [`transmit_one`]. Éxito → sale de la
/// cola; fallo → backoff. Devuelve un evento resumen `{successful, failed}`.
pub(crate) async fn process_contingency_queue(
    input: &Json,
    host: &dyn NativeHost,
) -> Result<Output> {
    let (payload, ctx) = split_input(input)?;
    let limit = int_field(&payload, "limit", 100).clamp(1, 500);

    let config = read_config(host, &ctx.hub_id).await?.ok_or_else(|| {
        RuntimeError::Native("VeriFactu sin configurar (verifactu.config.save)".into())
    })?;
    // Gate: sin NINGUNA vía (certificado o pasarela) no hay nada que transmitir; deja la cola
    // como está — los hubs sin cert pero con la pasarela enrolada por fin drenan (hub#1432).
    if !can_transmit(host, &ctx.hub_id, &config).await? {
        return Ok(Output::new());
    }

    let eligible = host
        .read(
            "SELECT record_id FROM verifactu_contingencyqueue \
             WHERE hub_id = :hub_id AND is_deleted = 0 AND status IN ('pending','retrying') \
             AND (next_attempt_at IS NULL OR next_attempt_at <= :now) \
             ORDER BY priority ASC, queued_at ASC LIMIT :limit",
            &params(json!({ "hub_id": ctx.hub_id, "now": ctx.now, "limit": limit })),
        )
        .await?;

    // 3 ids por registro (evento + cola + ancla de recuperación); reservamos 1 para el resumen.
    let max_records = (ctx.new_ids.len().saturating_sub(1)) / 3;
    let mut out = Output::new();
    let mut id_idx = 0usize;
    let (mut successful, mut failed) = (0i64, 0i64);

    for q in eligible.iter().take(max_records) {
        let rid = str_field(q, "record_id");
        let rec = host
            .read(
                "SELECT * FROM verifactu_record WHERE id = :rid AND hub_id = :hub_id AND is_deleted = 0 LIMIT 1",
                &params(json!({ "rid": rid, "hub_id": ctx.hub_id })),
            )
            .await?
            .into_iter()
            .next();
        let rec = match rec {
            Some(r) => r,
            None => continue, // registro borrado: ignorar la entrada huérfana
        };
        if str_field(&rec, "status") == "accepted" {
            // Ya aceptado: limpiar la entrada de cola obsoleta.
            out = out.with_operation(op(
                "verifactu._resolve_contingency",
                json!({ "record_id": rid }),
            ));
            continue;
        }
        let event_id = ctx.new_ids[id_idx].clone();
        let queue_id = ctx.new_ids[id_idx + 1].clone();
        // Tercer id: el ancla de recuperación automática. La cola de contingencia es JUSTO el
        // sitio donde engancha el reintento tras restaurar un backup (hub#287).
        let recovery_id = ctx.new_ids[id_idx + 2].clone();
        id_idx += 3;
        let (ops, events, success) = transmit_one(
            host,
            &ctx,
            &rec,
            &config,
            &event_id,
            &queue_id,
            &recovery_id,
            // ESTE es el envío que declara `Incidencia=S`: sale de la cola de contingencia.
            Remission::FromContingency,
        )
        .await?;
        for e in events {
            out = out.with_event(e);
        }
        for o in ops {
            out = out.with_operation(o);
        }
        if success {
            successful += 1;
        } else {
            failed += 1;
        }
    }

    let summary_id = ctx.new_ids.get(id_idx).cloned().unwrap_or_default();
    out = out.with_operation(op(
        "verifactu._insert_event",
        json!({
            "event_id": summary_id,
            "record_id": Json::Null,
            "event_type": "contingency_processed",
            "severity": if failed > 0 { "warning" } else { "info" },
            "message": format!("Cola de contingencia procesada: {successful} enviados, {failed} con error"),
            "details": details_for("verifactu.contingency_processed", json!({ "successful": successful, "failed": failed })),
            "timestamp": ctx.now,
        }),
    ));
    Ok(out)
}

// ── run_diagnostics: prueba en vivo (cert + huella + QR + envío AEAT) ──────────

#[cfg(test)]
mod tests {
    use super::{archive_transmission_xml, derive_tax_rate, fault_reason, NativeHost, Params, Result};
    use serde_json::Value as Json;
    use std::sync::Mutex;

    // ── a delivered body that is not a verdict is a VISIBLE failure (2026-09-02) ──────────────

    /// The live bug (hub#1452): a SOAP Fault filed as an all-empty verdict — «AEAT (testing): » with no
    /// code, no message, no clue. The Fault below is the AEAT preproduction's real answer to
    /// the old demo tax id (`B00000000`, Fault 4116), captured on 2026-09-02.
    #[test]
    fn a_soap_fault_is_a_failure_that_names_the_fault() {
        let body = r#"<?xml version="1.0" encoding="UTF-8"?><env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"><env:Body><env:Fault><faultcode>env:Client</faultcode><faultstring>Codigo[4116].Error en la cabecera: el campo NIF del bloque ObligadoEmision tiene un formato incorrecto.. NIF:B00000000. NOMBRE_RAZON:ERPlora Demo SL</faultstring></env:Fault></env:Body></env:Envelope>"#;

        let reason = fault_reason(body).expect("a Fault is never a verdict");

        assert!(reason.contains("4116"), "the fault code must survive: {reason}");
        assert!(reason.contains("Fault"), "the reason says WHAT came back: {reason}");
    }

    /// The positive control: a REAL verdict (the AEAT's own `AceptadoConErrores` fixture) must
    /// flow through untouched — `fault_reason` returning `Some` for it would send every
    /// legitimate answer to the retry queue.
    #[test]
    fn a_real_verdict_is_not_a_fault() {
        let body = include_str!("../tests/fixtures/alta_2007_aceptado_con_errores_2026-08-02.xml");
        assert_eq!(fault_reason(body), None);
    }

    /// An intermediary's HTML (a proxy error page, a captive portal) is not a verdict either,
    /// and it carries no faultstring — the reason still says something a human can act on.
    #[test]
    fn unrecognisable_bodies_fail_visibly_too() {
        let reason = fault_reason("<html><body>502 Bad Gateway</body></html>")
            .expect("HTML is not a verdict");
        assert!(reason.contains("veredicto"), "{reason}");
    }

    // ── the two roads of ADR-0320, resolved in one place (hub#1432) ───────────────────────────

    /// A throwaway mTLS identity so a fake host can answer the capability like the real broker.
    fn throwaway_identity() -> reqwest::Identity {
        use openssl::asn1::Asn1Time;
        use openssl::hash::MessageDigest;
        use openssl::nid::Nid;
        let group = openssl::ec::EcGroup::from_curve_name(Nid::X9_62_PRIME256V1).unwrap();
        let pkey = openssl::pkey::PKey::from_ec_key(openssl::ec::EcKey::generate(&group).unwrap())
            .unwrap();
        let mut name = openssl::x509::X509NameBuilder::new().unwrap();
        name.append_entry_by_nid(Nid::COMMONNAME, "route-test")
            .unwrap();
        let name = name.build();
        let mut cert = openssl::x509::X509::builder().unwrap();
        cert.set_version(2).unwrap();
        cert.set_subject_name(&name).unwrap();
        cert.set_issuer_name(&name).unwrap();
        cert.set_pubkey(&pkey).unwrap();
        cert.set_not_before(&Asn1Time::days_from_now(0).unwrap())
            .unwrap();
        cert.set_not_after(&Asn1Time::days_from_now(1).unwrap())
            .unwrap();
        cert.sign(&pkey, MessageDigest::sha256()).unwrap();
        let bundle = format!(
            "{}\n{}",
            String::from_utf8(pkey.private_key_to_pem_pkcs8().unwrap()).unwrap(),
            String::from_utf8(cert.build().to_pem().unwrap()).unwrap(),
        );
        reqwest::Identity::from_pem(bundle.as_bytes()).unwrap()
    }

    /// Default host: NO certificate capability, NO gateway broker — the state of every hub that
    /// enrolled nothing.
    struct NoRoadHost;
    #[async_trait::async_trait]
    impl NativeHost for NoRoadHost {
        async fn read(&self, _sql: &str, _params: &Params) -> Result<Vec<Json>> {
            Ok(vec![])
        }
    }

    /// The common name the enrolled test hub is issued for. It has to match what the fake
    /// control plane mints, or the cross-check refuses the token — which is the point of it.
    const GATEWAY_CN: &str = "hub-gateway-test.fiscal.erplora.internal";

    /// A host that lends what hub#1459 says a host lends: an identity of its own, and a call to
    /// its own cloud. The enrolled, certless hub — the one that goes through the cell.
    struct GatewayHost;
    #[async_trait::async_trait]
    impl NativeHost for GatewayHost {
        async fn read(&self, _sql: &str, _params: &Params) -> Result<Vec<Json>> {
            Ok(vec![])
        }
        async fn machine_identity(
            &self,
            _hub_id: &str,
        ) -> Result<Option<erplora_runtime::gateway_identity::MachineIdentity>> {
            Ok(Some(erplora_runtime::gateway_identity::MachineIdentity {
                identity: throwaway_identity(),
                ca_pem: b"irrelevant-here".to_vec(),
                common_name: GATEWAY_CN.to_owned(),
            }))
        }
        async fn cloud_call(
            &self,
            _request: erplora_runtime::cloud_call::CloudRequest,
        ) -> Result<Option<erplora_runtime::cloud_call::CloudResponse>> {
            Ok(Some(erplora_runtime::cloud_call::CloudResponse {
                status: 200,
                body: serde_json::json!({
                    "token": "bearer",
                    "expires_in": 300,
                    "gateway_url": "https://cell.internal.example",
                    "obligado_nif": "B12345678",
                    "presenter_nif": "B27593136",
                    "presenter_name": "ERPLORA CLOUD SL",
                    "mtls_common_name": GATEWAY_CN,
                })
                .to_string(),
            }))
        }
    }

    /// 🔒 REGRESIÓN (hub#1432, lo que la tarea exige): un hub sin certificado Y sin pasarela no
    /// llega a ningún cable — ni a la AEAT directa (hoy lo garantizaba `build_identity`) ni a la
    /// celda. La ruta es la ÚNICA puerta y contesta con el error visible; la cola deja los
    /// registros `pending` en vez de quemar reintentos.
    #[tokio::test]
    async fn a_hub_with_neither_certificate_nor_gateway_never_reaches_any_wire() {
        let host = NoRoadHost;
        let config = serde_json::json!({ "environment": "testing" });

        let err = crate::config::resolve_route(&host, "hub-no-road", &config)
            .await
            .err()
            .expect("no road = a visible error, never a silent direct");
        let message = err.to_string();
        assert!(message.contains("vía de transmisión"), "{message}");
        assert!(message.contains("pasarela"), "{message}");

        assert!(
            !crate::config::can_transmit(&host, "hub-no-road", &config)
                .await
                .unwrap(),
            "the contingency gate must leave the queue untouched"
        );
    }

    /// 🔒 REGRESIÓN (hub#1460): `resolve_route` sube por DELANTE de la validación —para estampar
    /// el `Representante` en el XML que se valida y archiva— pero su error se DIFIERE: un sobre
    /// que no cumple el esquema se marca `rejected` LOCALMENTE aunque además no haya vía.
    /// Propagar el error de la vía primero devolvería este registro a la cola a reintentarse para
    /// siempre con un XML que no puede validar nunca — el caso real es la carrera en la que
    /// `can_transmit` pasó y el acuñado del token falló un instante después.
    #[tokio::test]
    async fn an_invalid_envelope_is_rejected_locally_even_when_no_route_resolves() {
        let record = serde_json::json!({
            "id": "rec-xsd-no-road",
            "record_type": "alta",
            "environment": "testing",
            "issuer_nif": "B12345678",
            "is_first_record": 1,
            "sequence_number": 1,
            // Frozen from a previous attempt, and it can never validate: no Cabecera at all.
            "xml_content": "<sum:RegFactuSistemaFacturacion></sum:RegFactuSistemaFacturacion>",
        });
        let ctx = crate::util::Ctx {
            hub_id: "hub-no-road".to_owned(),
            now: "2026-09-03T10:00:00Z".to_owned(),
            new_ids: Vec::new(),
        };
        let config = serde_json::json!({ "environment": "testing" });

        let (ops, events, success) = super::transmit_one(
            &NoRoadHost,
            &ctx,
            &record,
            &config,
            "event-1",
            "queue-1",
            "",
            super::Remission::Punctual,
        )
        .await
        .expect("an invalid envelope is a local outcome, never the route's error");

        assert!(!success);
        let applied = ops
            .iter()
            .find(|o| o.command == "verifactu._apply_transmission")
            .expect("the record must be marked rejected, not sent back to the queue");
        assert_eq!(
            applied.params.get("status"),
            Some(&serde_json::json!("rejected"))
        );
        assert_eq!(
            applied.params.get("aeat_response_code"),
            Some(&serde_json::json!("XSD"))
        );
        assert!(
            events
                .iter()
                .any(|e| e.name == crate::events::EVENT_RECORD_REJECTED),
            "the rejection must be visible as an event"
        );
    }

    /// Sin certificado pero con la pasarela enrolada, la ruta es la celda — jamás la AEAT
    /// directa sin identidad, que era el modelo que saas#1435 retiró.
    #[tokio::test]
    async fn a_certless_hub_with_a_gateway_resolves_the_gateway_route() {
        let host = GatewayHost;
        let config = serde_json::json!({ "environment": "testing" });

        let route = crate::config::resolve_route(&host, "hub-route-gateway", &config)
            .await
            .unwrap();
        assert!(matches!(route, crate::config::TransmitRoute::Gateway(_)));
        assert!(
            crate::config::can_transmit(&host, "hub-route-gateway", &config)
                .await
                .unwrap()
        );
    }

    /// 🔒 REGRESIÓN (hub#985 §2 — hub#1460): la vía por la celda lleva encima **quién presenta**,
    /// y ese par sale del token FIRMADO por el plano de control, no de la config del hub ni del
    /// slot del certificado.
    ///
    /// Es la mitad que el guard de `tests/representative_from_signed_identity.rs` no puede ver:
    /// allí se comprueba la REGLA (presentador ≠ obligado ⇒ bloque), aquí que el dato que la
    /// alimenta llega de verdad desde el token y no se pierde por el camino — que es como
    /// `resolve_access` lo trataba hasta ahora, leyéndolo del JSON y tirándolo al construir el
    /// acceso.
    #[tokio::test]
    async fn the_gateway_route_carries_the_signed_presenter_into_the_envelope() {
        let config = serde_json::json!({ "environment": "testing" });
        let route = crate::config::resolve_route(&GatewayHost, "hub-presenter", &config)
            .await
            .unwrap();

        let crate::config::TransmitRoute::Gateway(access) = route else {
            panic!("a certless enrolled hub goes through the cell");
        };
        let presenter = access.presenter();
        // Exactly what the fake control plane signed above — not a constant of this module.
        assert_eq!(presenter.nif, "B27593136");
        assert_eq!(presenter.name, "ERPLORA CLOUD SL");

        // And it reaches the envelope: the obligado of the mocked token is another NIF, so this is
        // a representation and the block is emitted with the SIGNED identity.
        let envelope = "<sum:Cabecera><sum1:ObligadoEmision><sum1:NombreRazon>CLIENTE SL\
             </sum1:NombreRazon><sum1:NIF>B12345678</sum1:NIF>\
             </sum1:ObligadoEmision></sum:Cabecera>";
        let stamped = crate::aeat::set_representative(envelope, Some(presenter), "B12345678");
        assert!(
            stamped.contains(
                "<sum1:Representante><sum1:NombreRazon>ERPLORA CLOUD SL</sum1:NombreRazon>\
                 <sum1:NIF>B27593136</sum1:NIF></sum1:Representante>"
            ),
            "{stamped}"
        );
    }

    /// El certificado del core GANA: un negocio con su propio `.p12` sigue firmando y
    /// transmitiendo directo, exactamente como hoy — la pasarela ni se consulta.
    #[tokio::test]
    async fn a_certified_hub_still_resolves_direct_without_asking_the_broker() {
        struct CertHost;
        #[async_trait::async_trait]
        impl NativeHost for CertHost {
            async fn read(&self, _sql: &str, _params: &Params) -> Result<Vec<Json>> {
                Ok(vec![])
            }
            async fn certificate_identity(&self, _hub_id: &str) -> Result<reqwest::Identity> {
                Ok(throwaway_identity())
            }
            async fn machine_identity(
                &self,
                _hub_id: &str,
            ) -> Result<Option<erplora_runtime::gateway_identity::MachineIdentity>> {
                panic!("the gateway road must not be resolved when the core certificate signs");
            }
            async fn cloud_call(
                &self,
                _request: erplora_runtime::cloud_call::CloudRequest,
            ) -> Result<Option<erplora_runtime::cloud_call::CloudResponse>> {
                panic!("the control plane must not be asked when the core certificate signs");
            }
        }

        let config = serde_json::json!({ "certificate_source": "core" });
        let route = crate::config::resolve_route(&CertHost, "hub-1", &config)
            .await
            .unwrap();
        assert!(matches!(route, crate::config::TransmitRoute::Direct(_)));
    }

    /// 🔒 REGRESIÓN de punta a punta (hub#985 §2 — hub#1460): **los bytes que salen por el cable**
    /// hacia la celda llevan el `Representante` de la identidad FIRMADA.
    ///
    /// Los dos guards anteriores miran una mitad cada uno —la regla (`tests/`) y el dato que la
    /// alimenta (`resolve_route`)—, y las dos pueden estar verdes con el estampado desconectado
    /// del camino real. Esto conduce `transmit_one` entero contra una celda de mentira, decodifica
    /// el `xml_b64` que recibió y mira el sobre que de verdad viajó: es el mismo que se archiva y
    /// el mismo cuyo sha256 comparará el canario de hub#1461.
    #[tokio::test]
    async fn the_bytes_that_leave_for_the_cell_carry_the_signed_representante() {
        use base64::Engine as _;
        use std::sync::Arc;
        use tokio::io::{AsyncReadExt as _, AsyncWriteExt as _};

        /// The obligado is the CLIENT; the presenter the fake control plane signs is ERPlora.
        const OBLIGADO_NIF: &str = "B12345678";

        // A cell that records what it was handed and answers a receipt echoing the AEAT.
        let seen: Arc<Mutex<Option<String>>> = Arc::new(Mutex::new(None));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let recorder = Arc::clone(&seen);
        tokio::spawn(async move {
            let Ok((mut socket, _)) = listener.accept().await else {
                return;
            };
            let mut buffer = Vec::new();
            let mut chunk = [0u8; 8192];
            // Read until the JSON body is complete — the envelope is bigger than one chunk.
            while let Ok(n) = socket.read(&mut chunk).await {
                if n == 0 {
                    break;
                }
                buffer.extend_from_slice(&chunk[..n]);
                if buffer.windows(2).any(|w| w == b"\r\n") && buffer.ends_with(b"}") {
                    break;
                }
            }
            let raw = String::from_utf8_lossy(&buffer).into_owned();
            *recorder.lock().unwrap() = Some(raw.clone());
            // Like the REAL cell: the digest is recomputed over the bytes IT decoded, never
            // copied from the envelope. That way the canary of hub#1461 compares two independent
            // computations of the same fact — if the hub digested anything else, this goes red.
            let request_sha256 = raw
                .split("\r\n\r\n")
                .nth(1)
                .and_then(|body| serde_json::from_str::<Json>(body).ok())
                .and_then(|envelope| {
                    let b64 = envelope["xml_b64"].as_str()?.to_owned();
                    base64::engine::general_purpose::STANDARD.decode(b64).ok()
                })
                .map(|xml| {
                    use sha2::Digest as _;
                    sha2::Sha256::digest(&xml)
                        .iter()
                        .map(|byte| format!("{byte:02x}"))
                        .collect::<String>()
                })
                // With no digest the delivery is refused upstream, which is what should happen
                // if this fake cell ever stops resembling the real one.
                .unwrap_or_default();
            let receipt = serde_json::json!({
                "schema_version": 1,
                "transmission_id": "record-1460",
                "request_sha256": request_sha256,
                "aeat_http_status": 200,
                "aeat_response_b64": base64::engine::general_purpose::STANDARD.encode(
                    "<soapenv:Envelope><EstadoEnvio>Correcto</EstadoEnvio>\
                     <EstadoRegistro>Correcto</EstadoRegistro></soapenv:Envelope>",
                ),
                "aeat_response_sha256": "00".repeat(32),
                "received_at": "2026-09-03T04:00:00Z",
            })
            .to_string();
            let answer = format!(
                "HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{receipt}",
                receipt.len()
            );
            let _ = socket.write_all(answer.as_bytes()).await;
            let _ = socket.shutdown().await;
        });

        /// The enrolled certless hub: it lends its machine identity and its cloud call, and the
        /// fake control plane points it at the cell above.
        struct CellHost {
            url: String,
            archived: Mutex<Vec<String>>,
        }
        #[async_trait::async_trait]
        impl NativeHost for CellHost {
            async fn read(&self, _sql: &str, _params: &Params) -> Result<Vec<Json>> {
                Ok(vec![])
            }
            async fn write_static_file(
                &self,
                relative_path: &str,
                bytes: &[u8],
                _content_type: &str,
            ) -> Result<String> {
                self.archived
                    .lock()
                    .unwrap()
                    .push(String::from_utf8_lossy(bytes).into_owned());
                Ok(format!("modules/verifactu/{relative_path}"))
            }
            async fn machine_identity(
                &self,
                _hub_id: &str,
            ) -> Result<Option<erplora_runtime::gateway_identity::MachineIdentity>> {
                Ok(Some(erplora_runtime::gateway_identity::MachineIdentity {
                    identity: throwaway_identity(),
                    ca_pem: b"unused-over-plain-http".to_vec(),
                    common_name: GATEWAY_CN.to_owned(),
                }))
            }
            async fn cloud_call(
                &self,
                _request: erplora_runtime::cloud_call::CloudRequest,
            ) -> Result<Option<erplora_runtime::cloud_call::CloudResponse>> {
                Ok(Some(erplora_runtime::cloud_call::CloudResponse {
                    status: 200,
                    body: serde_json::json!({
                        "token": "bearer",
                        "expires_in": 300,
                        "gateway_url": self.url,
                        "obligado_nif": OBLIGADO_NIF,
                        "presenter_nif": "B27593136",
                        "presenter_name": "ERPLORA CLOUD SL",
                        "mtls_common_name": GATEWAY_CN,
                    })
                    .to_string(),
                }))
            }
        }

        let host = CellHost {
            url: url.clone(),
            archived: Mutex::new(Vec::new()),
        };
        let ctx = crate::util::Ctx {
            hub_id: "hub-1460".to_owned(),
            now: "2026-09-03T04:00:00Z".to_owned(),
            new_ids: Vec::new(),
        };
        let hash = crate::chain::alta_hash(
            OBLIGADO_NIF,
            "A-1",
            "2026-09-03",
            "F2",
            21.0,
            121.0,
            "",
            "2026-09-03T04:00:00Z",
        );
        let record = serde_json::json!({
            "id": "record-1460",
            "record_type": "alta",
            "environment": "testing",
            "issuer_nif": OBLIGADO_NIF,
            "issuer_name": "PELUQUERIA LA MODERNA SL",
            "invoice_number": "A-1",
            "invoice_date": "2026-09-03",
            "invoice_type": "F2",
            "description": "Servicio",
            "base_amount": 10000,
            "tax_rate": 21.0,
            "tax_amount": 2100,
            "total_amount": 12100,
            "sequence_number": 1,
            "is_first_record": 1,
            "generation_timestamp": "2026-09-03T04:00:00Z",
            "record_hash": hash,
        });
        let config = serde_json::json!({
            "environment": "testing",
            "producer_facts": {
                "NombreRazon": "ERPLORA CLOUD SL",
                "NIF": "B27593136",
                "NombreSistemaInformatico": "ERPlora Hub",
                "IdSistemaInformatico": "EC",
                "TipoUsoPosibleSoloVerifactu": "S",
                "TipoUsoPosibleMultiOT": "S",
                "IndicadorMultiplesOT": "N",
            },
        });

        let (ops, _events, success) = super::transmit_one(
            &host,
            &ctx,
            &record,
            &config,
            "event-1",
            "queue-1",
            "",
            super::Remission::Punctual,
        )
        .await
        .expect("the cell answered a receipt");

        let request = seen.lock().unwrap().clone().expect("the cell was called");
        let body = request.split("\r\n\r\n").nth(1).expect("a JSON body");
        let envelope: Json = serde_json::from_str(body).expect("the envelope is JSON");
        let xml = String::from_utf8(
            base64::engine::general_purpose::STANDARD
                .decode(envelope["xml_b64"].as_str().expect("xml_b64"))
                .expect("base64"),
        )
        .expect("utf8");

        assert!(
            xml.contains(
                "<sum1:Representante><sum1:NombreRazon>ERPLORA CLOUD SL</sum1:NombreRazon>\
                 <sum1:NIF>B27593136</sum1:NIF></sum1:Representante>"
            ),
            "the bytes on the wire must declare the signed presenter: {xml}"
        );
        // And the archive holds the SAME bytes — the canary of hub#1461 compares this sha256.
        assert_eq!(
            host.archived.lock().unwrap().as_slice(),
            std::slice::from_ref(&xml),
            "what was archived is what was transmitted"
        );

        // 🔒 POSITIVE CONTROL for the canary (hub#1461). The cell above recomputes the digest
        // exactly like the real one, so this road is the HONEST one: the delivery must reach a
        // verdict. Without this half, a canary that refused EVERY receipt would leave the test
        // green — `transmit_one` returns `Ok` when it queues contingency too — and the whole
        // fleet would stop filing invoices with nobody noticing.
        assert!(success, "the honest delivery must be filed, not queued");
        let applied = ops
            .iter()
            .find(|o| o.command == "verifactu._apply_transmission")
            .expect("the AEAT verdict must reach the record");
        assert_eq!(
            applied.params.get("status"),
            Some(&serde_json::json!("accepted")),
            "the receipt held up, so the verdict is filed"
        );
        assert!(
            !ops.iter()
                .any(|o| o.command == "verifactu._enqueue_contingency"),
            "a receipt whose digest matches is NOT a transmission failure"
        );
    }

    /// 🔒 REGRESIÓN de punta a punta (hub#1436): **por la celda también se recupera la cadena.**
    ///
    /// Es el caso que la vía gateway no cubría: un hub sin certificado restaura un backup, su
    /// cadena local retrocede, la AEAT rechaza el envío por encadenamiento (2007) y hasta ahora el
    /// motor se saltaba el auto-rechain a propósito —consultaba con la identity del core, que ese
    /// hub no tiene— dejando el rechazo registrado y **ninguna** recuperación disponible: la
    /// manual (`recover_from_aeat`) consulta por el mismo sitio y fallaba igual.
    ///
    /// Conduce `transmit_one` entero contra una celda de mentira que atiende las TRES llamadas de
    /// la secuencia —alta rechazada → consulta → reenvío re-anclado— y mira los bytes de cada una.
    /// Lo que clava, y que ningún test de XML suelto puede ver:
    ///
    /// 1. la consulta **viaja por la celda** y lleva el `IndicadorRepresentante` (sin él la AEAT
    ///    devuelve un 4112 en vez de la cadena del cliente), y **no** un bloque `Representante`,
    ///    que su esquema no admite;
    /// 2. el reenvío re-anclado lleva el `Representante` de la identidad FIRMADA — el sobre se
    ///    reconstruye con `build_soap` y sale sin él si nadie lo estampa;
    /// 3. las tres llamadas pasan el canario del digest (hub#1461), porque la celda de mentira
    ///    recalcula el sha256 sobre lo que decodifica, como la real;
    /// 4. y el DESENLACE: `transmit_one` devuelve `Ok` también cuando encola contingencia, así que
    ///    se afirma el ancla, el re-encadenado y el veredicto aceptado — no solo que no explotó.
    #[tokio::test]
    async fn a_certless_hub_recovers_its_chain_through_the_cell() {
        use base64::Engine as _;
        use std::sync::Arc;
        use tokio::io::{AsyncReadExt as _, AsyncWriteExt as _};

        const OBLIGADO_NIF: &str = "B12345678";
        // La huella que la AEAT dice tener por último eslabón: el ancla de la recuperación.
        const ANCHOR_HASH: &str =
            "3056799E8B154276ED2F71108D8570168FD8FE345428C5270459C90AEFBF3696";

        // Rechazo de encadenamiento tal como llega: `Incorrecto` + 2007.
        let chaining_rejection = "<soapenv:Envelope><EstadoEnvio>Incorrecto</EstadoEnvio>\
             <EstadoRegistro>Incorrecto</EstadoRegistro>\
             <CodigoErrorRegistro>2007</CodigoErrorRegistro>\
             <DescripcionErrorRegistro>No debe informarse como primer registro, existen \
             facturas emitidas con el obligado emisión y el sistema informático actual.\
             </DescripcionErrorRegistro></soapenv:Envelope>"
            .to_owned();
        // Un registro en la respuesta de consulta, con la forma que el parser agrupa POR
        // registro (`RegistroRespuestaConsultaFactuSistemaFacturacion`).
        let consult_answer = format!(
            "<env:Envelope><env:Body><tikLRRC:RespuestaConsultaFactuSistemaFacturacion>\
             <tikLRRC:RegistroRespuestaConsultaFactuSistemaFacturacion>\
             <tikLRRC:IDFactura><tik:IDEmisorFactura>{OBLIGADO_NIF}</tik:IDEmisorFactura>\
             <tik:NumSerieFactura>PREVIA-9</tik:NumSerieFactura>\
             <tik:FechaExpedicionFactura>02-09-2026</tik:FechaExpedicionFactura></tikLRRC:IDFactura>\
             <tikLRRC:DatosRegistroFacturacion>\
             <tikLRRC:FechaHoraHusoGenRegistro>2026-09-02T10:00:00Z</tikLRRC:FechaHoraHusoGenRegistro>\
             <tikLRRC:Huella>{ANCHOR_HASH}</tikLRRC:Huella></tikLRRC:DatosRegistroFacturacion>\
             <tikLRRC:EstadoRegistro><tikLRRC:EstadoRegistro>Correcto</tikLRRC:EstadoRegistro>\
             </tikLRRC:EstadoRegistro>\
             </tikLRRC:RegistroRespuestaConsultaFactuSistemaFacturacion>\
             </tikLRRC:RespuestaConsultaFactuSistemaFacturacion></env:Body></env:Envelope>"
        );
        let accepted = "<soapenv:Envelope><EstadoEnvio>Correcto</EstadoEnvio>\
             <EstadoRegistro>Correcto</EstadoRegistro><CSV>CSV-RECHAINED</CSV></soapenv:Envelope>"
            .to_owned();

        // The cell: answers the queued AEAT bodies in order and records every envelope it got.
        let seen: Arc<Mutex<Vec<Json>>> = Arc::new(Mutex::new(Vec::new()));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let recorder = Arc::clone(&seen);
        let answers = vec![chaining_rejection, consult_answer, accepted];
        tokio::spawn(async move {
            for aeat_body in answers {
                let Ok((mut socket, _)) = listener.accept().await else {
                    return;
                };
                let mut buffer = Vec::new();
                let mut chunk = [0u8; 8192];
                while let Ok(n) = socket.read(&mut chunk).await {
                    if n == 0 {
                        break;
                    }
                    buffer.extend_from_slice(&chunk[..n]);
                    if buffer.windows(2).any(|w| w == b"\r\n") && buffer.ends_with(b"}") {
                        break;
                    }
                }
                let raw = String::from_utf8_lossy(&buffer).into_owned();
                let envelope: Json = raw
                    .split("\r\n\r\n")
                    .nth(1)
                    .and_then(|body| serde_json::from_str(body).ok())
                    .unwrap_or(Json::Null);
                recorder.lock().unwrap().push(envelope.clone());
                // Like the real cell: the digest is recomputed over what IT decoded.
                let request_sha256 = envelope["xml_b64"]
                    .as_str()
                    .and_then(|b64| base64::engine::general_purpose::STANDARD.decode(b64).ok())
                    .map(|xml| {
                        use sha2::Digest as _;
                        sha2::Sha256::digest(&xml)
                            .iter()
                            .map(|byte| format!("{byte:02x}"))
                            .collect::<String>()
                    })
                    .unwrap_or_default();
                let receipt = serde_json::json!({
                    "schema_version": 1,
                    "request_sha256": request_sha256,
                    "aeat_http_status": 200,
                    "aeat_response_b64":
                        base64::engine::general_purpose::STANDARD.encode(&aeat_body),
                })
                .to_string();
                let answer = format!(
                    "HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{receipt}",
                    receipt.len()
                );
                let _ = socket.write_all(answer.as_bytes()).await;
                let _ = socket.shutdown().await;
            }
        });

        struct CellHost {
            url: String,
        }
        #[async_trait::async_trait]
        impl NativeHost for CellHost {
            async fn read(&self, _sql: &str, _params: &Params) -> Result<Vec<Json>> {
                Ok(vec![])
            }
            async fn write_static_file(
                &self,
                relative_path: &str,
                _bytes: &[u8],
                _content_type: &str,
            ) -> Result<String> {
                Ok(format!("modules/verifactu/{relative_path}"))
            }
            async fn machine_identity(
                &self,
                _hub_id: &str,
            ) -> Result<Option<erplora_runtime::gateway_identity::MachineIdentity>> {
                Ok(Some(erplora_runtime::gateway_identity::MachineIdentity {
                    identity: throwaway_identity(),
                    ca_pem: b"unused-over-plain-http".to_vec(),
                    common_name: GATEWAY_CN.to_owned(),
                }))
            }
            async fn cloud_call(
                &self,
                _request: erplora_runtime::cloud_call::CloudRequest,
            ) -> Result<Option<erplora_runtime::cloud_call::CloudResponse>> {
                Ok(Some(erplora_runtime::cloud_call::CloudResponse {
                    status: 200,
                    body: serde_json::json!({
                        "token": "bearer",
                        "expires_in": 300,
                        "gateway_url": self.url,
                        "obligado_nif": OBLIGADO_NIF,
                        "presenter_nif": "B27593136",
                        "presenter_name": "ERPLORA CLOUD SL",
                        "mtls_common_name": GATEWAY_CN,
                    })
                    .to_string(),
                }))
            }
        }

        let host = CellHost { url };
        let ctx = crate::util::Ctx {
            hub_id: "hub-1436".to_owned(),
            now: "2026-09-03T06:00:00Z".to_owned(),
            new_ids: Vec::new(),
        };
        let hash = crate::chain::alta_hash(
            OBLIGADO_NIF,
            "A-1",
            "2026-09-03",
            "F2",
            21.0,
            121.0,
            "",
            "2026-09-03T06:00:00Z",
        );
        let record = serde_json::json!({
            "id": "record-1436",
            "record_type": "alta",
            "environment": "testing",
            "issuer_nif": OBLIGADO_NIF,
            "issuer_name": "PELUQUERIA LA MODERNA SL",
            "invoice_number": "A-1",
            "invoice_date": "2026-09-03",
            "invoice_type": "F2",
            "description": "Servicio",
            "base_amount": 10000,
            "tax_rate": 21.0,
            "tax_amount": 2100,
            "total_amount": 12100,
            "sequence_number": 1,
            "is_first_record": 1,
            "generation_timestamp": "2026-09-03T06:00:00Z",
            "record_hash": hash,
        });
        let config = serde_json::json!({
            "environment": "testing",
            "issuer_nif": OBLIGADO_NIF,
            "issuer_name": "PELUQUERIA LA MODERNA SL",
            "producer_facts": {
                "NombreRazon": "ERPLORA CLOUD SL",
                "NIF": "B27593136",
                "NombreSistemaInformatico": "ERPlora Hub",
                "IdSistemaInformatico": "EC",
                "TipoUsoPosibleSoloVerifactu": "S",
                "TipoUsoPosibleMultiOT": "S",
                "IndicadorMultiplesOT": "N",
            },
        });

        let (ops, _events, success) = super::transmit_one(
            &host,
            &ctx,
            &record,
            &config,
            "event-1436",
            "queue-1436",
            "recovery-1436",
            super::Remission::Punctual,
        )
        .await
        .expect("the cell answered every leg");

        let envelopes = seen.lock().unwrap().clone();
        assert_eq!(
            envelopes.len(),
            3,
            "alta rechazada → consulta → reenvío re-anclado: {envelopes:?}"
        );
        let xml_of = |envelope: &Json| -> String {
            String::from_utf8(
                base64::engine::general_purpose::STANDARD
                    .decode(envelope["xml_b64"].as_str().expect("xml_b64"))
                    .expect("base64"),
            )
            .expect("utf8")
        };

        // ── 1. La consulta salió POR LA CELDA, con el flag y sin el bloque ────────────────
        let consult = xml_of(&envelopes[1]);
        assert!(
            consult.contains("<con:ConsultaFactuSistemaFacturacion>"),
            "la segunda llamada tiene que ser la consulta: {consult}"
        );
        assert!(
            consult.contains("<sum1:IndicadorRepresentante>S</sum1:IndicadorRepresentante>"),
            "sin el flag la AEAT devuelve un 4112, no la cadena del cliente: {consult}"
        );
        assert!(
            !consult.contains("<sum1:Representante>"),
            "CabeceraConsultaSf no admite el bloque del alta: {consult}"
        );
        // Y su clave de correlación NO es la del registro: una consulta no se puede servir de
        // una caché de idempotencia.
        assert_ne!(
            envelopes[1]["transmission_id"], envelopes[0]["transmission_id"],
            "la consulta lleva su propia clave: {envelopes:?}"
        );

        // ── 2. El reenvío re-anclado declara al presentador FIRMADO ──────────────────────
        let retry = xml_of(&envelopes[2]);
        assert!(
            retry.contains(
                "<sum1:Representante><sum1:NombreRazon>ERPLORA CLOUD SL</sum1:NombreRazon>\
                 <sum1:NIF>B27593136</sum1:NIF></sum1:Representante>"
            ),
            "el sobre re-anclado se reconstruye desde cero y sale sin Representante si nadie lo \
             estampa: {retry}"
        );
        assert!(
            retry.contains(ANCHOR_HASH),
            "el reenvío encadena desde la huella que dio la AEAT: {retry}"
        );
        // Bytes distintos para el mismo registro ⇒ clave de correlación distinta, o el 409
        // `transmission_digest_mismatch` que la celda tiene reservado lo rechazaría para siempre.
        assert_ne!(
            envelopes[2]["transmission_id"], envelopes[0]["transmission_id"],
            "el re-anclado manda otros bytes: {envelopes:?}"
        );

        // ── 3. El DESENLACE: ancla + re-encadenado + veredicto aceptado ──────────────────
        assert!(success, "el reenvío re-anclado fue aceptado");
        assert!(
            ops.iter()
                .any(|o| o.command == "verifactu._insert_recovery"),
            "el ancla recuperada tiene que persistirse: {:?}",
            ops.iter().map(|o| &o.command).collect::<Vec<_>>()
        );
        assert!(
            ops.iter()
                .any(|o| o.command == "verifactu._rechain_record"),
            "el registro tiene que quedar re-encadenado: {:?}",
            ops.iter().map(|o| &o.command).collect::<Vec<_>>()
        );
        let applied = ops
            .iter()
            .find(|o| o.command == "verifactu._apply_transmission")
            .expect("el veredicto llega al registro");
        assert_eq!(
            applied.params.get("status"),
            Some(&serde_json::json!("accepted")),
            "tras re-anclar, la AEAT aceptó: {:?}",
            applied.params
        );
        assert!(
            !ops.iter()
                .any(|o| o.command == "verifactu._enqueue_contingency"),
            "una recuperación que funciona NO deja el registro en la cola"
        );
    }

    #[derive(Default)]
    struct ArchiveHost {
        writes: Mutex<Vec<(String, Vec<u8>, String)>>,
    }

    #[async_trait::async_trait]
    impl NativeHost for ArchiveHost {
        async fn read(&self, _sql: &str, _params: &Params) -> Result<Vec<Json>> {
            Ok(vec![])
        }

        async fn write_static_file(
            &self,
            relative_path: &str,
            bytes: &[u8],
            content_type: &str,
        ) -> Result<String> {
            self.writes.lock().unwrap().push((
                relative_path.to_string(),
                bytes.to_vec(),
                content_type.to_string(),
            ));
            Ok(format!("modules/verifactu/{relative_path}"))
        }
    }

    #[tokio::test]
    async fn xml_is_archived_before_transmission_under_a_stable_record_path() {
        let host = ArchiveHost::default();
        let path = archive_transmission_xml(&host, "record-123", "<soap />")
            .await
            .unwrap();

        assert_eq!(path, "modules/verifactu/xml/record-123.xml");
        assert_eq!(
            host.writes.lock().unwrap().as_slice(),
            &[(
                "xml/record-123.xml".to_string(),
                b"<soap />".to_vec(),
                "application/xml".to_string()
            )]
        );
    }

    #[test]
    fn tipo_unico_se_toma_del_desglose() {
        // Factura a 10% (peluquería/restaurante): el desglose tiene un único tipo → 10, no 21.
        let tb = r#"{"10.00":{"base":1100,"tax":110}}"#;
        assert_eq!(derive_tax_rate(tb, 1100.0, 110.0), 10.0);
        // Factura a 21% estándar.
        let tb21 = r#"{"21.00":{"base":10000,"tax":2100}}"#;
        assert_eq!(derive_tax_rate(tb21, 10000.0, 2100.0), 21.0);
        // Tipo reducido 4% (libros/alimentos).
        let tb4 = r#"{"4.00":{"base":500,"tax":20}}"#;
        assert_eq!(derive_tax_rate(tb4, 500.0, 20.0), 4.0);
    }

    #[test]
    fn mixto_o_vacio_cae_al_tipo_efectivo() {
        // Mixed 21%+10% in the old map: the row is single-rate → effective. The XML does emit one
        // line per real rate (`aeat::desglose`), so nothing declared is lost.
        let mixto = r#"{"21.00":{"base":10000,"tax":2100},"10.00":{"base":1000,"tax":100}}"#;
        let r = derive_tax_rate(mixto, 11000.0, 2200.0); // 2200/11000 = 20%
        assert_eq!(r, 20.0);
        // Desglose vacío (facturas antiguas '{}'): efectivo desde base/cuota.
        assert_eq!(derive_tax_rate("{}", 1000.0, 100.0), 10.0);
        // JSON inválido → efectivo.
        assert_eq!(derive_tax_rate("", 1000.0, 210.0), 21.0);
    }

    #[test]
    fn base_cero_no_divide_por_cero() {
        assert_eq!(derive_tax_rate("{}", 0.0, 0.0), 0.0);
    }

    #[test]
    fn rectificativa_negativa_conserva_signo_del_tipo() {
        // R1 con importes negativos: 2100/10000 = 21% (positivo), el desglose de tipo único manda.
        let tb = r#"{"21.00":{"base":-10000,"tax":-2100}}"#;
        assert_eq!(derive_tax_rate(tb, -10000.0, -2100.0), 21.0);
        // Sin desglose, efectivo de negativos: (-210)/(-1000) → 21%.
        assert_eq!(derive_tax_rate("{}", -1000.0, -210.0), 21.0);
    }

    /// Regression test for ERPlora/hub#1198.
    ///
    /// The live `tax_breakdown` that `invoice` writes is the ARRAY generation (one entry per full
    /// tax key, per the breakdown contract of `aeat::desglose`), not the old rate-keyed map. The
    /// row used to read only the map, so every real ticket fell through to the effective rate —
    /// and with `invoice`'s per-line rounding the effective rate is not a Spanish rate at all
    /// (4 lines of 0,50 € at 21 % → base 200 / quota 44 → 22,0 %).
    #[test]
    fn derive_tax_rate_reads_the_array_breakdown_hub1198() {
        // The exact ticket of the issue: one fiscal key at 21 %, quota rounded up per line.
        let real_ticket =
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":200,"quota":44}]"#;
        assert_eq!(derive_tax_rate(real_ticket, 200.0, 44.0), 21.0);

        // Reduced rate, exact amounts: same reading, no rounding involved.
        let reduced = r#"[{"tax":"vat","regime":"01","class":"subject","rate":10.0,"base":1100,"quota":110}]"#;
        assert_eq!(derive_tax_rate(reduced, 1100.0, 110.0), 10.0);

        // Equivalence surcharge: it travels in its own pair, so the effective rate (2620/10000 =
        // 26,2 %) is not a rate anybody charged. The declared one is.
        let surcharge = r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":10000,"quota":2100,"surcharge_rate":5.20,"surcharge_quota":520}]"#;
        assert_eq!(derive_tax_rate(surcharge, 10000.0, 2620.0), 21.0);

        // Several entries that all declare the SAME rate (same rate, different regime) still have
        // one rate — the row can state it without inventing anything.
        let same_rate_twice = r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":10000,"quota":2100},
                                  {"tax":"vat","regime":"51","class":"subject","rate":21.0,"base":5000,"quota":1050}]"#;
        assert_eq!(derive_tax_rate(same_rate_twice, 15000.0, 3150.0), 21.0);

        // A rectifying record keeps the sign of the amounts and the declared rate stays positive.
        let rectificativa = r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":-10000,"quota":-2100}]"#;
        assert_eq!(derive_tax_rate(rectificativa, -10000.0, -2100.0), 21.0);
    }

    /// hub#1198 — two DIFFERENT declared rates leave the row without «the» rate of the invoice, so
    /// the effective rate stands (deliberate: picking the first entry would invent a fiscal fact).
    /// The XML does not depend on this — `aeat::desglose` emits one line per real rate.
    #[test]
    fn derive_tax_rate_falls_back_to_the_effective_rate_on_a_mixed_array_hub1198() {
        let mixed = r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"base":10000,"quota":2100},
                        {"tax":"vat","regime":"01","class":"subject","rate":10.0,"base":1000,"quota":100}]"#;
        assert_eq!(derive_tax_rate(mixed, 11000.0, 2200.0), 20.0);

        // An array whose amounts cannot be read is not a breakdown: nothing is declared, so the
        // effective rate is all that is left (and `aeat::desglose` refuses the record anyway).
        let unreadable =
            r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.0,"quota":2100}]"#;
        assert_eq!(derive_tax_rate(unreadable, 10000.0, 2100.0), 21.0);

        // An empty array declares nothing either.
        assert_eq!(derive_tax_rate("[]", 1000.0, 100.0), 10.0);
    }
}

#[cfg(test)]
mod environment_chain_tests {
    //! ADR-0202 phase 1, guard R4 (hub#313): the hash chain is scoped by AEAT environment.
    //! `production` and `testing` are two parallel, independent chains — the anchor, the
    //! sequence and `PrimerRegistro` never cross environments, and the engine passes the
    //! explicit `:environment` param to the module's insert SQL.
    //!
    //! And the same scope reaches the WIRE (hub#471): the endpoint a record is POSTed to is
    //! the one its own chain lives in, so a record that waited in the queue across a go-live
    //! is still remitted to the tax agency that owns it.

    use super::*;
    use std::sync::Mutex;

    /// A hub UUID (the engine hard-fails on non-UUID hub ids — ADR-0202 §4.2).
    const HUB: &str = "7b2f8a44-9c1d-4e2f-8a3b-944445555666";
    const NIF: &str = "B12345678";
    /// 64-hex hashes so anything that validates hash shape accepts them.
    const HASH_TESTING_1: &str = "1111111111111111111111111111111111111111111111111111111111111111";
    const HASH_TESTING_2: &str = "2222222222222222222222222222222222222222222222222222222222222222";
    const HASH_PRODUCTION_1: &str =
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";

    /// In-memory `verifactu_record` table that honours EXACTLY the WHERE clauses present in
    /// the SQL it receives — like a real database, it only filters by `environment` when the
    /// query asks for it. That is what makes the red case honest: an unscoped anchor query
    /// sees BOTH chains.
    struct ChainHost {
        config: Json,
        records: Vec<Json>,
        /// Contingency entries, so a batch drain can be driven end to end (hub#471).
        queue: Vec<Json>,
        has_core_certificate: bool,
        reads: Mutex<Vec<(String, Params)>>,
        /// Every XML this engine archived, in order.
        ///
        /// It is the honest observation point for «what was about to be transmitted»: the archive
        /// happens **after** the envelope is final and **before** the network is touched, and a
        /// transmission that cannot be archived is never sent. Asserting here needs neither a
        /// fake AEAT nor a certificate.
        archived: Mutex<Vec<String>>,
    }

    impl ChainHost {
        fn new(config: Json, records: Vec<Json>) -> Self {
            ChainHost {
                config,
                records,
                queue: Vec::new(),
                has_core_certificate: false,
                reads: Mutex::new(Vec::new()),
                archived: Mutex::new(Vec::new()),
            }
        }

        /// The XML of the FIRST transmission this host archived.
        fn first_archived(&self) -> String {
            self.archived
                .lock()
                .unwrap()
                .first()
                .cloned()
                .expect("nothing was archived, so nothing was about to be transmitted")
        }
    }

    #[async_trait::async_trait]
    impl NativeHost for ChainHost {
        async fn read(&self, sql: &str, p: &Params) -> Result<Vec<Json>> {
            self.reads
                .lock()
                .unwrap()
                .push((sql.to_string(), p.clone()));
            if sql.contains("FROM verifactu_config") {
                return Ok(vec![self.config.clone()]);
            }
            if sql.contains("FROM verifactu_contingencyqueue") {
                return Ok(self.queue.clone());
            }
            if sql.contains("FROM verifactu_record") {
                let param = |k: &str| p.get(k).cloned().unwrap_or(Json::Null);
                let mut rows: Vec<Json> = self
                    .records
                    .iter()
                    .filter(|r| {
                        let mut keep = true;
                        if sql.contains("hub_id = :hub_id") {
                            keep &= r["hub_id"] == param("hub_id");
                        }
                        if sql.contains("issuer_nif = :issuer_nif") {
                            keep &= r["issuer_nif"] == param("issuer_nif");
                        }
                        if sql.contains("environment = :environment") {
                            keep &= r["environment"] == param("environment");
                        }
                        if sql.contains("status <> 'rejected'") {
                            keep &= r["status"] != "rejected";
                        }
                        if sql.contains("sequence_number = :prev_seq") {
                            keep &= r["sequence_number"] == param("prev_seq");
                        }
                        if sql.contains("id = :record_id") {
                            keep &= r["id"] == param("record_id");
                        }
                        keep
                    })
                    .cloned()
                    .collect();
                if sql.contains("ORDER BY sequence_number DESC") {
                    rows.sort_by_key(|r| {
                        std::cmp::Reverse(r["sequence_number"].as_i64().unwrap_or(0))
                    });
                } else if sql.contains("ORDER BY sequence_number ASC") {
                    rows.sort_by_key(|r| r["sequence_number"].as_i64().unwrap_or(0));
                }
                if sql.contains("LIMIT 1") {
                    rows.truncate(1);
                }
                return Ok(rows);
            }
            Ok(vec![])
        }

        /// The certificate question is the CORE's to answer (hub#319) — the engine no longer
        /// queries `_hub_certificate`, so the fixture stops pretending to be that table. One slot
        /// since hub#1435, so the answer is «the business's own certificate» or nothing at all.
        async fn certificate_signing_kind(&self, _hub_id: &str) -> Result<Option<String>> {
            Ok(self.has_core_certificate.then(|| "own".to_string()))
        }

        /// The manufacturer's facts as the control plane serves them (hub#323). Without them no
        /// envelope can be built at all, so a fixture that transmits has to answer this.
        async fn producer_facts(&self) -> Result<Option<Json>> {
            Ok(Some(json!({
                "NombreRazon": "ERPLORA CLOUD SL",
                "NIF": "B27593136",
                "NombreSistemaInformatico": "ERPlora Hub",
                "IdSistemaInformatico": "EC",
                "TipoUsoPosibleSoloVerifactu": "S",
                "TipoUsoPosibleMultiOT": "S",
                "IndicadorMultiplesOT": "N",
            })))
        }

        async fn write_static_file(
            &self,
            relative_path: &str,
            bytes: &[u8],
            _content_type: &str,
        ) -> Result<String> {
            self.archived
                .lock()
                .unwrap()
                .push(String::from_utf8_lossy(bytes).into_owned());
            Ok(format!("modules/verifactu/{relative_path}"))
        }
    }

    fn config_row(environment: &str) -> Json {
        json!({ "hub_id": HUB, "environment": environment, "issuer_nif": NIF,
                "issuer_name": "Test Business SL" })
    }

    /// A minimal chain row as the post-008 schema stores it (every row carries `environment`).
    fn chain_row(id: &str, seq: i64, environment: &str, hash: &str, prev: &str) -> Json {
        json!({
            "id": id, "hub_id": HUB, "issuer_nif": NIF, "issuer_name": "Test Business SL",
            "environment": environment, "sequence_number": seq,
            "record_type": "alta", "invoice_number": format!("INV-{seq}"),
            "invoice_date": "2026-08-01", "invoice_type": "F2",
            "base_amount": 10000, "tax_rate": 21.0, "tax_amount": 2100, "total_amount": 12100,
            "tax_breakdown": r#"{"21.00":{"base":10000,"tax":2100}}"#,
            "previous_hash": prev, "record_hash": hash,
            "is_first_record": if prev.is_empty() { 1 } else { 0 },
            "generation_timestamp": "2026-08-01T10:00:00+02:00",
            "status": "accepted", "xml_content": "", "is_deleted": 0
        })
    }

    fn create_input() -> Json {
        json!({
            "payload": {
                "record_type": "alta", "issuer_nif": NIF, "issuer_name": "Test Business SL",
                "invoice_number": "F-2026-000123", "invoice_date": "2026-08-06",
                "invoice_type": "F2", "base_amount": 10000, "tax_rate": 21.0,
                "tax_amount": 2100, "total_amount": 12100,
                "tax_breakdown": r#"{"21.00":{"base":10000,"tax":2100}}"#
            },
            "context": {
                "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00", "current_user_id": "u1",
                "new_ids": ["id-rec", "id-evt", "id-queue", "id-t1", "id-t2", "id-t3"]
            }
        })
    }

    fn find_op<'a>(out: &'a Output, command: &str) -> &'a Operation {
        out.operations
            .iter()
            .find(|o| o.command == command)
            .unwrap_or_else(|| panic!("expected an `{command}` operation"))
    }

    /// TDD red case of hub#313: with records only in `testing`, the FIRST `production`
    /// record starts its OWN chain — `PrimerRegistro=S` (is_first_record=1), empty
    /// `previous_hash`, sequence 1 — and stamps the explicit `environment` param.
    #[tokio::test]
    async fn first_production_record_starts_a_new_chain_despite_testing_records() {
        let host = ChainHost::new(
            config_row("production"),
            vec![chain_row("t1", 1, "testing", HASH_TESTING_1, "")],
        );
        let out = create_record(&create_input(), &host).await.unwrap();

        let insert = find_op(&out, "verifactu._insert_record");
        assert_eq!(
            insert.params.get("is_first_record"),
            Some(&json!(1)),
            "the first production record must open its own chain (PrimerRegistro=S)"
        );
        assert_eq!(
            insert.params.get("previous_hash"),
            Some(&json!("")),
            "a testing hash must never be the previous link of a production record"
        );
        assert_eq!(
            insert.params.get("sequence_number"),
            Some(&json!(1)),
            "the production sequence starts at 1, independent of testing"
        );
        assert_eq!(
            insert.params.get("environment"),
            Some(&json!("production")),
            "the engine must pass the explicit :environment param (no COALESCE fallback)"
        );
        // R3 pin (verifactu#26): module active = always emit; the schema no longer has
        // `auto_transmit`, so nothing may enqueue a deferred-transmission entry on create.
        assert!(
            !out.operations
                .iter()
                .any(|o| o.command == "verifactu._enqueue_contingency"),
            "create must not enqueue contingency: auto_transmit is gone (R3)"
        );
    }

    /// Switching back to an environment RESUMES that environment's own chain: the anchor is
    /// the last chainable row of the ACTIVE environment, even when the other chain is longer.
    #[tokio::test]
    async fn chaining_resumes_the_active_environment_chain_and_never_crosses() {
        let host = ChainHost::new(
            config_row("production"),
            vec![
                chain_row("t1", 1, "testing", HASH_TESTING_1, ""),
                chain_row("t2", 2, "testing", HASH_TESTING_2, HASH_TESTING_1),
                chain_row("p1", 1, "production", HASH_PRODUCTION_1, ""),
            ],
        );
        let out = create_record(&create_input(), &host).await.unwrap();

        let insert = find_op(&out, "verifactu._insert_record");
        assert_eq!(
            insert.params.get("previous_hash"),
            Some(&json!(HASH_PRODUCTION_1)),
            "the anchor must be production's last link, not testing's (longer) chain"
        );
        assert_eq!(
            insert.params.get("sequence_number"),
            Some(&json!(2)),
            "the production sequence resumes at 2 even though testing is at 2 already"
        );
        assert_eq!(insert.params.get("is_first_record"), Some(&json!(0)));
        assert_eq!(insert.params.get("environment"), Some(&json!("production")));
    }

    /// Recovery anchors join the chain of the ACTIVE environment: scoped sequence and an
    /// explicit `environment` param on `_insert_recovery`.
    #[tokio::test]
    async fn recovery_anchor_is_scoped_and_stamped_with_the_active_environment() {
        let host = ChainHost::new(
            config_row("production"),
            vec![
                chain_row("t1", 1, "testing", HASH_TESTING_1, ""),
                chain_row("t2", 2, "testing", HASH_TESTING_2, HASH_TESTING_1),
            ],
        );
        let input = json!({
            "payload": { "record_hash": HASH_TESTING_2 },
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1", "new_ids": ["id-anchor", "id-evt"] }
        });
        let out = recover_manual(&input, &host).await.unwrap();

        let recovery = find_op(&out, "verifactu._insert_recovery");
        assert_eq!(
            recovery.params.get("sequence_number"),
            Some(&json!(1)),
            "the anchor takes production's next sequence (1), not testing's (3)"
        );
        assert_eq!(
            recovery.params.get("environment"),
            Some(&json!("production")),
            "the recovery insert must carry the explicit :environment param"
        );
    }

    /// Chain validation walks ONLY the active environment's chain: with a valid chain in each
    /// environment, interleaving them by sequence number would false-flag a break.
    #[tokio::test]
    async fn validate_chain_walks_only_the_active_environment() {
        let ts1 = "2026-08-01T10:00:00+02:00";
        let ts2 = "2026-08-02T10:00:00+02:00";
        // Real hashes so the walk's recompute matches (amounts in cents → euros /100).
        let t1_hash = chain::alta_hash(NIF, "INV-1", "2026-08-01", "F2", 21.0, 121.0, "", ts1);
        let t2_hash =
            chain::alta_hash(NIF, "INV-2", "2026-08-01", "F2", 21.0, 121.0, &t1_hash, ts2);
        let mut t1 = chain_row("t1", 1, "testing", &t1_hash, "");
        t1["generation_timestamp"] = json!(ts1);
        let mut t2 = chain_row("t2", 2, "testing", &t2_hash, t1_hash.as_str());
        t2["generation_timestamp"] = json!(ts2);
        // A parallel, self-consistent production chain that would break the walk if mixed in.
        let p1 = chain_row("p1", 1, "production", HASH_PRODUCTION_1, "");

        let host = ChainHost::new(config_row("testing"), vec![t1, p1, t2]);
        let input = json!({
            "payload": {},
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1", "new_ids": ["id-evt"] }
        });
        let out = validate_chain(&input, &host).await.unwrap();

        let event = find_op(&out, "verifactu._insert_event");
        assert_eq!(
            event.params.get("event_type"),
            Some(&json!("chain_validated")),
            "both per-environment chains are valid; mixing them is what breaks"
        );
        let details: Json =
            serde_json::from_str(event.params.get("details").and_then(Json::as_str).unwrap())
                .unwrap();
        assert_eq!(details["valid"], json!(true));
        assert_eq!(
            details["total"],
            json!(2),
            "only the 2 testing rows belong to the validated chain"
        );
    }

    /// Retransmission reads the previous link from the RECORD's own environment — sequence
    /// numbers repeat across environments, so an unscoped `prev_seq` lookup can pick the
    /// other chain's row. The record's stored environment wins over the hub's current config.
    #[tokio::test]
    async fn transmit_previous_link_lookup_is_scoped_to_the_records_environment() {
        let mut record = chain_row("rec-2", 2, "testing", HASH_TESTING_2, HASH_TESTING_1);
        record["status"] = json!("pending");
        let mut host = ChainHost::new(
            // The hub has ALREADY switched to production; the retried record is testing.
            config_row("production"),
            vec![
                // Inserted first so an UNSCOPED lookup (stable order, LIMIT 1) picks it.
                chain_row("p1", 1, "production", HASH_PRODUCTION_1, ""),
                chain_row("t1", 1, "testing", HASH_TESTING_1, ""),
                record,
            ],
        );
        host.has_core_certificate = true; // pass the certificate gate before transmit_one
        let input = json!({
            "payload": { "record_id": "rec-2" },
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1",
                         "new_ids": ["id-evt", "id-queue", "id-anchor"] }
        });
        // The flow errs later (no real mTLS identity in tests) — the prev-link read under
        // scrutiny happens before that, so the outcome itself is irrelevant here.
        let _ = transmit_record(&input, &host).await;

        let reads = host.reads.lock().unwrap();
        let (sql, params) = reads
            .iter()
            .find(|(sql, _)| sql.contains(":prev_seq"))
            .expect("transmit must look up the previous link");
        assert!(
            sql.contains("environment = :environment"),
            "the previous-link lookup must filter by environment: {sql}"
        );
        assert_eq!(
            params.get("environment"),
            Some(&json!("testing")),
            "the RECORD's environment scopes the lookup, not the current config's"
        );
    }

    // ── hub#471: the ENVIRONMENT travels with the RECORD, the DOOR with today's config ──────
    //
    // R4 scoped the chain by environment but the wire kept reading the config, so the three
    // things that describe one transmission disagreed: the previous link and the frozen XML
    // said `testing` and the URL said `production`. The two axes of the endpoint fail in
    // opposite ways — a wrong door is REJECTED (loud, fixable one record at a time), a wrong
    // environment is ACCEPTED by a tax agency that was never meant to receive it, and an
    // accepted record is neither resent nor deleted (ADR-0189).
    //
    // The URLs are spelled out on purpose: deriving them from `aeat::endpoint` here would make
    // these tests agree with the code by construction instead of pinning the destination.
    //
    // ⚠️ Coverage boundary, unchanged since hub#320: the four call sites that live BEHIND the
    // socket (`post_soap`/`run_consult` inside `transmit_one` and `auto_rechain_and_retry`) are
    // not reachable from a unit test — `build_identity` needs a real mTLS identity, and driving
    // them further would mean opening a connection to Hacienda from `cargo test`. What is pinned
    // here is the VALUE those call sites are handed; that they keep being handed it is review.
    const PREPRODUCTION_HOLDER: &str =
        "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP";
    const PRODUCTION_HOLDER: &str =
        "https://www1.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP";
    const PREPRODUCTION_SEAL: &str =
        "https://prewww10.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP";

    /// The record that outlived a go-live: chained in `testing`, XML frozen from that attempt,
    /// still queued when the operator flipped the hub to `production`.
    fn queued_testing_record() -> Json {
        let mut record = chain_row("rec-2", 2, "testing", HASH_TESTING_2, HASH_TESTING_1);
        record["status"] = json!("pending");
        // `DescripcionOperacion` is required and must not be empty (`xsd::REQUIRED_ALTA`).
        // Without it the XSD gate refuses the record BEFORE the envelope is archived, and a test
        // asserting on what was about to be transmitted would find nothing at all.
        record["description"] = json!("Ticket");
        record
    }

    /// 🔴 The bug of hub#471: draining that queue after the go-live POSTed a PRACTICE record to
    /// the real AEAT. Nothing undoes that — a remitted record is never resent nor deleted.
    #[test]
    fn a_record_queued_in_testing_is_never_posted_to_the_real_aeat_after_a_go_live() {
        let destination = destination_of(&queued_testing_record(), &config_row("production"))
            .expect("a record that carries its environment resolves");

        assert_eq!(
            destination.endpoint, PREPRODUCTION_HOLDER,
            "the record belongs to the testing chain, so preproduction is the tax agency that \
             must receive it — whatever the hub's config says today"
        );
        assert_eq!(destination.environment, "testing");
    }

    /// The mirror image, and the one that breaks the LAW rather than the sandbox: a real sale
    /// queued before someone flipped the toggle back must still reach the real AEAT. Sent to
    /// preproduction it would be marked accepted here and be an orphan RF there (FAQ §5).
    #[test]
    fn a_record_queued_in_production_still_reaches_the_real_aeat_after_a_rollback() {
        let mut record = chain_row("prod-2", 2, "production", HASH_TESTING_2, HASH_PRODUCTION_1);
        record["status"] = json!("pending");

        let destination = destination_of(&record, &config_row("testing"))
            .expect("a record that carries its environment resolves");

        assert_eq!(
            destination.endpoint, PRODUCTION_HOLDER,
            "a real invoice belongs to the real chain; a hub back in testing does not move it"
        );
        assert_eq!(destination.environment, "production");
    }

    /// The two axes come from different places ON PURPOSE, and both survive together: the
    /// environment from the record (its chain), the door from the certificate signing TODAY
    /// (hub#320 — the AEAT segregates by the certificate presented in the TLS handshake, so a
    /// record that waited days goes through the door of whatever signs now).
    ///
    /// The door axis is the certificate's **TYPE**, not the slot it came from (hub#470): `delegated`
    /// says the control plane handed the container down, and ERPlora's own `.p12` is a
    /// *representative* certificate — routing on the slot would have sent the whole delegated fleet
    /// to `www10` and had every record rejected.
    #[test]
    fn the_door_follows_todays_certificate_while_the_environment_follows_the_record() {
        let mut config = config_row("production");
        config["certificate_type"] = json!("seal");

        let destination = destination_of(&queued_testing_record(), &config)
            .expect("a record that carries its environment resolves");

        assert_eq!(
            destination.endpoint, PREPRODUCTION_SEAL,
            "preproduction because of the RECORD, the seal door because of TODAY's certificate"
        );

        // And a config that says nothing about the TYPE keeps the holder's door, on the very same
        // record: «cannot tell» is never a reason to knock on the seal's (hub#470).
        assert_eq!(
            destination_of(&queued_testing_record(), &config_row("production"))
                .expect("a record that carries its environment resolves")
                .endpoint,
            PREPRODUCTION_HOLDER,
            "an unknown certificate type routes to the holder's door (hub#470)"
        );
    }

    /// A record that does not say which of the two tax agencies owns it is NOT sent. Both
    /// guesses are unrecoverable — a practice record accepted by the real AEAT, or a real
    /// invoice the real AEAT never receives — so the engine refuses instead of picking one.
    #[test]
    fn a_record_that_does_not_say_which_aeat_owns_it_is_never_transmitted() {
        let mut record = queued_testing_record();
        record.as_object_mut().unwrap().remove("environment");

        let refusal = destination_of(&record, &config_row("production"))
            .expect_err("an unstamped record has no provable destination");

        assert!(
            refusal.contains("production"),
            "the refusal must name the environment the hub is in, so the owner can act: {refusal}"
        );
    }

    /// The refusal is loud and LOSSLESS: an `error` event with a stable reason, the record put
    /// back in the contingency queue, and — critically — no `_apply_transmission`, which
    /// overwrites `xml_content`/`xml_storage_path` unconditionally and would erase the archived
    /// XML of a record that was never sent.
    #[tokio::test]
    async fn the_refusal_queues_the_record_and_never_touches_its_archived_xml() {
        let mut record = queued_testing_record();
        record.as_object_mut().unwrap().remove("environment");
        let mut host = ChainHost::new(config_row("production"), vec![record]);
        host.has_core_certificate = true; // clear the certificate gate: the refusal is earlier
        let input = json!({
            "payload": { "record_id": "rec-2" },
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1",
                         "new_ids": ["id-evt", "id-queue", "id-anchor"] }
        });

        let out = transmit_record(&input, &host)
            .await
            .expect("the refusal is an outcome, not an error: one bad row must not abort a batch");

        let event = find_op(&out, "verifactu._insert_event");
        assert_eq!(event.params.get("severity"), Some(&json!("error")));
        let details: Json =
            serde_json::from_str(event.params.get("details").and_then(Json::as_str).unwrap())
                .unwrap();
        assert_eq!(
            details["reason"],
            json!("record_environment_unknown"),
            "a stable reason key, so the queue-depth alerting can tell this apart from an outage"
        );
        let queued = find_op(&out, "verifactu._enqueue_contingency");
        assert_eq!(
            queued.params.get("record_id"),
            Some(&json!("rec-2")),
            "the refused record has to stay in the queue: an RF may never be left generated and \
             never remitted (FAQ §5)"
        );
        assert_eq!(queued.params.get("queue_status"), Some(&json!("retrying")));
        assert!(
            !out.operations
                .iter()
                .any(|o| o.command == "verifactu._apply_transmission"),
            "nothing was transmitted, so nothing may overwrite the record's archived XML"
        );
    }

    // ── hub#322: the envelope says whether it comes out of the contingency queue ─────────────
    //
    // Both tests stop at the same place, on purpose: the envelope is archived BEFORE the network
    // is opened, and this host has no certificate to sign with, so the run dies right after the
    // archive. What was archived is exactly what was about to be handed to the AEAT — no fake
    // tax agency and no `.p12` needed to assert on it.

    fn contingency_input() -> Json {
        json!({
            "payload": {},
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1",
                         "new_ids": ["id-evt", "id-queue", "id-anchor", "id-summary"] }
        })
    }

    /// 🔴 The defect: a record that spent the outage in the queue was remitted looking punctual.
    /// `Incidencia` is what legalises a deferred remission, and no envelope carried it.
    #[tokio::test]
    async fn a_record_drained_from_the_queue_declares_the_incidence() {
        let mut host = ChainHost::new(config_row("testing"), vec![queued_testing_record()]);
        host.has_core_certificate = true;
        host.queue = vec![json!({ "record_id": "rec-2" })];

        let _ = process_contingency_queue(&contingency_input(), &host).await;

        let sent = host.first_archived();
        assert!(
            sent.contains(
                "<sum1:RemisionVoluntaria><sum1:Incidencia>S</sum1:Incidencia>\
                 </sum1:RemisionVoluntaria>"
            ),
            "an envelope out of the queue declares the incidence: {sent}"
        );
    }

    /// The other half, and the one that keeps the flag meaningful: an ordinary sale is a punctual
    /// remission and declares NO incidence. Stamping every envelope would say nothing at all.
    #[tokio::test]
    async fn an_ordinary_transmission_declares_no_incidence() {
        let mut host = ChainHost::new(config_row("testing"), vec![queued_testing_record()]);
        host.has_core_certificate = true;
        let input = json!({
            "payload": { "record_id": "rec-2" },
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1",
                         "new_ids": ["id-evt", "id-queue", "id-anchor"] }
        });

        let _ = transmit_record(&input, &host).await;

        let sent = host.first_archived();
        assert!(!sent.contains("Incidencia"), "{sent}");
        assert!(!sent.contains("RemisionVoluntaria"), "{sent}");
    }

    /// **The flag is the ENVELOPE's, and the record knows nothing about it** (the caveat of #322).
    ///
    /// The same invoice remitted punctually and remitted out of the queue is the SAME record —
    /// same fields, same fingerprint, same chain link — and only its envelope differs. So the
    /// incidence must live in the `Cabecera` and nowhere inside `RegistroFactura`, which is the
    /// half the fingerprint covers.
    ///
    /// (What DOES carry it afterwards is `xml_content`, and that is the point: the column is the
    /// evidence of what was actually transmitted, and the next retry reuses it verbatim.)
    #[tokio::test]
    async fn the_incidence_lives_in_the_header_and_not_in_the_record() {
        let mut host = ChainHost::new(config_row("testing"), vec![queued_testing_record()]);
        host.has_core_certificate = true;
        host.queue = vec![json!({ "record_id": "rec-2" })];

        let _ = process_contingency_queue(&contingency_input(), &host).await;

        let sent = host.first_archived();
        let registro_start = sent.find("<sum:RegistroFactura>").expect("RegistroFactura");
        assert!(
            sent[..registro_start].contains("<sum1:Incidencia>S</sum1:Incidencia>"),
            "the header declares it: {sent}"
        );
        assert!(
            !sent[registro_start..].contains("Incidencia"),
            "and the record does not — the fingerprint covers that block: {sent}"
        );
    }

    /// **A record whose amounts cannot be read is not transmitted either** (hub#324).
    ///
    /// It lands on the SAME refusal as hub#471 and for the same reason: nothing is sent, nothing
    /// overwrites the row, and the record keeps its place in the queue. What it must NOT do is
    /// what the old `unwrap_or(0.0)` did — build an envelope declaring `0,00`, hand it to the AEAT
    /// and have it accepted. That is unrecoverable: the record is remitted, fingerprinted and
    /// chained, and the AEAT neither replaces nor deletes it (ADR-0189).
    #[tokio::test]
    async fn a_record_with_an_unreadable_amount_is_refused_not_declared_as_zero() {
        let mut record = queued_testing_record();
        record.as_object_mut().unwrap().remove("total_amount");
        let mut host = ChainHost::new(config_row("testing"), vec![record]);
        host.has_core_certificate = true;
        let input = json!({
            "payload": { "record_id": "rec-2" },
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1",
                         "new_ids": ["id-evt", "id-queue", "id-anchor"] }
        });

        let out = transmit_record(&input, &host)
            .await
            .expect("an undeclarable record is an outcome, not an aborted batch");

        let event = find_op(&out, "verifactu._insert_event");
        assert_eq!(event.params.get("severity"), Some(&json!("error")));
        let details: Json =
            serde_json::from_str(event.params.get("details").and_then(Json::as_str).unwrap())
                .unwrap();
        assert_eq!(
            details["reason"],
            json!("record_not_declarable"),
            "its OWN key: telling this apart from an environment it cannot resolve is what \
             decides whether somebody goes to look at the invoice or at the config"
        );
        assert!(
            details["error"]
                .as_str()
                .unwrap_or_default()
                .contains("total_amount"),
            "the operator has to be told WHICH amount: {details}"
        );
        assert_eq!(
            find_op(&out, "verifactu._enqueue_contingency")
                .params
                .get("record_id"),
            Some(&json!("rec-2")),
            "an RF may never be left generated and never remitted (FAQ §5)"
        );
        assert!(
            !out.operations
                .iter()
                .any(|o| o.command == "verifactu._apply_transmission"),
            "nothing was built and nothing was sent, so nothing may touch the record"
        );
    }

    /// The refusal is per-record, not per-batch: a row nobody can place must not strand every
    /// other record behind it. That is why it is an outcome and not an `Err` —
    /// `process_contingency_queue` propagates errors with `?`.
    #[tokio::test]
    async fn one_unplaceable_record_does_not_abort_the_contingency_batch() {
        let mut record = queued_testing_record();
        record.as_object_mut().unwrap().remove("environment");
        let mut host = ChainHost::new(config_row("production"), vec![record]);
        host.has_core_certificate = true;
        host.queue = vec![json!({ "record_id": "rec-2", "attempts": 2 })];
        let input = json!({
            "payload": {},
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1",
                         "new_ids": ["id-evt", "id-queue", "id-anchor", "id-summary"] }
        });

        let out = process_contingency_queue(&input, &host)
            .await
            .expect("the batch must survive a record it cannot place");

        let summary = out
            .operations
            .iter()
            .find(|o| o.params.get("event_type") == Some(&json!("contingency_processed")))
            .expect("the batch must still report a summary");
        let details: Json = serde_json::from_str(
            summary
                .params
                .get("details")
                .and_then(Json::as_str)
                .unwrap(),
        )
        .unwrap();
        assert_eq!(
            details["failed"],
            json!(1),
            "a record that could not be placed counts as failed, never as sent"
        );
        assert_eq!(details["successful"], json!(0));
    }

    /// When the automatic re-anchor of hub#287 lands on a record that also outlived a go-live,
    /// the operator needs BOTH facts in the same line: what was re-chained, and which tax agency
    /// actually got it. Keeping only the first note would hide the one nobody expects.
    #[test]
    fn the_rechain_note_and_the_drift_note_travel_together() {
        let destination = destination_of(&queued_testing_record(), &config_row("production"))
            .expect("a record that carries its environment resolves");

        let (ops, ..) = response_ops(
            &queued_testing_record(),
            &accepted_response(),
            &destination,
            "<xml/>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-08-06T10:00:00+02:00",
            "rec-2",
            Some("re-anclado automáticamente tras 4102"),
        );

        let event = ops
            .iter()
            .find(|o| o.command == "verifactu._insert_event")
            .expect("the transmission must leave an event");
        let message = event
            .params
            .get("message")
            .and_then(Json::as_str)
            .unwrap_or_default();
        assert!(
            message.contains("re-anclado automáticamente tras 4102"),
            "the caller's note must survive: {message}"
        );
        assert!(
            message.contains("remitido a «testing»"),
            "and so must the drift note: {message}"
        );
    }

    /// 🔴 verifactu#75. A filed record kept the XML and nothing that PINS IT DOWN. The digest of
    /// the bytes that travelled was computed over the outgoing envelope and thrown away, so if
    /// `xml_content` — or the archived object behind `xml_storage_path` — moved afterwards,
    /// nothing noticed: a retry recomputed the digest over whatever was there and transmitted
    /// DIFFERENT bytes believing they were the same ones.
    #[test]
    fn a_filed_transmission_stamps_the_digest_of_the_bytes_that_travelled() {
        let destination = destination_of(&queued_testing_record(), &config_row("testing"))
            .expect("a record that carries its environment resolves");

        let (ops, ..) = response_ops(
            &queued_testing_record(),
            &accepted_response(),
            &destination,
            "<sf:RegistroFactura>QA</sf:RegistroFactura>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-09-03T10:00:00+02:00",
            "rec-2",
            None,
        );

        let apply = ops
            .iter()
            .find(|o| o.command == "verifactu._apply_transmission")
            .expect("filing a verdict updates the record");
        assert_eq!(
            apply.params.get("xml_sha256").and_then(Json::as_str),
            Some(crate::gateway::xml_sha256("<sf:RegistroFactura>QA</sf:RegistroFactura>").as_str()),
            "the row has to keep the digest of the bytes it is storing"
        );
    }

    /// The digest that is PERSISTED and the digest the cell is asked to echo back as
    /// `request_sha256` must be the same number, and the only way to guarantee that is for both to
    /// come out of the SAME function. If they ever diverge, the canary of ADR-0320 §2 starts
    /// comparing one thing and the audit trail recording another.
    #[test]
    fn the_persisted_digest_is_the_one_the_cell_is_asked_to_echo() {
        let xml = "<sf:RegistroFactura>QA</sf:RegistroFactura>";
        let destination = destination_of(&queued_testing_record(), &config_row("testing"))
            .expect("a record that carries its environment resolves");

        let (ops, ..) = response_ops(
            &queued_testing_record(),
            &accepted_response(),
            &destination,
            xml,
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-09-03T10:00:00+02:00",
            "rec-2",
            None,
        );
        let persisted = ops
            .iter()
            .find(|o| o.command == "verifactu._apply_transmission")
            .and_then(|o| o.params.get("xml_sha256"))
            .and_then(Json::as_str)
            .expect("the record keeps a digest")
            .to_string();

        let envelope = crate::gateway::GatewayEnvelope {
            hub_id: "hub-1",
            obligado_nif: "12345678Z",
            environment: "testing",
            transmission_id: "rec-2",
            xml,
        };
        assert_eq!(
            persisted,
            envelope.xml_sha256(),
            "what the row keeps and what the cell is asked to echo have to be ONE number"
        );
    }

    /// 🔴 verifactu#75. The id the delivery went out under is the `Idempotency-Key` the fiscal
    /// cell indexes on, and it is NOT always the record id: the automatic re-anchor presents the
    /// SAME record under `{id}-rechain-{anchor}` because the bytes changed. Without the column
    /// there is no way to cross a hub record with the cell's log line.
    #[test]
    fn a_filed_transmission_stamps_the_id_it_went_out_under() {
        let destination = destination_of(&queued_testing_record(), &config_row("testing"))
            .expect("a record that carries its environment resolves");

        let rechained = rechain_delivery_id("rec-2", HASH_TESTING_2);
        let (ops, ..) = response_ops(
            &queued_testing_record(),
            &accepted_response(),
            &destination,
            "<xml/>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-09-03T10:00:00+02:00",
            &rechained,
            Some("re-anclado automáticamente tras 4102"),
        );

        let apply = ops
            .iter()
            .find(|o| o.command == "verifactu._apply_transmission")
            .expect("filing a verdict updates the record");
        assert_eq!(
            apply.params.get("transmission_id").and_then(Json::as_str),
            Some(rechained.as_str()),
            "the row has to keep the key the cell actually saw, not the record id"
        );
        assert_ne!(
            rechained, "rec-2",
            "a re-anchored retry never goes out under the record id — that is the whole reason \
             the column is not redundant with `id`"
        );
    }

    fn accepted_response() -> aeat::AeatResponse {
        aeat::AeatResponse {
            estado_envio: "Correcto".to_string(),
            estado_registro: "Correcto".to_string(),
            ..Default::default()
        }
    }

    /// The audit trail told the truth about the chain and lied about the wire: the event said
    /// `AEAT (production)` for a record that was chained — and now sent — in testing.
    #[test]
    fn the_audit_event_names_the_environment_the_record_was_actually_sent_to() {
        let destination = destination_of(&queued_testing_record(), &config_row("production"))
            .expect("a record that carries its environment resolves");

        let (ops, ..) = response_ops(
            &queued_testing_record(),
            &accepted_response(),
            &destination,
            "<xml/>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-08-06T10:00:00+02:00",
            "rec-2",
            None,
        );

        let event = ops
            .iter()
            .find(|o| o.command == "verifactu._insert_event")
            .expect("the transmission must leave an event");
        let message = event
            .params
            .get("message")
            .and_then(Json::as_str)
            .unwrap_or_default();
        assert!(
            message.contains("AEAT (testing)"),
            "the event must name where the record WENT, not where the hub is: {message}"
        );
    }

    /// Draining a queue into the other tax agency is correct but never routine — it is exactly
    /// what a go-live with a non-empty queue looks like. A clean `Correcto` would otherwise be
    /// filed as `info` and the owner would never learn that their practice records left after
    /// the go-live, nor where they went.
    #[test]
    fn a_transmission_that_outlived_a_go_live_is_reported_as_a_warning() {
        let destination = destination_of(&queued_testing_record(), &config_row("production"))
            .expect("a record that carries its environment resolves");

        let (ops, _, success) = response_ops(
            &queued_testing_record(),
            &accepted_response(),
            &destination,
            "<xml/>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-08-06T10:00:00+02:00",
            "rec-2",
            None,
        );

        assert!(success, "the AEAT accepted it: the record IS remitted");
        let event = ops
            .iter()
            .find(|o| o.command == "verifactu._insert_event")
            .expect("the transmission must leave an event");
        assert_eq!(event.params.get("severity"), Some(&json!("warning")));
        assert_eq!(
            event.params.get("event_type"),
            Some(&json!("transmission_warning"))
        );
        let message = event
            .params
            .get("message")
            .and_then(Json::as_str)
            .unwrap_or_default();
        // Both halves, and in this order: the record LEFT for testing, the hub IS in production.
        // Read the other way round it describes the disaster instead of the safe outcome.
        assert!(
            message.contains("remitido a «testing»"),
            "the warning has to say where the record went: {message}"
        );
        assert!(
            message.contains("ahora en «production»"),
            "…and which environment the hub is in now: {message}"
        );
    }

    /// A config that never set `environment` IS in testing — that is the asymmetric default
    /// hub#320 fixed in place, and it has to be the same default on both sides of the drift
    /// comparison. Reading the raw field instead would make every ordinary testing record look
    /// like a record that outlived a go-live, and a warning that cries wolf is a warning nobody
    /// reads.
    #[test]
    fn an_unconfigured_environment_is_testing_on_both_sides_of_the_comparison() {
        let config = json!({ "hub_id": HUB, "issuer_nif": NIF });

        let destination = destination_of(&queued_testing_record(), &config)
            .expect("a record that carries its environment resolves");

        assert_eq!(destination.endpoint, PREPRODUCTION_HOLDER);
        assert_eq!(
            destination.drift_note(),
            None,
            "an unset environment is testing, so a testing record has not drifted anywhere"
        );

        let mut unstamped = queued_testing_record();
        unstamped.as_object_mut().unwrap().remove("environment");
        let refusal = destination_of(&unstamped, &config)
            .expect_err("an unstamped record has no provable destination");
        assert!(
            refusal.contains("«testing»"),
            "and the refusal names that same default, not an empty string: {refusal}"
        );
    }

    /// …and the ordinary case stays ordinary: a record sent in the hub's own environment is a
    /// clean `info` success, with no warning to cry wolf with.
    #[test]
    fn a_record_sent_in_the_hubs_own_environment_is_a_plain_success() {
        let destination = destination_of(&queued_testing_record(), &config_row("testing"))
            .expect("a record that carries its environment resolves");

        let (ops, ..) = response_ops(
            &queued_testing_record(),
            &accepted_response(),
            &destination,
            "<xml/>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-08-06T10:00:00+02:00",
            "rec-2",
            None,
        );

        let event = ops
            .iter()
            .find(|o| o.command == "verifactu._insert_event")
            .expect("the transmission must leave an event");
        assert_eq!(event.params.get("severity"), Some(&json!("info")));
        assert_eq!(
            event.params.get("message"),
            Some(&json!("AEAT (testing): Correcto Correcto")),
            "no drift, no note: the message keeps its plain shape"
        );
    }

    // ── verifactu#42 — the outcome that has to leave the module ────────────────────────────────
    //
    // Everything above writes `verifactu_event`, the module's own audit table. Nothing there
    // leaves: it is a row on a screen somebody has to open. This is the ONE part of the product
    // where not finding out has consequences before the AEAT, and a bar that closes at two in the
    // morning does not open that screen.
    //
    // So a failed outcome also emits a **public** event — the hub's outbox, the thing an
    // automation can be built on (`ERPlora/flows#18` R0 #6, «fiscal failure → tell the owner»).

    /// A real `Incorrecto` from the AEAT, as `parse_response` hands it over.
    fn rejected_response() -> aeat::AeatResponse {
        aeat::AeatResponse {
            estado_envio: "Incorrecto".to_string(),
            estado_registro: "Incorrecto".to_string(),
            codigo_error: "1189".to_string(),
            descripcion_error: "El NIF del destinatario no está identificado".to_string(),
            ..Default::default()
        }
    }

    /// `AceptadoConErrores` (ADR-0189): the AEAT REGISTERED it and noted an error on it.
    fn accepted_with_errors_response() -> aeat::AeatResponse {
        aeat::AeatResponse {
            estado_envio: "Correcto".to_string(),
            estado_registro: "AceptadoConErrores".to_string(),
            codigo_error: "2007".to_string(),
            descripcion_error: "Primer registro con obligado ya existente".to_string(),
            ..Default::default()
        }
    }

    fn emitted(events: &[Event], name: &str) -> Option<Json> {
        events
            .iter()
            .find(|e| e.name == name)
            .map(|e| e.payload.clone())
    }

    /// A rejection the AEAT really answered leaves the module, so something other than a screen
    /// can notice it.
    #[test]
    fn a_rejection_by_the_aeat_emits_a_public_event_the_owner_can_be_told_about() {
        let destination = destination_of(&queued_testing_record(), &config_row("testing"))
            .expect("a record that carries its environment resolves");

        let (_, events, success) = response_ops(
            &queued_testing_record(),
            &rejected_response(),
            &destination,
            "<xml/>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-08-06T10:00:00+02:00",
            "rec-2",
            None,
        );

        assert!(!success);
        let payload = emitted(&events, EVENT_RECORD_REJECTED)
            .expect("a rejection has to leave the module, not just the audit table");
        assert_eq!(payload["record_id"], json!("rec-2"));
        // The human reference. `record_id` is a uuid nobody can act on; «revisa la factura INV-2»
        // is the sentence an automation has to be able to write.
        assert_eq!(payload["invoice_number"], json!("INV-2"));
        assert_eq!(payload["reason"], json!(REASON_AEAT_REJECTED));
        assert_eq!(payload["error_code"], json!("1189"));
        assert_eq!(payload["environment"], json!("testing"));
        assert!(
            emitted(&events, EVENT_RECORD_ACCEPTED_WITH_ERRORS).is_none(),
            "a rejection is not an acceptance with a note on it"
        );
    }

    /// **Nothing fiscal travels.** The payload ends up in somebody's task list and in a message,
    /// and `flows#18` asks for this by name: enough to say «check invoice X», and no more.
    #[test]
    fn the_public_payload_carries_no_fiscal_content_at_all() {
        let destination = destination_of(&queued_testing_record(), &config_row("testing")).unwrap();
        let mut response = rejected_response();
        response.csv = "CSV-SHOULD-NOT-TRAVEL".to_string();

        let (_, events, _) = response_ops(
            &queued_testing_record(),
            &response,
            &destination,
            "<xml>the signed record</xml>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-08-06T10:00:00+02:00",
            "rec-2",
            None,
        );

        let payload = emitted(&events, EVENT_RECORD_REJECTED).expect("it emits");
        let text = payload.to_string();
        for secret in [
            "<xml>",        // the signed record itself
            HASH_TESTING_2, // the chain hash
            NIF,            // the issuer's tax id
            "12100",        // any amount
            "CSV-SHOULD-NOT-TRAVEL",
        ] {
            assert!(
                !text.contains(secret),
                "`{secret}` must never leave in a public event: {text}"
            );
        }
        // And the keys are the closed set, so a field added later is a decision and not a slip.
        let keys: Vec<&String> = payload.as_object().expect("an object").keys().collect();
        assert_eq!(
            keys,
            vec![
                "environment",
                "error_code",
                "error_message",
                "invoice_number",
                "reason",
                "record_id",
                "status",
            ]
        );
    }

    /// **An `AceptadoConErrores` is not a rejection** (ADR-0189): the record IS at the AEAT and
    /// resending it is a duplicate. Filing it as a rejection would send the owner chasing an
    /// invoice that is already registered — but staying silent leaves a latent problem nobody
    /// sees, which is the other half of verifactu#42. So it gets its own word.
    #[test]
    fn an_acceptance_with_errors_is_told_apart_from_a_rejection() {
        let destination = destination_of(&queued_testing_record(), &config_row("testing")).unwrap();

        let (_, events, success) = response_ops(
            &queued_testing_record(),
            &accepted_with_errors_response(),
            &destination,
            "<xml/>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-08-06T10:00:00+02:00",
            "rec-2",
            None,
        );

        assert!(
            success,
            "it is registered at the AEAT: it counts as accepted"
        );
        assert!(
            emitted(&events, EVENT_RECORD_REJECTED).is_none(),
            "never as a rejection: the invoice is filed"
        );
        let payload = emitted(&events, EVENT_RECORD_ACCEPTED_WITH_ERRORS)
            .expect("but it cannot be silent either");
        assert_eq!(payload["error_code"], json!("2007"));
        assert_eq!(payload["record_id"], json!("rec-2"));
    }

    /// A clean acceptance says nothing. `verifactu.record.transmitted` already exists for «it
    /// went out», and an outbox row per successful invoice would be the till's whole day.
    #[test]
    fn a_clean_acceptance_emits_no_failure_event() {
        let destination = destination_of(&queued_testing_record(), &config_row("testing")).unwrap();

        let (_, events, success) = response_ops(
            &queued_testing_record(),
            &accepted_response(),
            &destination,
            "<xml/>",
            "modules/verifactu/xml/rec-2.xml",
            "id-evt",
            "2026-08-06T10:00:00+02:00",
            "rec-2",
            None,
        );

        assert!(success);
        assert!(events.is_empty(), "nothing to tell anybody: {events:?}");
    }

    /// **The two refusals leave under their OWN reason** — the second one (hub#324, «the envelope
    /// cannot be built») landed after this event was written, and it must not inherit the first
    /// one's word.
    ///
    /// For the owner both are the same problem: the invoice is not at the AEAT. For whoever has to
    /// fix it they are opposite errands — one sends somebody to the config, the other to the
    /// invoice. So the event's `reason` is `Refusal::code`, the same key the audit row already
    /// carries, and never a literal written a second time next to it.
    #[tokio::test]
    async fn a_record_that_cannot_be_declared_leaves_under_its_own_reason() {
        let mut record = queued_testing_record();
        record.as_object_mut().unwrap().remove("total_amount");
        let mut host = ChainHost::new(config_row("testing"), vec![record]);
        host.has_core_certificate = true;
        let input = json!({
            "payload": { "record_id": "rec-2" },
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1",
                         "new_ids": ["id-evt", "id-queue", "id-anchor"] }
        });

        let out = transmit_record(&input, &host)
            .await
            .expect("an undeclarable record is an outcome, not an aborted batch");

        let payload = emitted(&out.events, EVENT_RECORD_REJECTED)
            .expect("nothing reached the AEAT: that has to leave the module");
        assert_eq!(payload["reason"], json!(REASON_RECORD_NOT_DECLARABLE));
        assert_eq!(payload["invoice_number"], json!("INV-2"));
        assert!(
            payload["error_message"]
                .as_str()
                .unwrap_or_default()
                .contains("total_amount"),
            "and it says WHICH amount, or the alarm is not actionable: {payload}"
        );
    }

    /// The other refusal — the record that cannot say which tax agency owns it (hub#471) — keeps
    /// its own key. Written as a pair with the test above: one of them alone would pass with both
    /// refusals collapsed onto a single literal.
    #[tokio::test]
    async fn a_record_with_no_environment_leaves_under_the_environment_reason() {
        let mut record = queued_testing_record();
        record.as_object_mut().unwrap().remove("environment");
        let mut host = ChainHost::new(config_row("production"), vec![record]);
        host.has_core_certificate = true;
        let input = json!({
            "payload": { "record_id": "rec-2" },
            "context": { "hub_id": HUB, "now": "2026-08-06T10:00:00+02:00",
                         "current_user_id": "u1",
                         "new_ids": ["id-evt", "id-queue", "id-anchor"] }
        });

        let out = transmit_record(&input, &host)
            .await
            .expect("an unplaceable record is an outcome, not an aborted batch");

        let payload = emitted(&out.events, EVENT_RECORD_REJECTED)
            .expect("nothing was built and nothing was sent: that has to leave the module");
        assert_eq!(payload["reason"], json!(REASON_ENVIRONMENT_UNKNOWN));
    }

    /// Turns the `verifactu._insert_record` operation `create_record` returned into the row a
    /// real INSERT would have persisted: `record_id` becomes `id`, and `hub_id`/`status` — which
    /// the operation's params never carry, since the runtime's own SQL supplies them — are filled
    /// in the way it would. Feeding this back into a fresh [`ChainHost`] is how a test chains a
    /// SECOND `create_record` call, or a `validate_chain` walk, onto a record this module itself
    /// produced — instead of a hand-typed row that could silently drift from the real shape.
    fn persisted(op: &Operation, status: &str) -> Json {
        let mut row = Json::Object(op.params.clone());
        let obj = row.as_object_mut().expect("insert op params are an object");
        let id = obj.remove("record_id").unwrap_or_else(|| json!("rec"));
        obj.insert("id".into(), id);
        obj.insert("hub_id".into(), json!(HUB));
        obj.insert("status".into(), json!(status));
        row
    }

    /// **Regression test for ERPlora/hub#1270** — LOCAL half of hub#325 (the AEAT preproduction
    /// half stays blocked on the FNMT seal, pm#73).
    ///
    /// The certificate a hub signs with is a fact of the CORE (`_hub_certificate`, ADR-0202
    /// §2.1) and can be rotated at any moment — the business re-uploads its own `.p12`, or deletes
    /// it and the hub falls to the fiscal cell. `alta_hash` (chain.rs) never takes it as an input: its
    /// formula is exactly the AEAT's (`IDEmisorFactura&NumSerieFactura&FechaExpedicionFactura&
    /// TipoFactura&CuotaTotal&ImporteTotal&Huella&FechaHoraHusoGenRegistro`, Orden HAC/1177/2024)
    /// — the PREVIOUS record's own fingerprint, never who signed it. So a rotation between two
    /// records must not break `Huella(N+1) == f(…, Huella(N), …)`, and `chain.validate` — the
    /// same recompute this engine runs to audit its own chain — must still walk it and accept it.
    #[tokio::test]
    async fn the_chain_does_not_break_when_the_certificate_changes_hub1270() {
        // Record 1, signed while the core holds the business's own certificate.
        let mut host_a = ChainHost::new(config_row("testing"), vec![]);
        host_a.has_core_certificate = true;
        let out1 = create_record(&create_input(), &host_a).await.unwrap();
        let insert1 = find_op(&out1, "verifactu._insert_record");
        assert_eq!(
            insert1.params.get("previous_hash"),
            Some(&json!("")),
            "record 1 opens the chain"
        );
        let hash1 = insert1
            .params
            .get("record_hash")
            .and_then(Json::as_str)
            .expect("record 1 carries its own hash")
            .to_string();
        let record1 = persisted(insert1, "accepted");

        // Certificate ROTATION, in the shape it takes since hub#1435 retired the delegated slot:
        // the business's certificate is gone from the core and this hub is now on the CELL's road
        // (ADR-0320) — a different identity entirely, with nothing shared with the one that signed
        // record 1. Same issuer, same environment, only the certificate changed.
        let mut host_b = ChainHost::new(config_row("testing"), vec![record1.clone()]);
        host_b.has_core_certificate = false;
        let mut input2 = create_input();
        input2["payload"]["invoice_number"] = json!("F-2026-000124");
        let out2 = create_record(&input2, &host_b).await.unwrap();
        let insert2 = find_op(&out2, "verifactu._insert_record");

        assert_eq!(
            insert2.params.get("previous_hash"),
            Some(&json!(hash1)),
            "record N+1 must chain on record N's OWN fingerprint, unaffected by the certificate \
             rotation between the two — the certificate never enters `alta_hash`"
        );
        assert_eq!(
            insert2.params.get("sequence_number"),
            Some(&json!(2)),
            "the sequence keeps advancing across the rotation"
        );
        let record2 = persisted(insert2, "accepted");

        // A verifier walking the chain accepts it — the SAME recompute `chain.validate` runs to
        // audit its own work, over BOTH records, spanning the rotation. The validating host
        // reports NO certificate at all (`has_core_certificate` defaults to `false`): a third,
        // different state from either cert A or cert B, so nothing here could accidentally leak
        // "the current certificate" into the recompute and still agree by coincidence.
        let validate_input = json!({
            "payload": {},
            "context": { "hub_id": HUB, "now": "2026-08-06T11:00:00+02:00",
                         "current_user_id": "u1", "new_ids": ["id-evt"] }
        });
        let valid_host = ChainHost::new(
            config_row("testing"),
            vec![record1.clone(), record2.clone()],
        );
        let out = validate_chain(&validate_input, &valid_host).await.unwrap();
        let event = find_op(&out, "verifactu._insert_event");
        assert_eq!(
            event.params.get("event_type"),
            Some(&json!("chain_validated")),
            "the chain must survive the certificate rotation: {:?}",
            event.params.get("message")
        );

        // NEGATIVE: a tampered record 1 — as if it had silently been re-signed instead of merely
        // re-transmitted — is exactly the break this guard has to catch. Without this half, a
        // verifier that always says "valid" would pass the assertion above for the wrong reason.
        let mut tampered = record1;
        tampered["record_hash"] = json!("f".repeat(64));
        let broken_host = ChainHost::new(config_row("testing"), vec![tampered, record2]);
        let out = validate_chain(&validate_input, &broken_host).await.unwrap();
        let event = find_op(&out, "verifactu._insert_event");
        assert_eq!(
            event.params.get("event_type"),
            Some(&json!("chain_error")),
            "a tampered record must still break the chain the verifier walks"
        );
    }
}
