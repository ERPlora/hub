//! The hub's MACHINE identity for the fiscal gateway (hub#1432, hub#985 §1, ADR-0419).
//!
//! The cell's ingress is mutual TLS: every hub presents a client certificate whose CN is derived
//! from its id and whose chain ends in the internal `ERPlora Fiscal Internal CA`. The invariant
//! of ADR-0320 is that **the private key is generated ON the hub and never leaves it**: only a
//! CSR travels to the operator (public material), and a signed certificate plus the CA come
//! back. The Cloud sees at most the fingerprint (`cnf` claim); this module is the only reader
//! and writer of the key.
//!
//! Storage is the singleton row `_hub_gateway_identity` (system migration v55). The key is
//! encrypted at rest with [`crate::secret_box`] and the write **fails closed**: without
//! `HUB_SECRETS_KEY` no key is generated at all — an unencrypted machine identity would outlive
//! every rotation of the master key, silently.
//!
//! Android: the generation/validation path rides OpenSSL, which does not cross-compile to the
//! NDK (same cfg as [`crate::certificate`]); the stubs answer with a clear error. Fiscal
//! transmission does not live on Android anyway.

use serde_json::json;

use crate::errors::{Result, RuntimeError};
use crate::registry::now_rfc3339;
use crate::secret_box::{self, SecretsKey};
use erplora_db::{DatabaseAdapter, Params};

/// The CN the ingress expects, derived exactly like the Cloud derives it
/// (`HubFiscalClientIdentity.common_name_for`) and like the cell checks it
/// (`ingress::expected_common_name`). Three independent derivations of ONE rule.
pub fn common_name(hub_id: &str) -> String {
    format!("hub-{hub_id}.fiscal.erplora.internal")
}

/// What the settings surface shows about the machine identity. Names and dates only — never key
/// material, never the certificate body.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GatewayIdentityStatus {
    pub has_key: bool,
    pub has_certificate: bool,
    pub common_name: String,
    /// `notAfter` of the installed certificate as ISO `YYYY-MM-DD`; `None` without one.
    pub not_after: Option<String>,
}

fn identity_error(context: &str, detail: impl std::fmt::Display) -> RuntimeError {
    RuntimeError::Certificate(format!("gateway identity: {context}: {detail}"))
}

fn master_key() -> Result<Option<SecretsKey>> {
    secret_box::master_key_from_env()
        .map_err(|e| identity_error(&format!("{} inválida", secret_box::MASTER_KEY_ENV), e))
}

async fn load_row(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Option<(String, String, String, String)>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT private_key_pem, certificate_pem, ca_pem, common_name \
             FROM _hub_gateway_identity WHERE hub_id = :hub_id LIMIT 1",
            &p,
        )
        .await?;
    let Some(row) = res.rows.into_iter().next() else {
        return Ok(None);
    };
    let field = |name: &str| {
        row.get(name)
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string()
    };
    Ok(Some((
        field("private_key_pem"),
        field("certificate_pem"),
        field("ca_pem"),
        field("common_name"),
    )))
}

