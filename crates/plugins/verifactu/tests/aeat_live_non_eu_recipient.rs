//! **REAL** rehearsal against the AEAT **preproduction**: full invoices (`F1`) to customers from
//! OUTSIDE the EU, identified by `IDOtro` with the customer's country and document kind instead of
//! a Spanish `NIF` the AEAT cannot find in its census (hub#1967).
//!
//! hub#1965 covered the EU (`IDType 02`, told by the VAT prefix). Outside the EU there is no prefix
//! to read: the invoice carries the customer's country (`recipient_country`) and, when it is not
//! the tax id of that country, the document kind (`recipient_id_type`). Four cases:
//!
//! - `us`: a US company, the tax id of its country (`IDType 04`, the default), services `N2`;
//! - `passport`: a US tourist paying with a passport (`IDType 03`), a haircut at 21 % (`S1`);
//! - `gb`: a British company with its `GB` VAT number, which is not an EU one (`04`), `N2`;
//! - `xi`: a Northern Ireland company, whose `XI` number IS valid in VIES but whose `CodigoPais`
//!   has to be `GB` (`XI` is not a `CountryType2`), without a country on the invoice (`02`).
//!   `XI366303068` is valid in VIES (checked on 2026-09-22).
//!
//! 🔴 **Preproduction ONLY** (condition of 2026-09-20). Every post goes through
//! [`preproduction_door`], which refuses any host that is not `prewww1`/`prewww10`, and the
//! offline test [`the_rehearsal_only_ever_talks_to_preproduction`] fails the suite if the
//! rehearsal's environment or door would ever resolve to production.
//!
//! The AEAT answers are frozen in `tests/fixtures/non_eu_recipient_*_2026-09-22.xml` and read
//! back by the offline tests, so the evidence stays in the suite without the network.
//!
//! ```sh
//! ERPLORA_CERT_P12=…/.secrets/ERPlora_Cloud__R__B27593136_.p12 \
//! ERPLORA_COMPANY_CERT_P12_PASSWORD=… \
//!   cargo test -p erplora-verifactu --test aeat_live_non_eu_recipient -- --ignored --nocapture
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

/// A B2B service to a business established abroad: not subject in Spain by location (ADR-0186).
const N2_BREAKDOWN: &str = r#"[{"tax":"vat","regime":"01","class":"not_subject_location","rate":0.00,"base":100000,"quota":0}]"#;

/// A service consumed in Spain by a private person: subject at 21 %.
const S1_BREAKDOWN: &str =
    r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.00,"base":10000,"quota":2100}]"#;

