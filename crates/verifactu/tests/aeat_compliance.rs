//! Tests de cumplimiento VeriFactu (RD 1007/2023 + detalle técnico de la huella,
//! Orden HAC/1177/2024) para el motor `erplora-verifactu`.
//!
//! ## Qué validan estos tests
//! - **Huella encadenada** (`chain::alta_hash` / `anulacion_hash`): que la concatenación
//!   `campo=valor` unida por `&`, en el ORDEN exacto de la AEAT, con los formatos AEAT
//!   (importe 2 decimales/punto, fecha DD-MM-AAAA, timestamp ISO con huso), y el SHA-256
//!   en HEX MAYÚSCULAS, produce la huella esperada. Incluye el ENCADENAMIENTO (la huella N
//!   usa la huella N-1 en el campo `Huella`).
//! - **Conversión céntimos→euros** (ADR-0007): el `create_record` del runtime convierte
//!   céntimos→euros SOLO en el límite de formateo fiscal; aquí se prueba que `format_amount`
//!   produce p.ej. `231.00` para 231,00 € (que vienen de 23100 céntimos).
//! - **XML `RegistroAlta`/`RegistroAnulacion`** (`aeat::build_soap`): golden del sobre SOAP,
//!   validando estructura, namespaces, el bloque `Encadenamiento`, y que los importes salen
//!   en EUROS con formato AEAT (la división céntimos→euros la hace `build_soap`).
//! - **QR** (`chain::qr_url`): que la URL de cotejo AEAT lleva `nif`, `numserie`, `fecha`
//!   (DD-MM-AAAA) e `importe` (euros, 2 decimales), correctamente url-encoded.
//!
//! ## Fórmula AEAT de la huella de ALTA (fuente: módulo `verifactu` WASM-TODO.md §1.3,
//! transcripción del «detalle técnico de la huella» de la AEAT):
//! ```text
//! IDEmisorFactura={nif}&NumSerieFactura={num}&FechaExpedicionFactura={DD-MM-AAAA}
//! &TipoFactura={tipo}&CuotaTotal={cuota 2dec}&ImporteTotal={total 2dec}
//! &Huella={huella_anterior}&FechaHoraHusoGenRegistro={ISO+huso}
//! record_hash = SHA256(input.utf8).hexdigest().UPPER()
//! ```
//! La ANULACIÓN usa la misma fórmula SIN `TipoFactura`, `CuotaTotal` ni `ImporteTotal`.
//!
//! ## Nivel de confianza
//! Los valores esperados se DERIVAN del algoritmo documentado (calculados de forma
//! independiente, no copiados de la salida del motor), por lo que estos tests detectan
//! cualquier desviación del motor respecto a la fórmula AEAT. La validación DEFINITIVA
//! requeriría un **vector oficial de la AEAT** (entrada conocida → huella publicada por la
//! Agencia); con él, basta cambiar las constantes esperadas de los tests por las oficiales.

use erplora_verifactu::aeat;
use erplora_verifactu::chain;
use serde_json::json;
use sha2::{Digest, Sha256};

// ── Vector de prueba conocido (campos fijos, no inventados: derivados aparte) ─────────────
const NIF: &str = "B12345678";
const NUM1: &str = "FA2026/001";
const NUM2: &str = "FA2026/002";
const FECHA_ISO: &str = "2026-06-10";
const FECHA_AEAT: &str = "10-06-2026";
const TIPO: &str = "F1";
const TS1: &str = "2026-06-10T12:34:56+00:00";
const TS2: &str = "2026-06-10T13:00:00+00:00";

/// Réplica independiente del SHA-256 hex-mayúsculas (oráculo del test, NO usa el motor).
fn sha256_upper(input: &str) -> String {
    let mut h = Sha256::new();
    h.update(input.as_bytes());
    format!("{:X}", h.finalize())
}

// ── 1. Formatos AEAT (los ladrillos de la huella y del XML) ───────────────────────────────

