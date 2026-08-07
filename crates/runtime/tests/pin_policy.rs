//! **"Ask for a PIN: always / per shift / never"** — plan step 2b, hub#359.
//!
//! This is the second control over the same decision, and the whole risk of the feature is in how
//! the two compose. hub#358 made the **device** decide how much identity friction it asks for
//! (`shared` = the counter till, `personal` = somebody's own laptop). This dial is what the
//! **business** says on top of it, and it exists for a case the device mode cannot express: the
//! one-person minimarket that does not want to type four digits to sell.
//!
//! ## Who wins, and why that is the only safe answer
//!
//! The two controls speak the same language about exactly one quantity — **how long a session may
//! live** — and there the rule is `min`: **the most restrictive wins, in both directions.**
//!
//! | device      | dial        | session window            | who won                              |
//! |-------------|-------------|---------------------------|--------------------------------------|
//! | `shared`    | `always`    | the short one             | the dial (it tightened the till)     |
//! | `shared`    | `per_shift` | the shift                 | the device — hub#358, unchanged      |
//! | `shared`    | **`never`** | **still the shift**       | **the device: the dial cannot loosen** |
//! | `personal`  | **`always`**| **the short one**         | **the dial: the device cannot loosen** |
//! | `personal`  | `per_shift` | the long one              | the device — hub#358, unchanged      |
//! | `personal`  | `never`     | the long one              | the device — "remember me", as always |
//!
//! Read the two bold rows together: **neither control can lengthen what the other shortened.** A
//! dial that could would be a way to give a shared till a month-long session from a screen that is
//! not the device's, and a device mode that could would make the business-wide decision advisory.
//!
//! Only `always` — the position an owner moves to on purpose — imposes a window of its own. The
//! **default** imposes none, and that is not a detail: the first version of this file asserted that
//! `per_shift` capped at twelve hours, and `the_default_position_changes_nothing` is the test that
//! caught what that meant — every laptop somebody had marked as their own dropping from a month to
//! twelve hours, because a setting they never touched appeared. A default is allowed to cause zero
//! surprise.
//!
//! ## Then what does `never` actually do — and what it deliberately does not
//!
//! It stops the hub asking **which of the staff** is at the till: no pinpad, so whoever opened the
//! till in the morning is the name on every sale until the session expires. That is the
//! consequence the owner is told, in those words.
//!
//! It does **not** unlock anything. The session still dies when the *device* says it does (the row
//! above), so somebody with a real account still has to open the till each shift. `never` gives up
//! **attribution**, never the lock — which is exactly why it can be a legitimate option at all.
//!
//! ## What "per shift" means, honestly
//!
//! **The hub cannot observe a shift.** There is no shift entity in the core, no business hours, no
//! clock-in; the only thing in the product that resembles one is the cash-register session of the
//! `cash_register` **module** — optional, one-per-hub rather than per-till, carrying no device id,
//! and known to be left open for days (ADR-0130). The core has no way to hear a module event
//! either, and hanging the hub's auth policy off an installable module would invert the
//! dependency. So `per_shift` means the shift-length **window** the hub already enforces and
//! already calls a shift (12 h, hub#358) — a clock, not an observed fact. hub#476 tracks binding
//! it to a real close-of-till if that ever becomes something the core can see.
//!
//! Same for `always`: the literal "every sale" needs a lock screen over the running app (hub#456).
//! Until it exists, `always` is the **shortest window the hub can promise and keep**, and the text
//! the owner reads says the hour out loud rather than promising something the hub does not do.
use erplora_db::testutil::fresh_db;
use erplora_runtime::device_mode::DeviceMode;
use erplora_runtime::pin_policy::{effective_session_ttl_secs, shorter_window, PinPolicy};
use erplora_runtime::Runtime;

async fn runtime(hub_id: &str) -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

/// The `name` of a malformed-payload rejection (`RuntimeError::InvalidPayload` → HTTP 422).
fn payload_name_of(error: &erplora_runtime::RuntimeError) -> String {
    match error {
        erplora_runtime::RuntimeError::InvalidPayload { name, .. } => name.clone(),
        other => other.to_string(),
    }
}

/// Every position of the dial, so a new one cannot be added without facing these tests.
const EVERY_POLICY: [PinPolicy; 3] = [PinPolicy::Always, PinPolicy::PerShift, PinPolicy::Never];
/// Every kind of device (hub#358).
const EVERY_MODE: [DeviceMode; 2] = [DeviceMode::Shared, DeviceMode::Personal];

