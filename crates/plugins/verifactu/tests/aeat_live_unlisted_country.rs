//! **REAL** rehearsal against the AEAT **preproduction**: a full invoice (`F1`) to a customer from
//! Kosovo or Western Sahara (ERPlora/sales#374, born from sales#360).
//!
//! Neither country is in the AEAT country list (`CountryType2`), so the till declares the customer
//! with `CodigoPais = QU` («otros países o territorios no relacionados», the list's own catch-all)
//! and `IDType = 04`. The XSD and the validations document allow it; this rehearsal sends one such
//! invoice to the AEAT so the claim rests on the service, not on the papers.
//!
//! 🔴 **Preproduction ONLY** (condition of 2026-09-20). Every post goes through
//! [`preproduction_door`], which refuses any host that is not `prewww1`/`prewww10`, and the
//! offline test [`the_rehearsal_only_ever_talks_to_preproduction`] fails the suite if the
//! rehearsal's environment or door would ever resolve to production.
//!
//! The AEAT answer is frozen in `tests/fixtures/unlisted_country_qu_2026-09-24.xml` (and what was
//! sent in `…_sent_…`), read back by the offline tests, so the evidence stays in the suite without
//! the network.
//!
//! ```sh
//! ERPLORA_CERT_P12=…/.secrets/ERPlora_Cloud__R__B27593136_.p12 \
//! ERPLORA_COMPANY_CERT_P12_PASSWORD=… \
//!   cargo test -p erplora-verifactu --test aeat_live_unlisted_country -- --ignored --nocapture
//! ```
use erplora_verifactu::{aeat, chain, xsd};
use serde_json::json;

type Json = serde_json::Value;

/// The only environment this rehearsal is allowed to declare.
const ENVIRONMENT: &str = "testing";

/// The representative `.p12` of ERPlora (`…_R_…`) is the shape of the `own` slot: door `prewww1`.
const CERTIFICATE_KIND: &str = "own";

/// The rehearsal issuer — the same test taxpayer as the other frozen fixtures (ADR-0189).
const ISSUER_NIF: &str = "B27593136";
const ISSUER_NAME: &str = "ERPLORA CLOUD SL";

/// Hosts this rehearsal may post to. Nothing else.
const PREPRODUCTION_HOSTS: [&str; 2] = ["https://prewww1.aeat.es/", "https://prewww10.aeat.es/"];

/// A haircut for a customer from Kosovo who pays with the tax id of their country: subject at 21 %.
const S1_BREAKDOWN: &str =
    r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.00,"base":10000,"quota":2100}]"#;

/// The recipient as the till stores it after sales#360: country `QU`, document kind `04`.
const TAX_ID: &str = "810000001";
const RECIPIENT_NAME: &str = "KOSOVO CUSTOMER";
const IDENTITY: &str = "<sum1:IDOtro><sum1:CodigoPais>QU</sum1:CodigoPais>\
                        <sum1:IDType>04</sum1:IDType><sum1:ID>810000001</sum1:ID></sum1:IDOtro>";

/// Panics unless `url` is an AEAT **preproduction** host.
fn assert_preproduction(url: &str) {
    assert!(
        PREPRODUCTION_HOSTS.iter().any(|h| url.starts_with(h)),
        "sales#374: the unlisted-country rehearsal only talks to AEAT preproduction, refused {url}"
    );
}

/// The door every post of this file goes through, checked before it is used.
fn preproduction_door() -> &'static str {
    let url = aeat::endpoint(
        config()["environment"].as_str().unwrap_or_default(),
        CERTIFICATE_KIND,
    );
    assert_preproduction(url);
    url
}

fn config() -> Json {
    json!({
        "software_name": ISSUER_NAME,
        "software_nif": ISSUER_NIF,
        "environment": ENVIRONMENT,
        "producer_facts": {
            "NombreRazon": ISSUER_NAME,
            "NIF": ISSUER_NIF,
            "NombreSistemaInformatico": "ERPlora Hub",
            "IdSistemaInformatico": "EC",
            "TipoUsoPosibleSoloVerifactu": "S",
            "TipoUsoPosibleMultiOT": "S",
            "IndicadorMultiplesOT": "N",
        },
    })
}

