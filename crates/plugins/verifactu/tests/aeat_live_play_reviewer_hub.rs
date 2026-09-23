//! The hub Google Play reviews the app with (`restaurante-demo-play`, hub#1884) sends its tickets
//! to the AEAT **preproduction** and nowhere else.
//!
//! That hub is a production hub whose business is a demo. A ticket the reviewer charges there must
//! reach the AEAT (rule of 2026-09-19: every ticket with a QR reaches it), and it must reach the
//! TEST AEAT: a real remission of a business that does not exist is exactly what the reviewer's
//! hub can never do.
//!
//! It was seeded with the test taxpayer `12345678Z` («Salon Aurora SL»). Posted to the AEAT
//! preproduction with the Sello, that identity is refused in the header with Fault `4104` (the
//! obligado is not in the census): every ticket of the reviewer would have died there. The hub now
//! carries the demo identity (`settings::DEMO_BUSINESS_TAX_ID`, hub#985) — the only obligado the
//! Sello presents in testing — and its first ticket is taken.
//!
//! Two layers:
//!
//! - **Offline, in every suite.** `fixtures/play_reviewer_config_2026-09-23.json` is the
//!   `verifactu.config.get` answer of that hub, saved on 2026-09-23 through its own API. The tests
//!   read it and fail if its environment, or either door the hub can use (its own certificate or
//!   the gateway's seal), would resolve to production, and read back both AEAT answers.
//! - **Live, by hand (`#[ignore]`).** One ticket with the exact shape of the reviewer's first
//!   sale (F2, 29,90 € at 21 %) is posted for each identity with the Sello de Entidad — what the
//!   gateway presents with — through [`preproduction_door`]. The answers are frozen in
//!   `fixtures/play_reviewer_{seeded_,}{sent,answer}_2026-09-23.xml`.
//!
//! ```sh
//! ERPLORA_SEAL_P12=…/sello-A.p12 GATEWAY_CERT_PASSWORD=… \
//!   cargo test -p erplora-verifactu --test aeat_live_play_reviewer_hub -- --ignored --nocapture
//! ```
use erplora_verifactu::{aeat, chain, xsd};
use serde_json::json;

type Json = serde_json::Value;

/// The day the reviewer hub's configuration and the AEAT answer were frozen.
const EVIDENCE_DAY: &str = "2026-09-23";

/// The certificate kinds a hub can transmit with: its own `.p12`, or the gateway's seal.
/// `"seal"` is the crate-private `SEAL_TYPE`.
const DOORS: [&str; 2] = ["own", "seal"];

/// The kind the reviewer hub really uses: it has no certificate of its own, so the gateway
/// transmits for it with the Sello de Entidad.
const GATEWAY_KIND: &str = "seal";

/// ERPlora, the software producer (`SistemaInformatico`), as in every other rehearsal.
const PRODUCER_NIF: &str = "B27593136";
const PRODUCER_NAME: &str = "ERPLORA CLOUD SL";

/// Hosts the reviewer hub may reach. Nothing else.
const PREPRODUCTION_HOSTS: [&str; 2] = ["https://prewww1.aeat.es/", "https://prewww10.aeat.es/"];

/// `answer.xml` → `tests/fixtures/play_reviewer_answer_2026-09-23.xml`.
fn fixture_path(name: &str) -> String {
    let (stem, ext) = name
        .rsplit_once('.')
        .expect("fixture names carry an extension");
    format!(
        "{}/tests/fixtures/play_reviewer_{stem}_{EVIDENCE_DAY}.{ext}",
        env!("CARGO_MANIFEST_DIR")
    )
}

fn fixture(name: &str) -> String {
    let path = fixture_path(name);
    std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{path}: {e}"))
}

/// The reviewer hub's saved VeriFactu configuration, as its API answered it.
fn reviewer_config() -> Json {
    serde_json::from_str(&fixture("config.json")).expect("the frozen config is JSON")
}

/// Panics unless `url` is an AEAT **preproduction** host.
fn assert_preproduction(url: &str) {
    assert!(
        PREPRODUCTION_HOSTS.iter().any(|h| url.starts_with(h)),
        "hub#1884: the Play reviewer's hub only talks to AEAT preproduction, refused {url}"
    );
}

