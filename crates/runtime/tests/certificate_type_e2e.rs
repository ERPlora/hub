//! hub#470 — the AEAT entry point follows **what the certificate is**, end to end
//! (ADR-0202 §2.1).
//!
//! The chain this file walks is the one that broke: the control plane installs a container in the
//! `delegated` slot → the core classifies it → `DbHost` answers the module → `read_config` puts the
//! answer in the config → `aeat::endpoint` turns it into a URL. Four hand-offs across two crates,
//! and the family of defects this issue belongs to (#317 the wrong slot, #318 the wrong date
//! format, #319 who signed, #470 what it is) is always the same shape: **one certificate fact
//! crossing a seam and being read differently on each side.** A test that stops at any one of those
//! hand-offs cannot see it.
//!
//! # The case that matters
//!
//! ERPlora invoices today with a **representative** certificate (`ERPlora_Cloud__R__B27593136_.p12`
//! — the `(R)`). hub#320 chose the entry point from the SLOT, so the day that container were
//! uploaded to the control plane, every delegated hub in the fleet would have POSTed to `www10` and
//! the AEAT would have rejected **all** of their records — one at a time, with nothing to warn
//! anybody, and a rejection is not a link in the chain (ADR-0189), so each one is corrected by hand.
//!
//! Every certificate here is generated in the test. No `.p12` lives in this repository, and least
//! of all the real one: it is the private key ERPlora identifies itself with before the tax agency.
#![cfg(not(target_os = "android"))]

use erplora_db::testutil::fresh_db;
use erplora_runtime::certificate::{self, CertificateKind, CertificateType};
use erplora_runtime::native::DbHost;
use erplora_runtime::Runtime;

const HOLDER_DOOR: &str = "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP";
const SEAL_DOOR: &str = "https://prewww10.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP";

const HUB: &str = "hub-test";

/// Which eIDAS `QcType` the generated certificate declares — the standard statement (ETSI EN
/// 319 412-5) a qualified certificate carries to say what it is for.
enum QcType {
    /// `0.4.0.1862.1.6.2` — an **eSeal**: the certificate belongs to a legal person. This is what a
    /// *Sello de Entidad* is, and the only thing that opens the AEAT's `www10` door.
    ESeal,
    /// `0.4.0.1862.1.6.1` — an **eSign** for a natural person: the taxpayer or their representative.
    ESign,
}

/// A real, parseable PKCS#12 declaring `qc_type`. Returns `(base64, password)`.
fn pkcs12(qc_type: QcType) -> (String, String) {
    use base64::Engine as _;
    use openssl::asn1::{Asn1Object, Asn1OctetString, Asn1Time};
    use openssl::hash::MessageDigest;
    use openssl::pkey::PKey;
    use openssl::rsa::Rsa;
    use openssl::x509::{X509Extension, X509NameBuilder, X509};

    let type_oid: &[u8] = match qc_type {
        QcType::ESeal => &[0x06, 0x07, 0x04, 0x00, 0x8E, 0x46, 0x01, 0x06, 0x02],
        QcType::ESign => &[0x06, 0x07, 0x04, 0x00, 0x8E, 0x46, 0x01, 0x06, 0x01],
    };
    // `qcStatements` ::= SEQUENCE OF QCStatement; QCStatement ::= { statementId, statementInfo }.
    // One statement: id-etsi-qcs-QcType (0.4.0.1862.1.6), info = SEQUENCE OF the type OID above.
    let mut statement = vec![0x06u8, 0x06, 0x04, 0x00, 0x8E, 0x46, 0x01, 0x06];
    statement.extend_from_slice(&der_sequence(type_oid));
    let extension_value = der_sequence(&der_sequence(&statement));

    let key = PKey::from_rsa(Rsa::generate(2048).unwrap()).unwrap();
    let mut name = X509NameBuilder::new().unwrap();
    name.append_entry_by_text("CN", "ERPlora hub470 fixture").unwrap();
    let name = name.build();

    let mut cert = X509::builder().unwrap();
    cert.set_version(2).unwrap();
    cert.set_subject_name(&name).unwrap();
    cert.set_issuer_name(&name).unwrap();
    cert.set_pubkey(&key).unwrap();
    cert.set_not_before(&Asn1Time::days_from_now(0).unwrap()).unwrap();
    cert.set_not_after(&Asn1Time::days_from_now(365).unwrap()).unwrap();
    let oid = Asn1Object::from_str("1.3.6.1.5.5.7.1.3").unwrap();
    let value = Asn1OctetString::new_from_bytes(&extension_value).unwrap();
    cert.append_extension(X509Extension::new_from_der(&oid, false, &value).unwrap())
        .unwrap();
    cert.sign(&key, MessageDigest::sha256()).unwrap();
    let cert = cert.build();

    let password = "e2e-pw".to_string();
    let der = openssl::pkcs12::Pkcs12::builder()
        .name("erplora")
        .pkey(&key)
        .cert(&cert)
        .build2(&password)
        .unwrap()
        .to_der()
        .unwrap();
    (
        base64::engine::general_purpose::STANDARD.encode(&der),
        password,
    )
}

