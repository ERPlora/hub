//! **Device mode** — `shared` (the counter till) vs `personal` (your own laptop), plan step 2b,
//! hub#357.
//!
//! The same business has both at once and the SAME person uses both, so the mode cannot be a hub
//! setting: it belongs to the **device**, keyed by the identifier that already exists
//! (`X-Device-Id`, ADR-0154). It is the base of the conditional pinpad (hub#358) and of the "ask
//! for a PIN: always / per shift / never" setting (hub#359).
//!
//! This is a **security** contract, because the mode decides how much identity friction there is
//! (`personal` = no pinpad, long session, "remember me"). The `device_id` is an *identifier*, not
//! a credential: the client sends it in plain text and can send any string it likes. So the whole
//! design leans on three properties, and these tests are what hold them:
//!
//!  - **The hub decides the mode, never the client.** It is persisted server-side and the only way
//!    to write it is [`Runtime::set_device_mode`], which the HTTP layer puts behind an admin
//!    session (see `crates/server/tests/device_mode_api.rs`). Nothing the client can send declares
//!    a mode.
//!  - **An unknown device gets the STRICT mode.** A device the hub never met is `shared` — maximum
//!    friction — and there is no code path where the absence of a row means the lax mode.
//!  - **`personal` cannot exist without device-trust.** The mode lives in the row of
//!    `hub_trusted_device`, so only a device that already proved identity online (§2.9, hub#330)
//!    can hold one, and revoking the trust of a stolen laptop takes its lax mode with it.
use erplora_db::testutil::fresh_db;
use erplora_runtime::device_mode::DeviceMode;
use erplora_runtime::Runtime;

async fn runtime(hub_id: &str) -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

/// The stable rejection code of a refused write (`RuntimeError::Domain`), or the raw message when
/// the runtime answered with something else — the assertion then shows what it really said.
fn code_of(error: &erplora_runtime::RuntimeError) -> String {
    match error {
        erplora_runtime::RuntimeError::Domain { code, .. } => code.clone(),
        other => other.to_string(),
    }
}

/// The `name` of a malformed-payload rejection (`RuntimeError::InvalidPayload` → HTTP 422), or the
/// raw message when the runtime answered with something else.
fn payload_name_of(error: &erplora_runtime::RuntimeError) -> String {
    match error {
        erplora_runtime::RuntimeError::InvalidPayload { name, .. } => name.clone(),
        other => other.to_string(),
    }
}

#[tokio::test]
async fn a_device_the_hub_never_met_is_shared() {
    let rt = runtime("hub-dm").await;

    assert_eq!(
        rt.device_mode("never-seen-before").await.unwrap(),
        DeviceMode::Shared,
        "an unknown device gets the strict mode: the lax one is never a default"
    );
    assert_eq!(
        rt.device_mode("").await.unwrap(),
        DeviceMode::Shared,
        "a client that identifies no device is the shape of the attack, not a personal laptop"
    );
}

#[tokio::test]
async fn an_administrator_marks_a_known_device_personal_and_it_is_persisted() {
    let rt = runtime("hub-dm").await;
    // The device did an online (cloud) login once: that is what `trust_device` records.
    rt.trust_device("laptop-1", "Office laptop").await.unwrap();

    assert_eq!(
        rt.device_mode("laptop-1").await.unwrap(),
        DeviceMode::Shared,
        "known is not personal: it takes somebody deciding"
    );

    rt.set_device_mode("laptop-1", DeviceMode::Personal, "hub_user:admin")
        .await
        .unwrap();
    assert_eq!(rt.device_mode("laptop-1").await.unwrap(), DeviceMode::Personal);

    // Lowering the identity friction of a terminal leaves a trace: WHO decided, and WHEN.
    let audit = rt
        .db()
        .query(
            "SELECT mode_set_by, mode_set_at FROM hub_trusted_device WHERE device_id = 'laptop-1'",
            &erplora_db::Params::new(),
        )
        .await
        .unwrap();
    assert_eq!(audit.rows[0]["mode_set_by"], serde_json::json!("hub_user:admin"));
    assert!(
        !audit.rows[0]["mode_set_at"]
            .as_str()
            .unwrap_or_default()
            .is_empty(),
        "the decision is stamped with its instant"
    );

    // And it is a two-way switch: the laptop goes back behind the counter.
    rt.set_device_mode("laptop-1", DeviceMode::Shared, "hub_user:admin")
        .await
        .unwrap();
    assert_eq!(rt.device_mode("laptop-1").await.unwrap(), DeviceMode::Shared);
}

#[tokio::test]
async fn the_mode_is_of_the_device_not_of_the_hub() {
    let rt = runtime("hub-dm").await;
    rt.trust_device("till-1", "Counter till").await.unwrap();
    rt.trust_device("laptop-1", "Office laptop").await.unwrap();

    rt.set_device_mode("laptop-1", DeviceMode::Personal, "hub_user:admin")
        .await
        .unwrap();

    assert_eq!(
        rt.device_mode("till-1").await.unwrap(),
        DeviceMode::Shared,
        "the till of the very same business stays shared: this is not a hub-wide setting"
    );
    assert_eq!(rt.device_mode("laptop-1").await.unwrap(), DeviceMode::Personal);
}

