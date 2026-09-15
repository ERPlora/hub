//! **«Usar mi propio certificado» is a CHOICE, and the certificate stays uploaded** (decision of
//! Ioan, 2026-09-15, amending ADR-0202 §2.4 and ADR-0320 §1).
//!
//! Until now the route was «own if a `.p12` is uploaded, otherwise ERPlora»: a fallback, not an
//! option. The owner of `banco-pre` (PRE) turned the switch off to file through ERPlora's Sello and
//! nothing happened — the switch only navigated, the `.p12` kept signing, and the only way out was
//! deleting the certificate. The two routes are EXCLUSIVE and REVERSIBLE: a hub can hold its `.p12`
//! AND an approved representation grant, and the owner picks which one files.
//!
//! What this file pins, through the runtime's real doors:
//!  - switched OFF, the uploaded `.p12` stays (`present`) but no longer signs: the route is
//!    `delegated` for every reader (`transmission_route`, `status`, `active_kind`);
//!  - switched back ON, it signs again without uploading anything;
//!  - uploading a certificate is choosing it: an upload turns the switch back on;
//!  - it cannot be switched ON with no certificate to use;
//!  - in PRODUCTION it cannot be switched OFF unless ERPlora may really file on the taxpayer's
//!    behalf: an approved (`vigente`) grant AND the enrolled machine identity. In `testing` it can,
//!    so the flow can be tried before the paperwork is done;
//!  - and the go-live asks for the grant on a hub whose certificate is switched off, exactly as on a
//!    hub that never uploaded one.
#![cfg(not(target_os = "android"))]

use erplora_db::testutil::fresh_db;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::certificate::{self, ROUTE_DELEGATED, ROUTE_OWN};
use erplora_runtime::{fiscal_profile, Runtime, RuntimeError};
use serde_json::json;

const HUB: &str = "hub-switch";

/// A hub booted the way the real runtime boots one.
async fn hub() -> Runtime {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt
}

/// The owner's own certificate, written straight into the system table: what the route readers look
/// at is the PRESENCE of the row, and the real writer needs the process-global `HUB_SECRETS_KEY`.
async fn upload_own(db: &dyn DatabaseAdapter) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    db.execute(
        "INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by) \
         VALUES (:hub_id, 'own', 'v1:ciphertext', 'v1:ciphertext', '2026-09-15T13:34:39Z', 'hub_user:owner')",
        &p,
    )
    .await
    .expect("the own certificate is stored");
}

/// The hub's ENROLLED machine identity: the three fields the cell road needs on this side.
async fn enrol_machine_identity(db: &dyn DatabaseAdapter) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert(
        "common_name".into(),
        json!(erplora_runtime::gateway_identity::common_name(HUB)),
    );
    db.execute(
        "INSERT INTO _hub_gateway_identity \
         (hub_id, private_key_pem, certificate_pem, ca_pem, common_name, created_at, updated_at) \
         VALUES (:hub_id, 'v1:ciphertext', '-----BEGIN CERTIFICATE-----\nhub\n-----END CERTIFICATE-----', \
                 '-----BEGIN CERTIFICATE-----\nca\n-----END CERTIFICATE-----', :common_name, \
                 '2026-09-15T09:00:00Z', '2026-09-15T09:00:00Z')",
        &p,
    )
    .await
    .expect("the machine identity is enrolled");
}

/// Puts the fiscal profile in PRODUCTION — the state the go-live leaves behind.
async fn in_production(db: &dyn DatabaseAdapter) {
    fiscal_profile::ensure(db, HUB).await.unwrap();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    db.execute(
        "UPDATE _hub_fiscal_profile SET environment = 'production', status = 'ACTIVE' WHERE hub_id = :hub_id",
        &p,
    )
    .await
    .unwrap();
}

fn code_of(err: &RuntimeError) -> String {
    match err {
        RuntimeError::Domain { code, .. } => code.clone(),
        other => other.to_string(),
    }
}

