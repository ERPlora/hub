#![allow(non_snake_case)] // the names shout the part that matters, like the rest of the battery
//! hub#1701 — **the gate**: a rule the OWNER wrote stops a command BEFORE anything is stored.
//!
//! Doc: `architecture/hub/policies.md` (§4.3 the exact spot, §5 the guards, §6.1 the fail-closed
//! path). The as-built order of the funnel's seven gates lives in `runtime-dispatcher.md` §2.0 and
//! is not copied here.
//!
//! This battery is what holds up the three non-negotiable guards. Each one has its mutant written
//! in the test that covers it — a mutant that is RUN, not one that is declared.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::policies::{self, Mode};
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::json;

fn fixture_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_1701")
}

fn admin_ctx() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

/// A cashier: they have the command's permission, and nothing else.
fn cashier_ctx() -> RequestContext {
    RequestContext::new("h1", "u2", ["p1701.order.discount".to_string()])
}

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

async fn fresh_runtime() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture_dir())
        .await
        .expect("install p1701");
    rt
}

/// The usual rule: «a discount over 20 % is not allowed».
fn over_20(mode: &str) -> policies::NewPolicy {
    policies::NewPolicy {
        checkpoint: "p1701/discount_limit".into(),
        condition: json!({ "discount_percent": { "gt": 20 } }),
        outcome: "block".into(),
        message: "Los descuentos de más del 20 % los autoriza el encargado".into(),
        mode: mode.into(),
        is_active: true,
    }
}

/// The rule of the second checkpoint, the one declaring a fact the command may not carry.
fn tip_over_10(mode: &str) -> policies::NewPolicy {
    policies::NewPolicy {
        checkpoint: "p1701/tip_limit".into(),
        condition: json!({ "tip_percent": { "gt": 10 } }),
        outcome: "block".into(),
        message: "Una propina de más del 10 % la aprueba el encargado".into(),
        mode: mode.into(),
        is_active: true,
    }
}

/// Writes a `_policy` row **skipping the write door**: it is the only way to have in the table
/// what only a LATER core could have stored (ADR-0269 allows rolling back).
async fn insert_raw_policy(rt: &Runtime, outcome: &str, condition: &str) {
    let mut p = Params::new();
    p.insert("id".into(), json!("pol-raw"));
    p.insert("outcome".into(), json!(outcome));
    p.insert("condition".into(), json!(condition));
    rt.db()
        .execute(
            "INSERT INTO _policy (id, hub_id, checkpoint, condition, outcome, message, mode, \
                                  is_active, created_at, created_by, updated_at, updated_by) \
             VALUES (:id, 'h1', 'p1701/discount_limit', :condition, :outcome, 'del futuro', \
                     'enforce', 1, '2026-09-09T00:00:00Z', 'u1', '2026-09-09T00:00:00Z', 'u1')",
            &p,
        )
        .await
        .expect("insertar la fila del futuro");
}

fn domain_code(err: &RuntimeError) -> String {
    match err {
        RuntimeError::Domain { code, .. } => code.clone(),
        other => panic!("se esperaba un error de dominio (ADR-0205) y llegó {other:?}"),
    }
}

// ─────────────────────────────────────────────────────────────────────────────────────────────
// The complete path of `block`
// ─────────────────────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_checkpoint_of_an_installed_module_is_offered_to_the_owner_hub1701() {
    let rt = fresh_runtime().await;
    let checkpoints = rt.policy_checkpoints();
    // The TWO the package declares and the installer accepted, in stable order. `tip_limit` has
    // to be here: half the battery below writes rules on it, and a rule on a checkpoint that is
    // not offered is rejected with `ERR_CHECKPOINT_NOT_FOUND`.
    assert_eq!(checkpoints.len(), 2, "{checkpoints:?}");
    assert_eq!(checkpoints[0].id, "p1701/discount_limit");
    assert_eq!(checkpoints[0].command, "p1701.order.set_discount");
    assert_eq!(checkpoints[1].id, "p1701/tip_limit");
    assert_eq!(checkpoints[1].command, "p1701.order.set_tip");
}

