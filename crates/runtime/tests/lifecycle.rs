//! Ciclo de vida de módulos (hot-plug): install → deactivate → activate → uninstall.
//! Verifica que el menú y las capacidades solo se exponen cuando el módulo está ACTIVO.
use std::path::PathBuf;

use erplora_db::{Params, SqliteAdapter};
use erplora_runtime::{ModuleStatus, RequestContext, Runtime, RuntimeError};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_inventory")
}
fn ctx() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

#[tokio::test]
async fn install_activates_and_exposes() {
    let mut rt = Runtime::new(Box::new(SqliteAdapter::open_in_memory().await.unwrap()));
    rt.install_from_dir(&fixture()).await.unwrap();

    // recién instalado → activo, con menú y query disponible
    let mods = rt.modules();
    assert_eq!(mods.len(), 1);
    assert_eq!(mods[0].id, "inventory");
    assert_eq!(mods[0].status, ModuleStatus::Active);
    assert_eq!(rt.navigation().len(), 1);
    assert!(rt.execute_query("inventory.products.list", &Params::new(), &ctx()).await.is_ok());
}

#[tokio::test]
async fn deactivate_hides_menu_and_blocks_capabilities() {
    let mut rt = Runtime::new(Box::new(SqliteAdapter::open_in_memory().await.unwrap()));
    rt.install_from_dir(&fixture()).await.unwrap();

    rt.deactivate("inventory").await.unwrap();

    // inactivo → sin menú, query/command devuelven NotFound (no existen para el caller)
    assert_eq!(rt.modules()[0].status, ModuleStatus::Inactive);
    assert_eq!(rt.navigation().len(), 0, "el menú no debe mostrar módulos inactivos");
    // Desactivado ≠ desinstalado: el módulo SIGUE en el hub (sus datos y su manifest están), solo
    // que inactivo — así que la query "no se encuentra", no "el módulo no está instalado".
    assert!(matches!(
        rt.execute_query("inventory.products.list", &Params::new(), &ctx()).await.unwrap_err(),
        RuntimeError::QueryNotFound(_)
    ));
    assert!(matches!(
        rt.execute_command("inventory.products.create", &params(json!({"name":"X","sku":"X","price":1,"stock":1})), &ctx()).await.unwrap_err(),
        RuntimeError::CommandNotFound(_)
    ));

    // reactivar → vuelve a estar disponible
    rt.activate("inventory").await.unwrap();
    assert_eq!(rt.navigation().len(), 1);
    assert!(rt.execute_query("inventory.products.list", &Params::new(), &ctx()).await.is_ok());
}

#[tokio::test]
async fn data_survives_deactivation() {
    let mut rt = Runtime::new(Box::new(SqliteAdapter::open_in_memory().await.unwrap()));
    rt.install_from_dir(&fixture()).await.unwrap();
    rt.execute_command("inventory.products.create",
        &params(json!({"name":"Café","sku":"CAF","price":4.5,"stock":7})), &ctx()).await.unwrap();

    rt.deactivate("inventory").await.unwrap();
    rt.activate("inventory").await.unwrap();

    // los datos creados antes de desactivar siguen ahí tras reactivar
    let rows = rt.execute_query("inventory.products.list", &Params::new(), &ctx()).await.unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0]["name"], json!("Café"));
}

#[tokio::test]
async fn uninstall_removes_module() {
    let mut rt = Runtime::new(Box::new(SqliteAdapter::open_in_memory().await.unwrap()));
    rt.install_from_dir(&fixture()).await.unwrap();
    rt.uninstall("inventory").await.unwrap();

    assert_eq!(rt.modules().len(), 0);
    assert_eq!(rt.navigation().len(), 0);
    // Tras desinstalar, el dueño de la query YA NO ESTÁ: el error correcto es la AUSENCIA del
    // módulo (ADR-0127 — es lo que permite a `queryOptional` distinguirla de un contrato roto),
    // no un `QueryNotFound` genérico.
    assert!(matches!(
        rt.execute_query("inventory.products.list", &Params::new(), &ctx()).await.unwrap_err(),
        RuntimeError::ModuleNotInstalled { .. }
    ));
}

#[tokio::test]
async fn status_persisted_in_hub_module_table() {
    // misma BD compartida: instalar/desactivar deja rastro en hub_module
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    // probamos vía un segundo adapter NO es posible (in-memory es por conexión);
    // así que consultamos a través del propio runtime tras desactivar.
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture()).await.unwrap();
    rt.deactivate("inventory").await.unwrap();
    // el módulo sigue instalado (aparece en modules()) aunque inactivo
    assert_eq!(rt.modules()[0].status, ModuleStatus::Inactive);
}
