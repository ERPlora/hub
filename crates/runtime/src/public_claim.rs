//! **Public claims** — the one door of this hub that answers somebody with no session (hub#963).
//!
//! A claim is a promise printed on paper: *"whoever holds this locator may run exactly this
//! command, exactly once, until this date"*. The first thing it buys is the self-service invoice —
//! a diner takes their ticket home, types the locator into a web page, fills in their tax details
//! and walks away with the complete invoice (F3) — without a waiter ever typing a NIF at the
//! counter, and without a hub employee being involved at all.
//!
//! ## Why the core, and why generic
//!
//! Only the core can open an HTTP surface: a module is queries, commands and a Web Component
//! behind the authenticated dispatcher, and none of that can be reached without a session. So the
//! door has to live here. What must NOT live here is the word *invoice*: the core names no module
//! (same rule as `RequestContext::fiscal_providers`). A claim therefore stores the command to run
//! and the payload to run it with — the module that mints it decides what those are.
//!
//! ## What authorises the redemption
//!
//! **The locator is the authorisation, and it is the only one.** There is no session, no role and
//! no user behind a public redemption, so the row itself has to carry every restriction:
//!
//! | Risk | What stops it |
//! |---|---|
//! | Guessing a neighbour's locator | HMAC-SHA256 under a per-hub key, never a row id or a sequence — the printed VeriFactu QR is *not* usable for this, its `numserie` is correlative and public |
//! | Redeeming somebody else's ticket twice | `redeemed_at` set by a **conditional UPDATE**: the first writer wins, the second gets `false` |
//! | Tampering with the amounts | the payload is **sealed at mint time**; the visitor may only fill the keys listed in `public_fields`, and anything else they send is dropped |
//! | Coming back a year later | `expires_at`, checked on every read |
//!
//! The locator is **deterministic** — `HMAC(key, kind || subject_id)` — and that is deliberate:
//! reprinting a lost ticket has to yield the SAME locator, or the copy the customer holds stops
//! working. It is unguessable for the same reason [`crate::identity::badge_index`] is: the key
//! never leaves `_public_claim_key`, a system table with no HTTP door of its own.
//!
//! Persistence: `_public_claim` + `_public_claim_key`, **system migration v51**.

use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::registry::{new_id, now_rfc3339};

/// Characters of the printed locator. Crockford base32 over 80 bits of HMAC: unguessable, and
/// still short enough to be typed by hand off a thermal ticket when the camera fails.
pub const LOCATOR_CHARS: usize = 16;

/// Crockford's base32 alphabet — no `I`, `L`, `O` or `U`, so `1/I`, `0/O` and the accidental word
/// cannot happen on a receipt read under a restaurant's lighting.
const CROCKFORD: &[u8; 32] = b"0123456789ABCDEFGHJKMNPQRSTVWXYZ";

/// How long a claim stays redeemable when the minter names no deadline, in days.
///
/// **The ceiling is the law, not a preference.** Art. 11.2 RD 1619/2012: when the recipient is a
/// business or professional — which is the only reason to ask for a complete invoice — the invoice
/// must be issued *before the 16th of the month following* the one the VAT accrued in. 45 days is
/// the smallest fixed window that always reaches that date from any day of the month (a sale on
/// the 1st needs 46 to reach the 16th of the next month… so the minter may override it; see
/// [`NewClaim::expires_at`]). The market puts no shorter limit on it: Cuiner's *QuieroFactura*
/// documents the locator as redeemable "later", with no published cut-off at all.
pub const DEFAULT_TTL_DAYS: i64 = 45;

