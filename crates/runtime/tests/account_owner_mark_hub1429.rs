//! **Which row is the account owner's** (hub#1429).
//!
//! The hub has to be able to name that row, because it is the only party that can police it: the
//! runtime talks to the SaaS with the **machine credential**, which `assert_can_manage_hub_member`
//! treats as owner rank, so the SaaS cannot tell whether the person who clicked was the owner, the
//! administrator or the cashier (saas#1638/#1788). Either the hub knows, or nobody does.
//!
//! The mark is **derived**, never typed: it is asserted at boot from `HUB_OWNER_EMAIL` — the same
//! provisioning env `seed_owner` already trusts to decide who the creator is (ADR-0157) — and no
//! HTTP door writes it. The local `owner` ROLE is not resurrected: hub#349 retired it on purpose
//! and administering the hub stays `admin`. Ownership is a fact of the ACCOUNT plane; the mark is
//! only its shadow on the row.
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;

async fn runtime(hub_id: &str) -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

async fn owners(rt: &Runtime) -> Vec<String> {
    rt.list_hub_users()
        .await
        .unwrap()
        .into_iter()
        .filter(|u| u.is_account_owner)
        .map(|u| u.name)
        .collect()
}

/// The row `seed_owner` creates from the provisioning env carries the mark, and nobody else does.
#[tokio::test]
async fn the_seeded_creator_is_the_account_owner() {
    let rt = runtime("hub-owner-mark").await;
    let cashier = rt
        .create_user("Marta Ruiz", "1234", "cashier", None)
        .await
        .unwrap();

    assert!(rt.seed_owner("ioan@example.com").await.unwrap());

    let users = rt.list_hub_users().await.unwrap();
    let owner = users
        .iter()
        .find(|u| u.email == "ioan@example.com")
        .expect("the seeded creator is in Personal");
    assert!(
        owner.is_account_owner,
        "the row seeded from HUB_OWNER_EMAIL is the account owner's"
    );
    let marta = users.iter().find(|u| u.id == cashier).unwrap();
    assert!(
        !marta.is_account_owner,
        "everybody else is not: the mark names ONE row"
    );
}

/// The mark has to reach a hub that already existed — the owner's row is normally already there
/// (they logged in before this shipped), and `seed_owner` returns `false` for it. Marking only on
/// the create path would leave every hub in production without an owner: the guard would then
/// protect nothing, silently, which is the worst outcome of the three.
#[tokio::test]
async fn an_already_seeded_owner_is_marked_too() {
    let rt = runtime("hub-owner-mark-existing").await;
    // First boot: the row exists and carries the mark.
    assert!(rt.seed_owner("ioan@example.com").await.unwrap());
    // Second boot: idempotent — it seeds nothing…
    assert!(!rt.seed_owner("ioan@example.com").await.unwrap());
    // …and the mark is still exactly on that one row.
    assert_eq!(owners(&rt).await, vec!["ioan".to_string()]);
}

/// Ownership moves in the ACCOUNT plane (the SaaS transfers it and redeploys the hub with the new
/// `HUB_OWNER_EMAIL`); the mark follows it and never accumulates. Two protected rows would mean
/// the ex-owner keeps a row no administrator can touch — locked for good.
#[tokio::test]
async fn transferring_ownership_moves_the_mark_it_does_not_add_one() {
    let rt = runtime("hub-owner-mark-transfer").await;
    rt.seed_owner("ioan@example.com").await.unwrap();

    // The account is transferred: the deployment now carries another `HUB_OWNER_EMAIL`.
    assert!(rt.seed_owner("ana@example.com").await.unwrap());

    assert_eq!(owners(&rt).await, vec!["ana".to_string()]);
}

/// No env (a `pnpm dev` outside provisioning) marks nothing. There is no row to protect and none is
/// invented: a hub with no named owner keeps exactly today's rules.
#[tokio::test]
async fn without_the_provisioning_env_nothing_is_marked() {
    let rt = runtime("hub-owner-mark-none").await;
    rt.create_user("Marta Ruiz", "1234", "cashier", None)
        .await
        .unwrap();
    assert!(!rt.seed_owner("   ").await.unwrap());
    assert!(owners(&rt).await.is_empty());
}
