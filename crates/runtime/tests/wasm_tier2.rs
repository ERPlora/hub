//! Tests del Tier 2 (handlers WASM). ARQUITECTURA.md §5.3, §9.2.
//!
//! Cobertura sin necesidad de compilar un guest real:
//!  - `installer` carga los bytes del `.wasm` declarado por un command y los
//!    guarda en el `RegisteredCommand` (fixture con bytes dummy).
//!  - la validación de intenciones (mismo módulo / command desconocido / otro
//!    módulo) está cubierta por los tests unitarios de `commands::validate_operation`.
//!
//! El round-trip E2E real —handler compilado a wasm32 que devuelve N operaciones y el host las
//! ejecuta— vive en `kernel_conformance_guest_wasm.rs` (hub#1238), contra el `.wasm` COMMITEADO en
//! `tests/fixtures/kernel-fixture/`. Aquí vivía como `real_guest_bulk_create`, `#[ignore]` desde que
//! existe y con la receta de compilación en un comentario: un contrato que nadie ejecuta es un
//! contrato que nadie mantiene, así que se ha ido con su fixture de 4 bytes dummy.
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;

fn notes_fixture() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_notes")
}

#[tokio::test]
async fn installer_loads_wasm_bytes_into_registry() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let id = rt.install_from_dir(&notes_fixture()).await.unwrap();
    assert_eq!(id, "notes");

    // El command con handler tiene bytes wasm cargados; el SQL-only no.
    let bulk = rt
        .registry()
        .commands
        .get("notes.bulk")
        .expect("notes.bulk registrado");
    let bytes = bulk
        .wasm
        .as_ref()
        .expect("notes.bulk debe tener bytes wasm cargados");
    assert!(!bytes.is_empty());
    assert_eq!(&bytes[..4], b"\xde\xad\xbe\xef");

    let create = rt
        .registry()
        .commands
        .get("notes.create")
        .expect("notes.create registrado");
    assert!(
        create.wasm.is_none(),
        "command SQL-only no debe tener bytes wasm"
    );
}