/// The alta the hub would build, chained on `previous_hash`, generated at `ts`. Amounts in CENTS
/// (ADR-0007).
fn build_record(invoice_number: &str, ts: &str, previous_hash: &str) -> Json {
    let date = &ts[..10];
    let hash = chain::alta_hash(
        ISSUER_NIF,
        invoice_number,
        date,
        "F1",
        21.0,
        121.0,
        previous_hash,
        ts,
    );
    json!({
        "id": invoice_number,
        "record_type": "alta",
        "issuer_nif": ISSUER_NIF,
        "issuer_name": ISSUER_NAME,
        "invoice_number": invoice_number,
        "invoice_date": date,
        "invoice_type": "F1",
        "description": format!("Unlisted-country customer rehearsal {invoice_number}"),
        "base_amount": 10000,
        "tax_rate": 21.0,
        "tax_breakdown": S1_BREAKDOWN,
        "tax_amount": 2100,
        "total_amount": 12100,
        "recipient_nif": TAX_ID,
        "recipient_name": RECIPIENT_NAME,
        "recipient_country": "QU",
        "recipient_id_type": "04",
        "record_hash": hash,
        "previous_hash": previous_hash,
        "is_first_record": if previous_hash.is_empty() { 1 } else { 0 },
        "generation_timestamp": ts,
    })
}

fn fixture(key: &str) -> String {
    let path = format!(
        "{}/tests/fixtures/unlisted_country_{key}_2026-09-24.xml",
        env!("CARGO_MANIFEST_DIR")
    );
    std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{path}: {e}"))
}

/// The text of the first `<…:tag>` element in `xml`, whatever its namespace prefix.
fn element(xml: &str, tag: &str) -> String {
    let open = format!(":{tag}>");
    let start = xml.find(&open).map(|i| i + open.len()).unwrap_or_default();
    xml[start..]
        .split('<')
        .next()
        .unwrap_or_default()
        .to_string()
}

// ── Offline: runs in every suite ────────────────────────────────────────────────────────────

/// 🔴 The hard condition: this rehearsal cannot reach production. Pointing `ENVIRONMENT` at
/// `production`, or `aeat::endpoint` at a production host for this environment, turns this red.
#[test]
fn the_rehearsal_only_ever_talks_to_preproduction() {
    assert_ne!(config()["environment"], "production");
    assert_eq!(
        preproduction_door(),
        "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
    );
}

/// The guard is not decorative: it refuses both production doors.
#[test]
fn the_door_guard_refuses_production() {
    // `"seal"` is the crate-private `SEAL_TYPE`: the stamp door (`www10`).
    for kind in ["own", "seal"] {
        let production = aeat::endpoint("production", kind);
        let refused = std::panic::catch_unwind(|| assert_preproduction(production));
        assert!(refused.is_err(), "the guard let {production} through");
    }
}

/// What is sent identifies the customer by `IDOtro` with `QU`/`04` and passes the XSD gate that
/// runs before every real transmission.
#[test]
fn the_unlisted_country_goes_as_qu_and_passes_the_xsd_gate() {
    let prev = json!({
        "issuer_nif": ISSUER_NIF,
        "invoice_number": "QU-PREV",
        "invoice_date": "2026-09-24",
        "record_hash": "AB".repeat(32),
    });
    let record = build_record("QU-OFFLINE", "2026-09-24T12:00:00+02:00", &"AB".repeat(32));
    let xml = aeat::build_soap(&record, &config(), Some(&prev), "hub-unlisted-country")
        .expect("declarable");
    xsd::validate_registro(&xml).expect("XSD gate");
    assert!(xml.contains(IDENTITY), "{xml}");
}

