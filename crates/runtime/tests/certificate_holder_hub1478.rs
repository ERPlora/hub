//! hub#1478 — **whose is the certificate that signs?**, read from the bytes the hub actually holds.
//!
//! ADR-0268 §4 makes the `Representante` block hang off ONE question: *is the HOLDER of the
//! signing certificate the same as the `IDEmisorFactura`?* If they differ, the block is emitted
//! **with the holder's identity, read from the container**, never from a constant and never from
//! the slot.
//!
//! hub#1460 shipped the half the hub could answer: through the fiscal cell the holder is whoever
//! the control plane SIGNED into the token, because the hub never sees that Sello. On the own
//! road it assumed the holder *is* the obligado — true for the business that uploaded its own
//! certificate, and **false for a gestoría** that uploads its own to file for its client. There
//! the block must be emitted, and until this primitive existed there was nowhere to read the
//! identity from.
//!
//! # The order is load-bearing, and it is where this gets silently wrong
//!
//! A Spanish *certificado de representante* carries **two** identifiers in its subject: the
//! natural person's document in `serialNumber` (2.5.4.5) and the ENTITY's tax id in
//! `organizationIdentifier` (2.5.4.97). Reading `serialNumber` first would file every record under
//! a private individual's DNI. The same rule, in the same order, is what the fiscal cell already
//! applies to its own Sello (`verifactu-gateway/src/certificate.rs::holder_nif_of`,
//! `verifactu-gateway#8`) — this is the hub's half of it, not a second answer to one question.
//!
//! Every certificate here is generated in the test: no `.p12` lives in this repository.
#![cfg(not(target_os = "android"))]

use erplora_db::testutil::fresh_db;
use erplora_runtime::certificate::{self, CertificateHolder};
use erplora_runtime::native::{DbHost, NativeHost};
use erplora_runtime::Runtime;

const HUB: &str = "hub-test";

/// The gestoría that files for its client: what a real `own` container of a third party looks
/// like from the subject's point of view.
const GESTORIA_NIF: &str = "B99999999";
const GESTORIA_NAME: &str = "GESTORIA MARTINEZ SL";
/// The natural person the certificate hangs off — their DNI is what `serialNumber` carries, and
/// filing under it is the mistake the order exists to prevent.
const EMPLOYEE_DNI: &str = "12345678Z";

/// One subject entry, as OpenSSL takes it: a short name (`O`, `serialNumber`) or a dotted OID for
/// the attributes the binding has no constant for.
type Entry<'a> = (&'a str, &'a str);

