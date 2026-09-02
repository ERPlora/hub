//! **Step-up authorisation**: the manager's PIN, verified here, buys exactly ONE action
//! (hub#361, PLAN paso 2b rules 2 and 4).
//!
//! In a POS the sensitive actions — a discount, a void, taking payment — are authorised by the
//! manager **without closing the cashier's session**: a dialog appears, the manager types four
//! digits, and the action goes through attributed to them. [`ADR-0238`](hub#360) made the refusal
//! distinguishable ([`RuntimeError::RequiresElevation`](crate::errors::RuntimeError)); this module
//! is what turns an approval into a *yes*.
//!
//! ## What an approval is, and what it is deliberately not
//!
//! Rule 4 is one sentence — *«la elevación es POR ACCIÓN, nunca una sesión. Ventana de segundos, y
//! se acabó»* — and it rules out the shape everybody builds first: a manager MODE that stays open
//! for N minutes. That mode is worse than no control at all, because it looks like control: the
//! manager approves one refund and walks off to the kitchen, and the till stays open behind them
//! for the rest of the window. So:
//!
//! 1. **One execution, not an interval.** A [`Grant`] is *spent* by the action it authorised
//!    ([`Grants::spend`] removes it). Ten actions need ten approvals. The TTL
//!    ([`GRANT_TTL`]) is a **ceiling**, never a licence: it exists so an approval that was never
//!    used stops being spendable, not so more actions fit inside it.
//! 2. **Bound to THE action.** The grant names the `command` and fingerprints the `payload` the
//!    manager was shown ([`fingerprint`]), plus the cashier who asked and the hub. Approving
//!    «void this €4 ticket» therefore cannot void a €400 one — which is the whole difference
//!    between an approval and a permission.
//! 3. **It lives in this process's memory and dies with it.** No table, no column, no migration.
//!    An approval describes somebody standing at the till *now*; one that survived a restart would
//!    be a credential outliving the very event that should have cleared it, and it would travel in
//!    backups, exports and blueprints — where a step-up authorisation has no business being. The
//!    cost of not persisting is that a redeploy mid-approval makes the manager tap again; the cost
//!    of persisting is a spendable credential in a dump.
//! 4. **It cannot be replayed.** The token is an opaque 244-bit secret the client can neither
//!    guess nor mint — it is a *reference* to a grant the runtime holds, never a claim the payload
//!    or the context can assert. Spent once, expired by the ceiling, and useless to anyone but the
//!    exact `(hub, cashier, command, payload)` it was granted for.
//!
//! ## Who may approve
//!
//! Only somebody who **could have done it themselves**: [`Runtime::approve_elevation`] verifies
//! the PIN against `hub_user` and then requires the approver's role to hold the very permission
//! being stepped up to. Combined with rule 5 (only what a `manager` is granted is elevable at all
//! — [`crate::permissions::is_elevable`]), that keeps `admin` territory (fiscal identity, plan,
//! deletion, installing apps) out of reach of four digits typed in front of customers.
//!
//! [`Runtime::approve_elevation`]: crate::Runtime::approve_elevation
use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use erplora_db::{DatabaseAdapter, Params};
use serde_json::Value as Json;
use sha2::{Digest, Sha256};

/// How long an **unused** approval stays spendable.
///
/// A ceiling, not a window to work inside: the grant is spent by its first successful use, so this
/// only decides how long a manager's tap survives if the retry never arrives (a dropped request, a
/// cashier distracted mid-action). Long enough that a slow network does not send the manager back
/// to the till — if approving hurts, the whole shop ends up sharing the manager's credential and
/// the audit trail becomes fiction — and short enough that a token captured from a log or a
/// screenshot is worthless by the time anybody reads it.
pub const GRANT_TTL: Duration = Duration::from_secs(120);

