//! Diagnostics run and AEAT consult snapshot — split out of `lib.rs` verbatim (hub#1405).

use crate::*;
use erplora_runtime::producer_facts::ProducerFacts;

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

    // El registro de MUESTRA. Se arma ANTES de saber por dónde sale el hub porque las dos vías lo
    // necesitan igual: la propia lo presenta a la AEAT y la delegada lo construye y lo valida sin
    // presentarlo (hub#1485). Los importes de muestra son los de arriba: base 100,00 € · IVA 21 %.
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

    let mut cert_ok = false;
    let cert_message;
    // WHY the test failed, as a code the module translates (hub#1575). The prose below is the
    // same sentence it always was and keeps travelling as `cert_message`: it is what a hub on an
    // older module version still paints, exactly like `message` since hub#1178.
    let mut cert_reason: Option<CertReason> = None;
    let mut aeat = Json::Null;
    let mut gateway = Json::Null;
    // Whether the test stopped on a field of THIS hub instead of on the road (hub#1531). It is a
    // fact of its own because the two ask for opposite things from whoever reads the event: one is
    // a form to fill, the other a service to wait for.
    let mut missing_issuer_nif = false;
    // And whether it stopped on the test RECORD this hub's own data produces (hub#1559). Same
    // shape, same reason: «your configuration does not yield a valid record» asks for a form, «the
    // gateway cannot transmit» asks for patience, and only one of them is true at a time.
    let mut invalid_sample_record = false;

    // ── ¿POR DÓNDE sale este hub? (hub#1485) ─────────────────────────────────────────────────
    // Which road this hub is ON, in the CORE's words (`certificate::route_of`), so the screen
    // reads ONE vocabulary and not two. It is answered even when the road turns out to be
    // unusable: a hub that has not enrolled yet is still on the delegated road — it just cannot
    // reach the cell.
    let road = if has_certificate(&config) {
        erplora_runtime::certificate::ROUTE_OWN
    } else {
        erplora_runtime::certificate::ROUTE_DELEGATED
    };

    // La MISMA puerta que la transmisión y la consulta (`resolve_route`, hub#1432). Antes era
    // el gate del certificado propio, que solo sabe del `.p12` del negocio: por la celda
    // (ADR-0320) contestaba «no hay certificado» a un hub que transmite perfectamente, y el botón
    // «probar conexión» informaba de un fallo de certificado a un hub sano (hub#1485). Un
    // diagnóstico que miente sobre el camino sano es peor que no tenerlo.
    match resolve_route(host, &ctx.hub_id, &config).await {
        Ok(TransmitRoute::Direct { identity, holder }) => {
            let route = TransmitRoute::Direct { identity, holder };
            cert_ok = true;
            let loaded = constant_reason("certificate_loaded", "Certificado cargado correctamente.");
            cert_message = loaded.prose.clone();
            cert_reason = Some(loaded);
            if issuer_nif.is_empty() {
                // Sin NIF del obligado no se puede enviar (la AEAT lo rechazaría por formato).
                aeat = json!({ "ok": false, "error": "Configura el NIF del obligado tributario (emisor) antes de enviar la prueba." });
            } else {
                // Mismo gate que la transmisión real: la prueba tiene que fallar donde falla el
                // envío de verdad, no ir a la AEAT a que lo diga con un 4102. Y si el sobre ni
                // siquiera se puede construir (hub#324), el diagnóstico lo dice aquí.
                match sample_envelope(&sample, &config, &route, &ctx.hub_id, &issuer_nif) {
                    Err(reason) => aeat = json!({ "ok": false, "error": reason.prose }),
                    Ok(xml) => {
                        let TransmitRoute::Direct { identity, .. } = route else {
                            unreachable!("this arm matched Direct")
                        };
                        match aeat::post_soap(transmission_endpoint(&config), identity, &xml).await {
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
        Ok(TransmitRoute::Gateway(access)) => {
            // 🔴 Por la celda el diagnóstico **NO EMITE**. La muestra sería un alta REAL presentada
            // con el Sello de ERPlora por cuenta del cliente: en `production` consumiría la
            // autorización de representación (Anexo I) que la celda exige para cualquier envío, y
            // ningún registro remitido se puede deshacer (ADR-0189). Así que esta vía **prueba el
            // camino en vez de usarlo** — y es además la comprobación más fuerte disponible aquí:
            // la identidad de máquina abre el ingress mTLS de la celda, el plano de control ya
            // acuñó el Bearer para construir el acceso, y la celda dice si su Sello puede firmar
            // hoy. `aeat` se queda a null, que es el «no enviado» que la pantalla ya pinta.
            let route = TransmitRoute::Gateway(access);
            let TransmitRoute::Gateway(ref access) = route else {
                unreachable!("this arm matched Gateway")
            };

            // 🔎 La celda se sondea SIEMPRE y PRIMERO (hub#1531). `/readyz` no necesita nada de la
            // config de este hub, así que no hay motivo para dejar el bloque `gateway` a null:
            // contar «la pasarela no está disponible» sin haberla preguntado es justo cómo el
            // diagnóstico acabó culpando a un servicio sano de un campo que el negocio no había
            // rellenado. Un bloque vacío se lee igual que un sondeo que nadie hizo.
            let cell = match crate::gateway::probe_readiness(access).await {
                Ok(readiness) => {
                    gateway = json!({
                        "ok": readiness.ready,
                        "status": readiness.status,
                        "reason": readiness.reason,
                        "transmission_enabled": readiness.transmission_enabled,
                        "holder_nif": readiness.holder_nif,
                    });
                    if readiness.ready {
                        Ok(())
                    } else {
                        Err(gateway_not_ready_reason(&readiness))
                    }
                }
                Err(e) => {
                    gateway = json!({ "ok": false, "error": e.to_string() });
                    Err(CertReason::new(
                        "gateway_unreachable",
                        json!({ "error": e.to_string() }),
                        format!("No se pudo contactar con la pasarela fiscal: {e}"),
                    ))
                }
            };

            // Y lo que le falta a ESTE hub manda sobre lo que conteste la celda: es la mitad que el
            // negocio puede arreglar, en la misma pantalla que está mirando. Nombrar la pasarela en
            // su lugar lo manda a vigilar un servicio que no puede tocar (hub#1531).
            if issuer_nif.is_empty() {
                missing_issuer_nif = true;
                let missing = constant_reason(
                    "issuer_nif_missing",
                    "Configura el NIF del obligado tributario (emisor) antes de probar la conexión.",
                );
                cert_message = missing.prose.clone();
                cert_reason = Some(missing);
            } else if let Err(reason) = sample_envelope(&sample, &config, &route, &ctx.hub_id, &issuer_nif)
            {
                // El sobre se construye y se valida IGUAL que en la vía propia. Una config que no
                // produce un registro conforme es un fallo de ESTE hub, y el diagnóstico es donde
                // tiene que salir — solo que sin dárselo a Hacienda para que lo diga ella.
                invalid_sample_record = true;
                cert_message = reason.prose.clone();
                cert_reason = Some(reason);
            } else {
                match cell {
                    Ok(()) => {
                        cert_ok = true;
                        let ready = constant_reason(
                            "gateway_ready",
                            "Pasarela fiscal disponible: ERPlora presenta por ti.",
                        );
                        cert_message = ready.prose.clone();
                        cert_reason = Some(ready);
                    }
                    Err(reason) => {
                        cert_message = reason.prose.clone();
                        cert_reason = Some(reason);
                    }
                }
            }
        }
        Err(e) => {
            // Sin vía NINGUNA. Con certificado del negocio el mensaje sigue hablando del
            // certificado, que es lo que hay que arreglar; sin él habla de la pasarela, porque
            // mandar a alguien a renovar un `.p12` que no tiene es el defecto de hub#1485 otra vez.
            let reason = if road == erplora_runtime::certificate::ROUTE_OWN {
                CertReason::new(
                    "certificate_unavailable",
                    json!({ "error": e.to_string() }),
                    format!("El certificado no carga o no está configurado: {e}"),
                )
            } else {
                CertReason::new(
                    "no_transmission_route",
                    json!({ "error": e.to_string() }),
                    format!("Este hub no tiene vía de transmisión: {e}"),
                )
            };
            cert_message = reason.prose.clone();
            cert_reason = Some(reason);
        }
    }

    let details = json!({
        "cert_ok": cert_ok,
        "cert_message": cert_message,
        // The verdict behind the dash, as a CODE + facts (hub#1575), so the module's catalogue can
        // say it in the language of the business instead of interpolating Spanish prose inside an
        // English sentence. Since verifactu#95 the runs that SUCCEED carry one too: «it went well»
        // was the last sentence a business read in Spanish, and it is the one it reads most often.
        // `null` is left for the road that answers nothing at all — never for a verdict.
        "cert_reason": cert_reason.as_ref().map_or(Json::Null, CertReason::as_details),
        // Which road this hub files on (hub#1485). The words are the core's own
        // (`certificate::ROUTE_OWN`/`ROUTE_DELEGATED`) because the screen programs against them.
        "route": road,
        "issuer_nif": issuer_nif,
        "invoice_type": invoice_type,
        "recipient_nif": recipient_nif,
        "environment": environment,
        "sample_number": sample_number,
        "huella": huella,
        "qr_url": qr_url,
        "aeat": aeat,
        "gateway": gateway,
    });
    // hub#1178: dos hechos distintos, dos claves — «la prueba corrió» y «el certificado no vale»
    // piden cosas distintas de quien lo lee. Desde hub#1485 hay un tercero: por la vía delegada lo
    // que falla NO es un certificado que el negocio pueda arreglar, sino la pasarela — mandarle a
    // renovar un `.p12` que no tiene es el defecto original. Y desde hub#1531 un cuarto: cuando lo
    // que falta es un dato SUYO, culpar a la pasarela lo manda a vigilar un servicio que no puede
    // tocar en vez de rellenar el campo que tiene delante. Y desde hub#1559 un quinto: el NIF puede
    // estar puesto y el registro de prueba no salir igual — culpar entonces a la pasarela nombra a
    // un servicio al que ni se le ha pedido llevar ese registro.
    //
    // Por la vía propia el mismo hueco ya se cuenta bien sin clave nueva: el certificado carga
    // (`cert_ok`) y el bloque `aeat` lleva el «configura el NIF antes de enviar» que la pantalla
    // pinta en rojo, así que ahí la clave sigue siendo la de la prueba que corrió.
    let message_key = if missing_issuer_nif {
        "verifactu.diagnostic_issuer_nif_missing"
    } else if invalid_sample_record {
        "verifactu.diagnostic_sample_record_invalid"
    } else if cert_ok {
        "verifactu.diagnostic_ran"
    } else if road == erplora_runtime::certificate::ROUTE_OWN {
        "verifactu.diagnostic_certificate_invalid"
    } else {
        "verifactu.diagnostic_gateway_unavailable"
    };

    Ok(Output::new().with_operation(op(
        "verifactu._insert_event",
        json!({
            "event_id": ctx.new_ids.first().cloned().unwrap_or_default(),
            "record_id": Json::Null,
            "event_type": "diagnostic",
            "severity": if cert_ok { "info" } else { "warning" },
            // La prosa acompaña a la CLAVE, no a la vía: es el fallback que el módulo pinta
            // mientras su catálogo no traduzca la clave (verifactu#63), así que tiene que decir lo
            // mismo que ella.
            "message": match message_key {
                "verifactu.diagnostic_ran" => format!("Prueba VeriFactu ejecutada ({environment})"),
                "verifactu.diagnostic_issuer_nif_missing" => {
                    "Prueba VeriFactu: falta el NIF del obligado tributario".to_string()
                }
                "verifactu.diagnostic_certificate_invalid" => {
                    "Prueba VeriFactu: certificado no válido".to_string()
                }
                "verifactu.diagnostic_sample_record_invalid" => {
                    "Prueba VeriFactu: el registro de prueba no es válido".to_string()
                }
                _ => "Prueba VeriFactu: la pasarela fiscal no está disponible".to_string(),
            },
            "details": details_for(message_key, details),
            "timestamp": ctx.now,
        }),
    )))
}

/// El sobre de MUESTRA, construido y comprobado **exactamente como lo estaría uno de verdad**:
/// mismo constructor, mismo XSD y el mismo `Representante` derivado de la vía que lo llevaría
/// ([`TransmitRoute::presenter`], ADR-0268 §4).
///
/// Que el presentador venga de la VÍA y no de `None` es lo que hace que el control pueda cazar el
/// positivo: en la vía propia de una gestoría el envío real declara representación (hub#1478) y un
/// diagnóstico que validara el sobre sin ella pasaría en verde para luego fallar con un 4112 en la
/// primera factura; por la celda el presentador es el Sello, que es justo la diferencia que la AEAT
/// mira. Se separa en su propia función porque las dos vías lo necesitan igual — la delegada lo
/// construye y lo valida aunque NO lo envíe (hub#1485).
fn sample_envelope(
    sample: &Json,
    config: &Json,
    route: &TransmitRoute,
    hub_id: &str,
    issuer_nif: &str,
) -> std::result::Result<String, CertReason> {
    let xml = aeat::build_soap(sample, config, None, hub_id).map_err(|e| {
        // WHICH of the two it is, asked of the CONFIG and never of the message (hub#1575): the
        // prose belongs to the engine and would move with any reword, while whether the control
        // plane has served the producer facts is a fact this hub can read. The two ask opposite
        // things of the reader — one waits for the next heartbeat, the other has a form to fix.
        let missing_facts = config
            .get("producer_facts")
            .and_then(ProducerFacts::parse)
            .is_none();
        CertReason::new(
            if missing_facts {
                "producer_facts_missing"
            } else {
                "sample_envelope_invalid"
            },
            json!({ "error": e.to_string() }),
            e.to_string(),
        )
    })?;
    let xml = aeat::set_representative(&xml, route.presenter(), issuer_nif);
    xsd::validate_registro(&xml).map_err(|e| {
        CertReason::new(
            "sample_record_schema_invalid",
            // The element the validator named travels on its own: it is the actionable half, and
            // the AEAT spells those in Spanish by law, so it reads the same in either language.
            json!({ "detail": e.to_string() }),
            format!("XML no conforme al esquema: {e}"),
        )
    })?;
    Ok(xml)
}

/// Why the test failed, as a **stable code + facts** — plus the Spanish prose that was the whole
/// answer until hub#1575.
///
/// The verdict already travelled as a key (`message_key`, hub#1178) and the module translated it;
/// the REASON behind the dash did not, so a business running in English read «…does not produce a
/// valid test record — faltan los hechos del productor…»: half a sentence in a language it did not
/// choose, and it was the half that says what to fix.
///
/// `prose` is **not** withdrawn: it is the fallback painted by a hub whose module does not know the
/// code yet, exactly the contract `message` has had since hub#1178. Dropping it the day the code
/// lands would leave those hubs with half an empty sentence, which is worse than a Spanish one.
#[derive(Debug)]
pub(crate) struct CertReason {
    /// Stable: it is what the module's catalogue indexes. Never renamed without translating it.
    code: &'static str,
    /// The data the sentence needs, already split out of it. Always an object.
    facts: Json,
    /// The engine's own Spanish sentence, exactly as it has always been written.
    prose: String,
}

impl CertReason {
    fn new(code: &'static str, facts: Json, prose: impl Into<String>) -> Self {
        Self {
            code,
            facts,
            prose: prose.into(),
        }
    }

    /// `{"code": …}` with the facts beside it — the shape `details` publishes and the module reads.
    fn as_details(&self) -> Json {
        let mut out = json!({ "code": self.code });
        if let (Some(target), Some(source)) = (out.as_object_mut(), self.facts.as_object()) {
            for (key, value) in source {
                target.insert(key.clone(), value.clone());
            }
        }
        out
    }
}

/// A verdict with nothing to fill: one code, one sentence, no facts (verifactu#95).
///
/// It exists so the runs that SUCCEED travel the same channel as the ones that fail. Until then the
/// module had no code to look up on a good run and fell back to `cert_message`, which is the
/// engine's Spanish — so the two runs a business sees most often were the two it could not read.
fn constant_reason(code: &'static str, prose: &str) -> CertReason {
    CertReason::new(code, json!({}), prose)
}

/// The cell answered and said no. Which of the two shapes it takes depends on whether it said WHY:
/// a cell that gives a reason carries it in its sentence; one that does not — an older cell, an
/// intermediary's error page — carries a sentence that stands on its own.
///
/// Two codes and not one with an empty hole, because a `{detail}` painted blank reads as a broken
/// screen rather than as a service that kept quiet.
fn gateway_not_ready_reason(readiness: &crate::gateway::GatewayReadiness) -> CertReason {
    let detail = if readiness.reason.is_empty() {
        readiness.status.clone()
    } else {
        readiness.reason.clone()
    };
    if detail.is_empty() {
        return CertReason::new(
            "gateway_not_ready_unspecified",
            json!({}),
            "La pasarela fiscal no puede transmitir ahora mismo.",
        );
    }
    CertReason::new(
        "gateway_not_ready",
        json!({
            "status": readiness.status,
            "reason": readiness.reason,
            "detail": detail,
        }),
        format!("La pasarela fiscal no puede transmitir ahora mismo ({detail})."),
    )
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
    // Built BEFORE opening the connection: an envelope without the obligado's registered name is
    // not valid, and there is no point talking to Hacienda just to collect a 4102.
    let xml = consult_envelope(config, route, issuer_nif, now)?;
    let body = match route {
        // Vía propia: TLS mutua con el certificado del core (opaca) o legacy. Ver ADR-0079.
        TransmitRoute::Direct { identity, .. } => {
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

/// The envelope of ONE consult, with **who asks** answered by the road that will carry it
/// ([`TransmitRoute::presenter`], ADR-0268 §4).
///
/// Through the cell the presenter is whoever the control plane SIGNED into the token, same as the
/// alta's `Representante` (hub#1460) — but here it travels as a FLAG, not as a block: the consult
/// schema admits no `Representante`. On the own road it is the holder of the `.p12` the hub has
/// put up (hub#1478). Pinning this road back to `None` would emit the block on the alta and NOT
/// the flag on the consult — the same 4112 through the other door, which is why the derivation is
/// extracted where a test without network can guard it
/// (`tests::the_own_route_raises_the_consult_representation_flag_hub1478`).
fn consult_envelope(
    config: &Json,
    route: &TransmitRoute,
    issuer_nif: &str,
    now: &str,
) -> Result<String> {
    let issuer_name = obligado_name(config);
    let (ejercicio, periodo) = year_month(now);
    Ok(aeat::build_consult_soap(
        issuer_nif,
        &issuer_name,
        &ejercicio,
        &periodo,
        route.presenter(),
    )?)
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::transmission::tests::throwaway_identity;
    use erplora_runtime::certificate::CertificateHolder;

    /// The certless, ENROLLED hub — the one ADR-0320 sends through the fiscal cell. It answers
    /// exactly what a real one answers: a saved fiscal config (with the producer facts the core
    /// attaches), NO `certificate_signing_kind`, and the two generic primitives hub#1459 left in
    /// the host — a machine identity and a call to its own control plane.
    ///
    /// The cell it is pointed at lives under `.example`, the TLD RFC 2606 reserves as
    /// never-resolvable: the readiness probe fails on DNS, fast and offline, which is the state
    /// this test wants — the point is WHAT the diagnostic says about the road, not whether a cell
    /// happens to answer.
    struct CellHost;

    #[async_trait::async_trait]
    impl NativeHost for CellHost {
        async fn read(&self, _sql: &str, _params: &Params) -> Result<Vec<Json>> {
            Ok(vec![json!({
                "id": "cfg-1",
                "enabled": 1,
                "environment": "testing",
                "issuer_nif": "B12345678",
                "issuer_name": "PELUQUERIA LA MODERNA SL",
            })])
        }
        async fn producer_facts(&self) -> Result<Option<Json>> {
            Ok(crate::aeat::test_config_with_producer_facts()
                .get("producer_facts")
                .cloned())
        }
        async fn machine_identity(
            &self,
            _hub_id: &str,
        ) -> Result<Option<erplora_runtime::gateway_identity::MachineIdentity>> {
            Ok(Some(erplora_runtime::gateway_identity::MachineIdentity {
                identity: throwaway_identity(),
                ca_pem: throwaway_ca_pem(),
                common_name: CELL_CN.to_owned(),
            }))
        }
        async fn cloud_call(
            &self,
            _request: erplora_runtime::cloud_call::CloudRequest,
        ) -> Result<Option<erplora_runtime::cloud_call::CloudResponse>> {
            Ok(Some(erplora_runtime::cloud_call::CloudResponse {
                status: 200,
                body: json!({
                    "token": "bearer",
                    "expires_in": 300,
                    "gateway_url": "https://cell.invalid.example",
                    "obligado_nif": "B12345678",
                    "presenter_nif": "B27593136",
                    "presenter_name": "ERPLORA CLOUD SL",
                    "mtls_common_name": CELL_CN,
                })
                .to_string(),
            }))
        }
    }

    const CELL_CN: &str = "hub-cell.fiscal.erplora.internal";

    /// A throwaway CA in PEM. It has to PARSE: `reqwest` refuses to build the client when the root
    /// certificate does not, and a client that never gets built cannot tell a probe that failed
    /// from a probe that was never made — which is precisely the difference these tests measure.
    fn throwaway_ca_pem() -> Vec<u8> {
        use openssl::asn1::Asn1Time;
        use openssl::hash::MessageDigest;
        use openssl::nid::Nid;
        let group = openssl::ec::EcGroup::from_curve_name(Nid::X9_62_PRIME256V1).unwrap();
        let pkey =
            openssl::pkey::PKey::from_ec_key(openssl::ec::EcKey::generate(&group).unwrap()).unwrap();
        let mut name = openssl::x509::X509NameBuilder::new().unwrap();
        name.append_entry_by_nid(Nid::COMMONNAME, "cell-ca-test")
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
        cert.build().to_pem().unwrap()
    }

    fn diagnostics_input(hub_id: &str) -> Json {
        json!({
            "payload": { "invoice_type": "F2" },
            "context": {
                "hub_id": hub_id,
                "now": "2026-09-04T10:00:00+02:00",
                "new_ids": ["ev-1"],
            }
        })
    }

    /// The `details` the diagnostic filed, already parsed — it travels as a STRING inside the
    /// event, which is what the Settings screen reads back through `verifactu.diagnostics.last`.
    fn filed_details(out: &Output) -> Json {
        let event = out
            .operations
            .iter()
            .find(|o| o.command == "verifactu._insert_event")
            .expect("the diagnostic always files its event");
        serde_json::from_str(
            event
                .params
                .get("details")
                .and_then(Json::as_str)
                .expect("details travels as a string"),
        )
        .expect("details is JSON")
    }

    /// 🔴 **RED de hub#1485.** A hub on the cell road is transmitting perfectly, and the «test
    /// connection» button tells it its CERTIFICATE is broken — because `run_diagnostics` asked
    /// for the business `.p12` instead of `resolve_route`, the one door hub#1432 left for this
    /// question.
    /// A diagnostic that lies about the healthy road is worse than no diagnostic.
    #[tokio::test]
    async fn the_cell_road_is_never_diagnosed_as_a_broken_certificate_hub1485() {
        let out = run_diagnostics(&diagnostics_input("hub-cell"), &CellHost)
            .await
            .expect("the diagnostic always answers, on either road");
        let details = filed_details(&out);

        assert_eq!(
            details["route"],
            json!(erplora_runtime::certificate::ROUTE_DELEGATED),
            "the diagnostic has to say WHICH road it exercised, in the CORE's words: {details}"
        );
        assert_ne!(
            details["message_key"],
            json!("verifactu.diagnostic_certificate_invalid"),
            "a hub with no certificate of its own has no broken certificate to report: {details}"
        );
    }

    /// 🔒 **The guard the issue asks for by name: no AEAT emission by accident.** Through the cell
    /// the sample would be a REAL alta filed with ERPlora's Seal on the client's behalf — in
    /// `production` it would burn the Anexo I authorisation, and no filing can be undone
    /// (ADR-0189). So this road checks the road and files nothing: `aeat` stays null, which is
    /// already the «no enviado» the Settings screen paints.
    #[tokio::test]
    async fn the_cell_road_never_files_a_sample_to_the_aeat_hub1485() {
        let out = run_diagnostics(&diagnostics_input("hub-cell"), &CellHost)
            .await
            .expect("the diagnostic always answers, on either road");
        let details = filed_details(&out);

        assert!(
            details["aeat"].is_null(),
            "a diagnostic through the cell must never present a sample invoice: {details}"
        );
        // And it has to say what it DID check instead. An unreachable cell is reported as such —
        // which is also the proof that the probe was ATTEMPTED: a `gateway` block left empty would
        // read the same as one from a road nobody walked.
        assert_eq!(details["gateway"]["ok"], json!(false), "{details}");
        assert!(
            details["gateway"]["error"]
                .as_str()
                .is_some_and(|e| e.contains("pasarela")),
            "the failure has to name the leg that failed: {details}"
        );
    }

    /// 🔴 **REGRESIÓN hub#1478 — the consult door.** The alta and the consult answer the same
    /// question through [`TransmitRoute::presenter`]; pinning THIS door back to `None` would emit
    /// the `Representante` block on the alta and not the flag on the consult — the same 4112
    /// through the other door. This is the mutant that survived the first review pass of hub#1498:
    /// every consult test went straight to `build_consult_soap`, so nothing guarded the wiring.
    #[test]
    fn the_own_route_raises_the_consult_representation_flag_hub1478() {
        let route = TransmitRoute::Direct {
            identity: throwaway_identity(),
            holder: Some(CertificateHolder {
                nif: "B99999999".to_owned(),
                name: "GESTORIA MARTINEZ SL".to_owned(),
            }),
        };
        let config = json!({ "issuer_name": "CLIENTE SL" });

        let xml = consult_envelope(&config, &route, "B12345678", "2026-09-03T10:00:00Z").unwrap();

        assert!(
            xml.contains("<sum1:IndicadorRepresentante>S</sum1:IndicadorRepresentante>"),
            "a holder who is not the obligado consults as a representative: {xml}"
        );
    }

    /// 🔒 A container whose subject names nobody leaves the consult exactly as it was before
    /// hub#1478: no flag. Absence concludes nothing — the twin of
    /// `transmission::tests::a_certificate_that_names_no_holder_leaves_the_envelope_as_it_was_hub1478`.
    #[test]
    fn a_route_without_a_holder_leaves_the_consult_flag_out_hub1478() {
        let route = TransmitRoute::Direct {
            identity: throwaway_identity(),
            holder: None,
        };
        let config = json!({ "issuer_name": "CLIENTE SL" });

        let xml = consult_envelope(&config, &route, "B12345678", "2026-09-03T10:00:00Z").unwrap();

        assert!(!xml.contains("IndicadorRepresentante"), "{xml}");
    }

    /// The taxpayer's own road, UNCHANGED (hub#1485 must not move it). Reported as `own`, the
    /// certificate arm still answers about the certificate, and nothing about the cell is filed.
    ///
    /// It stops at the empty obligado on purpose: that is the last step before the wire, so the
    /// whole decision is pinned without a unit test presenting a sample invoice to Hacienda.
    #[tokio::test]
    async fn the_own_road_is_reported_as_own_and_still_talks_about_the_certificate_hub1485() {
        struct OwnCertHost;
        #[async_trait::async_trait]
        impl NativeHost for OwnCertHost {
            async fn read(&self, _sql: &str, _params: &Params) -> Result<Vec<Json>> {
                // No `issuer_nif`: the diagnostic stops right before the send.
                Ok(vec![json!({ "id": "cfg-1", "environment": "testing" })])
            }
            async fn certificate_signing_kind(&self, _hub_id: &str) -> Result<Option<String>> {
                Ok(Some("own".to_owned()))
            }
            async fn certificate_identity(&self, _hub_id: &str) -> Result<reqwest::Identity> {
                Ok(throwaway_identity())
            }
        }

        let out = run_diagnostics(&diagnostics_input("hub-own"), &OwnCertHost)
            .await
            .expect("the diagnostic always answers, on either road");
        let details = filed_details(&out);

        assert_eq!(
            details["route"],
            json!(erplora_runtime::certificate::ROUTE_OWN),
            "{details}"
        );
        assert_eq!(details["cert_ok"], json!(true), "{details}");
        assert_eq!(
            details["message_key"],
            json!("verifactu.diagnostic_ran"),
            "{details}"
        );
        assert!(
            details["gateway"].is_null(),
            "a hub that files with its own certificate has no cell to report: {details}"
        );
    }

    /// 🔒 The other half of hub#1485, and the reason the message is not shared: a hub with NO road
    /// at all — no `.p12` and no enrolled machine identity — must not be sent to renew a
    /// certificate it never had. That instruction is unfollowable, and following it is the trip to
    /// a form nobody can finish (`certificate::route_of`'s own warning).
    #[tokio::test]
    async fn a_hub_with_no_road_is_not_sent_to_renew_a_certificate_it_never_had_hub1485() {
        struct NoRoadHost;
        #[async_trait::async_trait]
        impl NativeHost for NoRoadHost {
            async fn read(&self, _sql: &str, _params: &Params) -> Result<Vec<Json>> {
                Ok(vec![json!({
                    "id": "cfg-1",
                    "environment": "testing",
                    "issuer_nif": "B12345678",
                })])
            }
        }

        let out = run_diagnostics(&diagnostics_input("hub-nowhere"), &NoRoadHost)
            .await
            .expect("the diagnostic always answers, even with nowhere to go");
        let details = filed_details(&out);

        assert_eq!(
            details["route"],
            json!(erplora_runtime::certificate::ROUTE_DELEGATED),
            "{details}"
        );
        assert_eq!(details["cert_ok"], json!(false), "{details}");
        assert_eq!(
            details["message_key"],
            json!("verifactu.diagnostic_gateway_unavailable"),
            "the fault is the missing road, not a broken certificate: {details}"
        );
        assert!(
            !details["cert_message"]
                .as_str()
                .unwrap_or_default()
                .contains("El certificado no carga"),
            "nobody can renew a certificate they never uploaded: {details}"
        );
    }

    /// 🔒 The sample is checked against the envelope that WOULD travel, presenter included. A
    /// diagnostic that validated a `Representante`-less envelope would go green for a gestoría and
    /// then collect a 4112 on the first real invoice (hub#1478) — a control that cannot catch the
    /// positive.
    #[test]
    fn the_sample_envelope_declares_the_presenter_of_the_road_that_would_file_it_hub1485() {
        let sample = json!({
            "record_type": "alta",
            "issuer_nif": "B12345678",
            "issuer_name": "PELUQUERIA LA MODERNA SL",
            "invoice_number": "PRUEBA-2026-09-04",
            "invoice_date": "2026-09-04",
            "invoice_type": "F2",
            "description": "Factura de PRUEBA (diagnóstico VeriFactu)",
            "tax_rate": 21,
            "tax_breakdown": r#"{"21.00":{"base":10000,"tax":2100}}"#,
            "base_amount": 10000,
            "tax_amount": 2100,
            "total_amount": 12100,
            "recipient_nif": "",
            "recipient_name": "",
            "record_hash": "A".repeat(64),
            "is_first_record": 1,
            "generation_timestamp": "2026-09-04T10:00:00+02:00",
        });
        let config = crate::aeat::test_config_with_producer_facts();
        let gestoria = TransmitRoute::Direct {
            identity: throwaway_identity(),
            holder: Some(CertificateHolder {
                nif: "B99999999".to_owned(),
                name: "GESTORIA MARTINEZ SL".to_owned(),
            }),
        };

        let xml = sample_envelope(&sample, &config, &gestoria, "hub-1", "B12345678")
            .expect("the sample envelope is conforming");
        assert!(
            xml.contains("<sum1:Representante>") && xml.contains("B99999999"),
            "a filing signed by somebody who is not the obligado declares it: {xml}"
        );

        let owner = TransmitRoute::Direct {
            identity: throwaway_identity(),
            holder: Some(CertificateHolder {
                nif: "B12345678".to_owned(),
                name: "PELUQUERIA LA MODERNA SL".to_owned(),
            }),
        };
        let xml = sample_envelope(&sample, &config, &owner, "hub-1", "B12345678")
            .expect("the sample envelope is conforming");
        assert!(
            !xml.contains("<sum1:Representante>"),
            "and somebody filing their own records declares nobody: {xml}"
        );
    }

    /// The same enrolled, certless hub as [`CellHost`] — except the business never filled in its
    /// own obligado NIF. Everything about the cell is identical, so any difference in the verdict
    /// is about the MISSING FIELD and nothing else.
    struct CellHostWithoutIssuerNif;

    #[async_trait::async_trait]
    impl NativeHost for CellHostWithoutIssuerNif {
        async fn read(&self, _sql: &str, _params: &Params) -> Result<Vec<Json>> {
            Ok(vec![json!({
                "id": "cfg-1",
                "enabled": 1,
                "environment": "testing",
                "issuer_nif": "",
                "issuer_name": "",
            })])
        }
        async fn producer_facts(&self) -> Result<Option<Json>> {
            CellHost.producer_facts().await
        }
        async fn machine_identity(
            &self,
            hub_id: &str,
        ) -> Result<Option<erplora_runtime::gateway_identity::MachineIdentity>> {
            CellHost.machine_identity(hub_id).await
        }
        async fn cloud_call(
            &self,
            request: erplora_runtime::cloud_call::CloudRequest,
        ) -> Result<Option<erplora_runtime::cloud_call::CloudResponse>> {
            CellHost.cloud_call(request).await
        }
    }

    /// 🔴 **RED de hub#1531.** A hub on the cell road that never filled in its obligado NIF is told
    /// THE GATEWAY is unavailable — a service it cannot touch, and most likely perfectly healthy —
    /// when the only thing missing is a field on the screen it is already looking at. It is the
    /// hub#1485 defect one box further in: the diagnostic blames the road for what the business
    /// owns, and sends it to watch a status page instead of typing its own tax ID.
    #[tokio::test]
    async fn a_missing_issuer_nif_is_never_reported_as_an_unavailable_gateway_hub1531() {
        let out = run_diagnostics(
            &diagnostics_input("hub-cell-no-nif"),
            &CellHostWithoutIssuerNif,
        )
        .await
        .expect("the diagnostic always answers, on either road");
        let details = filed_details(&out);

        assert_eq!(
            details["message_key"],
            json!("verifactu.diagnostic_issuer_nif_missing"),
            "the field this hub is missing is its own verdict, not a gateway fault: {details}"
        );
        assert!(
            details["cert_message"]
                .as_str()
                .unwrap_or_default()
                .contains("NIF"),
            "and the sentence names the field the business has to fill: {details}"
        );
    }

    /// 🔒 The other half of hub#1531: `/readyz` needs NOTHING from this hub's config, so there is
    /// no reason to leave the cell unprobed and its block at `null`. Reporting on a road nobody
    /// walked is exactly how the screen came to call a healthy gateway unavailable — and an empty
    /// block reads the same as a probe that was never made.
    #[tokio::test]
    async fn the_cell_is_still_probed_when_the_issuer_nif_is_missing_hub1531() {
        let out = run_diagnostics(
            &diagnostics_input("hub-cell-no-nif"),
            &CellHostWithoutIssuerNif,
        )
        .await
        .expect("the diagnostic always answers, on either road");
        let details = filed_details(&out);

        assert!(
            !details["gateway"].is_null(),
            "the cell answers without the NIF, so its state is knowable and belongs in the report: \
             {details}"
        );
        // The cell of this test is unreachable by construction (`.example` never resolves), so the
        // block has to carry THAT — a probe that failed, never a probe that was skipped.
        assert_eq!(details["gateway"]["ok"], json!(false), "{details}");
        assert!(
            details["gateway"]["error"]
                .as_str()
                .is_some_and(|e| e.contains("pasarela")),
            "the failure has to name the leg that failed: {details}"
        );
    }

    /// The same enrolled, certless hub as [`CellHost`] — obligado NIF filled in, cell identical —
    /// except the producer facts this hub files with never arrived from the control plane, so the
    /// test record cannot be built at all (`sistema_informatico` refuses: a legal declaration has
    /// no defaults).
    ///
    /// It is the reachable half of `sample_envelope`. The other half — a record that builds and
    /// then fails the XSD — is closed today from every input the diagnostic has: the sample is
    /// hardcoded well-formed, `ProducerFacts::parse` already enforces the bounds the schema
    /// checks, and `representative_block` refuses a half presenter rather than emit one. Both
    /// halves leave through the SAME arm, so pinning this one pins the verdict for both.
    struct CellHostWithoutProducerFacts;

    #[async_trait::async_trait]
    impl NativeHost for CellHostWithoutProducerFacts {
        async fn read(&self, sql: &str, params: &Params) -> Result<Vec<Json>> {
            CellHost.read(sql, params).await
        }
        async fn producer_facts(&self) -> Result<Option<Json>> {
            Ok(None)
        }
        async fn machine_identity(
            &self,
            hub_id: &str,
        ) -> Result<Option<erplora_runtime::gateway_identity::MachineIdentity>> {
            CellHost.machine_identity(hub_id).await
        }
        async fn cloud_call(
            &self,
            request: erplora_runtime::cloud_call::CloudRequest,
        ) -> Result<Option<erplora_runtime::cloud_call::CloudResponse>> {
            CellHost.cloud_call(request).await
        }
    }

    /// 🔴 **RED de hub#1559.** hub#1531 one box further along: the obligado NIF IS filled in, and
    /// the test record still does not come out — so the diagnostic falls through to «the fiscal
    /// gateway is unavailable», naming a service the business cannot touch and that was never even
    /// asked to carry this record. The long text does explain the real error; the headline and the
    /// KEY, which are what the screen programs against, blame the road.
    #[tokio::test]
    async fn a_sample_record_that_does_not_come_out_is_never_blamed_on_the_gateway_hub1559() {
        let out = run_diagnostics(
            &diagnostics_input("hub-cell-no-facts"),
            &CellHostWithoutProducerFacts,
        )
        .await
        .expect("the diagnostic always answers, on either road");
        let details = filed_details(&out);

        // The control has to catch the positive it claims to catch: this run stops on the RECORD,
        // not on the cell. Both are false in this test, and only one of them is the verdict.
        assert!(
            details["cert_message"]
                .as_str()
                .unwrap_or_default()
                .contains("no se puede construir el registro"),
            "this case has to stop on the sample record, not on the road: {details}"
        );
        assert_eq!(
            details["message_key"],
            json!("verifactu.diagnostic_sample_record_invalid"),
            "a test record that does not come out is this hub's own verdict, not a gateway fault: \
             {details}"
        );
    }

    /// The event as filed, so a test can read the prose the screen paints while the module's
    /// catalogue has not caught up with a key (hub#1178: `message` is the fallback, and for a hub
    /// on an older module version it is the ONLY thing shown).
    fn filed_event_message(out: &Output) -> String {
        out.operations
            .iter()
            .find(|o| o.command == "verifactu._insert_event")
            .and_then(|o| o.params.get("message"))
            .and_then(Json::as_str)
            .expect("the diagnostic always files its event with a sentence")
            .to_string()
    }

    /// 🔒 The HEADLINE has to move with the key. `message_key` is what the module renders once its
    /// catalogue knows the key; `message` is what every hub shows until then — leaving the prose on
    /// the gateway would fix the code and change nothing on the screen.
    #[tokio::test]
    async fn the_headline_stops_naming_the_gateway_too_hub1559() {
        let out = run_diagnostics(
            &diagnostics_input("hub-cell-no-facts"),
            &CellHostWithoutProducerFacts,
        )
        .await
        .expect("the diagnostic always answers, on either road");
        let message = filed_event_message(&out);

        assert!(
            !message.contains("pasarela"),
            "the headline must stop blaming a service that was never asked to carry this: {message}"
        );
        assert!(
            message.contains("registro de prueba"),
            "and it has to name what actually failed: {message}"
        );
    }

    /// 🔒 And the sentence keeps carrying WHY the record was refused. A verdict of its own that
    /// dropped the reason would trade one lie for a silence: the person would know it is not the
    /// gateway and still not know what to fix.
    #[tokio::test]
    async fn the_verdict_still_carries_the_reason_the_record_was_refused_hub1559() {
        let out = run_diagnostics(
            &diagnostics_input("hub-cell-no-facts"),
            &CellHostWithoutProducerFacts,
        )
        .await
        .expect("the diagnostic always answers, on either road");
        let details = filed_details(&out);

        assert_eq!(details["cert_ok"], json!(false), "{details}");
        assert!(
            !details["cert_message"]
                .as_str()
                .unwrap_or_default()
                .contains("pasarela"),
            "the sentence must stop naming a service that was never asked to carry this: {details}"
        );
    }

    /// 🔒 The same guard hub#1531 left for its own case: `/readyz` needs nothing from this hub, so
    /// the cell is still probed and its block still filed. Otherwise the new verdict would buy a
    /// truthful headline by hiding the state of the road — and an empty block reads exactly like a
    /// probe nobody made.
    #[tokio::test]
    async fn the_cell_is_still_probed_when_the_sample_record_is_invalid_hub1559() {
        let out = run_diagnostics(
            &diagnostics_input("hub-cell-no-facts"),
            &CellHostWithoutProducerFacts,
        )
        .await
        .expect("the diagnostic always answers, on either road");
        let details = filed_details(&out);

        assert!(
            !details["gateway"].is_null(),
            "the cell answers whatever this hub's config says, so its state belongs in the report: \
             {details}"
        );
        assert_eq!(details["gateway"]["ok"], json!(false), "{details}");
        // And nothing was filed: this road checks the road, it never uses it (ADR-0189).
        assert!(
            details["aeat"].is_null(),
            "a diagnostic through the cell must never present a sample invoice: {details}"
        );
    }

    // ── hub#1575: the reason behind the dash travels as a CODE ────────────────────────────────

    /// A hub on the CELL road whose obligado NIF is set and whose sample record still does not
    /// come out — the same host hub#1559 left, asked the question hub#1575 asks.
    ///
    /// 🔴 **RED de hub#1575.** The verdict already travels as a key the module translates
    /// (`message_key`), but the REASON behind the dash is Spanish prose the engine wrote, and the
    /// module interpolates it raw as `{cert_message}`. An English reader gets «…does not produce a
    /// valid test record — faltan los hechos del productor…»: half a sentence in a language they
    /// did not choose, and it is the half that says what to fix.
    #[tokio::test]
    async fn the_reason_a_test_failed_travels_as_a_code_hub1575() {
        let out = run_diagnostics(
            &diagnostics_input("hub-cell-no-facts"),
            &CellHostWithoutProducerFacts,
        )
        .await
        .expect("the diagnostic always answers, on either road");
        let details = filed_details(&out);

        assert_eq!(
            details["cert_reason"]["code"],
            json!("producer_facts_missing"),
            "the reason has to be a code the module can translate, not prose: {details}"
        );
        // …and the FACTS travel with it. The catalogue sentences interpolate them by name, so a
        // code that arrives bare prints `{error}` braces and all on a fiscal screen — the one
        // shape worse than the Spanish it replaces. Caught by mutation: publishing only the code
        // left all 208 tests green.
        assert!(
            details["cert_reason"]["error"]
                .as_str()
                .is_some_and(|e| !e.is_empty()),
            "the facts the module's sentence needs have to travel with the code: {details}"
        );
    }

    /// 🔒 The publisher itself, on its own: every fact goes out BESIDE the code, at the top level
    /// of `cert_reason`, which is where the module reads them from.
    ///
    /// Nested or dropped, the catalogue would print its placeholders raw. This is the control that
    /// caught it — the end-to-end test above only ever looked at `code`, so an `as_details` that
    /// published nothing else passed the whole suite.
    #[test]
    fn the_published_reason_carries_its_facts_beside_the_code_hub1575() {
        let reason = CertReason::new(
            "gateway_not_ready",
            json!({ "status": "expired", "reason": "", "detail": "expired" }),
            "prose",
        );

        assert_eq!(
            reason.as_details(),
            json!({
                "code": "gateway_not_ready",
                "status": "expired",
                "reason": "",
                "detail": "expired",
            }),
            "the module reads the facts from the top level, next to the code"
        );
    }

    /// 🔒 And the prose STAYS. It is the fallback a hub on an older module version paints — the
    /// same contract `message` has carried since hub#1178. Dropping it the day the code lands
    /// would leave those hubs with an empty half-sentence, which is worse than the Spanish one.
    #[tokio::test]
    async fn the_spanish_prose_stays_as_the_fallback_for_older_modules_hub1575() {
        let out = run_diagnostics(
            &diagnostics_input("hub-cell-no-facts"),
            &CellHostWithoutProducerFacts,
        )
        .await
        .expect("the diagnostic always answers, on either road");
        let details = filed_details(&out);

        assert!(
            details["cert_message"]
                .as_str()
                .unwrap_or_default()
                .contains("no se puede construir el registro"),
            "the prose is the fallback for a module that does not know the code yet: {details}"
        );
    }

    /// A cell that cannot be reached is a road fault, and it says so with its own code: what the
    /// business does about it (wait, retry) is the opposite of what a broken sample record asks
    /// for (fix the settings), so the two cannot share a sentence.
    #[tokio::test]
    async fn an_unreachable_cell_reports_its_own_reason_code_hub1575() {
        let out = run_diagnostics(&diagnostics_input("hub-cell"), &CellHost)
            .await
            .expect("the diagnostic always answers, on either road");
        let details = filed_details(&out);

        assert_eq!(
            details["cert_reason"]["code"],
            json!("gateway_unreachable"),
            "{details}"
        );
    }

    /// A hub with NO road at all: not enrolled and with no `.p12` of its own. Its own code, for
    /// the same reason hub#1485 gave it its own sentence — «renew your certificate» is
    /// unfollowable advice for somebody who never had one.
    #[tokio::test]
    async fn a_hub_with_no_road_reports_the_missing_road_as_a_code_hub1575() {
        struct NoRoadHost;
        #[async_trait::async_trait]
        impl NativeHost for NoRoadHost {
            async fn read(&self, _sql: &str, _params: &Params) -> Result<Vec<Json>> {
                Ok(vec![json!({
                    "id": "cfg-1",
                    "environment": "testing",
                    "issuer_nif": "B12345678",
                })])
            }
        }

        let out = run_diagnostics(&diagnostics_input("hub-nowhere"), &NoRoadHost)
            .await
            .expect("the diagnostic always answers, even with nowhere to go");
        let details = filed_details(&out);

        assert_eq!(
            details["cert_reason"]["code"],
            json!("no_transmission_route"),
            "{details}"
        );
    }

    /// The taxpayer's own road, with a container the core cannot open. Its own code too: this one
    /// IS a certificate to renew, and it is the only reason of the five that says so.
    #[tokio::test]
    async fn an_own_certificate_that_does_not_load_reports_its_own_code_hub1575() {
        struct BrokenCertHost;
        #[async_trait::async_trait]
        impl NativeHost for BrokenCertHost {
            async fn read(&self, _sql: &str, _params: &Params) -> Result<Vec<Json>> {
                Ok(vec![json!({
                    "id": "cfg-1",
                    "environment": "testing",
                    "issuer_nif": "B12345678",
                })])
            }
            async fn certificate_signing_kind(&self, _hub_id: &str) -> Result<Option<String>> {
                Ok(Some("own".to_owned()))
            }
            async fn certificate_identity(&self, _hub_id: &str) -> Result<reqwest::Identity> {
                Err(RuntimeError::Certificate(
                    "el .p12 no abre con la contraseña guardada".into(),
                ))
            }
        }

        let out = run_diagnostics(&diagnostics_input("hub-broken-cert"), &BrokenCertHost)
            .await
            .expect("the diagnostic always answers, on either road");
        let details = filed_details(&out);

        assert_eq!(
            details["route"],
            json!(erplora_runtime::certificate::ROUTE_OWN),
            "{details}"
        );
        assert_eq!(
            details["cert_reason"]["code"],
            json!("certificate_unavailable"),
            "{details}"
        );
    }

    /// The sample record that IS built and then refused by the schema. Distinct from
    /// `producer_facts_missing` because the two ask opposite things of the reader: one waits for
    /// ERPlora's next heartbeat, the other has a field to fix — so the element the schema named
    /// travels with the code.
    ///
    /// Asked of [`sample_envelope`] directly: the diagnostic's own sample is synthetic and well
    /// formed, so the only way through this arm from `run_diagnostics` would be producer facts
    /// that parse and then break the schema — and `ProducerFacts::parse` already enforces the
    /// bounds the schema checks. A host contrived past that would be testing the stub, not the map.
    #[test]
    fn a_sample_refused_by_the_schema_carries_the_element_it_named_hub1575() {
        let config = crate::aeat::test_config_with_producer_facts();
        // The diagnostic's own sample with ONE hole the schema refuses: `Descripcion` is
        // mandatory and this one is empty.
        let sample = json!({
            "record_type": "alta",
            "issuer_nif": "B12345678",
            "issuer_name": "PELUQUERIA LA MODERNA SL",
            "invoice_number": "PRUEBA-2026-09-04",
            "invoice_date": "2026-09-04",
            "invoice_type": "F2",
            "description": "",
            "tax_rate": 21,
            "tax_breakdown": r#"{"21.00":{"base":10000,"tax":2100}}"#,
            "base_amount": 10000,
            "tax_amount": 2100,
            "total_amount": 12100,
            "recipient_nif": "",
            "recipient_name": "",
            "record_hash": "F".repeat(64),
            "is_first_record": 1,
            "generation_timestamp": "2026-09-04T10:00:00+02:00",
        });
        let route = TransmitRoute::Direct {
            identity: throwaway_identity(),
            holder: None,
        };

        let reason = sample_envelope(&sample, &config, &route, "hub-1", "B12345678")
            .expect_err("an empty Descripcion is refused by the schema");

        assert_eq!(reason.code, "sample_record_schema_invalid", "{reason:?}");
        assert!(
            reason.facts["detail"]
                .as_str()
                .unwrap_or_default()
                .contains("Descripcion"),
            "the reason has to keep naming what to fix: {reason:?}"
        );
        // And the prose stays whole for a hub whose module does not know the code yet.
        assert!(reason.prose.contains("XML no conforme al esquema"), "{reason:?}");
    }

    /// 🔒 The same envelope with nothing missing produces no reason at all — the control has to
    /// catch the positive it claims to catch, or «refused by the schema» would be what this
    /// builder answers to everything.
    #[test]
    fn a_complete_sample_is_not_refused_by_the_schema_hub1575() {
        let config = crate::aeat::test_config_with_producer_facts();
        let sample = json!({
            "record_type": "alta",
            "issuer_nif": "B12345678",
            "issuer_name": "PELUQUERIA LA MODERNA SL",
            "invoice_number": "PRUEBA-2026-09-04",
            "invoice_date": "2026-09-04",
            "invoice_type": "F2",
            "description": "Factura de PRUEBA (diagnóstico VeriFactu)",
            "tax_rate": 21,
            "tax_breakdown": r#"{"21.00":{"base":10000,"tax":2100}}"#,
            "base_amount": 10000,
            "tax_amount": 2100,
            "total_amount": 12100,
            "recipient_nif": "",
            "recipient_name": "",
            "record_hash": "F".repeat(64),
            "is_first_record": 1,
            "generation_timestamp": "2026-09-04T10:00:00+02:00",
        });
        let route = TransmitRoute::Direct {
            identity: throwaway_identity(),
            holder: None,
        };

        assert!(
            sample_envelope(&sample, &config, &route, "hub-1", "B12345678").is_ok(),
            "the diagnostic's own sample has to pass, or the guard above proves nothing"
        );
    }

    /// A cell that answers and says no gives its state as FACTS, not inside a sentence — that is
    /// what lets the module put the sentence in the reader's language and keep the state.
    #[test]
    fn a_cell_that_cannot_file_reports_its_state_as_facts_hub1575() {
        let reason = gateway_not_ready_reason(&crate::gateway::GatewayReadiness {
            ready: false,
            status: "expired".to_owned(),
            reason: "seal expired on 2026-08-31".to_owned(),
            transmission_enabled: true,
            holder_nif: "B27593136".to_owned(),
        });

        assert_eq!(reason.code, "gateway_not_ready", "{reason:?}");
        assert_eq!(reason.facts["status"], json!("expired"), "{reason:?}");
        assert_eq!(
            reason.facts["detail"],
            json!("seal expired on 2026-08-31"),
            "the sentence needs ONE value that is never empty: {reason:?}"
        );
    }

    /// 🔒 And a cell that says nothing gets a sentence that stands on its own. A `{detail}` painted
    /// blank reads like a broken screen, not like a service that stayed quiet — which is the same
    /// trade hub#1531 made for the missing-NIF verdict.
    #[test]
    fn a_cell_that_gives_no_reason_gets_a_sentence_that_stands_alone_hub1575() {
        let reason = gateway_not_ready_reason(&crate::gateway::GatewayReadiness {
            ready: false,
            status: String::new(),
            reason: String::new(),
            transmission_enabled: false,
            holder_nif: String::new(),
        });

        assert_eq!(reason.code, "gateway_not_ready_unspecified", "{reason:?}");
        assert!(!reason.prose.contains("()"), "{reason:?}");
    }

    /// 🔴 **RED de verifactu#95.** hub#1575 coded the reasons that VARY and left the three
    /// CONSTANT sentences behind, so the two runs a business sees most often — «Certificado cargado
    /// correctamente.» and «Pasarela fiscal disponible: ERPlora presenta por ti.» — stayed Spanish
    /// inside an English screen. «It went well» was the last untranslated verdict.
    ///
    /// This test used to assert the opposite (`cert_reason` null on success, hub#1575), for a
    /// reason that no longer holds: the fear was the module composing «the test ran — <reason>» out
    /// of a stale field, and its own catalogue forbids that — `diagnostic_ran` interpolates no
    /// `{cert_message}`, pinned by the module's placeholder parity test. What the code buys instead
    /// is the Settings box saying «the certificate loaded correctly» in the reader's language.
    #[tokio::test]
    async fn a_test_that_passes_says_so_with_a_code_verifactu95() {
        struct OwnCertHost;
        #[async_trait::async_trait]
        impl NativeHost for OwnCertHost {
            async fn read(&self, _sql: &str, _params: &Params) -> Result<Vec<Json>> {
                Ok(vec![json!({ "id": "cfg-1", "environment": "testing" })])
            }
            async fn certificate_signing_kind(&self, _hub_id: &str) -> Result<Option<String>> {
                Ok(Some("own".to_owned()))
            }
            async fn certificate_identity(&self, _hub_id: &str) -> Result<reqwest::Identity> {
                Ok(throwaway_identity())
            }
        }

        let out = run_diagnostics(&diagnostics_input("hub-own"), &OwnCertHost)
            .await
            .expect("the diagnostic always answers, on either road");
        let details = filed_details(&out);

        assert_eq!(details["cert_ok"], json!(true), "{details}");
        assert_eq!(
            details["cert_reason"]["code"],
            json!("certificate_loaded"),
            "a verdict the business reads has to be a code the module can translate: {details}"
        );
        // …and the Spanish stays beside it, the fallback a hub on an older module still paints.
        assert!(
            details["cert_message"]
                .as_str()
                .is_some_and(|m| m.contains("Certificado cargado")),
            "the prose is the fallback for a module that does not know the code yet: {details}"
        );
    }

    /// 🔒 The second constant: the field THIS hub never filled. It already had its own verdict key
    /// (hub#1531) but no reason code, so the Settings box — which paints `cert_message` when no
    /// reason resolves — was still handing an English reader «Configura el NIF del obligado
    /// tributario (emisor)…».
    #[tokio::test]
    async fn a_missing_issuer_nif_travels_as_a_code_verifactu95() {
        let out = run_diagnostics(
            &diagnostics_input("hub-cell-no-nif"),
            &CellHostWithoutIssuerNif,
        )
        .await
        .expect("the diagnostic always answers, on either road");
        let details = filed_details(&out);

        assert_eq!(
            details["cert_reason"]["code"],
            json!("issuer_nif_missing"),
            "{details}"
        );
    }

    /// 🔒 And the third: a cell that IS ready. This is the run a healthy delegated hub gets every
    /// time it presses the button, and the one arm of `run_diagnostics` the suite had never walked —
    /// every cell test so far pointed at `.example`, which fails DNS by design, so the success path
    /// was reachable only in production.
    #[tokio::test]
    async fn a_ready_cell_says_so_with_a_code_verifactu95() {
        let cell = canned_ready_cell().await;
        let out = run_diagnostics(&diagnostics_input("hub-cell-ready"), &ReadyCellHost(cell))
            .await
            .expect("the diagnostic always answers, on either road");
        let details = filed_details(&out);

        assert_eq!(
            details["gateway"]["ok"],
            json!(true),
            "the canned cell has to be reachable, or this test proves nothing: {details}"
        );
        assert_eq!(details["cert_ok"], json!(true), "{details}");
        assert_eq!(
            details["cert_reason"]["code"],
            json!("gateway_ready"),
            "{details}"
        );
        assert!(
            details["cert_message"]
                .as_str()
                .is_some_and(|m| m.contains("Pasarela fiscal disponible")),
            "the prose is the fallback for a module that does not know the code yet: {details}"
        );
    }

    /// A cell that answers `/readyz` with the contract body, over plain HTTP.
    ///
    /// Same trade as `gateway::tests::canned_cell`: the mTLS handshake belongs to the REAL cell and
    /// to the PRE end-to-end, and pinning it here would buy nothing this file measures. What it
    /// buys is a success arm that can be walked at all.
    async fn canned_ready_cell() -> String {
        use tokio::io::{AsyncReadExt as _, AsyncWriteExt as _};
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        tokio::spawn(async move {
            while let Ok((mut socket, _)) = listener.accept().await {
                let mut buffer = [0u8; 4096];
                let _ = socket.read(&mut buffer).await;
                let body = json!({
                    "status": "ready",
                    "reason": "",
                    "conditions": { "transmission_enabled": true },
                    "holder_nif": "B27593136",
                })
                .to_string();
                let answer = format!(
                    "HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{body}",
                    body.len()
                );
                let _ = socket.write_all(answer.as_bytes()).await;
                let _ = socket.shutdown().await;
            }
        });
        format!("http://{address}")
    }

    /// [`CellHost`] pointed at a cell that actually answers.
    struct ReadyCellHost(String);

    #[async_trait::async_trait]
    impl NativeHost for ReadyCellHost {
        async fn read(&self, sql: &str, params: &Params) -> Result<Vec<Json>> {
            CellHost.read(sql, params).await
        }
        async fn producer_facts(&self) -> Result<Option<Json>> {
            CellHost.producer_facts().await
        }
        async fn machine_identity(
            &self,
            hub_id: &str,
        ) -> Result<Option<erplora_runtime::gateway_identity::MachineIdentity>> {
            CellHost.machine_identity(hub_id).await
        }
        async fn cloud_call(
            &self,
            request: erplora_runtime::cloud_call::CloudRequest,
        ) -> Result<Option<erplora_runtime::cloud_call::CloudResponse>> {
            let mut answer = CellHost
                .cloud_call(request)
                .await?
                .expect("the cell host always answers the mint");
            let mut body: Json = serde_json::from_str(&answer.body).expect("the mint answers JSON");
            body["gateway_url"] = json!(self.0);
            answer.body = body.to_string();
            Ok(Some(answer))
        }
    }

    /// 🔒 The other half of the map: a sample the engine cannot wrap while the producer facts ARE
    /// present is this hub's own record, not a missing heartbeat — the two ask opposite things of
    /// the reader. Without this positive, «always `producer_facts_missing`» survived the suite, and
    /// a business would have been told to wait for a sync that fixes nothing.
    #[test]
    fn a_sample_the_engine_cannot_wrap_with_facts_present_is_its_own_code_hub1575() {
        let config = crate::aeat::test_config_with_producer_facts();
        // The diagnostic's own sample with the ONE thing `build_soap` refuses before the schema
        // ever sees it (hub#324): a total nobody wrote.
        let sample = json!({
            "record_type": "alta",
            "issuer_nif": "B12345678",
            "issuer_name": "PELUQUERIA LA MODERNA SL",
            "invoice_number": "PRUEBA-2026-09-05",
            "invoice_date": "2026-09-05",
            "invoice_type": "F2",
            "description": "Factura de PRUEBA (diagnóstico VeriFactu)",
            "tax_rate": 21,
            "tax_breakdown": r#"{"21.00":{"base":10000,"tax":2100}}"#,
            "base_amount": 10000,
            "tax_amount": 2100,
            "recipient_nif": "",
            "recipient_name": "",
            "record_hash": "F".repeat(64),
            "is_first_record": 1,
            "generation_timestamp": "2026-09-05T10:00:00+02:00",
        });
        let route = TransmitRoute::Direct {
            identity: throwaway_identity(),
            holder: None,
        };

        let reason = sample_envelope(&sample, &config, &route, "hub-1", "B12345678")
            .expect_err("a record with no total cannot be wrapped");

        assert_eq!(reason.code, "sample_envelope_invalid", "{reason:?}");
        assert!(
            reason.facts["error"]
                .as_str()
                .is_some_and(|e| e.contains("total_amount")),
            "the reason has to keep naming what to fix: {reason:?}"
        );
    }
}