#[tokio::test]
async fn a_device_that_never_proved_itself_online_cannot_be_personal() {
    let rt = runtime("hub-dm").await;

    let refused = rt
        .set_device_mode("some-id-from-a-header", DeviceMode::Personal, "hub_user:admin")
        .await
        .expect_err("a device id nobody has ever seen is not a device: it is a string");
    assert_eq!(code_of(&refused), "hub.device.unknown_device");
    assert_eq!(
        rt.device_mode("some-id-from-a-header").await.unwrap(),
        DeviceMode::Shared,
        "a refused write changes nothing"
    );

    // Not even to `shared`: the write door does not create devices either.
    let refused_shared = rt
        .set_device_mode("some-id-from-a-header", DeviceMode::Shared, "hub_user:admin")
        .await
        .expect_err("the write door records a decision about a known device, it does not enrol one");
    assert_eq!(code_of(&refused_shared), "hub.device.unknown_device");
}

#[tokio::test]
async fn revoking_the_trust_of_a_lost_device_takes_its_lax_mode_with_it() {
    let rt = runtime("hub-dm").await;
    rt.trust_device("laptop-1", "Office laptop").await.unwrap();
    rt.set_device_mode("laptop-1", DeviceMode::Personal, "hub_user:admin")
        .await
        .unwrap();

    // The laptop is stolen: the admin revokes its trust.
    rt.untrust_device("laptop-1").await.unwrap();

    assert_eq!(
        rt.device_mode("laptop-1").await.unwrap(),
        DeviceMode::Shared,
        "whoever has the laptop must not keep the lax mode the trust granted"
    );

    // And it does not come back on its own: trusting it again starts strict.
    rt.trust_device("laptop-1", "Office laptop").await.unwrap();
    assert_eq!(
        rt.device_mode("laptop-1").await.unwrap(),
        DeviceMode::Shared,
        "a mode is a decision, and a decision that was revoked is taken again or not at all"
    );
}

#[tokio::test]
async fn an_online_login_never_resets_the_mode_an_administrator_chose() {
    let rt = runtime("hub-dm").await;
    rt.trust_device("laptop-1", "Office laptop").await.unwrap();
    rt.set_device_mode("laptop-1", DeviceMode::Personal, "hub_user:admin")
        .await
        .unwrap();

    // Every successful cloud login re-marks the device as trusted (server `auth_cloud`). If that
    // wrote the mode back to its default, the administrator's decision would evaporate at the very
    // next sign-in and nobody would understand why the pinpad came back.
    rt.trust_device("laptop-1", "Marta Ruiz").await.unwrap();

    assert_eq!(rt.device_mode("laptop-1").await.unwrap(), DeviceMode::Personal);
}

#[tokio::test]
async fn the_mode_survives_a_restart_of_the_runtime() {
    let test_db = erplora_db::testutil::TestDb::new().await;
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-dm");
    rt.ensure_system_tables().await.unwrap();
    rt.trust_device("laptop-1", "Office laptop").await.unwrap();
    rt.set_device_mode("laptop-1", DeviceMode::Personal, "hub_user:admin")
        .await
        .unwrap();
    drop(rt);

    // Same database, new runtime: the mode is state of the hub, not of the process.
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), "hub-dm");
    assert_eq!(rt.device_mode("laptop-1").await.unwrap(), DeviceMode::Personal);
}

#[test]
fn a_mode_the_hub_does_not_know_is_refused_and_never_resolves_to_personal() {
    // A spelling outside the pair is a MALFORMED request (422), not a business conflict: the UI
    // picks from two options, so only a caller that is not the UI can produce one.
    for candidate in ["", "  ", "Personal", "root", "personal ", "shared;"] {
        let refused = DeviceMode::parse(candidate).expect_err(candidate);
        assert_eq!(payload_name_of(&refused), "hub.device.mode", "{candidate}");
    }

    // The two the hub does know, spelled exactly as they travel on the wire.
    assert_eq!(DeviceMode::parse("shared").unwrap(), DeviceMode::Shared);
    assert_eq!(DeviceMode::parse("personal").unwrap(), DeviceMode::Personal);
    assert_eq!(DeviceMode::Shared.as_str(), "shared");
    assert_eq!(DeviceMode::Personal.as_str(), "personal");
}

#[tokio::test]
async fn a_stored_mode_the_hub_cannot_read_is_taken_as_shared() {
    let rt = runtime("hub-dm").await;
    rt.trust_device("laptop-1", "Office laptop").await.unwrap();
    // Somebody (a hand-run UPDATE, a future migration, a restored backup) leaves a value the
    // catalogue does not contain. Reading has to fail CLOSED: guessing high would be guessing in
    // the direction that removes the pinpad.
    rt.db()
        .execute_batch("UPDATE hub_trusted_device SET mode = 'trusted-forever';")
        .await
        .unwrap();

    assert_eq!(rt.device_mode("laptop-1").await.unwrap(), DeviceMode::Shared);
}