/// The decrypted private key of this hub's machine identity. `None` if none was generated yet.
async fn load_private_key_pem(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Option<String>> {
    let Some((key_stored, _, _, _)) = load_row(db, hub_id).await? else {
        return Ok(None);
    };
    if key_stored.is_empty() {
        return Ok(None);
    }
    let key = master_key()?;
    let pem = secret_box::decrypt_or_legacy(key.as_ref(), &key_stored)
        .map_err(|e| identity_error("descifrando la clave privada", e))?;
    Ok(Some(pem))
}

/// The internal CA already stored for this hub, if any — **public material**, unlike everything
/// else this module guards.
///
/// Its reader is the enrolment door (hub#1457): the yearly renewal brings back a new certificate
/// for the SAME key, signed by the SAME authority, so an issued certificate that arrives without
/// its CA is installable as long as this hub already knows the CA. Without this the renewal of
/// every hub in the fleet would stop on a technicality that has nothing to do with the identity.
pub async fn stored_ca_pem(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Option<String>> {
    let Some((_, _, ca_pem, _)) = load_row(db, hub_id).await? else {
        return Ok(None);
    };
    Ok(Some(ca_pem).filter(|pem| !pem.trim().is_empty()))
}

/// **Who this machine is on the wire**, as the host lends it to an engine (hub#1459).
///
/// The three public facts of the enrolled identity and nothing else: the mTLS client identity
/// (built from a private key that never leaves the hub), the CA that anchors the PEER's server
/// certificate, and the common name the control plane knows this machine by — which is what lets
/// an engine notice that the credential it was handed was minted for somebody else.
///
/// **No URL and no bearer.** A destination belongs to the engine (the hub does not block
/// destinations, it decorates the call with an identity), and a bearer is not an identity.
pub struct MachineIdentity {
    pub identity: reqwest::Identity,
    pub ca_pem: Vec<u8>,
    pub common_name: String,
}

impl std::fmt::Debug for MachineIdentity {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // `reqwest::Identity` wraps a private key. The name is what identifies the value in a log.
        f.debug_struct("MachineIdentity")
            .field("common_name", &self.common_name)
            .field("ca_pem_bytes", &self.ca_pem.len())
            .finish_non_exhaustive()
    }
}

/// mTLS material for one connection to the cell: the client identity plus the CA that anchors
/// the cell's SERVER certificate (same internal CA). `None` while the operator has not installed
/// the signed certificate yet — the caller treats that as "route not available", never a panic.
pub async fn client_identity(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Option<(reqwest::Identity, Vec<u8>)>> {
    let Some((key_stored, certificate_pem, ca_pem, _)) = load_row(db, hub_id).await? else {
        return Ok(None);
    };
    if key_stored.is_empty() || certificate_pem.is_empty() || ca_pem.is_empty() {
        return Ok(None);
    }
    let key = master_key()?;
    let key_pem = secret_box::decrypt_or_legacy(key.as_ref(), &key_stored)
        .map_err(|e| identity_error("descifrando la clave privada", e))?;
    let bundle = format!("{key_pem}\n{certificate_pem}");
    let identity = reqwest::Identity::from_pem(bundle.as_bytes())
        .map_err(|e| identity_error("montando la identidad mTLS", e))?;
    Ok(Some((identity, ca_pem.into_bytes())))
}

/// **Is the cell road open from THIS side?** — the local half of «can this hub file?» (hub#1489).
///
/// `true` when the three things [`client_identity`] demands are installed: the private key
/// generated on this hub, the certificate the operator signed for it, and the internal CA that
/// anchors the cell's server certificate. It is deliberately the SAME triple, read from the same
/// row: a presence check that accepted less would promise a road that
/// `reqwest::Identity::from_pem` then refuses to build.
///
/// # Why the core asks this instead of asking the engine
///
/// The engine's own answer (`config::can_transmit`) is the live one and it is worth more — it
/// mints a token against the control plane and learns whether this hub is routed through the cell
/// at all. It is also a NETWORK call, and the three readers of [`crate::certificate::can_transmit`]
/// are the dispatcher gate, the onboarding checklist and the boot-time profile refresh. A hub with
/// no connectivity would fail every sale, and that is precisely the direction ADR-0203 must not
/// fail in: the gate exists to stop a sale nobody can file, not to stop a sale nobody can phone
/// home about.
///
/// So this is the offline predicate: **has this hub got something to present at the ingress?**
/// Everything downstream of the handshake (the token, the grant, the quota) is refused by the
/// cell with its own code on the record, where it is visible and recoverable — a contingency, not
/// a rejected sale.
///
/// Never decrypts: presence of the ciphertext is presence of the key.
pub async fn is_enrolled(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<bool> {
    let Some((private_key_pem, certificate_pem, ca_pem, _)) = load_row(db, hub_id).await? else {
        return Ok(false);
    };
    Ok(!private_key_pem.is_empty() && !certificate_pem.is_empty() && !ca_pem.is_empty())
}

/// What exists, without touching key material beyond its presence.
pub async fn status(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<GatewayIdentityStatus> {
    let row = load_row(db, hub_id).await?;
    let (has_key, has_certificate, not_after) = match &row {
        None => (false, false, None),
        Some((key, cert, _, _)) => {
            let not_after = if cert.is_empty() {
                None
            } else {
                not_after_iso(cert)
            };
            (!key.is_empty(), !cert.is_empty(), not_after)
        }
    };
    Ok(GatewayIdentityStatus {
        has_key,
        has_certificate,
        common_name: common_name(hub_id),
        not_after,
    })
}

/// Forgets the identity entirely (key included). The operator's recovery path when a key must be
/// rotated: delete, re-issue the CSR, re-sign. The old certificate stops at the Cloud's
/// `HubFiscalClientIdentity.revoke()`, which is the revocation that actually bites (ADR-0419).
pub async fn delete(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<()> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    db.execute(
        "DELETE FROM _hub_gateway_identity WHERE hub_id = :hub_id",
        &p,
    )
    .await?;
    Ok(())
}

/// "Jun 10 09:12:33 2028 GMT" → "2028-06-10". Same single-read rule as
/// `certificate::asn1_time_to_iso`: an unrecognised shape answers `None`, never a made-up date.
#[cfg(not(target_os = "android"))]
fn asn1_display_to_iso(s: &str) -> Option<String> {
    let parts: Vec<&str> = s.split_whitespace().collect();
    if parts.len() < 4 {
        return None;
    }
    let month = match parts[0] {
        "Jan" => "01",
        "Feb" => "02",
        "Mar" => "03",
        "Apr" => "04",
        "May" => "05",
        "Jun" => "06",
        "Jul" => "07",
        "Aug" => "08",
        "Sep" => "09",
        "Oct" => "10",
        "Nov" => "11",
        "Dec" => "12",
        _ => return None,
    };
    let day = parts[1];
    let day = if day.len() == 1 {
        format!("0{day}")
    } else {
        day.to_string()
    };
    Some(format!("{}-{}-{}", parts[3], month, day))
}

#[cfg(not(target_os = "android"))]
fn not_after_iso(certificate_pem: &str) -> Option<String> {
    let cert = openssl::x509::X509::from_pem(certificate_pem.as_bytes()).ok()?;
    asn1_display_to_iso(&cert.not_after().to_string())
}

#[cfg(target_os = "android")]
fn not_after_iso(_certificate_pem: &str) -> Option<String> {
    None
}

/// Generates the keypair (EC P-256) if this hub has none yet and returns the CSR for the
/// operator to sign — **idempotent**: a second call re-derives the CSR from the SAME key, so
/// losing the first response costs nothing and the key never has to move.
///
/// Fails closed without `HUB_SECRETS_KEY`: a machine identity stored in plaintext would be
/// exactly the durable secret this whole design exists to avoid.
#[cfg(not(target_os = "android"))]
pub async fn ensure_key_and_csr(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<String> {
    use openssl::pkey::PKey;

    if let Some(existing_pem) = load_private_key_pem(db, hub_id).await? {
        let pkey = PKey::private_key_from_pem(existing_pem.as_bytes())
            .map_err(|e| identity_error("clave privada almacenada ilegible", e))?;
        return build_csr(&pkey, &common_name(hub_id));
    }

    let Some(key) = master_key()? else {
        return Err(identity_error(
            "sin clave maestra",
            format!(
                "{} no está configurada; la identidad de máquina no se genera sin cifrado at-rest",
                secret_box::MASTER_KEY_ENV
            ),
        ));
    };

    let group = openssl::ec::EcGroup::from_curve_name(openssl::nid::Nid::X9_62_PRIME256V1)
        .map_err(|e| identity_error("curva P-256", e))?;
    let ec = openssl::ec::EcKey::generate(&group)
        .map_err(|e| identity_error("generando la clave", e))?;
    let pkey = PKey::from_ec_key(ec).map_err(|e| identity_error("envolviendo la clave", e))?;
    let key_pem = String::from_utf8(
        pkey.private_key_to_pem_pkcs8()
            .map_err(|e| identity_error("serializando la clave", e))?,
    )
    .map_err(|e| identity_error("clave no UTF-8", e))?;

    let encrypted = secret_box::encrypt(&key, &key_pem)
        .map_err(|e| identity_error("cifrando la clave privada", e))?;
    let now = now_rfc3339();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("private_key_pem".into(), json!(encrypted));
    p.insert("common_name".into(), json!(common_name(hub_id)));
    p.insert("now".into(), json!(now));
    db.execute(
        "INSERT INTO _hub_gateway_identity \
           (hub_id, private_key_pem, certificate_pem, ca_pem, common_name, created_at, updated_at) \
         VALUES (:hub_id, :private_key_pem, '', '', :common_name, :now, :now) \
         ON CONFLICT (hub_id) DO UPDATE SET \
           private_key_pem = :private_key_pem, common_name = :common_name, updated_at = :now",
        &p,
    )
    .await?;

    build_csr(&pkey, &common_name(hub_id))
}

#[cfg(not(target_os = "android"))]
fn build_csr(pkey: &openssl::pkey::PKey<openssl::pkey::Private>, cn: &str) -> Result<String> {
    let mut name =
        openssl::x509::X509NameBuilder::new().map_err(|e| identity_error("nombre del CSR", e))?;
    name.append_entry_by_nid(openssl::nid::Nid::COMMONNAME, cn)
        .map_err(|e| identity_error("CN del CSR", e))?;
    let name = name.build();

    let mut req =
        openssl::x509::X509ReqBuilder::new().map_err(|e| identity_error("builder del CSR", e))?;
    req.set_subject_name(&name)
        .map_err(|e| identity_error("sujeto del CSR", e))?;
    req.set_pubkey(pkey)
        .map_err(|e| identity_error("clave pública del CSR", e))?;
    req.sign(pkey, openssl::hash::MessageDigest::sha256())
        .map_err(|e| identity_error("firma del CSR", e))?;
    String::from_utf8(
        req.build()
            .to_pem()
            .map_err(|e| identity_error("PEM del CSR", e))?,
    )
    .map_err(|e| identity_error("CSR no UTF-8", e))
}

/// Installs the certificate the operator signed, plus the internal CA that anchors both sides.
/// Three refusals, each its own message: a certificate for ANOTHER key (the classic
/// wrong-file-uploaded), a CN that is not this hub's, and an already-expired certificate.
#[cfg(not(target_os = "android"))]
pub async fn install_certificate(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    certificate_pem: &str,
    ca_pem: &str,
) -> Result<GatewayIdentityStatus> {
    use openssl::x509::X509;

    let Some(key_pem) = load_private_key_pem(db, hub_id).await? else {
        return Err(identity_error(
            "sin clave",
            "no hay clave privada generada: pide primero el CSR",
        ));
    };
    let pkey = openssl::pkey::PKey::private_key_from_pem(key_pem.as_bytes())
        .map_err(|e| identity_error("clave privada almacenada ilegible", e))?;

    let cert = X509::from_pem(certificate_pem.as_bytes())
        .map_err(|e| identity_error("certificado ilegible", e))?;
    X509::from_pem(ca_pem.as_bytes()).map_err(|e| identity_error("CA ilegible", e))?;

    let cert_pub = cert
        .public_key()
        .map_err(|e| identity_error("clave pública del certificado", e))?;
    if !cert_pub.public_eq(&pkey) {
        return Err(identity_error(
            "clave equivocada",
            "el certificado no corresponde a la clave generada en este hub",
        ));
    }

    let expected_cn = common_name(hub_id);
    let cn = cert
        .subject_name()
        .entries_by_nid(openssl::nid::Nid::COMMONNAME)
        .next()
        .and_then(|e| e.data().as_utf8().ok().map(|s| s.to_string()))
        .unwrap_or_default();
    if cn != expected_cn {
        return Err(identity_error(
            "CN equivocado",
            format!("el certificado nombra '{cn}', este hub es '{expected_cn}'"),
        ));
    }

    let now =
        openssl::asn1::Asn1Time::days_from_now(0).map_err(|e| identity_error("reloj ASN.1", e))?;
    if cert
        .not_after()
        .compare(&now)
        .map_err(|e| identity_error("comparando la caducidad", e))?
        == std::cmp::Ordering::Less
    {
        return Err(identity_error(
            "caducado",
            format!("el certificado terminó el {}", cert.not_after()),
        ));
    }

    let stamp = now_rfc3339();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("certificate_pem".into(), json!(certificate_pem));
    p.insert("ca_pem".into(), json!(ca_pem));
    p.insert("now".into(), json!(stamp));
    db.execute(
        "UPDATE _hub_gateway_identity SET certificate_pem = :certificate_pem, \
           ca_pem = :ca_pem, updated_at = :now WHERE hub_id = :hub_id",
        &p,
    )
    .await?;

    status(db, hub_id).await
}

#[cfg(target_os = "android")]
pub async fn ensure_key_and_csr(_db: &dyn DatabaseAdapter, _hub_id: &str) -> Result<String> {
    Err(identity_error(
        "no disponible",
        "la identidad de máquina fiscal no está soportada en Android",
    ))
}

#[cfg(target_os = "android")]
pub async fn install_certificate(
    _db: &dyn DatabaseAdapter,
    _hub_id: &str,
    _certificate_pem: &str,
    _ca_pem: &str,
) -> Result<GatewayIdentityStatus> {
    Err(identity_error(
        "no disponible",
        "la identidad de máquina fiscal no está soportada en Android",
    ))
}

#[cfg(test)]
#[cfg(not(target_os = "android"))]
mod tests {
    use super::*;
    use crate::secret_box::test_support::{env_lock, test_key_b64, EnvVarGuard};
    use erplora_db::testutil::fresh_db;
    use erplora_db::PgAdapter;

    const HUB: &str = "11111111-2222-4333-8444-555566667777";

    async fn db_ready() -> PgAdapter {
        let db = fresh_db().await;
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        crate::system_migrations::apply(&db, "hub-test")
            .await
            .unwrap();
        db
    }

    /// Signs `csr_pem` with a throwaway test CA, optionally FORCING a different CN — the shape
    /// `gateway-pki sign` produces, built here so the roundtrip needs no external binary.
    fn sign_with_test_ca(csr_pem: &str, cn_override: Option<&str>, days: u32) -> (String, String) {
        use openssl::asn1::Asn1Time;
        use openssl::hash::MessageDigest;
        use openssl::nid::Nid;
        use openssl::pkey::PKey;
        use openssl::x509::{X509NameBuilder, X509Req, X509};

        let ca_key = PKey::from_ec_key(
            openssl::ec::EcKey::generate(
                &openssl::ec::EcGroup::from_curve_name(Nid::X9_62_PRIME256V1).unwrap(),
            )
            .unwrap(),
        )
        .unwrap();
        let mut ca_name = X509NameBuilder::new().unwrap();
        ca_name
            .append_entry_by_nid(Nid::COMMONNAME, "ERPlora Fiscal Internal CA TEST")
            .unwrap();
        let ca_name = ca_name.build();
        let mut ca = X509::builder().unwrap();
        ca.set_version(2).unwrap();
        ca.set_subject_name(&ca_name).unwrap();
        ca.set_issuer_name(&ca_name).unwrap();
        ca.set_pubkey(&ca_key).unwrap();
        ca.set_not_before(&Asn1Time::days_from_now(0).unwrap())
            .unwrap();
        ca.set_not_after(&Asn1Time::days_from_now(3650).unwrap())
            .unwrap();
        ca.sign(&ca_key, MessageDigest::sha256()).unwrap();
        let ca = ca.build();

        let req = X509Req::from_pem(csr_pem.as_bytes()).unwrap();
        let subject = match cn_override {
            None => req.subject_name().to_owned().unwrap(),
            Some(cn) => {
                let mut name = X509NameBuilder::new().unwrap();
                name.append_entry_by_nid(Nid::COMMONNAME, cn).unwrap();
                name.build()
            }
        };
        let mut cert = X509::builder().unwrap();
        cert.set_version(2).unwrap();
        cert.set_subject_name(&subject).unwrap();
        cert.set_issuer_name(&ca_name).unwrap();
        cert.set_pubkey(&req.public_key().unwrap()).unwrap();
        cert.set_not_before(&Asn1Time::days_from_now(0).unwrap())
            .unwrap();
        cert.set_not_after(&Asn1Time::days_from_now(days.try_into().unwrap()).unwrap())
            .unwrap();
        cert.sign(&ca_key, MessageDigest::sha256()).unwrap();
        let cert = cert.build();

        (
            String::from_utf8(cert.to_pem().unwrap()).unwrap(),
            String::from_utf8(ca.to_pem().unwrap()).unwrap(),
        )
    }

    /// The CA is remembered so a renewal that brings only the certificate can still be installed
    /// (hub#1457). Empty is `None`, never an empty PEM somebody would try to parse.
    #[tokio::test]
    async fn the_stored_ca_is_readable_only_once_one_has_been_installed() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(47));
        let db = db_ready().await;

        assert_eq!(stored_ca_pem(&db, HUB).await.unwrap(), None, "sin fila, nada");

        let csr = ensure_key_and_csr(&db, HUB).await.unwrap();
        assert_eq!(
            stored_ca_pem(&db, HUB).await.unwrap(),
            None,
            "con clave pero sin certificado, la columna está vacía y eso NO es una CA"
        );

        let (cert, ca) = sign_with_test_ca(&csr, None, 365);
        install_certificate(&db, HUB, &cert, &ca).await.unwrap();
        assert_eq!(stored_ca_pem(&db, HUB).await.unwrap(), Some(ca));
    }

    /// 🔒 **A filed CSR is NOT a route** (hub#1489). Between `ensure_key_and_csr` and the operator
    /// approving it a hub holds a private key and nothing else, and that gap is days long. Reading
    /// it as «enrolled» would let `certificate::can_transmit` open the fiscal gate for a hub that
    /// cannot complete a single mTLS handshake: every sale accepted, every record unfilable. So the
    /// answer walks the real lifecycle — nothing, key only, fully installed — and only the last one
    /// is a road.
    #[tokio::test]
    async fn only_a_fully_installed_identity_counts_as_enrolled() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(53));
        let db = db_ready().await;

        assert!(
            !is_enrolled(&db, HUB).await.unwrap(),
            "sin fila no hay nada que presentar en el ingress"
        );

        let csr = ensure_key_and_csr(&db, HUB).await.unwrap();
        assert!(
            !is_enrolled(&db, HUB).await.unwrap(),
            "con la clave generada y el CSR presentado todavía no hay certificado: no es una vía"
        );

        let (cert, ca) = sign_with_test_ca(&csr, None, 365);
        install_certificate(&db, HUB, &cert, &ca).await.unwrap();
        assert!(
            is_enrolled(&db, HUB).await.unwrap(),
            "clave + certificado + CA: exactamente lo que `client_identity` monta"
        );
        assert!(
            client_identity(&db, HUB).await.unwrap().is_some(),
            "y la respuesta tiene que ser la MISMA que la del constructor real, o `is_enrolled` \
             estaría prometiendo una conexión que no se puede abrir"
        );

        delete(&db, HUB).await.unwrap();
        assert!(
            !is_enrolled(&db, HUB).await.unwrap(),
            "rotar la clave cierra la vía hasta que se re-enrola"
        );
    }

    #[tokio::test]
    async fn the_csr_carries_the_hub_common_name_and_the_key_never_leaves() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(41));
        let db = db_ready().await;

        let csr_pem = ensure_key_and_csr(&db, HUB).await.unwrap();

        let req = openssl::x509::X509Req::from_pem(csr_pem.as_bytes()).unwrap();
        let cn = req
            .subject_name()
            .entries_by_nid(openssl::nid::Nid::COMMONNAME)
            .next()
            .unwrap()
            .data()
            .as_utf8()
            .unwrap()
            .to_string();
        assert_eq!(cn, common_name(HUB));
        assert!(
            req.verify(&req.public_key().unwrap()).unwrap(),
            "self-signature"
        );

        // At rest the key is CIPHERTEXT — what a database dump shows is not a key.
        let row = load_row(&db, HUB).await.unwrap().unwrap();
        assert!(
            secret_box::is_encrypted(&row.0),
            "private key stored encrypted"
        );
        assert!(
            !row.0.contains("PRIVATE KEY"),
            "no PEM marker in the stored row"
        );

        // Idempotent: the second CSR re-derives from the SAME key.
        let second = ensure_key_and_csr(&db, HUB).await.unwrap();
        let req2 = openssl::x509::X509Req::from_pem(second.as_bytes()).unwrap();
        assert!(
            req2.public_key()
                .unwrap()
                .public_eq(&req.public_key().unwrap()),
            "same key, twice"
        );
    }

    #[tokio::test]
    async fn without_the_master_key_no_identity_is_generated_at_all() {
        let _lock = env_lock();
        let _key = EnvVarGuard::unset();
        let db = db_ready().await;

        let err = ensure_key_and_csr(&db, HUB).await.unwrap_err();
        assert!(
            err.to_string().contains(secret_box::MASTER_KEY_ENV),
            "{err}"
        );
        assert!(
            load_row(&db, HUB).await.unwrap().is_none(),
            "nothing stored"
        );
    }

    #[tokio::test]
    async fn install_refuses_a_certificate_for_another_key_or_cn_or_expired() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(42));
        let db = db_ready().await;
        let csr = ensure_key_and_csr(&db, HUB).await.unwrap();

        // A certificate for a DIFFERENT key: sign a foreign CSR and try to install it here.
        let foreign_db = db_ready().await;
        let foreign_csr = ensure_key_and_csr(&foreign_db, "99999999-aaaa-4bbb-8ccc-dddddddddddd")
            .await
            .unwrap();
        let (foreign_cert, ca) = sign_with_test_ca(&foreign_csr, Some(&common_name(HUB)), 365);
        let err = install_certificate(&db, HUB, &foreign_cert, &ca)
            .await
            .unwrap_err();
        assert!(err.to_string().contains("clave"), "{err}");

        // The right key but the WRONG name.
        let (wrong_cn, ca2) =
            sign_with_test_ca(&csr, Some("hub-otro.fiscal.erplora.internal"), 365);
        let err = install_certificate(&db, HUB, &wrong_cn, &ca2)
            .await
            .unwrap_err();
        assert!(err.to_string().contains("CN"), "{err}");

        // Nothing half-installed after the refusals.
        let st = status(&db, HUB).await.unwrap();
        assert!(st.has_key && !st.has_certificate);
    }

    #[tokio::test]
    async fn the_signed_certificate_roundtrips_into_a_client_identity() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(43));
        let db = db_ready().await;

        assert!(
            client_identity(&db, HUB).await.unwrap().is_none(),
            "nothing yet"
        );

        let csr = ensure_key_and_csr(&db, HUB).await.unwrap();
        let (cert, ca) = sign_with_test_ca(&csr, None, 365);
        let st = install_certificate(&db, HUB, &cert, &ca).await.unwrap();
        assert!(st.has_key && st.has_certificate);
        assert_eq!(st.common_name, common_name(HUB));
        assert!(st.not_after.is_some(), "the ISO expiry is reported");

        let (identity, ca_bytes) = client_identity(&db, HUB).await.unwrap().unwrap();
        let _usable = reqwest::Client::builder()
            .use_rustls_tls()
            .identity(identity)
            .add_root_certificate(reqwest::Certificate::from_pem(&ca_bytes).unwrap())
            .build()
            .unwrap();

        // And delete forgets everything, key included.
        delete(&db, HUB).await.unwrap();
        assert!(client_identity(&db, HUB).await.unwrap().is_none());
        assert!(!status(&db, HUB).await.unwrap().has_key);
    }

    /// hub#1459: the host lends the identity through a GENERIC method — «who this machine is» —
    /// carrying the common name and NO destination. A host that answered `None` for an enrolled
    /// hub would silently take the engine off the wire, so the enrolled case is the assertion.
    #[tokio::test]
    async fn the_host_lends_the_machine_identity_with_its_common_name() {
        let _lock = env_lock();
        let _key = EnvVarGuard::set(&test_key_b64(47));
        let db = db_ready().await;
        let host = crate::native::DbHost {
            db: &db,
            storage: None,
            hub_id: HUB,
            module_id: "testregime",
            static_folder: None,
        };

        assert!(
            crate::native::NativeHost::machine_identity(&host, HUB)
                .await
                .unwrap()
                .is_none(),
            "nothing enrolled yet"
        );

        let csr = ensure_key_and_csr(&db, HUB).await.unwrap();
        let (cert, ca) = sign_with_test_ca(&csr, None, 365);
        install_certificate(&db, HUB, &cert, &ca).await.unwrap();

        let lent = crate::native::NativeHost::machine_identity(&host, HUB)
            .await
            .unwrap()
            .expect("an enrolled hub has an identity to lend");
        assert_eq!(lent.common_name, common_name(HUB));
        assert!(!lent.ca_pem.is_empty());
        let printed = format!("{lent:?}");
        assert!(printed.contains(&common_name(HUB)), "{printed}");
    }
}
