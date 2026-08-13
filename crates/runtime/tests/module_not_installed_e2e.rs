//! `module_not_installed` ≠ `query_not_found` (ADR-0127, `queryOptional`).
//!
//! El SDK necesita distinguir dos ausencias que hoy comparten error:
//!  * el MÓDULO dueño no está instalado → `queryOptional` devuelve `undefined` (integración
//!    opcional inactiva: `sales` consulta `verifactu` solo si el hub lo tiene);
//!  * el módulo SÍ está y la query NO existe → CONTRATO ROTO → error de verdad.
//!
//! Sin esta distinción, `queryOptional` tendría que tragarse también los contratos rotos —
//! y sería el mismo `.catch(() => [])` silencioso que estamos matando.

use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{RequestContext, Runtime, RuntimeError};

fn mdir(name: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(name)
}
fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

async fn hub_with_taxes() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&mdir("taxes")).await.unwrap();
    rt
}

#[tokio::test]
async fn query_de_un_modulo_no_instalado_es_module_not_installed() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let rt = hub_with_taxes().await;
    let err = rt
        .execute_query_page("verifactu.records.by_invoice", &Params::new(), &admin())
        .await
        .expect_err("verifactu no está instalado");
    assert!(
        matches!(err, RuntimeError::ModuleNotInstalled { ref module, .. } if module == "verifactu"),
        "esperaba ModuleNotInstalled, fue: {err:?}"
    );
}

#[tokio::test]
async fn query_inexistente_de_un_modulo_instalado_sigue_siendo_query_not_found() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let rt = hub_with_taxes().await;
    let err = rt
        .execute_query_page("taxes.rates.list", &Params::new(), &admin()) // rates: retirado por ADR-0085
        .await
        .expect_err("taxes está instalado pero esa query no existe");
    assert!(
        matches!(err, RuntimeError::QueryNotFound(_)),
        "un contrato roto contra un módulo PRESENTE no puede disfrazarse de ausencia: {err:?}"
    );
}