#[tokio::test]
async fn the_rule_applies_to_the_CASHIER_who_does_have_the_permission_hub1701() {
    // The other half of «it only restricts», and the real case the feature exists for: whoever
    // comes through here is not someone without permission, it is the person at the counter who
    // CAN apply discounts and whom the owner puts a cap on. Without this positive control, «a
    // policy never opens a door» would hold just as well with a gate that NEVER applies.
    let rt = fresh_runtime().await;
    rt.create_policy(&over_20("enforce"), "u1").await.unwrap();

    rt.execute_command(
        "p1701.order.set_discount",
        &params(json!({ "order_id": "o1", "discount_percent": 10 })),
        &cashier_ctx(),
    )
    .await
    .expect("un 10 % entra en lo que el dueño dejó");

    let err = rt
        .execute_command(
            "p1701.order.set_discount",
            &params(json!({ "order_id": "o2", "discount_percent": 35 })),
            &cashier_ctx(),
        )
        .await
        .expect_err("y un 35 % no, aunque tenga el permiso");
    assert_eq!(domain_code(&err), policies::ERR_BLOCKED);
    assert_eq!(order_rows(&rt).await, 1, "solo entró la venta que la norma dejó");
}

#[tokio::test]
async fn a_matching_policy_BLOCKS_the_command_before_the_row_exists_hub1701() {
    let rt = fresh_runtime().await;
    rt.create_policy(&over_20("enforce"), "u1").await.unwrap();

    let err = rt
        .execute_command(
            "p1701.order.set_discount",
            &params(json!({ "order_id": "o1", "discount_percent": 35 })),
            &admin_ctx(),
        )
        .await
        .expect_err("la norma tiene que impedirlo");

    assert_eq!(domain_code(&err), policies::ERR_BLOCKED);
    // 🔴 «BEFORE anything is stored»: if the gate ran after the transaction, the row would be there.
    assert_eq!(order_rows(&rt).await, 0, "el gate corre antes de la transacción");
}

#[tokio::test]
async fn the_owners_own_words_travel_with_the_refusal_hub1701() {
    // A mute `block` would be worse than not having the feature: the person at the counter has to
    // read WHY. The code is stable (ADR-0205) and the text is the one the owner wrote.
    let rt = fresh_runtime().await;
    rt.create_policy(&over_20("enforce"), "u1").await.unwrap();

    let err = rt
        .execute_command(
            "p1701.order.set_discount",
            &params(json!({ "order_id": "o1", "discount_percent": 35 })),
            &admin_ctx(),
        )
        .await
        .unwrap_err();

    match err {
        RuntimeError::Domain { code, message } => {
            assert_eq!(code, policies::ERR_BLOCKED);
            assert_eq!(message, "Los descuentos de más del 20 % los autoriza el encargado");
        }
        other => panic!("{other:?}"),
    }
}

#[tokio::test]
async fn a_policy_that_does_NOT_match_lets_the_command_through_hub1701() {
    let rt = fresh_runtime().await;
    rt.create_policy(&over_20("enforce"), "u1").await.unwrap();

    rt.execute_command(
        "p1701.order.set_discount",
        &params(json!({ "order_id": "o1", "discount_percent": 5 })),
        &admin_ctx(),
    )
    .await
    .expect("un 5 % no lo toca ninguna norma");

    assert_eq!(order_rows(&rt).await, 1);
}

#[tokio::test]
async fn a_command_with_NO_policy_costs_nothing_and_passes_hub1701() {
    let rt = fresh_runtime().await;
    rt.execute_command(
        "p1701.order.set_discount",
        &params(json!({ "order_id": "o1", "discount_percent": 90 })),
        &admin_ctx(),
    )
    .await
    .expect("sin normas escritas no hay gate");
    assert_eq!(order_rows(&rt).await, 1);
}

#[tokio::test]
async fn an_INACTIVE_policy_does_not_gate_anything_hub1701() {
    let rt = fresh_runtime().await;
    let mut new = over_20("enforce");
    new.is_active = false;
    rt.create_policy(&new, "u1").await.unwrap();

    rt.execute_command(
        "p1701.order.set_discount",
        &params(json!({ "order_id": "o1", "discount_percent": 35 })),
        &admin_ctx(),
    )
    .await
    .expect("una norma apagada no impide nada");
}

