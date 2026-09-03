//! The hub's fiscal certificates, in the core (ADR-0079, ADR-0202 §2.1).
//!
//! The PKCS#12 that gives the hub a fiscal identity (VeriFactu today, B2B tomorrow) is a **HUB**
//! resource, not a module one. It lives in the system table `_hub_certificate`. A module only USES
//! it if the `certificate` capability was granted (the dispatcher's gate demands it before the
//! native handler); the private key never crosses into the WASM sandbox.
//!
//! # ONE slot: the business's own certificate (hub#1435)
//!
//! A hub holds at most one certificate — [`Own`](CertificateKind::Own), the BUSINESS's, uploaded by
//! its owner in Ajustes → Negocio (`PUT /api/business/certificate`). Renewing it is the customer's
//! job, as it always was.
//!
//! **There used to be a second slot**, `delegated`: ERPlora's own `.p12`, handed down by the control
//! plane so that we could sign before the AEAT on a hub's behalf (ADR-0202 §2, hub#316/#317). It is
//! **retired** (ADR-0320 point 8). The key no longer travels: the Hub builds the XML and the fiscal
//! cell transmits it with ERPlora's Seal, which never leaves the platform. The SaaS shut its half in
//! saas#1435 phase 2 — model, endpoint and columns — and this is the hub half.
//!
//! ⚠️ **`delegated` still names the transmission ROUTE, and that one is alive**: [`ROUTE_DELEGATED`]
//! is «ERPlora files on the taxpayer's behalf, through the cell», which is where every hub with no
//! own certificate goes (ADR-0320 §1). The slot is gone; the route is the point of ADR-0320. See
//! `tests/delegated_certificate_slot_retired_hub1435.rs`, which fails if a cleanup takes both.
//!
//! # What may leave the hub
//!
//! [`exportable_der_bytes`] is the only door through which raw `.p12` bytes reach anything outside
//! this module (the blueprint/backup export — `crates/server/src/export_import.rs`), and it hands
//! out only the slots that [`CertificateKind::may_leave_the_hub`] allows. A bundle is a file: it is
//! downloaded, published to the catalogue and imported into hubs that are not this one, so the
//! question «may this slot travel?» has to be answered per slot and not assumed.
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

/// Which certificate a row is (ADR-0202 §2.1 — hub#316; one slot since hub#1435).
///
/// A SLOT, not a preference: nothing reads this column to decide which certificate signs. That is
/// [`active_kind`]'s job, and it answers from the order of [`SLOTS`].
///
/// ⚠️ Not to be confused with [`ROUTE_DELEGATED`]: that is the transmission ROUTE and it is alive.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CertificateKind {
    /// The BUSINESS's own certificate — uploaded by its owner in Ajustes → Negocio (ADR-0079/0081,
    /// still in force). Theirs to renew, theirs to delete, and the only one their backup carries.
    Own,
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

    /// Reads back what [`as_str`](Self::as_str) wrote. `None` for anything else. An unrecognised
    /// word is «this build cannot tell what that is», never a guess, and it degrades to the holder's
    /// AEAT entry point like every other container this hub cannot vouch for.
    pub fn parse(s: &str) -> Option<Self> {
        [Self::Seal, Self::Representative]
            .into_iter()
            .find(|t| t.as_str() == s)
    }
}

/// Every slot a hub can hold, **in selection order**. One since hub#1435 retired the delegated
/// certificate; it stays an array because it is the RULE, not a convenience.
///
/// [`active_kind`] walks it to pick the certificate that signs and [`exportable_der_bytes`] walks it
/// to pick the certificate that may travel, so «which one wins» and «which one may leave» can never
/// drift apart into two half-remembered lists. A slot added here has to answer both questions.
pub const SLOTS: [CertificateKind; 1] = [CertificateKind::Own];