// ── The default is the safe one ────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_hub_that_never_chose_still_asks() {
    let rt = runtime("hub-pp").await;

    assert_eq!(
        rt.pin_policy().await.unwrap(),
        PinPolicy::PerShift,
        "a hub with no row must land on a value that keeps every sale attributed to a person"
    );
    assert_eq!(PinPolicy::default(), PinPolicy::PerShift);
    assert!(
        PinPolicy::default().asks_for_pin(),
        "whatever the default is, it cannot be the one that stops asking"
    );

    // And the default preserves hub#358 exactly: nobody's sessions change length because this
    // setting arrived. The surprise a default is allowed to cause is zero.
    assert_eq!(
        rt.session_ttl_for_device("").await.unwrap(),
        DeviceMode::Shared.session_ttl_secs()
    );
}

#[tokio::test]
async fn a_stored_policy_the_hub_cannot_read_is_never_taken_as_never() {
    let rt = runtime("hub-pp").await;
    rt.set_pin_policy(PinPolicy::Never, "hub_user:admin")
        .await
        .unwrap();
    assert_eq!(rt.pin_policy().await.unwrap(), PinPolicy::Never);

    // A hand-run UPDATE, a restored backup, a column written by a newer version. Reading has to
    // fail CLOSED, and "closed" here means the hub goes back to asking — never the other way.
    for corrupt in ["", "  ", "Never", "never ", "off", "no", "0", "sometimes"] {
        rt.db()
            .execute(
                "UPDATE hub_settings SET value = :v WHERE key = 'pin_policy'",
                &erplora_db::Params::from_iter([("v".to_string(), serde_json::json!(corrupt))]),
            )
            .await
            .unwrap();
        let read = rt.pin_policy().await.unwrap();
        assert_eq!(read, PinPolicy::default(), "`{corrupt}` was read as {read:?}");
        assert!(read.asks_for_pin(), "`{corrupt}` stopped the hub asking");
    }
}

#[test]
fn a_policy_the_hub_does_not_know_is_refused_not_guessed() {
    // The set is CLOSED, with no trimming and no case folding — the same door as
    // `DeviceMode::parse`. Two spellings on the wire would mean the one that slips through is
    // always the lax one, and here the lax one gives up the name on every sale.
    for candidate in ["", " ", "Never", "never ", "NEVER", "nunca", "per shift", "shift", "0"] {
        let refused = PinPolicy::parse(candidate).expect_err(candidate);
        assert_eq!(payload_name_of(&refused), "hub.pin_policy", "{candidate}");
    }

    // The three the hub does know, spelled exactly as they travel on the wire and in the column.
    assert_eq!(PinPolicy::parse("always").unwrap(), PinPolicy::Always);
    assert_eq!(PinPolicy::parse("per_shift").unwrap(), PinPolicy::PerShift);
    assert_eq!(PinPolicy::parse("never").unwrap(), PinPolicy::Never);
    assert_eq!(PinPolicy::Always.as_str(), "always");
    assert_eq!(PinPolicy::PerShift.as_str(), "per_shift");
    assert_eq!(PinPolicy::Never.as_str(), "never");
    // …and the round trip holds for every position, so a new one cannot be added half-way.
    for policy in EVERY_POLICY {
        assert_eq!(PinPolicy::parse(policy.as_str()).unwrap(), policy);
    }
}

// ── The composition: the most restrictive wins ─────────────────────────────────────────────────

#[test]
fn neither_control_can_lengthen_what_the_other_shortened() {
    // The property, before the table: whatever the pair, the session that comes out is no longer
    // than what EITHER of the two allows on its own. This is what "the most restrictive wins"
    // means, and it is the one invariant that must survive anybody adding a fourth position.
    for mode in EVERY_MODE {
        for policy in EVERY_POLICY {
            let effective = effective_session_ttl_secs(mode, policy);
            assert!(
                effective <= mode.session_ttl_secs(),
                "{policy:?} lengthened a {mode:?} device: {effective}s > {}s",
                mode.session_ttl_secs()
            );
            if let Some(cap) = policy.max_session_ttl_secs() {
                assert!(
                    effective <= cap,
                    "{mode:?} lengthened {policy:?}: {effective}s > {cap}s"
                );
            }
            assert!(effective > 0, "no pair may produce a session that is already over");
        }
    }
}

