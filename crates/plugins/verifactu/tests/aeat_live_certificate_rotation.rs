//! **REAL** rehearsal against the AEAT **preproduction**: the chain survives a change of
//! certificate (hub#325).
//!
//! The fingerprint of a record (`chain::alta_hash`, Orden HAC/1177/2024) is built from the
//! invoice and the previous fingerprint — never from who signs the transmission — and the local
//! e2e `crates/runtime/tests/verifactu_chain_survives_certificate_rotation_e2e.rs` (hub#1270)
//! proves the hub keeps chaining when the business swaps its `.p12`. What only the AEAT can say is
//! whether IT takes the next link when it arrives under another certificate. This file asks it,
//! with the two real certificates of the same taxpayer (ERPlora, NIF `B27593136`):
//!
//! | step | certificate | door |
//! |---|---|---|
//! | `a` | representative `.p12` (`own` slot) | `prewww1` |
//! | `b` | Sello de Entidad (what the gateway presents with) | `prewww10` |
//! | `c` | representative `.p12` again | `prewww1` |
//!
//! Each step chains on the previous one, so both directions of the `own` ↔ gateway pair are
//! crossed. The AEAT does check the link — a record whose `RegistroAnterior` is not the last one
//! it holds comes back `AceptadoConErrores` with `2007` (frozen in
//! `alta_2007_aceptado_con_errores_2026-08-02.xml`) — so a clean `Correcto` on `b` and `c` is the
//! AEAT accepting the link across the certificate change. A final consult freezes what the AEAT
//! holds afterwards.
//!
//! 🔴 **Preproduction ONLY** (condition of 2026-09-20). Every post goes through [`door`], which
//! refuses any host that is not `prewww1`/`prewww10`, and the offline test
//! [`the_rotation_rehearsal_only_ever_talks_to_preproduction`] fails the suite if either
//! certificate's door would ever resolve to production.
//!
//! The AEAT answers are frozen in `tests/fixtures/rotation_*_2026-09-22.{xml,json}` and read back by the
//! offline tests. The live test is `#[ignore]`: it needs the network and both certificates.
//!
//! ```sh
//! ERPLORA_COMPANY_CERT_P12_PATH=…/.secrets/ERPlora_Cloud__R__B27593136_.p12 \
//! ERPLORA_COMPANY_CERT_P12_PASSWORD=… \
//! ERPLORA_SEAL_P12=…/sello-A.p12 GATEWAY_CERT_PASSWORD=… \
//!   cargo test -p erplora-verifactu --test aeat_live_certificate_rotation -- --ignored --nocapture
//! ```
use erplora_verifactu::{aeat, chain, xsd};
use serde_json::json;

type Json = serde_json::Value;

/// The only environment this rehearsal declares. The guard checks the HOST, not this word.
const ENVIRONMENT: &str = "testing";

/// The two certificate kinds crossed. `"seal"` is the crate-private `SEAL_TYPE`.
const OWN: &str = "own";
const SEAL: &str = "seal";

/// The steps, in chain order: the certificate changes on every one.
const STEPS: [(&str, &str); 3] = [("a", OWN), ("b", SEAL), ("c", OWN)];

/// The rehearsal taxpayer (ADR-0189: rehearsals go under ERPlora's own NIF and a rehearsal series).
const ISSUER_NIF: &str = "B27593136";
const ISSUER_NAME: &str = "ERPLORA CLOUD SL";

/// Hosts this rehearsal may post to. Nothing else.
const PREPRODUCTION_HOSTS: [&str; 2] = ["https://prewww1.aeat.es/", "https://prewww10.aeat.es/"];

/// The day the evidence was frozen.
const EVIDENCE_DAY: &str = "2026-09-22";

/// Panics unless `url` is an AEAT **preproduction** host.
fn assert_preproduction(url: &str) {
    assert!(
        PREPRODUCTION_HOSTS.iter().any(|h| url.starts_with(h)),
        "hub#325: the rotation rehearsal only talks to AEAT preproduction, refused {url}"
    );
}