#[test]
fn format_date_iso_a_ddmmaaaa() {
    // FechaExpedicionFactura: YYYY-MM-DD → DD-MM-AAAA (orden exacto AEAT).
    assert_eq!(chain::format_date("2026-06-10"), "10-06-2026");
    assert_eq!(chain::format_date("2026-01-01"), "01-01-2026");
}

#[test]
fn format_amount_dos_decimales_punto() {
    // Importes AEAT: 2 decimales, punto como separador.
    assert_eq!(chain::format_amount(231.0), "231.00");
    assert_eq!(chain::format_amount(0.0), "0.00");
    assert_eq!(chain::format_amount(1331.0), "1331.00");
    assert_eq!(chain::format_amount(1234.5), "1234.50");
}

#[test]
fn conversion_centimos_a_euros_formato_aeat() {
    // ADR-0007: importes en CÉNTIMOS (INTEGER); la AEAT exige euros 2dec. La conversión
    // céntimos→euros ocurre en el límite de formateo. Este es EL caso que cambió la migración.
    // 23100 céntimos == 231,00 € → "231.00"
    assert_eq!(chain::format_amount(23100.0 / 100.0), "231.00");
    // 133100 céntimos == 1331,00 €
    assert_eq!(chain::format_amount(133100.0 / 100.0), "1331.00");
    // 1 céntimo == 0,01 €
    assert_eq!(chain::format_amount(1.0 / 100.0), "0.01");
    // 4205 céntimos == 42,05 €  (verifica que NO se trunca a 42.00)
    assert_eq!(chain::format_amount(4205.0 / 100.0), "42.05");
}

#[test]
fn format_timestamp_iso_con_huso_segundos_enteros() {
    // FechaHoraHusoGenRegistro: ISO-8601 con huso, segundos enteros (sin fracción).
    assert_eq!(
        chain::format_timestamp("2026-06-10T12:34:56.789+00:00"),
        "2026-06-10T12:34:56+00:00"
    );
    // Ya normalizado → idéntico.
    assert_eq!(chain::format_timestamp(TS1), TS1);
}

// ── 2. Huella de ALTA: derivada del algoritmo AEAT, no del motor ──────────────────────────

#[test]
fn alta_hash_coincide_con_formula_aeat() {
    // Oráculo independiente: construimos el input EXACTO de la AEAT y lo hasheamos aquí.
    let cuota_eur = 231.00; // 23100 céntimos
    let total_eur = 1331.00; // 133100 céntimos
    let esperado_input = format!(
        "IDEmisorFactura={NIF}&NumSerieFactura={NUM1}&FechaExpedicionFactura={FECHA_AEAT}\
         &TipoFactura={TIPO}&CuotaTotal=231.00&ImporteTotal=1331.00&Huella=\
         &FechaHoraHusoGenRegistro={TS1}"
    );
    let esperado = sha256_upper(&esperado_input);
    // Valor fijado (anclaje contra regresiones silenciosas del oráculo): SHA-256 mayúsculas.
    assert_eq!(esperado, "A84E25C35B6BA9FDABE7CF8DD744AA23A4BA8E3E2FE6535C71A9572B418D9122");

    let obtenido = chain::alta_hash(
        NIF, NUM1, FECHA_ISO, TIPO, cuota_eur, total_eur, "", TS1,
    );
    assert_eq!(obtenido, esperado, "la huella de alta debe seguir la fórmula AEAT exacta");
}

#[test]
fn alta_hash_es_hex_mayusculas_64() {
    let h = chain::alta_hash(NIF, NUM1, FECHA_ISO, TIPO, 231.0, 1331.0, "", TS1);
    assert_eq!(h.len(), 64, "SHA-256 hex = 64 caracteres");
    assert!(
        h.chars().all(|c| c.is_ascii_digit() || ('A'..='F').contains(&c)),
        "la huella debe ir en HEX MAYÚSCULAS (sin minúsculas): {h}"
    );
}

