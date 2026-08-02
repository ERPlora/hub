//! Ensayo **REAL** contra la AEAT de preproducción: el ciclo `2007` → re-ancla → reintento.
//!
//! Un test verde no vale: los de la suite mockean la AEAT y pasan con flujos que el servicio
//! real no acepta. Este fichero habla con `prewww1.aeat.es` de verdad y **imprime el XML crudo**
//! enviado y recibido, para poder decidir el diseño sobre evidencia y no sobre razonamiento.
//!
//! Responde a dos preguntas:
//!
//! 1. **¿En qué `EstadoRegistro` llega un 2007 en el ALTA?** Si llega como `AceptadoConErrores`,
//!    `classify()` lo mapea a `"accepted"` y la condición `classify(&resp).0 == "rejected"` que
//!    dispara `auto_rechain_and_retry` **nunca se cumple** → la recuperación es código muerto.
//! 2. **¿Qué hace la AEAT ante un registro re-anclado que YA estaba aceptado?** ¿Lo duplica, lo
//!    rechaza por duplicado, o lo sustituye? De ahí sale el diseño correcto de la recuperación.
//!
//! Va `#[ignore]`: necesita red y el certificado del negocio.
//!
//! ```sh
//! ERPLORA_CERT_P12=…/.secrets/ERPlora_Cloud__R__B27593136_.p12 \
//! ERPLORA_COMPANY_CERT_P12_PASSWORD=… \
//! ERPLORA_ISSUER_NIF=B27593136 ERPLORA_ISSUER_NAME="ERPLORA CLOUD SL" \
//!   cargo test -p erplora-verifactu --test aeat_live_2007 -- --ignored --nocapture
//! ```
use erplora_verifactu::{aeat, chain, xsd};
use serde_json::json;

type Json = serde_json::Value;

fn env(k: &str) -> String {
    std::env::var(k).unwrap_or_else(|_| panic!("falta la variable de entorno {k}"))
}

/// Identidad mTLS nueva por petición (`reqwest::Identity` se consume al postear).
fn identity() -> reqwest::Identity {
    let der = std::fs::read(env("ERPLORA_CERT_P12")).expect("no se pudo leer el .p12");
    erplora_runtime::certificate::identity_from_der(&der, &env("ERPLORA_COMPANY_CERT_P12_PASSWORD"))
        .expect("el .p12 no abre (¿la contraseña del certificado PERSONAL por error?)")
}

fn config() -> Json {
    json!({
        "software_name": env("ERPLORA_ISSUER_NAME"),
        "software_nif": env("ERPLORA_ISSUER_NIF"),
        "environment": "testing",
    })
}

/// Una factura simplificada (F2, sin `Destinatarios`) de 1,21 € con huella correcta.
/// `previous_hash` vacío + `is_first_record = 1` → `<PrimerRegistro>S</PrimerRegistro>`.
fn build_record(invoice_number: &str, ts: &str, previous_hash: &str) -> Json {
    let nif = env("ERPLORA_ISSUER_NIF");
    let date = &ts[..10];
    let hash = chain::alta_hash(
        &nif,
        invoice_number,
        date,
        "F2",
        0.21,
        1.21,
        previous_hash,
        ts,
    );
    json!({
        "id": invoice_number.replace(['/', ' '], "-"),
        "record_type": "alta",
        "issuer_nif": nif,
        "issuer_name": env("ERPLORA_ISSUER_NAME"),
        "invoice_number": invoice_number,
        "invoice_date": date,
        "invoice_type": "F2",
        "description": format!("Ensayo 2007 {invoice_number}"),
        "base_amount": 100,
        "tax_rate": 21.0,
        "tax_breakdown": r#"{"21.00":{"base":100,"tax":21}}"#,
        "tax_amount": 21,
        "total_amount": 121,
        "record_hash": hash,
        "previous_hash": previous_hash,
        "is_first_record": if previous_hash.is_empty() { 1 } else { 0 },
        "generation_timestamp": ts,
    })
}

fn banner(title: &str) {
    println!("\n{}\n── {title}\n{}", "=".repeat(78), "=".repeat(78));
}

/// Postea un alta y devuelve `(cuerpo_crudo, respuesta_parseada)`, imprimiendo ambos enteros.
async fn send_alta(record: &Json, prev: Option<&Json>, label: &str) -> (String, aeat::AeatResponse) {
    let xml = aeat::build_soap(record, &config(), prev, "hub-ensayo-2007");
    banner(&format!("{label} — XML ENVIADO"));
    println!("{xml}");

    // El mismo gate que corre en producción antes de CADA transmisión.
    match xsd::validate_registro(&xml) {
        Ok(()) => println!("\n[XSD] válido"),
        Err(e) => panic!("[XSD] INVÁLIDO, no se envía a Hacienda: {e}"),
    }

    let body = aeat::post_soap(aeat::endpoint("testing"), identity(), &xml)
        .await
        .expect("la AEAT debe responder 200");
    banner(&format!("{label} — RESPUESTA CRUDA DE LA AEAT"));
    println!("{body}");

    let resp = aeat::parse_response(&body);
    println!(
        "\n[PARSEADO] EstadoEnvio={:?} EstadoRegistro={:?} CodigoError={:?} Descripcion={:?} CSV={:?}",
        resp.estado_envio, resp.estado_registro, resp.codigo_error, resp.descripcion_error, resp.csv
    );
    (body, resp)
}