/// The door for `kind`, checked before it is used.
fn door(kind: &str) -> &'static str {
    let url = aeat::endpoint(config()["environment"].as_str().unwrap_or_default(), kind);
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

/// A plain simplified invoice (F2, 21 %), amounts in CENTS (ADR-0007), chained on
/// `previous_hash` and generated at `ts`.
fn build_record(invoice_number: &str, ts: &str, previous_hash: &str) -> Json {
    let date = &ts[..10];
    let (base, tax) = (1000_i64, 210_i64);
    let total = base + tax;
    let hash = chain::alta_hash(
        ISSUER_NIF,
        invoice_number,
        date,
        "F2",
        tax as f64 / 100.0,
        total as f64 / 100.0,
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
        "invoice_type": "F2",
        "description": format!("Certificate rotation rehearsal {invoice_number}"),
        "base_amount": base,
        "tax_rate": 21.0,
        "tax_breakdown": r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.00,"base":1000,"quota":210}]"#,
        "tax_amount": tax,
        "total_amount": total,
        "record_hash": hash,
        "previous_hash": previous_hash,
        "is_first_record": if previous_hash.is_empty() { 1 } else { 0 },
        "generation_timestamp": ts,
    })
}

fn link_to(record: &Json) -> Json {
    json!({
        "issuer_nif": record["issuer_nif"],
        "invoice_number": record["invoice_number"],
        "invoice_date": record["invoice_date"],
        "record_hash": record["record_hash"],
    })
}

/// `a_sent.xml` → `tests/fixtures/rotation_a_sent_2026-09-22.xml`.
fn fixture_path(name: &str) -> String {
    let (stem, ext) = name.rsplit_once('.').unwrap_or((name, "xml"));
    format!(
        "{}/tests/fixtures/rotation_{stem}_{EVIDENCE_DAY}.{ext}",
        env!("CARGO_MANIFEST_DIR")
    )
}

fn fixture(name: &str) -> String {
    let path = fixture_path(name);
    std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{path}: {e}"))
}

/// The text of the first `<…:tag>` element in `xml`, whatever its namespace prefix.
fn element(xml: &str, tag: &str) -> String {
    elements(xml, tag).into_iter().next().unwrap_or_default()
}

/// The text of every `<…:tag>` element in `xml`, in order.
fn elements(xml: &str, tag: &str) -> Vec<String> {
    let open = format!(":{tag}>");
    xml.match_indices(&open)
        // Opening tags only: `</sum1:Huella>` carries the same `:Huella>`.
        .filter(|(i, _)| {
            xml[..*i]
                .rfind('<')
                .is_some_and(|lt| !xml[lt..].starts_with("</"))
        })
        .map(|(i, _)| {
            xml[i + open.len()..]
                .split('<')
                .next()
                .unwrap_or_default()
                .to_string()
        })
        .collect()
}

/// The fingerprint a sent `RegistroAlta` declares for ITSELF, recomputed from its own fields.
fn recomputed_hash(sent: &str) -> String {
    // `RegistroAlta` carries `DD-MM-YYYY`; `alta_hash` takes the ISO date and formats it back.
    let sent_date = element(sent, "FechaExpedicionFactura");
    let d: Vec<&str> = sent_date.split('-').collect();
    let date_iso = format!("{}-{}-{}", d[2], d[1], d[0]);
    // The `Huella` of the record itself is the LAST `Huella` in the envelope (the first one,
    // when chained, is the previous record's inside `Encadenamiento`).
    let previous = if sent.contains(":RegistroAnterior>") {
        element(sent, "Huella")
    } else {
        String::new()
    };
    chain::alta_hash(
        &element(sent, "IDEmisorFactura"),
        &element(sent, "NumSerieFactura"),
        &date_iso,
        &element(sent, "TipoFactura"),
        element(sent, "CuotaTotal").parse().expect("CuotaTotal"),
        element(sent, "ImporteTotal").parse().expect("ImporteTotal"),
        &previous,
        &element(sent, "FechaHoraHusoGenRegistro"),
    )
}

/// The record's own fingerprint: the last `Huella` of the envelope.
fn own_hash(sent: &str) -> String {
    elements(sent, "Huella").pop().unwrap_or_default()
}

