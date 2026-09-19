//! **REAL** rehearsal against the AEAT preproduction: what a LATE remission costs with and without
//! `Incidencia=S`, and what the AEAT does not decide for us (ERPlora/verifactu#111).
//!
//! On 2026-09-13 (`banco-pre`) six records born without a transmission road were forced out by
//! hand, as ordinary remissions, days after their generation — and after a newer sale had already
//! gone out. The AEAT took all six «with errors»: the first one with **2007** («it must not be
//! filed as the first record, there are invoices already issued») and the other five with **2004**
//! («FechaHoraHusoGenRegistro must be the AEAT's current date, with a 240-second margin»).
//!
//! This file reproduces both against the real service and pins the two facts the fix stands on:
//!
//! 1. a record generated long ago and filed WITHOUT the incidence gets **2004**, and the very same
//!    kind of record filed WITH `Incidencia=S` goes through clean — so every deferred remission
//!    must declare it;
//! 2. the **2007** of the first record is the same story: a first record filed late, as a punctual
//!    remission, after the taxpayer already has records at the AEAT, is taken with 2007 — and the
//!    very same first record declaring the incidence goes through clean.
//!
//! What the AEAT does NOT decide is the order: measured on 2026-09-19, a first record declaring
//! the incidence is taken clean even after newer records. Sending the records that waited in
//! sequence order, before any newer one, is the regulation's «consecutiva» remission and what
//! ERPlora/verifactu#111 asks for — this file does not pretend the AEAT enforces it.
//!
//! `#[ignore]`: it needs the network and the business certificate.
//!
//! ```sh
//! ERPLORA_CERT_P12=…/.secrets/ERPlora_Cloud__R__B27593136_.p12 \
//! ERPLORA_COMPANY_CERT_P12_PASSWORD=… \
//! ERPLORA_ISSUER_NIF=B27593136 ERPLORA_ISSUER_NAME="ERPLORA CLOUD SL" \
//!   cargo test -p erplora-verifactu --test aeat_live_late_remission -- --ignored --nocapture
//! ```
use erplora_verifactu::{aeat, chain, xsd};
use serde_json::json;

type Json = serde_json::Value;

fn env(k: &str) -> String {
    std::env::var(k).unwrap_or_else(|_| panic!("missing environment variable {k}"))
}

/// The representative `.p12` of ERPlora (`…_R_…`) is the shape of the `own` slot: door `prewww1`.
const CERTIFICATE_KIND: &str = "own";

fn identity() -> reqwest::Identity {
    let der = std::fs::read(env("ERPLORA_CERT_P12")).expect("could not read the .p12");
    erplora_runtime::certificate::identity_from_der(&der, &env("ERPLORA_COMPANY_CERT_P12_PASSWORD"))
        .expect("the .p12 does not open")
}

fn config() -> Json {
    json!({
        "software_name": env("ERPLORA_ISSUER_NAME"),
        "software_nif": env("ERPLORA_ISSUER_NIF"),
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
    })
}

/// A simplified invoice (F2) of 1.21 € with a correct fingerprint, generated at `ts`.
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
        "id": invoice_number,
        "record_type": "alta",
        "issuer_nif": nif,
        "issuer_name": env("ERPLORA_ISSUER_NAME"),
        "invoice_number": invoice_number,
        "invoice_date": date,
        "invoice_type": "F2",
        "description": format!("Late remission rehearsal {invoice_number}"),
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

/// The link `build_soap` writes as `RegistroAnterior`.
fn link_to(record: &Json) -> Json {
    json!({
        "issuer_nif": record["issuer_nif"],
        "invoice_number": record["invoice_number"],
        "invoice_date": record["invoice_date"],
        "record_hash": record["record_hash"],
    })
}

fn banner(title: &str) {
    println!("\n{}\n── {title}\n{}", "=".repeat(78), "=".repeat(78));
}

/// Files one alta — as a punctual remission, or declaring the incidence — and prints both ends.
async fn send_alta(
    record: &Json,
    prev: Option<&Json>,
    incidence: bool,
    label: &str,
) -> aeat::AeatResponse {
    let xml = aeat::build_soap(record, &config(), prev, "hub-rehearsal-v111").expect("declarable");
    let xml = if incidence {
        aeat::stamp_contingency_incidence(&xml)
    } else {
        xml
    };
    assert_eq!(
        xml.contains("<sum1:Incidencia>S</sum1:Incidencia>"),
        incidence,
        "the envelope must say exactly what this step is testing"
    );
    xsd::validate_registro(&xml).expect("the envelope must pass the schema before it is filed");
    banner(&format!("{label} — XML SENT"));
    println!("{xml}");

    let body = aeat::post_soap(
        aeat::endpoint("testing", CERTIFICATE_KIND),
        identity(),
        &xml,
    )
    .await
    .expect("the AEAT must answer 200");
    banner(&format!("{label} — RAW AEAT ANSWER"));
    println!("{body}");
    let resp = aeat::parse_response(&body);
    println!(
        "\n[PARSED] EstadoEnvio={:?} EstadoRegistro={:?} CodigoError={:?} Descripcion={:?} CSV={:?}",
        resp.estado_envio, resp.estado_registro, resp.codigo_error, resp.descripcion_error, resp.csv
    );
    resp
}