#[test]
fn alta_hash_sensible_al_importe_en_euros_no_centimos() {
    // Si el motor olvidara dividir céntimos→euros, el input AEAT cambiaría y la huella sería
    // distinta. Aquí confirmamos que la huella se calcula con EUROS (231.00), no con céntimos.
    let con_euros = chain::alta_hash(NIF, NUM1, FECHA_ISO, TIPO, 231.0, 1331.0, "", TS1);
    let con_centimos = chain::alta_hash(NIF, NUM1, FECHA_ISO, TIPO, 23100.0, 133100.0, "", TS1);
    assert_ne!(
        con_euros, con_centimos,
        "la huella con euros y con céntimos NO puede coincidir (detecta regresión de la conversión)"
    );
    // La correcta es la de euros (la que asserta el test de fórmula).
    assert_eq!(
        con_euros,
        "A84E25C35B6BA9FDABE7CF8DD744AA23A4BA8E3E2FE6535C71A9572B418D9122"
    );
}

// ── 3. Encadenamiento: la huella N usa la huella N-1 ──────────────────────────────────────

#[test]
fn encadenamiento_la_huella_n_usa_la_huella_n_menos_1() {
    // Registro 1 (primero de la cadena → previous_hash vacío).
    let h1 = chain::alta_hash(NIF, NUM1, FECHA_ISO, TIPO, 231.0, 1331.0, "", TS1);
    assert_eq!(h1, "A84E25C35B6BA9FDABE7CF8DD744AA23A4BA8E3E2FE6535C71A9572B418D9122");

    // Registro 2: su campo Huella = huella del registro 1.
    let h2 = chain::alta_hash(NIF, NUM2, FECHA_ISO, TIPO, 42.0, 242.0, &h1, TS2);

    // Oráculo independiente del registro 2 (con la huella anterior incrustada).
    let input2 = format!(
        "IDEmisorFactura={NIF}&NumSerieFactura={NUM2}&FechaExpedicionFactura={FECHA_AEAT}\
         &TipoFactura={TIPO}&CuotaTotal=42.00&ImporteTotal=242.00&Huella={h1}\
         &FechaHoraHusoGenRegistro={TS2}"
    );
    assert_eq!(h2, sha256_upper(&input2));
    assert_eq!(h2, "718F7F017C633C8471F8DB1B4413EF8B1A3B38231E97320AEFC9B9E26CE13033");

    // Cambiar la huella anterior cambia la huella siguiente (propiedad de encadenamiento).
    let h2_otra_cadena = chain::alta_hash(NIF, NUM2, FECHA_ISO, TIPO, 42.0, 242.0, "HASH_FALSO", TS2);
    assert_ne!(h2, h2_otra_cadena);
}

// ── 4. Huella de ANULACIÓN: sin TipoFactura/CuotaTotal/ImporteTotal ───────────────────────

#[test]
fn anulacion_hash_coincide_con_formula_aeat() {
    let input = format!(
        "IDEmisorFactura={NIF}&NumSerieFactura={NUM1}&FechaExpedicionFactura={FECHA_AEAT}\
         &Huella=&FechaHoraHusoGenRegistro={TS1}"
    );
    let esperado = sha256_upper(&input);
    assert_eq!(esperado, "E7D22B2996824720999CBF8B333AEC8AC4BAE2672932ABEE22DB4328B7B27B66");

    let obtenido = chain::anulacion_hash(NIF, NUM1, FECHA_ISO, "", TS1);
    assert_eq!(obtenido, esperado, "la huella de anulación omite tipo/cuota/importe");
    // Y es distinta de la de alta (lleva menos campos).
    let alta = chain::alta_hash(NIF, NUM1, FECHA_ISO, TIPO, 231.0, 1331.0, "", TS1);
    assert_ne!(obtenido, alta);
}

// ── 5. QR: URL de cotejo AEAT con parámetros bien formateados ─────────────────────────────