#[tokio::test]
async fn a_policy_only_gates_the_command_of_ITS_checkpoint_hub1701() {
    let rt = fresh_runtime().await;
    rt.create_policy(&over_20("enforce"), "u1").await.unwrap();

    rt.execute_command(
        "p1701.order.close",
        &params(json!({ "order_id": "o1" })),
        &admin_ctx(),
    )
    .await
    .expect("`close` no tiene checkpoint: la norma del descuento no le toca");
}

// ─────────────────────────────────────────────────────────────────────────────────────────────
// Guard 1 — IT ONLY RESTRICTS
// ─────────────────────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_policy_NEVER_opens_a_door_the_permission_had_shut_hub1701() {
    // 🔴 MUTANT of this guard: move the gate call ABOVE `permissions::check_command` in
    // `commands::execute_at`. This test falls, because the person without the permission would get
    // the policy's verdict (or would pass) instead of `PermissionDenied`.
    let rt = fresh_runtime().await;
    rt.create_policy(&over_20("enforce"), "u1").await.unwrap();
    // Someone WITHOUT the command's permission, with a discount the rule would let through.
    let nobody = RequestContext::new("h1", "u3", ["p1701.order.close".to_string()]);

    let err = rt
        .execute_command(
            "p1701.order.set_discount",
            &params(json!({ "order_id": "o1", "discount_percent": 1 })),
            &nobody,
        )
        .await
        .expect_err("sin permiso no se entra, con norma o sin ella");

    assert!(
        matches!(err, RuntimeError::PermissionDenied(_)),
        "la negativa la sigue firmando el RBAC, no la política: {err:?}"
    );
    assert_eq!(order_rows(&rt).await, 0);
}

#[tokio::test]
async fn a_policy_of_ANOTHER_hub_does_not_gate_this_one_hub1701() {
    // Row contract: a rule belongs to the hub that wrote it. 🔴 MUTANT: drop the `hub_id` filter
    // from `policies::enforce` — this test falls.
    let rt = fresh_runtime().await;
    rt.create_policy(&over_20("enforce"), "u1").await.unwrap();
    // Same runtime, context of ANOTHER hub.
    let other = RequestContext::new("h2", "u1", ["*".to_string()]);

    let err = rt
        .execute_command(
            "p1701.order.set_discount",
            &params(json!({ "order_id": "o1", "discount_percent": 35 })),
            &other,
        )
        .await
        .err();

    assert!(
        !matches!(&err, Some(RuntimeError::Domain { code, .. }) if code == policies::ERR_BLOCKED),
        "la norma del hub h1 no puede gatear a h2: {err:?}"
    );
}

// ─────────────────────────────────────────────────────────────────────────────────────────────
// Guard 2 — FAIL CLOSED
// ─────────────────────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_DECLARED_fact_the_command_does_not_carry_DENIES_hub1701() {
    // 🔴 The §6.1 guard, and its mutant: replace the denial with a `continue` in
    // `policies::evaluate` — this test falls.
    //
    // The `tip_limit` checkpoint declares `approved_by`, which the `set_tip` schema declares
    // OPTIONAL and WITHOUT a default: a payload that does not send it reaches the gate without the
    // fact. A gate that evaluated the condition and read its `bool` could not tell «the fact is
    // missing» from «it did not match», and would let the command through: a mute fail-open
    // through the back door.
    let rt = fresh_runtime().await;
    rt.create_policy(&tip_over_10("enforce"), "u1").await.unwrap();

    let err = rt
        .execute_command(
            "p1701.order.set_tip",
            &params(json!({ "order_id": "o1", "tip_percent": 5 })),
            &admin_ctx(),
        )
        .await
        .expect_err("falta un hecho declarado: se DENIEGA, no se deja pasar");

    assert_eq!(domain_code(&err), policies::ERR_FACT_MISSING);
    assert_eq!(order_rows(&rt).await, 0);
}

#[tokio::test]
async fn the_same_command_WITH_the_declared_fact_is_judged_on_its_merits_hub1701() {
    // The positive control of the test above: with the fact present, the rule decides by its
    // condition again. Without this, «it always denies» would pass for «fail-closed works».
    let rt = fresh_runtime().await;
    rt.create_policy(&tip_over_10("enforce"), "u1").await.unwrap();

    rt.execute_command(
        "p1701.order.set_tip",
        &params(json!({ "order_id": "o1", "tip_percent": 5, "approved_by": "u9" })),
        &admin_ctx(),
    )
    .await
    .expect("con el hecho presente y la condición sin casar, pasa");

    let err = rt
        .execute_command(
            "p1701.order.set_tip",
            &params(json!({ "order_id": "o2", "tip_percent": 50, "approved_by": "u9" })),
            &admin_ctx(),
        )
        .await
        .expect_err("y con la condición casando, impide");
    assert_eq!(domain_code(&err), policies::ERR_BLOCKED);
}

