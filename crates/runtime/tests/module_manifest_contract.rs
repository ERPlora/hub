//! hub#521 — the hub stops ignoring IN SILENCE what it does not understand of a `module.json`.
//!
//! `Manifest` deserialises without `deny_unknown_fields` and with `#[serde(default)]` on ~20
//! fields, so anything the core did not know about was dropped without a log, a warning or an
//! error. It is not a hypothetical: `cash_register` ships a top-level `protects` block that
//! nothing reads, and seven commands of `inventory`/`services` declare a `validates` guard the
//! runtime never runs (hub#610) — a manifest that *looks* like it validates and does not.
//!
//! The contract this file pins, in three tiers:
//!
//! 1. **Refused.** An unknown key where the misunderstanding changes what RUNS or who may run it
//!    (`commands`, `queries`, `migrations`, `seed`, `events`, `capabilities`, `roles[]`,
//!    `scheduled_tasks[]`). Installing it would mean executing a command without a guard its
//!    author declared. Better no module than a module that lies about its own gates.
//! 2. **Installed with a visible warning.** An unknown key anywhere else (top level,
//!    `navigation[]`, `widgets`, `settings`, `setup`, `agent`, `static_files`): the cost is a
//!    screen, a button or a checklist item, and bricking a till over a tab that does not render
//!    is the wrong trade for a POS. The warning is recorded on the module and travels in
//!    `/api/modules`, so it is consultable and not just a line in a log nobody reads.
//! 3. **Declared incompatibility.** `compatibility.min_erplora_version` is finally READ: a module
//!    that needs a newer core is refused with a message that names both versions, instead of
//!    installing and silently missing whatever the new core would have given it.
//!
//! The reverse direction — a NEW hub with an OLD module — must keep working untouched. That
//! tolerance is the reason the fleet survives an upgrade, and nothing here narrows it.

use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;

fn fixture(manifest: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "erplora-manifest-contract-{}",
        uuid::Uuid::new_v4()
    ));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("module.json"), manifest).unwrap();
    dir
}

