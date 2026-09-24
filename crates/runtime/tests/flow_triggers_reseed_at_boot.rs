//! **An automation that lost a trigger gets it back when the hub restarts** — hub#2061.
//!
//! The unit tests in `flows/store.rs` fix what the repair does. This one fixes the part that makes
//! it reach the hubs already in production: that it runs on the boot path, because nobody re-saves
//! an automation that «is on».
use erplora_db::testutil::TestDb;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::flows::store::{self, NewFlow};
use erplora_runtime::registry::Registry;
use erplora_runtime::Runtime;
use serde_json::json;

const HUB: &str = "hub-reseed";
const EVENT: &str = "hub.whatsapp.message_received";

async fn live_trigger_count(db: &dyn DatabaseAdapter, flow_id: &str) -> usize {
    let mut p = Params::new();
    p.insert("f".into(), json!(flow_id));
    db.query(
        "SELECT id FROM _flow_triggers WHERE flow_id = :f AND deleted_at IS NULL",
        &p,
    )
    .await
    .unwrap()
    .rows
    .len()
}

#[tokio::test]
async fn restarting_the_hub_gives_back_a_trigger_lost_before_the_fix() {
    let db = TestDb::new().await;
    let rt = Runtime::with_hub_id(Box::new(db.adapter().await), HUB);
    rt.ensure_system_tables().await.unwrap();

    let adapter = db.adapter().await;
    let flow = store::create(
        &adapter,
        HUB,
        &Registry::new(),
        &NewFlow {
            name: "WhatsApp".into(),
            enabled: true,
            definition: json!({
                "schema_version": 1,
                "triggers": [
                    { "kind": "event", "event": EVENT, "filter": { "event.text": { "neq": "" } } },
                    { "kind": "event", "event": EVENT, "filter": { "event.reply_id": { "neq": "" } } }
                ],
                "steps": [{ "id": "wait", "kind": "delay", "seconds": 5 }]
            }),
        },
        "hub_user:1",
    )
    .await
    .unwrap();
    assert_eq!(live_trigger_count(&adapter, &flow.id).await, 2);

    // What the seeding before the fix left: the twin collapsed into the bare `kind:event` row.
    let mut p = Params::new();
    p.insert("f".into(), json!(flow.id));
    adapter
        .execute(
            "DELETE FROM _flow_triggers WHERE flow_id = :f AND trigger_key LIKE '%#%'",
            &p,
        )
        .await
        .unwrap();
    assert_eq!(live_trigger_count(&adapter, &flow.id).await, 1);

    let restarted = Runtime::with_hub_id(Box::new(db.adapter().await), HUB);
    restarted.ensure_system_tables().await.unwrap();

    assert_eq!(
        live_trigger_count(&adapter, &flow.id).await,
        2,
        "the boot repair re-seeds the trigger the flow lost"
    );
}