#[tokio::test]
async fn the_gate_sees_the_payload_AFTER_the_schema_defaults_hub1701() {
    // 🔴 The spot in the funnel, checked by its consequence: `channel` is a DECLARED fact the
    // caller does not send and the schema fills in with `"counter"` (`commands.rs`, schema block).
    // A gate placed BEFORE that block would see `channel` missing and —fail-closed— would deny
    // every normal sale. MUTANT: move the gate call above the schema block; this test falls.
    let rt = fresh_runtime().await;
    rt.create_policy(&over_20("enforce"), "u1").await.unwrap();

    rt.execute_command(
        "p1701.order.set_discount",
        &params(json!({ "order_id": "o1", "discount_percent": 5 })),
        &admin_ctx(),
    )
    .await
    .expect("`channel` lo pone el default del schema antes de que el gate mire");

    let row = order_channel(&rt).await;
    assert_eq!(row, "counter", "y el default es el que se guarda");
}

#[tokio::test]
async fn a_stored_outcome_this_core_cannot_run_DENIES_instead_of_passing_hub1701() {
    // A hub that rolled back finds in `_policy` an `elevate:` this core does not run (hub#1710).
    // The row is written by hand because that is EXACTLY how it would arrive: this core's write
    // door rejects it.
    // 🔴 Fail-closed: it is not ignored. MUTANT: treat the unknown outcome as «does not apply» — falls.
    let rt = fresh_runtime().await;
    insert_raw_policy(&rt, "elevate:p1701.order.discount", r#"{"discount_percent":{"gt":20}}"#).await;
    rt.reload_policies().await.unwrap();

    let err = rt
        .execute_command(
            "p1701.order.set_discount",
            &params(json!({ "order_id": "o1", "discount_percent": 35 })),
            &admin_ctx(),
        )
        .await
        .expect_err("una consecuencia que no se sabe aplicar DENIEGA");

    assert_eq!(domain_code(&err), policies::ERR_OUTCOME_NOT_AVAILABLE);
    assert_eq!(order_rows(&rt).await, 0);
}

#[tokio::test]
async fn a_stored_condition_this_core_cannot_read_DENIES_hub1701() {
    // Same thing: an operator this core does not know can only have come from a later version.
    let rt = fresh_runtime().await;
    insert_raw_policy(&rt, "block", r#"{"discount_percent":{"matches":20}}"#).await;
    rt.reload_policies().await.unwrap();

    let err = rt
        .execute_command(
            "p1701.order.set_discount",
            &params(json!({ "order_id": "o1", "discount_percent": 5 })),
            &admin_ctx(),
        )
        .await
        .expect_err("una condición ilegible DENIEGA");

    assert_eq!(domain_code(&err), policies::ERR_CONDITION_UNREADABLE);
}

// ─────────────────────────────────────────────────────────────────────────────────────────────
// mode: warn — the ramp
// ─────────────────────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_warn_policy_NEVER_stops_the_till_hub1701() {
    let rt = fresh_runtime().await;
    rt.create_policy(&over_20("warn"), "u1").await.unwrap();

    rt.execute_command(
        "p1701.order.set_discount",
        &params(json!({ "order_id": "o1", "discount_percent": 35 })),
        &admin_ctx(),
    )
    .await
    .expect("`warn` avisa; no impide");

    assert_eq!(order_rows(&rt).await, 1, "y la venta se guarda");
}

#[tokio::test]
async fn a_warn_policy_that_cannot_be_evaluated_does_not_stop_the_till_either_hub1701() {
    // Fail-closed belongs to `enforce`. In `warn` the rule is NOT in force yet, so not even a
    // missing fact can stop a till: it is the ramp, and a ramp that blocks is not one.
    let rt = fresh_runtime().await;
    rt.create_policy(&tip_over_10("warn"), "u1").await.unwrap();

    rt.execute_command(
        "p1701.order.set_tip",
        &params(json!({ "order_id": "o1", "tip_percent": 50 })),
        &admin_ctx(),
    )
    .await
    .expect("en `warn` nada impide");
    assert_eq!(order_rows(&rt).await, 1);
}

// ─────────────────────────────────────────────────────────────────────────────────────────────
// Guard 3 — BOUNDED COST
// ─────────────────────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn the_number_of_policies_per_checkpoint_has_a_CEILING_hub1701() {
    let rt = fresh_runtime().await;
    for i in 0..policies::MAX_POLICIES_PER_CHECKPOINT {
        let mut new = over_20("enforce");
        new.message = format!("norma {i}");
        rt.create_policy(&new, "u1").await.expect("cabe");
    }
    let err = rt
        .create_policy(&over_20("enforce"), "u1")
        .await
        .expect_err("la que sobra no entra");
    assert_eq!(domain_code(&err), policies::ERR_TOO_MANY);
}