#[tokio::test]
async fn switched_off_the_uploaded_certificate_stays_but_erplora_files() {
    let rt = hub().await;
    upload_own(rt.db()).await;
    assert_eq!(certificate::transmission_route(rt.db(), HUB).await.unwrap(), ROUTE_OWN);

    rt.set_business_certificate_use(false).await.expect("testing: the owner may switch it off");

    assert_eq!(
        certificate::transmission_route(rt.db(), HUB).await.unwrap(),
        ROUTE_DELEGATED,
        "switched off, the certificate no longer signs"
    );
    assert_eq!(certificate::active_kind(rt.db(), HUB).await.unwrap(), None);
    let status = rt.business_certificate_status().await.unwrap();
    assert_eq!(status["present"], json!(true), "the .p12 is still uploaded: {status}");
    assert_eq!(status["use_for_transmission"], json!(false), "{status}");
    assert_eq!(status["transmission_route"], json!(ROUTE_DELEGATED), "{status}");
    assert_eq!(status["active"], json!(null), "{status}");
}

#[tokio::test]
async fn switched_back_on_it_signs_again_without_uploading_anything() {
    let rt = hub().await;
    upload_own(rt.db()).await;
    rt.set_business_certificate_use(false).await.unwrap();

    rt.set_business_certificate_use(true).await.expect("it is uploaded: it can be used again");

    assert_eq!(certificate::transmission_route(rt.db(), HUB).await.unwrap(), ROUTE_OWN);
    let status = rt.business_certificate_status().await.unwrap();
    assert_eq!(status["use_for_transmission"], json!(true), "{status}");
    assert_eq!(status["transmission_route"], json!(ROUTE_OWN), "{status}");
}

#[tokio::test]
async fn a_certificate_that_was_never_switched_reports_itself_in_use() {
    let rt = hub().await;
    upload_own(rt.db()).await;
    let status = rt.business_certificate_status().await.unwrap();
    assert_eq!(
        status["use_for_transmission"],
        json!(true),
        "every certificate uploaded before the switch existed keeps filing: {status}"
    );
}

#[tokio::test]
async fn it_cannot_be_switched_on_with_no_certificate_uploaded() {
    let rt = hub().await;

    let err = rt
        .set_business_certificate_use(true)
        .await
        .expect_err("there is nothing to use");

    assert_eq!(code_of(&err), certificate::OWN_CERTIFICATE_NOT_UPLOADED);
    assert_eq!(certificate::transmission_route(rt.db(), HUB).await.unwrap(), ROUTE_DELEGATED);
}

#[tokio::test]
async fn in_production_it_is_not_switched_off_without_an_approved_grant() {
    let rt = hub().await;
    upload_own(rt.db()).await;
    enrol_machine_identity(rt.db()).await;
    in_production(rt.db()).await;
    fiscal_profile::record_representation(rt.db(), HUB, "pendiente", "2026-09-13T01:05:56Z")
        .await
        .unwrap();

    let err = rt
        .set_business_certificate_use(false)
        .await
        .expect_err("ERPlora may not file for real on a grant nobody approved");

    assert_eq!(code_of(&err), fiscal_profile::NO_REPRESENTATION);
    assert_eq!(
        certificate::transmission_route(rt.db(), HUB).await.unwrap(),
        ROUTE_OWN,
        "a refused switch leaves the hub filing exactly as before"
    );
}

#[tokio::test]
async fn in_production_it_is_not_switched_off_without_the_enrolled_machine_identity() {
    let rt = hub().await;
    upload_own(rt.db()).await;
    in_production(rt.db()).await;
    fiscal_profile::record_representation(rt.db(), HUB, "vigente", "2026-09-15T09:00:00Z")
        .await
        .unwrap();

    let err = rt
        .set_business_certificate_use(false)
        .await
        .expect_err("with no connection to the fiscal cell the hub would have no road at all");

    assert_eq!(code_of(&err), certificate::GATEWAY_NOT_ENROLLED);
    assert_eq!(certificate::transmission_route(rt.db(), HUB).await.unwrap(), ROUTE_OWN);
}

#[tokio::test]
async fn in_production_with_the_grant_approved_and_the_connection_ready_it_switches_off() {
    let rt = hub().await;
    upload_own(rt.db()).await;
    enrol_machine_identity(rt.db()).await;
    in_production(rt.db()).await;
    fiscal_profile::record_representation(rt.db(), HUB, "vigente", "2026-09-15T09:00:00Z")
        .await
        .unwrap();

    rt.set_business_certificate_use(false).await.expect("everything ERPlora needs is in place");

    assert_eq!(certificate::transmission_route(rt.db(), HUB).await.unwrap(), ROUTE_DELEGATED);
}

