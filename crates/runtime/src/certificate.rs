//! The hub's fiscal certificates, in the core (ADR-0079, ADR-0202 §2.1).
//!
//! The PKCS#12 that gives the hub a fiscal identity (VeriFactu today, B2B tomorrow) is a **HUB**
//! resource, not a module one. It lives in the system table `_hub_certificate`. A module only USES
//! it if the `certificate` capability was granted (the dispatcher's gate demands it before the
//! native handler); the private key never crosses into the WASM sandbox.
//!
//! # Two slots, and the own one wins (ADR-0202 §2.1 — hub#316)
//!
//! Since VeriFactu phase 2 the table is no longer a singleton: a hub holds up to **two**
//! certificates, one per [`CertificateKind`], and they coexist.
//!
//! - [`Own`](CertificateKind::Own) — the BUSINESS's certificate, uploaded by its owner in
//!   Ajustes → Negocio (`PUT /api/business/certificate`). Renewing it was always the customer's job.
//! - [`Delegated`](CertificateKind::Delegated) — ERPlora's certificate, handed down by the control
//!   plane and rotated centrally, invisibly to the hub (saas#1124/#1125).
//!
//! **Selection is a fallback, never a setting**: [`active_kind`] answers «the own one if it was
//! uploaded, otherwise the delegated one». There is no question to the user and no column to flip —
//! it is the ORDER of [`SLOTS`] and nothing else.
//!
//! # The delegated slot never leaves the hub
//!
//! [`exportable_der_bytes`] is the only door through which raw `.p12` bytes reach anything outside
//! this module (the blueprint/backup export — `crates/server/src/export_import.rs`), and it hands
//! out only the slots that [`CertificateKind::may_leave_the_hub`] allows. The delegated certificate
//! is **ERPlora's private key, not the customer's**: the hub holds it to sign on their behalf under
//! a power of attorney, and a bundle is a file that gets downloaded, published to the catalogue and
//! imported into someone else's hub. One export carrying it would put the key that identifies
//! ERPlora before the AEAT in the hands of whoever opens the zip.
//!
//! `pkcs12_b64`/`password` are encrypted at rest ([`crate::secret_box`], ERPlora/hub#114) with a
//! master key that lives OUTSIDE the database (`HUB_SECRETS_KEY`, env) — whoever reads
//! `_hub_certificate` directly can no longer sign in the business's name. **Without the master key,
//! [`set`] fails (fail-closed): a new certificate is never stored in the clear.** Legacy rows
//! (uploaded before that fix, without the `v1:` prefix) are still READ as they were (backwards
//! compatibility); they get re-encrypted lazily the next time somebody uploads the certificate again
//! (there is no boot migration — see `secret_box.rs` for why).
use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value};

use crate::errors::{Result, RuntimeError};
use crate::registry::now_rfc3339;
use crate::secret_box::{self, SecretsKey};

/// Which of the hub's two certificates a row is (ADR-0202 §2.1 — hub#316).
///
/// A SLOT, not a preference: nothing reads this column to decide which certificate signs. That is
/// [`active_kind`]'s job, and it answers from the order of [`SLOTS`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CertificateKind {
    /// The BUSINESS's own certificate — uploaded by its owner in Ajustes → Negocio (ADR-0079/0081,
    /// still in force). Theirs to renew, theirs to delete, and the only one their backup carries.
    Own,
    /// ERPlora's certificate, delegated to this hub by the control plane (ADR-0202 §2, saas#1124).
    /// The hub receives it and rotates it without the customer ever seeing it — and, being someone
    /// else's private key, it never travels inside a bundle ([`may_leave_the_hub`]).
    ///
    /// [`may_leave_the_hub`]: CertificateKind::may_leave_the_hub
    Delegated,
}

/// Every slot a hub can hold, **in selection order**: the own certificate first, the delegated one
/// as the fallback behind it (ADR-0202 §2.1).
///
/// This array is the rule. [`active_kind`] walks it to pick the certificate that signs and
/// [`exportable_der_bytes`] walks it to pick the certificate that may travel, so «which one wins»
/// and «which one may leave» can never drift apart into two half-remembered lists.
pub const SLOTS: [CertificateKind; 2] = [CertificateKind::Own, CertificateKind::Delegated];

impl CertificateKind {
    /// Value stored in `_hub_certificate.kind`. Stable: it is a column of a deployed hub.
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Own => "own",
            Self::Delegated => "delegated",
        }
    }

    /// Reads back what [`as_str`](Self::as_str) wrote. `None` for anything else — a `kind` this
    /// runtime does not know is not guessed at.
    pub fn parse(s: &str) -> Option<Self> {
        SLOTS.into_iter().find(|k| k.as_str() == s)
    }

    /// May this slot's `.p12` travel inside a blueprint/backup bundle? (ADR-0202 §2.1 — hub#316)
    ///
    /// **Only the business's own certificate.** A bundle is a file: it is downloaded, published to
    /// the catalogue and imported into hubs that are not this one (`architecture/hub/export-import.md`).
    /// The own certificate belongs to the business exporting itself, so carrying it is restoring
    /// your own backup — and it is already protected by its own password, which does not travel.
    /// The delegated one belongs to **ERPlora**: it is the key that identifies us before the AEAT
    /// for every hub under our power of attorney, so a single leaked bundle would compromise the
    /// whole fleet, not one business.
    ///
    /// An exhaustive `match` on purpose: a third slot invented later cannot inherit «travels» by
    /// omission — whoever adds it has to answer this question.
    pub const fn may_leave_the_hub(self) -> bool {
        match self {
            Self::Own => true,
            // MUTATION CANARY (see `the_export_never_carries_the_delegated_certificate`): flipping
            // this to `true` must turn the export tests red.
            Self::Delegated => false,
        }
    }
}

fn certificate_error(context: &str, err: secret_box::SecretBoxError) -> RuntimeError {
    RuntimeError::Certificate(format!("{context}: {err}"))
}

/// Master key used to encrypt/decrypt `_hub_certificate` (ADR-0016, ERPlora/hub#114). Kept in its
/// own function so that [`set`]'s fail-closed error message is specific to the fiscal certificate
/// rather than a generic `secret_box` one.
fn load_master_key() -> Result<Option<SecretsKey>> {
    secret_box::master_key_from_env()
        .map_err(|e| certificate_error(&format!("{} inválida", secret_box::MASTER_KEY_ENV), e))
}

