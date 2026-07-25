//! Tests del Tier 2 (handlers WASM). ARQUITECTURA.md §5.3, §9.2.
//!
//! Cobertura sin necesidad de compilar un guest real:
//!  - `installer` carga los bytes del `.wasm` declarado por un command y los
//!    guarda en el `RegisteredCommand` (fixture con bytes dummy).
//!  - la validación de intenciones (mismo módulo / command desconocido / otro
//!    módulo) está cubierta por los tests unitarios de `commands::validate_operation`.
//!
//! El round-trip E2E real (handler que devuelve N operaciones `notes.create` →
//! N filas) requiere un guest Extism compilado a wasm32; queda `#[ignore]` con
//! instrucciones (ver `real_guest_bulk_create`).
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;

fn notes_fixture() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests").join("fixture_notes")
}

#[tokio::test]
async fn installer_loads_wasm_bytes_into_registry() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    let id = rt.install_from_dir(&notes_fixture()).await.unwrap();
    assert_eq!(id, "notes");

    // El command con handler tiene bytes wasm cargados; el SQL-only no.
    let bulk = rt.registry().commands.get("notes.bulk").expect("notes.bulk registrado");
    let bytes = bulk.wasm.as_ref().expect("notes.bulk debe tener bytes wasm cargados");
    assert!(!bytes.is_empty());
    assert_eq!(&bytes[..4], b"\xde\xad\xbe\xef");

    let create = rt.registry().commands.get("notes.create").expect("notes.create registrado");
    assert!(create.wasm.is_none(), "command SQL-only no debe tener bytes wasm");
}

/// Round-trip real Input→Output a través de un guest WASM compilado.
///
/// El fixture `handler.wasm` son bytes dummy (no es un módulo Extism válido), así
/// que ejecutar `notes.bulk` con él daría `RuntimeError::Wasm(Load…)`. Para el
/// E2E real se necesita un guest compilado:
/// ```text
/// # 1. Crea un guest crate (cdylib) que dependa de erplora-guest-sdk + extism-pdk,
/// #    exporte `handle` y devuelva, para input {items:[a,b,...]}, N operaciones
/// #    {kind:"sql", command:"notes.create", params:{body:<item>}}.
/// # 2. rustup target add wasm32-unknown-unknown
/// # 3. cargo build --target wasm32-unknown-unknown --release
/// # 4. Copia el .wasm sobre tests/fixture_notes/handler.wasm
/// # 5. cargo test -p erplora-runtime -- --ignored real_guest_bulk_create
/// ```
#[tokio::test]
#[ignore = "requires a real Extism guest .wasm at tests/fixture_notes/handler.wasm"]
async fn real_guest_bulk_create() {
    use erplora_db::Params;
    use erplora_runtime::RequestContext;
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&notes_fixture()).await.unwrap();
    let ctx = RequestContext::new("hub-1", "user-1", ["notes.write".to_string()]);
    let mut payload = Params::new();
    payload.insert("items".into(), serde_json::json!(["a", "b", "c"]));
    let out = rt.execute_command("notes.bulk", &payload, &ctx).await.expect("notes.bulk");
    assert_eq!(out["operations"], serde_json::json!(3));
}