/// A real, parseable PKCS#12 whose subject carries exactly `entries`. Returns `(base64, password)`.
fn pkcs12_with_subject(entries: &[Entry<'_>]) -> (String, String) {
    use base64::Engine as _;
    use openssl::asn1::Asn1Time;
    use openssl::hash::MessageDigest;
    use openssl::pkey::PKey;
    use openssl::rsa::Rsa;
    use openssl::x509::{X509NameBuilder, X509};

    let key = PKey::from_rsa(Rsa::generate(2048).unwrap()).unwrap();
    let mut name = X509NameBuilder::new().unwrap();
    name.append_entry_by_text("CN", "hub1478 test").unwrap();
    for (attribute, value) in entries {
        name.append_entry_by_text(attribute, value).unwrap();
    }
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

    let password = "hub1478-pw".to_string();
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

/// The secrets key `set_business_certificate` refuses to store a container without (ADR-0016): a
/// `.p12` is never persisted in the clear, not even by a test.
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

fn holder_of(entries: &[Entry<'_>]) -> Option<CertificateHolder> {
    use base64::Engine as _;
    let (b64, password) = pkcs12_with_subject(entries);
    let der = base64::engine::general_purpose::STANDARD
        .decode(&b64)
        .unwrap();
    certificate::holder_from_der(&der, &password).unwrap()
}

/// 🔴 **The case the issue is about, and the order that makes it right.** A representative
/// certificate of a gestoría: the entity in `organizationIdentifier`, the employee's DNI in
/// `serialNumber`. The holder is the ENTITY — reading the other one first would declare a private
/// individual as the representative of somebody else's invoices.
#[test]
fn the_holder_is_the_entity_not_the_person_in_the_serial_number_hub1478() {
    let holder = holder_of(&[
        ("O", GESTORIA_NAME),
        ("serialNumber", &format!("IDCES-{EMPLOYEE_DNI}")),
        ("2.5.4.97", &format!("VATES-{GESTORIA_NIF}")),
    ])
    .expect("a subject naming an organisation names a holder");

    assert_eq!(
        holder,
        CertificateHolder {
            nif: GESTORIA_NIF.to_owned(),
            name: GESTORIA_NAME.to_owned(),
        },
        "the entity identifier wins over the natural person's document"
    );
    assert_ne!(
        holder.nif, EMPLOYEE_DNI,
        "filing under the employee's DNI is the defect the order prevents"
    );
}

/// The ETSI EN 319 412-1 §5.1.4 semantics prefix says WHICH REGISTER the number comes from, not
/// which number it is, so it is stripped. A bare NIF — which plenty of containers carry — has to
/// compare identical to a prefixed one, or the same holder would look like two.
#[test]
fn the_etsi_semantics_prefix_is_stripped_hub1478() {
    let prefixed = holder_of(&[
        ("O", GESTORIA_NAME),
        ("2.5.4.97", &format!("VATES-{GESTORIA_NIF}")),
    ]);
    let bare = holder_of(&[("O", GESTORIA_NAME), ("2.5.4.97", GESTORIA_NIF)]);

    assert_eq!(prefixed, bare, "prefixed and bare are the same holder");
    assert_eq!(prefixed.unwrap().nif, GESTORIA_NIF);

    // The other registers of the same clause, so the list is not one entry wide by accident.
    for prefix in ["NTRES", "PASES", "IDCES", "PNOES", "TINES"] {
        let holder = holder_of(&[
            ("O", GESTORIA_NAME),
            ("2.5.4.97", &format!("{prefix}-{GESTORIA_NIF}")),
        ])
        .expect("a prefixed identifier still names a holder");
        assert_eq!(holder.nif, GESTORIA_NIF, "`{prefix}-` must be stripped too");
    }
}

/// A seal that puts the entity's tax id in `serialNumber` and carries no
/// `organizationIdentifier` — the fallback, and the only case where `serialNumber` is read.
#[test]
fn the_serial_number_is_the_fallback_when_nothing_else_names_the_entity_hub1478() {
    let holder = holder_of(&[
        ("O", GESTORIA_NAME),
        ("serialNumber", &format!("VATES-{GESTORIA_NIF}")),
    ])
    .expect("a seal that only carries serialNumber still names its holder");

    assert_eq!(holder.nif, GESTORIA_NIF);
}

/// 🔒 **Absence concludes nothing.** A subject that names no holder answers `None`, which leaves
/// the caller exactly where it was before this primitive existed — no block, today's behaviour.
/// Guessing a holder out of a `CN` (`"APELLIDO APELLIDO NOMBRE - NIF 12345678Z"`, as FNMT writes
/// it for a natural person) would declare somebody who is not the representative, and a wrong
/// `Representante` is worse than none: a fiscal record cannot be un-filed (ADR-0189).
#[test]
fn a_subject_that_names_no_holder_concludes_nothing_hub1478() {
    assert_eq!(holder_of(&[("O", GESTORIA_NAME)]), None);
    assert_eq!(holder_of(&[]), None);
}

/// 🔒 **Half an identity is not an identity.** The block needs NIF *and* razón social; a container
/// that states one without the other is not completed with a guess.
#[test]
fn a_holder_without_a_name_is_never_half_declared_hub1478() {
    assert_eq!(
        holder_of(&[("2.5.4.97", &format!("VATES-{GESTORIA_NIF}"))]),
        None,
        "an identifier with no organisation name declares nobody"
    );
}

/// The whole hand-off, through the REAL host the fiscal engine asks: the owner uploads a
/// container through the product's own door and the module reads the holder back. A hand-written
/// stand-in host would be a second implementation of the question under test — the exact shape of
/// #317/#318/#319/#470.
#[tokio::test]
async fn the_host_answers_the_holder_of_the_certificate_that_signs_hub1478() {
    ensure_master_key();
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();

    let (b64, password) = pkcs12_with_subject(&[
        ("O", GESTORIA_NAME),
        ("serialNumber", &format!("IDCES-{EMPLOYEE_DNI}")),
        ("2.5.4.97", &format!("VATES-{GESTORIA_NIF}")),
    ]);
    rt.set_business_certificate(&b64, &password, "hub_user:admin")
        .await
        .unwrap();

    let host = DbHost {
        db: rt.db(),
        storage: None,
        hub_id: HUB,
        module_id: "verifactu",
        static_folder: None,
    };
    assert_eq!(
        host.certificate_holder(HUB).await.unwrap(),
        Some(CertificateHolder {
            nif: GESTORIA_NIF.to_owned(),
            name: GESTORIA_NAME.to_owned(),
        }),
    );
}

/// A hub holding no certificate at all answers `None` — the default every host inherits, and the
/// state of every hub that files through the cell.
#[tokio::test]
async fn a_hub_without_a_certificate_has_no_holder_hub1478() {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();

    let host = DbHost {
        db: rt.db(),
        storage: None,
        hub_id: HUB,
        module_id: "verifactu",
        static_folder: None,
    };
    assert_eq!(host.certificate_holder(HUB).await.unwrap(), None);
}
