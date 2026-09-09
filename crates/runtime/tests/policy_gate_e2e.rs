#![allow(non_snake_case)] // los nombres gritan la parte que importa, como el resto de la batería
//! hub#1701 — **el gate**: una norma que el DUEÑO escribió impide una orden ANTES de guardar nada.
//!
//! Doc: `architecture/hub/policies.md` (§4.3 el punto exacto, §5 las guardas, §6.1 el fallo
//! cerrado). El orden as-built de los siete gates del embudo vive en `runtime-dispatcher.md` §2.0
//! y no se copia aquí.
//!
//! Esta batería es la que sostiene las tres guardas no negociables. Cada una tiene su mutante
//! escrito en el test que la cubre — un mutante que se EJECUTA, no que se declara.
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

/// Un cajero: tiene el permiso del command, y nada más.
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

/// La norma de siempre: «un descuento de más del 20 % no se deja».
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

/// La norma del segundo checkpoint, el que declara un hecho que el command puede no traer.
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

/// Escribe una fila de `_policy` **saltándose la puerta de escritura**: es la única forma de tener
/// en la tabla lo que solo un core POSTERIOR habría podido guardar (ADR-0269 permite rodar atrás).
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
// El camino completo del `block`
// ─────────────────────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_checkpoint_of_an_installed_module_is_offered_to_the_owner_hub1701() {
    let rt = fresh_runtime().await;
    let checkpoints = rt.policy_checkpoints();
    // Los DOS que el paquete declara y el instalador aceptó, en orden estable. `tip_limit` tiene
    // que estar aquí: media batería de abajo escribe normas sobre él, y una norma sobre un punto de
    // control que no se ofrece se rechaza con `ERR_CHECKPOINT_NOT_FOUND`.
    assert_eq!(checkpoints.len(), 2, "{checkpoints:?}");
    assert_eq!(checkpoints[0].id, "p1701/discount_limit");
    assert_eq!(checkpoints[0].command, "p1701.order.set_discount");
    assert_eq!(checkpoints[1].id, "p1701/tip_limit");
    assert_eq!(checkpoints[1].command, "p1701.order.set_tip");
}

#[tokio::test]
async fn the_rule_applies_to_the_CASHIER_who_does_have_the_permission_hub1701() {
    // La otra mitad de «solo restringe», y el caso real por el que existe la función: quien pasa por
    // aquí no es alguien sin permiso, es la persona del mostrador que SÍ puede aplicar descuentos y
    // a quien el dueño le pone un tope. Sin este control positivo, «la política nunca abre una
    // puerta» se cumpliría igual con un gate que no aplica NUNCA.
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
    // 🔴 «ANTES de guardar nada»: si el gate corriese después de la transacción, la fila estaría.
    assert_eq!(order_rows(&rt).await, 0, "el gate corre antes de la transacción");
}