#[tokio::test]
async fn install_refuses_an_unknown_field_inside_a_command() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-manifest-contract");
    runtime.ensure_system_tables().await.unwrap();
    // `requires_approval` reads exactly like a gate. Dropping it silently would run the command
    // with no approval at all, while its author believes the manifest covers it.
    let dir = fixture(
        r#"{
          "id":"inventory",
          "name":"Inventory",
          "version":"1.0.0",
          "commands":{
            "inventory.stock.write_off": {
              "permission":"inventory.edit_stock",
              "sql":[],
              "requires_approval":"manager"
            }
          }
        }"#,
    );

    let error = runtime
        .install_from_dir(&dir)
        .await
        .expect_err("a command carrying a gate this core cannot run must not install")
        .to_string();

    assert!(
        error.contains("commands.inventory.stock.write_off.requires_approval"),
        "the refusal must name the exact path it refused: {error}"
    );
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test]
async fn install_refuses_an_unknown_field_inside_the_events_block() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-manifest-contract");
    runtime.ensure_system_tables().await.unwrap();
    // A subscription this core does not understand is a reaction that never happens: the module
    // installs, the event fires, and nothing runs — the exact silence hub#521 is about.
    let dir = fixture(
        r#"{
          "id":"analytics",
          "name":"Analytics",
          "version":"1.0.0",
          "events":{ "subscribe":{ "sale.completed":{"command":"analytics.count"} } }
        }"#,
    );

    let error = runtime
        .install_from_dir(&dir)
        .await
        .expect_err("an events block this core cannot read must not install")
        .to_string();

    assert!(
        error.contains("events.subscribe"),
        "the refusal must name the exact path it refused: {error}"
    );
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test]
async fn install_accepts_an_unknown_optional_block_and_records_a_visible_warning() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-manifest-contract");
    runtime.ensure_system_tables().await.unwrap();
    // An unknown top-level block the shell MIGHT one day read (here, a hypothetical `experiments`
    // toggle). It costs a screen, not correctness, so the module installs — but never in silence.
    //
    // (hub#775 retired `protects` from this role: it is now parsed and acted on by the dispatcher,
    // so it no longer reaches this warning tier. A genuinely unknown root field still does.)
    let dir = fixture(
        r#"{
          "id":"cash_register",
          "name":"Cash register",
          "version":"1.0.0",
          "experiments":[{"flag":"beta_drawer"}]
        }"#,
    );

    let id = runtime
        .install_from_dir(&dir)
        .await
        .expect("an optional block this core does not know must not brick the till");
    assert_eq!(id, "cash_register");

    let module = runtime
        .modules()
        .into_iter()
        .find(|m| m.id == "cash_register")
        .expect("the module is installed");
    assert!(
        module
            .manifest_warnings
            .iter()
            .any(|w| w.path == "experiments"),
        "the warning must be consultable on the module, naming the block: {:?}",
        module.manifest_warnings
    );
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test]
async fn install_parses_a_protects_block_without_warning() {
    // hub#775: `protects` was the canonical "unknown optional block" of this file until the issue
    // taught the runtime to PARSE it and act on it authoritatively. Now it must install CLEAN — no
    // warning, no refusal — and the guard must be reachable on the installed manifest.
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-manifest-contract");
    runtime.ensure_system_tables().await.unwrap();
    let dir = fixture(
        r#"{
          "id":"cash_register",
          "name":"Cash register",
          "version":"1.0.0",
          "permissions":["cash_register.view_session"],
          "queries":{
            "cash_register.settings.get":{"permission":"cash_register.view_session","sql":"queries/s.sql"},
            "cash_register.current_session":{"permission":"cash_register.view_session","sql":"queries/cs.sql"}
          },
          "protects":[{
            "settings_query":"cash_register.settings.get",
            "enabled_setting":"enable_cash_register",
            "route_setting":"protected_pos_url",
            "guard_query":"cash_register.current_session",
            "expect":"non_empty",
            "component":"erp-cashregister-open",
            "resume_on":"cash_register.session_opened"
          }]
        }"#,
    );
    std::fs::create_dir_all(dir.join("queries")).unwrap();
    std::fs::write(dir.join("queries/s.sql"), "SELECT 1").unwrap();
    std::fs::write(dir.join("queries/cs.sql"), "SELECT 1").unwrap();

    runtime
        .install_from_dir(&dir)
        .await
        .expect("a well-formed protects block must install clean");

    let module = runtime
        .modules()
        .into_iter()
        .find(|m| m.id == "cash_register")
        .expect("the module is installed");
    assert!(
        !module
            .manifest_warnings
            .iter()
            .any(|w| w.path.starts_with("protects")),
        "`protects` is now parsed and acted on — it must NOT warn: {:?}",
        module.manifest_warnings
    );
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test]
async fn install_warns_about_an_unknown_field_in_a_navigation_entry() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-manifest-contract");
    runtime.ensure_system_tables().await.unwrap();
    // The example used to be `permission`, because `invoice` shipped exactly that and the core
    // dropped it — the tab rendered for everyone and nobody was told. hub#1052 made `permission`
    // a REAL field, so it is no longer unknown; the contract this test guards is not about that
    // one field but about the PATH of the warning, so the example moves to another unknown key.
    // Keeping `permission` here would have quietly turned this into a test of nothing.
    let dir = fixture(
        r#"{
          "id":"invoice",
          "name":"Invoice",
          "version":"1.0.0",
          "navigation":[
            {"id":"invoice","label":"Invoices","component":"erp-invoice-list"},
            {"id":"settings","label":"Settings","component":"erp-invoice-settings",
             "badge":"new"}
          ]
        }"#,
    );

    runtime
        .install_from_dir(&dir)
        .await
        .expect("a tab the core cannot fully read still installs");

    let module = runtime
        .modules()
        .into_iter()
        .find(|m| m.id == "invoice")
        .unwrap();
    assert!(
        module
            .manifest_warnings
            .iter()
            .any(|w| w.path == "navigation[1].badge"),
        "the warning must point at the entry, not just at `navigation`: {:?}",
        module.manifest_warnings
    );
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test]
async fn install_refuses_a_module_that_needs_a_newer_core() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-manifest-contract");
    runtime.ensure_system_tables().await.unwrap();
    // `compatibility.min_erplora_version` is the field the SaaS already reads from the manifest and
    // republishes to the catalogue as `min_core_version`. Until now the hub never looked at it.
    let dir = fixture(
        r#"{
          "id":"future",
          "name":"Future",
          "version":"2.0.0",
          "compatibility":{"min_erplora_version":"999.0.0"}
        }"#,
    );

    let error = runtime
        .install_from_dir(&dir)
        .await
        .expect_err("a module that needs a newer core must be refused, not half-installed")
        .to_string();

    assert!(
        error.contains("999.0.0") && error.contains(erplora_runtime::CORE_VERSION),
        "the refusal must name the version it needs AND the one this hub runs: {error}"
    );
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test]
async fn install_accepts_an_old_module_on_a_new_hub() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-manifest-contract");
    runtime.ensure_system_tables().await.unwrap();
    // The direction that must NEVER narrow: a module built for an older core keeps installing.
    // It is what lets a hub upgrade without every module having to move on the same day.
    let dir = fixture(
        r#"{
          "id":"legacy",
          "name":"Legacy",
          "version":"0.1.0",
          "compatibility":{"min_erplora_version":"0.1.0"}
        }"#,
    );

    let id = runtime
        .install_from_dir(&dir)
        .await
        .expect("an old module on a new hub is the normal case, not an error");
    assert_eq!(id, "legacy");

    let module = runtime
        .modules()
        .into_iter()
        .find(|m| m.id == "legacy")
        .unwrap();
    assert!(
        module.manifest_warnings.is_empty(),
        "declaring a core floor this hub clears is not worth a warning: {:?}",
        module.manifest_warnings
    );
    std::fs::remove_dir_all(dir).unwrap();
}

