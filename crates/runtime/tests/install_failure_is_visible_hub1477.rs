//! **hub#1477** — un módulo que el hub recibió la orden de instalar y NO se instaló no puede ser
//! invisible.
//!
//! `install_all_from_dir` es tolerante a propósito (un módulo de terceros roto no debe brickear el
//! arranque), pero «tolerante» se había vuelto «mudo»: el fallo salía por un `eprintln!` y ahí
//! moría. Y el módulo tampoco llegaba a `hub_module`, que es la vara de medir de `/readyz`, así
//! que la sonda publicaba `missing: []` y el hub se daba por sano **sin** el módulo.
//!
//! El caso real que lo destapó: `verifactu` es el único de los 27 módulos publicados que declara
//! `static_files`, el instalador materializa esa carpeta contra el backend del host, y el backend
//! del Cloud sin token de máquina falla. Resultado: un hub servía **sin el módulo fiscal** y decía
//! `UP`. Aquí se fija el contrato: **lo que no se pudo instalar queda registrado**.

use std::sync::Arc;

use erplora_db::testutil::fresh_db;
use erplora_runtime::module_storage::ModuleStorage;
use erplora_runtime::{Result, Runtime, RuntimeError};

/// El backend que el server inyecta en Cloud cuando NO hay token de máquina: rechaza.
#[derive(Debug)]
struct RefusingStorage;

#[async_trait::async_trait]
impl ModuleStorage for RefusingStorage {
    async fn ensure_module_folder(&self, _hub_id: &str, _folder: &str) -> Result<()> {
        Err(RuntimeError::Storage(
            "Hub Cloud sin token de máquina".to_string(),
        ))
    }

    async fn write_module_file(
        &self,
        _hub_id: &str,
        _folder: &str,
        _relative_path: &str,
        _bytes: &[u8],
        _content_type: &str,
    ) -> Result<String> {
        unreachable!("este test solo provisiona la carpeta")
    }
}

/// Un árbol de módulos: `(id, fragmento extra del manifest)`.
fn modules_dir(tag: &str, modules: &[(&str, &str)]) -> std::path::PathBuf {
    let root = std::env::temp_dir().join(format!("erplora-hub1477-{tag}-{}", uuid::Uuid::new_v4()));
    for (id, extra) in modules {
        let dir = root.join(id);
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(
            dir.join("module.json"),
            format!(r#"{{"id":"{id}","name":"{id}","version":"1.0.0"{extra}}}"#),
        )
        .unwrap();
    }
    root
}

async fn runtime_with(storage: Arc<dyn ModuleStorage>) -> Runtime {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-1477");
    runtime.ensure_system_tables().await.unwrap();
    runtime.set_module_storage(storage);
    runtime
}

const STATIC_FILES: &str = r#","static_files":{"folder":"archive"}"#;

/// **El corazón de la issue.** El lote sigue siendo tolerante —`plain` entra, el arranque no se
/// cae— pero lo que se quedó fuera queda ANOTADO, con su id y su motivo.
#[tokio::test]
async fn install_all_from_dir_records_every_module_it_could_not_install() {
    let root = modules_dir("records", &[("plain", ""), ("archive", STATIC_FILES)]);
    let mut runtime = runtime_with(Arc::new(RefusingStorage)).await;

    let installed = runtime.install_all_from_dir(&root).await.unwrap();

    // Tolerante: lo que se pudo instalar, se instaló.
    assert_eq!(installed, vec!["plain".to_string()]);
    // Y lo que NO, ya no es un silencio.
    let failed = &runtime.registry().failed_installs;
    assert_eq!(failed.len(), 1, "se esperaba UN fallo anotado: {failed:?}");
    assert_eq!(failed[0].module_id, "archive");
    assert!(
        failed[0].reason.contains("sin token de máquina"),
        "el motivo tiene que decir POR QUÉ, no solo que falló: {}",
        failed[0].reason
    );
    assert!(
        failed[0].source.contains("archive"),
        "hace falta saber QUÉ paquete era: {}",
        failed[0].source
    );

    std::fs::remove_dir_all(root).unwrap();
}

/// Un manifest que ni siquiera carga también se anota: es un módulo que se pidió instalar y no
/// está. Sin id legible, el nombre de la carpeta es lo único que hay — y es lo que el operador ve.
#[tokio::test]
async fn a_manifest_that_does_not_even_load_is_recorded_too() {
    let root = modules_dir("badmanifest", &[("plain", "")]);
    let broken = root.join("broken");
    std::fs::create_dir_all(&broken).unwrap();
    std::fs::write(broken.join("module.json"), "{ no soy json").unwrap();
    let mut runtime = runtime_with(Arc::new(RefusingStorage)).await;

    runtime.install_all_from_dir(&root).await.unwrap();

    let failed = &runtime.registry().failed_installs;
    assert_eq!(failed.len(), 1, "{failed:?}");
    assert_eq!(failed[0].module_id, "broken");

    std::fs::remove_dir_all(root).unwrap();
}

/// Un lote limpio no anota nada: la lista es «lo que falta», no un historial.
#[tokio::test]
async fn a_batch_that_installs_cleanly_records_nothing() {
    let root = modules_dir("clean", &[("plain", ""), ("other", "")]);
    let mut runtime = runtime_with(Arc::new(RefusingStorage)).await;

    runtime.install_all_from_dir(&root).await.unwrap();

    assert!(
        runtime.registry().failed_installs.is_empty(),
        "{:?}",
        runtime.registry().failed_installs
    );

    std::fs::remove_dir_all(root).unwrap();
}

/// **La lista describe el intento ACTUAL, no acumula.** Si no, un módulo que se arregló entre dos
/// pasadas seguiría denunciado para siempre y `/readyz` no volvería a ponerse verde nunca.
#[tokio::test]
async fn a_second_pass_replaces_the_previous_verdict_instead_of_piling_up() {
    let root = modules_dir("retry", &[("archive", STATIC_FILES)]);
    let mut runtime = runtime_with(Arc::new(RefusingStorage)).await;

    runtime.install_all_from_dir(&root).await.unwrap();
    assert_eq!(runtime.registry().failed_installs.len(), 1);

    // Segunda pasada con un backend que sí materializa: el veredicto anterior se retira.
    runtime.set_module_storage(Arc::new(AcceptingStorage));
    let installed = runtime.install_all_from_dir(&root).await.unwrap();

    assert_eq!(installed, vec!["archive".to_string()]);
    assert!(
        runtime.registry().failed_installs.is_empty(),
        "un fallo ya resuelto no puede seguir en la lista: {:?}",
        runtime.registry().failed_installs
    );

    std::fs::remove_dir_all(root).unwrap();
}

#[derive(Debug)]
struct AcceptingStorage;

#[async_trait::async_trait]
impl ModuleStorage for AcceptingStorage {
    async fn ensure_module_folder(&self, _hub_id: &str, _folder: &str) -> Result<()> {
        Ok(())
    }

    async fn write_module_file(
        &self,
        _hub_id: &str,
        _folder: &str,
        _relative_path: &str,
        _bytes: &[u8],
        _content_type: &str,
    ) -> Result<String> {
        unreachable!("este test solo provisiona la carpeta")
    }
}
