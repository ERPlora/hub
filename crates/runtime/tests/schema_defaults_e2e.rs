//! Regresión de la causa raíz (decision-log 2026-06-25): el runtime debe inyectar los `default`
//! del JSON Schema de entrada de un command en las claves AUSENTES, ANTES de bindear el SQL.
//!
//! El fixture `defaults` tiene `defaults.items.create` con un schema que declara
//! `status` (default "open") y `priority` (default 3) opcionales, y un SQL que los bindea
//! `:status`/`:priority` **SIN COALESCE** sobre columnas `NOT NULL`. Sin la inyección de defaults
//! el INSERT petaría con `NOT NULL constraint failed`; con ella inserta y persiste el valor por
//! defecto. Esto demuestra que el COALESCE por-módulo es ahora redundante (no necesario).
use std::path::PathBuf;

use erplora_db::{Params, SqliteAdapter};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn module_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_defaults")
}

async fn fresh_runtime() -> Runtime {
    let db = SqliteAdapter::open_in_memory().await.expect("sqlite en memoria");
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&module_dir()).await.expect("instalar defaults");
    rt
}

fn admin_ctx() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

/// Caso raíz: omitir un campo opcional con `default` ya NO peta; el INSERT (sin COALESCE)
/// recibe el valor por defecto del schema y lo persiste.
#[tokio::test]
async fn omitted_defaulted_fields_are_injected_and_inserted_without_coalesce() {
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();

    // Solo `name`; `status` y `priority` se omiten → el binder debe inyectar sus defaults.
    rt.execute_command("defaults.items.create", &params(json!({ "name": "alpha" })), &ctx)
        .await
        .expect("crear con defaults omitidos NO debe petar por NOT NULL");

    let rows =
        rt.execute_query("defaults.items.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0]["status"], json!("open"), "default de status no aplicado");
    assert_eq!(rows[0]["priority"], json!(3), "default de priority no aplicado");
}

/// Los valores aportados por el caller NO se sobreescriben con el `default`.
#[tokio::test]
async fn provided_values_are_not_overwritten_by_defaults() {
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();

    rt.execute_command(
        "defaults.items.create",
        &params(json!({ "name": "beta", "status": "done", "priority": 9 })),
        &ctx,
    )
    .await
    .unwrap();

    let rows =
        rt.execute_query("defaults.items.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(rows[0]["status"], json!("done"), "el valor aportado se respeta");
    assert_eq!(rows[0]["priority"], json!(9), "el valor aportado se respeta");
}

/// Decisión documentada: un `null` EXPLÍCITO es un valor presente, NO una ausencia → NO se
/// rellena con el default. Como aquí la columna es `NOT NULL` y el SQL no lleva COALESCE,
/// el `null` explícito llega a la BD y peta — confirmando que el binder no lo tocó.
#[tokio::test]
async fn explicit_null_is_respected_not_defaulted() {
    let rt = fresh_runtime().await;
    let ctx = admin_ctx();

    let res = rt
        .execute_command(
            "defaults.items.create",
            &params(json!({ "name": "gamma", "status": null, "priority": 1 })),
            &ctx,
        )
        .await;

    assert!(
        res.is_err(),
        "un null explícito NO se sustituye por el default; llega a la columna NOT NULL y peta"
    );
}