/// **How the approver proves they are standing there** (hub#658).
///
/// Two presentations of one identity, which is what the market decision of hub#658 settled: Toast,
/// Aloha/NCR and Square use the same credential to sign in, to clock in and to approve. What
/// authorises is the ROLE — [`Runtime::approve_elevation`] asks exactly the same questions of both
/// branches, and neither manufactures a privilege its holder did not already have.
///
/// [`Runtime::approve_elevation`]: crate::Runtime::approve_elevation
#[derive(Debug, Clone, Copy)]
pub enum ApproverCredential<'a> {
    /// The pinpad: it resolves people by NAME, so the name travels with the digits.
    Pin { name: &'a str, pin: &'a str },
    /// A badge resolves the person on its own — it replaces the (name, PIN) **pair**, never the
    /// PIN alone. Making a manager type four digits in front of the customer when they already
    /// hold the card is friction the sector removed twenty years ago.
    Badge { badge: &'a str },
}

/// What the manager is being asked to approve. `payload` is the caller's payload **as sent**
/// (before schema defaults are applied): it is what the dialog showed and what the fingerprint
/// has to match on the retry.
#[derive(Debug, Clone, Copy)]
pub struct ElevationRequest<'a> {
    pub credential: ApproverCredential<'a>,
    pub command: &'a str,
    pub payload: &'a Params,
}

impl<'a> ElevationRequest<'a> {
    /// The manager taps their name and types four digits.
    pub fn with_pin(name: &'a str, pin: &'a str, command: &'a str, payload: &'a Params) -> Self {
        Self {
            credential: ApproverCredential::Pin { name, pin },
            command,
            payload,
        }
    }

    /// The manager swipes their card, and that IS the approval.
    pub fn with_badge(badge: &'a str, command: &'a str, payload: &'a Params) -> Self {
        Self {
            credential: ApproverCredential::Badge { badge },
            command,
            payload,
        }
    }
}

/// A minted approval. The `token` is the only part the client ever sees.
#[derive(Debug, Clone)]
pub struct ElevationApproval {
    /// Opaque secret, meaningless outside this process. The client sends it back on the retry.
    pub token: String,
    /// The permission that was stepped up to — the same field the refusal named, so the dialog
    /// never has to parse a sentence.
    pub permission: String,
    /// `hub_user.id` of the manager who approved. This is the seam hub#362 writes as `approved_by`
    /// next to the cashier's `created_by`.
    pub approved_by: String,
    /// Their name, for the confirmation the cashier sees («approved by Sofía»).
    pub approver_name: String,
    /// [`GRANT_TTL`] in seconds, so the UI can stop offering a retry that will be refused.
    pub expires_in_seconds: u64,
}

/// Everything an approval is tied to. Every field is part of the answer to *«may THIS run?»*, and
/// any mismatch is simply a grant that does not exist.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub(crate) struct Binding {
    pub hub_id: String,
    /// The cashier the approval was granted to (`RequestContext::user_id`).
    pub requester: String,
    pub command: String,
    /// [`fingerprint`] of the payload the manager was shown.
    pub fingerprint: String,
    /// The permission being stepped up to. Belt and braces: a command's permission cannot change
    /// mid-approval without a reinstall, but a grant that outlived such a change would be a grant
    /// for a door that now means something else.
    pub permission: String,
}

struct Grant {
    binding: Binding,
    approved_by: String,
    /// **What the approver used** (hub#658). It travels inside the grant and not inside the
    /// [`Binding`] on purpose: the binding is what the retry has to MATCH, and the retry sends
    /// only the token — it does not re-present the card. Carrying it here is what lets
    /// [`record_spend`] name the credential on the receipt without the client ever being asked.
    credential: crate::identity::Credential,
    expires_at: Instant,
}

/// An approval that has just been spent: who allowed it and what they used to say so.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SpentApproval {
    /// `hub_user.id` of the approver.
    pub approved_by: String,
    pub credential: crate::identity::Credential,
}

/// The live approvals of this runtime. Tiny (bounded by the approvals a human taps within
/// [`GRANT_TTL`]) and touched twice per elevated action, so one `Mutex` is plenty.
#[derive(Default)]
pub struct Grants {
    entries: Mutex<HashMap<String, Grant>>,
}

impl Grants {
    pub fn new() -> Self {
        Self::default()
    }

    /// Mint an approval and return its token.
    pub(crate) fn mint(
        &self,
        binding: Binding,
        approved_by: &str,
        credential: crate::identity::Credential,
    ) -> String {
        self.mint_at(binding, approved_by, credential, Instant::now())
    }

