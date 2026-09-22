//! **REAL** rehearsal against the AEAT **preproduction**: every `<Desglose>` qualification that
//! ADR-0186 says the hub can declare, one real alta each (hub#294).
//!
//! A badly qualified breakdown validates against the XSD exactly as well as a correct one — that
//! is why ADR-0186 exists — and the local validator only covers the rules the document spells out.
//! What the document does not say and the service does is only learnt by sending. Until this file,
//! the only breakdown that had ever reached the AEAT was a national 21 % line
//! (`aeat_live_2007.rs`); these are the other seven:
//!
//! | case | what it declares |
//! |---|---|
//! | `mixed` | two `DetalleDesglose`, 21 % + 10 % |
//! | `exempt` | `OperacionExenta E1`, no rate nor quota (§15.5) |
//! | `surcharge` | `TipoRecargoEquivalencia`/`CuotaRecargoEquivalencia` INSIDE the VAT line |
//! | `igic` | `Impuesto 03` + `ClaveRegimen 01` (L8B) + `S1` at a Canarian rate |
//! | `ipsi` | `Impuesto 02` |
//! | `n2` | `N2`, no rate nor quota (error 1237) |
//! | `s2` | `S2` with `TipoImpositivo = 0` and `CuotaRepercutida = 0` explicit (§15.4) |
//!
//! 🔴 **Preproduction ONLY** (hub#294, condition of 2026-09-20). Every post goes through
//! [`preproduction_door`], which refuses any host that is not `prewww1`/`prewww10`, and the
//! offline test [`the_rehearsal_only_ever_talks_to_preproduction`] fails the suite if the
//! rehearsal's environment or door would ever resolve to production.
//!
//! The AEAT answers are frozen in `tests/fixtures/desglose_*_2026-09-22.xml` and read back by the
//! offline tests, so the evidence stays in the suite without the network.
//!
//! The live test is `#[ignore]`: it needs the network and the business certificate.
//!
//! ```sh
//! ERPLORA_CERT_P12=…/.secrets/ERPlora_Cloud__R__B27593136_.p12 \
//! ERPLORA_COMPANY_CERT_P12_PASSWORD=… \
//!   cargo test -p erplora-verifactu --test aeat_live_desglose -- --ignored --nocapture
//! ```
use erplora_verifactu::{aeat, chain, xsd};
use serde_json::json;

type Json = serde_json::Value;

/// The only environment this rehearsal is allowed to declare. Anything that is not literally
/// `production` stays in preproduction (`aeat::endpoint`), but the guard below checks the HOST,
/// not this word, so a change here is caught either way.
const ENVIRONMENT: &str = "testing";

/// The representative `.p12` of ERPlora (`…_R_…`) is the shape of the `own` slot: door `prewww1`.
const CERTIFICATE_KIND: &str = "own";

/// The rehearsal issuer — the same test taxpayer as the other frozen fixtures (ADR-0189: what
/// preproduction accepts stays recorded there, so it goes under ERPlora's own NIF and a
/// rehearsal series).
const ISSUER_NIF: &str = "B27593136";
const ISSUER_NAME: &str = "ERPLORA CLOUD SL";

/// A recipient that exists in the census, for the cases that need a full invoice (F1).
const RECIPIENT_NIF: &str = "Q2826000H";
const RECIPIENT_NAME: &str = "AGENCIA ESTATAL DE ADMINISTRACION TRIBUTARIA";

/// Hosts this rehearsal may post to. Nothing else.
const PREPRODUCTION_HOSTS: [&str; 2] = ["https://prewww1.aeat.es/", "https://prewww10.aeat.es/"];

/// Panics unless `url` is an AEAT **preproduction** host.
fn assert_preproduction(url: &str) {
    assert!(
        PREPRODUCTION_HOSTS.iter().any(|h| url.starts_with(h)),
        "hub#294: the desglose rehearsal only talks to AEAT preproduction, refused {url}"
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

/// One qualification to rehearse. Amounts in CENTS (ADR-0007), as `invoice` writes them.
struct Case {
    key: &'static str,
    invoice_type: &'static str,
    /// The array-shaped `tax_breakdown` (ADR-0186), exactly what the producer sends.
    tax_breakdown: &'static str,
    base: i64,
    /// `CuotaTotal` in cents: quotas PLUS equivalence surcharge.
    tax: i64,
    /// Fragments the generated XML must carry.
    must: &'static [&'static str],
    /// Elements the generated XML must NOT carry.
    must_not: &'static [&'static str],
}