/// The door the reviewer hub reaches with `kind`, checked before it is used.
fn preproduction_door(kind: &str) -> &'static str {
    let environment = reviewer_config()["environment"]
        .as_str()
        .unwrap_or_default()
        .to_owned();
    let url = aeat::endpoint(&environment, kind);
    assert_preproduction(url);
    url
}

// ── Offline: runs in every suite ────────────────────────────────────────────────────────────

/// 🔴 The hard condition. Saving the reviewer hub as `production`, or `aeat::endpoint` sending
/// either door of `testing` to a production host, turns this red.
#[test]
fn the_play_reviewer_hub_only_ever_reaches_preproduction() {
    let config = reviewer_config();
    assert_eq!(config["environment"], "testing");
    assert_eq!(
        config["issuer_nif"],
        erplora_runtime::settings::DEMO_BUSINESS_TAX_ID,
        "the reviewer hub must carry the one obligado the Sello presents in testing"
    );
    assert_eq!(
        preproduction_door("own"),
        "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
    );
    assert_eq!(
        preproduction_door("seal"),
        "https://prewww10.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
    );
}

/// The guard is not decorative: it refuses the production door of every kind.
#[test]
fn the_play_reviewer_door_guard_refuses_production() {
    for kind in DOORS {
        let production = aeat::endpoint("production", kind);
        let refused = std::panic::catch_unwind(|| assert_preproduction(production));
        assert!(refused.is_err(), "the guard let {production} through");
    }
}

// ── The ticket the live rehearsal posts ─────────────────────────────────────────────────────

fn rehearsal_config() -> Json {
    let config = reviewer_config();
    json!({
        "software_name": PRODUCER_NAME,
        "software_nif": PRODUCER_NIF,
        "environment": config["environment"],
        "producer_facts": {
            "NombreRazon": PRODUCER_NAME,
            "NIF": PRODUCER_NIF,
            "NombreSistemaInformatico": config["software_name"],
            "IdSistemaInformatico": config["software_id"],
            "TipoUsoPosibleSoloVerifactu": "S",
            "TipoUsoPosibleMultiOT": "S",
            "IndicadorMultiplesOT": "N",
        },
    })
}

/// `(NIF, legal name)` of an obligado.
type Issuer<'a> = (&'a str, &'a str);

/// The identity the reviewer hub was seeded with, refused by the AEAT (`4104`).
const SEEDED: Issuer<'static> = ("12345678Z", "Salon Aurora SL");

/// The identity the reviewer hub carries now, as its saved config answers it.
fn current() -> (String, String) {
    let config = reviewer_config();
    let text = |key: &str| config[key].as_str().unwrap_or_default().to_owned();
    (text("issuer_nif"), text("issuer_name"))
}

/// The reviewer's first ticket (`TICKET-2026-000001`): F2, 24,71 € base + 5,19 € VAT = 29,90 €.
/// Amounts in CENTS (ADR-0007).
fn build_record(issuer: Issuer<'_>, invoice_number: &str, ts: &str, previous_hash: &str) -> Json {
    let (issuer_nif, issuer_name) = issuer;
    let (base, tax) = (2471_i64, 519_i64);
    let total = base + tax;
    let date = &ts[..10];
    let hash = chain::alta_hash(
        issuer_nif,
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
        "issuer_nif": issuer_nif,
        "issuer_name": issuer_name,
        "invoice_number": invoice_number,
        "invoice_date": date,
        "invoice_type": "F2",
        "description": format!("Play reviewer hub rehearsal {invoice_number}"),
        "base_amount": base,
        "tax_rate": 21.0,
        "tax_breakdown": r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.00,"base":2471,"quota":519}]"#,
        "tax_amount": tax,
        "total_amount": total,
        "record_hash": hash,
        "previous_hash": previous_hash,
        "is_first_record": if previous_hash.is_empty() { 1 } else { 0 },
        "generation_timestamp": ts,
    })
}