    /// Spend the approval matching `binding`, returning who approved it and with what.
    ///
    /// **Removes it.** That single line is rule 4: after this call the same token, for the same
    /// action, buys nothing. `None` = there is no such approval (never granted, already spent,
    /// expired, or granted for a different action, cashier or hub) — and every one of those is
    /// reported identically, because to the caller they mean the same thing: ask the manager.
    pub(crate) fn spend(&self, token: &str, binding: &Binding) -> Option<SpentApproval> {
        self.spend_at(token, binding, Instant::now())
    }

    // ── The same logic with an explicit clock, so the tests below can prove expiry ──

    fn mint_at(
        &self,
        binding: Binding,
        approved_by: &str,
        credential: crate::identity::Credential,
        now: Instant,
    ) -> String {
        let token = new_token();
        let mut entries = self.lock();
        sweep(&mut entries, now);
        entries.insert(
            token.clone(),
            Grant {
                binding,
                approved_by: approved_by.to_string(),
                credential,
                expires_at: now + GRANT_TTL,
            },
        );
        token
    }

    fn spend_at(&self, token: &str, binding: &Binding, now: Instant) -> Option<SpentApproval> {
        let mut entries = self.lock();
        sweep(&mut entries, now);
        let grant = entries.get(token)?;
        // A token that resolves to a grant for a DIFFERENT action is not an error to report and
        // not a reason to burn the grant: the cashier may simply have retried the wrong thing,
        // and consuming it here would let anybody destroy an approval by guessing… nothing.
        if grant.binding != *binding {
            return None;
        }
        entries.remove(token).map(|g| SpentApproval {
            approved_by: g.approved_by,
            credential: g.credential,
        })
    }

    /// Live approvals. Only the tests look; production never needs to count them.
    #[cfg(test)]
    fn len(&self) -> usize {
        self.lock().len()
    }

    fn lock(&self) -> std::sync::MutexGuard<'_, HashMap<String, Grant>> {
        // A poisoned mutex here would mean a panic while holding it; the map is a plain
        // `HashMap` with no invariant a panic could half-break, so recovering is safe and far
        // better than taking the till down.
        self.entries.lock().unwrap_or_else(|e| e.into_inner())
    }
}

/// Write the **receipt** of an approval that has just been spent (hub#362, rule 3).
///
/// ## Why the runtime, and not the module
///
/// hub#361 already hands the manager's id to a module's SQL as `:approved_by`, so a module *can*
/// stamp it next to `created_by`. That is not enough to call it an audit trail: a module that
/// never declares the column loses the attribution **in silence**, and the party deciding is the
/// module author — the one with the least reason to record that their own manager-level command
/// was waved through. Today **none** of the 24 published modules declares one, so «the module
/// records it» means «nothing is recorded».
///
/// The runtime is the only component that knows an approval happened, so the runtime keeps the
/// record. Same shape as [ADR-0238](crate::permissions::is_elevable): *a manifest coins no
/// privilege* — and, symmetrically, a manifest cannot drop the trace either. The column in a
/// module's own table stays welcome (a ticket that prints «approved by Sofía» wants it), but
/// nothing about the audit depends on it, and no module had to be republished for this.
///
/// ## Why a table, when the grant deliberately has none
///
/// [`Grants`] lives in memory precisely so an approval cannot outlive the process, travel in a
/// backup or be spent out of a dump. A receipt is the opposite kind of thing: a fact about
/// something that already happened, worth nothing to an attacker and useless unless it survives
/// exactly what the grant must not.
///
/// ## Why before the command runs, and outside its transaction
///
/// The grant is gone the instant it is spent, whatever the command does next. Writing the receipt
/// afterwards — or inside the command's own transaction — would mean an approval spent on an
/// action that then failed disappears from the record: a burnt approval and no trace of who burnt
/// it. What is recorded is *an approval was used for this*, which is true either way.
///
/// **The error is not swallowed.** If the receipt cannot be written the elevated command must not
/// run: otherwise «break the audit» becomes a way to have a manager-level action executed leaving
/// no trace, which is the exact outcome this exists to prevent.
pub(crate) async fn record_spend(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    command: &str,
    permission: &str,
    created_by: &str,
    spent: &SpentApproval,
    fingerprint: &str,
) -> crate::errors::Result<()> {
    let approved_by = spent.approved_by.as_str();
    let mut p = Params::new();
    p.insert("id".into(), Json::String(crate::registry::new_id()));
    p.insert("hub_id".into(), Json::String(hub_id.to_string()));
    p.insert("command".into(), Json::String(command.to_string()));
    p.insert("permission".into(), Json::String(permission.to_string()));
    // The two attributions, side by side in one row — which is the whole of rule 3. Both come
    // from the runtime: the cashier from the authenticated context, the manager from the grant
    // just spent. Neither is ever read from the payload.
    p.insert("created_by".into(), Json::String(created_by.to_string()));
    p.insert("approved_by".into(), Json::String(approved_by.to_string()));
    // The fingerprint of the payload the manager was shown: it says WHICH €4 ticket, not just
    // that some `till.sale.void` was approved.
    p.insert(
        "payload_fingerprint".into(),
        Json::String(fingerprint.to_string()),
    );
    p.insert(
        "created_at".into(),
        Json::String(crate::registry::now_rfc3339()),
    );
    // **Which credential said yes, and which card** (hub#658). This is the criterion the market
    // study called the one worth the most: no competitor records it, so in every one of them
    // «somebody used my card» is structurally unanswerable — their log only names the employee.
    // The reference is the badge's INDEX, never the number printed on it, so the audit trail does
    // not become a list of live credentials.
    p.insert(
        "credential_kind".into(),
        Json::String(spent.credential.kind.clone()),
    );
    p.insert(
        "credential_ref".into(),
        Json::String(spent.credential.reference.clone()),
    );
    db.execute(
        "INSERT INTO _elevation_audit \
         (id, hub_id, command, permission, created_by, approved_by, payload_fingerprint, \
          created_at, credential_kind, credential_ref) \
         VALUES (:id, :hub_id, :command, :permission, :created_by, :approved_by, \
         :payload_fingerprint, :created_at, :credential_kind, :credential_ref)",
        &p,
    )
    .await?;
    Ok(())
}