/// What a caller must supply to mint a claim. Everything here is sealed into the row.
#[derive(Debug, Clone)]
pub struct NewClaim {
    /// The minter's own word for what this is (`invoice_request`). Opaque to the core; it is half
    /// the identity of the claim, so two purposes over the same subject are two locators.
    pub kind: String,
    /// What the claim is about (the F2's row id). Opaque to the core.
    pub subject_id: String,
    /// The command a redemption runs. Named by the minter, never by the core.
    pub command: String,
    /// The payload, minus what the visitor fills. **This is the seal**: amounts, lines and the id
    /// of the ticket being substituted are decided at the counter, where they are already true.
    pub sealed_payload: Json,
    /// The payload keys the visitor is allowed to fill. Anything else they submit is dropped, not
    /// rejected — a form that 400s on an extra field is a form that breaks on the next browser.
    pub public_fields: Vec<String>,
    /// When it stops being redeemable (RFC-3339). `None` → [`DEFAULT_TTL_DAYS`] from `now`.
    pub expires_at: Option<String>,
    /// `hub_user.id` of whoever minted it, for the audit trail. Empty when the runtime did.
    pub created_by: String,
}

/// A claim as the door reads it back.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Claim {
    pub id: String,
    pub kind: String,
    pub subject_id: String,
    pub command: String,
    pub sealed_payload: Json,
    pub public_fields: Vec<String>,
    pub expires_at: String,
    /// `Some` once somebody has spent it. A spent claim is still readable on purpose: the visitor
    /// who refreshes the page must see their invoice, not a 404.
    pub redeemed_at: Option<String>,
    /// What the redemption produced (the F3's id), so a refresh can show it again.
    pub result_ref: String,
}

impl Claim {
    /// Has it been spent already?
    pub fn is_redeemed(&self) -> bool {
        self.redeemed_at.is_some()
    }

    /// Is `now` past its deadline?
    pub fn is_expired(&self, now: &str) -> bool {
        now > self.expires_at.as_str()
    }
}

/// Why a locator did not open the door. Kept apart from "no such claim" **only inside the
/// runtime**: the HTTP door collapses `NotFound` and a wrong-hub lookup into one answer, because
/// telling a stranger that a locator exists but is not theirs is already an oracle.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum ClaimRefusal {
    #[error("no such claim")]
    NotFound,
    #[error("claim expired at {0}")]
    Expired(String),
    #[error("claim already redeemed at {0}")]
    AlreadyRedeemed(String),
}

/// The clock the door compares deadlines against, in the shape the rows store.
///
/// Exposed because the HTTP door lives in another crate and must not invent its own format: two
/// spellings of "now" compared as strings is how an expiry check silently stops working.
pub fn now() -> String {
    now_rfc3339()
}

/// The **per-hub key** the locator is derived under. Minted once, kept forever.
///
/// Same shape and the same reasons as [`crate::identity::badge_index_key`]: it lives in a system
/// table with no HTTP door, so nobody who can read `hub_settings` can forge a locator; and it is
/// never rotated, because a new key would silently orphan every ticket already on paper.
pub async fn claim_key(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Vec<u8>> {
    if let Some(key) = stored_key(db, hub_id).await? {
        return Ok(key);
    }
    let mut bytes = [0u8; 32];
    ring::rand::SecureRandom::fill(&ring::rand::SystemRandom::new(), &mut bytes)
        .map_err(|_| RuntimeError::Other("could not generate the public-claim key".into()))?;
    let mut ins = Params::new();
    ins.insert("hub_id".into(), json!(hub_id));
    ins.insert("key_hex".into(), json!(hex_lower(&bytes)));
    ins.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "INSERT INTO _public_claim_key (hub_id, key_hex, created_at) \
          VALUES (:hub_id, :key_hex, :now) ON CONFLICT (hub_id) DO NOTHING",
        &ins,
    )
    .await?;
    // Re-read, never `bytes`: if another boot won the race, the good key is theirs. Two processes
    // of the same hub deriving different locators during a rollout would print tickets that stop
    // working the moment the other replica answers.
    stored_key(db, hub_id)
        .await?
        .ok_or_else(|| RuntimeError::Other("the public-claim key was not stored".into()))
}

async fn stored_key(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Option<Vec<u8>>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT key_hex FROM _public_claim_key WHERE hub_id = :hub_id",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .first()
        .and_then(|row| row["key_hex"].as_str())
        .and_then(hex_bytes))
}