fn cases() -> Vec<Case> {
    vec![
        Case {
            key: "mixed",
            invoice_type: "F2",
            tax_breakdown: r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.00,"base":1000,"quota":210},
                               {"tax":"vat","regime":"01","class":"subject","rate":10.00,"base":1000,"quota":100}]"#,
            base: 2000,
            tax: 310,
            must: &[
                "<sum1:TipoImpositivo>21.00</sum1:TipoImpositivo>",
                "<sum1:TipoImpositivo>10.00</sum1:TipoImpositivo>",
            ],
            must_not: &[],
        },
        Case {
            key: "exempt",
            invoice_type: "F2",
            tax_breakdown: r#"[{"tax":"vat","regime":"01","class":"exempt","exempt_reason":"E1","rate":0.00,"base":5000,"quota":0}]"#,
            base: 5000,
            tax: 0,
            must: &["<sum1:OperacionExenta>E1</sum1:OperacionExenta>"],
            must_not: &[
                "CalificacionOperacion",
                "TipoImpositivo",
                "CuotaRepercutida",
            ],
        },
        Case {
            key: "surcharge",
            invoice_type: "F1",
            tax_breakdown: r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.00,"base":10000,"quota":2100,"surcharge_rate":5.20,"surcharge_quota":520}]"#,
            base: 10000,
            tax: 2620,
            must: &[
                "<sum1:TipoImpositivo>21.00</sum1:TipoImpositivo>",
                "<sum1:TipoRecargoEquivalencia>5.20</sum1:TipoRecargoEquivalencia>",
                "<sum1:CuotaRecargoEquivalencia>5.20</sum1:CuotaRecargoEquivalencia>",
            ],
            must_not: &["<sum1:TipoImpositivo>5.20</sum1:TipoImpositivo>"],
        },
        Case {
            key: "igic",
            invoice_type: "F2",
            tax_breakdown: r#"[{"tax":"igic","regime":"01","class":"subject","rate":7.00,"base":10000,"quota":700}]"#,
            base: 10000,
            tax: 700,
            must: &[
                "<sum1:Impuesto>03</sum1:Impuesto>",
                "<sum1:ClaveRegimen>01</sum1:ClaveRegimen>",
                "<sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>",
                "<sum1:TipoImpositivo>7.00</sum1:TipoImpositivo>",
            ],
            must_not: &["<sum1:Impuesto>01</sum1:Impuesto>"],
        },
        Case {
            key: "ipsi",
            invoice_type: "F2",
            tax_breakdown: r#"[{"tax":"ipsi","regime":"01","class":"subject","rate":4.00,"base":10000,"quota":400}]"#,
            base: 10000,
            tax: 400,
            must: &[
                "<sum1:Impuesto>02</sum1:Impuesto>",
                "<sum1:TipoImpositivo>4.00</sum1:TipoImpositivo>",
            ],
            must_not: &["<sum1:Impuesto>01</sum1:Impuesto>"],
        },
        Case {
            key: "n2",
            invoice_type: "F1",
            tax_breakdown: r#"[{"tax":"vat","regime":"01","class":"not_subject_location","rate":0.00,"base":100000,"quota":0}]"#,
            base: 100000,
            tax: 0,
            must: &["<sum1:CalificacionOperacion>N2</sum1:CalificacionOperacion>"],
            must_not: &["TipoImpositivo", "CuotaRepercutida"],
        },
        Case {
            key: "s2",
            invoice_type: "F1",
            tax_breakdown: r#"[{"tax":"vat","regime":"01","class":"subject_reverse","rate":0.00,"base":10000,"quota":0}]"#,
            base: 10000,
            tax: 0,
            must: &[
                "<sum1:CalificacionOperacion>S2</sum1:CalificacionOperacion>",
                "<sum1:TipoImpositivo>0.00</sum1:TipoImpositivo>",
                "<sum1:CuotaRepercutida>0.00</sum1:CuotaRepercutida>",
            ],
            must_not: &[],
        },
    ]
}

