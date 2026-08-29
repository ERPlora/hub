//! KCS · events — `emits`, the outbox and the listener that runs the module's own command.
//!
//! Regression test for ERPlora/hub#1238. Kernel contract («El Hub se CIERRA como KERNEL») §5.
//!
//! Events are how two modules compose without importing each other, so the kernel owns the whole
//! path: a command's `emit` is written to `_event_outbox` INSIDE its transaction, the relay
//! delivers it to the listeners declared by installed modules, and the catalogue of what a module
//! may emit is `events.emits` — a name outside it is a broken contract, refused NAMING the event,
//! because an event name is a cross-module promise and not a field of the payload.
#[path = "support/kernel_fixture.rs"]
mod kernel_fixture;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{Runtime, RuntimeError};
use kernel_fixture::{admin, broken_copy, install_fixture, MODULE_ID};
use serde_json::json;

/// How many times the listener ran, read straight from the table only it writes.
async fn listener_runs(rt: &Runtime) -> i64 {
    rt.db_for_test()
        .query(
            "SELECT runs FROM kfx_log WHERE event = 'kfx.item.created'",
            &Params::new(),
        )
        .await
        .expect("read the listener log")
        .rows
        .first()
        .and_then(|r| r["runs"].as_i64())
        .unwrap_or(0)
}

/// Names of the events sitting in the outbox, in insertion order.
async fn outbox(rt: &Runtime) -> Vec<String> {
    rt.db_for_test()
        .query(
            "SELECT event_name FROM _event_outbox ORDER BY created_at, event_name",
            &Params::new(),
        )
        .await
        .expect("read the outbox")
        .rows
        .into_iter()
        .map(|r| r["event_name"].as_str().unwrap_or_default().to_string())
        .collect()
}

async fn create(rt: &Runtime, name: &str) {
    let mut p = Params::new();
    p.insert("name".into(), json!(name));
    rt.execute_command("kfx.item.create", &p, &admin())
        .await
        .expect("create");
}

/// A declarative `emit` reaches the outbox, and the relay hands it to the module's own listener.
#[tokio::test]
async fn a_declared_emit_travels_through_the_outbox_to_its_listener_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    create(&rt, "a").await;
    assert!(
        outbox(&rt).await.contains(&"kfx.item.created".to_string()),
        "the event is in the outbox before anything delivers it"
    );
    assert_eq!(
        listener_runs(&rt).await,
        0,
        "and it has not been delivered yet"
    );

    rt.drain_outbox().await.expect("drain");
    assert_eq!(
        listener_runs(&rt).await,
        1,
        "the relay ran the declared listener"
    );
}

/// An event a HANDLER returns takes the same path — `Output.events` is not a second mechanism.
#[tokio::test]
async fn a_handler_event_takes_the_same_path_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let mut p = Params::new();
    p.insert("names".into(), json!(["a", "b"]));
    rt.execute_command("kfx.items.bulk", &p, &admin())
        .await
        .expect("bulk");
    assert!(
        outbox(&rt).await.contains(&"kfx.items.bulked".to_string()),
        "the event the guest returned is in the outbox"
    );
}

/// The event is written in the command's OWN transaction: a command that fails emits nothing.
#[tokio::test]
async fn a_failed_command_emits_nothing_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let mut p = Params::new();
    p.insert("names".into(), json!(["a"]));
    p.insert("escape_to".into(), json!("kfx.nowhere"));
    rt.execute_command("kfx.items.bulk", &p, &admin())
        .await
        .expect_err("the operations name nothing");
    assert!(
        outbox(&rt).await.is_empty(),
        "an event that outlived its transaction would be a lie told to every other module"
    );
}

/// 🔴 Proof the guard catches the positive: with `events.emits` declared the module is in STRICT
/// mode, so a handler returning a name outside the catalogue is refused NAMING the event, and the
/// command fails whole rather than half-writing.
///
/// It runs against a copy of the fixture whose bulk command declares a **native** handler instead
/// of the WASM one: `Output.events` shares the exact code path
/// (`commands::persist_handler_output`), and this lets the test choose the event name without
/// recompiling a guest for every case.
#[tokio::test]
async fn an_undeclared_handler_event_is_refused_naming_it_hub1238() {
    use std::sync::Arc;

    use async_trait::async_trait;
    use erplora_runtime::native::{NativeHandler, NativeHost};
    use erplora_wasm_host::{Event, Output};

    /// Returns whatever event name the payload asks for — the test drives the name.
    #[derive(Debug)]
    struct EmittingHandler;

    #[async_trait]
    impl NativeHandler for EmittingHandler {
        async fn call(
            &self,
            _function: &str,
            input: &serde_json::Value,
            _host: &dyn NativeHost,
        ) -> Result<Output, RuntimeError> {
            let name = input["payload"]["event"]
                .as_str()
                .expect("the test names the event");
            Ok(Output::new().with_event(Event::new(name, json!({}))))
        }
    }

    let broken = broken_copy("emits-strict", |manifest| {
        manifest["commands"] = json!({
            "kfx.items.bulk": {
                "permission": "kfx.bulk",
                "transaction": true,
                "handler": { "type": "native", "function": "emit" },
                "emit": ["kfx.items.bulked"]
            }
        });
        manifest["queries"] = json!({});
        manifest["events"] = json!({ "emits": ["kfx.items.bulked"] });
    });

    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(broken.path())
        .await
        .expect("install the native variant");
    rt.register_native(MODULE_ID, Arc::new(EmittingHandler));

    let mut ok = Params::new();
    ok.insert("event".into(), json!("kfx.items.bulked"));
    rt.execute_command("kfx.items.bulk", &ok, &admin())
        .await
        .expect("a declared name goes through");

    let mut forbidden = Params::new();
    forbidden.insert("event".into(), json!("kfx.item.smuggled"));
    match rt
        .execute_command("kfx.items.bulk", &forbidden, &admin())
        .await
        .expect_err("the name is outside `events.emits`")
    {
        RuntimeError::EventNotDeclared { module, event } => {
            assert_eq!(module, MODULE_ID);
            assert_eq!(event, "kfx.item.smuggled");
        }
        other => panic!("expected EventNotDeclared, got {other:?}"),
    }
}

/// The catalogue the flow editor reads is exactly what the manifest declares — the event name is
/// the key, and it points back at the module that promised it.
#[tokio::test]
async fn the_declared_event_catalogue_is_what_the_manifest_says_hub1238() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    install_fixture(&mut rt).await;

    let declared = rt.registry().declared_events();
    let ours: Vec<&String> = declared.keys().filter(|k| k.starts_with("kfx.")).collect();
    assert_eq!(
        ours,
        vec!["kfx.item.created", "kfx.items.bulked"],
        "what the module can emit is the manifest's list, sorted and stable"
    );
    assert_eq!(
        declared.get("kfx.items.bulked").map(Vec::as_slice),
        Some([MODULE_ID.to_string()].as_slice()),
        "and it names the module that promised it"
    );
}
