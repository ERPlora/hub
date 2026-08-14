//! La caché de código compilado de los handlers (hub#926).
//!
//! Lo que se prueba aquí es la promesa que justifica el cambio y las dos formas de romperla:
//!
//!  1. **compilar una sola vez** por versión de módulo — es el ahorro entero (en saas#1460 se
//!     midió que recompilar en cada comando fijaba el suelo de memoria del plan free en 512 MB y
//!     ponía la venta en 11 s a 0,1 vCPU);
//!  2. **no servir código viejo** tras actualizar un módulo — servir la versión anterior sería un
//!     fallo mucho peor que recompilar siempre;
//!  3. **no bloquear la caja** mientras se compila.

use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

use erplora_runtime::wasm_cache::{CacheKey, WasmCache};
use erplora_wasm_host::{CompiledModule, WasmLimits};

/// Un `.wasm` mínimo y válido: un módulo vacío. Compila de verdad (es lo que queremos contar) y
/// no ejecuta nada, que aquí no hace falta.
fn wasm_vacio() -> Vec<u8> {
    wat::parse_str("(module)").expect("compilar WAT de prueba")
}

fn key(module: &str, version: &str) -> CacheKey {
    CacheKey::new(module, version, WasmLimits::default())
}

/// El contador de compilaciones: lo que la caché tiene que reducir a uno.
fn contador() -> (Arc<AtomicUsize>, impl Fn() -> Result<CompiledModule, erplora_runtime::errors::RuntimeError> + Clone)
{
    let veces = Arc::new(AtomicUsize::new(0));
    let bytes = wasm_vacio();
    let contado = {
        let veces = veces.clone();
        move || {
            veces.fetch_add(1, Ordering::SeqCst);
            CompiledModule::compile(&bytes, WasmLimits::default())
                .map_err(|e| erplora_runtime::errors::RuntimeError::Wasm(e.to_string()))
        }
    };
    (veces, contado)
}

#[test]
fn compila_una_vez_por_mas_llamadas_que_haya() {
    let cache = WasmCache::default();
    let (veces, compilar) = contador();

    for _ in 0..5 {
        cache
            .get_or_compile_with(key("sales", "2.14.1"), compilar.clone())
            .expect("la caché debe entregar el módulo compilado");
    }

    assert_eq!(
        veces.load(Ordering::SeqCst),
        1,
        "cinco cobros del mismo módulo compilan UNA vez"
    );
    assert_eq!(cache.len(), 1);
}

#[test]
fn una_version_nueva_no_reutiliza_el_codigo_de_la_anterior() {
    // El fallo peligroso: tras actualizar el módulo, el hub ejecutaría lógica que ya no existe.
    let cache = WasmCache::default();
    let (veces, compilar) = contador();

    cache.get_or_compile_with(key("sales", "2.14.1"), compilar.clone()).unwrap();
    cache.get_or_compile_with(key("sales", "2.15.0"), compilar.clone()).unwrap();

    assert_eq!(veces.load(Ordering::SeqCst), 2, "otra versión, otra compilación");
    assert_eq!(cache.len(), 2);
}

#[test]
fn modulos_distintos_no_se_pisan() {
    let cache = WasmCache::default();
    let (veces, compilar) = contador();

    cache.get_or_compile_with(key("sales", "1.0.0"), compilar.clone()).unwrap();
    cache.get_or_compile_with(key("invoice", "1.0.0"), compilar.clone()).unwrap();

    assert_eq!(veces.load(Ordering::SeqCst), 2);
    assert_eq!(cache.len(), 2);
}

#[test]
fn desregistrar_un_modulo_tira_su_codigo_compilado() {
    // Toda actualización pasa por aquí (`Registry::remove_module`, hub#516). Es el cinturón que
    // cubre el caso que la versión no ve: un hub de desarrollo reinstalando la MISMA versión con
    // bytes distintos.
    let cache = WasmCache::default();
    let (veces, compilar) = contador();

    cache.get_or_compile_with(key("sales", "2.14.1"), compilar.clone()).unwrap();
    cache.get_or_compile_with(key("invoice", "1.0.0"), compilar.clone()).unwrap();
    cache.forget_module("sales");

    assert_eq!(cache.len(), 1, "solo sobrevive el módulo que no se tocó");

    cache.get_or_compile_with(key("sales", "2.14.1"), compilar.clone()).unwrap();
    assert_eq!(
        veces.load(Ordering::SeqCst),
        3,
        "tras desregistrarlo, el mismo módulo vuelve a compilarse"
    );
}

#[test]
fn un_fallo_de_compilacion_no_se_queda_cacheado() {
    // Si un módulo roto dejara una entrada, el hub serviría el fallo para siempre.
    let cache = WasmCache::default();
    let roto = || {
        Err(erplora_runtime::errors::RuntimeError::Wasm(
            "bytes corruptos".to_string(),
        ))
    };

    assert!(cache.get_or_compile_with(key("sales", "2.14.1"), roto).is_err());
    assert!(cache.is_empty(), "un fallo no deja entrada");

    let (_, compilar) = contador();
    assert!(cache
        .get_or_compile_with(key("sales", "2.14.1"), compilar)
        .is_ok());
    assert_eq!(cache.len(), 1, "y el reintento sí puede tener éxito");
}

#[test]
fn compilar_no_sostiene_el_candado() {
    // Si la caché sostuviera su candado mientras compila, todos los cobros del hub se
    // serializarían detrás de la compilación más lenta — justo lo que se viene a quitar. El test
    // lo comprueba llamando a la caché DESDE DENTRO de la compilación: con el candado tomado,
    // esto se quedaría clavado para siempre.
    let cache = WasmCache::default();
    let bytes = wasm_vacio();

    let resultado = cache.get_or_compile_with(key("sales", "2.14.1"), || {
        assert_eq!(cache.len(), 0, "la caché es consultable mientras se compila");
        CompiledModule::compile(&bytes, WasmLimits::default())
            .map_err(|e| erplora_runtime::errors::RuntimeError::Wasm(e.to_string()))
    });

    assert!(resultado.is_ok());
    assert_eq!(cache.len(), 1);
}