/// Stores/replaces the certificate of ONE slot (upsert on `(hub_id, kind)`), leaving the other slot
/// untouched. `by` = `hub_user:<id>` for [`Own`](CertificateKind::Own), the control plane for
/// [`Delegated`](CertificateKind::Delegated).
///
/// **`pub(crate)` on purpose (hub#317).** There are exactly TWO doors into this table and each pins
/// its own slot: [`crate::Runtime::set_business_certificate`] pins [`Own`](CertificateKind::Own) and
/// [`set_delegated`] pins [`Delegated`](CertificateKind::Delegated). Keeping the generic writer
/// inside the crate is what makes «the slot is explicit» a fact rather than a doc comment — and it
/// is what stops anybody writing delegated bytes without saying which `version` they are.
///
/// **`version` travels in the SAME upsert as the bytes.** `Some(v)` for the delegated slot, `None`
/// for the own one (nobody rotates the business's certificate centrally, so it has no version). A
/// second statement would open a window where the row holds new bytes under the old number, and a
/// hub that reports a version it does not have is a hub the fleet panel calls up to date while it
/// signs with a superseded — possibly revoked — key.
///
/// **Fail-closed:** without `HUB_SECRETS_KEY` it fails — a new `.p12`/password is NEVER persisted in
/// the clear, nor is a key generated and stored in the same database (that would protect nothing).
/// The Hub is Postgres-only/cloud-only since ADR-0154 (there is no Local/Cloud split that could
/// relax this policy for a subset of deployments).
pub(crate) async fn set(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    kind: CertificateKind,
    pkcs12_b64: &str,
    password: &str,
    by: &str,
    version: Option<i64>,
) -> Result<()> {
    let key = load_master_key()?.ok_or_else(|| {
        RuntimeError::Certificate(format!(
            "cifrado de secretos no configurado: define {} antes de subir un certificado nuevo \
             (ADR-0016, ERPlora/hub#114) — nunca se guarda un .p12/contraseña en claro",
            secret_box::MASTER_KEY_ENV
        ))
    })?;
    let pkcs12_b64_enc =
        secret_box::encrypt(&key, pkcs12_b64).map_err(|e| certificate_error("cifrando el .p12", e))?;
    let password_enc = secret_box::encrypt(&key, password)
        .map_err(|e| certificate_error("cifrando la contraseña", e))?;

    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("kind".into(), json!(kind.as_str()));
    p.insert("pkcs12_b64".into(), json!(pkcs12_b64_enc));
    p.insert("password".into(), json!(password_enc));
    p.insert("uploaded_at".into(), json!(now_rfc3339()));
    p.insert("uploaded_by".into(), json!(by));
    p.insert("cert_version".into(), json!(version));
    db.execute(
        "INSERT INTO _hub_certificate \
           (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by, cert_version) \
         VALUES (:hub_id, :kind, :pkcs12_b64, :password, :uploaded_at, :uploaded_by, :cert_version) \
         ON CONFLICT (hub_id, kind) DO UPDATE SET \
           pkcs12_b64 = excluded.pkcs12_b64, password = excluded.password, \
           uploaded_at = excluded.uploaded_at, uploaded_by = excluded.uploaded_by, \
           cert_version = excluded.cert_version",
        &p,
    )
    .await?;
    Ok(())
}

/// `uploaded_by` of the delegated slot. Not a user: nobody in this hub uploaded ERPlora's key — the
/// control plane handed it down (ADR-0202 §2). It is what the read-only «signing with: ERPlora»
/// surface shows, so it has to say so rather than borrow a human's id.
pub const CONTROL_PLANE: &str = "cloud";

/// Stores the certificate the CONTROL PLANE handed down, together with the `version` it was served
/// under (ADR-0202 §2, saas#1125 — hub#317).
///
/// The one door into the [`Delegated`](CertificateKind::Delegated) slot, mirroring
/// [`crate::Runtime::set_business_certificate`] for the own one: the slot and the provenance are
/// pinned HERE, once, so no call site can land on the wrong one by passing a default. Encryption at
/// rest and the fail-closed rule are [`set`]'s, unchanged — this is ERPlora's private key, and it
/// gets exactly the same treatment as the customer's.
pub async fn set_delegated(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    pkcs12_b64: &str,
    password: &str,
    version: i64,
) -> Result<()> {
    set(
        db,
        hub_id,
        CertificateKind::Delegated,
        pkcs12_b64,
        password,
        CONTROL_PLANE,
        Some(version),
    )
    .await
}

/// The `version` of the delegated certificate this hub currently holds — what the heartbeat reports
/// up as `cert_version` and compares against the one the control plane announces (ADR-0202 §2.5).
///
/// `None` means «this hub holds no delegated certificate», which the SaaS reads as `0` and NOT as
/// «never reported» — the two are different states over there, so the caller must not conflate them.
///
/// Never touches `pkcs12_b64`/`password`: answering «which version do I have?» must not drag a
/// private key through memory, let alone decrypt one.
pub async fn delegated_version(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Option<i64>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("kind".into(), json!(CertificateKind::Delegated.as_str()));
    let res = db
        .query(
            "SELECT cert_version FROM _hub_certificate \
             WHERE hub_id = :hub_id AND kind = :kind AND pkcs12_b64 <> '' LIMIT 1",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .into_iter()
        .next()
        .and_then(|r| r.get("cert_version").and_then(|v| v.as_i64())))
}

/// The slots that actually HOLD a certificate, in [`SLOTS`] order (i.e. selection order), each with
/// its audit metadata. **One query**, and it never selects `pkcs12_b64`: the emptiness test runs in
/// SQL so that answering «do I have a certificate?» does not drag the encrypted key through memory.
///
/// One round trip matters here: [`status`] is on the dispatcher's path (`commands`/`queries` fill
/// `has_certificate` on every call that arrives without the business identity), so asking slot by
/// slot would have turned one query into four.
async fn occupied_slots(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Vec<(CertificateKind, Value)>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT kind, uploaded_at, uploaded_by FROM _hub_certificate \
             WHERE hub_id = :hub_id AND pkcs12_b64 <> ''",
            &p,
        )
        .await?;
    // Ordered by walking SLOTS, not by whatever order the rows came back in: this list IS the
    // selection order, and a database that returns them the other way round must not flip the rule.
    let mut out = Vec::new();
    for kind in SLOTS {
        if let Some(r) = res
            .rows
            .iter()
            .find(|r| r.get("kind").and_then(|v| v.as_str()) == Some(kind.as_str()))
        {
            out.push((
                kind,
                json!({
                    "present": true,
                    "uploaded_at": r.get("uploaded_at").cloned().unwrap_or(Value::Null),
                    "uploaded_by": r.get("uploaded_by").cloned().unwrap_or(Value::Null),
                }),
            ));
        }
    }
    Ok(out)
}

/// State of ONE slot (never its bytes nor its password): `{ present, uploaded_at, uploaded_by }`.
pub async fn slot_status(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    kind: CertificateKind,
) -> Result<Value> {
    Ok(occupied_slots(db, hub_id)
        .await?
        .into_iter()
        .find(|(k, _)| *k == kind)
        .map(|(_, v)| v)
        .unwrap_or_else(|| json!({ "present": false })))
}