/// The frozen evidence of 2026-09-24: what was SENT carries `QU`/`04`, and the AEAT preproduction
/// took that very invoice (same `NumSerieFactura`) clean — `Correcto`, no error code, and a CSV.
#[test]
fn the_aeat_took_the_unlisted_country_clean() {
    let sent = fixture("qu_sent");
    assert!(sent.contains(IDENTITY), "the sent XML lacks the QU IDOtro");
    let number = element(&sent, "NumSerieFactura");
    assert!(number.starts_with("QU-"), "{number}");

    let answer = fixture("qu");
    assert_eq!(
        element(&answer, "NumSerieFactura"),
        number,
        "another invoice"
    );
    let resp = aeat::parse_response(&answer);
    assert_eq!(resp.estado_envio, "Correcto", "{resp:?}");
    assert_eq!(resp.estado_registro, "Correcto", "{resp:?}");
    assert!(resp.codigo_error.is_empty(), "{resp:?}");
    assert!(!resp.csv.is_empty(), "no CSV");
}

// ── Live: preproduction, by hand ────────────────────────────────────────────────────────────

fn identity() -> reqwest::Identity {
    let var =
        |k: &str| std::env::var(k).unwrap_or_else(|_| panic!("missing environment variable {k}"));
    let der = std::fs::read(var("ERPLORA_CERT_P12")).expect("could not read the .p12");
    erplora_runtime::certificate::identity_from_der(&der, &var("ERPLORA_COMPANY_CERT_P12_PASSWORD"))
        .expect("the .p12 does not open")
}

#[tokio::test]
#[ignore = "needs the network and the business certificate"]
async fn the_unlisted_country_against_preproduction() {
    let door = preproduction_door();
    println!("DOOR {door}");

    // Chain from what the AEAT holds as the taxpayer's last record, so the invoice does not pay a
    // 2007 that would blur the verdict on the recipient.
    let now = chrono::Local::now();
    let consult = aeat::build_consult_soap(
        ISSUER_NIF,
        ISSUER_NAME,
        &now.format("%Y").to_string(),
        &now.format("%m").to_string(),
        None,
    )
    .expect("consult envelope");
    let body = aeat::post_soap(door, identity(), &consult)
        .await
        .expect("the consult must answer 200");
    let held = aeat::parse_consult_response(&body).expect("the AEAT refused the consult");
    let anchor = aeat::pick_latest_record(&held).expect("the taxpayer already has records");
    let d: Vec<&str> = anchor.invoice_date.split('-').collect();
    let prev = json!({
        "issuer_nif": anchor.issuer_nif,
        "invoice_number": anchor.invoice_number,
        // The consult answers DD-MM-YYYY; `build_soap` expects ISO.
        "invoice_date": format!("{}-{}-{}", d[2], d[1], d[0]),
        "record_hash": chain::normalize_hash(&anchor.record_hash),
    });

    let ts = chrono::Local::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, false);
    // Own series: the AEAT dedupes by (NIF, number, date) — a shared one is a 3000.
    let number = format!("QU-{}", now.format("%Y%m%d-%H%M%S"));
    let record = build_record(
        &number,
        &ts,
        prev["record_hash"].as_str().unwrap_or_default(),
    );
    let xml = aeat::build_soap(&record, &config(), Some(&prev), "hub-unlisted-country")
        .expect("declarable");
    xsd::validate_registro(&xml).expect("the XSD gate runs before every post");
    assert!(xml.contains(IDENTITY), "{xml}");
    println!("\n===== SENT qu =====\n{xml}");

    let answer = aeat::post_soap(preproduction_door(), identity(), &xml)
        .await
        .expect("the AEAT must answer 200");
    println!("\n===== RESPONSE qu =====\n{answer}\n===== END qu =====");
    let resp = aeat::parse_response(&answer);
    println!(
        "[qu] EstadoEnvio={:?} EstadoRegistro={:?} CodigoError={:?} Descripcion={:?} CSV={:?}",
        resp.estado_envio,
        resp.estado_registro,
        resp.codigo_error,
        resp.descripcion_error,
        resp.csv
    );
    assert_eq!(resp.estado_registro, "Correcto", "{answer}");
    assert!(resp.codigo_error.is_empty(), "{answer}");
    assert!(!resp.csv.is_empty(), "an accepted submission carries a CSV");
}