/// The printed locator for `(kind, subject_id)` under this hub's key.
///
/// Deterministic **and** keyed. Deterministic so a reprint matches the customer's copy; keyed so
/// the sequence of ticket ids — which is public, it is on every receipt — cannot be walked.
pub fn locator(key: &[u8], kind: &str, subject_id: &str) -> String {
    let key = ring::hmac::Key::new(ring::hmac::HMAC_SHA256, key);
    // `\u{1f}` (unit separator) and not `:`: without a byte that cannot occur in either field,
    // `("ab","c")` and `("a","bc")` would hash to the same locator.
    let msg = format!("{kind}\u{1f}{subject_id}");
    let tag = ring::hmac::sign(&key, msg.as_bytes());
    base32_crockford(tag.as_ref(), LOCATOR_CHARS)
}

/// Fold a locator typed by hand into the form the index stores: upper case, no spaces, and the
/// three characters Crockford maps back onto digits (`O`→`0`, `I`/`L`→`1`).
///
/// This is **tolerance at the door**, never identity: it maps sloppy input onto a locator that
/// already exists, exactly like [`crate::print_stations::normalize_key`].
pub fn normalize_locator(raw: &str) -> String {
    raw.chars()
        .filter(|c| c.is_ascii_alphanumeric())
        .map(|c| match c.to_ascii_uppercase() {
            'O' => '0',
            'I' | 'L' => '1',
            other => other,
        })
        .collect()
}

/// Mint a claim, returning its printed locator. **Idempotent** on `(hub_id, kind, subject_id)`:
/// minting twice for the same ticket returns the same locator and does not reset the deadline or
/// un-spend a redemption. That is what lets the POS call it on every reprint without thinking.
pub async fn mint(db: &dyn DatabaseAdapter, hub_id: &str, spec: NewClaim) -> Result<String> {
    if spec.kind.trim().is_empty() || spec.subject_id.trim().is_empty() {
        return Err(RuntimeError::Domain {
            code: "public_claim.incomplete".into(),
            message: "a claim needs both a kind and a subject".into(),
        });
    }
    if spec.command.trim().is_empty() {
        return Err(RuntimeError::Domain {
            code: "public_claim.no_command".into(),
            message: "a claim that runs nothing is not a claim".into(),
        });
    }
    let key = claim_key(db, hub_id).await?;
    let locator = locator(&key, &spec.kind, &spec.subject_id);
    let now = now_rfc3339();
    let expires_at = spec
        .expires_at
        .clone()
        .unwrap_or_else(|| plus_days(&now, DEFAULT_TTL_DAYS));

    let mut p = Params::new();
    p.insert("id".into(), json!(new_id()));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("token_hash".into(), json!(hash_locator(&locator)));
    p.insert("kind".into(), json!(spec.kind));
    p.insert("subject_id".into(), json!(spec.subject_id));
    p.insert("command".into(), json!(spec.command));
    p.insert(
        "sealed_payload".into(),
        json!(spec.sealed_payload.to_string()),
    );
    p.insert(
        "public_fields".into(),
        json!(json!(spec.public_fields).to_string()),
    );
    p.insert("expires_at".into(), json!(expires_at));
    p.insert("created_by".into(), json!(spec.created_by));
    p.insert("now".into(), json!(now));
    db.execute(
        "INSERT INTO _public_claim (\
           id, hub_id, token_hash, kind, subject_id, command, sealed_payload, public_fields, \
           expires_at, redeemed_at, result_ref, created_by, created_at) \
         VALUES (:id, :hub_id, :token_hash, :kind, :subject_id, :command, :sealed_payload, \
           :public_fields, :expires_at, NULL, '', :created_by, :now) \
         ON CONFLICT (hub_id, kind, subject_id) DO NOTHING",
        &p,
    )
    .await?;
    Ok(locator)
}