/// Wraps DER contents in a SEQUENCE (short form only — these are small test certificates).
fn der_sequence(contents: &[u8]) -> Vec<u8> {
    let mut out = vec![0x30u8, contents.len() as u8];
    out.extend_from_slice(contents);
    out
}

/// Sets `HUB_SECRETS_KEY` once for this test binary. The core is fail-closed on purpose (hub#114):
/// without a master key nothing is ever written in the clear, so a test that goes through the REAL
/// writers — which is the whole point of this file — needs one.
///
/// One value for the whole binary, so no lock: every test here wants the same key and none of them
/// unsets it. (`crates/runtime/src/secret_box.rs`'s `test_support` serialises instead, because the
/// unit tests there DO need to see the variable missing.)
fn ensure_master_key() {
    use base64::Engine as _;
    use std::sync::Once;
    static ONCE: Once = Once::new();
    ONCE.call_once(|| {
        let key = base64::engine::general_purpose::STANDARD.encode([0x47u8; 32]);
        // SAFETY: `Once` runs this before any test touches the variable, and nothing here ever
        // writes it again.
        unsafe { std::env::set_var("HUB_SECRETS_KEY", key) };
    });
}

/// A hub booted the way the real runtime boots one — baseline plus the versioned system
/// migrations, including the v21 that adds `certificate_type`.
async fn hub() -> Runtime {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    // The verifactu module's own table, which `read_config` reads. Left EMPTY on purpose: a hub that
    // has not configured anything is in `testing`, so every URL here is a preproduction one and no
    // test can accidentally assert against the real tax agency's host.
    rt.db()
        .execute_batch(
            "CREATE TABLE verifactu_config (\
               hub_id TEXT NOT NULL, environment TEXT NOT NULL DEFAULT 'testing', \
               is_deleted INTEGER NOT NULL DEFAULT 0);",
        )
        .await
        .unwrap();
    rt
}

/// The URL the fiscal engine would POST to right now, resolved the way the engine resolves it.
///
/// Asked through the runtime's REAL host (`DbHost`), never a hand-written stand-in: a twin host
/// would be a second implementation of the question under test, which is exactly how the two
/// readings of «which certificate?» drifted apart in #317 and #318.
async fn entry_point(rt: &Runtime) -> &'static str {
    let host = DbHost {
        db: rt.db(),
        storage: None,
        hub_id: HUB,
        module_id: "verifactu",
        static_folder: None,
    };
    erplora_verifactu::transmission_endpoint_for(&host, HUB).await.unwrap()
}

/// 🔴 **The bug.** A representative container in the DELEGATED slot must transmit through the
/// holder's door. Routing on the slot sent it to the seal's, and every record of every delegated
/// hub would have come back rejected.
#[tokio::test]
async fn a_representative_certificate_in_the_delegated_slot_uses_the_holder_door() {
    ensure_master_key();
    let rt = hub().await;
    let (b64, password) = pkcs12(QcType::ESign);

    certificate::set_delegated(rt.db(), HUB, &b64, &password, 4, Some("representative"))
        .await
        .unwrap();

    assert_eq!(
        certificate::active_kind(rt.db(), HUB).await.unwrap(),
        Some(CertificateKind::Delegated),
        "the slot is unchanged — it is still ERPlora's certificate"
    );
    assert_eq!(entry_point(&rt).await, HOLDER_DOOR);
}