/// Réplica EXACTA de `classify()` (privada en lib.rs) para poder afirmar sobre el veredicto real.
fn classify_status(resp: &aeat::AeatResponse) -> &'static str {
    match resp.estado_registro.as_str() {
        "Correcto" | "AceptadoConErrores" => "accepted",
        "Incorrecto" => "rejected",
        _ if resp.estado_envio == "Correcto" => "accepted",
        _ => "error",
    }
}

/// §0 + §1 en una sola pasada: hace falta que el 2007 y el re-anclaje ocurran sobre el MISMO
/// registro para que la segunda pregunta tenga sentido.
#[tokio::test]
#[ignore = "necesita red y el certificado real del negocio"]
async fn ciclo_2007_rechain_reintento_contra_preproduccion() {
    let now = chrono::Local::now();
    let ts = now.to_rfc3339_opts(chrono::SecondsFormat::Secs, false);
    let serial = format!("ENS-{}", now.format("%Y%m%d-%H%M%S"));

    // ── PASO 1 — cadena local vacía → PrimerRegistro=S → se espera 2007 ────────────────────
    // El NIF B27593136 con IdSistemaInformatico "EC" YA tiene registros en preproducción, así
    // que anunciarse como primer registro es exactamente el escenario «he restaurado un backup».
    let record = build_record(&serial, &ts, "");
    let (_, resp) = send_alta(&record, None, "PASO 1 · ALTA con PrimerRegistro=S").await;

    banner("VEREDICTO §0 — ¿se dispara la recuperación automática?");
    let status = classify_status(&resp);
    let is_chaining = aeat::is_chaining_rejection(&resp.codigo_error, &resp.descripcion_error);
    println!("EstadoRegistro real ....... {:?}", resp.estado_registro);
    println!("CodigoErrorRegistro ....... {:?}", resp.codigo_error);
    println!("classify() lo mapea a ..... {status:?}");
    println!("is_chaining_rejection() ... {is_chaining}");
    println!(
        "\n=> la condición de disparo `classify == \"rejected\" && is_chaining` es {}",
        status == "rejected" && is_chaining
    );
    println!(
        "=> auto_rechain_and_retry {} en este escenario real",
        if status == "rejected" && is_chaining {
            "SÍ se ejecuta"
        } else {
            "NO se ejecuta — ES CÓDIGO MUERTO"
        }
    );

    // ── PASO 2 — ¿está el registro con 2007 REGISTRADO en la AEAT? ─────────────────────────
    // Si lo está, reenviarlo re-anclado lo duplicaría, y el diseño de la recuperación cambia.
    let nif = env("ERPLORA_ISSUER_NIF");
    let name = env("ERPLORA_ISSUER_NAME");
    let consult = aeat::build_consult_soap(&nif, &name, &now.format("%Y").to_string(), &now.format("%m").to_string())
        .expect("envelope de consulta");
    let body = aeat::post_soap(aeat::consult_endpoint("testing"), identity(), &consult)
        .await
        .expect("la consulta debe responder 200");
    banner("PASO 2 · CONSULTA tras el 2007 — RESPUESTA CRUDA");
    println!("{body}");
    let records = aeat::parse_consult_response(&body).expect("la AEAT rechazó la consulta");
    let hits: Vec<_> = records.iter().filter(|r| r.invoice_number == serial).collect();
    println!(
        "\n=> {serial} aparece {} vez/veces en la AEAT tras el 2007 => {}",
        hits.len(),
        if hits.is_empty() {
            "NO quedó registrado"
        } else {
            "SÍ quedó REGISTRADO (reenviarlo re-anclado lo DUPLICARÍA)"
        }
    );
    for h in &hits {
        println!("   estado={:<20} huella={} gen={}", h.estado, h.record_hash, h.generated_at);
    }

    // ── PASO 3 — re-anclar ese MISMO registro y reenviarlo (lo que hace auto_rechain_and_retry) ──
    let anchor = aeat::pick_latest_record(&records).expect("hace falta un ancla con huella");
    println!(
        "\nANCLA ELEGIDA -> {} {} {} huella={}",
        anchor.generated_at, anchor.invoice_number, anchor.estado, anchor.record_hash
    );
    let (rechained, _) = erplora_verifactu::rechain_record(&record, anchor, 2);
    // La consulta devuelve la fecha en formato AEAT (DD-MM-YYYY); `build_soap` espera ISO.
    let anchor_date_parts: Vec<&str> = anchor.invoice_date.split('-').collect();
    let anchor_date_iso = if anchor_date_parts.len() == 3 {
        format!(
            "{}-{}-{}",
            anchor_date_parts[2], anchor_date_parts[1], anchor_date_parts[0]
        )
    } else {
        anchor.invoice_date.clone()
    };
    let prev = json!({
        "issuer_nif": anchor.issuer_nif,
        "invoice_number": anchor.invoice_number,
        "invoice_date": anchor_date_iso,
        "record_hash": chain::normalize_hash(&anchor.record_hash),
    });
    let (_, resp2) = send_alta(&rechained, Some(&prev), "PASO 3 · MISMO registro RE-ANCLADO").await;

    banner("VEREDICTO §1 — ¿qué hace la AEAT con un re-anclado ya aceptado?");
    println!("EstadoRegistro ....... {:?}", resp2.estado_registro);
    println!("CodigoError .......... {:?}", resp2.codigo_error);
    println!("Descripcion .......... {:?}", resp2.descripcion_error);

    // ── PASO 4 — consultar de nuevo: ¿duplicado, sustituido o rechazado? ───────────────────
    let body = aeat::post_soap(aeat::consult_endpoint("testing"), identity(), &aeat::build_consult_soap(&nif, &name, &now.format("%Y").to_string(), &now.format("%m").to_string()).unwrap())
        .await
        .expect("la consulta debe responder 200");
    banner("PASO 4 · CONSULTA FINAL — RESPUESTA CRUDA");
    println!("{body}");
    let after = aeat::parse_consult_response(&body).expect("consulta final");
    let hits2: Vec<_> = after.iter().filter(|r| r.invoice_number == serial).collect();
    println!(
        "\n=> {serial} aparece ahora {} vez/veces (antes {})",
        hits2.len(),
        hits.len()
    );
    for h in &hits2 {
        println!("   estado={:<20} huella={} gen={}", h.estado, h.record_hash, h.generated_at);
    }
    println!(
        "\n=> CONCLUSIÓN: la AEAT {}",
        match (hits.len(), hits2.len()) {
            (a, b) if b > a => "DUPLICA el registro re-anclado",
            (a, b) if a == b && b > 0 => "NO duplica: sustituye/ignora el reenvío (misma IDFactura)",
            _ => "hizo algo inesperado — mirar el XML crudo de arriba",
        }
    );

    // ── PASO 5 — la prueba de que la cadena SIGUE viva tras el 2007 ────────────────────────
    // Es lo que de verdad importa: que la SIGUIENTE factura encadene desde el registro que la
    // AEAT tiene por último y la acepte **sin código de error**. Si esto falla, el 2007 dejó la
    // cadena rota y el TPV no puede volver a facturar.
    let siguiente_ts = chrono::Local::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, false);
    let siguiente_serial = format!("{serial}-B");
    let anchor_hash = chain::normalize_hash(&hits2[0].record_hash);
    let siguiente = build_record(&siguiente_serial, &siguiente_ts, &anchor_hash);
    let prev_real = json!({
        "issuer_nif": nif,
        "invoice_number": serial,
        "invoice_date": &ts[..10],
        "record_hash": anchor_hash,
    });
    let (_, resp3) = send_alta(
        &siguiente,
        Some(&prev_real),
        "PASO 5 · SIGUIENTE factura encadenada desde el registro con 2007",
    )
    .await;

    banner("VEREDICTO §3.1 — ¿sigue viva la cadena tras el 2007?");
    println!("EstadoRegistro ....... {:?}", resp3.estado_registro);
    println!("CodigoError .......... {:?}", resp3.codigo_error);
    println!("CSV .................. {:?}", resp3.csv);

    // ── Aserciones: esto deja de ser una sonda y pasa a ser un ensayo con veredicto ────────
    assert_eq!(
        resp.estado_registro, "AceptadoConErrores",
        "§0: un 2007 llega como ACEPTADO con errores, no como Incorrecto"
    );
    assert_eq!(resp.codigo_error, "2007");
    assert_eq!(
        classify_status(&resp),
        "accepted",
        "§0: por eso la condición `== rejected` nunca se cumplía"
    );
    assert_eq!(
        resp2.codigo_error, "3000",
        "§1: reenviar re-anclado un registro ya aceptado es un DUPLICADO"
    );
    assert_eq!(
        hits2.len(),
        hits.len(),
        "§1: la AEAT no duplicó el registro — lo rechazó"
    );
    assert_eq!(
        resp3.estado_registro, "Correcto",
        "§3.1: la siguiente factura debe encadenar y ser aceptada"
    );
    assert!(
        resp3.codigo_error.is_empty(),
        "§3.1: y sin código de error: {} {}",
        resp3.codigo_error,
        resp3.descripcion_error
    );
    println!("\n✅ ciclo completo verificado contra la AEAT de preproducción");
}
