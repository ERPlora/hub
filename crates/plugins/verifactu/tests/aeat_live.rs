//! Comprobación **contra la AEAT de preproducción** con el certificado real — hub#287.
//!
//! Un test verde no basta: mockean el servicio y pasan con XML que la AEAT rechaza. Este fichero
//! ejercita EXACTAMENTE el mismo código que el motor (`aeat::consult_endpoint`,
//! `aeat::build_consult_soap`, `aeat::parse_consult_response`, `aeat::pick_latest_record`,
//! `xsd::validate_registro`) contra el servicio de verdad, e imprime la respuesta cruda.
//!
//! Va `#[ignore]`: necesita red y el certificado del negocio, así que no corre en la suite normal.
//! No toca la cadena ni la base de datos — solo **consulta** y valida XML en memoria.
//!
//! ```sh
//! ERPLORA_CERT_P12=…/ERPlora_Cloud__R__B27593136_.p12 \
//! ERPLORA_COMPANY_CERT_P12_PASSWORD=… \
//! ERPLORA_ISSUER_NIF=B27593136 ERPLORA_ISSUER_NAME="ERPLORA CLOUD SL" \
//!   cargo test -p erplora-verifactu --test aeat_live -- --ignored --nocapture
//! ```
use erplora_verifactu::{aeat, xsd};

fn env(k: &str) -> String {
    std::env::var(k).unwrap_or_else(|_| panic!("falta la variable de entorno {k}"))
}

#[tokio::test]
#[ignore = "necesita red y el certificado real del negocio"]
async fn consulta_real_contra_preproduccion() {
    let der = std::fs::read(env("ERPLORA_CERT_P12")).expect("no se pudo leer el .p12");
    let identity = erplora_runtime::certificate::identity_from_der(
        &der,
        &env("ERPLORA_COMPANY_CERT_P12_PASSWORD"),
    )
    .expect("el .p12 no abre (¿contraseña equivocada? no confundir con el certificado personal)");

    let nif = env("ERPLORA_ISSUER_NIF");
    let name = env("ERPLORA_ISSUER_NAME");
    let ejercicio = std::env::var("ERPLORA_EJERCICIO").unwrap_or_else(|_| "2026".into());
    let periodo = std::env::var("ERPLORA_PERIODO").unwrap_or_else(|_| "08".into());

    // El `.p12` de este ensayo es el de REPRESENTANTE de ERPlora (`…_R_…`), es decir la forma del
    // slot `own`: puerta `prewww1` (hub#320). Con un Sello de Entidad habría que pasar
    // `"delegated"` aquí y el ensayo iría contra `prewww10`.
    let certificate_kind = "own";
    let endpoint = aeat::consult_endpoint("testing", certificate_kind);
    println!("ENDPOINT DE CONSULTA : {endpoint}");
    println!(
        "ENDPOINT DE ALTA     : {}",
        aeat::endpoint("testing", certificate_kind)
    );
    assert_eq!(
        endpoint,
        aeat::endpoint("testing", certificate_kind),
        "el WSDL publica la consulta en el endpoint del alta; si difieren, vuelve el 404"
    );

    let xml = aeat::build_consult_soap(&nif, &name, &ejercicio, &periodo, None).expect("envelope");
    println!("\n── ENVELOPE ENVIADO ──────────────────────────────────────\n{xml}");

    let body = aeat::post_soap(endpoint, identity, &xml)
        .await
        .expect("la consulta debe responder 200 (un 404 sería la URL inventada de vuelta)");
    println!("\n── RESPUESTA CRUDA DE LA AEAT ────────────────────────────\n{body}");

    let records = aeat::parse_consult_response(&body)
        .expect("la AEAT rechazó la consulta (un Fault NO es «0 registros»)");
    println!("\nREGISTROS DEVUELTOS: {}", records.len());
    for r in &records {
        println!(
            "   {:<22} {:<12} {:<20} {:<26} {}",
            r.invoice_number,
            r.invoice_date,
            r.estado,
            r.generated_at,
            r.record_hash.chars().take(16).collect::<String>()
        );
    }

    match aeat::pick_latest_record(&records) {
        Some(latest) => {
            println!(
                "\nANCLA ELEGIDA   -> {}  {}  {}",
                latest.generated_at, latest.invoice_number, latest.estado
            );
            println!(
                "PRIMERO DE LA LISTA -> {}  {}  {}",
                records[0].generated_at, records[0].invoice_number, records[0].estado
            );
            assert!(
                !latest.record_hash.is_empty(),
                "el ancla tiene que traer huella: es el eslabón"
            );
        }
        None => println!("\nsin ancla utilizable (ningún registro con huella)"),
    }
}

/// El gate que corre en producción antes de CADA transmisión, sobre el XML de alta real.
#[test]
#[ignore = "se ejecuta junto a la consulta real, para dejar la salida completa en la PR"]
fn validacion_xsd_sobre_el_xml_real() {
    let nif = env("ERPLORA_ISSUER_NIF");
    let name = env("ERPLORA_ISSUER_NAME");
    let cfg = serde_json::json!({
        "software_name": name, "software_nif": nif,
        // Hechos del productor tal y como los sirve el plano de control (hub#323): sin ellos
        // no hay `SistemaInformatico`, y por tanto no hay sobre que validar.
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
    let f2 = serde_json::json!({
        "record_type": "alta", "issuer_nif": nif, "issuer_name": name,
        "invoice_number": "PRUEBA-XSD", "invoice_date": "2026-08-02", "invoice_type": "F2",
        "description": "Validación local", "base_amount": 10000, "tax_rate": 21.0,
        "tax_breakdown": r#"{"21.00":{"base":10000,"tax":2100}}"#,
        "tax_amount": 2100, "total_amount": 12100, "record_hash": "A".repeat(64),
        "is_first_record": 1, "generation_timestamp": "2026-08-02T10:00:00+02:00",
    });
    let mut f1_sin_destinatario = f2.clone();
    f1_sin_destinatario["invoice_type"] = serde_json::json!("F1");

    let xml_f2 = aeat::build_soap(&f2, &cfg, None, "hub-preproduccion").expect("declarable");
    println!(
        "F2 sin destinatario → {:?}",
        xsd::validate_registro(&xml_f2)
    );
    xsd::validate_registro(&xml_f2).expect("una simplificada no lleva destinatario: es válida");

    let xml_f1 = aeat::build_soap(&f1_sin_destinatario, &cfg, None, "hub-preproduccion")
        .expect("declarable");
    let err = xsd::validate_registro(&xml_f1).expect_err("una F1 sin Destinatarios es un 1189");
    println!("F1 SIN destinatario → BLOQUEADO: {err}");
}
