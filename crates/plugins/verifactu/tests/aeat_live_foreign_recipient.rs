//! **REAL** rehearsal against the AEAT **preproduction**: a full invoice (`F1`, intra-community
//! `N2`) to a customer of another EU member state, identified by `IDOtro` + `IDType 02` NIF-IVA
//! instead of a Spanish `NIF` (hub#1965).
//!
//! hub#294 proved the `N2` qualification with a Spanish recipient, to isolate the breakdown. This
//! file sends the real shape of that sale: the customer's EU VAT number. Two cases, the general one
//! (`DE…`) and the only member state whose VAT prefix is not its ISO code (`EL…` → `GR`). Both
//! numbers are valid in VIES (checked on 2026-09-22), because the AEAT checks NIF-IVAs there.
//!
//! 🔴 **Preproduction ONLY** (condition of 2026-09-20). Every post goes through
//! [`preproduction_door`], which refuses any host that is not `prewww1`/`prewww10`, and the
//! offline test [`the_rehearsal_only_ever_talks_to_preproduction`] fails the suite if the
//! rehearsal's environment or door would ever resolve to production.
//!
//! The AEAT answers are frozen in `tests/fixtures/foreign_recipient_*_2026-09-22.xml` and read
//! back by the offline tests, so the evidence stays in the suite without the network.
//!
//! ```sh
//! ERPLORA_CERT_P12=…/.secrets/ERPlora_Cloud__R__B27593136_.p12 \
//! ERPLORA_COMPANY_CERT_P12_PASSWORD=… \
//!   cargo test -p erplora-verifactu --test aeat_live_foreign_recipient -- --ignored --nocapture
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

/// The intra-community B2B sale of ADR-0186: not subject in Spain by location, no rate nor quota.
const N2_BREAKDOWN: &str = r#"[{"tax":"vat","regime":"01","class":"not_subject_location","rate":0.00,"base":100000,"quota":0}]"#;

/// Panics unless `url` is an AEAT **preproduction** host.
fn assert_preproduction(url: &str) {
    assert!(
        PREPRODUCTION_HOSTS.iter().any(|h| url.starts_with(h)),
        "hub#1965: the foreign-recipient rehearsal only talks to AEAT preproduction, refused {url}"
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
    /// The customer's tax id as the invoice stores it (`customer_tax_id`).
    tax_id: &'static str,
    name: &'static str,
    /// The identity block the XML must carry.
    identity: &'static str,
}

fn cases() -> Vec<Case> {
    vec![
        Case {
            key: "de",
            tax_id: "DE811569869",
            name: "KUNDE GMBH",
            identity: "<sum1:IDOtro><sum1:CodigoPais>DE</sum1:CodigoPais>\
                       <sum1:IDType>02</sum1:IDType><sum1:ID>DE811569869</sum1:ID></sum1:IDOtro>",
        },
        Case {
            key: "el",
            tax_id: "EL094259216",
            name: "INTER DYNAMIC AE",
            identity: "<sum1:IDOtro><sum1:CodigoPais>GR</sum1:CodigoPais>\
                       <sum1:IDType>02</sum1:IDType><sum1:ID>EL094259216</sum1:ID></sum1:IDOtro>",
        },
    ]
}

/// The alta the hub would build for `case`, chained on `previous_hash`, generated at `ts`.
/// Amounts in CENTS (ADR-0007): 1.000,00 € base, no quota.
fn build_record(case: &Case, invoice_number: &str, ts: &str, previous_hash: &str) -> Json {
    let date = &ts[..10];
    let hash = chain::alta_hash(
        ISSUER_NIF,
        invoice_number,
        date,
        "F1",
        0.0,
        1000.0,
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
        "description": format!("Intra-community sale rehearsal {} {invoice_number}", case.key),
        "base_amount": 100000,
        "tax_rate": 0.0,
        "tax_breakdown": N2_BREAKDOWN,
        "tax_amount": 0,
        "total_amount": 100000,
        "recipient_nif": case.tax_id,
        "recipient_name": case.name,
        "record_hash": hash,
        "previous_hash": previous_hash,
        "is_first_record": if previous_hash.is_empty() { 1 } else { 0 },
        "generation_timestamp": ts,
    })
}

fn fixture(key: &str) -> String {
    let path = format!(
        "{}/tests/fixtures/foreign_recipient_{key}_2026-09-22.xml",
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
fn every_foreign_recipient_goes_as_idotro_and_passes_the_xsd_gate() {
    let ts = "2026-09-22T12:00:00+02:00";
    let prev = json!({
        "issuer_nif": ISSUER_NIF,
        "invoice_number": "INTRA-PREV",
        "invoice_date": "2026-09-22",
        "record_hash": "AB".repeat(32),
    });
    for case in cases() {
        let record = build_record(&case, &format!("INTRA-{}", case.key), ts, &"AB".repeat(32));
        let xml = aeat::build_soap(&record, &config(), Some(&prev), "hub-intra")
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
fn the_aeat_took_every_foreign_recipient_clean() {
    for case in cases() {
        let sent = fixture(&format!("{}_sent", case.key));
        assert!(
            sent.contains(case.identity),
            "{}: the sent XML lacks the IDOtro",
            case.key
        );
        assert!(
            sent.contains("<sum1:CalificacionOperacion>N2</sum1:CalificacionOperacion>"),
            "{}: not the intra-community N2",
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
async fn every_foreign_recipient_against_preproduction() {
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

    let serial = format!("INTRA-{}", now.format("%Y%m%d-%H%M%S"));
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
            aeat::build_soap(&record, &config(), Some(&prev), "hub-intra").expect("declarable");
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
        "the AEAT did not take every foreign recipient clean: {failures:#?}"
    );
}
