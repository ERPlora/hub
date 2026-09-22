//! **hub#1940 — an expired own certificate is not a road to the AEAT.**
//!
//! A business that files with its own certificate can let it expire. Before this, the rule that
//! decides whether a live hub can file (`fiscal_profile::filing_gap`, hub#1935) took the own road
//! as open the moment a certificate was uploaded, and never looked at its `notAfter`: the till kept
//! charging and every record was refused by the AEAT, which does not accept an expired certificate.
//!
//! What this file pins, through the runtime's real doors (the upload door and the core query the
//! TPV reads before charging):
//!  - the upload stores WHEN the certificate expires, next to its bytes, so the rule never has to
//!    decrypt the container on the sale's path;
//!  - a live hub whose own certificate expired is told so with its own stable code;
//!  - renewing the certificate (uploading a valid one) opens the road again;
//!  - a certificate uploaded before the date was stored is read from its container;
//!  - the TPV learns the expiry instant, so it can warn BEFORE the certificate runs out;
//!  - in `testing` nothing stops the till (hub#1934).
#![cfg(not(target_os = "android"))]

use erplora_db::testutil::fresh_db;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::certificate::{self, OWN_CERTIFICATE_EXPIRED};
use erplora_runtime::{fiscal_profile, RequestContext, Runtime};
use serde_json::json;

const HUB: &str = "hub-own-expiry";

/// The secrets key `set_business_certificate` refuses to store a container without (ADR-0016).
fn ensure_master_key() {
    use base64::Engine as _;
    use std::sync::Once;
    static ONCE: Once = Once::new();
    ONCE.call_once(|| {
        let key = base64::engine::general_purpose::STANDARD.encode([0x47u8; 32]);
        // SAFETY: `Once` runs this before any test of this binary touches the variable, and
        // nothing here ever writes it again.
        unsafe { std::env::set_var("HUB_SECRETS_KEY", key) };
    });
}

/// A real, parseable PKCS#12 whose certificate expires `valid_for_secs` from now (negative: it
/// already expired). Returns `(base64, password, notAfter as the RFC 3339 instant it really is)`.
fn pkcs12_expiring_in(valid_for_secs: i64) -> (String, String, String) {
    use base64::Engine as _;
    use openssl::asn1::Asn1Time;
    use openssl::hash::MessageDigest;
    use openssl::pkey::PKey;
    use openssl::rsa::Rsa;
    use openssl::x509::{X509NameBuilder, X509};

    let now = chrono::Utc::now().timestamp();
    let not_after_unix = now + valid_for_secs;
    let key = PKey::from_rsa(Rsa::generate(2048).unwrap()).unwrap();
    let mut name = X509NameBuilder::new().unwrap();
    name.append_entry_by_text("CN", "hub1940 test").unwrap();
    let name = name.build();

    let mut cert = X509::builder().unwrap();
    cert.set_version(2).unwrap();
    cert.set_subject_name(&name).unwrap();
    cert.set_issuer_name(&name).unwrap();
    cert.set_pubkey(&key).unwrap();
    cert.set_not_before(&Asn1Time::from_unix(now - 400 * 86_400).unwrap())
        .unwrap();
    cert.set_not_after(&Asn1Time::from_unix(not_after_unix).unwrap())
        .unwrap();
    cert.sign(&key, MessageDigest::sha256()).unwrap();
    let cert = cert.build();

    let password = "hub1940-pw".to_string();
    let der = openssl::pkcs12::Pkcs12::builder()
        .name("erplora")
        .pkey(&key)
        .cert(&cert)
        .build2(&password)
        .unwrap()
        .to_der()
        .unwrap();
    let instant = chrono::DateTime::from_timestamp(not_after_unix, 0)
        .unwrap()
        .format("%Y-%m-%dT%H:%M:%SZ")
        .to_string();
    (
        base64::engine::general_purpose::STANDARD.encode(&der),
        password,
        instant,
    )
}

const A_YEAR: i64 = 365 * 86_400;
const A_DAY_AGO: i64 = -86_400;

async fn hub() -> Runtime {
    ensure_master_key();
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt
}

/// Puts the fiscal profile in PRODUCTION — the state the go-live leaves behind.
async fn in_production(db: &dyn DatabaseAdapter) {
    fiscal_profile::ensure(db, HUB).await.unwrap();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    db.execute(
        "UPDATE _hub_fiscal_profile SET environment = 'production', status = 'ACTIVE' \
         WHERE hub_id = :hub_id",
        &p,
    )
    .await
    .unwrap();
}

async fn upload(rt: &Runtime, valid_for_secs: i64) -> String {
    let (b64, password, not_after) = pkcs12_expiring_in(valid_for_secs);
    rt.set_business_certificate(&b64, &password, "hub_user:owner")
        .await
        .expect("the owner uploads their certificate");
    not_after
}

/// What `hub.fiscal.transmission` — the core query the TPV reads before charging — says.
async fn transmission(rt: &Runtime) -> serde_json::Value {
    let rows = rt
        .execute_query(
            "hub.fiscal.transmission",
            &Params::new(),
            &RequestContext::new(HUB, "u1", ["*".to_string()]),
        )
        .await
        .expect("the core answers hub.fiscal.transmission");
    rows[0].clone()
}

