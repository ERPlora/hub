//! hub#986 — the **automation kernel** travels in a backup: the DEFINITION as a declarative
//! document, its GRANTS as keys re-granted through their own door, and nothing else.
//!
//! `_flow` and `_flow_triggers` hold what the owner of the business wrote — «when a sale over 100 €
//! closes, leave a note on that customer» — and the export never looked at them. So restoring a
//! backup gave back a hub **without its automations**, with an import report that said everything
//! landed: the same shape of failure hub#473 had just fixed for `_module_capability_grants`, and
//! the case ADR-0345 §2bis left written down as ⚠️ rather than solved.
//!
//! What this file pins, following ADR-0345 tabla por tabla:
//!
//! - **The definition is of the BUSINESS** → it travels in a `backup`, and its triggers travel with
//!   it because they ARE part of the document (`store::seed_triggers` re-materialises them at the
//!   destination, on the destination's own clock).
//! - **The grants are the approval of THIS deployment** → keys, never rows, re-granted through
//!   `flows::grants::replace` and only when the bundle is this hub's own copy (`is_same_hub`),
//!   exactly like the capability grants of hub#473.
//! - **A flow whose authority did not come back arrives DISABLED**, with a stable code. An armed
//!   flow with no grants is a flow that dies at 3 AM in every run; paused with a reason is the
//!   honest state.
//! - **`_flow_secrets` never leaves**, and neither does the execution history
//!   (`_flow_runs`/`_flow_run_steps`/`_flow_approvals`).
//! - **The import uses the SAME door as `POST /flows`** (`store::create`), so a document this hub
//!   would refuse at the screen cannot get in through a zip.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::export::{export_hub, BundlePurpose, ExportSelection, FLOWS_SECTION};
use erplora_runtime::flows::grants::GrantKind;
use erplora_runtime::flows::NewFlow;
use erplora_runtime::import::{import_sections, ImportReport, ImportSelection, SectionStatus};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::{json, Value};

const CREATED_AT: &str = "2026-08-15T10:00:00Z";
const OWNER: &str = "hub_user:owner";

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_flows")
        .join(name)
}

/// A hub with the two fixture modules of the kernel's own e2e: `sales` emits `sale.completed`,
/// `crm` owns the command a flow reaches for.
async fn hub_with(hub_id: &str, modules: &[&str]) -> Runtime {
    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), hub_id);
    rt.ensure_system_tables().await.unwrap();
    for m in modules {
        rt.install_from_dir(&fixture(m)).await.unwrap();
    }
    rt
}

/// The cashier at the till: the permissions of their own module and **not** the flow's.
fn cashier(hub_id: &str) -> RequestContext {
    RequestContext::new(hub_id, "cashier-1", ["sales.add_sale".to_string()])
}

/// «When a sale over 100 € closes, leave a note on that customer» — the flow of hub#661's story,
/// and the one whose disappearance from a backup is what this issue is about.
fn welcome_definition() -> Value {
    json!({
        "schema_version": 1,
        "triggers": [{
            "kind": "event",
            "event": "sale.completed",
            "filter": { "event.total": { "gte": "100" } },
            "input": { "customer_id": "event.customer_id", "total": "event.total" }
        }],
        "steps": [{
            "id": "note",
            "kind": "command",
            "command": "crm.note.add",
            "params": {
                "customer_id": "input.customer_id",
                "text": "thanks for the {{input.total}} order"
            }
        }]
    })
}

async fn create_flow(rt: &Runtime, name: &str, definition: Value, enabled: bool) -> String {
    rt.create_flow(
        &NewFlow {
            name: name.into(),
            enabled,
            definition,
        },
        OWNER,
    )
    .await
    .expect("the owner writes the flow")
    .id
}

async fn grant(rt: &Runtime, flow_id: &str, pairs: &[(GrantKind, &str)]) {
    let wanted: Vec<(GrantKind, String)> = pairs.iter().map(|(k, v)| (*k, v.to_string())).collect();
    rt.replace_flow_grants(flow_id, &wanted, OWNER)
        .await
        .expect("the owner grants the flow what it may do");
}