#[test]
fn the_rule_is_the_shorter_window_even_for_a_dial_position_that_does_not_exist_yet() {
    // Found by mutation: with today's three positions every cap is shorter than every device
    // window, so «take the shorter» and «take the CAP» are indistinguishable through the enum — a
    // build that ignored the device entirely passed every test above. The rule has to be `min`
    // *before* somebody adds a position longer than a shift, not after.
    let shift = DeviceMode::Shared.session_ttl_secs();

    assert_eq!(
        shorter_window(shift, Some(shift * 4)),
        shift,
        "a dial cap LONGER than the device window must not lengthen the session"
    );
    assert_eq!(shorter_window(shift, Some(60)), 60, "a shorter cap does tighten");
    assert_eq!(shorter_window(shift, None), shift, "no cap leaves the device's own window");
    assert_eq!(shorter_window(60, Some(60)), 60, "equal windows are that window");

    // And the composition really is that rule, not a second copy of it.
    for mode in EVERY_MODE {
        for policy in EVERY_POLICY {
            assert_eq!(
                effective_session_ttl_secs(mode, policy),
                shorter_window(mode.session_ttl_secs(), policy.max_session_ttl_secs()),
                "{mode:?} + {policy:?}"
            );
        }
    }
}

#[tokio::test]
async fn a_hub_whose_settings_cannot_be_READ_keeps_asking() {
    // The tolerant branch of the reader, which exists for a hub whose `hub_settings` does not exist
    // yet — and which is read on EVERY login. Found by mutation: nothing here covered a failing
    // query, so a build where "the database did not answer" meant `never` passed the whole suite.
    // A lock that opens when the storage behind it is unreachable is not a lock.
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-with-no-tables");

    assert_eq!(
        rt.pin_policy().await.unwrap(),
        PinPolicy::default(),
        "a read that could not happen must not resolve to the position that stops asking"
    );
    assert!(rt.pin_policy().await.unwrap().asks_for_pin());
}

#[test]
fn the_dial_cannot_stop_a_shared_till_expiring_and_the_device_cannot_stop_the_dial() {
    // The two rows that decide whether this feature is safe.

    // «never» on the counter till does NOT buy a session that outlives the shift. It stops the hub
    // asking WHICH person is there — it does not leave the till open.
    assert_eq!(
        effective_session_ttl_secs(DeviceMode::Shared, PinPolicy::Never),
        DeviceMode::Shared.session_ttl_secs(),
        "the dial loosened a device the business itself marked as shared"
    );
    assert!(
        effective_session_ttl_secs(DeviceMode::Shared, PinPolicy::Never)
            < DeviceMode::Personal.session_ttl_secs(),
        "«never» must never be a back door to the long session of a personal device"
    );

    // And the mirror image: the owner's own laptop does not escape a business that asked for the
    // strictest setting. A per-device switch that could opt out of the hub-wide decision would
    // make that decision advisory.
    assert_eq!(
        effective_session_ttl_secs(DeviceMode::Personal, PinPolicy::Always),
        PinPolicy::Always.max_session_ttl_secs().unwrap(),
        "a device marked personal escaped the strictest policy the business chose"
    );
    assert!(
        effective_session_ttl_secs(DeviceMode::Personal, PinPolicy::Always)
            < DeviceMode::Personal.session_ttl_secs()
    );

    // The rest of the table, spelled out.
    assert_eq!(
        effective_session_ttl_secs(DeviceMode::Shared, PinPolicy::Always),
        PinPolicy::Always.max_session_ttl_secs().unwrap()
    );
    assert_eq!(
        effective_session_ttl_secs(DeviceMode::Shared, PinPolicy::PerShift),
        DeviceMode::Shared.session_ttl_secs(),
        "the default pair is exactly what hub#358 already shipped"
    );
    assert_eq!(
        effective_session_ttl_secs(DeviceMode::Personal, PinPolicy::PerShift),
        DeviceMode::Personal.session_ttl_secs(),
        "the default may not shorten a device somebody marked as their own either"
    );
    assert_eq!(
        effective_session_ttl_secs(DeviceMode::Personal, PinPolicy::Never),
        DeviceMode::Personal.session_ttl_secs(),
        "«remember me» on your own device, unchanged"
    );
}

#[test]
fn the_default_position_changes_nothing() {
    // The invariant a default has to satisfy, and the one that caught the first version of this
    // feature: under the position nobody chose, every device gets EXACTLY the window hub#358 gave
    // it. Capping the default at a shift looked stricter and therefore safer — and it would have
    // silently cut every laptop somebody had marked as their own from a month to twelve hours,
    // because a setting they never touched appeared in an update.
    for mode in EVERY_MODE {
        assert_eq!(
            effective_session_ttl_secs(mode, PinPolicy::default()),
            mode.session_ttl_secs(),
            "the default moved the window of a {mode:?} device"
        );
    }
    assert_eq!(PinPolicy::default().max_session_ttl_secs(), None);
}