#[tokio::test]
#[ignore = "needs the network and the real business certificate"]
async fn a_late_remission_is_clean_only_when_it_declares_the_incidence() {
    let now = chrono::Local::now();
    let serial = format!("LATE-{}", now.format("%Y%m%d-%H%M%S"));
    // Four days late, like record nº 19 of `banco-pre` (born 2026-09-15 without a road).
    let late = (now - chrono::Duration::days(4)).to_rfc3339_opts(chrono::SecondsFormat::Secs, false);

    // The chain these records hang from: the last record the AEAT already holds for this taxpayer
    // this month — the case of a hub whose newer sale went out first.
    let consult = aeat::build_consult_soap(
        &env("ERPLORA_ISSUER_NIF"),
        &env("ERPLORA_ISSUER_NAME"),
        &now.format("%Y").to_string(),
        &now.format("%m").to_string(),
        None,
    )
    .expect("consult envelope");
    let body = aeat::post_soap(
        aeat::consult_endpoint("testing", CERTIFICATE_KIND),
        identity(),
        &consult,
    )
    .await
    .expect("the consult must answer 200");
    let held = aeat::parse_consult_response(&body).expect("the AEAT refused the consult");
    let anchor = aeat::pick_latest_record(&held).expect("the taxpayer already has records");
    let anchor_hash = chain::normalize_hash(&anchor.record_hash);
    let anchor_date: Vec<&str> = anchor.invoice_date.split('-').collect();
    let anchor_link = json!({
        "issuer_nif": anchor.issuer_nif,
        "invoice_number": anchor.invoice_number,
        // The consult answers DD-MM-YYYY; `build_soap` expects ISO.
        "invoice_date": format!("{}-{}-{}", anchor_date[2], anchor_date[1], anchor_date[0]),
        "record_hash": anchor_hash,
    });

    // ── 2004: a record generated four days ago, filed as a PUNCTUAL remission ──────────────────
    let plain = build_record(&format!("{serial}-A"), &late, &anchor_hash);
    let plain_resp = send_alta(&plain, Some(&anchor_link), false, "late, WITHOUT incidence").await;

    // ── the fix: the next record of the same age, filed declaring the incidence ────────────────
    let declared = build_record(&format!("{serial}-B"), &late, &plain["record_hash"].as_str().unwrap());
    let declared_resp =
        send_alta(&declared, Some(&link_to(&plain)), true, "late, WITH Incidencia=S").await;

    // ── 2007: record nº 1 of 2026-09-13 — a FIRST record, late, filed as a punctual remission
    // after the taxpayer already has records at the AEAT ────────────────────────────────────────
    let first_plain = build_record(&format!("{serial}-C"), &late, "");
    let first_plain_resp =
        send_alta(&first_plain, None, false, "first record, late, WITHOUT incidence").await;

    // ── the fix: the same first record, declaring the incidence ──────────────────────────────
    let first_declared = build_record(&format!("{serial}-D"), &late, "");
    let first_declared_resp =
        send_alta(&first_declared, None, true, "first record, late, WITH Incidencia=S").await;

    banner("VERDICT");
    for (label, resp) in [
        ("late without incidence ........", &plain_resp),
        ("late with incidence ...........", &declared_resp),
        ("first, late, without incidence ", &first_plain_resp),
        ("first, late, with incidence ...", &first_declared_resp),
    ] {
        println!("{label} {} {} {}", resp.estado_registro, resp.codigo_error, resp.descripcion_error);
    }

    assert_eq!(
        (plain_resp.estado_registro.as_str(), plain_resp.codigo_error.as_str()),
        ("AceptadoConErrores", "2004"),
        "a late record filed as a punctual remission is the 2004 of 2026-09-13"
    );
    assert_eq!(
        (first_plain_resp.estado_registro.as_str(), first_plain_resp.codigo_error.as_str()),
        ("AceptadoConErrores", "2007"),
        "a late first record filed as a punctual remission is the 2007 of 2026-09-13"
    );
    for (what, resp) in [("late", &declared_resp), ("first, late", &first_declared_resp)] {
        assert_eq!(
            (resp.estado_registro.as_str(), resp.codigo_error.as_str()),
            ("Correcto", ""),
            "{what}: declaring the incidence is what makes the late remission clean — {}",
            resp.descripcion_error
        );
    }
}
