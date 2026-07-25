//! El bloque `seed` del manifest se APLICA al instalar el módulo.
//!
//! Estaba declarado en `taxes` desde ADR-0085 —categorías fiscales canónicas y reglas de IVA de
//! España— y **no lo ejecutaba nadie**: ni `module.schema.json` lo declaraba, ni había una línea de
//! Rust que lo leyera. `Runtime::apply_seed` existía como método público, pero el instalador nunca
//! lo llamaba con el bloque del manifest.
//!
//! Es la cuarta facilidad de la misma clase que aparece en el proyecto (las `reads` de ADR-0069, el
//! `Qty` del SDK, `printer_name`): escrita, y sin cablear.
//!
//! Contrato: DML **idempotente por hub**, aplicado tras migrar, con `:hub_id`/`:now`/
//! `:current_user_id` inyectados. Reinstalar no duplica.
//!
//! Ojo con el `hub_id` al montar el test: la semilla se escribe con el del RUNTIME
//! (`Runtime::new` usa `DEV_HUB_ID`), así que hay que construirlo con `with_hub_id` para que
//! coincida con el del `RequestContext` de la consulta. Si no, la semilla entra en un hub y se
//! consulta en otro, y parece que no se sembró nada.

use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{RequestContext, Runtime};

fn mdir(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules").join(name)
}
fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

#[tokio::test]
async fn instalar_taxes_siembra_sus_categorias_fiscales() {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&mdir("taxes")).await.expect("instalar taxes");

    let cats = rt
        .execute_query("taxes.categories.list", &Params::new(), &admin())
        .await
        .expect("la query de categorías existe");

    assert!(
        !cats.is_empty(),
        "instalar `taxes` tiene que dejar sembradas sus categorías canónicas: {cats:?}"
    );
    assert!(
        cats.iter().any(|c| c["key"] == serde_json::json!("restaurant.food")),
        "falta la categoría canónica de restauración: {cats:?}"
    );
}

#[tokio::test]
async fn la_semilla_es_idempotente_reinstalar_no_duplica() {
    // El seed es DML re-ejecutable (WHERE NOT EXISTS por la clave natural). Si no lo fuera, una
    // reinstalación —o un reintento del instalador— dejaría el catálogo fiscal duplicado.
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&mdir("taxes")).await.expect("primera instalación");
    let antes = rt.execute_query("taxes.categories.list", &Params::new(), &admin()).await.unwrap();

    rt.install_from_dir(&mdir("taxes")).await.expect("reinstalar");
    let despues = rt.execute_query("taxes.categories.list", &Params::new(), &admin()).await.unwrap();

    assert_eq!(antes.len(), despues.len(), "reinstalar NO puede duplicar la semilla");
}

#[tokio::test]
async fn un_modulo_sin_bloque_seed_se_instala_igual() {
    // La inmensa mayoría de los módulos no siembra nada: la ausencia del bloque no es un error.
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&mdir("customers")).await.expect("instalar un módulo sin seed");
}
