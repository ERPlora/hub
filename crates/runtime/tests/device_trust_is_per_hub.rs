//! **A device is trusted by a HUB, not by a database** (hub#489).
//!
//! `hub_trusted_device` was keyed on `device_id` alone while every other system table —
//! `hub_settings`, `hub_api_key`, `hub_module` — is keyed on `(hub_id, …)`. In the pre-ADR-0201
//! shape, where several hubs share one database, that made the table **common ground**:
//!
//!  - a device that earned its trust in hub A walked through hub B's PIN gate (§2.9) without ever
//!    having signed in online against B;
//!  - an administrator of A could mark `personal` — or **revoke** — a device of B;
//!  - since hub#455 there is a screen that *lists* devices, so A's administrator was also **shown**
//!    B's devices: their label, when they were last used and how long their sessions still had.
//!    That turned a silent isolation defect into tenant data on a screen.
//!
//! Every test here therefore keeps **the neighbour alive and populated while the action runs** and
//! asserts it came out unchanged. A test that stood the neighbour down first would pass with the
//! unscoped SQL too — which is exactly how this survived three reviews.
//!
//! What this file does **not** claim: `hub_session` and `hub_user` still carry no `hub_id`, so in a
//! shared database the *sessions* of a neighbour are still collateral to a revocation, and a token
//! minted by one hub still resolves in the other. That is a separate, larger defect (hub#497) and
//! is called out where it shows.
use erplora_db::testutil::TestDb;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::device_mode::DeviceMode;
use erplora_runtime::Runtime;

/// The stable rejection code of a refused write, or the raw message when it was something else.
fn code_of(error: &erplora_runtime::RuntimeError) -> String {
    match error {
        erplora_runtime::RuntimeError::Domain { code, .. } => code.clone(),
        other => other.to_string(),
    }
}