/// Drop everything already past its ceiling. Called on both doors, so an approval nobody spent
/// stops occupying memory (and stops being spendable) without a background task.
fn sweep(entries: &mut HashMap<String, Grant>, now: Instant) {
    entries.retain(|_, g| g.expires_at > now);
}

/// A fresh opaque token: 244 bits of OS randomness, hex. Two v4 UUIDs rather than a hand-rolled
/// RNG — the same source `registry::new_id` already trusts. It carries **no** information: it is
/// a lookup key for a grant this process holds, so forging one means guessing it.
fn new_token() -> String {
    format!(
        "{}{}",
        uuid::Uuid::new_v4().simple(),
        uuid::Uuid::new_v4().simple()
    )
}

/// A stable fingerprint of the payload the manager approved.
///
/// This is **the** security property of the binding: «approve THIS €4 ticket» must not authorise
/// the €400 one. So the encoding it hashes has to be **injective** — two payloads that differ in
/// any way must produce different bytes — and it must be so *by construction*, not because no
/// test has found a collision yet. The caller controls the payload, so anything a separator-based
/// format leaves ambiguous is a collision somebody can build by hand.
pub(crate) fn fingerprint(payload: &Params) -> String {
    let mut hasher = Sha256::new();
    let mut canonical = String::new();
    write_canonical(&Json::Object(payload.clone()), &mut canonical);
    hasher.update(canonical.as_bytes());
    format!("{:x}", hasher.finalize())
}