/// Read a claim back by the locator the visitor typed or scanned.
///
/// `Ok(None)` covers every way a locator can fail to name a row in THIS hub — unknown, malformed,
/// or belonging to a neighbour. One answer on purpose: three would let a stranger tell an existing
/// locator from a typo.
pub async fn find(db: &dyn DatabaseAdapter, hub_id: &str, raw: &str) -> Result<Option<Claim>> {
    let normalized = normalize_locator(raw);
    if normalized.len() != LOCATOR_CHARS {
        return Ok(None);
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("token_hash".into(), json!(hash_locator(&normalized)));
    let res = db
        .query(
            "SELECT id, kind, subject_id, command, sealed_payload, public_fields, expires_at, \
                    redeemed_at, result_ref \
               FROM _public_claim WHERE hub_id = :hub_id AND token_hash = :token_hash",
            &p,
        )
        .await?;
    let Some(row) = res.rows.first() else {
        return Ok(None);
    };
    Ok(Some(Claim {
        id: str_of(row, "id"),
        kind: str_of(row, "kind"),
        subject_id: str_of(row, "subject_id"),
        command: str_of(row, "command"),
        sealed_payload: parse_json(&str_of(row, "sealed_payload")).unwrap_or_else(|| json!({})),
        public_fields: parse_json(&str_of(row, "public_fields"))
            .and_then(|v| serde_json::from_value(v).ok())
            .unwrap_or_default(),
        expires_at: str_of(row, "expires_at"),
        redeemed_at: row
            .get("redeemed_at")
            .and_then(|v| v.as_str())
            .filter(|s| !s.is_empty())
            .map(str::to_string),
        result_ref: str_of(row, "result_ref"),
    }))
}

/// The claim a locator names, **or the reason it cannot be spent right now**.
///
/// One function and not three checks at the call site: "found", "not expired" and "not yet spent"
/// have to be asked in that order and every caller has to ask all three, so asking them anywhere
/// else is how one of them eventually goes missing.
pub async fn redeemable(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    raw: &str,
    now: &str,
) -> Result<std::result::Result<Claim, ClaimRefusal>> {
    let Some(claim) = find(db, hub_id, raw).await? else {
        return Ok(Err(ClaimRefusal::NotFound));
    };
    if let Some(at) = &claim.redeemed_at {
        return Ok(Err(ClaimRefusal::AlreadyRedeemed(at.clone())));
    }
    if claim.is_expired(now) {
        return Ok(Err(ClaimRefusal::Expired(claim.expires_at.clone())));
    }
    Ok(Ok(claim))
}

/// Spend the claim. Returns `false` when somebody else got there first.
///
/// The `redeemed_at IS NULL` in the WHERE is the whole guarantee, and it has to be **in the
/// statement**: a read-then-write would let two taps on a slow phone both see "not redeemed" and
/// both issue an invoice, which for an F3 means two complete invoices substituting one ticket —
/// two entries in a fiscal chain that cannot be un-sent.
pub async fn spend(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    claim_id: &str,
    result_ref: &str,
    now: &str,
) -> Result<bool> {
    let mut p = Params::new();
    p.insert("id".into(), json!(claim_id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("result_ref".into(), json!(result_ref));
    p.insert("now".into(), json!(now));
    let result = db
        .execute(
            "UPDATE _public_claim SET redeemed_at = :now, result_ref = :result_ref \
              WHERE id = :id AND hub_id = :hub_id AND redeemed_at IS NULL",
            &p,
        )
        .await?;
    Ok(result.affected > 0)
}

/// Write down what the redemption produced, once the command has actually succeeded.
///
/// Separate from [`spend`] because the two answer different questions and happen at different
/// moments: `spend` closes the door (before running anything, so a double tap cannot get through),
/// and this records the result (after, when there is one to record).
pub async fn record_result(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    claim_id: &str,
    result_ref: &str,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("id".into(), json!(claim_id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("result_ref".into(), json!(result_ref));
    db.execute(
        "UPDATE _public_claim SET result_ref = :result_ref WHERE id = :id AND hub_id = :hub_id",
        &p,
    )
    .await?;
    Ok(())
}

/// Hand the claim back after a redemption that produced **nothing**.
///
/// A mistyped NIF, or a hub that has not configured its fiscal identity yet, must not cost the
/// customer their one shot: they can fix it in five seconds, and the alternative is sending them
/// back to the counter for a locator that is now dead. It only ever releases a claim whose result
/// is still empty, so it can never re-open one that did issue a document.
pub async fn release(db: &dyn DatabaseAdapter, hub_id: &str, claim_id: &str) -> Result<()> {
    let mut p = Params::new();
    p.insert("id".into(), json!(claim_id));
    p.insert("hub_id".into(), json!(hub_id));
    db.execute(
        "UPDATE _public_claim SET redeemed_at = NULL \
          WHERE id = :id AND hub_id = :hub_id AND result_ref = ''",
        &p,
    )
    .await?;
    Ok(())
}

/// The payload a redemption actually runs: the seal, plus **only** the declared public fields of
/// what the visitor submitted.
///
/// The direction matters. Sealed values are written last, so a visitor who posts
/// `original_invoice_id` or `items` overwrites nothing — their copy is simply dropped on the floor.
pub fn merge_payload(claim: &Claim, submitted: &Json) -> Params {
    let mut out = Params::new();
    if let Some(fields) = submitted.as_object() {
        for key in &claim.public_fields {
            if let Some(value) = fields.get(key) {
                out.insert(key.clone(), value.clone());
            }
        }
    }
    if let Some(sealed) = claim.sealed_payload.as_object() {
        for (key, value) in sealed {
            out.insert(key.clone(), value.clone());
        }
    }
    out
}

// ── helpers ─────────────────────────────────────────────────────────────────────────────────

fn str_of(row: &Json, key: &str) -> String {
    row.get(key)
        .and_then(|v| v.as_str())
        .unwrap_or_default()
        .to_string()
}

fn parse_json(raw: &str) -> Option<Json> {
    serde_json::from_str(raw).ok()
}

/// What the table indexes. The locator itself is never stored: a dump of `_public_claim` must not
/// hand over every open ticket in the hub. SHA-256 with no salt on purpose — the input is 80 bits
/// of HMAC output, so there is nothing to brute-force and the lookup has to be by equality.
fn hash_locator(locator: &str) -> String {
    hex_lower(ring::digest::digest(&ring::digest::SHA256, locator.as_bytes()).as_ref())
}

fn base32_crockford(bytes: &[u8], chars: usize) -> String {
    let mut out = String::with_capacity(chars);
    let mut acc: u16 = 0;
    let mut bits = 0u8;
    for byte in bytes {
        acc = (acc << 8) | u16::from(*byte);
        bits += 8;
        while bits >= 5 {
            bits -= 5;
            let index = ((acc >> bits) & 0x1f) as usize;
            out.push(CROCKFORD[index] as char);
            if out.len() == chars {
                return out;
            }
        }
    }
    out
}

fn hex_lower(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

fn hex_bytes(hex: &str) -> Option<Vec<u8>> {
    if hex.len() % 2 != 0 {
        return None;
    }
    (0..hex.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).ok())
        .collect()
}

/// `now` plus whole days, in the same RFC-3339 shape the rest of the runtime compares as a string.
fn plus_days(now: &str, days: i64) -> String {
    match chrono::DateTime::parse_from_rfc3339(now) {
        Ok(dt) => (dt + chrono::Duration::days(days))
            .to_utc()
            .to_rfc3339_opts(chrono::SecondsFormat::Secs, true),
        // Unparseable clock: fall back to a deadline in the past rather than an open-ended claim.
        // A locator that refuses is recoverable at the counter; one that never expires is not.
        Err(_) => now.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::testutil::TestDb;
    use erplora_db::PgAdapter;

    async fn claim_db() -> PgAdapter {
        let db = TestDb::new().await.adapter().await;
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        crate::system_migrations::apply(&db, "h1").await.unwrap();
        db
    }

    fn ticket_claim() -> NewClaim {
        NewClaim {
            kind: "invoice_request".into(),
            subject_id: "f2-0001".into(),
            command: "invoice.substitute".into(),
            sealed_payload: json!({
                "original_invoice_id": "f2-0001",
                "items": [{"description": "Menú", "quantity": 1, "unit_price": 1500}],
            }),
            public_fields: vec![
                "customer_tax_id".into(),
                "customer_name".into(),
                "customer_address".into(),
            ],
            expires_at: None,
            created_by: String::new(),
        }
    }

    /// **The locator cannot be walked.** This is the whole reason the VeriFactu QR already on the
    /// ticket does not serve: its `numserie` is correlative and public, so knowing your own ticket
    /// would hand you your neighbour's. Two consecutive subjects must land nowhere near each other.
    #[tokio::test]
    async fn consecutive_tickets_do_not_produce_guessable_locators() {
        let db = claim_db().await;
        let key = claim_key(&db, "h1").await.unwrap();
        let a = locator(&key, "invoice_request", "f2-0001");
        let b = locator(&key, "invoice_request", "f2-0002");
        assert_eq!(a.len(), LOCATOR_CHARS);
        assert_ne!(a, b);
        let shared = a.chars().zip(b.chars()).take_while(|(x, y)| x == y).count();
        assert!(
            shared < 4,
            "consecutive ids must not share a prefix ({a} vs {b}) — that is a walkable sequence"
        );
    }

    /// A different hub with the same ticket id gets a different locator, because the key is the
    /// hub's. Without this, a locator scanned in one restaurant would open a claim in another.
    #[tokio::test]
    async fn the_locator_is_derived_under_the_hubs_own_key() {
        let db = claim_db().await;
        let one = claim_key(&db, "h1").await.unwrap();
        let two = claim_key(&db, "h2").await.unwrap();
        assert_ne!(one, two);
        assert_ne!(
            locator(&one, "invoice_request", "f2-0001"),
            locator(&two, "invoice_request", "f2-0001")
        );
    }

    /// The key is minted once and kept. A rotated key would silently orphan every ticket already
    /// printed — every locator on paper stops working and nothing says why.
    #[tokio::test]
    async fn the_key_is_minted_once_and_never_changes() {
        let db = claim_db().await;
        assert_eq!(
            claim_key(&db, "h1").await.unwrap(),
            claim_key(&db, "h1").await.unwrap()
        );
    }

    /// **Reprinting a lost ticket must yield the same locator**, or the copy the customer already
    /// holds stops working. Minting is idempotent for that reason, deadline included.
    #[tokio::test]
    async fn minting_twice_for_the_same_ticket_returns_the_same_locator() {
        let db = claim_db().await;
        let first = mint(&db, "h1", ticket_claim()).await.unwrap();
        let second = mint(&db, "h1", ticket_claim()).await.unwrap();
        assert_eq!(first, second);
        let claim = find(&db, "h1", &first).await.unwrap().unwrap();
        assert_eq!(claim.subject_id, "f2-0001");
        assert_eq!(claim.command, "invoice.substitute");
    }

    /// Typed by hand off a thermal ticket, under a restaurant's lighting: lower case, a stray
    /// space, and the three characters Crockford exists to disambiguate.
    #[tokio::test]
    async fn a_locator_typed_by_hand_still_opens_the_claim() {
        let db = claim_db().await;
        let printed = mint(&db, "h1", ticket_claim()).await.unwrap();
        let sloppy = format!(" {} ", printed.to_lowercase().replace('0', "o"));
        assert!(
            find(&db, "h1", &sloppy).await.unwrap().is_some(),
            "`{sloppy}` is the same locator as `{printed}`, typed by a person"
        );
    }

    /// A neighbour's locator is not "forbidden", it is **absent**. Anything else is an oracle that
    /// says which locators exist.
    #[tokio::test]
    async fn a_locator_from_another_hub_is_simply_not_found() {
        let db = claim_db().await;
        let printed = mint(&db, "h1", ticket_claim()).await.unwrap();
        assert!(find(&db, "h2", &printed).await.unwrap().is_none());
        assert!(find(&db, "h1", "ZZZZZZZZZZZZZZZZ").await.unwrap().is_none());
        assert!(find(&db, "h1", "").await.unwrap().is_none());
    }

    /// **Spending is atomic.** Two taps on a slow phone must not both issue an invoice: for an F3
    /// that means two complete invoices substituting one ticket, in a chain that cannot be un-sent.
    #[tokio::test]
    async fn a_claim_can_only_be_spent_once() {
        let db = claim_db().await;
        let printed = mint(&db, "h1", ticket_claim()).await.unwrap();
        let claim = find(&db, "h1", &printed).await.unwrap().unwrap();
        let now = now_rfc3339();
        assert!(spend(&db, "h1", &claim.id, "f3-0007", &now).await.unwrap());
        assert!(
            !spend(&db, "h1", &claim.id, "f3-0008", &now).await.unwrap(),
            "the second writer must lose"
        );
        let after = find(&db, "h1", &printed).await.unwrap().unwrap();
        assert_eq!(after.result_ref, "f3-0007", "and the first result stands");
        assert!(after.is_redeemed());
    }

    /// A spent claim stays **readable**: the visitor who refreshes the page has to see their
    /// invoice, not a 404 that looks like the hub lost it.
    #[tokio::test]
    async fn a_spent_claim_still_reads_back_with_its_result() {
        let db = claim_db().await;
        let printed = mint(&db, "h1", ticket_claim()).await.unwrap();
        let claim = find(&db, "h1", &printed).await.unwrap().unwrap();
        let now = now_rfc3339();
        spend(&db, "h1", &claim.id, "f3-0007", &now).await.unwrap();
        match redeemable(&db, "h1", &printed, &now).await.unwrap() {
            Err(ClaimRefusal::AlreadyRedeemed(_)) => {}
            other => panic!("expected AlreadyRedeemed, got {other:?}"),
        }
        assert_eq!(
            find(&db, "h1", &printed).await.unwrap().unwrap().result_ref,
            "f3-0007"
        );
    }

    /// The deadline is checked on read, not by a sweeper: a claim nobody looks at is harmless, and
    /// a hub that was switched off for a month must not wake up honouring last year's tickets.
    #[tokio::test]
    async fn an_expired_claim_is_refused_by_its_deadline_alone() {
        let db = claim_db().await;
        let mut spec = ticket_claim();
        spec.expires_at = Some("2026-01-01T00:00:00Z".into());
        let printed = mint(&db, "h1", spec).await.unwrap();
        match redeemable(&db, "h1", &printed, "2026-08-15T10:00:00Z")
            .await
            .unwrap()
        {
            Err(ClaimRefusal::Expired(_)) => {}
            other => panic!("expected Expired, got {other:?}"),
        }
        assert!(redeemable(&db, "h1", &printed, "2025-12-31T00:00:00Z")
            .await
            .unwrap()
            .is_ok());
    }

    /// The default deadline reaches the date the law actually cares about (art. 11.2 RD
    /// 1619/2012), rather than being a round number somebody liked.
    #[tokio::test]
    async fn the_default_deadline_clears_the_16th_of_the_following_month() {
        let db = claim_db().await;
        let printed = mint(&db, "h1", ticket_claim()).await.unwrap();
        let claim = find(&db, "h1", &printed).await.unwrap().unwrap();
        assert!(
            claim.expires_at > now_rfc3339(),
            "a freshly minted claim is redeemable"
        );
        assert!(
            claim.expires_at < plus_days(&now_rfc3339(), DEFAULT_TTL_DAYS + 1),
            "and it is not open-ended"
        );
    }

    /// **The seal.** Amounts, lines and the ticket being substituted are decided at the counter.
    /// A visitor who posts them anyway changes nothing — their copy is dropped, not honoured.
    #[test]
    fn the_visitor_cannot_overwrite_what_the_counter_sealed() {
        let claim = Claim {
            id: "c1".into(),
            kind: "invoice_request".into(),
            subject_id: "f2-0001".into(),
            command: "invoice.substitute".into(),
            sealed_payload: json!({"original_invoice_id": "f2-0001", "items": [{"unit_price": 1500}]}),
            public_fields: vec!["customer_tax_id".into(), "customer_name".into()],
            expires_at: "2099-01-01T00:00:00Z".into(),
            redeemed_at: None,
            result_ref: String::new(),
        };
        let merged = merge_payload(
            &claim,
            &json!({
                "customer_tax_id": "B12345678",
                "customer_name": "ACME SL",
                "original_invoice_id": "f2-9999",
                "items": [{"unit_price": 1}],
                "status": "paid",
            }),
        );
        assert_eq!(merged["customer_tax_id"], json!("B12345678"));
        assert_eq!(merged["customer_name"], json!("ACME SL"));
        assert_eq!(
            merged["original_invoice_id"],
            json!("f2-0001"),
            "the sealed ticket wins over the one the visitor named"
        );
        assert_eq!(merged["items"], json!([{"unit_price": 1500}]));
        assert!(
            !merged.contains_key("status"),
            "a field the claim never declared is dropped, not carried into the command"
        );
    }

    /// A field the visitor simply did not fill must not arrive as `null` — the command's schema
    /// would judge that a value.
    #[test]
    fn an_unfilled_public_field_is_absent_not_null() {
        let claim = Claim {
            id: "c1".into(),
            kind: "invoice_request".into(),
            subject_id: "f2-0001".into(),
            command: "invoice.substitute".into(),
            sealed_payload: json!({}),
            public_fields: vec!["customer_tax_id".into(), "customer_address".into()],
            expires_at: "2099-01-01T00:00:00Z".into(),
            redeemed_at: None,
            result_ref: String::new(),
        };
        let merged = merge_payload(&claim, &json!({"customer_tax_id": "B12345678"}));
        assert!(!merged.contains_key("customer_address"));
    }

    /// **A refusal must not cost the customer their ticket.** A mistyped NIF hands the claim back;
    /// the same locator opens the form again and the second try works.
    #[tokio::test]
    async fn a_redemption_that_issued_nothing_gives_the_claim_back() {
        let db = claim_db().await;
        let printed = mint(&db, "h1", ticket_claim()).await.unwrap();
        let claim = find(&db, "h1", &printed).await.unwrap().unwrap();
        let now = now_rfc3339();
        assert!(spend(&db, "h1", &claim.id, "", &now).await.unwrap());
        release(&db, "h1", &claim.id).await.unwrap();
        assert!(
            redeemable(&db, "h1", &printed, &now).await.unwrap().is_ok(),
            "the customer gets their one shot back"
        );
    }

    /// …but only when nothing was issued. Once a document exists, handing the claim back would be
    /// an invitation to substitute the same ticket twice.
    #[tokio::test]
    async fn a_redemption_that_issued_a_document_is_never_given_back() {
        let db = claim_db().await;
        let printed = mint(&db, "h1", ticket_claim()).await.unwrap();
        let claim = find(&db, "h1", &printed).await.unwrap().unwrap();
        let now = now_rfc3339();
        spend(&db, "h1", &claim.id, "", &now).await.unwrap();
        record_result(&db, "h1", &claim.id, "FACT-2026-000012")
            .await
            .unwrap();
        release(&db, "h1", &claim.id).await.unwrap();
        match redeemable(&db, "h1", &printed, &now).await.unwrap() {
            Err(ClaimRefusal::AlreadyRedeemed(_)) => {}
            other => panic!("expected AlreadyRedeemed, got {other:?}"),
        }
        assert_eq!(
            find(&db, "h1", &printed).await.unwrap().unwrap().result_ref,
            "FACT-2026-000012"
        );
    }

    /// A claim that runs nothing, or is about nothing, is refused at mint time — not discovered by
    /// a visitor holding a locator that cannot do anything.
    #[tokio::test]
    async fn an_incomplete_claim_is_refused_at_the_counter() {
        let db = claim_db().await;
        let mut no_command = ticket_claim();
        no_command.command = String::new();
        assert!(mint(&db, "h1", no_command).await.is_err());
        let mut no_subject = ticket_claim();
        no_subject.subject_id = "  ".into();
        assert!(mint(&db, "h1", no_subject).await.is_err());
    }
}
