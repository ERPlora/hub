//! `module_not_installed` ≠ `query_not_found`/`command_not_found` (ADR-0127, `queryOptional`;
//! hub#1428, `commandOptional`).
//!
//! El SDK necesita distinguir dos ausencias que hoy comparten error:
//!  * el MÓDULO dueño no está instalado → `queryOptional`/`commandOptional` devuelven `undefined`
//!    (integración opcional inactiva: `sales` consulta `verifactu` solo si el hub lo tiene);
//!  * el módulo SÍ está y la query/command NO existe → CONTRATO ROTO → error de verdad.
//!
//! Sin esta distinción, `queryOptional`/`commandOptional` tendrían que tragarse también los
//! contratos rotos — y sería el mismo `.catch(() => [])` silencioso que estamos matando.

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
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
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
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
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
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

/// hub#1428: el mismo criterio de `query_de_un_modulo_no_instalado_es_module_not_installed`,
/// pero para la puerta de ESCRITURA — hasta este fix, `execute_at` (`commands.rs`) nunca miraba
/// si el módulo dueño estaba instalado y devolvía `CommandNotFound` para las dos ausencias por
/// igual, lo que habría dejado a `commandOptional` sin nada que perdonar (SIEMPRE explotaría).
#[tokio::test]
async fn command_de_un_modulo_no_instalado_es_module_not_installed() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = hub_with_taxes().await;
    let err = rt
        .execute_command("verifactu.config_save", &Params::new(), &admin())
        .await
        .expect_err("verifactu no está instalado");
    assert!(
        matches!(err, RuntimeError::ModuleNotInstalled { ref module, .. } if module == "verifactu"),
        "esperaba ModuleNotInstalled, fue: {err:?}"
    );
}

#[tokio::test]
async fn command_inexistente_de_un_modulo_instalado_sigue_siendo_command_not_found() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = hub_with_taxes().await;
    let err = rt
        .execute_command("taxes.rates.create", &Params::new(), &admin()) // rates: retirado por ADR-0085
        .await
        .expect_err("taxes está instalado pero ese command no existe");
    assert!(
        matches!(err, RuntimeError::CommandNotFound(_)),
        "un contrato roto contra un módulo PRESENTE no puede disfrazarse de ausencia: {err:?}"
    );
}

/// El namespace reservado del core (`hub.*`, ADR-0192) nunca es un módulo "ausente": un command
/// `hub.*` que no resuelve tiene que seguir siendo `CommandNotFound` (contrato roto), nunca
/// `ModuleNotInstalled` — igual que `queryOptional('hub.…')` nunca se traga la ausencia del
/// core (hub#1211, `CORE_NAMESPACE_OWNER` en el SDK). Hoy no existe ningún command `hub.*`
/// registrado (las escrituras del core van por rutas HTTP dedicadas, no por el dispatcher
/// declarativo), así que este es exactamente el camino que ejercita la excepción.
#[tokio::test]
async fn command_hub_namespace_inexistente_no_se_disfraza_de_modulo_ausente() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = hub_with_taxes().await;
    let err = rt
        .execute_command("hub.does_not_exist", &Params::new(), &admin())
        .await
        .expect_err("no hay ningún command hub.* registrado");
    assert!(
        matches!(err, RuntimeError::CommandNotFound(_)),
        "el namespace del core nunca está \"ausente\": {err:?}"
    );
}
