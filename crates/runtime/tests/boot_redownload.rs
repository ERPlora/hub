//! Contrato de auto-curación del Hub Cloud **stateless** (cache `module_cache` efímero en `/tmp`,
//! borrado en cada redeploy/reschedule): tras un reinicio con el cache vacío, `rehydrate_installed`
//! no puede re-registrar los módulos (sus carpetas no existen), así que el hub debe saber cuáles
//! **re-descargar** del marketplace. `installed_but_unregistered` devuelve exactamente esos: los que
//! `hub_module` marca instalados pero no están en el registro.

use std::fs;
use std::path::{Path, PathBuf};

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::Runtime;
use serde_json::json;

fn write_module(root: &Path, id: &str) -> PathBuf {
    let dir = root.join(id);
    fs::create_dir_all(&dir).unwrap();
    fs::write(
        dir.join("module.json"),
        format!(r#"{{"id":"{id}","name":"{id}","version":"1.0.0"}}"#),
    )
    .unwrap();
    dir
}

#[tokio::test]
async fn lists_installed_modules_missing_from_registry() {
    let tmp = std::env::temp_dir().join(format!("erplora-redl-{}", std::process::id()));
    let _ = fs::remove_dir_all(&tmp);
    let alpha = write_module(&tmp, "alpha");

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    rt.install_from_dir(&alpha).await.unwrap(); // alpha: en hub_module Y en el registro

    // Todo lo instalado está registrado → nada que re-descargar.
    assert!(rt.installed_but_unregistered().await.unwrap().is_empty());

    // Simula "instalado según hub_module pero SIN carpeta de caché" (cache efímero borrado tras un
    // redeploy): una fila fantasma en hub_module que el registro no conoce.
    let hub_id = rt.hub_id().to_string();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("module_id".into(), json!("ghost"));
    p.insert("version".into(), json!("2.5.0"));
    p.insert("now".into(), json!("2026-07-09T00:00:00Z"));
    rt.db_for_test()
        .execute(
            "INSERT INTO hub_module (hub_id, module_id, version, status, installed_at, updated_at) \
             VALUES (:hub_id, :module_id, :version, 'active', :now, :now)",
            &p,
        )
        .await
        .unwrap();

    // ghost hay que re-descargarlo; alpha (registrado) NO aparece.
    let missing = rt.installed_but_unregistered().await.unwrap();
    assert_eq!(missing, vec![("ghost".to_string(), "2.5.0".to_string())]);

    let _ = fs::remove_dir_all(&tmp);
}
