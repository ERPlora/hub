//! Regresión ERPlora/saas#616 (fleco 1): un `HUB_MODULES_DIR` ausente NO debe abortar el arranque.
//!
//! En el despliegue demo (contenedor stateless) `HUB_MODULES_DIR=/tmp/modules` apunta a una ruta que
//! NO existe al arrancar (los módulos no vienen horneados; se instalan desde el marketplace en
//! runtime). `install_all_from_dir` debe tratar un dir ausente como "no hay módulos que instalar"
//! (lote vacío), en vez de propagar `io: No such file or directory (os error 2)` — que ensuciaba
//! TODOS los logs de arranque del hub demo (`✗ instalación de módulos: …`).
use erplora_db::SqliteAdapter;
use erplora_runtime::Runtime;

#[tokio::test]
async fn install_all_from_missing_dir_is_ok_empty() {
    let db = SqliteAdapter::open_in_memory().await.expect("sqlite en memoria");
    let mut rt = Runtime::new(Box::new(db));

    // Ruta que garantizadamente NO existe (nunca se crea). No debe ser un error.
    let missing = std::env::temp_dir().join("erplora-616-modules-dir-inexistente-jamas-creado");
    assert!(!missing.exists(), "precondición: el dir de módulos no debe existir");

    let installed = rt
        .install_all_from_dir(&missing)
        .await
        .expect("un dir de módulos ausente no debe abortar el arranque del hub");
    assert!(installed.is_empty(), "sin dir de módulos → cero módulos instalados");
}
