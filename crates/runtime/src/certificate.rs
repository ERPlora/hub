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

/// **What the certificate IS** — which is the axis the AEAT segregates its VERI\*FACTU service by
/// (ADR-0202 §2.1 — hub#470).
///
/// Not to be confused with [`CertificateKind`], which says **whose** it is. `delegated` means «the
/// control plane handed it down», and that says nothing about the container: the `.p12` ERPlora
/// invoices with today is a *representative* certificate, and had it been uploaded to the delegated
/// slot the whole delegated fleet would have POSTed to the seal's entry point and been rejected,
/// record by record, with nothing to warn anybody. Two words for two questions, so the confusion
/// cannot come back.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CertificateType {
    /// **Sello de entidad** — an eIDAS electronic *seal*: it belongs to a legal person and hangs off
    /// no human's DNI. Enters the AEAT through `www10` / `prewww10`.
    Seal,
    /// A certificate carrying a **natural person** (the taxpayer, or somebody representing them).
    /// Enters through `www1` / `prewww1` — where every certificate in the field goes today.
    Representative,
}

impl CertificateType {
    /// Value stored in `_hub_certificate.certificate_type` and travelled across the border. Stable:
    /// it is a column of a deployed hub AND a field of the control plane's payload.
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Seal => "seal",
            Self::Representative => "representative",
        }
    }

    /// Reads back what [`as_str`](Self::as_str) wrote. `None` for anything else — including a
    /// spelling a NEWER control plane might invent. An unrecognised word is «this build cannot tell
    /// what that is», never a guess, and [`resolve_certificate_type`] treats it as if nothing had
    /// been declared.
    pub fn parse(s: &str) -> Option<Self> {
        [Self::Seal, Self::Representative]
            .into_iter()
            .find(|t| t.as_str() == s)
    }
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
/// **`certificate_type` travels in the SAME upsert too**, and for the same reason (hub#470): it
/// describes THESE bytes, so a row holding a new `.p12` under the previous container's type would
/// pick the AEAT entry point of a certificate it no longer has. `None` writes the empty string —
/// «this hub cannot tell», which routes to the holder's door like everything else it cannot vouch
/// for.
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
    certificate_type: Option<CertificateType>,
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
    p.insert(
        "certificate_type".into(),
        json!(certificate_type.map(CertificateType::as_str).unwrap_or("")),
    );
    db.execute(
        "INSERT INTO _hub_certificate \
           (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by, cert_version, \
            certificate_type) \
         VALUES (:hub_id, :kind, :pkcs12_b64, :password, :uploaded_at, :uploaded_by, \
                 :cert_version, :certificate_type) \
         ON CONFLICT (hub_id, kind) DO UPDATE SET \
           pkcs12_b64 = excluded.pkcs12_b64, password = excluded.password, \
           uploaded_at = excluded.uploaded_at, uploaded_by = excluded.uploaded_by, \
           cert_version = excluded.cert_version, \
           certificate_type = excluded.certificate_type",
        &p,
    )
    .await?;
    Ok(())
}