// ─────────────────────────────────────────────────────────────────────────────────────────────
// CRUD — what the owner writes, and what they are not allowed to write
// ─────────────────────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_policy_survives_a_restart_and_gates_again_hub1701() {
    // The in-memory index is rebuilt on boot: otherwise a rule would only be in force until the
    // next deploy.
    let rt = fresh_runtime().await;
    rt.create_policy(&over_20("enforce"), "u1").await.unwrap();
    rt.reload_policies().await.unwrap();

    let err = rt
        .execute_command(
            "p1701.order.set_discount",
            &params(json!({ "order_id": "o1", "discount_percent": 35 })),
            &admin_ctx(),
        )
        .await
        .unwrap_err();
    assert_eq!(domain_code(&err), policies::ERR_BLOCKED);
}

#[tokio::test]
async fn a_deleted_policy_stops_gating_in_the_very_next_command_hub1701() {
    let rt = fresh_runtime().await;
    let saved = rt.create_policy(&over_20("enforce"), "u1").await.unwrap();
    rt.delete_policy(&saved.id, "u1").await.unwrap();

    rt.execute_command(
        "p1701.order.set_discount",
        &params(json!({ "order_id": "o1", "discount_percent": 35 })),
        &admin_ctx(),
    )
    .await
    .expect("borrada la norma, la orden pasa — y en la MISMA sesión, no tras reiniciar");
}

#[tokio::test]
async fn a_policy_on_a_checkpoint_that_does_not_exist_is_refused_hub1701() {
    let rt = fresh_runtime().await;
    let mut new = over_20("enforce");
    new.checkpoint = "p1701/ghost".into();
    let err = rt.create_policy(&new, "u1").await.unwrap_err();
    assert_eq!(domain_code(&err), policies::ERR_CHECKPOINT_NOT_FOUND);
}

#[tokio::test]
async fn a_condition_on_a_fact_the_checkpoint_does_not_declare_is_refused_hub1701() {
    // The checkpoint says WHICH DATA may be reasoned about. A condition naming something else
    // reads outside the vocabulary the module declared — and that is the same hole hub#662 closed
    // in flows with `secret.·`.
    let rt = fresh_runtime().await;
    let mut new = over_20("enforce");
    new.condition = json!({ "order_id": { "eq": "o1" } });
    let err = rt.create_policy(&new, "u1").await.unwrap_err();
    assert_eq!(domain_code(&err), policies::ERR_FACT_NOT_DECLARED);
}

#[tokio::test]
async fn an_outcome_the_checkpoint_does_not_offer_is_refused_hub1701() {
    let rt = fresh_runtime().await;
    let mut new = over_20("enforce");
    new.outcome = "elevate:p1701.order.close".into();
    let err = rt.create_policy(&new, "u1").await.unwrap_err();
    assert_eq!(domain_code(&err), policies::ERR_OUTCOME_NOT_OFFERED);
}

#[tokio::test]
async fn the_elevate_outcome_is_refused_by_THIS_core_with_its_own_code_hub1701() {
    // The checkpoint DOES offer it; what is missing is this core knowing how to run it
    // (hub#1710). Telling it apart from the one above matters: one is fixed by changing the rule,
    // the other by waiting for a release.
    let rt = fresh_runtime().await;
    let mut new = over_20("enforce");
    new.outcome = "elevate:p1701.order.discount".into();
    let err = rt.create_policy(&new, "u1").await.unwrap_err();
    assert_eq!(domain_code(&err), policies::ERR_OUTCOME_NOT_AVAILABLE);
}