// ── Offline: runs in every suite ────────────────────────────────────────────────────────────

/// 🔴 The hard condition: neither certificate's door can be production. Pointing `ENVIRONMENT`
/// at `production`, or `aeat::endpoint` at a production host for either kind, turns this red.
#[test]
fn the_rotation_rehearsal_only_ever_talks_to_preproduction() {
    assert_ne!(config()["environment"], "production");
    assert_eq!(
        door(OWN),
        "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
    );
    assert_eq!(
        door(SEAL),
        "https://prewww10.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
    );
}

/// The guard is not decorative: it refuses both production doors.
#[test]
fn the_rotation_door_guard_refuses_production() {
    for kind in [OWN, SEAL] {
        let production = aeat::endpoint("production", kind);
        let refused = std::panic::catch_unwind(|| assert_preproduction(production));
        assert!(refused.is_err(), "the guard let {production} through");
    }
}

/// What the rehearsal sends is a chain: each record passes the XSD gate and links on the one
/// before it, whatever certificate will carry it.
#[test]
fn the_rehearsed_records_form_one_chain_and_pass_the_xsd_gate() {
    let mut prev: Option<Json> = None;
    let mut previous_hash = "AB".repeat(32);
    for (i, (step, _)) in STEPS.iter().enumerate() {
        let ts = format!("{EVIDENCE_DAY}T12:00:0{i}+02:00");
        let record = build_record(&format!("ROT-{step}"), &ts, &previous_hash);
        let anchor = prev.clone().unwrap_or_else(|| {
            json!({
                "issuer_nif": ISSUER_NIF,
                "invoice_number": "ROT-PREV",
                "invoice_date": EVIDENCE_DAY,
                "record_hash": previous_hash,
            })
        });
        let xml = aeat::build_soap(&record, &config(), Some(&anchor), "hub-rotation")
            .unwrap_or_else(|e| panic!("{step}: not declarable: {e}"));
        xsd::validate_registro(&xml).unwrap_or_else(|e| panic!("{step}: XSD: {e}"));
        assert_eq!(element(&xml, "Huella"), previous_hash, "{step}: link");
        assert_eq!(
            own_hash(&xml),
            recomputed_hash(&xml),
            "{step}: own fingerprint"
        );
        previous_hash = record["record_hash"]
            .as_str()
            .unwrap_or_default()
            .to_string();
        prev = Some(link_to(&record));
    }
}

/// The door and certificate each step really used, frozen by the live run.
fn doors() -> Vec<Json> {
    serde_json::from_str::<Json>(&fixture("doors.json"))
        .expect("doors.json")
        .as_array()
        .cloned()
        .unwrap_or_default()
}

/// The frozen evidence of 2026-09-22: the certificate really changed on every step, and every
/// post went to a preproduction door.
#[test]
fn the_certificate_really_changed_on_every_step() {
    let doors = doors();
    assert_eq!(doors.len(), STEPS.len());
    for ((step, kind), d) in STEPS.iter().zip(&doors) {
        assert_eq!(d["step"], *step);
        assert_eq!(d["certificate_kind"], *kind);
        let url = d["door"].as_str().unwrap_or_default();
        assert_preproduction(url);
        assert_eq!(url, door(kind), "{step}: another door");
    }
    let fingerprints: Vec<&str> = doors
        .iter()
        .map(|d| d["certificate_sha256"].as_str().unwrap_or_default())
        .collect();
    assert!(
        fingerprints.iter().all(|f| f.len() == 64),
        "{fingerprints:?}"
    );
    assert_ne!(
        fingerprints[0], fingerprints[1],
        "a → b must change certificate"
    );
    assert_ne!(
        fingerprints[1], fingerprints[2],
        "b → c must change certificate"
    );
    assert_eq!(
        fingerprints[0], fingerprints[2],
        "c goes back to a's certificate"
    );
}