async fn stored_not_after(db: &dyn DatabaseAdapter) -> String {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    let rows = db
        .query(
            "SELECT not_after FROM _hub_certificate WHERE hub_id = :hub_id AND kind = 'own'",
            &p,
        )
        .await
        .unwrap()
        .rows;
    rows[0]["not_after"]
        .as_str()
        .unwrap_or_default()
        .to_string()
}

/// The upload writes the instant the certificate expires, in the same row as its bytes.
#[tokio::test]
async fn the_upload_stores_when_the_certificate_expires() {
    let rt = hub().await;

    let expected = upload(&rt, A_YEAR).await;

    assert_eq!(stored_not_after(rt.db()).await, expected);
    assert_eq!(
        certificate::signing_not_after(rt.db(), HUB).await.unwrap(),
        Some(expected)
    );
}

/// 🔴 **The case the issue names.** A live hub signing with an expired own certificate: the till
/// learns, before charging, the code the dispatcher refuses the sale with.
#[tokio::test]
async fn a_live_hub_whose_own_certificate_expired_is_told_so() {
    let rt = hub().await;
    in_production(rt.db()).await;
    let not_after = upload(&rt, A_DAY_AGO).await;

    let answer = transmission(&rt).await;

    assert_eq!(
        answer["transmission_route"],
        json!(certificate::ROUTE_OWN),
        "{answer}"
    );
    assert_eq!(
        answer["filing_blocked"],
        json!(OWN_CERTIFICATE_EXPIRED),
        "{answer}"
    );
    assert_eq!(
        answer["own_certificate_expires_at"],
        json!(not_after),
        "{answer}"
    );
}

/// Renewing is uploading a valid certificate: the road opens again with nothing else to do.
#[tokio::test]
async fn renewing_the_certificate_opens_the_road_again() {
    let rt = hub().await;
    in_production(rt.db()).await;
    upload(&rt, A_DAY_AGO).await;
    assert_eq!(
        transmission(&rt).await["filing_blocked"],
        json!(OWN_CERTIFICATE_EXPIRED)
    );

    let renewed = upload(&rt, A_YEAR).await;

    let answer = transmission(&rt).await;
    assert_eq!(answer["filing_blocked"], json!(""), "{answer}");
    assert_eq!(
        answer["own_certificate_expires_at"],
        json!(renewed),
        "{answer}"
    );
}

/// A valid certificate blocks nothing, and the TPV still learns WHEN it runs out: that is what
/// lets it warn the owner days before instead of the morning it stops charging.
#[tokio::test]
async fn a_valid_certificate_blocks_nothing_and_says_when_it_runs_out() {
    let rt = hub().await;
    in_production(rt.db()).await;
    let not_after = upload(&rt, 5 * 86_400).await;

    let answer = transmission(&rt).await;

    assert_eq!(answer["filing_blocked"], json!(""), "{answer}");
    assert_eq!(
        answer["own_certificate_expires_at"],
        json!(not_after),
        "{answer}"
    );
}

/// A certificate uploaded before the date was stored (`''`) is read from its own container: those
/// hubs are exactly the ones whose certificate is oldest, so they cannot be the blind spot.
#[tokio::test]
async fn a_certificate_stored_before_its_date_was_is_read_from_its_container() {
    let rt = hub().await;
    in_production(rt.db()).await;
    let not_after = upload(&rt, A_DAY_AGO).await;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    rt.db()
        .execute(
            "UPDATE _hub_certificate SET not_after = '' WHERE hub_id = :hub_id",
            &p,
        )
        .await
        .unwrap();

    let answer = transmission(&rt).await;

    assert_eq!(
        answer["filing_blocked"],
        json!(OWN_CERTIFICATE_EXPIRED),
        "{answer}"
    );
    assert_eq!(
        answer["own_certificate_expires_at"],
        json!(not_after),
        "{answer}"
    );
}

/// Switched off, the expired `.p12` signs nothing: the hub is on ERPlora's road and its expiry is
/// neither a block nor something to warn about.
#[tokio::test]
async fn a_switched_off_expired_certificate_is_not_what_signs() {
    let rt = hub().await;
    upload(&rt, A_DAY_AGO).await;
    rt.set_business_certificate_use(false)
        .await
        .expect("testing: the owner may switch it off");
    in_production(rt.db()).await;

    let answer = transmission(&rt).await;

    assert_eq!(
        answer["transmission_route"],
        json!(certificate::ROUTE_DELEGATED),
        "{answer}"
    );
    assert_ne!(
        answer["filing_blocked"],
        json!(OWN_CERTIFICATE_EXPIRED),
        "{answer}"
    );
    assert_eq!(answer["own_certificate_expires_at"], json!(""), "{answer}");
}

/// In `testing` nothing stops the till (hub#1934) — but the date still travels, so the warning
/// shows up while the business is trying things out.
#[tokio::test]
async fn in_testing_an_expired_certificate_blocks_nothing() {
    let rt = hub().await;
    fiscal_profile::ensure(rt.db(), HUB).await.unwrap();
    let not_after = upload(&rt, A_DAY_AGO).await;

    let answer = transmission(&rt).await;

    assert_eq!(answer["filing_blocked"], json!(""), "{answer}");
    assert_eq!(
        answer["own_certificate_expires_at"],
        json!(not_after),
        "{answer}"
    );
}