/// A hub running on `test_db`, booted the way the server boots it.
async fn hub_on(test_db: &TestDb, hub_id: &str) -> Runtime {
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

/// Two hubs **sharing one database** — the pre-ADR-0201 shape this issue is about. Since ADR-0201
/// each hub owns its own database, so this is the legacy shape and the defence in depth: the row
/// contract of this schema is `(hub_id, …)` whatever the deployment does with databases.
async fn two_hubs_sharing_a_database() -> (TestDb, Runtime, Runtime) {
    let test_db = TestDb::new().await;
    let mine = hub_on(&test_db, "hub-mine").await;
    let neighbour = hub_on(&test_db, "hub-neighbour").await;
    (test_db, mine, neighbour)
}

/// A business with its counter till and a floor tablet, both trusted as an online login leaves
/// them, the tablet marked `personal` — the lax mode, the one worth stealing. Returns the admin.
async fn a_business_with_a_till_and_a_tablet(rt: &Runtime, admin_name: &str) -> String {
    let admin = rt
        .create_user(admin_name, "1111", "admin", None)
        .await
        .unwrap();
    rt.trust_device("till-1", "Counter till").await.unwrap();
    rt.trust_device("tablet-1", "Floor tablet").await.unwrap();
    rt.set_device_mode("tablet-1", DeviceMode::Personal, &admin)
        .await
        .unwrap();
    admin
}

/// The whole `hub_trusted_device` table as `(hub_id, device_id, label, mode)`, ordered — so a test
/// can assert both what went and what stayed, across every tenant in the database.
async fn every_row(db: &dyn DatabaseAdapter) -> Vec<(String, String, String, String)> {
    let res = db
        .query(
            "SELECT hub_id, device_id, label, mode FROM hub_trusted_device \
              ORDER BY hub_id, device_id",
            &Params::new(),
        )
        .await
        .unwrap();
    res.rows
        .iter()
        .map(|r| {
            (
                r["hub_id"].as_str().unwrap_or_default().to_string(),
                r["device_id"].as_str().unwrap_or_default().to_string(),
                r["label"].as_str().unwrap_or_default().to_string(),
                r["mode"].as_str().unwrap_or_default().to_string(),
            )
        })
        .collect()
}

/// The ids a hub lists, sorted.
async fn listed_ids(rt: &Runtime) -> Vec<String> {
    let mut ids: Vec<String> = rt
        .list_devices()
        .await
        .unwrap()
        .into_iter()
        .map(|d| d.device_id)
        .collect();
    ids.sort();
    ids
}

#[tokio::test]
async fn a_device_trusted_next_door_does_not_open_the_pin_gate_here() {
    let (_test_db, mine, neighbour) = two_hubs_sharing_a_database().await;
    a_business_with_a_till_and_a_tablet(&neighbour, "Ana").await;

    // The gate of §2.9: a PIN is only usable where the device already proved identity online. My
    // hub has never seen this tablet, so it must not accept it — the neighbour's login is not mine.
    assert!(
        !mine.is_device_trusted("tablet-1").await.unwrap(),
        "trust earned against another business is not trust against this one"
    );
    assert_eq!(
        mine.device_mode("tablet-1").await.unwrap(),
        DeviceMode::Shared,
        "and the lax mode the neighbour granted does not take my pinpad off either"
    );

    // The neighbour is untouched by having been asked about: it still trusts its own tablet.
    assert!(neighbour.is_device_trusted("tablet-1").await.unwrap());
    assert_eq!(
        neighbour.device_mode("tablet-1").await.unwrap(),
        DeviceMode::Personal
    );
}

#[tokio::test]
async fn the_same_tablet_can_be_trusted_by_two_businesses_at_once() {
    // The unicity decision, spelled out: the key is `(hub_id, device_id)` and not the id alone,
    // because one tablet legitimately works in two businesses — the same person's shop and their
    // partner's. Keying on the id alone would make the second trust overwrite the first, and the
    // label (the name of the last person to sign in online) would flip between tenants.
    let (test_db, mine, neighbour) = two_hubs_sharing_a_database().await;
    let db = test_db.adapter().await;

    mine.trust_device("tablet-1", "Ana Soto").await.unwrap();
    neighbour
        .trust_device("tablet-1", "Bruno Díaz")
        .await
        .unwrap();

    assert!(mine.is_device_trusted("tablet-1").await.unwrap());
    assert!(neighbour.is_device_trusted("tablet-1").await.unwrap());
    assert_eq!(
        every_row(&db).await,
        vec![
            (
                "hub-mine".to_string(),
                "tablet-1".to_string(),
                "Ana Soto".to_string(),
                "shared".to_string()
            ),
            (
                "hub-neighbour".to_string(),
                "tablet-1".to_string(),
                "Bruno Díaz".to_string(),
                "shared".to_string()
            ),
        ],
        "two rows, one per business: neither login overwrote the other's label"
    );
}

#[tokio::test]
async fn an_owner_only_sees_the_devices_of_their_own_business() {
    // The read hub#455 added and this issue widened: the list hands over label, last use and how
    // long each session still has. The neighbour is ALIVE and populated while the list is read.
    let (_test_db, mine, neighbour) = two_hubs_sharing_a_database().await;
    let their_admin = a_business_with_a_till_and_a_tablet(&neighbour, "Ana").await;
    neighbour
        .create_session(&their_admin, 3600, Some("tablet-1"))
        .await
        .unwrap();
    mine.trust_device("my-till", "My counter").await.unwrap();

    assert_eq!(
        listed_ids(&mine).await,
        vec!["my-till".to_string()],
        "the neighbour's devices are not mine to enumerate"
    );
    assert_eq!(
        listed_ids(&neighbour).await,
        vec!["tablet-1".to_string(), "till-1".to_string()],
        "and the neighbour still sees its own, unchanged"
    );
}

#[tokio::test]
async fn revoking_here_leaves_the_neighbours_device_of_the_same_id_trusted() {
    let (test_db, mine, neighbour) = two_hubs_sharing_a_database().await;
    let db = test_db.adapter().await;
    a_business_with_a_till_and_a_tablet(&neighbour, "Ana").await;
    mine.trust_device("tablet-1", "My own tablet")
        .await
        .unwrap();

    mine.revoke_device("tablet-1").await.unwrap();

    // Alive and with data DURING the revocation, asserted unchanged after it: its trust, its lax
    // mode and its label are all still there.
    assert!(
        neighbour.is_device_trusted("tablet-1").await.unwrap(),
        "one business cannot cut off another business's tablet"
    );
    assert_eq!(
        neighbour.device_mode("tablet-1").await.unwrap(),
        DeviceMode::Personal,
        "nor take the mode an administrator next door decided"
    );
    assert_eq!(
        every_row(&db).await,
        vec![
            (
                "hub-neighbour".to_string(),
                "tablet-1".to_string(),
                "Floor tablet".to_string(),
                "personal".to_string()
            ),
            (
                "hub-neighbour".to_string(),
                "till-1".to_string(),
                "Counter till".to_string(),
                "shared".to_string()
            ),
        ],
        "exactly my row went; both of the neighbour's stayed, labels and modes intact"
    );
}

#[tokio::test]
async fn marking_a_device_personal_here_does_not_take_the_pinpad_off_next_door() {
    let (_test_db, mine, neighbour) = two_hubs_sharing_a_database().await;
    a_business_with_a_till_and_a_tablet(&neighbour, "Ana").await;
    let my_admin = mine
        .create_user("Bruno", "2222", "admin", None)
        .await
        .unwrap();
    mine.trust_device("till-1", "My counter till")
        .await
        .unwrap();

    mine.set_device_mode("till-1", DeviceMode::Personal, &my_admin)
        .await
        .unwrap();

    assert_eq!(
        mine.device_mode("till-1").await.unwrap(),
        DeviceMode::Personal,
        "my decision applies to my till"
    );
    assert_eq!(
        neighbour.device_mode("till-1").await.unwrap(),
        DeviceMode::Shared,
        "the neighbour's till of the same id keeps asking who is standing at it"
    );
}

#[tokio::test]
async fn an_administrator_cannot_name_a_device_only_the_neighbour_knows() {
    let (test_db, mine, neighbour) = two_hubs_sharing_a_database().await;
    let db = test_db.adapter().await;
    a_business_with_a_till_and_a_tablet(&neighbour, "Ana").await;
    let my_admin = mine
        .create_user("Bruno", "2222", "admin", None)
        .await
        .unwrap();
    let before = every_row(&db).await;

    let refused = mine
        .set_device_mode("tablet-1", DeviceMode::Personal, &my_admin)
        .await
        .expect_err("that is not a device of mine");

    // The same answer as any other id this hub never met — deliberately not a distinguishable one:
    // a different message would tell a caller which ids exist in the database next door.
    assert_eq!(code_of(&refused), "hub.device.unknown_device");
    assert_eq!(
        every_row(&db).await,
        before,
        "a refused write changes nothing — least of all the neighbour's row it was aimed at"
    );
}

#[tokio::test]
async fn a_deployment_that_does_not_say_which_hub_it_is_trusts_no_device() {
    // `hub_id = ''` is the value the v23 migration reserves for "this row names no hub": every row
    // written before the column existed carries it, and those rows are deleted rather than handed
    // to whoever booted first. So the runtime must never *write* it either — otherwise a hub
    // started without `HUB_ID` would keep re-creating exactly the unattributable rows the migration
    // exists to remove, and a re-run of the migration would then delete live trust.
    let test_db = TestDb::new().await;
    let nameless = hub_on(&test_db, "").await;
    let db = test_db.adapter().await;

    nameless
        .trust_device("till-1", "Counter till")
        .await
        .unwrap();

    assert!(
        !nameless.is_device_trusted("till-1").await.unwrap(),
        "a deployment that cannot say which hub it is grants no device trust"
    );
    assert_eq!(
        every_row(&db).await,
        Vec::new(),
        "and writes no row that a later migration would have to guess about"
    );
    assert!(nameless.list_devices().await.unwrap().is_empty());
}

/// hub#1560 — reading **one** device's name is scoped like reading all of them.
///
/// The print host registry asks this on every registration, so an unscoped read would put the
/// neighbour's name for the same `device_id` on my Printers screen — the same shape of leak as the
/// device list, through a door an ordinary cashier's session can open.
#[tokio::test]
async fn the_name_of_a_device_is_the_name_my_own_hub_gave_it() {
    let (_db, mine, neighbour) = two_hubs_sharing_a_database().await;
    // The neighbour is alive and populated while the read runs: a test that named the device in
    // only one hub would pass with unscoped SQL too.
    mine.trust_device("till-1", "Marta").await.unwrap();
    neighbour.trust_device("till-1", "Luis").await.unwrap();
    mine.rename_device("till-1", "Barra").await.unwrap();
    neighbour.rename_device("till-1", "Cocina").await.unwrap();

    assert_eq!(mine.device_name("till-1").await.unwrap(), "Barra");
    assert_eq!(neighbour.device_name("till-1").await.unwrap(), "Cocina");
    assert_eq!(
        mine.device_name("unknown-1").await.unwrap(),
        "",
        "a device this hub never saw has no name, and that is not an error"
    );
}

/// hub#1560 — and naming a device only renames the print host of the hub that named it.
#[tokio::test]
async fn naming_a_device_does_not_rename_the_neighbours_print_host() {
    let (_db, mine, neighbour) = two_hubs_sharing_a_database().await;
    mine.trust_device("till-1", "Marta").await.unwrap();
    neighbour.trust_device("till-1", "Luis").await.unwrap();
    mine.register_print_host("till-1", "receipt", "Mostrador", "u1")
        .await
        .unwrap();
    neighbour
        .register_print_host("till-1", "receipt", "Cocina", "u2")
        .await
        .unwrap();

    mine.rename_device("till-1", "Barra").await.unwrap();

    assert_eq!(mine.print_hosts().await.unwrap()[0].label, "Barra");
    assert_eq!(
        neighbour.print_hosts().await.unwrap()[0].label,
        "Cocina",
        "the neighbour's printer card is not mine to rewrite"
    );
}