/// State of the hub's certificates for `GET /api/business/certificate`.
///
/// `present`/`uploaded_at`/`uploaded_by` describe the **own** slot, and mean exactly what they meant
/// before there were two: what the owner uploaded in Ajustes → Negocio, which is what that screen
/// shows and what its delete button removes. Saying `present: true` because ERPlora handed the hub a
/// delegated certificate would offer the customer a certificate they cannot see and a button that
/// deletes a key that is not theirs.
///
/// What is new is read-only and additive: `slots` (state per slot) and `active` (which one signs,
/// per [`active_kind`]) — the «firmando con: certificado propio / ERPlora» the module shows
/// (ADR-0202 §2.2). `null` when the hub has neither.
///
/// # ⚠️ `present` has THREE readers, and they must move together (hub#319)
///
/// `present` is not only this endpoint's field: it is also the answer to «can this hub issue?», read
/// identically by [`crate::commands::execute`], [`crate::queries::execute_page`] (both to fill
/// `RequestContext::has_certificate`, which is what the ADR-0203 gate checks) and
/// [`crate::setup_status`] (the ⛔ arm of the checklist — hub#370). They must give the SAME answer:
/// a ⛔ that blocks a screen while the dispatcher accepts, or the reverse, is the checklist lying.
///
/// This PR keeps all three on the **own** slot, so they stay consistent and today's behaviour is
/// unchanged — nothing writes a delegated certificate yet (that is hub#317). The moment one exists,
/// a hub that holds only the delegated one CAN invoice (ADR-0202 §2.1), and all three have to switch
/// from `status()["present"]` to `active_kind(..).is_some()` **in the same change** (hub#319).
/// Switching one alone is what starts the lie; switching them early, before hub#317, would be a
/// no-op change to the hottest path in the runtime.
pub async fn status(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Value> {
    let occupied = occupied_slots(db, hub_id).await?;
    let of = |kind: CertificateKind| {
        occupied
            .iter()
            .find(|(k, _)| *k == kind)
            .map(|(_, v)| v.clone())
            .unwrap_or_else(|| json!({ "present": false }))
    };
    let own = of(CertificateKind::Own);
    // `active` = the first occupied slot in SLOTS order — the same rule as `active_kind`, answered
    // from the rows already in hand.
    let active = occupied.first().map(|(k, _)| k.as_str());
    let mut out = own.clone();
    if let Some(o) = out.as_object_mut() {
        o.insert(
            "slots".into(),
            json!({
                CertificateKind::Own.as_str(): own,
                CertificateKind::Delegated.as_str(): of(CertificateKind::Delegated),
            }),
        );
        o.insert("active".into(), json!(active));
    }
    Ok(out)
}

/// Removes the certificate of ONE slot. The other one stays: deleting your own certificate leaves
/// the hub signing with the delegated one (that is the fallback, ADR-0202 §2.1), it does not leave
/// the hub unable to invoice.
pub async fn delete(db: &dyn DatabaseAdapter, hub_id: &str, kind: CertificateKind) -> Result<()> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("kind".into(), json!(kind.as_str()));
    db.execute(
        "DELETE FROM _hub_certificate WHERE hub_id = :hub_id AND kind = :kind",
        &p,
    )
    .await?;
    Ok(())
}