async fn complete_sale(rt: &Runtime, hub_id: &str, total: &str) {
    let mut p = Params::new();
    p.insert("total".into(), json!(total));
    p.insert("customer_id".into(), json!("c-1"));
    rt.execute_command("sales.sale.complete", &p, &cashier(hub_id))
        .await
        .expect("the cashier closes the sale");
}

async fn count(rt: &Runtime, sql: &str) -> i64 {
    rt.db_for_test()
        .query(sql, &Params::new())
        .await
        .unwrap()
        .rows
        .first()
        .and_then(|r| {
            r["c"]
                .as_i64()
                .or_else(|| r["c"].as_f64().map(|f| f as i64))
        })
        .unwrap_or(-1)
}

/// The section row the import report carries for the flows, if any.
fn flows_row(report: &ImportReport) -> Option<&erplora_runtime::import::SectionResult> {
    report.sections.iter().find(|s| s.section == FLOWS_SECTION)
}

fn reason(status: &SectionStatus) -> String {
    match status {
        SectionStatus::Ignored(r)
        | SectionStatus::PartiallyApplied(r)
        | SectionStatus::Failed(r) => r.clone(),
        other => panic!("expected a status with a reason, got {other:?}"),
    }
}

/// Sets `HUB_SECRETS_KEY` once for this binary: the core is fail-closed (hub#114), so storing a
/// flow secret through the real writer needs a master key.
fn ensure_master_key() {
    use base64::Engine as _;
    use std::sync::Once;
    static ONCE: Once = Once::new();
    ONCE.call_once(|| {
        let key = base64::engine::general_purpose::STANDARD.encode([0x51u8; 32]);
        // SAFETY: `Once` runs before any test touches the variable and nothing else writes it.
        unsafe { std::env::set_var("HUB_SECRETS_KEY", key) };
    });
}

// ── The round trip the issue is about ────────────────────────────────────────────────────

/// 🟢 The trip that names the issue: a hub whose owner automated «note the big sales» is backed up,
/// redeployed and restored — and the automation **runs again**.
///
/// Proven by firing a REAL event, not by counting rows: the run has to be created by the relay from
/// a sale nobody scripted, and the step has to pass the grant gate. Before this, `export_hub` never
/// looked at `_flow`, so the restore came back with an empty flow list and the report said the
/// import was complete.
#[tokio::test]
async fn a_backup_restores_the_flows_and_they_run_again() {
    let origin = hub_with("h1", &["sales", "crm"]).await;
    let flow_id = create_flow(&origin, "Welcome", welcome_definition(), true).await;
    grant(&origin, &flow_id, &[(GrantKind::Command, "crm.note.add")]).await;

    let selection = ExportSelection {
        purpose: BundlePurpose::Backup,
        ..Default::default()
    };
    let bundle = export_hub(&origin, "h1", &selection, "bar-pepe", "es", CREATED_AT)
        .await
        .expect("export");

    assert_eq!(
        bundle.manifest.flows.len(),
        1,
        "the backup carries the flow the owner wrote"
    );
    let spec = &bundle.manifest.flows[0];
    assert_eq!(spec.name, "Welcome");
    assert!(spec.enabled, "it was armed, and it comes back armed");
    assert_eq!(
        spec.definition,
        welcome_definition(),
        "the DOCUMENT travels, whole: its triggers are part of it"
    );
    assert_eq!(
        spec.grants
            .iter()
            .map(|g| (g.kind.as_str(), g.value.as_str()))
            .collect::<Vec<_>>(),
        vec![("command", "crm.note.add")],
        "what the flow may do travels as KEYS, next to its document"
    );
    assert!(
        bundle
            .manifest
            .sections
            .contains(&FLOWS_SECTION.to_string()),
        "the inventory the user confirms before importing has to show the bundle brings flows"
    );
    assert!(
        !bundle.files.keys().any(|p| p.contains("flow")),
        "a flow is a declarative document in the manifest, never a `data/*.sql` with raw INSERTs \
         into `_flow_grants`"
    );

    // The new deployment: same hub id (it IS this hub coming back), same modules, no flows.
    let mut restored = hub_with("h1", &["sales", "crm"]).await;
    assert!(
        restored.list_flows().await.unwrap().is_empty(),
        "precondition: a fresh deployment has no automations"
    );

    let report = import_sections(
        &mut restored,
        &bundle.manifest,
        &bundle.files,
        &ImportSelection::default(),
        "h1",
    )
    .await
    .expect("the backup is accepted");

    let flows = restored.list_flows().await.unwrap();
    assert_eq!(flows.len(), 1, "the flow is back");
    assert!(
        flows[0].enabled,
        "and it is ARMED, or it is not back at all"
    );
    assert_eq!(
        restored
            .list_flow_grants(&flows[0].id)
            .await
            .unwrap()
            .iter()
            .map(|g| (g.kind.clone(), g.value.clone()))
            .collect::<Vec<_>>(),
        vec![("command".to_string(), "crm.note.add".to_string())],
        "its authority came back through the granting door"
    );
    assert!(
        matches!(
            flows_row(&report).map(|r| &r.status),
            Some(SectionStatus::Applied)
        ),
        "the report says what it did with the flows: {:?}",
        report.sections
    );

    // 🔴 The real proof: a sale nobody scripted sets the automation off, end to end.
    complete_sale(&restored, "h1", "120.50").await;
    restored.drain_outbox().await.unwrap();
    restored.process_flows().await.unwrap();
    assert_eq!(
        count(&restored, "SELECT COUNT(*) AS c FROM crm_note").await,
        1,
        "the restored flow reacted to a REAL event and wrote the note"
    );
}