/// The frozen evidence of 2026-09-22: what was SENT is one chain — each record links on the
/// previous record's own fingerprint and its own fingerprint recomputes — and the AEAT took every
/// link clean: `Correcto`, no error code (so no `2007`), a CSV, for that very invoice.
#[test]
fn the_aeat_took_every_link_across_the_certificate_change() {
    let mut previous: Option<String> = None;
    for (step, _) in STEPS {
        let sent = fixture(&format!("{step}_sent.xml"));
        assert_eq!(
            own_hash(&sent),
            recomputed_hash(&sent),
            "{step}: own fingerprint"
        );
        if let Some(prev) = &previous {
            assert!(sent.contains(":RegistroAnterior>"), "{step}: not chained");
            assert_eq!(&element(&sent, "Huella"), prev, "{step}: broken link");
        }
        previous = Some(own_hash(&sent));

        let answer = fixture(&format!("{step}.xml"));
        assert_eq!(
            element(&answer, "NumSerieFactura"),
            element(&sent, "NumSerieFactura"),
            "{step}: another invoice"
        );
        let resp = aeat::parse_response(&answer);
        assert_eq!(resp.estado_envio, "Correcto", "{step}: {resp:?}");
        assert_eq!(resp.estado_registro, "Correcto", "{step}: {resp:?}");
        assert!(resp.codigo_error.is_empty(), "{step}: {resp:?}");
        assert!(!resp.csv.is_empty(), "{step}: no CSV");
    }
}

/// The control that makes «no error code» mean something: the AEAT DOES check the link, and a
/// broken one comes back `AceptadoConErrores` + `2007` (frozen 2026-08-02).
#[test]
fn the_aeat_flags_a_broken_link_so_a_clean_answer_is_a_checked_link() {
    let path = format!(
        "{}/tests/fixtures/alta_2007_aceptado_con_errores_2026-08-02.xml",
        env!("CARGO_MANIFEST_DIR")
    );
    let answer = std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{path}: {e}"));
    let resp = aeat::parse_response(&answer);
    assert_eq!(resp.estado_registro, "AceptadoConErrores", "{resp:?}");
    assert_eq!(resp.codigo_error, "2007", "{resp:?}");
}

/// The frozen consult after the run: the AEAT holds the three records, each with the fingerprint
/// that was sent, and the last one it holds is step `c`.
#[test]
fn the_aeat_holds_the_three_links_after_the_rotation() {
    let held = aeat::parse_consult_response(&fixture("consult.xml")).expect("consult");
    for (step, _) in STEPS {
        let sent = fixture(&format!("{step}_sent.xml"));
        let number = element(&sent, "NumSerieFactura");
        let record = held
            .iter()
            .find(|r| r.invoice_number == number)
            .unwrap_or_else(|| panic!("{step}: the AEAT does not hold {number}"));
        assert_eq!(
            chain::normalize_hash(&record.record_hash),
            own_hash(&sent),
            "{step}: another fingerprint"
        );
    }
    let last = aeat::pick_latest_record(&held).expect("records");
    let c = fixture("c_sent.xml");
    assert_eq!(last.invoice_number, element(&c, "NumSerieFactura"));
}

// ── Live: preproduction, by hand ────────────────────────────────────────────────────────────

fn var(k: &str) -> String {
    std::env::var(k).unwrap_or_else(|_| panic!("missing environment variable {k}"))
}

/// `(path, password)` of the certificate for `kind`.
fn material(kind: &str) -> (String, String) {
    if kind == SEAL {
        (var("ERPLORA_SEAL_P12"), var("GATEWAY_CERT_PASSWORD"))
    } else {
        (
            var("ERPLORA_COMPANY_CERT_P12_PATH"),
            var("ERPLORA_COMPANY_CERT_P12_PASSWORD"),
        )
    }
}

/// A fresh mTLS identity (`reqwest::Identity` is consumed by every post).
fn identity(kind: &str) -> reqwest::Identity {
    let (path, password) = material(kind);
    let der = std::fs::read(&path).expect("could not read the .p12");
    erplora_runtime::certificate::identity_from_der(&der, &password)
        .unwrap_or_else(|e| panic!("the {kind} .p12 does not open: {e}"))
}