#[tokio::test]
async fn the_owners_own_words_travel_with_the_refusal_hub1701() {
    // Un `block` mudo sería peor que no tener la función: la persona del mostrador tiene que leer
    // POR QUÉ. El código es estable (ADR-0205) y el texto es el que escribió el dueño.
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
// Guarda 1 — SOLO RESTRINGE
// ─────────────────────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_policy_NEVER_opens_a_door_the_permission_had_shut_hub1701() {
    // 🔴 MUTANTE de esta guarda: mover la llamada al gate por ENCIMA de `permissions::check_command`
    // en `commands::execute_at`. Este test cae, porque la persona sin permiso recibiría el veredicto
    // de la política (o pasaría) en vez de `PermissionDenied`.
    let rt = fresh_runtime().await;
    rt.create_policy(&over_20("enforce"), "u1").await.unwrap();
    // Alguien SIN el permiso del command, con un descuento que la norma dejaría pasar.
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
    // Contrato de fila: una norma es del hub que la escribió. 🔴 MUTANTE: quitar el filtro por
    // `hub_id` de `policies::enforce` — este test cae.
    let rt = fresh_runtime().await;
    rt.create_policy(&over_20("enforce"), "u1").await.unwrap();
    // Mismo runtime, contexto de OTRO hub.
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
// Guarda 2 — FALLO CERRADO
// ─────────────────────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_DECLARED_fact_the_command_does_not_carry_DENIES_hub1701() {
    // 🔴 La guarda del §6.1, y su mutante: sustituir la denegación por un `continue` en
    // `policies::evaluate` — este test cae.
    //
    // El checkpoint `tip_limit` declara `approved_by`, que el schema de `set_tip` declara OPCIONAL
    // y SIN default: un payload que no lo mande llega al gate sin el hecho. Un gate que evaluase la
    // condición y leyese su `bool` no podría distinguir «falta el hecho» de «no casaba», y dejaría
    // pasar el command: fail-open mudo por la puerta de atrás.
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
    // El control positivo del test de arriba: con el hecho presente, la norma vuelve a decidir por
    // la condición. Sin esto, «deniega siempre» pasaría por «fail-closed funciona».
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
    // 🔴 El punto del embudo, comprobado por su consecuencia: `channel` es un hecho DECLARADO que el
    // llamador no manda y que el schema rellena con `"counter"` (`commands.rs`, bloque de schema).
    // Un gate colocado ANTES de ese bloque vería `channel` ausente y —fail-closed— denegaría toda
    // venta normal. MUTANTE: mover la llamada al gate por encima del bloque de schema; este test cae.
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
    // Un hub que rodó atrás encuentra en `_policy` un `elevate:` que este core no ejecuta
    // (hub#1710). La fila se escribe a mano porque es EXACTAMENTE como llegaría: la puerta de
    // escritura de este core la rechaza.
    // 🔴 Fail-closed: no se ignora. MUTANTE: tratar el outcome desconocido como «no aplica» — cae.
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
    // Igual: un operador que este core no conoce solo puede haber llegado de una versión posterior.
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
// mode: warn — la rampa
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
    // El fallo cerrado es de `enforce`. En `warn` la norma todavía NO está en vigor, así que ni
    // siquiera un hecho ausente puede parar una caja: es la rampa, y una rampa que bloquea no lo es.
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
// Guarda 3 — COSTE ACOTADO
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
// CRUD — lo que el dueño escribe, y lo que no se le deja escribir
// ─────────────────────────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn a_policy_survives_a_restart_and_gates_again_hub1701() {
    // El índice en memoria se reconstruye al arrancar: si no, una norma solo estaría en vigor
    // hasta el siguiente despliegue.
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
    // El checkpoint dice CON QUÉ DATOS se puede razonar. Una condición que nombra otra cosa lee
    // fuera del vocabulario que el módulo declaró — y ese es el mismo agujero que hub#662 cerró en
    // los flujos con `secret.·`.
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
    // El checkpoint SÍ lo ofrece; lo que falta es que este core lo sepa ejecutar (hub#1710).
    // Distinguirlo del de arriba importa: uno se arregla cambiando la norma, el otro esperando una
    // release.
    let rt = fresh_runtime().await;
    let mut new = over_20("enforce");
    new.outcome = "elevate:p1701.order.discount".into();
    let err = rt.create_policy(&new, "u1").await.unwrap_err();
    assert_eq!(domain_code(&err), policies::ERR_OUTCOME_NOT_AVAILABLE);
}

#[tokio::test]
async fn a_block_with_no_message_is_refused_hub1701() {
    // Un `block` mudo sería peor que no tener la función.
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
    // Viene del lenguaje congelado: operador desconocido.
    assert!(
        matches!(&err, RuntimeError::Domain { code, .. } if code.starts_with("flow.")),
        "{err:?}"
    );
}

#[tokio::test]
async fn an_empty_condition_is_refused_hub1701() {
    // Una condición vacía casa SIEMPRE (es el default permisivo de los flujos, explícito allí). En
    // una política eso es una norma que bloquea el command entero sin decirlo, y el dueño la
    // escribió creyendo que filtraba algo.
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

    // Y la promoción está en vigor sin reiniciar.
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
// Helpers de lectura
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