#[test]
fn qr_url_lleva_parametros_aeat_correctos() {
    // En producción el host es www2.agenciatributaria.gob.es.
    let url = chain::qr_url(NIF, NUM1, FECHA_ISO, 1331.0, "production");
    assert!(url.starts_with(
        "https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR?"
    ));
    // nif sin caracteres especiales → tal cual.
    assert!(url.contains("nif=B12345678"), "{url}");
    // numserie: la '/' se url-encodea a %2F.
    assert!(url.contains("numserie=FA2026%2F001"), "{url}");
    // fecha en formato AEAT DD-MM-AAAA (los '-' son unreserved → no se encodean).
    assert!(url.contains("fecha=10-06-2026"), "{url}");
    // importe en euros, 2 decimales ('.' es unreserved → no se encodea).
    assert!(url.contains("importe=1331.00"), "{url}");
}

#[test]
fn qr_url_host_segun_entorno() {
    // testing → prewww2.aeat.es (un QR de pruebas con el host de producción no validaría).
    let test = chain::qr_url(NIF, NUM1, FECHA_ISO, 1331.0, "testing");
    assert!(test.starts_with("https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?"), "{test}");
    let prod = chain::qr_url(NIF, NUM1, FECHA_ISO, 1331.0, "production");
    assert!(prod.starts_with("https://www2.agenciatributaria.gob.es/"), "{prod}");
}

#[test]
fn qr_importe_en_euros_no_centimos() {
    // El `create_record` pasa total en EUROS al qr_url; confirmamos el formato resultante.
    let url = chain::qr_url(NIF, NUM1, FECHA_ISO, 23100.0 / 100.0, "testing");
    assert!(url.contains("importe=231.00"), "{url}");
}

// ── 6. XML golden: RegistroAlta con importes en euros ─────────────────────────────────────

/// Construye un `record` JSON como el que persiste `create_record`: importes en CÉNTIMOS
/// (ADR-0007); `build_soap` los divide /100 al formatear para la AEAT.
fn record_alta_centimos(record_hash: &str) -> serde_json::Value {
    json!({
        "record_type": "alta",
        "issuer_nif": NIF,
        "issuer_name": "Acme S.L.",
        "invoice_number": NUM1,
        "invoice_date": FECHA_ISO,
        "invoice_type": TIPO,
        "description": "Venta TPV",
        "base_amount": 110000,   // 1100,00 €
        "tax_rate": 21.0,
        "tax_amount": 23100,     // 231,00 €
        "total_amount": 133100,  // 1331,00 €
        "is_first_record": 1,
        "generation_timestamp": TS1,
        "record_hash": record_hash,
    })
}

fn config_minima() -> serde_json::Value {
    json!({
        "software_name": "ERPlora",
        "software_nif": "B99999999",
        "software_id": "01",
        "software_version": "1.0",
    })
}

#[test]
fn xml_alta_importes_en_euros_y_estructura() {
    let hash = chain::alta_hash(NIF, NUM1, FECHA_ISO, TIPO, 231.0, 1331.0, "", TS1);
    let record = record_alta_centimos(&hash);
    let xml = aeat::build_soap(&record, &config_minima(), None, "hub-test")
        .expect("el registro se puede declarar");

    // Importes formateados en EUROS (la conversión céntimos→euros la hace build_soap /100).
    assert!(xml.contains("<sum1:CuotaTotal>231.00</sum1:CuotaTotal>"), "{xml}");
    assert!(xml.contains("<sum1:ImporteTotal>1331.00</sum1:ImporteTotal>"), "{xml}");
    assert!(
        xml.contains("<sum1:BaseImponibleOimporteNoSujeto>1100.00</sum1:BaseImponibleOimporteNoSujeto>"),
        "base imponible en euros: {xml}"
    );
    assert!(xml.contains("<sum1:CuotaRepercutida>231.00</sum1:CuotaRepercutida>"), "{xml}");
    assert!(xml.contains("<sum1:TipoImpositivo>21.00</sum1:TipoImpositivo>"), "{xml}");

    // Estructura: tipo de registro, identificación de factura, fecha AEAT, huella, encadenamiento.
    assert!(xml.contains("<sum1:RegistroAlta>"));
    assert!(xml.contains(&format!("<sum1:NumSerieFactura>{NUM1}</sum1:NumSerieFactura>")));
    assert!(xml.contains(&format!(
        "<sum1:FechaExpedicionFactura>{FECHA_AEAT}</sum1:FechaExpedicionFactura>"
    )));
    assert!(xml.contains(&format!("<sum1:TipoFactura>{TIPO}</sum1:TipoFactura>")));
    assert!(xml.contains(&format!("<sum1:Huella>{hash}</sum1:Huella>")));
    assert!(xml.contains("<sum1:TipoHuella>01</sum1:TipoHuella>"));
    // Primer registro de la cadena.
    assert!(xml.contains("<sum1:PrimerRegistro>S</sum1:PrimerRegistro>"));
    // Sobre SOAP + namespaces.
    assert!(xml.contains("<sum:RegFactuSistemaFacturacion>"));
    assert!(xml.contains("xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\""));
}