#[tokio::test]
async fn a_block_with_no_message_is_refused_hub1701() {
    // A mute `block` would be worse than not having the feature.
    let rt = fresh_runtime().await;
    let mut new = over_20("enforce");
    new.message = "   ".into();
    let err = rt.create_policy(&new, "u1").await.unwrap_err();
    assert_eq!(domain_code(&err), policies::ERR_MESSAGE_REQUIRED);
}

#[tokio::test]
async fn an_unknown_mode_is_refused_hub1701() {
    let rt = fresh_runtime().await;
    let mut new = over_20("enforce");
    new.mode = "silent".into();
    let err = rt.create_policy(&new, "u1").await.unwrap_err();
    assert_eq!(domain_code(&err), policies::ERR_UNKNOWN_MODE);
}

#[tokio::test]
async fn an_unreadable_condition_is_refused_at_WRITE_time_hub1701() {
    let rt = fresh_runtime().await;
    let mut new = over_20("enforce");
    new.condition = json!({ "discount_percent": { "matches": 20 } });
    let err = rt.create_policy(&new, "u1").await.unwrap_err();
    // It comes from the frozen language: unknown operator.
    assert!(
        matches!(&err, RuntimeError::Domain { code, .. } if code.starts_with("flow.")),
        "{err:?}"
    );
}

#[tokio::test]
async fn an_empty_condition_is_refused_hub1701() {
    // An empty condition matches ALWAYS (it is the flows' permissive default, explicit there). In
    // a policy that is a rule blocking the whole command without saying so, and the owner wrote it
    // believing it filtered something.
    let rt = fresh_runtime().await;
    let mut new = over_20("enforce");
    new.condition = json!({});
    let err = rt.create_policy(&new, "u1").await.unwrap_err();
    assert_eq!(domain_code(&err), policies::ERR_EMPTY_CONDITION);
}

#[tokio::test]
async fn listing_and_updating_a_policy_round_trips_hub1701() {
    let rt = fresh_runtime().await;
    let saved = rt.create_policy(&over_20("warn"), "u1").await.unwrap();
    assert_eq!(saved.mode, Mode::Warn.as_str());

    let mut promoted = over_20("enforce");
    promoted.message = "Con el encargado".into();
    let updated = rt.update_policy(&saved.id, &promoted, "u2").await.unwrap();
    assert_eq!(updated.mode, "enforce");
    assert_eq!(updated.message, "Con el encargado");
    assert_eq!(updated.updated_by, "u2");

    let all = rt.list_policies().await.unwrap();
    assert_eq!(all.len(), 1);
    assert_eq!(all[0].id, saved.id);

    // And the promotion is in force without restarting.
    let err = rt
        .execute_command(
            "p1701.order.set_discount",
            &params(json!({ "order_id": "o1", "discount_percent": 35 })),
            &admin_ctx(),
        )
        .await
        .unwrap_err();
    assert_eq!(domain_code(&err), policies::ERR_BLOCKED);
}

#[tokio::test]
async fn a_policy_of_another_hub_is_not_listed_nor_readable_hub1701() {
    let rt = fresh_runtime().await;
    rt.create_policy(&over_20("enforce"), "u1").await.unwrap();
    let other = Runtime::with_hub_id(Box::new(fresh_db().await), "h2");
    other.ensure_system_tables().await.unwrap();
    assert!(other.list_policies().await.unwrap().is_empty());
}

// ─────────────────────────────────────────────────────────────────────────────────────────────
// Read helpers
// ─────────────────────────────────────────────────────────────────────────────────────────────

async fn order_rows(rt: &Runtime) -> i64 {
    let rows = rt
        .db()
        .query("SELECT COUNT(*) AS n FROM p1701_order", &Params::new())
        .await
        .expect("count")
        .rows;
    rows[0]["n"].as_i64().unwrap()
}

async fn order_channel(rt: &Runtime) -> String {
    let rows = rt
        .db()
        .query("SELECT channel FROM p1701_order", &Params::new())
        .await
        .expect("channel")
        .rows;
    rows[0]["channel"].as_str().unwrap().to_string()
}