impl CertificateKind {
    /// Value stored in `_hub_certificate.kind`. Stable: it is a column of a deployed hub.
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Own => "own",
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
    ///
    /// **It survives the retirement of the second slot on purpose** (hub#1435). With one variant the
    /// answer is always `true`, which looks like a predicate that has stopped deciding anything —
    /// but this is the ONE path where getting it wrong publishes a private key to whoever opens the
    /// zip, and the `match` is exhaustive so that a slot added later cannot inherit «travels» by
    /// omission. The cost is six lines; the failure it prevents is the most expensive one here.
    pub const fn may_leave_the_hub(self) -> bool {
        match self {
            Self::Own => true,
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

/// Stores/replaces the certificate of ONE slot (upsert on `(hub_id, kind)`).
/// `by` = `hub_user:<id>`, the owner who uploaded it.
///
/// **`pub(crate)` on purpose (hub#317).** There is exactly ONE door into this table and it pins its
/// slot: [`crate::Runtime::set_business_certificate`] pins [`Own`](CertificateKind::Own). Keeping the
/// generic writer inside the crate is what makes «the slot is explicit» a fact rather than a doc
/// comment. The second door — the control plane's, which wrote the retired `delegated` slot — was
/// removed with it in hub#1435.
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
    certificate_type: Option<CertificateType>,
) -> Result<()> {
    let key = load_master_key()?.ok_or_else(|| {
        RuntimeError::Certificate(format!(
            "cifrado de secretos no configurado: define {} antes de subir un certificado nuevo \
             (ADR-0016, ERPlora/hub#114) — nunca se guarda un .p12/contraseña en claro",
            secret_box::MASTER_KEY_ENV
        ))
    })?;
    let pkcs12_b64_enc = secret_box::encrypt(&key, pkcs12_b64)
        .map_err(|e| certificate_error("cifrando el .p12", e))?;
    let password_enc = secret_box::encrypt(&key, password)
        .map_err(|e| certificate_error("cifrando la contraseña", e))?;

    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("kind".into(), json!(kind.as_str()));
    p.insert("pkcs12_b64".into(), json!(pkcs12_b64_enc));
    p.insert("password".into(), json!(password_enc));
    p.insert("uploaded_at".into(), json!(now_rfc3339()));
    p.insert("uploaded_by".into(), json!(by));
    p.insert(
        "certificate_type".into(),
        json!(certificate_type.map(CertificateType::as_str).unwrap_or("")),
    );
    db.execute(
        // `cert_version` is NOT written: it numbered the control plane's central ROTATION of the
        // retired delegated certificate (ADR-0202 §2.5), and nothing rotates a certificate centrally
        // any more. The column stays — a system migration retires structure by leaving it alone
        // (ADR-0269) — and stays NULL for every row written from here on.
        "INSERT INTO _hub_certificate \
           (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by, certificate_type) \
         VALUES (:hub_id, :kind, :pkcs12_b64, :password, :uploaded_at, :uploaded_by, \
                 :certificate_type) \
         ON CONFLICT (hub_id, kind) DO UPDATE SET \
           pkcs12_b64 = excluded.pkcs12_b64, password = excluded.password, \
           uploaded_at = excluded.uploaded_at, uploaded_by = excluded.uploaded_by, \
           certificate_type = excluded.certificate_type",
        &p,
    )
    .await?;
    Ok(())
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
/// # ⚠️ `present` is NOT «can this hub issue?» — that question is [`can_transmit`] (hub#319)
///
/// The two used to be the same read, and hub#316/#317 warned that they would have to part company.
/// They did: `present` answers «did the owner upload a certificate?» and stays on the **own** slot,
/// while «can this hub issue?» — the ADR-0203 gate on [`crate::commands::execute`] and
/// [`crate::queries::execute_page`], and the ⛔ arm of [`crate::setup_status`] (hub#370) — reads
/// [`can_transmit`], which accepts the cell road too.
///
/// So a hub on the cell road reports `present: false` **and** invoices normally. That is not a
/// contradiction: nothing of the customer's is loaded (this screen has nothing to show and nothing
/// to delete), and ERPlora files on their behalf. What the module shows as «firmando con: ERPlora»
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
            json!({ CertificateKind::Own.as_str(): own }),
        );
        o.insert("active".into(), json!(active));
        // Which of the two EXCLUSIVE routes to the AEAT this hub is on (ADR-0320 §1 — hub#1314).
        // Named here instead of left to the screen to derive from `active`: Ajustes → Negocio picks
        // the route with it, and `fiscal_profile::go_live` decides whether the Anexo I is required
        // with the same `route_of`. A screen that deduced it on its own would be a second rule.
        o.insert(
            "transmission_route".into(),
            json!(route_of(occupied.first().map(|(k, _)| *k))),
        );
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
/// **«Can this hub issue?» is NOT this function** — that is [`can_transmit`], which the dispatcher
/// gate and the ⛔ arm of the setup checklist both go through (hub#319, hub#1489) and which the
/// cell road satisfies without any certificate at all. Use `can_transmit` when the question is
/// *whether*, and this one when it is *which certificate*.
pub async fn active_kind(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Option<CertificateKind>> {
    Ok(occupied_slots(db, hub_id).await?.first().map(|(k, _)| *k))
}

/// **The two EXCLUSIVE ways a hub's records reach the tax authority** (ADR-0320 §1 — hub#1314).
///
/// [`ROUTE_OWN`] — the taxpayer signs and files with their own certificate; nothing is delegated to
/// anybody, so no representation grant (Anexo I) exists or is needed. [`ROUTE_DELEGATED`] — ERPlora
/// files ON BEHALF of the taxpayer with its Sello, which is exactly what the signed Anexo I
/// authorises. One or the other, never both: the SaaS already picks like this
/// (`select_transmission_route`, `apps/dashboard/fiscal/services/verifactu_gateway.py`), and the
/// hub used to demand the grant on both.
///
/// Stable words: they cross to the browser and the screen programs against them.
pub const ROUTE_OWN: &str = "own";
pub const ROUTE_DELEGATED: &str = "delegated";

/// [`ROUTE_OWN`]/[`ROUTE_DELEGATED`] from the slot that signs — **the rule, in one place**.
///
/// A `const fn` over the already-resolved slot instead of a second query, so [`status`] (which has
/// the occupied slots in hand) and [`transmission_route`] (which has a hub id) answer through the
/// same match. Two call sites deriving «is this the own one?» separately is how the screen and the
/// go-live end up disagreeing about which route a business is on.
///
/// **No certificate at all is [`ROUTE_DELEGATED`]**, deliberately: it is the route the fiscal cell
/// serves (ADR-0320), and the one the screen must offer by default. Answering `own` there would send
/// somebody with no `.p12` to a form they cannot finish.
///
/// 🔒 This is the function hub#1435 had to leave alone. The delegated SLOT was retired with it; the
/// delegated ROUTE is what ADR-0320 put in its place, and collapsing the two would put every hub
/// without a certificate on the `own` route — demanding a `.p12` they do not have and skipping the
/// Anexo I the cell does require. `tests/delegated_certificate_slot_retired_hub1435.rs` pins it.
pub const fn route_of(active: Option<CertificateKind>) -> &'static str {
    match active {
        Some(CertificateKind::Own) => ROUTE_OWN,
        None => ROUTE_DELEGATED,
    }
}

/// [`route_of`] for a hub: which of the two routes its records take right now.
pub async fn transmission_route(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<&'static str> {
    Ok(route_of(active_kind(db, hub_id).await?))
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

/// **Whose is the certificate that signs today** (hub#1478), or `None` when this hub holds none —
/// or holds one whose subject names no entity.
///
/// No column stores this: unlike the type, nothing has ever written the holder down, so the answer
/// is read from the container every time. That costs a decrypt plus a PKCS#12 parse, the same
/// price [`identity`] already pays on the very same path — and the alternative, a stored column,
/// would be one more place able to disagree with the bytes, which is the whole family of defects
/// #317/#318/#319/#470 came from.
///
/// Nothing about the key leaves the core: what crosses to a module is the pair of public fields of
/// [`CertificateHolder`].
pub async fn active_holder(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Option<CertificateHolder>> {
    let Some(kind) = active_kind(db, hub_id).await? else {
        return Ok(None);
    };
    slot_holder(db, hub_id, kind).await
}

/// [`active_holder`] for ONE slot, whichever it is.
pub async fn slot_holder(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    kind: CertificateKind,
) -> Result<Option<CertificateHolder>> {
    let Some((der, password)) = load_pkcs12(db, hub_id, kind).await? else {
        return Ok(None);
    };
    holder_from_der(&der, &password)
}

/// **«Can this hub issue?» — the one function that answers it** (ADR-0203, ADR-0320 §1 — hub#319,
/// hub#1489).
///
/// The question is **«has this hub got a ROUTE?»**, and ADR-0320 gave it two exclusive ones:
///
/// * [`ROUTE_OWN`] — the business uploaded its own `.p12` and files with it ([`active_kind`]); or
/// * [`ROUTE_DELEGATED`] — ERPlora files on its behalf through the fiscal cell, which from this
///   hub's side needs the enrolled machine identity of ADR-0419
///   ([`crate::gateway_identity::is_enrolled`]).
///
/// # Why it is not «has it got a certificate?»
///
/// It used to be, and that was invisible while the delegated route ALSO meant holding a `.p12`:
/// the control plane handed ERPlora's certificate down into a local slot, so a delegated hub
/// answered `true` by accident. hub#1435 retired that slot — no private key of ERPlora's reaches
/// the fleet any more — and the hole came out (hub#1489): a hub that transmits perfectly through
/// the cell was refused its own sales, painted ⛔ on the checklist and never reached
/// [`crate::fiscal_profile::FiscalStatus::Ready`], so its go-live died in `NOT_READY` with the
/// Anexo I signed. Asking about the *certificate* answered a question nobody was asking; the route
/// is what the gate is actually protecting.
///
/// **The own certificate is checked FIRST and short-circuits**, so a hub on the direct route never
/// pays for the second read — and a deployment whose gateway table cannot be read does not lose
/// the answer it already had.
///
/// # Why this is a function and not three copies of the same expression
///
/// The question has three askers and they must never diverge:
///
/// 1. [`crate::commands::execute`] and 2. [`crate::queries::execute_page`], which fill
///    [`RequestContext::has_certificate`] — the second arm of the ADR-0203 fiscal gate; and
/// 3. [`crate::setup_status`], the ⛔ arm of the onboarding checklist (hub#370), plus
///    [`crate::fiscal_profile::refresh`], which computes `READY` from it.
///
/// ⛔ *asserts that the dispatcher is going to refuse the operation*. If the checklist and the gate
/// answer this differently, one of them is lying: either a ⛔ that blocks a screen while the sale
/// goes through, or a rejection nobody warned about. Giving the question a NAME is what makes
/// agreement structural instead of a comment asking four call sites to remember each other —
/// which is also why this rename is the whole fix: the compiler visited every asker.
///
/// **Not the same question as `status(..)["present"]`, which stays where it is.** That one describes
/// what the owner uploaded in Ajustes → Negocio — what that screen shows and what its delete button
/// removes — and it must keep saying `false` for a hub that files through the cell. Nor is it
/// [`transmission_route`], which answers *which* of the two roads, never *whether* there is one.
///
/// [`RequestContext::has_certificate`]: crate::registry::RequestContext::has_certificate
pub async fn can_transmit(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<bool> {
    if active_kind(db, hub_id).await?.is_some() {
        return Ok(true);
    }
    crate::gateway_identity::is_enrolled(db, hub_id).await
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

    let der = base64::engine::general_purpose::STANDARD
        .decode(b64.trim())
        .map_err(|e| {
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
pub async fn exportable_der_bytes(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<Option<Vec<u8>>> {
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
        RuntimeError::Certificate(
            "no hay certificado del negocio cargado (Ajustes → Negocio)".into(),
        )
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
    let parsed = pkcs12.parse2(password).map_err(|e| {
        RuntimeError::Certificate(format!("PKCS#12 (¿contraseña incorrecta?): {e}"))
    })?;
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
        &cert
            .to_pem()
            .map_err(|e| RuntimeError::Certificate(format!("certificado: {e}")))?,
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
    let parsed = pkcs12.parse2(password).map_err(|e| {
        RuntimeError::Certificate(format!("PKCS#12 (¿contraseña incorrecta?): {e}"))
    })?;
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
    let parsed = pkcs12.parse2(password).map_err(|e| {
        RuntimeError::Certificate(format!("PKCS#12 (¿contraseña incorrecta?): {e}"))
    })?;
    let Some(cert) = parsed.cert else {
        return Ok(None);
    };
    let cert_der = cert
        .to_der()
        .map_err(|e| RuntimeError::Certificate(format!("certificado: {e}")))?;
    Ok(certificate_type_of_x509(&cert_der, cert.subject_name()))
}

/// Stub Android: sin OpenSSL no se puede parsear el `.p12` (ver `Cargo.toml`).
///
/// ⚠️ **MUTANTE EQUIVALENTE CONOCIDO** (`cargo mutants`, hub#470): sustituir este cuerpo por
/// `Ok(Some(…))` **sobrevive**, y no se puede matar desde aquí. La función está detrás de
/// `#[cfg(target_os = "android")]`, así que en la plataforma donde corren los tests (y donde corre
/// el gate) **no se compila**: mutarla no cambia el binario que se prueba. Matarlo exigiría una
/// suite cross-compilada a Android, que este workspace no tiene — y el shell Android tampoco hace
/// transmisión fiscal todavía (mismo motivo por el que existe el stub). Sus gemelos
/// `identity_from_der`, `expiry_from_der` y `expiry_instant_from_der` están exactamente igual.
#[cfg(target_os = "android")]
pub fn certificate_type_from_der(_der: &[u8], _password: &str) -> Result<Option<CertificateType>> {
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
/// in the certificate, and a false NEGATIVE degrades to «cannot tell» — the safe side, which routes
/// to the holder's entry point.
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
        (false, false) => {
            subject_holds_a_natural_person(subject).then_some(CertificateType::Representative)
        }
    }
}

/// Does the subject name a HUMAN? `givenName` + `surname` are what a Spanish *certificado de
/// representante* carries and what a *sello de entidad* never does.
///
/// **Both, not either.** An organisation whose name happens to land in one of the two must not be
/// read as a person; and every certificate that really belongs to somebody carries the pair.
/// (MUTATION CANARY: turning the `&&` below into `||` must turn
/// `one_natural_person_attribute_alone_does_not_make_a_person` red.)
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

/// **Whose** a certificate is: the tax id and the registered name of the entity it belongs to,
/// read from the subject of the container the hub holds (hub#1478).
///
/// The companion of [`CertificateType`], and not a synonym: that one says *what* a certificate is,
/// this one says *who* it belongs to. Both are answered by the core and cross to a module as data;
/// neither drags the private key anywhere.
///
/// **Both fields or nothing.** A caller that has to declare an identity needs the pair, and
/// completing the missing half with a guess declares somebody who is not there — which is why
/// [`holder_from_der`] answers `None` rather than a half-filled struct.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CertificateHolder {
    /// Normalised: upper case, and without the semantics prefix of ETSI EN 319 412-1 §5.1.4.
    pub nif: String,
    /// `organizationName` (`O`) of the subject — the registered name, as the certificate spells
    /// it — or, for a natural person's own certificate (no `O`), `givenName` + `surname`
    /// (hub#1497).
    pub name: String,
}

/// [`CertificateHolder`] of a PKCS#12 in DER, or `None` when its subject names no entity.
///
/// `pub` for the same reason as its neighbours: the PKCS#12 crypto lives in the core, in ONE
/// place, and a caller holding a container in memory asks here instead of growing its own parser.
#[cfg(not(target_os = "android"))]
pub fn holder_from_der(der: &[u8], password: &str) -> Result<Option<CertificateHolder>> {
    ensure_legacy_provider();
    let pkcs12 = openssl::pkcs12::Pkcs12::from_der(der)
        .map_err(|e| RuntimeError::Certificate(format!("PKCS#12 inválido: {e}")))?;
    let parsed = pkcs12.parse2(password).map_err(|e| {
        RuntimeError::Certificate(format!("PKCS#12 (¿contraseña incorrecta?): {e}"))
    })?;
    Ok(parsed
        .cert
        .and_then(|cert| holder_of_x509(cert.subject_name())))
}

/// Stub Android: sin OpenSSL no se puede parsear el `.p12` (ver `Cargo.toml`). Mismo mutante
/// equivalente conocido que sus gemelos — en esta plataforma la función no se compila.
#[cfg(target_os = "android")]
pub fn holder_from_der(_der: &[u8], _password: &str) -> Result<Option<CertificateHolder>> {
    Ok(None)
}

/// The entity a subject names, or `None` when it names none.
///
/// # The order of the two identifiers is load-bearing
///
/// A qualified certificate issued to a person who REPRESENTS an entity carries both: the natural
/// person's document in `serialNumber` (2.5.4.5) and the entity's tax id in
/// `organizationIdentifier` (2.5.4.97). Reading `serialNumber` first would answer with a private
/// individual's document for a certificate that belongs to a company — so the entity identifier
/// wins, and `serialNumber` is only the fallback for containers that carry nothing else.
///
/// The same rule in the same order already guards the fiscal cell's own credential
/// (`verifactu-gateway/src/certificate.rs::holder_nif_of`, `verifactu-gateway#8`). This is not a
/// second answer to one question: it is the same rule where the other half of the pair needs it.
#[cfg(not(target_os = "android"))]
fn holder_of_x509(subject: &openssl::x509::X509NameRef) -> Option<CertificateHolder> {
    let nif = organization_identifier(subject)
        .or_else(|| subject_entry(subject, openssl::nid::Nid::SERIALNUMBER))
        .map(|raw| normalise_holder_id(&raw))
        .filter(|nif| !nif.is_empty())?;
    // Half an identity is not an identity: a caller declaring a party needs both, and inventing
    // the missing one would name somebody who is not there.
    let name = subject_entry(subject, openssl::nid::Nid::ORGANIZATIONNAME)
        .or_else(|| natural_person_name(subject))?;
    Some(CertificateHolder { nif, name })
}

/// `givenName` + `surname` (hub#1497): the fallback for a natural person's OWN certificate, which
/// carries no `organizationName` — the gap #1478 deliberately left out. Same clean pair
/// [`subject_holds_a_natural_person`] already trusts to route a certificate to `www1`, composed
/// rather than parsed out of `CN` (FNMT writes `"APELLIDOS NOMBRE - NIF 12345678Z"`, embedding the
/// very NIF this function must not guess). Both fields or nothing, same rule as its neighbour.
#[cfg(not(target_os = "android"))]
fn natural_person_name(subject: &openssl::x509::X509NameRef) -> Option<String> {
    let given = subject_entry(subject, openssl::nid::Nid::GIVENNAME)?;
    let surname = subject_entry(subject, openssl::nid::Nid::SURNAME)?;
    Some(format!("{given} {surname}"))
}

/// `organizationIdentifier` has no `Nid` constant in the binding, so it is matched by OID.
#[cfg(not(target_os = "android"))]
fn organization_identifier(subject: &openssl::x509::X509NameRef) -> Option<String> {
    let wanted = openssl::asn1::Asn1Object::from_str("2.5.4.97").ok()?;
    subject
        .entries()
        .find(|entry| entry.object().nid() == wanted.nid())
        .map(|entry| String::from_utf8_lossy(entry.data().as_slice()).into_owned())
        .filter(|value| !value.trim().is_empty())
}

#[cfg(not(target_os = "android"))]
fn subject_entry(subject: &openssl::x509::X509NameRef, nid: openssl::nid::Nid) -> Option<String> {
    subject
        .entries_by_nid(nid)
        .next()
        .map(|entry| String::from_utf8_lossy(entry.data().as_slice()).into_owned())
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
}

/// ETSI EN 319 412-1 §5.1.4 semantics identifiers: a qualified certificate writes the number as
/// `VATES-B27593136`, `NTRES-…`, `IDCES-…`, `PASES-…`, `PNOES-…` or `TINES-…`. The prefix says
/// *which register the number comes from*, not which number it is, so it is stripped before
/// anybody compares — and a bare identifier, which plenty of containers carry, compares the same
/// either way.
#[cfg(not(target_os = "android"))]
fn normalise_holder_id(raw: &str) -> String {
    const PREFIXES: [&str; 6] = ["VATES-", "NTRES-", "PASES-", "IDCES-", "PNOES-", "TINES-"];
    let value = raw.trim().to_ascii_uppercase();
    for prefix in PREFIXES {
        if let Some(rest) = value.strip_prefix(prefix) {
            return rest.trim().to_owned();
        }
    }
    value
}

/// `notAfter` de un PKCS#12 en DER como **instante** RFC 3339 UTC (`2028-06-10T09:12:33Z`).
/// Gemelo de [`expiry_from_der`] sin truncar el día — ver [`slot_expiry_instant`] para el porqué.
#[cfg(not(target_os = "android"))]
pub fn expiry_instant_from_der(der: &[u8], password: &str) -> Result<Option<String>> {
    ensure_legacy_provider();
    let pkcs12 = openssl::pkcs12::Pkcs12::from_der(der)
        .map_err(|e| RuntimeError::Certificate(format!("PKCS#12 inválido: {e}")))?;
    let parsed = pkcs12.parse2(password).map_err(|e| {
        RuntimeError::Certificate(format!("PKCS#12 (¿contraseña incorrecta?): {e}"))
    })?;
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
        assert_eq!(
            asn1_time_to_iso("Jun 10 00:00:00 2028 GMT").as_deref(),
            Some("2028-06-10")
        );
        assert_eq!(
            asn1_time_to_iso("Mar 3 23:59:59 2027 GMT").as_deref(),
            Some("2027-03-03")
        );
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
        assert_eq!(
            asn1_time_to_rfc3339("Jun 10 9:12:33 2028 GMT").as_deref(),
            None
        );
        assert_eq!(
            asn1_time_to_rfc3339("Jun 10 091233 2028 GMT").as_deref(),
            None
        );
        assert_eq!(
            asn1_time_to_rfc3339("Jun 10 09-12-33 2028 GMT").as_deref(),
            None
        );
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
        base64::engine::general_purpose::STANDARD
            .decode(b64)
            .unwrap()
    }

    async fn db_ready() -> PgAdapter {
        let db = fresh_db().await;
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        // hub_session baseline (v0): la migración v8 (device_id, ADR-0154) lo ALTERa.
        crate::identity::ensure_tables(&db).await.unwrap();
        crate::system_migrations::apply(&db, "hub-test")
            .await
            .unwrap();
        db
    }

    /// Reads the raw row of one slot as it sits in the database (without going through
    /// `load_pkcs12`/decryption) — what somebody with direct database access would see.
    async fn raw_row(
        db: &dyn DatabaseAdapter,
        hub_id: &str,
        kind: CertificateKind,
    ) -> (String, String) {
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
            row.get("pkcs12_b64")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            row.get("password")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
        )
    }

    // ── The own slot behaves exactly as it did before there were two ──────────────────────────

    #[tokio::test]
    async fn set_status_delete_roundtrip() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(1));
        let db = db_ready().await;
        // Ausente.
        assert_eq!(
            status(&db, "hub-test").await.unwrap()["present"],
            json!(false)
        );
        // Subir.
        set(
            &db,
            "hub-test",
            CertificateKind::Own,
            "QkFTRTY0",
            "secret",
            "hub_user:admin",
            None,
        )
        .await
        .unwrap();
        let st = status(&db, "hub-test").await.unwrap();
        assert_eq!(st["present"], json!(true));
        assert_eq!(st["uploaded_by"], json!("hub_user:admin"));
        // status NO expone bytes ni password.
        assert!(st.get("pkcs12_b64").is_none() && st.get("password").is_none());
        // Reemplazar (upsert, no duplica).
        set(
            &db,
            "hub-test",
            CertificateKind::Own,
            "TkVX",
            "p2",
            "hub_user:admin",
            None,
        )
        .await
        .unwrap();
        assert_eq!(
            status(&db, "hub-test").await.unwrap()["present"],
            json!(true)
        );
        // Borrar.
        delete(&db, "hub-test", CertificateKind::Own).await.unwrap();
        assert_eq!(
            status(&db, "hub-test").await.unwrap()["present"],
            json!(false)
        );
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

    #[tokio::test]
    async fn set_then_load_pkcs12_roundtrip_returns_originals() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(3));
        let db = db_ready().await;

        let original_b64 = "TVVZLVNFQ1JFVE8tUEtDUzEy"; // base64("MUY-SECRETO-PKCS12")
        set(
            &db,
            "hub-test",
            CertificateKind::Own,
            original_b64,
            "mi-contraseña-real",
            "hub_user:admin",
            None,
        )
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

        set(
            &db,
            "hub-test",
            CertificateKind::Own,
            OWN_B64,
            "no-debe-viajar",
            "hub_user:admin",
            None,
        )
        .await
        .unwrap();

        let der = exportable_der_bytes(&db, "hub-test")
            .await
            .unwrap()
            .expect("certificado presente");
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

        let err = set(
            &db,
            "hub-test",
            CertificateKind::Own,
            "cGtjczEy",
            "password",
            "hub_user:admin",
            None,
        )
        .await
        .unwrap_err();
        let msg = err.to_string();
        assert!(
            msg.contains("HUB_SECRETS_KEY"),
            "mensaje de error poco claro: {msg}"
        );
        // No debe haber guardado nada.
        assert_eq!(
            status(&db, "hub-test").await.unwrap()["present"],
            json!(false)
        );
    }

    #[tokio::test]
    async fn load_pkcs12_wrong_key_fails_clearly_not_panics() {
        let _lock = env_lock();
        let db = {
            let _guard = EnvVarGuard::set(&test_key_b64(4));
            let db = db_ready().await;
            set(
                &db,
                "hub-test",
                CertificateKind::Own,
                "cGtjczEy",
                "password",
                "hub_user:admin",
                None,
            )
            .await
            .unwrap();
            db
        };

        // Misma fila, master key DISTINTA: debe fallar con un error claro, no un pánico.
        let _guard = EnvVarGuard::set(&test_key_b64(5));
        let err = load_pkcs12(&db, "hub-test", CertificateKind::Own)
            .await
            .unwrap_err();
        assert!(matches!(err, RuntimeError::Certificate(_)));
    }

    // ── ADR-0202 §2.1 (hub#316) · un solo slot desde hub#1435 ─────────────────────────────────

    /// 🔒 **La VÍA por la que las facturas llegan a la AEAT, nombrada** (ADR-0320 §1 — hub#1314): o
    /// la firma y remite el obligado con su certificado (`own`), o lo hace ERPlora en su nombre con
    /// el Sello, por la celda (`delegated`). Son excluyentes, y quien decide cuál es si hay
    /// certificado o no — nada más.
    ///
    /// Un hub SIN certificado es `delegated` **a propósito**: es la vía de la celda, la que le
    /// atiende hoy (ADR-0320) y la que la pantalla tiene que ofrecerle por defecto. Decir `own` ahí
    /// mandaría a alguien sin `.p12` a una pantalla que no puede completar.
    ///
    /// Este es el canario de hub#1435: retirado el SLOT delegado, la RUTA delegada sigue siendo la
    /// de un hub sin certificado. Un «limpiar lo que sobra» que se llevase las dos rompería aquí.
    #[tokio::test]
    async fn the_transmission_route_says_whether_there_is_a_certificate() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(11));
        let db = db_ready().await;

        assert_eq!(
            transmission_route(&db, "hub-test").await.unwrap(),
            ROUTE_DELEGATED,
            "sin certificado la vía es la de la celda, no la propia"
        );

        set(
            &db,
            "hub-test",
            CertificateKind::Own,
            OWN_B64,
            "pw-own",
            "hub_user:admin",
            None,
        )
        .await
        .unwrap();
        assert_eq!(
            transmission_route(&db, "hub-test").await.unwrap(),
            ROUTE_OWN,
            "el propio gana en cuanto se sube — y con él sobra el otorgamiento"
        );

        // Y la misma respuesta viaja en el JSON que lee la pantalla, sin que esta tenga que
        // deducirla de `active`: dos deducciones separadas es como se separan.
        let seen = status(&db, "hub-test").await.unwrap();
        assert_eq!(seen["transmission_route"], json!(ROUTE_OWN));

        delete(&db, "hub-test", CertificateKind::Own).await.unwrap();
        assert_eq!(
            status(&db, "hub-test").await.unwrap()["transmission_route"],
            json!(ROUTE_DELEGATED),
            "al borrar el propio la pantalla vuelve a la vía de ERPlora"
        );
    }

