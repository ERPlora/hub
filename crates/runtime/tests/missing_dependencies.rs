//! Instalación anidada (nested install): el Runtime sabe qué dependencias declaradas de un
//! módulo aún NO están instaladas, para que el flujo de instalación desde el Cloud
//! (`server::install::install_from_cloud`) descargue e instale esas deps ANTES del módulo que
//! las declara. Replica para el camino "descarga marketplace" el topo-orden que
//! `install_all_from_dir` ya hace para los módulos horneados (hub#16).
//!
//! Bug reproducido en vivo (2026-07-08): instalar `reservations` (depends_on `tables`,`customers`)
//! en un hub fresco devolvía 502 `MissingDependency`; instalar las hojas primero y luego el
//! dependiente funcionaba. La causa era que el Hub no ordenaba/descargaba `depends_on` en el
//! camino Cloud.
use std::fs;
use std::path::{Path, PathBuf};

use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use serde_json::json;

/// Escribe un `module.json` mínimo (id/name/version + depends_on) en `<root>/<id>/`.
fn write_module(root: &Path, id: &str, deps: &[&str]) -> PathBuf {
    let dir = root.join(id);
    fs::create_dir_all(&dir).unwrap();
    let manifest = json!({ "id": id, "name": id, "version": "1.0.0", "depends_on": deps });
    fs::write(
        dir.join("module.json"),
        serde_json::to_string(&manifest).unwrap(),
    )
    .unwrap();
    dir
}

#[tokio::test]
async fn missing_dependencies_lists_only_uninstalled_declared_deps() {
    let tmp = std::env::temp_dir().join(format!("erplora-missdeps-{}", std::process::id()));
    let _ = fs::remove_dir_all(&tmp);
    let leaf = write_module(&tmp, "leaf", &[]);
    let dependent = write_module(&tmp, "dependent", &["leaf", "absent"]);

    let mut rt = Runtime::new(Box::new(fresh_db().await));

    // Nada instalado → ambas deps declaradas faltan, en el orden del manifest.
    let missing = rt.missing_dependencies(&dependent).unwrap();
    assert_eq!(missing, vec!["leaf".to_string(), "absent".to_string()]);

    // Instala la hoja → deja de aparecer como faltante; la dep inexistente sigue faltando.
    rt.install_from_dir(&leaf).await.unwrap();
    let missing = rt.missing_dependencies(&dependent).unwrap();
    assert_eq!(missing, vec!["absent".to_string()]);

    // Un módulo sin deps declaradas nunca reporta faltantes.
    assert!(rt.missing_dependencies(&leaf).unwrap().is_empty());

    let _ = fs::remove_dir_all(&tmp);
}