/// Injective, **length-prefixed** encoding of a JSON value. Deliberately NOT JSON.
///
/// Every element opens with a **type tag** and every variable-length part carries its **length in
/// bytes** (or its element count), so a reader always knows where each piece ends and no content
/// can ever be mistaken for structure:
///
/// | Value | Bytes |
/// |---|---|
/// | `null` / `true` / `false` | `n` · `t` · `f` |
/// | number | `#<len>:<serde repr>` |
/// | string | `s<len>:<utf-8>` |
/// | array | `a<count>:` then each item, **in order** (in a payload, order is meaning) |
/// | object | `o<count>:` then each `key,value` pair with keys **sorted** |
///
/// **Why not JSON text.** A `{"a":…,"b":…}` format is only injective if the separators cannot
/// appear inside the data — and here they can: with keys written plainly, `{"ab":"c"}` and
/// `{"a":"bc"}` both render `ab:c`; with quoting but no length, a key containing `","` can close
/// its own entry and open a fake one. Length prefixes remove the whole class: the bytes of a
/// string are never *read* as structure, because the reader was told how many of them there are.
/// That also makes the format visibly different from `serde_json`'s, so a fallback to
/// `Value::to_string()` anywhere in here is a failing test rather than a silent equivalence.
fn write_canonical(value: &Json, out: &mut String) {
    match value {
        Json::Null => out.push('n'),
        Json::Bool(true) => out.push('t'),
        Json::Bool(false) => out.push('f'),
        // A number is tagged apart from a string, so `1` and `"1"` can never collide.
        Json::Number(n) => write_tagged(out, '#', &n.to_string()),
        Json::String(s) => write_tagged(out, 's', s),
        Json::Array(items) => {
            out.push_str(&format!("a{}:", items.len()));
            for item in items {
                write_canonical(item, out);
            }
        }
        Json::Object(map) => write_object(map.iter().map(|(k, v)| (k.as_str(), v)), out),
    }
}

/// `<tag><byte-len>:<body>` — the length is what makes the body unreadable as structure.
fn write_tagged(out: &mut String, tag: char, body: &str) {
    out.push(tag);
    out.push_str(&body.len().to_string());
    out.push(':');
    out.push_str(body);
}