    /// `GET /api/business/certificate` keeps meaning what it meant: `present` is the certificate the
    /// owner uploaded, and `slots` describes the one slot there is.
    #[tokio::test]
    async fn status_reports_the_own_slot_and_says_which_one_signs() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(10));
        let db = db_ready().await;

        let st = status(&db, "hub-test").await.unwrap();
        assert_eq!(
            st["present"],
            json!(false),
            "el negocio no ha subido el suyo"
        );
        assert_eq!(st["active"], json!(null), "y no hay nada más con que firmar");
        assert_eq!(st["slots"]["own"]["present"], json!(false));
        assert!(
            st["slots"].get("delegated").is_none(),
            "el slot retirado no se ofrece: {st}"
        );

        set(
            &db,
            "hub-test",
            CertificateKind::Own,
            OWN_B64,
            "pw-own",
            "hub_user:admin",
            None,
        )
        .await
        .unwrap();
        let st = status(&db, "hub-test").await.unwrap();
        assert_eq!(st["present"], json!(true));
        assert_eq!(st["active"], json!("own"));
        // Ni el estado global ni el de cada slot filtran bytes o contraseñas.
        let dump = st.to_string();
        assert!(!dump.contains(OWN_B64));
        assert!(!dump.contains("pw-own"));
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
        cert.set_not_before(&Asn1Time::days_from_now(0).unwrap())
            .unwrap();
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

    /// Plants the enrolled machine identity — the three fields
    /// [`crate::gateway_identity::client_identity`] demands before the cell road exists on this
    /// side. Written raw because what is read here is the PRESENCE of the material, never its
    /// contents.
    async fn enrol_machine_identity(db: &dyn DatabaseAdapter, hub_id: &str) {
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(hub_id));
        p.insert(
            "common_name".into(),
            json!(crate::gateway_identity::common_name(hub_id)),
        );
        db.execute(
            "INSERT INTO _hub_gateway_identity \
             (hub_id, private_key_pem, certificate_pem, ca_pem, common_name, created_at, updated_at) \
             VALUES (:hub_id, 'v1:ciphertext', 'cert', 'ca', :common_name, \
                     '2026-09-03T09:00:00Z', '2026-09-03T09:00:00Z')",
            &p,
        )
        .await
        .expect("the machine identity is enrolled");
    }

    /// **`can_transmit` is «has this hub got a ROUTE?», in all four states** (hub#1489). Own
    /// certificate and enrolled cell identity are the two roads of ADR-0320 §1 and either of them
    /// is enough; only a hub with NEITHER has no way out. Walking all four in one test is the
    /// point: the failure this pins is not «one state is wrong», it is «the two roads stopped
    /// being interchangeable».
    #[tokio::test]
    async fn can_transmit_answers_either_road_in_every_state() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(24));
        let db = db_ready().await;

        for (own, enrolled) in [(false, false), (true, false), (false, true), (true, true)] {
            delete(&db, "hub-test", CertificateKind::Own).await.unwrap();
            let mut p = Params::new();
            p.insert("hub_id".into(), json!("hub-test"));
            db.execute(
                "DELETE FROM _hub_gateway_identity WHERE hub_id = :hub_id",
                &p,
            )
            .await
            .unwrap();
            if own {
                set(
                    &db,
                    "hub-test",
                    CertificateKind::Own,
                    OWN_B64,
                    "pw",
                    "hub_user:a",
                    None,
                )
                .await
                .unwrap();
            }
            if enrolled {
                enrol_machine_identity(&db, "hub-test").await;
            }

            assert_eq!(
                can_transmit(&db, "hub-test").await.unwrap(),
                own || enrolled,
                "own={own} enrolled={enrolled}: either road is a way out; neither is not"
            );
        }
    }

    /// **`active_kind` still answers «WHICH», and only about the own slot.** It is the half
    /// `can_transmit` must never absorb: `route_of` picks the AEAT road with it and
    /// `status(..)["present"]` shows the owner what they uploaded, and an enrolled cell identity is
    /// neither of those things — it is not the customer's certificate and there is nothing on that
    /// screen to delete.
    #[tokio::test]
    async fn an_enrolled_cell_identity_is_not_a_certificate() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(24));
        let db = db_ready().await;
        enrol_machine_identity(&db, "hub-test").await;

        assert_eq!(
            active_kind(&db, "hub-test").await.unwrap(),
            None,
            "the cell identity is ERPlora's road, not a certificate of the business's"
        );
        assert_eq!(
            status(&db, "hub-test").await.unwrap()["present"],
            json!(false),
            "Ajustes → Negocio has nothing to show and nothing to delete"
        );
        assert_eq!(
            transmission_route(&db, "hub-test").await.unwrap(),
            ROUTE_DELEGATED,
            "no own certificate is the cell road (ADR-0320 §1)"
        );
        assert!(
            can_transmit(&db, "hub-test").await.unwrap(),
            "…and that road is a way out: this hub files"
        );
    }

    // ── hub#470: what the certificate IS, read out of the bytes it was stored from ─────────────

    /// Stores a container in the hub's one slot through the writer the product uses, with the type
    /// DERIVED from the bytes — which since hub#1435 is the only source there is. Before it, the
    /// control plane also DECLARED a type and `resolve_certificate_type` reconciled the two; with
    /// the delegated slot gone there is no second opinion, so the container answers alone.
    async fn store_own(db: &dyn DatabaseAdapter, b64: &str, password: &str) -> Result<()> {
        set(
            db,
            "hub-test",
            CertificateKind::Own,
            b64,
            password,
            "hub_user:admin",
            derive_certificate_type(b64, password),
        )
        .await
    }

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
        /// **Only ONE** of the two natural-person attributes, and no `qcStatements`. Certificates
        /// issued to organisations do land text in `givenName` on their own now and then; one
        /// attribute is not a human.
        HalfAPerson,
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
        if matches!(shape, Shape::HalfAPerson) {
            name.append_entry_by_text("GN", "NOMBRE").unwrap();
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

        // The `qcStatements` extension (RFC 3739 `1.3.6.1.5.5.7.1.3`), hand-encoded: a SEQUENCE of
        // QCStatement, each `{ statementId, statementInfo }`. Here one statement — ETSI's
        // `id-etsi-qcs-QcType` (`0.4.0.1862.1.6`) — whose info is a SEQUENCE OF the type OIDs.
        let qc_types: &[&[u8]] = match shape {
            Shape::EntitySeal => &[&QC_TYPE_ESEAL_DER],
            Shape::QualifiedRepresentative => &[&QC_TYPE_ESIGN_DER],
            Shape::ContradictsItself => &[&QC_TYPE_ESEAL_DER, &QC_TYPE_ESIGN_DER],
            Shape::PersonWithoutQcStatements | Shape::Anonymous | Shape::HalfAPerson => &[],
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

    /// 🔒 **One natural-person attribute alone is not a person.** `givenName` **and** `surname`, both
    /// of them: an organisation with text in only one of the two must not be read as a human, and
    /// every certificate that really belongs to somebody carries the pair.
    ///
    /// It matters in the direction that costs: read as a person, such a container would be a
    /// *representative* — which is right by luck here, but the same laxity is what turns «I found no
    /// person» into evidence, and the absence of a person is the ONLY thing standing between an
    /// unclassifiable certificate and the seal's door. Found by mutation (`&&` → `||` survived).
    #[test]
    fn one_natural_person_attribute_alone_does_not_make_a_person() {
        assert_eq!(type_of(Shape::HalfAPerson), None);
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

    /// 🔴 **The bug hub#470 closes.** A REPRESENTATIVE container must not make the hub behave like a
    /// seal. Before this the SLOT was the answer, so a whole fleet would have POSTed to `www10` and
    /// had all of its records rejected, one by one (ADR-0189). The slot that made the mistake
    /// reachable is retired (hub#1435); the rule it forced — the TYPE decides — is what routes the
    /// fiscal cell today, so it stays pinned.
    #[tokio::test]
    async fn a_representative_container_is_not_a_seal() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(20));
        let db = db_ready().await;
        let (b64, pw) = pkcs12_shaped(Shape::QualifiedRepresentative);

        store_own(&db, &b64, &pw)
            .await
            .unwrap();

        assert_eq!(
            active_type(&db, "hub-test").await.unwrap(),
            Some(CertificateType::Representative),
            "the TYPE comes from the container"
        );
    }

    /// The other half: a real seal IS a seal, so hub#320's fix survives.
    #[tokio::test]
    async fn an_entity_seal_container_is_a_seal() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(21));
        let db = db_ready().await;
        let (b64, pw) = pkcs12_shaped(Shape::EntitySeal);
        store_own(&db, &b64, &pw)
            .await
            .unwrap();
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
        store_own(&db, &b64, &pw)
            .await
            .unwrap();
        assert_eq!(
            active_type(&db, "hub-test").await.unwrap(),
            Some(CertificateType::Seal)
        );
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
            derive_certificate_type(&seal_b64, &seal_pw),
        )
        .await
        .unwrap();
        assert_eq!(
            active_type(&db, "hub-test").await.unwrap(),
            Some(CertificateType::Seal)
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
            slot_type(&db, "hub-test", CertificateKind::Own).await.unwrap(),
            None
        );
    }

    /// 🔒 **A row written before the column existed is READ, never guessed.** The hubs that were
    /// already deployed have `certificate_type = ''` and nothing backfills it (that would be
    /// guessing what somebody's certificate is — the trap v19/hub#436 walked around). Parsing the
    /// container the row actually holds is a reading, and it is what keeps those hubs on the right
    /// door until their next upload writes the column.
    #[tokio::test]
    async fn a_row_without_a_stored_type_is_classified_from_its_own_container() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(29));
        let db = db_ready().await;
        let (b64, pw) = pkcs12_shaped(Shape::EntitySeal);
        store_own(&db, &b64, &pw)
            .await
            .unwrap();

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

    /// **The type is written in the SAME upsert as the bytes** (v21). A rotation that replaced the
    /// container but left the previous type behind would pick the AEAT door of a certificate the hub
    /// no longer holds.
    #[tokio::test]
    async fn replacing_the_container_replaces_its_type_in_the_same_write() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(30));
        let db = db_ready().await;
        let (seal_b64, seal_pw) = pkcs12_shaped(Shape::EntitySeal);
        store_own(&db, &seal_b64, &seal_pw)
            .await
            .unwrap();

        let (rep_b64, rep_pw) = pkcs12_shaped(Shape::QualifiedRepresentative);
        store_own(&db, &rep_b64, &rep_pw)
        .await
        .unwrap();

        assert_eq!(
            active_type(&db, "hub-test").await.unwrap(),
            Some(CertificateType::Representative)
        );

        // And deleting it leaves NO type: there is no second slot to fall back to (hub#1435), so a
        // hub that removes its certificate is a hub with nothing to route.
        delete(&db, "hub-test", CertificateKind::Own).await.unwrap();
        assert_eq!(active_type(&db, "hub-test").await.unwrap(), None);
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
        for unknown in [
            "",
            " ",
            "Seal",
            "seal ",
            "sello",
            "own",
            "delegated",
            "future",
        ] {
            assert_eq!(CertificateType::parse(unknown), None, "{unknown:?}");
        }
    }
}