#[test]
fn xml_alta_encadenamiento_referencia_registro_anterior() {
    // Registro 2 con un previo → el XML debe llevar RegistroAnterior con la huella del previo.
    let h1 = chain::alta_hash(NIF, NUM1, FECHA_ISO, TIPO, 231.0, 1331.0, "", TS1);
    let mut record = record_alta_centimos(&h1);
    record["is_first_record"] = json!(0);
    record["invoice_number"] = json!(NUM2);
    record["generation_timestamp"] = json!(TS2);

    let prev = json!({
        "issuer_nif": NIF,
        "invoice_number": NUM1,
        "invoice_date": FECHA_ISO,
        "record_hash": h1,
    });
    let xml = aeat::build_soap(&record, &config_minima(), Some(&prev), "hub-test")
        .expect("el registro se puede declarar");

    assert!(xml.contains("<sum1:RegistroAnterior>"), "{xml}");
    assert!(
        xml.contains(&format!("<sum1:Huella>{h1}</sum1:Huella>")),
        "encadenamiento debe referenciar la huella del registro anterior: {xml}"
    );
    assert!(!xml.contains("<sum1:PrimerRegistro>S</sum1:PrimerRegistro>"));
}

#[test]
fn xml_anulacion_estructura() {
    let hash = chain::anulacion_hash(NIF, NUM1, FECHA_ISO, "", TS1);
    let mut record = record_alta_centimos(&hash);
    record["record_type"] = json!("anulacion");
    let xml = aeat::build_soap(&record, &config_minima(), None, "hub-test")
        .expect("el registro se puede declarar");

    assert!(xml.contains("<sum1:RegistroAnulacion>"));
    assert!(xml.contains(&format!(
        "<sum1:NumSerieFacturaAnulada>{NUM1}</sum1:NumSerieFacturaAnulada>"
    )));
    assert!(xml.contains(&format!("<sum1:Huella>{hash}</sum1:Huella>")));
    // La anulación NO lleva importes ni TipoFactura.
    assert!(!xml.contains("<sum1:ImporteTotal>"));
    assert!(!xml.contains("<sum1:TipoFactura>"));
}

// ── Destinatarios (error AEAT 1189): obligatorio en F1/F3/R1-R4, ausente en simplificadas ──

#[test]
fn xml_alta_con_destinatario_emite_bloque_destinatarios() {
    // Una F1 con cliente identificado debe llevar <Destinatarios> (si no, la AEAT da 1189).
    let hash = chain::alta_hash(NIF, NUM1, FECHA_ISO, TIPO, 231.0, 1331.0, "", TS1);
    let mut record = record_alta_centimos(&hash);
    record["recipient_nif"] = json!("B87654321");
    record["recipient_name"] = json!("Cliente S.L.");
    let xml = aeat::build_soap(&record, &config_minima(), None, "hub-test")
        .expect("el registro se puede declarar");

    assert!(xml.contains("<sum1:Destinatarios><sum1:IDDestinatario>"), "{xml}");
    assert!(xml.contains("<sum1:NombreRazon>Cliente S.L.</sum1:NombreRazon>"), "{xml}");
    assert!(xml.contains("<sum1:NIF>B87654321</sum1:NIF>"), "{xml}");
    // Posición XSD: Destinatarios va ANTES de Desglose.
    let pos_dest = xml.find("<sum1:Destinatarios>").expect("Destinatarios presente");
    let pos_desglose = xml.find("<sum1:Desglose>").expect("Desglose presente");
    assert!(pos_dest < pos_desglose, "Destinatarios debe ir antes de Desglose: {xml}");
}