#[test]
fn the_positions_of_the_dial_are_ordered_and_each_one_is_a_different_promise() {
    // «always» has to be strictly stricter than a shift, or the dial has two positions painted as
    // three and the owner is choosing between a difference that does not exist.
    let always = PinPolicy::Always.max_session_ttl_secs().expect("always caps");
    assert!(
        always < DeviceMode::Shared.session_ttl_secs(),
        "«always» ({always}s) must be shorter than the shift window a shared till already has"
    );
    assert!(
        always <= 60 * 60,
        "«always» promises the till asks again soon: {always}s is not soon"
    );

    // The other two impose no window of THEIR own — «per shift» because it is the default and a
    // default may not move anything, «never» because it is the position that says «do not ask».
    // What separates them is not the clock: it is whether the pinpad is offered at all.
    assert_eq!(PinPolicy::PerShift.max_session_ttl_secs(), None);
    assert_eq!(PinPolicy::Never.max_session_ttl_secs(), None);
    assert!(PinPolicy::Always.asks_for_pin());
    assert!(PinPolicy::PerShift.asks_for_pin());
    assert!(
        !PinPolicy::Never.asks_for_pin(),
        "«never» is the only position that gives up the name on every sale"
    );
}

// ── Through the runtime, on real rows ──────────────────────────────────────────────────────────

#[tokio::test]
async fn the_session_a_login_gets_is_decided_by_both_controls_together() {
    let rt = runtime("hub-pp").await;
    rt.trust_device("till-1", "Counter till").await.unwrap();
    rt.trust_device("laptop-1", "Office laptop").await.unwrap();
    rt.set_device_mode("laptop-1", DeviceMode::Personal, "hub_user:admin")
        .await
        .unwrap();

    // Default dial: hub#358, untouched.
    assert_eq!(
        rt.session_ttl_for_device("till-1").await.unwrap(),
        DeviceMode::Shared.session_ttl_secs()
    );
    assert_eq!(
        rt.session_ttl_for_device("laptop-1").await.unwrap(),
        DeviceMode::Personal.session_ttl_secs()
    );

    // The business asks for the strictest. BOTH devices tighten — including the one somebody
    // marked as their own.
    rt.set_pin_policy(PinPolicy::Always, "hub_user:admin")
        .await
        .unwrap();
    let cap = PinPolicy::Always.max_session_ttl_secs().unwrap();
    assert_eq!(rt.session_ttl_for_device("till-1").await.unwrap(), cap);
    assert_eq!(rt.session_ttl_for_device("laptop-1").await.unwrap(), cap);

    // The family-shop end of the dial. The laptop gets its long session back — and the till does
    // NOT: it is still a device the business said several people share.
    rt.set_pin_policy(PinPolicy::Never, "hub_user:admin")
        .await
        .unwrap();
    assert_eq!(
        rt.session_ttl_for_device("till-1").await.unwrap(),
        DeviceMode::Shared.session_ttl_secs(),
        "«never» must not turn the counter till into a device that stays open for a month"
    );
    assert_eq!(
        rt.session_ttl_for_device("laptop-1").await.unwrap(),
        DeviceMode::Personal.session_ttl_secs()
    );

    // Same fail-closed rule as hub#358: a client that names no device is on the strict side of
    // BOTH controls, whatever the dial says.
    assert_eq!(
        rt.session_ttl_for_device("").await.unwrap(),
        DeviceMode::Shared.session_ttl_secs()
    );
    assert_eq!(
        rt.session_ttl_for_device("a-device-nobody-enrolled")
            .await
            .unwrap(),
        DeviceMode::Shared.session_ttl_secs()
    );
}

#[test]
fn the_dial_does_not_travel_in_a_blueprint() {
    // `PORTABLE_SETTING_KEYS` (ADR-0195 §4) is an ALLOWLIST, so this key is born non-portable — but
    // "born" is the kind of property that survives only while somebody remembers why. A template
    // that carried `never` would switch the pinpad off on every hub that imported it, and the
    // person importing it is not the person who chose it.
    assert!(
        !erplora_runtime::export::PORTABLE_SETTING_KEYS
            .contains(&erplora_runtime::pin_policy::PIN_POLICY_SETTING),
        "a blueprint must not be able to stop somebody else's hub asking who is selling"
    );
}

#[tokio::test]
async fn the_dial_is_of_the_hub_and_survives_a_restart() {
    let test_db = erplora_db::testutil::TestDb::new().await;
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-pp");
    rt.ensure_system_tables().await.unwrap();
    rt.set_pin_policy(PinPolicy::Never, "hub_user:admin")
        .await
        .unwrap();
    drop(rt);

    // Same database, new process: the decision is state of the hub, not of the runtime that was
    // running when somebody made it.
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-pp");
    assert_eq!(rt.pin_policy().await.unwrap(), PinPolicy::Never);

    // A different hub is untouched: this is a per-hub setting, and the hub id comes from the
    // deployment, not from the caller.
    let other = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-somebody-else");
    assert_eq!(other.pin_policy().await.unwrap(), PinPolicy::default());
}