/// 🔴 The **trigger comes back on the destination's clock**, not with the origin's countdown: a
/// nightly job restored at noon fires tonight, and it fires at all.
///
/// The triggers are not exported as rows on purpose — they are re-materialised by `seed_triggers`,
/// the same function `POST /flows` calls. Carrying `_flow_triggers` as data would have carried
/// `next_run`/`last_run` too: the schedule of ANOTHER installation, computed under a timezone the
/// destination may not have.
#[tokio::test]
async fn the_triggers_are_rematerialised_by_the_same_door_that_saves_a_flow() {
    let origin = hub_with("h1", &["sales", "crm"]).await;
    let nightly = json!({
        "schema_version": 1,
        "triggers": [{ "kind": "cron", "cron": "0 9 * * *" }],
        "steps": [{ "id": "wait", "kind": "delay", "seconds": 1 }]
    });
    create_flow(&origin, "Nightly", nightly.clone(), true).await;

    let bundle = export_hub(
        &origin,
        "h1",
        &ExportSelection::default(),
        "b",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");
    let mut restored = hub_with("h1", &["sales", "crm"]).await;
    import_sections(
        &mut restored,
        &bundle.manifest,
        &bundle.files,
        &ImportSelection::default(),
        "h1",
    )
    .await
    .expect("import");

    let rows = restored
        .db_for_test()
        .query(
            "SELECT kind, cron, enabled, next_run FROM _flow_triggers \
             WHERE hub_id = 'h1' AND deleted_at IS NULL",
            &Params::new(),
        )
        .await
        .unwrap()
        .rows;
    assert_eq!(
        rows.len(),
        1,
        "the cron trigger of the document was materialised"
    );
    assert_eq!(rows[0]["cron"], json!("0 9 * * *"));
    assert!(
        rows[0]["next_run"].as_str().is_some_and(|s| !s.is_empty()),
        "and it has a next run computed HERE — a trigger with no due date is invisible to the \
         claim query and silent forever (hub#730): {rows:?}"
    );
}

// ── What must NOT travel ─────────────────────────────────────────────────────────────────

/// 🔴 A **flow secret never leaves the hub**, in any form. It is a credential of the origin
/// (hub#662) sealed with the master key of its ENVIRONMENT: the envelope would travel and the key
/// would not, so at the destination it is useless bytes — and a useless copy of a credential in a
/// downloadable zip is still a copy of a credential.
///
/// Asserted over the WHOLE bundle — the serialised manifest and every file's bytes — and not over
/// the absence of a field, because the leak this guards against is the one nobody named.
#[tokio::test]
async fn a_flow_secret_never_leaves_the_hub_in_any_form() {
    ensure_master_key();
    let origin = hub_with("h1", &["sales", "crm"]).await;
    origin
        .put_flow_secret("SUPPLIER_TOKEN", "sk-live-do-not-leak", OWNER)
        .await
        .expect("the owner stores the credential of an `http` step");
    let flow_id = create_flow(&origin, "Reorder", welcome_definition(), true).await;
    grant(&origin, &flow_id, &[(GrantKind::Command, "crm.note.add")]).await;

    let selection = ExportSelection {
        purpose: BundlePurpose::Backup,
        ..Default::default()
    };
    let bundle = export_hub(&origin, "h1", &selection, "b", "es", CREATED_AT)
        .await
        .expect("export");

    let manifest = serde_json::to_string(&bundle.manifest).unwrap();
    let mut everything = manifest;
    for bytes in bundle.files.values() {
        everything.push_str(&String::from_utf8_lossy(bytes));
    }
    for forbidden in ["sk-live-do-not-leak", "SUPPLIER_TOKEN", "_flow_secrets"] {
        assert!(
            !everything.contains(forbidden),
            "`{forbidden}` is inside the bundle — a flow secret must not leave the hub, not even \
             as a name or as an unreadable envelope"
        );
    }
}

/// 🔴 The **execution history stays**: runs, their steps and the approvals a person decided are the
/// record of what happened in THIS installation, exactly like `_elevation_audit` (ADR-0345 §2bis).
/// Trasplanting them would give another deployment a history of things that never happened there.
#[tokio::test]
async fn the_execution_history_does_not_travel() {
    let origin = hub_with("h1", &["sales", "crm"]).await;
    let flow_id = create_flow(&origin, "Welcome", welcome_definition(), true).await;
    grant(&origin, &flow_id, &[(GrantKind::Command, "crm.note.add")]).await;
    complete_sale(&origin, "h1", "120.50").await;
    origin.drain_outbox().await.unwrap();
    origin.process_flows().await.unwrap();
    assert_eq!(
        origin
            .list_flow_runs(&flow_id, 10, None)
            .await
            .unwrap()
            .len(),
        1,
        "precondition: the origin has a run in its history"
    );

    let selection = ExportSelection {
        purpose: BundlePurpose::Backup,
        ..Default::default()
    };
    let bundle = export_hub(&origin, "h1", &selection, "b", "es", CREATED_AT)
        .await
        .expect("export");
    let mut restored = hub_with("h1", &["sales", "crm"]).await;
    import_sections(
        &mut restored,
        &bundle.manifest,
        &bundle.files,
        &ImportSelection::default(),
        "h1",
    )
    .await
    .expect("import");

    let new_flow = restored.list_flows().await.unwrap().remove(0);
    assert!(
        restored
            .list_flow_runs(&new_flow.id, 10, None)
            .await
            .unwrap()
            .is_empty(),
        "the restored hub starts its own history: a run of the origin is not something that \
         happened here"
    );
    assert_eq!(
        count(&restored, "SELECT COUNT(*) AS c FROM _flow_run_steps").await,
        0
    );
    assert_eq!(
        count(&restored, "SELECT COUNT(*) AS c FROM _flow_approvals").await,
        0
    );
}

/// 🔴 A **template** carries no flows at all — the producer gate, and the same one hub#473 put on
/// the capability grants. A published artefact is for ANOTHER business, and a flow document is the
/// origin's own: the URLs its `http` steps dial, the texts it sends, the reads it names.
///
/// Pre-made automations in a catalogue template are a product decision with its own review step;
/// they are not something a backup form quietly turns on for everybody who downloads a blueprint.
#[tokio::test]
async fn a_template_carries_no_flows() {
    let origin = hub_with("h1", &["sales", "crm"]).await;
    let flow_id = create_flow(&origin, "Welcome", welcome_definition(), true).await;
    grant(&origin, &flow_id, &[(GrantKind::Command, "crm.note.add")]).await;

    let selection = ExportSelection {
        purpose: BundlePurpose::Template,
        ..Default::default()
    };
    let bundle = export_hub(&origin, "h1", &selection, "restaurante", "es", CREATED_AT)
        .await
        .expect("export");

    assert!(
        bundle.manifest.flows.is_empty(),
        "a published template does not carry the automations of the hub that produced it"
    );
    assert!(!bundle
        .manifest
        .sections
        .contains(&FLOWS_SECTION.to_string()));
}

/// 🔴 Tenant isolation — the #1 risk of this engine, with a LIVE neighbour: the database is shared
/// (`tenancy.md`), and `_flow` has carried `hub_id` since hub#980. An export that forgot its
/// `WHERE hub_id` would put the automations of the business next door inside this backup.
#[tokio::test]
async fn the_export_carries_only_the_flows_of_its_own_hub() {
    let origin = hub_with("h1", &["sales", "crm"]).await;
    create_flow(&origin, "Mine", welcome_definition(), true).await;
    // The neighbour is created through the SAME door, so it is a real flow of a real hub sharing
    // this database — not a row somebody INSERTed to make the assertion pass.
    erplora_runtime::flows::store::create(
        origin.db(),
        "h2",
        origin.registry(),
        &NewFlow {
            name: "Neighbour's secret".into(),
            enabled: true,
            definition: welcome_definition(),
        },
        "hub_user:other",
    )
    .await
    .expect("the hub next door writes its own flow");

    let selection = ExportSelection {
        purpose: BundlePurpose::Backup,
        ..Default::default()
    };
    let bundle = export_hub(&origin, "h1", &selection, "b", "es", CREATED_AT)
        .await
        .expect("export");

    assert_eq!(
        bundle
            .manifest
            .flows
            .iter()
            .map(|f| f.name.as_str())
            .collect::<Vec<_>>(),
        vec!["Mine"],
        "only the automations of THIS hub travel in its backup"
    );
}

// ── Whose bundle it is, and what that changes ────────────────────────────────────────────

/// 🔴 The defense hub#986 asks for by name: a bundle from **another hub** does not re-grant a
/// single flow grant, and the report says so with its stable code.
///
/// The definitions DO land — a flow document is of the business, like the customers and products
/// that already travel in a backup section — but they land **paused**: without their authority a
/// flow is inert (default-deny), and arming it would be a file deciding that an automation nobody
/// reviewed may act here. Same criterion, and the same `is_same_hub`, as hub#473.
#[tokio::test]
async fn a_bundle_from_another_hub_regrants_nothing_and_its_flows_arrive_paused() {
    let origin = hub_with("h1", &["sales", "crm"]).await;
    let flow_id = create_flow(&origin, "Welcome", welcome_definition(), true).await;
    grant(&origin, &flow_id, &[(GrantKind::Command, "crm.note.add")]).await;
    let selection = ExportSelection {
        purpose: BundlePurpose::Backup,
        ..Default::default()
    };
    let bundle = export_hub(&origin, "h1", &selection, "b", "es", CREATED_AT)
        .await
        .expect("export");

    // Another hub entirely: a second location, or a file somebody was handed.
    let mut other = hub_with("h2", &["sales", "crm"]).await;
    let report = import_sections(
        &mut other,
        &bundle.manifest,
        &bundle.files,
        &ImportSelection::default(),
        "h2",
    )
    .await
    .expect("a bundle from elsewhere is not a reason to refuse the whole restore");

    let flows = other.list_flows().await.unwrap();
    assert_eq!(
        flows.len(),
        1,
        "the document is of the business, so it lands"
    );
    assert!(
        !flows[0].enabled,
        "…but PAUSED: a flow with no authority fails at every step, and arming it here was nobody's \
         decision"
    );
    assert_eq!(
        count(
            &other,
            "SELECT COUNT(*) AS c FROM _flow_grants WHERE deleted_at IS NULL"
        )
        .await,
        0,
        "not one grant row: a downloaded file may not decide what an automation is allowed to do"
    );
    let row = flows_row(&report).expect("the report has a row for the flows");
    assert_eq!(
        reason(&row.status),
        "flow_grants_not_portable",
        "and it says it with the stable code the shell translates: {:?}",
        row.status
    );

    // And it stays inert against a REAL event: the trigger is disarmed with the flow.
    complete_sale(&other, "h2", "120.50").await;
    other.drain_outbox().await.unwrap();
    other.process_flows().await.unwrap();
    assert_eq!(
        count(&other, "SELECT COUNT(*) AS c FROM crm_note").await,
        0,
        "a paused flow does not act, however real the event"
    );
}

/// 🔴 A bundle of **unknown origin** is not this hub either: bundles older than `hub.hub_id` carry
/// it empty, and «unknown == unknown» would make omitting the field the way to grant yourself an
/// automation's permissions.
#[tokio::test]
async fn a_bundle_of_unknown_origin_regrants_nothing() {
    let origin = hub_with("h1", &["sales", "crm"]).await;
    let flow_id = create_flow(&origin, "Welcome", welcome_definition(), true).await;
    grant(&origin, &flow_id, &[(GrantKind::Command, "crm.note.add")]).await;
    let mut bundle = export_hub(
        &origin,
        "h1",
        &ExportSelection::default(),
        "b",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");
    bundle.manifest.hub.hub_id = String::new();

    let mut restored = hub_with("h1", &["sales", "crm"]).await;
    let report = import_sections(
        &mut restored,
        &bundle.manifest,
        &bundle.files,
        &ImportSelection::default(),
        "h1",
    )
    .await
    .expect("import");

    assert_eq!(
        count(
            &restored,
            "SELECT COUNT(*) AS c FROM _flow_grants WHERE deleted_at IS NULL"
        )
        .await,
        0
    );
    assert!(!restored.list_flows().await.unwrap()[0].enabled);
    assert_eq!(
        reason(&flows_row(&report).unwrap().status),
        "flow_grants_not_portable"
    );
}

/// 🟡 A flow whose grant **cannot be re-granted here** arrives DISABLED, and the report says why.
///
/// The case is ordinary: the module that owned the command was not reinstalled, or a newer version
/// renamed it. The grant goes through `flows::grants::replace`, the same door the owner's screen
/// uses, so it is refused there — and an armed flow with a missing permission would fail on every
/// run, at 3 AM, with nobody watching. Paused with a reason is the honest state.
#[tokio::test]
async fn a_flow_whose_grant_cannot_be_regranted_arrives_disabled() {
    let origin = hub_with("h1", &["sales", "crm"]).await;
    let flow_id = create_flow(&origin, "Welcome", welcome_definition(), true).await;
    grant(&origin, &flow_id, &[(GrantKind::Command, "crm.note.add")]).await;
    let selection = ExportSelection {
        purpose: BundlePurpose::Backup,
        ..Default::default()
    };
    let bundle = export_hub(&origin, "h1", &selection, "b", "es", CREATED_AT)
        .await
        .expect("export");

    // The restore lands on a deployment where `crm` never came back.
    let mut restored = hub_with("h1", &["sales"]).await;
    let report = import_sections(
        &mut restored,
        &bundle.manifest,
        &bundle.files,
        &ImportSelection::default(),
        "h1",
    )
    .await
    .expect("a grant that cannot be re-made is not a reason to refuse the restore");

    let flows = restored.list_flows().await.unwrap();
    assert_eq!(flows.len(), 1, "the document is kept — the owner wrote it");
    assert!(
        !flows[0].enabled,
        "but it is PAUSED: an armed flow with no permission dies in every run"
    );
    assert!(
        restored
            .list_flow_grants(&flows[0].id)
            .await
            .unwrap()
            .is_empty(),
        "the grant naming a command this hub does not have was refused at the door"
    );
    let row = flows_row(&report).expect("the report has a row for the flows");
    assert_eq!(reason(&row.status), "flows_paused_without_grants");

    // And the flow really is inert: a sale creates no run.
    complete_sale(&restored, "h1", "120.50").await;
    restored.drain_outbox().await.unwrap();
    assert_eq!(
        count(&restored, "SELECT COUNT(*) AS c FROM _flow_runs").await,
        0,
        "a paused flow's triggers are disarmed, so the event starts nothing"
    );
}

/// 🟡 One refused grant does not take the flow's other permissions with it. `grants::replace`
/// refuses a whole list on purpose — a typed screen must fail loudly — but a restore is
/// best-effort, like everything else in this engine: what can come back, comes back.
#[tokio::test]
async fn the_grants_that_can_come_back_come_back_even_if_one_cannot() {
    let origin = hub_with("h1", &["sales", "crm"]).await;
    let flow_id = create_flow(&origin, "Welcome", welcome_definition(), true).await;
    grant(
        &origin,
        &flow_id,
        &[
            (GrantKind::Command, "crm.note.add"),
            (GrantKind::Query, "crm.customer.list"),
            (GrantKind::Http, "https://supplier.example/orders*"),
        ],
    )
    .await;
    let bundle = export_hub(
        &origin,
        "h1",
        &ExportSelection::default(),
        "b",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");
    let mut restored = hub_with("h1", &["sales", "crm"]).await;
    // The bundle also names a command nobody has: a hand-edited zip, or a module renamed since.
    let mut manifest = bundle.manifest.clone();
    manifest.flows[0]
        .grants
        .push(erplora_runtime::export::FlowGrantSpec {
            kind: "command".into(),
            value: "ghost.module.act".into(),
        });

    let report = import_sections(
        &mut restored,
        &manifest,
        &bundle.files,
        &ImportSelection::default(),
        "h1",
    )
    .await
    .expect("import");

    let flow = restored.list_flows().await.unwrap().remove(0);
    let mut live: Vec<String> = restored
        .list_flow_grants(&flow.id)
        .await
        .unwrap()
        .iter()
        .map(|g| format!("{}:{}", g.kind, g.value))
        .collect();
    live.sort();
    assert_eq!(
        live,
        vec![
            "command:crm.note.add".to_string(),
            "http:https://supplier.example/orders*".to_string(),
            "query:crm.customer.list".to_string(),
        ],
        "the three real permissions came back; only the one naming nothing was refused"
    );
    assert!(
        !flow.enabled,
        "and the flow waits, because part of its authority is missing"
    );
    assert_eq!(
        reason(&flows_row(&report).unwrap().status),
        "flows_paused_without_grants"
    );
}

// ── The same door as `POST /flows` ───────────────────────────────────────────────────────

/// 🔴 A document this hub **would refuse at the screen** cannot get in through a backup. The import
/// calls `store::create`, not an INSERT: whatever `POST /flows` rejects — an unknown schema version,
/// a broken cron, a `query` step naming a read nobody has — is rejected here too, counted, and the
/// rest of the flows still land.
#[tokio::test]
async fn a_document_the_save_door_refuses_does_not_get_in_through_a_backup() {
    let origin = hub_with("h1", &["sales", "crm"]).await;
    create_flow(&origin, "Good", welcome_definition(), true).await;
    let bundle = export_hub(
        &origin,
        "h1",
        &ExportSelection::default(),
        "b",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");

    // A hand-edited manifest with a second flow whose `query` step names a read that does not
    // exist. `store::create` refuses exactly this (hub#954) — a step naming nothing is not a read.
    let mut manifest = bundle.manifest.clone();
    manifest.flows.push(erplora_runtime::export::FlowSpec {
        name: "Forged".into(),
        enabled: true,
        definition: json!({
            "schema_version": 1,
            "triggers": [{ "kind": "manual" }],
            "steps": [{ "id": "read", "kind": "query", "query": "ghost.rows.list" }]
        }),
        grants: Vec::new(),
    });

    let mut restored = hub_with("h1", &["sales", "crm"]).await;
    let report = import_sections(
        &mut restored,
        &manifest,
        &bundle.files,
        &ImportSelection::default(),
        "h1",
    )
    .await
    .expect("a refused document is not a reason to refuse the whole restore");

    assert_eq!(
        restored
            .list_flows()
            .await
            .unwrap()
            .iter()
            .map(|f| f.name.clone())
            .collect::<Vec<_>>(),
        vec!["Good".to_string()],
        "the good one landed; the one this hub cannot save did not"
    );
    let row = flows_row(&report).expect("the report has a row for the flows");
    assert_eq!(reason(&row.status), "flows_not_restorable");
    assert_eq!(
        row.discarded_rows, 1,
        "and the refused document is counted, not swallowed"
    );
}

/// 🟡 Restoring the same backup **twice** does not duplicate the automations. A flow already live
/// with the same name and the same document is already there; re-creating it would give the owner
/// two copies of the same job — and two runs for every event.
#[tokio::test]
async fn restoring_the_same_backup_twice_does_not_duplicate_the_flows() {
    let origin = hub_with("h1", &["sales", "crm"]).await;
    let flow_id = create_flow(&origin, "Welcome", welcome_definition(), true).await;
    grant(&origin, &flow_id, &[(GrantKind::Command, "crm.note.add")]).await;
    let bundle = export_hub(
        &origin,
        "h1",
        &ExportSelection::default(),
        "b",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");

    let mut restored = hub_with("h1", &["sales", "crm"]).await;
    for _ in 0..2 {
        import_sections(
            &mut restored,
            &bundle.manifest,
            &bundle.files,
            &ImportSelection::default(),
            "h1",
        )
        .await
        .expect("import");
    }

    let flows = restored.list_flows().await.unwrap();
    assert_eq!(
        flows.len(),
        1,
        "the same document by the same name is one automation, not two"
    );
    assert_eq!(
        restored.list_flow_grants(&flows[0].id).await.unwrap().len(),
        1,
        "and its authority is not duplicated either"
    );
}

/// 🔴 The restore is **additive**: a flow this hub wrote after the backup was taken is still there
/// afterwards. Mirroring the bundle would let restoring an older copy DELETE an automation the
/// owner created later, with nobody deciding it — the same lesson as hub#473's grants.
#[tokio::test]
async fn restoring_never_removes_a_flow_the_bundle_does_not_carry() {
    let origin = hub_with("h1", &["sales", "crm"]).await;
    create_flow(&origin, "Welcome", welcome_definition(), true).await;
    let bundle = export_hub(
        &origin,
        "h1",
        &ExportSelection::default(),
        "b",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");

    let mut restored = hub_with("h1", &["sales", "crm"]).await;
    create_flow(&restored, "Written afterwards", welcome_definition(), true).await;
    import_sections(
        &mut restored,
        &bundle.manifest,
        &bundle.files,
        &ImportSelection::default(),
        "h1",
    )
    .await
    .expect("import");

    let mut names: Vec<String> = restored
        .list_flows()
        .await
        .unwrap()
        .iter()
        .map(|f| f.name.clone())
        .collect();
    names.sort();
    assert_eq!(
        names,
        vec!["Welcome".to_string(), "Written afterwards".to_string()]
    );
}

/// 🔴 A bundle with no flows says nothing about them: no hollow row in the report, no section in
/// the inventory. Silence is only honest when there is nothing to say.
#[tokio::test]
async fn a_hub_without_flows_reports_nothing_about_them() {
    let origin = hub_with("h1", &["sales", "crm"]).await;
    let bundle = export_hub(
        &origin,
        "h1",
        &ExportSelection::default(),
        "b",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export");
    assert!(bundle.manifest.flows.is_empty());
    assert!(!bundle
        .manifest
        .sections
        .contains(&FLOWS_SECTION.to_string()));

    let mut restored = hub_with("h1", &["sales", "crm"]).await;
    let report = import_sections(
        &mut restored,
        &bundle.manifest,
        &bundle.files,
        &ImportSelection::default(),
        "h1",
    )
    .await
    .expect("import");
    assert!(flows_row(&report).is_none(), "{:?}", report.sections);
}