/// What the rehearsal builds passes the XSD gate and carries the reviewer hub's issuer.
#[test]
fn the_play_reviewer_ticket_is_declarable() {
    let (nif, name) = current();
    let record = build_record(
        (&nif, &name),
        "PLAY-REHEARSAL-1",
        "2026-09-23T21:00:00+02:00",
        "",
    );
    let xml = aeat::build_soap(&record, &rehearsal_config(), None, "hub-play-reviewer")
        .expect("declarable");
    xsd::validate_registro(&xml).expect("XSD gate");
    assert!(
        xml.contains(&format!("<sum1:NIF>{nif}</sum1:NIF>")),
        "{xml}"
    );
}

/// Why the identity changed: the AEAT preproduction refused the seeded one in the header, so not
/// one of the reviewer's tickets could have been registered.
#[test]
fn the_aeat_refused_the_seeded_identity_with_4104() {
    let sent = fixture("seeded_sent.xml");
    assert!(sent.contains("<sum1:NIF>12345678Z</sum1:NIF>"));
    let answer = fixture("seeded_answer.xml");
    assert!(answer.contains("<faultstring>Codigo[4104]"), "{answer}");
}

/// The AEAT preproduction took the reviewer hub's ticket under its current identity.
#[test]
fn the_aeat_took_the_play_reviewer_ticket() {
    let (nif, _) = current();
    assert!(fixture("sent.xml").contains(&format!("<sum1:NIF>{nif}</sum1:NIF>")));
    let resp = aeat::parse_response(&fixture("answer.xml"));
    assert!(
        resp.estado_registro == "Correcto" || resp.estado_registro == "AceptadoConErrores",
        "the AEAT did not register it: {resp:?}"
    );
    assert!(
        !resp.csv.is_empty(),
        "a registered submission carries a CSV: {resp:?}"
    );
}

// ── Live: preproduction, by hand ────────────────────────────────────────────────────────────

fn var(k: &str) -> String {
    std::env::var(k).unwrap_or_else(|_| panic!("missing environment variable {k}"))
}

/// A fresh mTLS identity of the Sello de Entidad (`reqwest::Identity` is consumed per post).
fn seal_identity() -> reqwest::Identity {
    let der = std::fs::read(var("ERPLORA_SEAL_P12")).expect("could not read the seal .p12");
    erplora_runtime::certificate::identity_from_der(&der, &var("GATEWAY_CERT_PASSWORD"))
        .unwrap_or_else(|e| panic!("the seal .p12 does not open: {e}"))
}

fn freeze(name: &str, body: &str) {
    let path = fixture_path(name);
    std::fs::write(&path, body).unwrap_or_else(|e| panic!("{path}: {e}"));
}

/// Posts the reviewer's ticket for `issuer` and freezes what was sent and answered under
/// `{prefix}sent.xml` / `{prefix}answer.xml`.
async fn post(issuer: Issuer<'_>, prefix: &str) -> aeat::AeatResponse {
    let url = preproduction_door(GATEWAY_KIND);
    println!("DOOR {GATEWAY_KIND} {url} issuer={}", issuer.0);
    let serial = format!("PLAY-{}", chrono::Local::now().format("%Y%m%d-%H%M%S"));
    let ts = chrono::Local::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, false);
    let record = build_record(issuer, &serial, &ts, "");
    let xml = aeat::build_soap(&record, &rehearsal_config(), None, "hub-play-reviewer")
        .expect("declarable");
    xsd::validate_registro(&xml).expect("the XSD gate runs before every post");
    freeze(&format!("{prefix}sent.xml"), &xml);
    let answer = aeat::post_soap(url, seal_identity(), &xml)
        .await
        .expect("the AEAT must answer 200");
    freeze(&format!("{prefix}answer.xml"), &answer);
    let resp = aeat::parse_response(&answer);
    println!("{prefix}answer: {resp:?} fault={answer}");
    resp
}

#[tokio::test]
#[ignore = "needs the network and the Sello de Entidad"]
async fn the_play_reviewer_ticket_reaches_the_test_aeat() {
    post(SEEDED, "seeded_").await;
    let (nif, name) = current();
    let resp = post((&nif, &name), "").await;
    assert!(
        resp.estado_registro == "Correcto" || resp.estado_registro == "AceptadoConErrores",
        "the AEAT did not register the reviewer's ticket: {resp:?}"
    );
}