/// SHA-256 of the leaf certificate (public: tells the two certificates apart, reveals nothing).
fn certificate_sha256(kind: &str) -> String {
    let (path, password) = material(kind);
    let der = std::fs::read(&path).expect("could not read the .p12");
    let parsed = openssl::pkcs12::Pkcs12::from_der(&der)
        .and_then(|p| p.parse2(&password))
        .expect("the .p12 does not parse");
    let cert = parsed.cert.expect("the .p12 carries no certificate");
    cert.digest(openssl::hash::MessageDigest::sha256())
        .expect("digest")
        .iter()
        .map(|b| format!("{b:02X}"))
        .collect()
}

fn freeze(name: &str, body: &str) {
    let path = fixture_path(name);
    std::fs::write(&path, body).unwrap_or_else(|e| panic!("{path}: {e}"));
}

async fn consult(kind: &str) -> String {
    let now = chrono::Local::now();
    let envelope = aeat::build_consult_soap(
        ISSUER_NIF,
        ISSUER_NAME,
        &now.format("%Y").to_string(),
        &now.format("%m").to_string(),
        None,
    )
    .expect("consult envelope");
    aeat::post_soap(door(kind), identity(kind), &envelope)
        .await
        .expect("the consult must answer 200")
}

#[tokio::test]
#[ignore = "needs the network and both certificates"]
async fn the_chain_survives_a_certificate_change_at_the_aeat() {
    // Chain from what the AEAT holds as the taxpayer's last record, so step `a` pays no 2007.
    let held = aeat::parse_consult_response(&consult(OWN).await).expect("consult refused");
    let anchor = aeat::pick_latest_record(&held).expect("the taxpayer already has records");
    let d: Vec<&str> = anchor.invoice_date.split('-').collect();
    let mut prev = json!({
        "issuer_nif": anchor.issuer_nif,
        "invoice_number": anchor.invoice_number,
        // The consult answers DD-MM-YYYY; `build_soap` expects ISO.
        "invoice_date": format!("{}-{}-{}", d[2], d[1], d[0]),
        "record_hash": chain::normalize_hash(&anchor.record_hash),
    });

    let serial = format!("ROT-{}", chrono::Local::now().format("%Y%m%d-%H%M%S"));
    let mut doors = Vec::new();
    let mut failures = Vec::new();
    for (step, kind) in STEPS {
        let url = door(kind);
        println!("DOOR {step} {kind} {url}");
        let ts = chrono::Local::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, false);
        let record = build_record(
            &format!("{serial}-{step}"),
            &ts,
            prev["record_hash"].as_str().unwrap_or_default(),
        );
        let xml =
            aeat::build_soap(&record, &config(), Some(&prev), "hub-rotation").expect("declarable");
        xsd::validate_registro(&xml).expect("the XSD gate runs before every post");
        freeze(&format!("{step}_sent.xml"), &xml);

        let answer = aeat::post_soap(url, identity(kind), &xml)
            .await
            .expect("the AEAT must answer 200");
        freeze(&format!("{step}.xml"), &answer);
        let resp = aeat::parse_response(&answer);
        println!(
            "[{step}/{kind}] EstadoEnvio={:?} EstadoRegistro={:?} CodigoError={:?} Descripcion={:?} CSV={:?}",
            resp.estado_envio, resp.estado_registro, resp.codigo_error, resp.descripcion_error, resp.csv
        );
        if resp.estado_registro != "Correcto" || !resp.codigo_error.is_empty() {
            failures.push(format!(
                "{step}: {} {} {}",
                resp.estado_registro, resp.codigo_error, resp.descripcion_error
            ));
        }
        doors.push(json!({
            "step": step,
            "certificate_kind": kind,
            "door": url,
            "certificate_sha256": certificate_sha256(kind),
            "csv": resp.csv,
        }));
        if resp.estado_registro != "Incorrecto" {
            prev = link_to(&record);
        }
    }
    freeze(
        "doors.json",
        &format!("{}\n", serde_json::to_string_pretty(&doors).expect("json")),
    );
    freeze("consult.xml", &consult(OWN).await);
    assert!(
        failures.is_empty(),
        "the AEAT did not take every link clean: {failures:#?}"
    );
}
