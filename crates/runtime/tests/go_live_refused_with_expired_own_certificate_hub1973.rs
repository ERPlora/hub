//! **hub#1973 — the go-live refuses an own certificate that already expired.**
//!
//! A business that files with its own certificate pressed «Go live» with that certificate past its
//! `notAfter`: the hub froze its identity and switched to `production`, and the owner only found out
//! at the first sale, which the TPV refused with `fiscal.own_certificate_expired` (hub#1940). The
//! AEAT does not accept an expired certificate, so that go-live opened a road that did not exist.
//!
//! What this file pins, through the runtime's real doors (the upload and the go-live):
//!  - `READY` on the own road with an expired certificate → the go-live answers the SAME code the
//!    till answers, and nothing is frozen: the profile stays in `testing` and `READY`, with no activation instant;
//!  - the positive control: the same hub with a certificate still valid goes live;
//!  - renewing the certificate (uploading a valid one) opens the go-live again;
//!  - an expiry the hub cannot read blocks nothing, as in hub#1940;
//!  - on ERPlora's road (own certificate switched off) the own certificate's expiry is not asked:
//!    that road is decided by the grant, not by a certificate that does not sign.
#![cfg(not(target_os = "android"))]

use erplora_db::testutil::fresh_db;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::certificate::OWN_CERTIFICATE_EXPIRED;
use erplora_runtime::fiscal_profile::{self, FiscalStatus, ENV_PRODUCTION, ENV_TESTING};
use erplora_runtime::{Runtime, RuntimeError};
use serde_json::json;

const HUB: &str = "hub-go-live-expired";

/// The secrets key `set_business_certificate` refuses to store a container without (ADR-0016).
fn ensure_master_key() {
    use base64::Engine as _;
    use std::sync::Once;
    static ONCE: Once = Once::new();
    ONCE.call_once(|| {
        let key = base64::engine::general_purpose::STANDARD.encode([0x73u8; 32]);
        // SAFETY: `Once` runs this before any test of this binary touches the variable, and
        // nothing here ever writes it again.
        unsafe { std::env::set_var("HUB_SECRETS_KEY", key) };
    });
}

/// A real, parseable PKCS#12 whose certificate expires `valid_for_secs` from now (negative: it
/// already expired). Returns `(base64, password)`.
fn pkcs12_expiring_in(valid_for_secs: i64) -> (String, String) {
    use base64::Engine as _;
    use openssl::asn1::Asn1Time;
    use openssl::hash::MessageDigest;
    use openssl::pkey::PKey;
    use openssl::rsa::Rsa;
    use openssl::x509::{X509NameBuilder, X509};

    let now = chrono::Utc::now().timestamp();
    let key = PKey::from_rsa(Rsa::generate(2048).unwrap()).unwrap();
    let mut name = X509NameBuilder::new().unwrap();
    name.append_entry_by_text("CN", "hub1973 test").unwrap();
    let name = name.build();

    let mut cert = X509::builder().unwrap();
    cert.set_version(2).unwrap();
    cert.set_subject_name(&name).unwrap();
    cert.set_issuer_name(&name).unwrap();
    cert.set_pubkey(&key).unwrap();
    cert.set_not_before(&Asn1Time::from_unix(now - 400 * 86_400).unwrap())
        .unwrap();
    cert.set_not_after(&Asn1Time::from_unix(now + valid_for_secs).unwrap())
        .unwrap();
    cert.sign(&key, MessageDigest::sha256()).unwrap();
    let cert = cert.build();

    let password = "hub1973-pw".to_string();
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

const A_YEAR: i64 = 365 * 86_400;
const A_DAY_AGO: i64 = -86_400;

async fn hub() -> Runtime {
    ensure_master_key();
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt
}

async fn upload(rt: &Runtime, valid_for_secs: i64) {
    let (b64, password) = pkcs12_expiring_in(valid_for_secs);
    rt.set_business_certificate(&b64, &password, "hub_user:owner")
        .await
        .expect("the owner uploads their certificate");
}

/// Puts the profile where the checklist leaves it when everything is gathered: `READY`, in
/// `testing`.
async fn ready(db: &dyn DatabaseAdapter) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    fiscal_profile::ensure(db, HUB).await.unwrap();
    db.execute(
        "UPDATE _hub_fiscal_profile SET status = 'READY' WHERE hub_id = :hub_id",
        &p,
    )
    .await
    .unwrap();
}