/// Encodes an object from **any** iterator of pairs, sorting the keys itself.
///
/// Taking an iterator rather than a `&Map` is what makes the sort **testable**: `serde_json` is
/// built here without `preserve_order`, so a `Map` is a `BTreeMap` and hands its keys over
/// already sorted — a test that went through `Map` could never tell whether this function orders
/// anything. Cargo unifies features across the whole dependency graph, so the day anything turns
/// `preserve_order` on, `Map` becomes an `IndexMap` yielding **insertion** order, and without the
/// sort two spellings of the same payload would hash differently: a cashier's legitimate retry
/// refused at random, with nothing in the logs to explain it. The unit tests below feed
/// deliberately unsorted pairs straight in.
fn write_object<'a>(pairs: impl Iterator<Item = (&'a str, &'a Json)>, out: &mut String) {
    let mut pairs: Vec<(&str, &Json)> = pairs.collect();
    pairs.sort_by(|a, b| a.0.cmp(b.0));
    out.push_str(&format!("o{}:", pairs.len()));
    for (k, v) in pairs {
        write_tagged(out, 's', k);
        write_canonical(v, out);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn params(v: Json) -> Params {
        v.as_object().cloned().unwrap_or_default()
    }

    fn binding() -> Binding {
        Binding {
            hub_id: "h1".into(),
            requester: "u-cashier".into(),
            command: "till.sale.take_payment".into(),
            fingerprint: fingerprint(&params(json!({ "label": "table 4" }))),
            permission: "till.take_payment".into(),
        }
    }

    #[test]
    fn an_approval_is_spent_by_the_first_action_that_uses_it() {
        // Rule 4 in one assertion: the approval is not a window somebody works inside, it is a
        // single yes. A second identical action finds nothing left.
        let grants = Grants::new();
        let token = grants.mint(binding(), "u-manager", crate::identity::Credential::pin());

        assert_eq!(
            grants.spend(&token, &binding()).map(|s| s.approved_by),
            Some("u-manager".to_string())
        );
        assert_eq!(grants.spend(&token, &binding()), None);
        assert_eq!(grants.len(), 0, "spending removes it, it does not mark it");
    }

    /// Regression test for ERPlora/hub#978. Since the server's runtime sits behind a `RwLock`,
    /// commands overlap and two retries can reach `spend` at the same instant; the exactly-once
    /// spend is this store's own guarantee (one `get` + `remove` under one guard), not the
    /// request lock's. Sixteen threads released by one barrier race for the same token, and
    /// exactly one wins — every round. Many rounds on purpose: a `get` and a `remove` that are
    /// not under the same guard lose the race only when the scheduler interleaves them, which
    /// one round misses about half the time and fifty rounds never do. The HTTP-level test of the
    /// same rule (`multi_till_hub978`) has the same blind spot with far fewer chances to hit it.
    #[test]
    fn a_racing_spend_is_won_by_exactly_one_thread_hub978() {
        use std::sync::{Arc, Barrier};

        const RACERS: usize = 16;
        const ROUNDS: usize = 50;
        let grants = Arc::new(Grants::new());
        for round in 0..ROUNDS {
            let token = grants.mint(binding(), "u-manager", crate::identity::Credential::pin());
            let barrier = Arc::new(Barrier::new(RACERS));
            let racers: Vec<_> = (0..RACERS)
                .map(|_| {
                    let grants = Arc::clone(&grants);
                    let barrier = Arc::clone(&barrier);
                    let token = token.clone();
                    std::thread::spawn(move || {
                        barrier.wait();
                        grants.spend(&token, &binding()).is_some()
                    })
                })
                .collect();
            let wins = racers
                .into_iter()
                .map(|racer| racer.join().expect("a racer panicked"))
                .filter(|won| *won)
                .count();

            assert_eq!(
                wins, 1,
                "round {round}: exactly one racing retry spends the approval"
            );
            assert_eq!(
                grants.len(),
                0,
                "round {round}: the approval is gone once spent"
            );
        }
    }

    #[test]
    fn the_ceiling_is_measured_in_seconds_not_hours() {
        // ⚠️ Asserted in ABSOLUTE seconds on purpose. Every other test here says
        // `start + GRANT_TTL`, which is true of a 24-hour TTL as happily as of a 2-minute one:
        // a suite written that way only ever agrees with the constant. Rule 4 is
        // «ventana de SEGUNDOS, y se acabó» — an approval that outlived the customer standing at
        // the counter would be the manager mode this design exists to refuse, and one that died
        // before the retry arrived would send the manager back to the till until the shop gave up
        // and shared a password instead. Both edges are named here.
        assert!(
            GRANT_TTL >= Duration::from_secs(30),
            "too short to survive a slow retry: {GRANT_TTL:?}"
        );
        assert!(
            GRANT_TTL <= Duration::from_secs(300),
            "a step-up ceiling is seconds, not a session: {GRANT_TTL:?}"
        );

        let grants = Grants::new();
        let start = Instant::now();
        let token = grants.mint_at(
            binding(),
            "u-manager",
            crate::identity::Credential::pin(),
            start,
        );
        assert_eq!(
            grants.spend_at(&token, &binding(), start + Duration::from_secs(600)),
            None,
            "ten minutes later nothing is spendable, whatever the constant says"
        );
    }

    #[test]
    fn an_unused_approval_stops_being_spendable_at_the_ceiling() {
        let grants = Grants::new();
        let start = Instant::now();
        let token = grants.mint_at(
            binding(),
            "u-manager",
            crate::identity::Credential::pin(),
            start,
        );

        // Still inside the ceiling: the retry that took a moment to arrive still works.
        assert!(grants
            .spend_at(
                &token,
                &binding(),
                start + GRANT_TTL - Duration::from_secs(1)
            )
            .is_some());

        let token = grants.mint_at(
            binding(),
            "u-manager",
            crate::identity::Credential::pin(),
            start,
        );
        // Exactly at the ceiling is already over: an approval that expires "at" a moment must not
        // still be usable during it.
        assert_eq!(grants.spend_at(&token, &binding(), start + GRANT_TTL), None);
        assert_eq!(
            grants.spend_at(
                &token,
                &binding(),
                start + GRANT_TTL + Duration::from_secs(60)
            ),
            None
        );
        assert_eq!(grants.len(), 0, "the expired grant is swept, not kept");
    }

    #[test]
    fn every_part_of_the_binding_has_to_match() {
        // Each field closes a different way an approval could be turned into a licence. The
        // payload one is the load-bearing one: approving «this €4 ticket» must not void a €400 one.
        let variants: [(&str, Binding); 4] = [
            (
                "another cashier",
                Binding {
                    requester: "u-other".into(),
                    ..binding()
                },
            ),
            (
                "another command",
                Binding {
                    command: "till.sale.void".into(),
                    ..binding()
                },
            ),
            (
                "another ticket",
                Binding {
                    fingerprint: fingerprint(&params(json!({ "label": "table 11" }))),
                    ..binding()
                },
            ),
            (
                "another permission",
                Binding {
                    permission: "till.void_sale".into(),
                    ..binding()
                },
            ),
        ];
        for (what, other) in variants {
            let grants = Grants::new();
            let token = grants.mint(binding(), "u-manager", crate::identity::Credential::pin());
            assert_eq!(grants.spend(&token, &other), None, "{what} must not match");
            // …and the mismatch does not burn the real approval.
            assert!(
                grants.spend(&token, &binding()).is_some(),
                "{what}: the genuine action must still go through"
            );
        }
    }

    #[test]
    fn a_grant_of_another_hub_is_not_a_grant_here() {
        // The tenant is never negotiable. One process serves one hub today, but the binding does
        // not rely on that being true forever.
        let grants = Grants::new();
        let token = grants.mint(binding(), "u-manager", crate::identity::Credential::pin());
        let elsewhere = Binding {
            hub_id: "h2".into(),
            ..binding()
        };
        assert_eq!(grants.spend(&token, &elsewhere), None);
    }

    #[test]
    fn a_token_nobody_minted_is_simply_not_a_grant() {
        let grants = Grants::new();
        grants.mint(binding(), "u-manager", crate::identity::Credential::pin());
        for forged in ["", "approved", &"0".repeat(64), &new_token()] {
            assert_eq!(
                grants.spend(forged, &binding()),
                None,
                "`{forged}` is not a token"
            );
        }
    }

    #[test]
    fn two_tokens_are_never_the_same() {
        // The token IS the secret: it carries nothing, so unguessable is all it has to be.
        let a = new_token();
        let b = new_token();
        assert_ne!(a, b);
        assert_eq!(a.len(), 64, "244 bits of randomness, hex");
        assert!(a.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn the_same_payload_fingerprints_the_same_however_it_was_written() {
        // Key order must not decide whether the cashier's retry is accepted.
        let a = params(json!({ "label": "table 4", "amount_cents": 400 }));
        let b = params(json!({ "amount_cents": 400, "label": "table 4" }));
        assert_eq!(fingerprint(&a), fingerprint(&b));
        // Nested objects too: sorting only the top level would leave the inner order deciding.
        let c = params(json!({ "line": { "qty": 1, "sku": "x" } }));
        let d = params(json!({ "line": { "sku": "x", "qty": 1 } }));
        assert_eq!(fingerprint(&c), fingerprint(&d));
    }

    /// Pins the encoding **byte for byte**. Every other test here compares one fingerprint against
    /// another, which stays true under any change applied to both sides — so a format that quietly
    /// stopped tagging, stopped length-prefixing or fell back to `Value::to_string()` would go
    /// unnoticed. This is the assertion that notices.
    #[test]
    fn the_canonical_encoding_is_exactly_this() {
        fn enc(v: Json) -> String {
            let mut s = String::new();
            write_canonical(&v, &mut s);
            s
        }
        assert_eq!(enc(json!(null)), "n");
        assert_eq!(enc(json!(true)), "t");
        assert_eq!(enc(json!(false)), "f");
        assert_eq!(enc(json!(400)), "#3:400");
        assert_eq!(enc(json!("table 4")), "s7:table 4");
        assert_eq!(enc(json!([])), "a0:");
        assert_eq!(enc(json!(["a", 1])), "a2:s1:a#1:1");
        assert_eq!(enc(json!({})), "o0:");
        // Keys sorted, each part tagged and length-prefixed — and NOT JSON, which is the point:
        // `serde_json` would render this `{"amount_cents":400,"label":"x"}`.
        assert_eq!(
            enc(json!({ "label": "x", "amount_cents": 400 })),
            "o2:s12:amount_cents#3:400s5:labels1:x"
        );
        assert_eq!(enc(json!({ "l": { "q": 1 } })), "o1:s1:lo1:s1:q#1:1");
    }

    /// The sort is real code, not a courtesy of `BTreeMap`.
    ///
    /// A `serde_json::Map` hands its keys over already sorted while `preserve_order` is off, so
    /// nothing that goes through `Params` can tell whether this crate orders anything at all.
    /// Feeding the pairs in **backwards** can.
    #[test]
    fn an_object_is_ordered_by_this_crate_whatever_order_the_pairs_arrive_in() {
        let one = json!(1);
        let two = json!(2);
        let mut backwards = String::new();
        write_object([("b", &two), ("a", &one)].into_iter(), &mut backwards);
        let mut forwards = String::new();
        write_object([("a", &one), ("b", &two)].into_iter(), &mut forwards);

        assert_eq!(backwards, forwards);
        assert_eq!(backwards, "o2:s1:a#1:1s1:b#1:2", "sorted, whoever asked");
    }

    /// The collisions a caller would try to BUILD, given that they control every byte of the
    /// payload. Under a separator-based format (`"a":1,"b":2`) each of these pairs can be made to
    /// render identically — which would mean one approval covering two different actions. Length
    /// prefixes make them impossible, and these are the pairs that say so.
    #[test]
    fn no_payload_can_be_dressed_up_as_another_one() {
        let collisions: [(Json, Json); 6] = [
            // The key eats the separator: `ab:c` vs `ab:c` if keys were written raw.
            (json!({ "ab": "c" }), json!({ "a": "bc" })),
            // The value closes its own entry and opens a fake one.
            (json!({ "a": "1,\"b\":2" }), json!({ "a": "1", "b": 2 })),
            // An empty string next to a longer key: `"a""b"` vs `"ab"""` without lengths.
            (json!({ "a": "b" }), json!({ "ab": "" })),
            // Structure vs the text that looks like it.
            (json!({ "a": { "b": 1 } }), json!({ "a": "{\"b\":1}" })),
            // An array of one vs the item itself.
            (json!({ "a": ["b"] }), json!({ "a": "b" })),
            // A number vs the digits as a string.
            (json!({ "a": 1 }), json!({ "a": "1" })),
        ];
        for (left, right) in collisions {
            assert_ne!(
                fingerprint(&params(left.clone())),
                fingerprint(&params(right.clone())),
                "{left} and {right} must never approve each other"
            );
        }
    }

    #[test]
    fn a_payload_that_differs_at_all_fingerprints_differently() {
        let base = params(json!({ "sale_id": "s1", "amount_cents": 400 }));
        for other in [
            json!({ "sale_id": "s1", "amount_cents": 40000 }),
            json!({ "sale_id": "s2", "amount_cents": 400 }),
            json!({ "sale_id": "s1", "amount_cents": 400, "extra": true }),
            json!({ "sale_id": "s1" }),
            json!({}),
            // A number is not the string that looks like it, and `null` is not absence.
            json!({ "sale_id": "s1", "amount_cents": "400" }),
            json!({ "sale_id": "s1", "amount_cents": null }),
        ] {
            assert_ne!(
                fingerprint(&base),
                fingerprint(&params(other.clone())),
                "{other} must not pass as the approved payload"
            );
        }
        // Arrays are ordered: two lines swapped is a different ticket, not the same one.
        assert_ne!(
            fingerprint(&params(json!({ "lines": ["a", "b"] }))),
            fingerprint(&params(json!({ "lines": ["b", "a"] })))
        );
        // …and a key cannot smuggle a separator to collide with another shape.
        assert_ne!(
            fingerprint(&params(json!({ "a": "1,\"b\":2" }))),
            fingerprint(&params(json!({ "a": "1", "b": 2 })))
        );
    }

    #[test]
    fn one_approval_does_not_disturb_another() {
        // Two cashiers at two tills, each with their own approval. Spending one must not sweep,
        // shadow or invalidate the other — a single shared store is not a single shared grant.
        let grants = Grants::new();
        let mine = binding();
        let theirs = Binding {
            requester: "u-other".into(),
            ..binding()
        };
        let a = grants.mint(
            mine.clone(),
            "u-manager",
            crate::identity::Credential::pin(),
        );
        let b = grants.mint(
            theirs.clone(),
            "u-manager",
            crate::identity::Credential::pin(),
        );
        assert_ne!(a, b);

        assert!(grants.spend(&a, &mine).is_some());
        assert!(
            grants.spend(&b, &theirs).is_some(),
            "the other till is untouched"
        );
    }
}