/// **What the hub concludes a container is, from the two things that can say so** (hub#470).
///
/// `declared` is what the control plane put in the payload; `derived` is what the hub read out of
/// the bytes it is about to store. The whole point of having both is that this function can catch
/// them disagreeing — that is the failure this issue exists for, and it is the same shape as the
/// three that came before it in this chain (#317 the wrong slot, #318 the wrong format, #319 who
/// signed): one certificate fact crossing the border and meaning something different on each side.
///
/// | declared | derived | result |
/// |---|---|---|
/// | seal | seal | that type |
/// | seal | representative | **`Err`** — contested |
/// | seal | *(unclassifiable)* | the declaration stands |
/// | *(none)* | representative | the bytes answer |
/// | *(none)* | *(none)* | unknown → the holder's door |
///
/// **Contested is an error and not a "pick one" on purpose.** The caller ([`set_delegated`]) turns
/// it into a refusal to install, so the hub keeps the certificate it already had — which is a
/// certificate that WORKS — and the operator gets a loud line naming both values. Every other way
/// out is worse: trusting the declaration can send the fleet to a door where every record is
/// rejected (ADR-0189 — a rejection is not a link, so each one is corrected by hand), and trusting
/// the derivation silently overrides the control plane with a heuristic.
///
/// **A declaration this build cannot spell is treated as no declaration**, not as an error: a newer
/// control plane inventing a third word must not brick the hubs that have not been redeployed yet.
/// It degrades to the derived value, and to the holder's door if there is none.
pub(crate) fn resolve_certificate_type(
    declared: Option<CertificateType>,
    derived: Option<CertificateType>,
) -> Result<Option<CertificateType>> {
    match (declared, derived) {
        (Some(d), Some(v)) if d != v => Err(RuntimeError::Certificate(format!(
            "el plano de control declara un certificado `{}` pero el contenedor que ha servido es \
             `{}` (hub#470): no se instala — la puerta de la AEAT la elige el TIPO, y con el \
             equivocado la AEAT rechaza todos los registros, uno a uno",
            d.as_str(),
            v.as_str(),
        ))),
        (Some(d), _) => Ok(Some(d)),
        (None, derived) => Ok(derived),
    }
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
///
/// # `declared_type` is the border's word, and it gets checked (hub#470)
///
/// The control plane says what it is handing down (`certificate_type` in the payload); this function
/// **derives the same fact from the container itself** and refuses to install when the two disagree
/// (see [`resolve_certificate_type`]). Deriving alone would let a heuristic override the control
/// plane; declaring alone is what hub#470 is about — the premise that the delegated slot holds a
/// Sello de Entidad never travelled, and ERPlora's real `.p12` is a representative certificate.
///
/// A refusal leaves the hub exactly as it was, which is the recoverable failure: it keeps signing
/// with the certificate it already had while the operator sees the line. Installing a container
/// whose type nobody agrees on is the expensive one — every record POSTed to the wrong door comes
/// back rejected, and a rejection is not a link in the chain (ADR-0189), so they are corrected one
/// by one, by hand.
///
/// `None` = an older control plane that declares nothing. Then the bytes answer on their own; there
/// is nothing to contradict.
pub async fn set_delegated(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    pkcs12_b64: &str,
    password: &str,
    version: i64,
    declared_type: Option<&str>,
) -> Result<()> {
    let derived = derive_certificate_type(pkcs12_b64, password);
    let certificate_type =
        resolve_certificate_type(declared_type.and_then(CertificateType::parse), derived)?;
    set(
        db,
        hub_id,
        CertificateKind::Delegated,
        pkcs12_b64,
        password,
        CONTROL_PLANE,
        Some(version),
        certificate_type,
    )
    .await
}

/// [`certificate_type_from_der`] over a base64 container, with **every failure collapsing into
/// «cannot tell»** (hub#470).
///
/// Unreadable base64, a container that is not a PKCS#12, a wrong passphrase, a build without
/// OpenSSL (Android): none of them is an answer about the certificate's type, and none of them is
/// this function's problem to report. Storing an unusable container has always been allowed — it
/// fails later, loudly, at the TLS handshake — and turning that into a refusal HERE would be a new
/// way for the control plane to lock a hub out of a rotation.
///
/// «Cannot tell» is the safe value: it routes to the holder's entry point, where every certificate
/// in the field already goes.
pub(crate) fn derive_certificate_type(pkcs12_b64: &str, password: &str) -> Option<CertificateType> {
    use base64::Engine as _;
    let der = base64::engine::general_purpose::STANDARD
        .decode(pkcs12_b64.trim())
        .ok()?;
    certificate_type_from_der(&der, password).ok().flatten()
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
/// # ⚠️ `present` is NOT «can this hub issue?» — that question is [`can_sign`] (hub#319)
///
/// The two used to be the same read, and hub#316/#317 warned that they would have to part company.
/// They did: `present` answers «did the owner upload a certificate?» and stays on the **own** slot,
/// while «can this hub issue?» — the ADR-0203 gate on [`crate::commands::execute`] and
/// [`crate::queries::execute_page`], and the ⛔ arm of [`crate::setup_status`] (hub#370) — now reads
/// [`can_sign`], which accepts the delegated certificate too.
///
/// So a delegated-only hub reports `present: false` **and** invoices normally. That is not a
/// contradiction: nothing of the customer's is loaded (this screen has nothing to show and nothing
/// to delete), and ERPlora signs on their behalf. What the module shows as «firmando con: ERPlora»
/// comes from `active`/`slots` below, never from `present`.
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
/// **«Can this hub issue?» is this function's [`can_sign`] shape** — the dispatcher gate and the ⛔
/// arm of the setup checklist both go through it (hub#319). Use `can_sign` when the question is
/// *whether*, and this one when it is *which*.
pub async fn active_kind(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Option<CertificateKind>> {
    Ok(occupied_slots(db, hub_id).await?.first().map(|(k, _)| *k))
}

/// **What the certificate this hub signs with IS** — the axis that picks the AEAT entry point
/// (ADR-0202 §2.1 — hub#470). `None` when the hub holds no certificate, or holds one it cannot
/// vouch for.
///
/// Reads the column that [`set`] wrote in the same upsert as the bytes. When that column is empty
/// it **derives the answer from the container itself**, and that is the whole migration story for
/// the hubs that were already deployed when the column arrived: their rows have no type, and
/// nothing backfills one. A blind backfill would be a guess about what somebody's certificate is,
/// and this chain has already been bitten by exactly that (hub#436, where the tempting backfill
/// would have handed one person another's access). Parsing the bytes the row actually holds is a
/// reading, not a guess — and it costs a decrypt plus a PKCS#12 parse **only** until the next
/// upload or refetch writes the column.
///
/// It is deliberately NOT written back. Self-healing on a read path would put a write behind every
/// config read of the fiscal engine, and the two legitimate writers (the owner's upload and the
/// control plane's refetch) already converge every hub that is doing anything at all.
///
/// ⚠️ Unlike [`active_kind`], answering this **can** decrypt the container (only for a row with no
/// type stored). Nothing about the key leaves the core: what crosses to a module is one of the two
/// words of [`CertificateType::as_str`].
pub async fn active_type(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Option<CertificateType>> {
    let Some(kind) = active_kind(db, hub_id).await? else {
        return Ok(None);
    };
    slot_type(db, hub_id, kind).await
}

/// [`active_type`] for ONE slot, whichever it is.
pub async fn slot_type(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    kind: CertificateKind,
) -> Result<Option<CertificateType>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("kind".into(), json!(kind.as_str()));
    let res = db
        .query(
            "SELECT certificate_type FROM _hub_certificate \
             WHERE hub_id = :hub_id AND kind = :kind AND pkcs12_b64 <> '' LIMIT 1",
            &p,
        )
        .await?;
    let Some(row) = res.rows.into_iter().next() else {
        return Ok(None);
    };
    let stored = row
        .get("certificate_type")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    if let Some(known) = CertificateType::parse(stored) {
        return Ok(Some(known));
    }
    // Empty (a row written before the column existed) or a word this build does not know: read the
    // container. `load_pkcs12` already decrypts and un-base64s it.
    let Some((der, password)) = load_pkcs12(db, hub_id, kind).await? else {
        return Ok(None);
    };
    Ok(certificate_type_from_der(&der, &password).unwrap_or(None))
}

/// **«Can this hub issue?» — the one function that answers it** (ADR-0202 §2.1 — hub#319).
///
/// `true` when [`active_kind`] finds a certificate to sign with, i.e. the business uploaded its own
/// **or** the control plane handed one down. A hub holding only the delegated certificate can
/// invoice: ERPlora signs on its behalf, which is the whole point of the delegated slot.
///
/// # Why this is a function and not three copies of `active_kind(..).is_some()`
///
/// The question has three askers and they must never diverge:
///
/// 1. [`crate::commands::execute`] and 2. [`crate::queries::execute_page`], which fill
///    [`RequestContext::has_certificate`] — the second arm of the ADR-0203 fiscal gate; and
/// 3. [`crate::setup_status`], the ⛔ arm of the onboarding checklist (hub#370).
///
/// ⛔ *asserts that the dispatcher is going to refuse the operation*. If the checklist and the gate
/// answer this differently, one of them is lying: either a ⛔ that blocks a screen while the sale
/// goes through, or a rejection nobody warned about. They used to read
/// `status(..)["present"]`, which describes the **own** slot only — correct while nothing could
/// write a delegated certificate (hub#316), and wrong the moment hub#317 made that possible. Giving
/// the question a NAME is what makes agreement structural instead of a comment asking three call
/// sites to remember each other.
///
/// **Not the same question as `status(..)["present"]`, which stays where it is.** That one describes
/// what the owner uploaded in Ajustes → Negocio — what that screen shows and what its delete button
/// removes — and it must keep saying `false` for a hub that only holds ERPlora's certificate.
///
/// [`RequestContext::has_certificate`]: crate::registry::RequestContext::has_certificate
pub async fn can_sign(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<bool> {
    Ok(active_kind(db, hub_id).await?.is_some())
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

/// Expiry (notAfter) of the certificate this hub **signs with**, as ISO `YYYY-MM-DD`. `Ok(None)` if
/// there is none. This is the one the user is shown: it describes the certificate in use.
pub async fn expiry(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Option<String>> {
    match active_kind(db, hub_id).await? {
        Some(kind) => slot_expiry(db, hub_id, kind).await,
        None => Ok(None),
    }
}

/// Expiry (notAfter) of ONE slot, **whether or not it is the one that signs** (hub#317).
///
/// Needed because the two questions are genuinely different. What the hub REPORTS to the control
/// plane (`reported_cert_not_after`, ADR-0202 §2.5) is always the **delegated** slot's date — the
/// SaaS compares it against the `not_after` of the `.p12` it custodies to spot a hub that is not
/// really running our certificate. A hub with its own certificate uploaded still has to report its
/// delegated fallback, so answering with [`expiry`] there would report a date that has nothing to do
/// with ERPlora's and light up the mismatch alarm across the healthy half of the fleet.
pub async fn slot_expiry(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    kind: CertificateKind,
) -> Result<Option<String>> {
    match load_pkcs12(db, hub_id, kind).await? {
        Some((der, password)) => expiry_from_der(&der, &password),
        None => Ok(None),
    }
}

/// Expiry of ONE slot as the **instant** it really is (RFC 3339 UTC), not the day it falls on
/// (hub#318).
///
/// [`slot_expiry`] truncates to `YYYY-MM-DD` because that is what a person reads. What the hub
/// REPORTS to the control plane cannot be truncated: the fleet panel compares
/// `reported_cert_not_after` against the `not_after` the SaaS extracted from the container IT
/// custodies (`x509_cert.not_valid_after_utc`) for **equality**, and flags any hub that differs as
/// «not running our certificate» (ADR-0202 §2.6). A date comes back as midnight, so it would differ
/// for every certificate that does not expire at exactly 00:00:00 — that is, all of them — and the
/// alarm would fire on the entire healthy fleet.
///
/// Same shape of mistake hub#317 fixed by reading the wrong SLOT; this one is the format axis.
pub async fn slot_expiry_instant(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    kind: CertificateKind,
) -> Result<Option<String>> {
    match load_pkcs12(db, hub_id, kind).await? {
        Some((der, password)) => expiry_instant_from_der(&der, &password),
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

/// **What a PKCS#12 in DER IS** — an entity seal or a natural person's certificate (hub#470).
/// `Ok(None)` = this build cannot tell, which is an answer and not a failure.
///
/// `pub` for the same reason as its neighbours: the PKCS#12 crypto lives in the core, in ONE place,
/// and a caller holding a container in memory (a fresh upload, a just-fetched delegated key) asks
/// here instead of growing its own parser.
#[cfg(not(target_os = "android"))]
pub fn certificate_type_from_der(der: &[u8], password: &str) -> Result<Option<CertificateType>> {
    ensure_legacy_provider();
    let pkcs12 = openssl::pkcs12::Pkcs12::from_der(der)
        .map_err(|e| RuntimeError::Certificate(format!("PKCS#12 inválido: {e}")))?;
    let parsed = pkcs12
        .parse2(password)
        .map_err(|e| RuntimeError::Certificate(format!("PKCS#12 (¿contraseña incorrecta?): {e}")))?;
    let Some(cert) = parsed.cert else {
        return Ok(None);
    };
    let cert_der = cert
        .to_der()
        .map_err(|e| RuntimeError::Certificate(format!("certificado: {e}")))?;
    Ok(certificate_type_of_x509(&cert_der, cert.subject_name()))
}

/// Stub Android: sin OpenSSL no se puede parsear el `.p12` (ver `Cargo.toml`).
#[cfg(target_os = "android")]
pub fn certificate_type_from_der(
    _der: &[u8],
    _password: &str,
) -> Result<Option<CertificateType>> {
    Ok(None)
}

/// The eIDAS `QcType` statement (ETSI EN 319 412-5), DER-encoded, as it appears inside the
/// `qcStatements` extension (`1.3.6.1.5.5.7.1.3`) of a qualified certificate.
///
/// `0.4.0.1862.1.6.2` = *eSeal*: the certificate belongs to a legal person and hangs off nobody's
/// DNI — the Sello de Entidad the AEAT routes to `www10`.
#[cfg(not(target_os = "android"))]
const QC_TYPE_ESEAL_DER: [u8; 9] = [0x06, 0x07, 0x04, 0x00, 0x8E, 0x46, 0x01, 0x06, 0x02];

/// `0.4.0.1862.1.6.1` = *eSign*: a natural person's signature certificate — the taxpayer or their
/// representative, which the AEAT routes to `www1`.
#[cfg(not(target_os = "android"))]
const QC_TYPE_ESIGN_DER: [u8; 9] = [0x06, 0x07, 0x04, 0x00, 0x8E, 0x46, 0x01, 0x06, 0x01];

/// Classifies an X.509 certificate from its DER and its subject.
///
/// # Two signals, and only one of them can conclude «seal»
///
/// 1. **The eIDAS `QcType`** ([`QC_TYPE_ESEAL_DER`] / [`QC_TYPE_ESIGN_DER`]). This is the standard
///    answer and the only positive evidence of a seal: FNMT's *Sello de entidad* is a qualified
///    eSeal and carries it, and so does every qualified certificate issued in the EU since EN
///    319 412 became the norm.
/// 2. **A natural person in the subject** (`givenName` + `surname`). Only ever concludes
///    *representative*, never *seal*.
///
/// **The asymmetry is the safety property.** Concluding «seal» takes evidence; the ABSENCE of
/// evidence must never open the seal's door, because that is the expensive mistake — a fleet POSTing
/// to `www10` gets every record rejected and a rejection is not a link in the chain (ADR-0189).
/// Falling back to «cannot tell» sends the certificate to `www1`, which is where every certificate
/// in the field already goes.
///
/// A container declaring **both** QcTypes contradicts itself, and a self-contradictory certificate
/// is not resolved by looking at its subject: it answers «cannot tell» outright.
///
/// # Why the DER is scanned instead of walked
///
/// The `openssl` crate exposes typed accessors for a handful of extensions and no generic one, and
/// `qcStatements` is not among them. Scanning for the 9-byte DER encoding of the OID is exact in the
/// direction that matters: a false positive needs those nine bytes to appear verbatim somewhere else
/// in the certificate, and a false NEGATIVE degrades to «cannot tell» — the safe side, and the side
/// the control plane's declaration covers ([`resolve_certificate_type`]).
#[cfg(not(target_os = "android"))]
fn certificate_type_of_x509(
    cert_der: &[u8],
    subject: &openssl::x509::X509NameRef,
) -> Option<CertificateType> {
    let seal = contains_subslice(cert_der, &QC_TYPE_ESEAL_DER);
    let esign = contains_subslice(cert_der, &QC_TYPE_ESIGN_DER);
    match (seal, esign) {
        (true, false) => Some(CertificateType::Seal),
        (false, true) => Some(CertificateType::Representative),
        // Declares both: the container contradicts itself and nothing is inferred from it.
        (true, true) => None,
        (false, false) => subject_holds_a_natural_person(subject).then_some(CertificateType::Representative),
    }
}

/// Does the subject name a HUMAN? `givenName` + `surname` are what a Spanish *certificado de
/// representante* carries and what a *sello de entidad* never does.
///
/// **Both, not either.** An organisation whose name happens to land in one of the two must not be
/// read as a person; and every certificate that really belongs to somebody carries the pair.
#[cfg(not(target_os = "android"))]
fn subject_holds_a_natural_person(subject: &openssl::x509::X509NameRef) -> bool {
    use openssl::nid::Nid;
    let has = |nid: Nid| {
        subject
            .entries_by_nid(nid)
            .any(|e| !e.data().as_slice().is_empty())
    };
    has(Nid::GIVENNAME) && has(Nid::SURNAME)
}

/// `haystack.contains(needle)` for bytes — `[u8]` has no such method on stable.
#[cfg(not(target_os = "android"))]
fn contains_subslice(haystack: &[u8], needle: &[u8]) -> bool {
    haystack.windows(needle.len()).any(|w| w == needle)
}

/// `notAfter` de un PKCS#12 en DER como **instante** RFC 3339 UTC (`2028-06-10T09:12:33Z`).
/// Gemelo de [`expiry_from_der`] sin truncar el día — ver [`slot_expiry_instant`] para el porqué.
#[cfg(not(target_os = "android"))]
pub fn expiry_instant_from_der(der: &[u8], password: &str) -> Result<Option<String>> {
    ensure_legacy_provider();
    let pkcs12 = openssl::pkcs12::Pkcs12::from_der(der)
        .map_err(|e| RuntimeError::Certificate(format!("PKCS#12 inválido: {e}")))?;
    let parsed = pkcs12
        .parse2(password)
        .map_err(|e| RuntimeError::Certificate(format!("PKCS#12 (¿contraseña incorrecta?): {e}")))?;
    match parsed.cert {
        Some(cert) => Ok(asn1_time_to_rfc3339(&cert.not_after().to_string())),
        None => Ok(None),
    }
}

/// Stub Android: sin OpenSSL no se puede leer la caducidad del `.p12` (ver `Cargo.toml`).
#[cfg(target_os = "android")]
pub fn expiry_instant_from_der(_der: &[u8], _password: &str) -> Result<Option<String>> {
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

/// "Jun 10 09:12:33 2028 GMT" → "2028-06-10T09:12:33Z". `None` si el formato no casa.
///
/// La fecha sale de [`asn1_time_to_iso`] —una sola lectura del día, para que las dos respuestas no
/// puedan separarse— y solo se le añade la hora, que en el `Display` de OpenSSL es siempre UTC
/// (`GMT`). Una hora con una forma que no reconocemos devuelve `None`: mejor «no lo sé» que un
/// instante inventado, que es lo que el panel de flota compararía por igualdad.
#[cfg(not(target_os = "android"))]
fn asn1_time_to_rfc3339(s: &str) -> Option<String> {
    let date = asn1_time_to_iso(s)?;
    let time = s.split_whitespace().nth(2)?;
    let shaped = time.len() == 8
        && time.as_bytes().iter().enumerate().all(|(i, b)| {
            if i == 2 || i == 5 {
                *b == b':'
            } else {
                b.is_ascii_digit()
            }
        });
    shaped.then(|| format!("{date}T{time}Z"))
}

#[cfg(all(test, not(target_os = "android")))]
mod asn1_tests {
    use super::{asn1_time_to_iso, asn1_time_to_rfc3339};
    #[test]
    fn parses_openssl_asn1_time() {
        assert_eq!(asn1_time_to_iso("Jun 10 00:00:00 2028 GMT").as_deref(), Some("2028-06-10"));
        assert_eq!(asn1_time_to_iso("Mar 3 23:59:59 2027 GMT").as_deref(), Some("2027-03-03"));
        assert_eq!(asn1_time_to_iso("garbage").as_deref(), None);
    }

    /// El instante conserva la HORA. Truncarla haría que el hub reportase medianoche y que el panel
    /// de flota (ADR-0202 §2.6, igualdad exacta) marcase «no está firmando con nuestro certificado»
    /// a todo hub sano.
    #[test]
    fn parses_the_instant_and_not_only_the_day() {
        assert_eq!(
            asn1_time_to_rfc3339("Jun 10 09:12:33 2028 GMT").as_deref(),
            Some("2028-06-10T09:12:33Z")
        );
        // Día de un dígito: OpenSSL mete DOS espacios, y el instante tiene que salir igual de bien.
        assert_eq!(
            asn1_time_to_rfc3339("Mar  3 23:59:59 2027 GMT").as_deref(),
            Some("2027-03-03T23:59:59Z")
        );
    }

    /// Una forma que no reconocemos vale `None`, nunca un instante inventado: la fecha que se
    /// reporta se compara por IGUALDAD contra la que custodia el SaaS.
    #[test]
    fn an_unrecognised_shape_is_not_guessed_into_an_instant() {
        assert_eq!(asn1_time_to_rfc3339("garbage").as_deref(), None);
        assert_eq!(asn1_time_to_rfc3339("Jun 10 9:12:33 2028 GMT").as_deref(), None);
        assert_eq!(asn1_time_to_rfc3339("Jun 10 091233 2028 GMT").as_deref(), None);
        assert_eq!(asn1_time_to_rfc3339("Jun 10 09-12-33 2028 GMT").as_deref(), None);
    }

    /// **Las dos lecturas no pueden separarse**: la fecha es exactamente el prefijo del instante.
    /// Si alguna vez divergen, lo que el usuario ve y lo que el hub reporta describirían días
    /// distintos del mismo certificado.
    #[test]
    fn the_day_is_the_prefix_of_the_instant() {
        for raw in ["Jun 10 09:12:33 2028 GMT", "Mar  3 23:59:59 2027 GMT"] {
            let day = asn1_time_to_iso(raw).unwrap();
            let instant = asn1_time_to_rfc3339(raw).unwrap();
            assert_eq!(instant[..day.len()], day);
            assert_eq!(&instant[day.len()..day.len() + 1], "T");
            assert!(instant.ends_with('Z'));
        }
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
        set(&db, "hub-test", CertificateKind::Own, "QkFTRTY0", "secret", "hub_user:admin", None, None)
            .await
            .unwrap();
        let st = status(&db, "hub-test").await.unwrap();
        assert_eq!(st["present"], json!(true));
        assert_eq!(st["uploaded_by"], json!("hub_user:admin"));
        // status NO expone bytes ni password.
        assert!(st.get("pkcs12_b64").is_none() && st.get("password").is_none());
        // Reemplazar (upsert, no duplica).
        set(&db, "hub-test", CertificateKind::Own, "TkVX", "p2", "hub_user:admin", None, None).await.unwrap();
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
            None, None,
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

        set(&db, "hub-test", CertificateKind::Delegated, DELEGATED_B64, "erplora-pw", "cloud", None, None)
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
        set(&db, "hub-test", CertificateKind::Own, original_b64, "mi-contraseña-real", "hub_user:admin", None, None)
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

        set(&db, "hub-test", CertificateKind::Own, OWN_B64, "no-debe-viajar", "hub_user:admin", None, None)
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

        let err = set(&db, "hub-test", CertificateKind::Own, "cGtjczEy", "password", "hub_user:admin", None, None)
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
            set(&db, "hub-test", CertificateKind::Own, "cGtjczEy", "password", "hub_user:admin", None, None)
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

        set(&db, "hub-test", CertificateKind::Own, OWN_B64, "pw-own", "hub_user:admin", None, None).await.unwrap();
        set(&db, "hub-test", CertificateKind::Delegated, DELEGATED_B64, "pw-del", "cloud", None, None)
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
    ///
    /// Desde hub#319 el recorrido comprueba también [`can_sign`] en cada paso: «con cuál firmo» y
    /// «¿puedo facturar?» son la misma respuesta en dos formas, y aquí es donde se ve que no se
    /// separan — borrar el certificado propio NO deja al hub sin poder facturar.
    #[tokio::test]
    async fn the_own_certificate_wins_and_the_delegated_one_is_the_fallback() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(9));
        let db = db_ready().await;

        assert_eq!(active_kind(&db, "hub-test").await.unwrap(), None, "sin certificado no firma nada");
        assert!(!can_sign(&db, "hub-test").await.unwrap(), "…y por tanto no puede facturar");

        set(&db, "hub-test", CertificateKind::Delegated, DELEGATED_B64, "pw-del", "cloud", None, None)
            .await
            .unwrap();
        assert_eq!(
            active_kind(&db, "hub-test").await.unwrap(),
            Some(CertificateKind::Delegated),
            "sin certificado propio firma el delegado"
        );
        assert!(
            can_sign(&db, "hub-test").await.unwrap(),
            "y con el delegado el hub SÍ factura: ERPlora firma en su nombre (hub#319)"
        );

        set(&db, "hub-test", CertificateKind::Own, OWN_B64, "pw-own", "hub_user:admin", None, None).await.unwrap();
        assert_eq!(
            active_kind(&db, "hub-test").await.unwrap(),
            Some(CertificateKind::Own),
            "el propio GANA en cuanto se sube — sin preguntar ni reconfigurar"
        );
        assert!(can_sign(&db, "hub-test").await.unwrap());

        delete(&db, "hub-test", CertificateKind::Own).await.unwrap();
        assert_eq!(
            active_kind(&db, "hub-test").await.unwrap(),
            Some(CertificateKind::Delegated),
            "y al borrarlo se vuelve al delegado: el hub no se queda sin poder facturar"
        );
        assert!(
            can_sign(&db, "hub-test").await.unwrap(),
            "borrar el propio no puede dejar al hub sin facturar"
        );
    }

    /// `GET /api/business/certificate` keeps meaning what it meant: `present` is the certificate the
    /// owner uploaded. Offering to delete ERPlora's key would be a lie in a button.
    #[tokio::test]
    async fn status_reports_the_own_slot_and_says_which_one_signs() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(10));
        let db = db_ready().await;

        set(&db, "hub-test", CertificateKind::Delegated, DELEGATED_B64, "pw-del", "cloud", None, None)
            .await
            .unwrap();
        let st = status(&db, "hub-test").await.unwrap();
        assert_eq!(st["present"], json!(false), "el negocio no ha subido el suyo");
        assert_eq!(st["active"], json!("delegated"), "pero el hub firma con el de ERPlora");
        assert_eq!(st["slots"]["delegated"]["present"], json!(true));
        assert_eq!(st["slots"]["own"]["present"], json!(false));

        set(&db, "hub-test", CertificateKind::Own, OWN_B64, "pw-own", "hub_user:admin", None, None).await.unwrap();
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
        set(&db, "hub-test", CertificateKind::Delegated, DELEGATED_B64, "pw-del", "cloud", None, None)
            .await
            .unwrap();
        assert_eq!(
            exportable_der_bytes(&db, "hub-test").await.unwrap(),
            None,
            "la clave privada de ERPlora no sale del hub"
        );

        // Con los dos, sale el PROPIO — nunca el delegado.
        set(&db, "hub-test", CertificateKind::Own, OWN_B64, "pw-own", "hub_user:admin", None, None).await.unwrap();
        let der = exportable_der_bytes(&db, "hub-test").await.unwrap().expect("el propio sí viaja");
        assert_eq!(der, decoded(OWN_B64));
        assert_ne!(der, decoded(DELEGATED_B64));
    }

    /// The selection rule and the export rule are DIFFERENT questions, and this is the case that
    /// proves it: the hub signs with the delegated certificate, and still exports none.
    ///
    /// hub#319 is the change that could most easily blur the two — once this hub counts as «has a
    /// certificate» ([`can_sign`]) for the dispatcher and the checklist, it must NOT start putting
    /// ERPlora's private key into a bundle that travels to other people's hubs.
    #[tokio::test]
    async fn signing_with_the_delegated_certificate_does_not_make_it_exportable() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(12));
        let db = db_ready().await;

        set(&db, "hub-test", CertificateKind::Delegated, DELEGATED_B64, "pw-del", "cloud", None, None)
            .await
            .unwrap();
        assert_eq!(active_kind(&db, "hub-test").await.unwrap(), Some(CertificateKind::Delegated));
        assert!(can_sign(&db, "hub-test").await.unwrap(), "este hub SÍ puede facturar…");
        assert_eq!(
            exportable_der_bytes(&db, "hub-test").await.unwrap(),
            None,
            "…y aun así no exporta certificado alguno"
        );
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

        set_delegated(&db, "hub-test", DELEGATED_B64, "pw-del", 4, None).await.unwrap();

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

        let err = set_delegated(&db, "hub-test", DELEGATED_B64, "pw-del", 4, None).await.unwrap_err();
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

        set_delegated(&db, "hub-test", DELEGATED_B64, "pw-del", 4, None).await.unwrap();
        assert_eq!(delegated_version(&db, "hub-test").await.unwrap(), Some(4));

        // Una rotación reemplaza bytes Y número a la vez: nunca queda el número viejo sobre los
        // bytes nuevos (ni al revés), que es justo lo que rompería la convergencia.
        set_delegated(&db, "hub-test", OWN_B64, "pw-rotated", 5, None).await.unwrap();
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

        set_delegated(&db, "hub-test", DELEGATED_B64, "pw-del", 4, None).await.unwrap();
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

        set_delegated(&db, "hub-test", DELEGATED_B64, "pw-del", 7, None).await.unwrap();
        set(&db, "hub-test", CertificateKind::Own, OWN_B64, "pw-own", "hub_user:admin", None, None).await.unwrap();

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

        set_delegated(&db, "hub-test", DELEGATED_B64, "pw-del", 4, None).await.unwrap();
        assert_eq!(
            exportable_der_bytes(&db, "hub-test").await.unwrap(),
            None,
            "la clave privada de ERPlora no sale del hub ni llegando por el plano de control"
        );

        set(&db, "hub-test", CertificateKind::Own, OWN_B64, "pw-own", "hub_user:admin", None, None).await.unwrap();
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

        set_delegated(&db, "hub-test", DELEGATED_B64, "pw-del", 4, None).await.unwrap();
        let st = slot_status(&db, "hub-test", CertificateKind::Delegated).await.unwrap();
        assert_eq!(st["uploaded_by"], json!(CONTROL_PLANE));
        assert!(!st["uploaded_by"].as_str().unwrap().contains("hub_user"));
    }

    /// **The expiry the hub REPORTS is the delegated slot's, even when the own one is signing.**
    ///
    /// The heartbeat's `reported_cert_not_after` describes the delegated slot and only that
    /// (ADR-0202 §2.5: «un hub con certificado `own` puesto sigue reportando su slot delegado»), and
    /// the control plane compares it against the `not_after` of the `.p12` IT custodies to catch a
    /// hub that is not really running our certificate. Answering with the active slot's date would
    /// make every hub that has its own certificate report a date that has nothing to do with
    /// ERPlora's — and the mismatch alarm would fire on the whole healthy half of the fleet.
    ///
    /// The two certificates here are deliberately asymmetric: the delegated one is a REAL PKCS#12
    /// (so it has a readable date) and the own one is not (so it has none). That is what makes the
    /// difference between «read the active slot» and «read the delegated slot» visible at all.
    #[tokio::test]
    async fn the_delegated_expiry_is_reported_even_when_the_own_certificate_signs() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(20));
        let db = db_ready().await;

        let (delegated_b64, delegated_pw, expected_date) = real_pkcs12(365);
        set_delegated(&db, "hub-test", &delegated_b64, &delegated_pw, 4, None).await.unwrap();
        set(&db, "hub-test", CertificateKind::Own, OWN_B64, "pw-own", "hub_user:admin", None, None)
            .await
            .unwrap();

        // El propio MANDA para firmar (regla de hub#316) y no es un `.p12` legible, así que la
        // caducidad "activa" no se sabe (`.ok().flatten()` = lo que el llamador observa).
        assert_eq!(active_kind(&db, "hub-test").await.unwrap(), Some(CertificateKind::Own));
        assert_eq!(expiry(&db, "hub-test").await.ok().flatten(), None);
        // ...pero la del slot delegado sí, y es la que se reporta.
        assert_eq!(
            slot_expiry(&db, "hub-test", CertificateKind::Delegated).await.unwrap(),
            Some(expected_date)
        );
    }

    /// **The reported instant and the displayed day describe the SAME moment.** `slot_expiry` is
    /// what a person reads and `slot_expiry_instant` is what the control plane compares by
    /// equality, so the day has to be the instant's prefix — over a real container, not only over
    /// the string parser.
    #[tokio::test]
    async fn the_reported_instant_and_the_displayed_day_agree_on_the_same_slot() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(21));
        let db = db_ready().await;

        let (delegated_b64, delegated_pw, expected_day) = real_pkcs12(365);
        set_delegated(&db, "hub-test", &delegated_b64, &delegated_pw, 4, None).await.unwrap();

        let instant = slot_expiry_instant(&db, "hub-test", CertificateKind::Delegated)
            .await
            .unwrap()
            .expect("el instante del contenedor");
        assert!(
            instant.starts_with(&expected_day),
            "el instante {instant} no empieza por el día {expected_day}"
        );
        assert!(instant.ends_with('Z'), "el instante tiene que ser UTC: {instant}");
        // Y lleva la HORA: si fuese la fecha truncada, el panel de flota lo leería como medianoche.
        assert!(instant.len() > expected_day.len() + 1, "sin hora: {instant}");

        // Un slot vacío no inventa fecha.
        assert_eq!(
            slot_expiry_instant(&db, "hub-test", CertificateKind::Own).await.unwrap(),
            None
        );
    }

    /// A self-signed PKCS#12 that really parses, so a test can assert a DATE and not just a `None`.
    /// Returns `(base64 of the container, password, expected ISO notAfter)`.
    fn real_pkcs12(valid_for_days: u32) -> (String, String, String) {
        use base64::Engine as _;
        use openssl::asn1::Asn1Time;
        use openssl::hash::MessageDigest;
        use openssl::pkey::PKey;
        use openssl::rsa::Rsa;
        use openssl::x509::{X509NameBuilder, X509};

        ensure_legacy_provider();
        let key = PKey::from_rsa(Rsa::generate(2048).unwrap()).unwrap();
        let mut name = X509NameBuilder::new().unwrap();
        name.append_entry_by_text("CN", "ERPlora test").unwrap();
        let name = name.build();

        let not_after = Asn1Time::days_from_now(valid_for_days).unwrap();
        let mut cert = X509::builder().unwrap();
        cert.set_version(2).unwrap();
        cert.set_subject_name(&name).unwrap();
        cert.set_issuer_name(&name).unwrap();
        cert.set_pubkey(&key).unwrap();
        cert.set_not_before(&Asn1Time::days_from_now(0).unwrap()).unwrap();
        cert.set_not_after(&not_after).unwrap();
        cert.sign(&key, MessageDigest::sha256()).unwrap();
        let cert = cert.build();

        let password = "delegated-pw".to_string();
        let der = openssl::pkcs12::Pkcs12::builder()
            .name("erplora")
            .pkey(&key)
            .cert(&cert)
            .build2(&password)
            .unwrap()
            .to_der()
            .unwrap();

        let expected = asn1_time_to_iso(&not_after.to_string()).expect("fecha legible");
        (
            base64::engine::general_purpose::STANDARD.encode(&der),
            password,
            expected,
        )
    }

    /// **A hub whose only certificate is the delegated one CAN sign — and the screen that shows the
    /// business's own certificate still says there is none** (ADR-0202 §2.1 — hub#319).
    ///
    /// This replaces the pin hub#316 left standing here
    /// (`until_hub319_a_delegated_only_hub_still_reports_no_certificate`), and the edit is the point
    /// of the issue rather than a side effect. Until now the three readers of «can this hub issue?»
    /// looked at `status()["present"]`, i.e. the OWN slot, so a delegated-only hub was refused by
    /// the dispatcher AND shown ⛔: they agreed, so nothing lied — the runtime was simply stricter
    /// than the ADR, and failed closed.
    ///
    /// The two questions are now told apart by NAME, which is what stops them drifting again:
    ///
    /// * [`can_sign`] — «can this hub issue?». Own **or** delegated. Moved, all three readers at once.
    /// * `status()["present"]` — «did the owner upload a certificate in Ajustes → Negocio?». Own
    ///   only, deliberately unchanged: that screen shows it and its delete button removes it, so
    ///   answering `true` would offer the customer a certificate they cannot see and a button that
    ///   deletes a key that is not theirs.
    #[tokio::test]
    async fn a_delegated_only_hub_can_sign_while_the_own_slot_stays_empty() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(18));
        let db = db_ready().await;

        set_delegated(&db, "hub-test", DELEGATED_B64, "pw-del", 4, None).await.unwrap();

        assert!(
            can_sign(&db, "hub-test").await.unwrap(),
            "ERPlora's certificate signs on the hub's behalf: this hub can invoice"
        );
        assert_eq!(active_kind(&db, "hub-test").await.unwrap(), Some(CertificateKind::Delegated));

        let st = status(&db, "hub-test").await.unwrap();
        assert_eq!(
            st["present"],
            json!(false),
            "Ajustes → Negocio still has nothing of the customer's to show or delete"
        );
        assert_eq!(st["active"], json!("delegated"), "…but the hub knows what it signs with");
    }

    /// **`can_sign` is `active_kind` and can never be anything else.** The two are one answer split
    /// in two shapes («whether» and «which»), and every state of the two slots has to agree — a hub
    /// that «can sign» with nothing selected, or one that has a selection but «cannot sign», is the
    /// contradiction the three readers would then propagate.
    #[tokio::test]
    async fn can_sign_and_active_kind_agree_in_every_state_of_the_two_slots() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(24));
        let db = db_ready().await;

        for (own, delegated, expected) in [
            (false, false, None),
            (true, false, Some(CertificateKind::Own)),
            (false, true, Some(CertificateKind::Delegated)),
            (true, true, Some(CertificateKind::Own)),
        ] {
            delete(&db, "hub-test", CertificateKind::Own).await.unwrap();
            delete(&db, "hub-test", CertificateKind::Delegated).await.unwrap();
            if own {
                set(&db, "hub-test", CertificateKind::Own, OWN_B64, "pw", "hub_user:a", None, None)
                    .await
                    .unwrap();
            }
            if delegated {
                set_delegated(&db, "hub-test", DELEGATED_B64, "pw", 4, None).await.unwrap();
            }

            let kind = active_kind(&db, "hub-test").await.unwrap();
            assert_eq!(kind, expected, "own={own} delegated={delegated}");
            assert_eq!(
                can_sign(&db, "hub-test").await.unwrap(),
                kind.is_some(),
                "own={own} delegated={delegated}: «whether» and «which» must be the same answer"
            );
        }
    }

    // ── hub#470: what the certificate IS, declared at the border and checked against the bytes ───

    /// What a test certificate should look like. Named rather than a pile of booleans because each
    /// shape stands for a real certificate that exists in the wild.
    enum Shape {
        /// A qualified **eSeal** — an FNMT *Sello de entidad*. Carries the eIDAS `QcType` eSeal
        /// statement and no natural person.
        EntitySeal,
        /// A qualified **eSign** for a natural person — a *certificado de representante*, which is
        /// what ERPlora's own `.p12` is.
        QualifiedRepresentative,
        /// No `qcStatements` at all, but a human in the subject: the older Spanish certificates,
        /// and anything issued outside the EN 319 412 profile.
        PersonWithoutQcStatements,
        /// Neither. A self-signed `CN=…` — what every fixture in this file has always built, and
        /// what the hub genuinely cannot classify.
        Anonymous,
        /// Declares BOTH `QcType`s. Does not exist honestly; it is what a malformed or crafted
        /// container looks like, and it must not be resolved by falling back to the subject.
        ContradictsItself,
    }

    /// Builds a real, parseable PKCS#12 of a given [`Shape`]. Returns `(base64, password)`.
    ///
    /// Everything is generated here: no `.p12` is committed to the repository, and in particular not
    /// ERPlora's real one — the container this whole issue is about holds the private key that
    /// identifies the company before the AEAT.
    fn pkcs12_shaped(shape: Shape) -> (String, String) {
        use base64::Engine as _;
        use openssl::asn1::{Asn1Object, Asn1OctetString, Asn1Time};
        use openssl::hash::MessageDigest;
        use openssl::pkey::PKey;
        use openssl::rsa::Rsa;
        use openssl::x509::{X509Extension, X509NameBuilder, X509};

        ensure_legacy_provider();
        let key = PKey::from_rsa(Rsa::generate(2048).unwrap()).unwrap();

        let mut name = X509NameBuilder::new().unwrap();
        name.append_entry_by_text("CN", "ERPlora test").unwrap();
        if matches!(
            shape,
            Shape::QualifiedRepresentative | Shape::PersonWithoutQcStatements
        ) {
            name.append_entry_by_text("GN", "NOMBRE").unwrap();
            name.append_entry_by_text("SN", "APELLIDO").unwrap();
        }
        let name = name.build();

        let mut cert = X509::builder().unwrap();
        cert.set_version(2).unwrap();
        cert.set_subject_name(&name).unwrap();
        cert.set_issuer_name(&name).unwrap();
        cert.set_pubkey(&key).unwrap();
        cert.set_not_before(&Asn1Time::days_from_now(0).unwrap()).unwrap();
        cert.set_not_after(&Asn1Time::days_from_now(365).unwrap()).unwrap();

        // The `qcStatements` extension (RFC 3739 `1.3.6.1.5.5.7.1.3`), hand-encoded: a SEQUENCE of
        // QCStatement, each `{ statementId, statementInfo }`. Here one statement — ETSI's
        // `id-etsi-qcs-QcType` (`0.4.0.1862.1.6`) — whose info is a SEQUENCE OF the type OIDs.
        let qc_types: &[&[u8]] = match shape {
            Shape::EntitySeal => &[&QC_TYPE_ESEAL_DER],
            Shape::QualifiedRepresentative => &[&QC_TYPE_ESIGN_DER],
            Shape::ContradictsItself => &[&QC_TYPE_ESEAL_DER, &QC_TYPE_ESIGN_DER],
            Shape::PersonWithoutQcStatements | Shape::Anonymous => &[],
        };
        if !qc_types.is_empty() {
            let types: Vec<u8> = qc_types.concat();
            let type_seq = der_sequence(&types);
            // statementId = 0.4.0.1862.1.6
            let statement_id = [0x06u8, 0x06, 0x04, 0x00, 0x8E, 0x46, 0x01, 0x06];
            let mut statement = statement_id.to_vec();
            statement.extend_from_slice(&type_seq);
            let extension_value = der_sequence(&der_sequence(&statement));

            let oid = Asn1Object::from_str("1.3.6.1.5.5.7.1.3").unwrap();
            let value = Asn1OctetString::new_from_bytes(&extension_value).unwrap();
            let ext = X509Extension::new_from_der(&oid, false, &value).unwrap();
            cert.append_extension(ext).unwrap();
        }

        cert.sign(&key, MessageDigest::sha256()).unwrap();
        let cert = cert.build();

        let password = "shape-pw".to_string();
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

    /// Wraps DER contents in a SEQUENCE. Only short forms are needed here (test certificates), so
    /// the length is the one-byte encoding up to 127 and the two-byte `0x81` form beyond it.
    fn der_sequence(contents: &[u8]) -> Vec<u8> {
        let mut out = vec![0x30u8];
        if contents.len() < 0x80 {
            out.push(contents.len() as u8);
        } else {
            out.push(0x81);
            out.push(contents.len() as u8);
        }
        out.extend_from_slice(contents);
        out
    }

    fn type_of(shape: Shape) -> Option<CertificateType> {
        let (b64, pw) = pkcs12_shaped(shape);
        derive_certificate_type(&b64, &pw)
    }

    /// **An entity seal is recognised by its eIDAS `QcType`** — the standard, and the only positive
    /// evidence that opens the AEAT's `www10` door.
    #[test]
    fn an_entity_seal_is_recognised_by_its_eidas_qc_type() {
        assert_eq!(type_of(Shape::EntitySeal), Some(CertificateType::Seal));
    }

    /// A qualified certificate for a natural person is a representative's, wherever it was issued.
    #[test]
    fn a_qualified_natural_person_certificate_is_a_representative() {
        assert_eq!(
            type_of(Shape::QualifiedRepresentative),
            Some(CertificateType::Representative)
        );
    }

    /// Without `qcStatements`, a human in the subject still answers the question. This is the older
    /// Spanish profile, and it is the shape most likely to turn up in the field.
    #[test]
    fn a_person_in_the_subject_is_a_representative_even_without_qc_statements() {
        assert_eq!(
            type_of(Shape::PersonWithoutQcStatements),
            Some(CertificateType::Representative)
        );
    }

    /// 🔒 **The absence of evidence is never read as a seal.** A container with nothing to go on
    /// answers «cannot tell», which routes to the holder's entry point — where every certificate in
    /// the field already goes. Concluding «seal» from «no person found» would send an unclassifiable
    /// certificate to `www10` and have the AEAT reject every record it signs.
    #[test]
    fn a_container_with_nothing_to_go_on_is_not_guessed_to_be_a_seal() {
        assert_eq!(type_of(Shape::Anonymous), None);
    }

    /// A container declaring both `QcType`s contradicts itself, and a contradiction is not resolved
    /// by looking somewhere else: it answers «cannot tell» outright.
    #[test]
    fn a_container_declaring_both_qc_types_is_not_classified() {
        assert_eq!(type_of(Shape::ContradictsItself), None);
    }

    /// Garbage in, «cannot tell» out — never an error and never a guess. Storing an unusable
    /// container has always been allowed (it fails at the TLS handshake, loudly); refusing it here
    /// would be a new way for the control plane to lock a hub out of a rotation.
    #[test]
    fn an_unreadable_container_answers_that_it_cannot_tell() {
        assert_eq!(derive_certificate_type("not base64 at all!!", "pw"), None);
        assert_eq!(derive_certificate_type("QUJD", "pw"), None); // valid base64, not a PKCS#12
        let (b64, _pw) = pkcs12_shaped(Shape::EntitySeal);
        assert_eq!(
            derive_certificate_type(&b64, "the-wrong-password"),
            None,
            "a wrong passphrase is not an answer about the type"
        );
    }

    /// 🔴 **The bug hub#470 closes, at the door the control plane writes through.** A REPRESENTATIVE
    /// container installed in the DELEGATED slot — precisely what would happen the day ERPlora's own
    /// `.p12` (`…_R_…`) were uploaded to the control plane — must not make the hub behave like a
    /// seal. Before this the slot WAS the answer, so every delegated hub would have POSTed to
    /// `www10` and had all of its records rejected, one by one (ADR-0189).
    #[tokio::test]
    async fn a_representative_container_in_the_delegated_slot_is_not_a_seal() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(20));
        let db = db_ready().await;
        let (b64, pw) = pkcs12_shaped(Shape::QualifiedRepresentative);

        set_delegated(&db, "hub-test", &b64, &pw, 4, None).await.unwrap();

        assert_eq!(
            active_kind(&db, "hub-test").await.unwrap(),
            Some(CertificateKind::Delegated),
            "the slot is unchanged: it still says whose the certificate is"
        );
        assert_eq!(
            active_type(&db, "hub-test").await.unwrap(),
            Some(CertificateType::Representative),
            "and the TYPE comes from the container, not from the slot"
        );
    }

    /// The other half: a real seal in that slot IS a seal, so hub#320's fix survives.
    #[tokio::test]
    async fn a_seal_in_the_delegated_slot_is_a_seal() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(21));
        let db = db_ready().await;
        let (b64, pw) = pkcs12_shaped(Shape::EntitySeal);
        set_delegated(&db, "hub-test", &b64, &pw, 4, Some("seal")).await.unwrap();
        assert_eq!(
            active_type(&db, "hub-test").await.unwrap(),
            Some(CertificateType::Seal)
        );
    }

    /// 🔒 **A declaration that contradicts the container is refused, and the hub keeps what it had.**
    ///
    /// This is the loud, recoverable failure of hub#470: the hub goes on signing with a certificate
    /// that WORKS while the operator gets the line naming both values. Installing it instead would
    /// route every record to the wrong door, and a rejection is not a link in the chain (ADR-0189),
    /// so each one is corrected by hand.
    #[tokio::test]
    async fn a_declaration_that_contradicts_the_container_is_refused() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(22));
        let db = db_ready().await;
        let (good_b64, good_pw) = pkcs12_shaped(Shape::EntitySeal);
        set_delegated(&db, "hub-test", &good_b64, &good_pw, 4, Some("seal")).await.unwrap();

        let (bad_b64, bad_pw) = pkcs12_shaped(Shape::QualifiedRepresentative);
        let err = set_delegated(&db, "hub-test", &bad_b64, &bad_pw, 5, Some("seal"))
            .await
            .unwrap_err()
            .to_string();
        assert!(err.contains("seal") && err.contains("representative"), "{err}");

        assert_eq!(
            delegated_version(&db, "hub-test").await.unwrap(),
            Some(4),
            "the refused install must not have touched the certificate the hub was using"
        );
        assert_eq!(
            active_type(&db, "hub-test").await.unwrap(),
            Some(CertificateType::Seal)
        );
    }

    /// **An older control plane declares nothing, and the bytes answer alone.** This is what every
    /// hub sees until the SaaS half of hub#470 is deployed, and it must install exactly as before.
    #[tokio::test]
    async fn an_undeclared_certificate_gets_its_type_from_the_container() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(23));
        let db = db_ready().await;
        let (b64, pw) = pkcs12_shaped(Shape::EntitySeal);
        set_delegated(&db, "hub-test", &b64, &pw, 4, None).await.unwrap();
        assert_eq!(
            active_type(&db, "hub-test").await.unwrap(),
            Some(CertificateType::Seal)
        );
    }

    /// **When the hub cannot classify the container, the border's word stands.** This is what keeps
    /// a REAL Sello de Entidad working on a build whose classifier does not recognise it: the
    /// declaration can only ever be contradicted by a positive reading, never by silence.
    #[tokio::test]
    async fn a_declaration_stands_when_the_hub_cannot_classify_the_container() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(24));
        let db = db_ready().await;
        let (b64, pw) = pkcs12_shaped(Shape::Anonymous);
        set_delegated(&db, "hub-test", &b64, &pw, 4, Some("seal")).await.unwrap();
        assert_eq!(
            active_type(&db, "hub-test").await.unwrap(),
            Some(CertificateType::Seal)
        );
    }

    /// **A word this build does not know is treated as no declaration, not as an error.** A newer
    /// control plane inventing a third type must not brick the hubs that have not been redeployed.
    #[tokio::test]
    async fn a_declaration_this_build_cannot_spell_degrades_to_the_container() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(25));
        let db = db_ready().await;
        let (b64, pw) = pkcs12_shaped(Shape::QualifiedRepresentative);
        set_delegated(&db, "hub-test", &b64, &pw, 4, Some("qualified-eseal-v2"))
            .await
            .unwrap();
        assert_eq!(
            active_type(&db, "hub-test").await.unwrap(),
            Some(CertificateType::Representative)
        );
    }

    /// The resolution table, on its own, including the branch no `set_delegated` test can reach
    /// twice over: agreement.
    #[test]
    fn the_resolution_table_is_exactly_these_five_answers() {
        use CertificateType::{Representative, Seal};
        assert_eq!(
            resolve_certificate_type(Some(Seal), Some(Seal)).unwrap(),
            Some(Seal)
        );
        assert_eq!(
            resolve_certificate_type(Some(Representative), Some(Representative)).unwrap(),
            Some(Representative)
        );
        assert_eq!(
            resolve_certificate_type(Some(Representative), None).unwrap(),
            Some(Representative)
        );
        assert_eq!(
            resolve_certificate_type(None, Some(Seal)).unwrap(),
            Some(Seal)
        );
        assert_eq!(resolve_certificate_type(None, None).unwrap(), None);
        // Contested, in BOTH directions: neither side gets to be the one that wins by default.
        assert!(resolve_certificate_type(Some(Seal), Some(Representative)).is_err());
        assert!(resolve_certificate_type(Some(Representative), Some(Seal)).is_err());
    }

    /// **The business's own certificate gets its type from its own bytes too**, so a business that
    /// uploads an entity seal reaches `www10` without anybody configuring anything. There is no
    /// border here: the owner uploads the container directly, so there is nothing to cross-check.
    #[tokio::test]
    async fn the_business_certificate_gets_its_type_from_its_own_bytes() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(26));
        let db = db_ready().await;
        let (seal_b64, seal_pw) = pkcs12_shaped(Shape::EntitySeal);
        set(
            &db,
            "hub-test",
            CertificateKind::Own,
            &seal_b64,
            &seal_pw,
            "hub_user:admin",
            None,
            derive_certificate_type(&seal_b64, &seal_pw),
        )
        .await
        .unwrap();
        assert_eq!(
            active_type(&db, "hub-test").await.unwrap(),
            Some(CertificateType::Seal)
        );
    }

    /// **The type follows the slot that SIGNS.** Uploading the business's own certificate takes over
    /// from the delegated one on the next signature (ADR-0202 §2.1), and the entry point has to move
    /// with it — otherwise a hub would present one certificate at the door of another.
    #[tokio::test]
    async fn the_type_reported_is_the_one_of_the_certificate_that_signs() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(27));
        let db = db_ready().await;
        let (seal_b64, seal_pw) = pkcs12_shaped(Shape::EntitySeal);
        set_delegated(&db, "hub-test", &seal_b64, &seal_pw, 4, Some("seal")).await.unwrap();
        assert_eq!(
            active_type(&db, "hub-test").await.unwrap(),
            Some(CertificateType::Seal)
        );

        let (own_b64, own_pw) = pkcs12_shaped(Shape::QualifiedRepresentative);
        set(
            &db,
            "hub-test",
            CertificateKind::Own,
            &own_b64,
            &own_pw,
            "hub_user:admin",
            None,
            derive_certificate_type(&own_b64, &own_pw),
        )
        .await
        .unwrap();
        assert_eq!(
            active_type(&db, "hub-test").await.unwrap(),
            Some(CertificateType::Representative),
            "the own certificate wins the fallback, so its type is the one that picks the door"
        );

        delete(&db, "hub-test", CertificateKind::Own).await.unwrap();
        assert_eq!(
            active_type(&db, "hub-test").await.unwrap(),
            Some(CertificateType::Seal),
            "and deleting it hands the hub back to the delegated one, door included"
        );
    }

    /// A hub with no certificate has no type either.
    #[tokio::test]
    async fn a_hub_with_no_certificate_has_no_type() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(28));
        let db = db_ready().await;
        assert_eq!(active_type(&db, "hub-test").await.unwrap(), None);
        assert_eq!(
            slot_type(&db, "hub-test", CertificateKind::Delegated).await.unwrap(),
            None
        );
    }

    /// 🔒 **A row written before the column existed is READ, never guessed.** The hubs that were
    /// already deployed have `certificate_type = ''` and nothing backfills it (that would be
    /// guessing what somebody's certificate is — the trap v19/hub#436 walked around). Parsing the
    /// container the row actually holds is a reading, and it is what keeps those hubs on the right
    /// door until their next upload or refetch writes the column.
    #[tokio::test]
    async fn a_row_without_a_stored_type_is_classified_from_its_own_container() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(29));
        let db = db_ready().await;
        let (b64, pw) = pkcs12_shaped(Shape::EntitySeal);
        set_delegated(&db, "hub-test", &b64, &pw, 4, Some("seal")).await.unwrap();

        // Exactly the state of a hub deployed before v21: bytes, no type.
        let mut p = Params::new();
        p.insert("hub_id".into(), json!("hub-test"));
        db.execute(
            "UPDATE _hub_certificate SET certificate_type = '' WHERE hub_id = :hub_id",
            &p,
        )
        .await
        .unwrap();

        assert_eq!(
            active_type(&db, "hub-test").await.unwrap(),
            Some(CertificateType::Seal),
            "the stored container answers when the column does not"
        );
    }

    /// **The type is written in the SAME upsert as the bytes** (like `cert_version`, v16). A
    /// rotation that replaced the container but left the previous type behind would pick the AEAT
    /// door of a certificate the hub no longer holds.
    #[tokio::test]
    async fn replacing_the_container_replaces_its_type_in_the_same_write() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(30));
        let db = db_ready().await;
        let (seal_b64, seal_pw) = pkcs12_shaped(Shape::EntitySeal);
        set_delegated(&db, "hub-test", &seal_b64, &seal_pw, 4, Some("seal")).await.unwrap();

        let (rep_b64, rep_pw) = pkcs12_shaped(Shape::QualifiedRepresentative);
        set_delegated(&db, "hub-test", &rep_b64, &rep_pw, 5, Some("representative"))
            .await
            .unwrap();

        assert_eq!(
            active_type(&db, "hub-test").await.unwrap(),
            Some(CertificateType::Representative)
        );
        assert_eq!(delegated_version(&db, "hub-test").await.unwrap(), Some(5));
    }

    /// The two words are a CONTRACT (a column of a deployed hub and a field of the control plane's
    /// payload), so they are pinned literally and they round-trip.
    #[test]
    fn the_type_names_are_stable_and_round_trip() {
        assert_eq!(CertificateType::Seal.as_str(), "seal");
        assert_eq!(CertificateType::Representative.as_str(), "representative");
        for t in [CertificateType::Seal, CertificateType::Representative] {
            assert_eq!(CertificateType::parse(t.as_str()), Some(t));
        }
        for unknown in ["", " ", "Seal", "seal ", "sello", "own", "delegated", "future"] {
            assert_eq!(CertificateType::parse(unknown), None, "{unknown:?}");
        }
    }
}