/// Panics unless `url` is an AEAT **preproduction** host.
fn assert_preproduction(url: &str) {
    assert!(
        PREPRODUCTION_HOSTS.iter().any(|h| url.starts_with(h)),
        "hub#1967: the non-EU-recipient rehearsal only talks to AEAT preproduction, refused {url}"
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

struct Case {
    key: &'static str,
    /// The customer's tax id or document number as the invoice stores it (`customer_tax_id`).
    tax_id: &'static str,
    /// `customer_country` / `customer_id_type` of the invoice ('' = not on the invoice).
    country: &'static str,
    id_type: &'static str,
    name: &'static str,
    /// Subject at 21 % (`S1`) or not subject by location (`N2`).
    subject: bool,
    /// The identity block the XML must carry.
    identity: &'static str,
}

fn cases() -> Vec<Case> {
    vec![
        Case {
            key: "us",
            tax_id: "84-2345678",
            country: "US",
            id_type: "",
            name: "CUSTOMER INC",
            subject: false,
            identity: "<sum1:IDOtro><sum1:CodigoPais>US</sum1:CodigoPais>\
                       <sum1:IDType>04</sum1:IDType><sum1:ID>842345678</sum1:ID></sum1:IDOtro>",
        },
        Case {
            key: "passport",
            tax_id: "XA1234567",
            country: "US",
            id_type: "03",
            name: "JANE DOE",
            subject: true,
            identity: "<sum1:IDOtro><sum1:CodigoPais>US</sum1:CodigoPais>\
                       <sum1:IDType>03</sum1:IDType><sum1:ID>XA1234567</sum1:ID></sum1:IDOtro>",
        },
        Case {
            key: "gb",
            tax_id: "GB220430231",
            country: "GB",
            id_type: "",
            name: "TESCO PLC",
            subject: false,
            identity: "<sum1:IDOtro><sum1:CodigoPais>GB</sum1:CodigoPais>\
                       <sum1:IDType>04</sum1:IDType><sum1:ID>GB220430231</sum1:ID></sum1:IDOtro>",
        },
        Case {
            key: "xi",
            tax_id: "XI366303068",
            country: "",
            id_type: "",
            name: "DONNELLY BROS GARAGES (DUNGANNON) LIMITED",
            subject: false,
            identity: "<sum1:IDOtro><sum1:CodigoPais>GB</sum1:CodigoPais>\
                       <sum1:IDType>02</sum1:IDType><sum1:ID>XI366303068</sum1:ID></sum1:IDOtro>",
        },
    ]
}

/// The alta the hub would build for `case`, chained on `previous_hash`, generated at `ts`.
/// Amounts in CENTS (ADR-0007).
fn build_record(case: &Case, invoice_number: &str, ts: &str, previous_hash: &str) -> Json {
    let date = &ts[..10];
    let (base, quota, breakdown) = if case.subject {
        (10000, 2100, S1_BREAKDOWN)
    } else {
        (100000, 0, N2_BREAKDOWN)
    };
    let hash = chain::alta_hash(
        ISSUER_NIF,
        invoice_number,
        date,
        "F1",
        quota as f64 / 100.0,
        (base + quota) as f64 / 100.0,
        previous_hash,
        ts,
    );
    json!({
        "id": invoice_number.replace(['/', ' '], "-"),
        "record_type": "alta",
        "issuer_nif": ISSUER_NIF,
        "issuer_name": ISSUER_NAME,
        "invoice_number": invoice_number,
        "invoice_date": date,
        "invoice_type": "F1",
        "description": format!("Non-EU customer rehearsal {} {invoice_number}", case.key),
        "base_amount": base,
        "tax_rate": if case.subject { 21.0 } else { 0.0 },
        "tax_breakdown": breakdown,
        "tax_amount": quota,
        "total_amount": base + quota,
        "recipient_nif": case.tax_id,
        "recipient_name": case.name,
        "recipient_country": case.country,
        "recipient_id_type": case.id_type,
        "record_hash": hash,
        "previous_hash": previous_hash,
        "is_first_record": if previous_hash.is_empty() { 1 } else { 0 },
        "generation_timestamp": ts,
    })
}

fn fixture(key: &str) -> String {
    let path = format!(
        "{}/tests/fixtures/non_eu_recipient_{key}_2026-09-22.xml",
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

/// What is sent identifies the customer by `IDOtro`, never by a Spanish `NIF`, and passes the XSD
/// gate that runs before every real transmission.
#[test]
fn every_non_eu_recipient_goes_as_idotro_and_passes_the_xsd_gate() {
    let ts = "2026-09-22T12:00:00+02:00";
    let prev = json!({
        "issuer_nif": ISSUER_NIF,
        "invoice_number": "NONEU-PREV",
        "invoice_date": "2026-09-22",
        "record_hash": "AB".repeat(32),
    });
    for case in cases() {
        let record = build_record(&case, &format!("NONEU-{}", case.key), ts, &"AB".repeat(32));
        let xml = aeat::build_soap(&record, &config(), Some(&prev), "hub-non-eu")
            .unwrap_or_else(|e| panic!("{}: not declarable: {e}", case.key));
        xsd::validate_registro(&xml).unwrap_or_else(|e| panic!("{}: XSD: {e}", case.key));
        assert!(xml.contains(case.identity), "{}: {xml}", case.key);
        let recipient = xml
            .split("<sum1:IDDestinatario>")
            .nth(1)
            .and_then(|rest| rest.split("</sum1:IDDestinatario>").next())
            .unwrap_or_default();
        assert!(
            !recipient.contains("<sum1:NIF>"),
            "{}: the recipient goes as a Spanish NIF\n{xml}",
            case.key
        );
    }
}

/// The frozen evidence of 2026-09-22: what was SENT carries the `IDOtro`, and the AEAT
/// preproduction took that very invoice (same `NumSerieFactura`) clean — `Correcto`, no error
/// code, and a CSV.
#[test]
fn the_aeat_took_every_non_eu_recipient_clean() {
    for case in cases() {
        let sent = fixture(&format!("{}_sent", case.key));
        assert!(
            sent.contains(case.identity),
            "{}: the sent XML lacks the IDOtro",
            case.key
        );
        let qualification = if case.subject { "S1" } else { "N2" };
        assert!(
            sent.contains(&format!(
                "<sum1:CalificacionOperacion>{qualification}</sum1:CalificacionOperacion>"
            )),
            "{}: not {qualification}",
            case.key
        );
        let number = element(&sent, "NumSerieFactura");
        assert!(
            number.ends_with(&format!("-{}", case.key)),
            "{}: {number}",
            case.key
        );

        let answer = fixture(case.key);
        assert_eq!(
            element(&answer, "NumSerieFactura"),
            number,
            "{}: another invoice",
            case.key
        );
        let resp = aeat::parse_response(&answer);
        assert_eq!(resp.estado_envio, "Correcto", "{}: {resp:?}", case.key);
        assert_eq!(resp.estado_registro, "Correcto", "{}: {resp:?}", case.key);
        assert!(resp.codigo_error.is_empty(), "{}: {resp:?}", case.key);
        assert!(!resp.csv.is_empty(), "{}: no CSV", case.key);
    }
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
async fn every_non_eu_recipient_against_preproduction() {
    let door = preproduction_door();
    println!("DOOR {door}");

    // Chain from what the AEAT holds as the taxpayer's last record, so no case pays a 2007.
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
    let mut prev = json!({
        "issuer_nif": anchor.issuer_nif,
        "invoice_number": anchor.invoice_number,
        // The consult answers DD-MM-YYYY; `build_soap` expects ISO.
        "invoice_date": format!("{}-{}-{}", d[2], d[1], d[0]),
        "record_hash": chain::normalize_hash(&anchor.record_hash),
    });

    let serial = format!("NONEU-{}", now.format("%Y%m%d-%H%M%S"));
    let mut failures = Vec::new();
    for case in cases() {
        let ts = chrono::Local::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, false);
        let number = format!("{serial}-{}", case.key);
        let record = build_record(
            &case,
            &number,
            &ts,
            prev["record_hash"].as_str().unwrap_or_default(),
        );
        let xml =
            aeat::build_soap(&record, &config(), Some(&prev), "hub-non-eu").expect("declarable");
        xsd::validate_registro(&xml).expect("the XSD gate runs before every post");
        println!("\n===== SENT {} =====\n{xml}", case.key);

        let answer = aeat::post_soap(preproduction_door(), identity(), &xml)
            .await
            .expect("the AEAT must answer 200");
        println!(
            "\n===== RESPONSE {} =====\n{answer}\n===== END {} =====",
            case.key, case.key
        );
        let resp = aeat::parse_response(&answer);
        println!(
            "[{}] EstadoEnvio={:?} EstadoRegistro={:?} CodigoError={:?} Descripcion={:?} CSV={:?}",
            case.key,
            resp.estado_envio,
            resp.estado_registro,
            resp.codigo_error,
            resp.descripcion_error,
            resp.csv
        );
        if resp.estado_registro != "Correcto" || !resp.codigo_error.is_empty() {
            failures.push(format!(
                "{}: {} {} {}",
                case.key, resp.estado_registro, resp.codigo_error, resp.descripcion_error
            ));
        }
        // Only a registered record may anchor the next one.
        if resp.estado_registro != "Incorrecto" {
            prev = json!({
                "issuer_nif": record["issuer_nif"],
                "invoice_number": record["invoice_number"],
                "invoice_date": record["invoice_date"],
                "record_hash": record["record_hash"],
            });
        }
    }
    assert!(
        failures.is_empty(),
        "the AEAT did not take every non-EU recipient clean: {failures:#?}"
    );
}