#[tokio::test]
async fn a_published_manifest_without_a_compatibility_block_installs_clean() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-manifest-contract");
    runtime.ensure_system_tables().await.unwrap();
    // The shape of all 24 published manifests: no `compatibility` at all. Absence means "runs
    // anywhere", so it must install with a clean bill — otherwise this issue becomes a fleet-wide
    // republish, which is exactly the cost it was meant to avoid.
    let dir = fixture(
        r#"{
          "id":"catalog",
          "name":"Catalog",
          "version":"1.0.0",
          "permissions":["catalog.view_item"],
          "queries":{"catalog.items.list":{"permission":"catalog.view_item","sql":"queries/list.sql"}},
          "commands":{"catalog.items.create":{"permission":"catalog.view_item","sql":[]}},
          "navigation":[{"id":"catalog","label":"Catalog","component":"erp-catalog"}],
          "marketplace":{"functional_unit":"finance"},
          "ui":{"entry":"dist/catalog.js"}
        }"#,
    );
    std::fs::create_dir_all(dir.join("queries")).unwrap();
    std::fs::write(dir.join("queries/list.sql"), "SELECT 1").unwrap();

    let id = runtime
        .install_from_dir(&dir)
        .await
        .expect("a published manifest must keep installing");
    assert_eq!(id, "catalog");

    let module = runtime
        .modules()
        .into_iter()
        .find(|m| m.id == "catalog")
        .unwrap();
    assert!(
        module.manifest_warnings.is_empty(),
        "blocks the schema knows but the runtime deliberately leaves to the shell or the SaaS \
         (`ui`, `marketplace`) are not unknown and must not warn: {:?}",
        module.manifest_warnings
    );
    std::fs::remove_dir_all(dir).unwrap();
}

/// 🔴 The guard on the whole feature: **no module the fleet already runs may be refused by it.**
///
/// A refusal at `Manifest::load` is not only "this install fails" — the boot scan re-registers
/// every installed module through the same door, so a rule that refuses one of the 24 published
/// manifests would make it VANISH from a hub that has been running it for months, with no way to
/// update the module out of trouble (ADR-0269). That is a worse silence than the one being fixed.
///
/// This is why `validates` is retired rather than refused: it lives inside `commands`, where an
/// unknown field is refused, and two published modules carry it. The exception is enumerated in
/// `manifest::RETIRED_FIELDS`, and this test is what would catch the next one.
#[test]
fn no_published_manifest_is_refused_by_the_contract() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let root = erplora_runtime::modules_root();
    let mut loaded = 0;
    for entry in std::fs::read_dir(&root)
        .expect("modules root is readable")
        .flatten()
    {
        let dir = entry.path();
        if !dir.join("module.json").is_file() {
            continue;
        }
        let module = dir
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();
        let manifest = erplora_runtime::Manifest::load(&dir)
            .unwrap_or_else(|e| panic!("`{module}` is PUBLISHED and must keep loading: {e}"));
        for warning in &manifest.warnings {
            println!("⚠  {module}: `{}` — {}", warning.path, warning.detail);
        }
        loaded += 1;
    }
    assert!(
        loaded >= 20,
        "expected the published catalogue (~24 modules), only {loaded} loaded from {}",
        root.display()
    );
}