#[tokio::test]
async fn in_testing_it_switches_off_before_the_paperwork_is_done() {
    let rt = hub().await;
    upload_own(rt.db()).await;
    fiscal_profile::ensure(rt.db(), HUB).await.unwrap();

    rt.set_business_certificate_use(false)
        .await
        .expect("testing: the owner can try the ERPlora road before the grant is approved");

    assert_eq!(certificate::transmission_route(rt.db(), HUB).await.unwrap(), ROUTE_DELEGATED);
}

#[tokio::test]
async fn deleting_the_certificate_and_uploading_one_again_starts_in_use() {
    let rt = hub().await;
    upload_own(rt.db()).await;
    rt.set_business_certificate_use(false).await.unwrap();

    rt.delete_business_certificate().await.unwrap();
    upload_own(rt.db()).await;

    let status = rt.business_certificate_status().await.unwrap();
    assert_eq!(
        status["use_for_transmission"],
        json!(true),
        "a certificate uploaded now is the one the owner chose: {status}"
    );
    assert_eq!(certificate::transmission_route(rt.db(), HUB).await.unwrap(), ROUTE_OWN);
}

#[tokio::test]
async fn the_go_live_asks_for_the_grant_when_the_certificate_is_switched_off() {
    let rt = hub().await;
    upload_own(rt.db()).await;
    rt.set_business_certificate_use(false).await.unwrap();

    let route = certificate::transmission_route(rt.db(), HUB).await.unwrap();
    assert_eq!(
        route, ROUTE_DELEGATED,
        "the go-live reads this same route: with the certificate off, it is ERPlora's and needs the grant"
    );
}

/// A real, parseable PKCS#12 generated in the test — no `.p12` lives in this repository.
fn generated_pkcs12() -> (String, String) {
    use base64::Engine as _;
    use openssl::asn1::Asn1Time;
    use openssl::hash::MessageDigest;
    use openssl::pkey::PKey;
    use openssl::rsa::Rsa;
    use openssl::x509::{X509NameBuilder, X509};

    let key = PKey::from_rsa(Rsa::generate(2048).unwrap()).unwrap();
    let mut name = X509NameBuilder::new().unwrap();
    name.append_entry_by_text("CN", "ERPlora own-certificate switch fixture")
        .unwrap();
    let name = name.build();
    let mut cert = X509::builder().unwrap();
    cert.set_version(2).unwrap();
    cert.set_subject_name(&name).unwrap();
    cert.set_issuer_name(&name).unwrap();
    cert.set_pubkey(&key).unwrap();
    cert.set_not_before(&Asn1Time::days_from_now(0).unwrap())
        .unwrap();
    cert.set_not_after(&Asn1Time::days_from_now(365).unwrap())
        .unwrap();
    cert.sign(&key, MessageDigest::sha256()).unwrap();
    let cert = cert.build();
    let password = "switch-pw".to_string();
    let der = openssl::pkcs12::Pkcs12::builder()
        .name("erplora")
        .pkey(&key)
        .cert(&cert)
        .build2(&password)
        .unwrap()
        .to_der()
        .unwrap();
    (base64::engine::general_purpose::STANDARD.encode(&der), password)
}

/// `HUB_SECRETS_KEY` once for this binary: the real writer never stores a `.p12` in the clear.
fn ensure_master_key() {
    use base64::Engine as _;
    use std::sync::Once;
    static ONCE: Once = Once::new();
    ONCE.call_once(|| {
        let key = base64::engine::general_purpose::STANDARD.encode([0x5au8; 32]);
        // SAFETY: `Once` runs this before any test reads the variable, and nothing writes it again.
        unsafe { std::env::set_var("HUB_SECRETS_KEY", key) };
    });
}

#[tokio::test]
async fn uploading_a_certificate_over_a_switched_off_one_turns_it_back_on() {
    ensure_master_key();
    let rt = hub().await;
    let (b64, password) = generated_pkcs12();
    rt.set_business_certificate(&b64, &password, "hub_user:owner").await.unwrap();
    rt.set_business_certificate_use(false).await.unwrap();

    // Replacing the `.p12` through the REAL door the screen uses (an upsert on the same row).
    let (b64, password) = generated_pkcs12();
    rt.set_business_certificate(&b64, &password, "hub_user:owner").await.unwrap();

    let status = rt.business_certificate_status().await.unwrap();
    assert_eq!(
        status["use_for_transmission"],
        json!(true),
        "uploading a certificate is choosing it: {status}"
    );
    assert_eq!(certificate::transmission_route(rt.db(), HUB).await.unwrap(), ROUTE_OWN);
}