/// The alta record the hub would build for `case`, chained on `previous_hash`, generated at `ts`.
fn build_record(case: &Case, invoice_number: &str, ts: &str, previous_hash: &str) -> Json {
    let date = &ts[..10];
    let total = case.base + case.tax;
    let hash = chain::alta_hash(
        ISSUER_NIF,
        invoice_number,
        date,
        case.invoice_type,
        case.tax as f64 / 100.0,
        total as f64 / 100.0,
        previous_hash,
        ts,
    );
    let mut record = json!({
        "id": invoice_number.replace(['/', ' '], "-"),
        "record_type": "alta",
        "issuer_nif": ISSUER_NIF,
        "issuer_name": ISSUER_NAME,
        "invoice_number": invoice_number,
        "invoice_date": date,
        "invoice_type": case.invoice_type,
        "description": format!("Desglose rehearsal {} {invoice_number}", case.key),
        "base_amount": case.base,
        "tax_rate": 0.0,
        "tax_breakdown": case.tax_breakdown,
        "tax_amount": case.tax,
        "total_amount": total,
        "record_hash": hash,
        "previous_hash": previous_hash,
        "is_first_record": if previous_hash.is_empty() { 1 } else { 0 },
        "generation_timestamp": ts,
    });
    if case.invoice_type == "F1" {
        record["recipient_nif"] = json!(RECIPIENT_NIF);
        record["recipient_name"] = json!(RECIPIENT_NAME);
    }
    record
}

fn link_to(record: &Json) -> Json {
    json!({
        "issuer_nif": record["issuer_nif"],
        "invoice_number": record["invoice_number"],
        "invoice_date": record["invoice_date"],
        "record_hash": record["record_hash"],
    })
}

fn fixture(key: &str) -> String {
    let path = format!(
        "{}/tests/fixtures/desglose_{key}_2026-09-22.xml",
        env!("CARGO_MANIFEST_DIR")
    );
    std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{path}: {e}"))
}

// ── Offline: runs in every suite ────────────────────────────────────────────────────────────

/// 🔴 The hard condition of hub#294: this rehearsal cannot reach production. Pointing
/// `ENVIRONMENT` at `production`, or `aeat::endpoint` at a production host for this environment,
/// turns this test red.
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

/// What is sent is what ADR-0186 says: each case carries its qualification and passes the same
/// XSD gate that runs before every real transmission.
#[test]
fn every_rehearsed_breakdown_is_qualified_and_passes_the_xsd_gate() {
    let ts = "2026-09-22T12:00:00+02:00";
    for case in cases() {
        let record = build_record(
            &case,
            &format!("DESG-{}", case.key),
            ts,
            "AB".repeat(32).as_str(),
        );
        let prev = json!({
            "issuer_nif": ISSUER_NIF,
            "invoice_number": "DESG-PREV",
            "invoice_date": "2026-09-22",
            "record_hash": "AB".repeat(32),
        });
        let xml = aeat::build_soap(&record, &config(), Some(&prev), "hub-desglose")
            .unwrap_or_else(|e| panic!("{}: not declarable: {e}", case.key));
        xsd::validate_registro(&xml).unwrap_or_else(|e| panic!("{}: XSD: {e}", case.key));
        for m in case.must {
            assert!(xml.contains(m), "{}: missing {m}\n{xml}", case.key);
        }
        for m in case.must_not {
            assert!(!xml.contains(m), "{}: must not carry {m}\n{xml}", case.key);
        }
    }
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

/// The frozen evidence of 2026-09-22: what was SENT carries each qualification, and the AEAT
/// preproduction took that very invoice (same `NumSerieFactura`) clean — `Correcto`, no error
/// code, and a CSV.
#[test]
fn the_aeat_took_every_rehearsed_breakdown_clean() {
    for case in cases() {
        let sent = fixture(&format!("{}_sent", case.key));
        for m in case.must {
            assert!(sent.contains(m), "{}: the sent XML lacks {m}", case.key);
        }
        for m in case.must_not {
            assert!(!sent.contains(m), "{}: the sent XML carries {m}", case.key);
        }
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
async fn every_breakdown_qualification_against_preproduction() {
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

    let serial = format!("DESG-{}", now.format("%Y%m%d-%H%M%S"));
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
            aeat::build_soap(&record, &config(), Some(&prev), "hub-desglose").expect("declarable");
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
            prev = link_to(&record);
        }
    }
    assert!(
        failures.is_empty(),
        "the AEAT did not take every breakdown clean: {failures:#?}"
    );
}