/// The half hub#320 got right, kept: a real entity seal in that slot reaches the seal's door, and
/// it does so all the way through the two crates.
#[tokio::test]
async fn an_entity_seal_in_the_delegated_slot_uses_the_seal_door() {
    ensure_master_key();
    let rt = hub().await;
    let (b64, password) = pkcs12(QcType::ESeal);

    certificate::set_delegated(rt.db(), HUB, &b64, &password, 4, Some("seal")).await.unwrap();

    assert_eq!(entry_point(&rt).await, SEAL_DOOR);
}

/// **The mirror nobody could reach before**: a business that uploads its OWN entity seal in
/// Ajustes → Negocio reaches the seal's door too. Under hub#320 the `own` slot meant «holder», full
/// stop, so that business would have been rejected by the AEAT with a perfectly valid certificate.
#[tokio::test]
async fn a_business_that_uploads_its_own_seal_uses_the_seal_door() {
    ensure_master_key();
    let rt = hub().await;
    let (b64, password) = pkcs12(QcType::ESeal);

    // The REAL door the owner's upload comes through (`PUT /api/business/certificate`), not a
    // hand-written write into the table: the type has to be derived by the writer the product uses.
    rt.set_business_certificate(&b64, &password, "hub_user:admin").await.unwrap();

    assert_eq!(
        certificate::active_kind(rt.db(), HUB).await.unwrap(),
        Some(CertificateKind::Own)
    );
    assert_eq!(entry_point(&rt).await, SEAL_DOOR);
}

/// 🔒 **A hub that cannot vouch for its certificate keeps the holder's door.** This is every hub
/// deployed before v21 whose row has no type and whose container says nothing — and `prewww1` is
/// exactly where all of them already went, so nothing moves under them.
#[tokio::test]
async fn a_certificate_that_declares_nothing_keeps_the_holder_door() {
    ensure_master_key();
    let rt = hub().await;
    // "DELEGATED-PKCS12" — bytes that are not a PKCS#12 at all, which is the strongest form of
    // «the hub cannot tell»: it cannot even open the container.
    certificate::set_delegated(rt.db(), HUB, "REVMRUdBVEVELVBLQ1MxMg==", "pw", 4, None)
        .await
        .unwrap();

    assert_eq!(certificate::active_type(rt.db(), HUB).await.unwrap(), None);
    assert_eq!(entry_point(&rt).await, HOLDER_DOOR);
}

/// 🔒 **A declaration the container contradicts is refused, and the hub keeps signing with what it
/// had.** The loud, recoverable failure: the door does not move, the fleet does not break, and the
/// operator gets a line naming both values.
#[tokio::test]
async fn a_contested_declaration_is_refused_and_the_hub_keeps_its_certificate() {
    ensure_master_key();
    let rt = hub().await;
    let (seal_b64, seal_pw) = pkcs12(QcType::ESeal);
    certificate::set_delegated(rt.db(), HUB, &seal_b64, &seal_pw, 4, Some("seal")).await.unwrap();

    let (representative_b64, representative_pw) = pkcs12(QcType::ESign);
    let err = certificate::set_delegated(
        rt.db(),
        HUB,
        &representative_b64,
        &representative_pw,
        5,
        Some("seal"),
    )
    .await
    .unwrap_err()
    .to_string();
    assert!(err.contains("seal") && err.contains("representative"), "{err}");

    assert_eq!(
        certificate::delegated_version(rt.db(), HUB).await.unwrap(),
        Some(4),
        "the working certificate is untouched"
    );
    assert_eq!(entry_point(&rt).await, SEAL_DOOR);
}

/// The type the core reports and the type the engine routes on are the SAME answer, in every state.
/// Two readings of one fact is how #317/#318/#319 each broke; this pins them together.
#[tokio::test]
async fn the_core_and_the_engine_never_disagree_about_the_type() {
    ensure_master_key();
    let rt = hub().await;

    for (qc_type, expected_type, expected_door) in [
        (QcType::ESeal, Some(CertificateType::Seal), SEAL_DOOR),
        (
            QcType::ESign,
            Some(CertificateType::Representative),
            HOLDER_DOOR,
        ),
    ] {
        let (b64, password) = pkcs12(qc_type);
        certificate::set_delegated(rt.db(), HUB, &b64, &password, 9, None).await.unwrap();
        assert_eq!(certificate::active_type(rt.db(), HUB).await.unwrap(), expected_type);
        assert_eq!(entry_point(&rt).await, expected_door);
    }
}