/// hub#709 — the other half of that guard: the published catalogue does not only LOAD, it also
/// **declares what it emits**.
///
/// Before this, 23 of the 24 manifests had `events.emits` empty or absent, and `sale.completed` —
/// emitted on every sale, listened to by `inventory`, `customers`, `cash_register`, `invoice` and
/// `tables` — appeared in no manifest at all. The hub's event catalogue is the aggregation of what
/// each installed module declares, so the list a flow can react to came out with the eleven events
/// of `whatsapp_inbox` and nothing else.
///
/// The rule is a WARNING and not a refusal (see `Manifest::undeclared_emit_warnings`), so nothing
/// here can stop a till. What this test buys is that the catalogue stays true: put back a command
/// that emits without declaring, and this goes red naming the module and the event.
#[test]
fn no_published_manifest_hides_an_event_it_emits() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let root = erplora_runtime::modules_root();
    let mut holes: Vec<String> = Vec::new();
    let mut loaded = 0;
    for entry in std::fs::read_dir(&root)
        .expect("modules root is readable")
        .flatten()
    {
        let dir = entry.path();
        if !dir.join("module.json").is_file() {
            continue;
        }
        let module = dir
            .file_name()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string();
        let manifest = erplora_runtime::Manifest::load(&dir)
            .unwrap_or_else(|e| panic!("`{module}` is PUBLISHED and must keep loading: {e}"));
        for warning in &manifest.warnings {
            if warning.path == "events.emits" {
                holes.push(format!("  {module}: {}", warning.detail));
            }
        }
        loaded += 1;
    }
    assert!(
        loaded >= 20,
        "expected the published catalogue (~24 modules), only {loaded} loaded from {}",
        root.display()
    );
    assert!(
        holes.is_empty(),
        "these published modules emit events they do not declare, so the hub's event catalogue \
         cannot offer them:\n{}",
        holes.join("\n")
    );
}

#[tokio::test]
async fn the_retired_validates_block_installs_but_says_out_loud_that_it_does_nothing() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-manifest-contract");
    runtime.ensure_system_tables().await.unwrap();
    // hub#610. Seven commands of two PUBLISHED modules declare `validates`, and the runtime has
    // never implemented it. Refusing it as an unknown command field would be consistent — and
    // would stop `inventory` and `services` from installing on hubs that already run them, with
    // no module-update path to fix it (ADR-0269). So the name is RETIRED instead: enumerated,
    // reported by name, and pointing at the issue that decides its fate. That is a debt with a
    // number, not a permanent tolerance — and, unlike today, it is not a lie.
    let dir = fixture(
        r#"{
          "id":"services",
          "name":"Services",
          "version":"1.0.0",
          "commands":{
            "services.services.create":{
              "permission":"services.edit_service",
              "sql":[],
              "validates":[{"field":"tax_category_key","query":"taxes.categories.get"}]
            }
          }
        }"#,
    );

    let id = runtime
        .install_from_dir(&dir)
        .await
        .expect("a retired name must not brick a module the fleet already runs");
    assert_eq!(id, "services");

    let module = runtime
        .modules()
        .into_iter()
        .find(|m| m.id == "services")
        .unwrap();
    let warning = module
        .manifest_warnings
        .iter()
        .find(|w| w.path == "commands.services.services.create.validates")
        .unwrap_or_else(|| {
            panic!(
                "the retired guard must be reported: {:?}",
                module.manifest_warnings
            )
        });
    assert!(
        warning.detail.contains("610"),
        "the warning must point at the issue that decides the name: {}",
        warning.detail
    );
    std::fs::remove_dir_all(dir).unwrap();
}