/// Which certificate signs for this hub — **the own one if it was uploaded, otherwise the delegated
/// one** (ADR-0202 §2.1). `None` if the hub holds neither.
///
/// A fallback, not an option: there is no setting, no prompt and no stored preference. It is the
/// order of [`SLOTS`], read fresh every time, so uploading your own certificate takes over on the
/// next signature and deleting it hands the hub back to the delegated one — both directions, with
/// nothing to reconfigure.
///
/// **This is what «can this hub issue?» must eventually ask** — see the warning on [`status`]: the
/// dispatcher gate and the ⛔ arm of the setup checklist still read the own slot, and hub#319 moves
/// both here at once, once hub#317 makes a delegated certificate possible at all.
pub async fn active_kind(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Option<CertificateKind>> {
    Ok(occupied_slots(db, hub_id).await?.first().map(|(k, _)| *k))
}

// ── Signing/identity MEDIATED by the host (ADR-0079) ──────────────────────────
// The core owns the certificates and does ALL the PKCS#12 crypto (OpenSSL) in ONE place. Modules
// (verifactu, future B2B…) only ASK for the operation (`NativeHost::certificate_*`); the private key
// NEVER crosses into the module (it does not see the `.p12` bytes). Reusable by any fiscal/signing
// scheme. The module only needs the `certificate` capability granted.

/// Reads one slot's PKCS#12 from `_hub_certificate` (base64 → DER) + password. `None` if that slot
/// is empty.
///
/// Decrypts both columns ([`crate::secret_box`]); legacy rows (plaintext, no `v1:` prefix) are read
/// as they always were, without demanding a master key. Rows that ARE encrypted do demand it — if it
/// is missing or does not match, the error is explicit (never a panic nor a silently corrupt `.p12`).
async fn load_pkcs12(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    kind: CertificateKind,
) -> Result<Option<(Vec<u8>, String)>> {
    use base64::Engine as _;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("kind".into(), json!(kind.as_str()));
    let res = db
        .query(
            "SELECT pkcs12_b64, password FROM _hub_certificate \
             WHERE hub_id = :hub_id AND kind = :kind LIMIT 1",
            &p,
        )
        .await?;
    let Some(row) = res.rows.into_iter().next() else {
        return Ok(None);
    };
    let b64_stored = row.get("pkcs12_b64").and_then(|v| v.as_str()).unwrap_or("");
    if b64_stored.is_empty() {
        return Ok(None);
    }
    let password_stored = row.get("password").and_then(|v| v.as_str()).unwrap_or("");

    let key = load_master_key()?;
    let b64 = secret_box::decrypt_or_legacy(key.as_ref(), b64_stored)
        .map_err(|e| certificate_error("descifrando el .p12 de _hub_certificate", e))?;
    let password = secret_box::decrypt_or_legacy(key.as_ref(), password_stored)
        .map_err(|e| certificate_error("descifrando la contraseña de _hub_certificate", e))?;

    let der = base64::engine::general_purpose::STANDARD.decode(b64.trim()).map_err(|e| {
        RuntimeError::Certificate(format!("PKCS#12 base64 inválido en _hub_certificate: {e}"))
    })?;
    Ok(Some((der, password)))
}

/// DER bytes of the `.p12` that MAY leave the hub inside a bundle — **decrypted, without the
/// password** (`crates/server/src/export_import.rs`, ADR-0113 decision (d): "the password does not
/// travel"). `None` if the hub has no exportable certificate.
///
/// This is the one door through which raw `.p12` bytes reach anything outside this module, so the
/// rule lives here and not at the call site: it walks [`SLOTS`] and only ever hands out a slot that
/// [`CertificateKind::may_leave_the_hub`] allows. A hub whose only certificate is the delegated one
/// exports **no certificate at all** — correctly: that key is ERPlora's, and the business restoring
/// this bundle has to upload its own.
///
/// (Before ERPlora/hub#114 the export read `pkcs12_b64` raw from the database — it was the plaintext
/// base64 back then; with encryption at rest it has to come through here.)
pub async fn exportable_der_bytes(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Option<Vec<u8>>> {
    for kind in SLOTS {
        if !kind.may_leave_the_hub() {
            continue;
        }
        if let Some((der, _password)) = load_pkcs12(db, hub_id, kind).await? {
            return Ok(Some(der));
        }
    }
    Ok(None)
}

/// mTLS client identity of the hub, so that a module holding the `certificate` capability can
/// transmit to the tax authority **without seeing the `.p12`**. Uses whichever certificate
/// [`active_kind`] selects. Errors if the hub has none, or if it does not parse.
pub async fn identity(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<reqwest::Identity> {
    let (der, password) = load_active_pkcs12(db, hub_id).await?.ok_or_else(|| {
        RuntimeError::Certificate("no hay certificado del negocio cargado (Ajustes → Negocio)".into())
    })?;
    identity_from_der(&der, &password)
}

/// Expiry (notAfter) of the certificate this hub signs with, as ISO `YYYY-MM-DD`. `Ok(None)` if
/// there is none or the date cannot be interpreted.
pub async fn expiry(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Option<String>> {
    match load_active_pkcs12(db, hub_id).await? {
        Some((der, password)) => expiry_from_der(&der, &password),
        None => Ok(None),
    }
}

/// The PKCS#12 of the slot that [`active_kind`] selects.
async fn load_active_pkcs12(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Option<(Vec<u8>, String)>> {
    match active_kind(db, hub_id).await? {
        Some(kind) => load_pkcs12(db, hub_id, kind).await,
        None => Ok(None),
    }
}

/// Parsea el PKCS#12 **en memoria con OpenSSL** (acepta los `.p12` BER reales de FNMT/Windows que un
/// parser DER estricto rechaza) y lo entrega a **rustls** como PEM (clave + certificado + cadena).
/// A diferencia de `native-tls`, OpenSSL no importa la clave al Llavero del SO (sin diálogos macOS).
/// `pub` para `certificate_*_from` (cert provisto en memoria, p.ej. validar uno recién subido) — la
/// cripto sigue viviendo SOLO aquí, en el core. (OpenSSL → solo non-Android; ver stub abajo.)
#[cfg(not(target_os = "android"))]
pub fn identity_from_der(der: &[u8], password: &str) -> Result<reqwest::Identity> {
    ensure_legacy_provider();
    let pkcs12 = openssl::pkcs12::Pkcs12::from_der(der)
        .map_err(|e| RuntimeError::Certificate(format!("PKCS#12 inválido: {e}")))?;
    let parsed = pkcs12
        .parse2(password)
        .map_err(|e| RuntimeError::Certificate(format!("PKCS#12 (¿contraseña incorrecta?): {e}")))?;
    let key = parsed
        .pkey
        .ok_or_else(|| RuntimeError::Certificate("el PKCS#12 no contiene clave privada".into()))?;
    let cert = parsed
        .cert
        .ok_or_else(|| RuntimeError::Certificate("el PKCS#12 no contiene certificado".into()))?;
    let mut pem = key
        .private_key_to_pem_pkcs8()
        .map_err(|e| RuntimeError::Certificate(format!("clave privada: {e}")))?;
    pem.extend_from_slice(
        &cert.to_pem().map_err(|e| RuntimeError::Certificate(format!("certificado: {e}")))?,
    );
    // Cadena intermedia (si el `.p12` la incluye) — la AEAT valida hasta la raíz FNMT.
    if let Some(chain) = parsed.ca {
        for c in chain {
            if let Ok(b) = c.to_pem() {
                pem.extend_from_slice(&b);
            }
        }
    }
    reqwest::Identity::from_pem(&pem)
        .map_err(|e| RuntimeError::Certificate(format!("identidad TLS inválida: {e}")))
}

/// Stub Android: sin OpenSSL no se puede parsear el `.p12` (ver `Cargo.toml`). El shell Android no
/// hace transmisión fiscal todavía; la firma vive en Hub Cloud/Local.
#[cfg(target_os = "android")]
pub fn identity_from_der(_der: &[u8], _password: &str) -> Result<reqwest::Identity> {
    Err(RuntimeError::Certificate(
        "firma con certificado fiscal no disponible en Android (sin OpenSSL)".into(),
    ))
}

/// Caducidad (notAfter) de un PKCS#12 en DER como ISO `YYYY-MM-DD`. `pub` para `certificate_*_from`.
#[cfg(not(target_os = "android"))]
pub fn expiry_from_der(der: &[u8], password: &str) -> Result<Option<String>> {
    ensure_legacy_provider();
    let pkcs12 = openssl::pkcs12::Pkcs12::from_der(der)
        .map_err(|e| RuntimeError::Certificate(format!("PKCS#12 inválido: {e}")))?;
    let parsed = pkcs12
        .parse2(password)
        .map_err(|e| RuntimeError::Certificate(format!("PKCS#12 (¿contraseña incorrecta?): {e}")))?;
    match parsed.cert {
        // El Display de Asn1Time es "MMM DD HH:MM:SS YYYY GMT" (p.ej. "Jun 10 00:00:00 2028 GMT").
        Some(cert) => Ok(asn1_time_to_iso(&cert.not_after().to_string())),
        None => Ok(None),
    }
}

/// Stub Android: sin OpenSSL no se puede leer la caducidad del `.p12` (ver `Cargo.toml`).
#[cfg(target_os = "android")]
pub fn expiry_from_der(_der: &[u8], _password: &str) -> Result<Option<String>> {
    Ok(None)
}

/// Carga (una sola vez) el proveedor **`legacy`** de OpenSSL 3 junto al `default`, para descifrar
/// PKCS#12 con PBE antiguos (RC2-40-CBC, 3DES) de certificados reales (FNMT, exportados de Windows).
/// OpenSSL 3 los movió fuera del proveedor por defecto; sin esto fallan con `RC2-40-CBC : unsupported`.
#[cfg(not(target_os = "android"))]
fn ensure_legacy_provider() {
    use std::sync::OnceLock;
    static LEGACY: OnceLock<Option<openssl::provider::Provider>> = OnceLock::new();
    LEGACY.get_or_init(|| openssl::provider::Provider::try_load(None, "legacy", true).ok());
}

/// "Jun 10 00:00:00 2028 GMT" → "2028-06-10". `None` si el formato no casa.
#[cfg(not(target_os = "android"))]
fn asn1_time_to_iso(s: &str) -> Option<String> {
    let parts: Vec<&str> = s.split_whitespace().collect();
    if parts.len() < 4 {
        return None;
    }
    let month = match parts[0] {
        "Jan" => "01", "Feb" => "02", "Mar" => "03", "Apr" => "04",
        "May" => "05", "Jun" => "06", "Jul" => "07", "Aug" => "08",
        "Sep" => "09", "Oct" => "10", "Nov" => "11", "Dec" => "12",
        _ => return None,
    };
    let day = parts[1];
    let day = if day.len() == 1 { format!("0{day}") } else { day.to_string() };
    Some(format!("{}-{}-{}", parts[3], month, day))
}

#[cfg(all(test, not(target_os = "android")))]
mod asn1_tests {
    use super::asn1_time_to_iso;
    #[test]
    fn parses_openssl_asn1_time() {
        assert_eq!(asn1_time_to_iso("Jun 10 00:00:00 2028 GMT").as_deref(), Some("2028-06-10"));
        assert_eq!(asn1_time_to_iso("Mar 3 23:59:59 2027 GMT").as_deref(), Some("2027-03-03"));
        assert_eq!(asn1_time_to_iso("garbage").as_deref(), None);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::secret_box::test_support::{env_lock, test_key_b64, EnvVarGuard};
    use erplora_db::{testutil::fresh_db, PgAdapter};

    /// base64 of "OWN-PKCS12" and "DELEGATED-PKCS12" — two payloads that share no substring, so a
    /// test asserting one did not leak cannot pass by accident on a prefix of the other.
    const OWN_B64: &str = "T1dOLVBLQ1MxMg==";
    const DELEGATED_B64: &str = "REVMRUdBVEVELVBLQ1MxMg==";

    fn decoded(b64: &str) -> Vec<u8> {
        use base64::Engine as _;
        base64::engine::general_purpose::STANDARD.decode(b64).unwrap()
    }

    async fn db_ready() -> PgAdapter {
        let db = fresh_db().await;
        crate::installer::ensure_hub_module_table(&db).await.unwrap();
        // hub_session baseline (v0): la migración v8 (device_id, ADR-0154) lo ALTERa.
        crate::identity::ensure_tables(&db).await.unwrap();
        crate::system_migrations::apply(&db, "hub-test").await.unwrap();
        db
    }

    /// Reads the raw row of one slot as it sits in the database (without going through
    /// `load_pkcs12`/decryption) — what somebody with direct database access would see.
    async fn raw_row(db: &dyn DatabaseAdapter, hub_id: &str, kind: CertificateKind) -> (String, String) {
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("kind".into(), json!(kind.as_str()));
        let res = db
            .query(
                "SELECT pkcs12_b64, password FROM _hub_certificate \
                 WHERE hub_id = :hub_id AND kind = :kind LIMIT 1",
                &p,
            )
            .await
            .unwrap();
        let row = res.rows.into_iter().next().expect("fila esperada");
        (
            row.get("pkcs12_b64").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            row.get("password").and_then(|v| v.as_str()).unwrap_or("").to_string(),
        )
    }

    // ── The own slot behaves exactly as it did before there were two ──────────────────────────

    #[tokio::test]
    async fn set_status_delete_roundtrip() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(1));
        let db = db_ready().await;
        // Ausente.
        assert_eq!(status(&db, "hub-test").await.unwrap()["present"], json!(false));
        // Subir.
        set(&db, "hub-test", CertificateKind::Own, "QkFTRTY0", "secret", "hub_user:admin", None)
            .await
            .unwrap();
        let st = status(&db, "hub-test").await.unwrap();
        assert_eq!(st["present"], json!(true));
        assert_eq!(st["uploaded_by"], json!("hub_user:admin"));
        // status NO expone bytes ni password.
        assert!(st.get("pkcs12_b64").is_none() && st.get("password").is_none());
        // Reemplazar (upsert, no duplica).
        set(&db, "hub-test", CertificateKind::Own, "TkVX", "p2", "hub_user:admin", None).await.unwrap();
        assert_eq!(status(&db, "hub-test").await.unwrap()["present"], json!(true));
        // Borrar.
        delete(&db, "hub-test", CertificateKind::Own).await.unwrap();
        assert_eq!(status(&db, "hub-test").await.unwrap()["present"], json!(false));
    }

    // ── ERPlora/hub#114: cifrado at-rest de `_hub_certificate` ─────────────────────────────────

    #[tokio::test]
    async fn set_encrypts_pkcs12_and_password_at_rest() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(2));
        let db = db_ready().await;

        set(
            &db,
            "hub-test",
            CertificateKind::Own,
            "TVVZLVNFQ1JFVE8tUEtDUzEy",
            "s3cr3t-p12-password",
            "hub_user:admin",
            None,
        )
        .await
        .unwrap();

        let (pkcs12_raw, password_raw) = raw_row(&db, "hub-test", CertificateKind::Own).await;
        // La fila cruda NUNCA debe contener el password ni el .p12 en claro.
        assert_ne!(pkcs12_raw, "TVVZLVNFQ1JFVE8tUEtDUzEy");
        assert_ne!(password_raw, "s3cr3t-p12-password");
        assert!(!pkcs12_raw.contains("TVVZLVNFQ1JFVE8tUEtDUzEy"));
        assert!(!password_raw.contains("s3cr3t-p12-password"));
        // Formato versionado (`secret_box::PREFIX`).
        assert!(pkcs12_raw.starts_with("v1:"));
        assert!(password_raw.starts_with("v1:"));
    }

    /// The delegated certificate is somebody else's private key: it must be as unreadable from a
    /// database dump as the business's own one.
    #[tokio::test]
    async fn the_delegated_certificate_is_encrypted_at_rest_too() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(7));
        let db = db_ready().await;

        set(&db, "hub-test", CertificateKind::Delegated, DELEGATED_B64, "erplora-pw", "cloud", None)
            .await
            .unwrap();

        let (pkcs12_raw, password_raw) = raw_row(&db, "hub-test", CertificateKind::Delegated).await;
        assert!(!pkcs12_raw.contains(DELEGATED_B64));
        assert!(!password_raw.contains("erplora-pw"));
        assert!(pkcs12_raw.starts_with("v1:") && password_raw.starts_with("v1:"));
    }

    #[tokio::test]
    async fn set_then_load_pkcs12_roundtrip_returns_originals() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(3));
        let db = db_ready().await;

        let original_b64 = "TVVZLVNFQ1JFVE8tUEtDUzEy"; // base64("MUY-SECRETO-PKCS12")
        set(&db, "hub-test", CertificateKind::Own, original_b64, "mi-contraseña-real", "hub_user:admin", None)
            .await
            .unwrap();

        let (der, password) = load_pkcs12(&db, "hub-test", CertificateKind::Own)
            .await
            .unwrap()
            .expect("certificado presente");
        assert_eq!(der, decoded(original_b64));
        assert_eq!(password, "mi-contraseña-real");
    }

    #[tokio::test]
    async fn exportable_der_bytes_decrypts_without_leaking_password() {
        // Regresión: `crates/server/src/export_import.rs` (export de blueprint, decisión (d) "la
        // contraseña no viaja") leía antes el base64 crudo de la columna. Con cifrado at-rest debe
        // pasar por aquí para no exportar el ciphertext como si fuera el `.p12`.
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(6));
        let db = db_ready().await;

        set(&db, "hub-test", CertificateKind::Own, OWN_B64, "no-debe-viajar", "hub_user:admin", None)
            .await
            .unwrap();

        let der = exportable_der_bytes(&db, "hub-test").await.unwrap().expect("certificado presente");
        assert_eq!(der, decoded(OWN_B64));
    }

    #[tokio::test]
    async fn load_pkcs12_reads_legacy_plaintext_row_without_key() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::unset();
        let db = db_ready().await;

        // Fila legacy: escrita ANTES de este fix, directamente en claro (bypassa `set`, que ahora
        // exige la master key). Reproduce el estado real de las instalaciones ya existentes.
        let mut p = Params::new();
        p.insert("hub_id".into(), json!("hub-test"));
        p.insert("pkcs12_b64".into(), json!("TEVHQUNZLVBMQUlOVEVYVA=="));
        p.insert("password".into(), json!("legacy-plaintext-password"));
        p.insert("uploaded_at".into(), json!(now_rfc3339()));
        p.insert("uploaded_by".into(), json!("hub_user:admin"));
        // Sin `kind`: la migración v14 lo rellena con `own` por defecto, que es lo que esa fila es.
        db.execute(
            "INSERT INTO _hub_certificate (hub_id, pkcs12_b64, password, uploaded_at, uploaded_by) \
             VALUES (:hub_id, :pkcs12_b64, :password, :uploaded_at, :uploaded_by)",
            &p,
        )
        .await
        .unwrap();

        // Sin HUB_SECRETS_KEY, la fila legacy se sigue leyendo igual (compat hacia atrás).
        let (der, password) = load_pkcs12(&db, "hub-test", CertificateKind::Own)
            .await
            .unwrap()
            .expect("certificado presente");
        assert_eq!(der, decoded("TEVHQUNZLVBMQUlOVEVYVA=="));
        assert_eq!(password, "legacy-plaintext-password");
    }

    #[tokio::test]
    async fn set_without_master_key_fails_fail_closed() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::unset();
        let db = db_ready().await;

        let err = set(&db, "hub-test", CertificateKind::Own, "cGtjczEy", "password", "hub_user:admin", None)
            .await
            .unwrap_err();
        let msg = err.to_string();
        assert!(msg.contains("HUB_SECRETS_KEY"), "mensaje de error poco claro: {msg}");
        // No debe haber guardado nada.
        assert_eq!(status(&db, "hub-test").await.unwrap()["present"], json!(false));
    }

    #[tokio::test]
    async fn load_pkcs12_wrong_key_fails_clearly_not_panics() {
        let _lock = env_lock();
        let db = {
            let _guard = EnvVarGuard::set(&test_key_b64(4));
            let db = db_ready().await;
            set(&db, "hub-test", CertificateKind::Own, "cGtjczEy", "password", "hub_user:admin", None)
                .await
                .unwrap();
            db
        };

        // Misma fila, master key DISTINTA: debe fallar con un error claro, no un pánico.
        let _guard = EnvVarGuard::set(&test_key_b64(5));
        let err = load_pkcs12(&db, "hub-test", CertificateKind::Own).await.unwrap_err();
        assert!(matches!(err, RuntimeError::Certificate(_)));
    }

    // ── ADR-0202 §2.1 (hub#316): dos slots, y el propio gana ───────────────────────────────────

    /// Storing one slot must never evict the other: the business's own certificate and ERPlora's
    /// are two different keys with two different owners and two different renewal cycles.
    #[tokio::test]
    async fn the_two_slots_coexist_without_evicting_each_other() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(8));
        let db = db_ready().await;

        set(&db, "hub-test", CertificateKind::Own, OWN_B64, "pw-own", "hub_user:admin", None).await.unwrap();
        set(&db, "hub-test", CertificateKind::Delegated, DELEGATED_B64, "pw-del", "cloud", None)
            .await
            .unwrap();

        assert_eq!(slot_status(&db, "hub-test", CertificateKind::Own).await.unwrap()["present"], json!(true));
        assert_eq!(
            slot_status(&db, "hub-test", CertificateKind::Delegated).await.unwrap()["present"],
            json!(true)
        );
        // Y cada slot conserva SUS bytes (no se pisan).
        let (own, _) = load_pkcs12(&db, "hub-test", CertificateKind::Own).await.unwrap().unwrap();
        let (del, _) = load_pkcs12(&db, "hub-test", CertificateKind::Delegated).await.unwrap().unwrap();
        assert_eq!(own, decoded(OWN_B64));
        assert_eq!(del, decoded(DELEGATED_B64));
    }

    /// The whole selection rule, in both directions and with nothing to configure: with no
    /// certificate nothing signs; the delegated one covers a hub that has no own certificate;
    /// uploading your own takes over; deleting it hands the hub back to the delegated one.
    #[tokio::test]
    async fn the_own_certificate_wins_and_the_delegated_one_is_the_fallback() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(9));
        let db = db_ready().await;

        assert_eq!(active_kind(&db, "hub-test").await.unwrap(), None, "sin certificado no firma nada");

        set(&db, "hub-test", CertificateKind::Delegated, DELEGATED_B64, "pw-del", "cloud", None)
            .await
            .unwrap();
        assert_eq!(
            active_kind(&db, "hub-test").await.unwrap(),
            Some(CertificateKind::Delegated),
            "sin certificado propio firma el delegado"
        );

        set(&db, "hub-test", CertificateKind::Own, OWN_B64, "pw-own", "hub_user:admin", None).await.unwrap();
        assert_eq!(
            active_kind(&db, "hub-test").await.unwrap(),
            Some(CertificateKind::Own),
            "el propio GANA en cuanto se sube — sin preguntar ni reconfigurar"
        );

        delete(&db, "hub-test", CertificateKind::Own).await.unwrap();
        assert_eq!(
            active_kind(&db, "hub-test").await.unwrap(),
            Some(CertificateKind::Delegated),
            "y al borrarlo se vuelve al delegado: el hub no se queda sin poder facturar"
        );
    }

    /// `GET /api/business/certificate` keeps meaning what it meant: `present` is the certificate the
    /// owner uploaded. Offering to delete ERPlora's key would be a lie in a button.
    #[tokio::test]
    async fn status_reports_the_own_slot_and_says_which_one_signs() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(10));
        let db = db_ready().await;

        set(&db, "hub-test", CertificateKind::Delegated, DELEGATED_B64, "pw-del", "cloud", None)
            .await
            .unwrap();
        let st = status(&db, "hub-test").await.unwrap();
        assert_eq!(st["present"], json!(false), "el negocio no ha subido el suyo");
        assert_eq!(st["active"], json!("delegated"), "pero el hub firma con el de ERPlora");
        assert_eq!(st["slots"]["delegated"]["present"], json!(true));
        assert_eq!(st["slots"]["own"]["present"], json!(false));

        set(&db, "hub-test", CertificateKind::Own, OWN_B64, "pw-own", "hub_user:admin", None).await.unwrap();
        let st = status(&db, "hub-test").await.unwrap();
        assert_eq!(st["present"], json!(true));
        assert_eq!(st["active"], json!("own"));
        // Ni el estado global ni el de cada slot filtran bytes o contraseñas.
        let dump = st.to_string();
        assert!(!dump.contains(OWN_B64) && !dump.contains(DELEGATED_B64));
        assert!(!dump.contains("pw-own") && !dump.contains("pw-del"));
    }

    /// **The rule of this issue**: the delegated `.p12` is not the customer's to export.
    ///
    /// Unit half of the guarantee (the end-to-end half runs over the real zip, in
    /// `crates/server/tests/export_import_test.rs`). Flipping
    /// `CertificateKind::Delegated => may_leave_the_hub() == true` must turn this red.
    #[tokio::test]
    async fn the_delegated_certificate_is_never_exportable() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(11));
        let db = db_ready().await;

        // Un hub que SOLO tiene el delegado no exporta certificado alguno.
        set(&db, "hub-test", CertificateKind::Delegated, DELEGATED_B64, "pw-del", "cloud", None)
            .await
            .unwrap();
        assert_eq!(
            exportable_der_bytes(&db, "hub-test").await.unwrap(),
            None,
            "la clave privada de ERPlora no sale del hub"
        );

        // Con los dos, sale el PROPIO — nunca el delegado.
        set(&db, "hub-test", CertificateKind::Own, OWN_B64, "pw-own", "hub_user:admin", None).await.unwrap();
        let der = exportable_der_bytes(&db, "hub-test").await.unwrap().expect("el propio sí viaja");
        assert_eq!(der, decoded(OWN_B64));
        assert_ne!(der, decoded(DELEGATED_B64));
    }

    /// The selection rule and the export rule are DIFFERENT questions, and this is the case that
    /// proves it: the hub signs with the delegated certificate, and still exports none.
    #[tokio::test]
    async fn signing_with_the_delegated_certificate_does_not_make_it_exportable() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(12));
        let db = db_ready().await;

        set(&db, "hub-test", CertificateKind::Delegated, DELEGATED_B64, "pw-del", "cloud", None)
            .await
            .unwrap();
        assert_eq!(active_kind(&db, "hub-test").await.unwrap(), Some(CertificateKind::Delegated));
        assert_eq!(exportable_der_bytes(&db, "hub-test").await.unwrap(), None);
    }

    #[test]
    fn slot_names_round_trip_and_unknown_ones_are_not_guessed() {
        for kind in SLOTS {
            assert_eq!(CertificateKind::parse(kind.as_str()), Some(kind));
        }
        assert_eq!(CertificateKind::parse("Own"), None);
        assert_eq!(CertificateKind::parse(""), None);
    }

    // ── The control plane's door: `set_delegated` (ADR-0202 §2, hub#317) ──────────────────────

    /// 🔒 **What the control plane hands down is stored ENCRYPTED, like everything in this table.**
    /// This is ERPlora's private key: whoever reads `_hub_certificate` directly — a `pg_dump`, a
    /// pgBackRest archive, a restored standby — must not come away able to sign as ERPlora before
    /// the AEAT for the whole fleet.
    #[tokio::test]
    async fn the_delegated_certificate_is_stored_encrypted_at_rest() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(13));
        let db = db_ready().await;

        set_delegated(&db, "hub-test", DELEGATED_B64, "pw-del", 4).await.unwrap();

        let (stored_b64, stored_password) = raw_row(&db, "hub-test", CertificateKind::Delegated).await;
        assert!(
            secret_box::is_encrypted(&stored_b64),
            "el .p12 delegado está en claro en la BD: {stored_b64}"
        );
        assert!(
            secret_box::is_encrypted(&stored_password),
            "la contraseña delegada está en claro en la BD: {stored_password}"
        );
        assert!(!stored_b64.contains(DELEGATED_B64));
        assert!(!stored_password.contains("pw-del"));
        // Y se lee de vuelta intacto: cifrar no puede significar corromper.
        assert_eq!(
            load_pkcs12(&db, "hub-test", CertificateKind::Delegated).await.unwrap(),
            Some((decoded(DELEGATED_B64), "pw-del".to_string()))
        );
    }

    /// 🔒 **Fail-closed, same as the own slot.** Without the master key nothing is written — the
    /// hub does NOT fall back to storing the control plane's key in the clear, and it does not
    /// leave a half-written row either.
    #[tokio::test]
    async fn without_the_master_key_the_delegated_certificate_is_not_stored_at_all() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::unset();
        let db = db_ready().await;

        let err = set_delegated(&db, "hub-test", DELEGATED_B64, "pw-del", 4).await.unwrap_err();
        assert!(
            err.to_string().contains(secret_box::MASTER_KEY_ENV),
            "el error debería nombrar la clave que falta: {err}"
        );
        assert_eq!(slot_status(&db, "hub-test", CertificateKind::Delegated).await.unwrap()["present"], json!(false));
        assert_eq!(delegated_version(&db, "hub-test").await.unwrap(), None);
    }

    /// **The version stored is the version served.** It is the whole basis of the convergence
    /// contract (§2.5): the hub compares this number with the one the heartbeat announces, and
    /// reports it back so the fleet panel can say «987/1000 en v4». A number that drifted from the
    /// bytes would make a hub claim it is up to date while signing with a superseded key.
    #[tokio::test]
    async fn the_stored_version_is_the_one_that_was_served() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(14));
        let db = db_ready().await;

        assert_eq!(delegated_version(&db, "hub-test").await.unwrap(), None);

        set_delegated(&db, "hub-test", DELEGATED_B64, "pw-del", 4).await.unwrap();
        assert_eq!(delegated_version(&db, "hub-test").await.unwrap(), Some(4));

        // Una rotación reemplaza bytes Y número a la vez: nunca queda el número viejo sobre los
        // bytes nuevos (ni al revés), que es justo lo que rompería la convergencia.
        set_delegated(&db, "hub-test", OWN_B64, "pw-rotated", 5).await.unwrap();
        assert_eq!(delegated_version(&db, "hub-test").await.unwrap(), Some(5));
        assert_eq!(
            load_pkcs12(&db, "hub-test", CertificateKind::Delegated).await.unwrap(),
            Some((decoded(OWN_B64), "pw-rotated".to_string()))
        );
    }

    /// **«Which version do I have?» and «do I have one?» must never disagree.** A row whose bytes
    /// were cleared counts as an EMPTY slot everywhere else (`occupied_slots` filters on
    /// `pkcs12_b64 <> ''`), so it must report no version either. Otherwise the hub would announce a
    /// `cert_version` for a certificate it cannot sign with, and the fleet panel would count it as
    /// up to date (ADR-0202 §2.5).
    #[tokio::test]
    async fn a_delegated_row_without_bytes_reports_no_version() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(19));
        let db = db_ready().await;

        set_delegated(&db, "hub-test", DELEGATED_B64, "pw-del", 4).await.unwrap();
        let mut p = Params::new();
        p.insert("hub_id".into(), json!("hub-test"));
        db.execute(
            "UPDATE _hub_certificate SET pkcs12_b64 = '' WHERE hub_id = :hub_id AND kind = 'delegated'",
            &p,
        )
        .await
        .unwrap();

        assert_eq!(slot_status(&db, "hub-test", CertificateKind::Delegated).await.unwrap()["present"], json!(false));
        assert_eq!(
            delegated_version(&db, "hub-test").await.unwrap(),
            None,
            "un slot vacío no puede seguir anunciando una versión"
        );
    }

    /// The version belongs to the DELEGATED row and to no other. The business's own certificate has
    /// no version — its owner uploads it, nobody rotates it centrally — so uploading one must not
    /// invent a version, and must not overwrite the delegated one's.
    #[tokio::test]
    async fn the_own_certificate_has_no_version_and_does_not_disturb_the_delegated_one() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(15));
        let db = db_ready().await;

        set_delegated(&db, "hub-test", DELEGATED_B64, "pw-del", 7).await.unwrap();
        set(&db, "hub-test", CertificateKind::Own, OWN_B64, "pw-own", "hub_user:admin", None).await.unwrap();

        assert_eq!(delegated_version(&db, "hub-test").await.unwrap(), Some(7));
        // Los dos slots siguen ahí y el propio manda (la regla de selección de hub#316, intacta).
        assert_eq!(active_kind(&db, "hub-test").await.unwrap(), Some(CertificateKind::Own));
        assert_eq!(
            load_pkcs12(&db, "hub-test", CertificateKind::Delegated).await.unwrap(),
            Some((decoded(DELEGATED_B64), "pw-del".to_string()))
        );
    }

    /// 🔒 **The guard of hub#316 survives the new writer.** `set_delegated` is a NEW door into the
    /// delegated slot, so the export rule has to be re-proven through it: a hub whose delegated
    /// certificate arrived from the control plane exports no certificate at all.
    ///
    /// MUTATION CANARY: flipping `CertificateKind::Delegated => may_leave_the_hub() == true` turns
    /// this red too, not just the tests written by hub#316.
    #[tokio::test]
    async fn a_certificate_handed_down_by_the_control_plane_still_never_leaves_the_hub() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(16));
        let db = db_ready().await;

        set_delegated(&db, "hub-test", DELEGATED_B64, "pw-del", 4).await.unwrap();
        assert_eq!(
            exportable_der_bytes(&db, "hub-test").await.unwrap(),
            None,
            "la clave privada de ERPlora no sale del hub ni llegando por el plano de control"
        );

        set(&db, "hub-test", CertificateKind::Own, OWN_B64, "pw-own", "hub_user:admin", None).await.unwrap();
        assert_eq!(
            exportable_der_bytes(&db, "hub-test").await.unwrap(),
            Some(decoded(OWN_B64))
        );
    }

    /// **Provenance stays honest**: the delegated row says the control plane put it there, never a
    /// user id. `uploaded_by` is what the read-only «firmando con» surface shows, and claiming a
    /// human uploaded ERPlora's key would be a lie in the one field that exists to answer «who».
    #[tokio::test]
    async fn the_delegated_row_is_attributed_to_the_control_plane() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(17));
        let db = db_ready().await;

        set_delegated(&db, "hub-test", DELEGATED_B64, "pw-del", 4).await.unwrap();
        let st = slot_status(&db, "hub-test", CertificateKind::Delegated).await.unwrap();
        assert_eq!(st["uploaded_by"], json!(CONTROL_PLANE));
        assert!(!st["uploaded_by"].as_str().unwrap().contains("hub_user"));
    }

    /// ⚠️ **PIN of the inconsistency hub#319 has to close, deliberately left standing here.**
    ///
    /// `status()["present"]` still describes the OWN slot, and three readers depend on it (the
    /// dispatcher's fiscal gate via `RequestContext::has_certificate`, the paged-query path, and the
    /// ⛔ arm of `setup_status` — hub#370). hub#317 makes a delegated-only hub POSSIBLE for the first
    /// time, and in that state all of them answer «no certificate»: the checklist shows ⛔ **and**
    /// the gate refuses to issue. They agree, so the checklist is not lying — it is uniformly
    /// stricter than ADR-0202 §2.1 wants, and fails CLOSED.
    ///
    /// Moving `present` here alone is what would start the lie (the module's `build_identity` still
    /// demands the core marker), so hub#319 moves all of them at once. This test exists so that day
    /// is a conscious edit and not a surprise: when #319 lands, it must be updated, not deleted.
    #[tokio::test]
    async fn until_hub319_a_delegated_only_hub_still_reports_no_certificate() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(18));
        let db = db_ready().await;

        set_delegated(&db, "hub-test", DELEGATED_B64, "pw-del", 4).await.unwrap();

        let st = status(&db, "hub-test").await.unwrap();
        assert_eq!(st["present"], json!(false), "hub#319 aún no ha movido el gate");
        // Y sin embargo el core YA sabe con cuál firmaría: la pieza que falta es solo el gate.
        assert_eq!(st["active"], json!("delegated"));
        assert_eq!(active_kind(&db, "hub-test").await.unwrap(), Some(CertificateKind::Delegated));
    }
}