async fn profile(db: &dyn DatabaseAdapter) -> fiscal_profile::FiscalProfile {
    fiscal_profile::ensure(db, HUB).await.unwrap()
}

fn domain_code(err: RuntimeError) -> String {
    match err {
        RuntimeError::Domain { code, .. } => code,
        other => panic!("expected a domain refusal, got {other:?}"),
    }
}

/// 🔴 **The case the issue names.** `READY` on the own road, certificate expired: the go-live says
/// what the till would say at the first sale, and freezes nothing.
#[tokio::test]
async fn the_go_live_refuses_an_expired_own_certificate_and_freezes_nothing() {
    let rt = hub().await;
    upload(&rt, A_DAY_AGO).await;
    ready(rt.db()).await;

    let err = rt
        .fiscal_go_live()
        .await
        .expect_err("an expired own certificate is not a road to the AEAT");

    assert_eq!(domain_code(err), OWN_CERTIFICATE_EXPIRED);
    let after = profile(rt.db()).await;
    assert_eq!(after.environment, ENV_TESTING, "nothing may reach the real AEAT");
    assert_eq!(after.status, FiscalStatus::Ready);
    assert_eq!(after.activated_at, "", "the go-live froze nothing");
}

/// The positive control: the same hub, with a certificate that is still valid, goes live.
#[tokio::test]
async fn a_valid_own_certificate_goes_live() {
    let rt = hub().await;
    upload(&rt, A_YEAR).await;
    ready(rt.db()).await;

    let live = rt.fiscal_go_live().await.expect("a valid own certificate goes live");

    assert_eq!(live.status, FiscalStatus::Active);
    assert_eq!(live.environment, ENV_PRODUCTION);
    assert!(!live.activated_at.is_empty());
}

/// Renewing — uploading a valid certificate over the expired one — opens the go-live again.
#[tokio::test]
async fn renewing_the_certificate_opens_the_go_live_again() {
    let rt = hub().await;
    upload(&rt, A_DAY_AGO).await;
    ready(rt.db()).await;
    assert!(rt.fiscal_go_live().await.is_err());

    upload(&rt, A_YEAR).await;
    ready(rt.db()).await;

    let live = rt.fiscal_go_live().await.expect("the renewed certificate goes live");
    assert_eq!(live.environment, ENV_PRODUCTION);
}

/// An expiry the hub cannot read is not a date, and blocks nothing — the rule of hub#1940.
#[tokio::test]
async fn an_unreadable_expiry_does_not_block_the_go_live() {
    let rt = hub().await;
    upload(&rt, A_DAY_AGO).await;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    rt.db()
        .execute(
            "UPDATE _hub_certificate SET not_after = 'not-a-date' WHERE hub_id = :hub_id",
            &p,
        )
        .await
        .unwrap();
    ready(rt.db()).await;

    let live = rt
        .fiscal_go_live()
        .await
        .expect("an unknown expiry is not an expired certificate");
    assert_eq!(live.environment, ENV_PRODUCTION);
}

/// On ERPlora's road (own certificate switched off, grant approved) the expired own certificate
/// signs nothing, so the go-live does not ask about it: that road is the grant's (hub#817).
#[tokio::test]
async fn on_erploras_road_the_own_certificate_expiry_is_not_asked() {
    let rt = hub().await;
    upload(&rt, A_DAY_AGO).await;
    rt.set_business_certificate_use(false).await.unwrap();
    ready(rt.db()).await;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert("vigente".into(), json!(fiscal_profile::REPRESENTATION_VIGENTE));
    rt.db()
        .execute(
            "UPDATE _hub_fiscal_profile SET representation_status = :vigente \
             WHERE hub_id = :hub_id",
            &p,
        )
        .await
        .unwrap();

    let live = rt
        .fiscal_go_live()
        .await
        .expect("ERPlora files with the grant: the own certificate's expiry is not its business");
    assert_eq!(live.environment, ENV_PRODUCTION);
}