// ── FacturasSustituidas (F3): tiquet→factura completa declara la F2 sustituida (ADR-0140) ──

#[test]
fn xml_alta_f3_emite_bloque_facturas_sustituidas() {
    // Una F3 (factura completa en SUSTITUCIÓN de una simplificada F2 ya declarada) debe declarar la
    // F2 sustituida con su nº+serie, fecha de expedición y NIF del emisor, en el bloque
    // FacturasSustituidas/IDFacturaSustituida. Los datos vienen snapshoteados en el registro (los
    // pobla `ingest_invoice` con el LEFT JOIN a la F2 por `substitutes_invoice_id`).
    let hash = chain::alta_hash(NIF, NUM1, FECHA_ISO, "F3", 231.0, 1331.0, "", TS1);
    let mut record = record_alta_centimos(&hash);
    record["invoice_type"] = json!("F3");
    record["substitutes_number"] = json!("T-2026-000145");
    record["substitutes_date"] = json!("2026-06-08"); // ISO → build_soap la formatea a AEAT
    record["substitutes_nif"] = json!(NIF);
    // Una F3 exige destinatario (como F1) — el cliente que pide la factura.
    record["recipient_nif"] = json!("B87654321");
    record["recipient_name"] = json!("Cliente S.L.");
    let xml = aeat::build_soap(&record, &config_minima(), None, "hub-test")
        .expect("el registro se puede declarar");

    assert!(xml.contains("<sum1:FacturasSustituidas><sum1:IDFacturaSustituida>"), "{xml}");
    assert!(
        xml.contains("<sum1:NumSerieFactura>T-2026-000145</sum1:NumSerieFactura>"),
        "declara el nº de la F2 sustituida: {xml}"
    );
    assert!(
        xml.contains("<sum1:FechaExpedicionFactura>08-06-2026</sum1:FechaExpedicionFactura>"),
        "fecha de la F2 en formato AEAT DD-MM-YYYY: {xml}"
    );
    // Posición XSD: FacturasSustituidas va tras TipoFactura y antes de DescripcionOperacion.
    let pos_tipo = xml.find("<sum1:TipoFactura>").expect("TipoFactura presente");
    let pos_sust = xml.find("<sum1:FacturasSustituidas>").expect("FacturasSustituidas presente");
    let pos_desc = xml.find("<sum1:DescripcionOperacion>").expect("DescripcionOperacion presente");
    assert!(
        pos_tipo < pos_sust && pos_sust < pos_desc,
        "orden XSD: TipoFactura < FacturasSustituidas < DescripcionOperacion: {xml}"
    );
}

#[test]
fn xml_alta_sin_sustitucion_no_emite_bloque() {
    // Guardarraíl: un alta normal (F1/F2, sin datos de sustitución) NO lleva FacturasSustituidas.
    let hash = chain::alta_hash(NIF, NUM1, FECHA_ISO, TIPO, 231.0, 1331.0, "", TS1);
    let record = record_alta_centimos(&hash);
    let xml = aeat::build_soap(&record, &config_minima(), None, "hub-test")
        .expect("el registro se puede declarar");
    assert!(!xml.contains("<sum1:FacturasSustituidas>"), "sin sustitución no debe emitir el bloque: {xml}");
}

#[test]
fn xml_alta_sin_destinatario_omite_bloque() {
    // Sin recipient_nif (p.ej. F2 simplificada / ticket de POS) NO se emite Destinatarios.
    let hash = chain::alta_hash(NIF, NUM1, FECHA_ISO, TIPO, 231.0, 1331.0, "", TS1);
    let record = record_alta_centimos(&hash); // sin recipient_*
    let xml = aeat::build_soap(&record, &config_minima(), None, "hub-test")
        .expect("el registro se puede declarar");

    assert!(!xml.contains("<sum1:Destinatarios>"), "no debe emitir Destinatarios vacío: {xml}");
}
