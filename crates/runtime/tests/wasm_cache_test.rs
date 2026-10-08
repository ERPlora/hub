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
fn contador() -> (
    Arc<AtomicUsize>,
    impl Fn() -> Result<CompiledModule, erplora_runtime::errors::RuntimeError> + Clone,
) {
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

    cache
        .get_or_compile_with(key("sales", "2.14.1"), compilar.clone())
        .unwrap();
    cache
        .get_or_compile_with(key("sales", "2.15.0"), compilar.clone())
        .unwrap();

    assert_eq!(
        veces.load(Ordering::SeqCst),
        2,
        "otra versión, otra compilación"
    );
    assert_eq!(cache.len(), 2);
}

#[test]
fn modulos_distintos_no_se_pisan() {
    let cache = WasmCache::default();
    let (veces, compilar) = contador();

    cache
        .get_or_compile_with(key("sales", "1.0.0"), compilar.clone())
        .unwrap();
    cache
        .get_or_compile_with(key("invoice", "1.0.0"), compilar.clone())
        .unwrap();

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

    cache
        .get_or_compile_with(key("sales", "2.14.1"), compilar.clone())
        .unwrap();
    cache
        .get_or_compile_with(key("invoice", "1.0.0"), compilar.clone())
        .unwrap();
    cache.forget_module("sales");

    assert_eq!(cache.len(), 1, "solo sobrevive el módulo que no se tocó");

    cache
        .get_or_compile_with(key("sales", "2.14.1"), compilar.clone())
        .unwrap();
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

    assert!(cache
        .get_or_compile_with(key("sales", "2.14.1"), roto)
        .is_err());
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
        assert_eq!(
            cache.len(),
            0,
            "la caché es consultable mientras se compila"
        );
        CompiledModule::compile(&bytes, WasmLimits::default())
            .map_err(|e| erplora_runtime::errors::RuntimeError::Wasm(e.to_string()))
    });

    assert!(resultado.is_ok());
    assert_eq!(cache.len(), 1);
}

// ─── Precalentado al arrancar (hub#926, segunda mitad) ────────────────────────────────────────
//
// Medido en HARDWARE DE PRODUCCIÓN (amd64, imagen que corre la flota, 512 MiB / 0,25 vCPU): tras
// un DEPLOY —que estrena contenedor y por tanto vacía la caché en disco de wasmtime— las dos
// primeras ventas costaron **8,2 s y 5,7 s**, y de la tercera en adelante 75-91 ms. Ese es el
// «tarda una eternidad» del incidente saas#1460 visto de cerca: no es cada venta, es la PRIMERA
// después de cada despliegue, y la paga el cajero que tenga un cliente delante.
//
// La compilación hay que hacerla igual; lo que se puede elegir es CUÁNDO. Precalentar al arrancar
// la mueve al hueco en que nadie está esperando.

use erplora_runtime::wasm_cache::warm_up;

/// Un `Registry` de mentira: lo que el precalentado necesita saber es qué módulos tienen handler.
fn modulo(id: &str, version: &str, con_handler: bool) -> (String, String, Option<Vec<u8>>) {
    (
        id.to_string(),
        version.to_string(),
        con_handler.then(wasm_vacio),
    )
}

#[test]
fn precalentar_compila_los_handlers_instalados() {
    let cache = WasmCache::default();
    let modulos = vec![
        modulo("sales", "2.14.1", true),
        modulo("invoice", "1.2.0", true),
    ];

    let calentados = warm_up(&cache, &modulos, WasmLimits::default());

    assert_eq!(calentados, 2, "los dos handlers quedan compilados");
    assert_eq!(cache.len(), 2);
}

#[test]
fn precalentar_ignora_los_modulos_sin_handler() {
    // Un módulo declarativo (Tier 0) no tiene nada que compilar: ni entra en la caché ni cuenta.
    let cache = WasmCache::default();
    let modulos = vec![
        modulo("sales", "2.14.1", true),
        modulo("printing", "1.0.0", false),
    ];

    assert_eq!(warm_up(&cache, &modulos, WasmLimits::default()), 1);
    assert_eq!(cache.len(), 1);
}

#[test]
fn un_handler_roto_no_impide_calentar_los_demas() {
    // Arrancar es lo único que no puede fallar: si un módulo trae bytes corruptos, se salta y el
    // hub sigue en pie — ese comando fallará cuando alguien lo llame, con su error, no antes.
    let cache = WasmCache::default();
    let modulos = vec![
        (
            "roto".to_string(),
            "1.0.0".to_string(),
            Some(vec![0u8, 1, 2, 3]),
        ),
        modulo("sales", "2.14.1", true),
    ];

    assert_eq!(
        warm_up(&cache, &modulos, WasmLimits::default()),
        1,
        "solo cuenta el que compiló"
    );
    assert_eq!(cache.len(), 1);
}

#[test]
fn precalentar_dos_veces_no_recompila() {
    let cache = WasmCache::default();
    let modulos = vec![modulo("sales", "2.14.1", true)];

    warm_up(&cache, &modulos, WasmLimits::default());
    warm_up(&cache, &modulos, WasmLimits::default());

    assert_eq!(
        cache.len(),
        1,
        "la segunda pasada encuentra la caché caliente"
    );
}

/// Qué handlers hay que precalentar: uno por MÓDULO, no uno por comando.
///
/// El registro guarda los bytes del `.wasm` en cada comando, y un módulo declara varios comandos
/// contra el mismo handler. Sin deduplicar, `sales` (21 comandos) se compilaría 21 veces al
/// arrancar — el precalentado costaría más que el problema que quita.
#[test]
fn los_handlers_a_precalentar_van_uno_por_modulo() {
    use erplora_runtime::manifest::{CommandDef, Manifest};
    use erplora_runtime::registry::{RegisteredCommand, Registry};
    use serde_json::json;

    let cmd_def = |permission: &str| -> CommandDef {
        serde_json::from_value(json!({ "permission": permission })).expect("CommandDef de prueba")
    };
    let manifest = |id: &str, version: &str| -> Manifest {
        serde_json::from_value(json!({ "id": id, "name": id, "version": version }))
            .expect("Manifest de prueba")
    };

    let mut registry = Registry::default();
    let bytes = wasm_vacio();
    for (name, module) in [
        ("sales.complete_sale", "sales"),
        ("sales.void", "sales"),
        ("invoice.create", "invoice"),
    ] {
        registry.commands.insert(
            name.to_string(),
            RegisteredCommand {
                module_id: module.to_string(),
                def: cmd_def("sales.take_payment"),
                sql: vec![],
                wasm: Some(bytes.clone()),
                schema: None,
            },
        );
    }
    // Un comando declarativo (Tier 0) no aporta nada que compilar.
    registry.commands.insert(
        "printing.job.enqueue".to_string(),
        RegisteredCommand {
            module_id: "printing".to_string(),
            def: cmd_def("printing.enqueue"),
            sql: vec!["INSERT INTO printing_job DEFAULT VALUES".to_string()],
            wasm: None,
            schema: None,
        },
    );
    for (id, version) in [
        ("sales", "2.14.1"),
        ("invoice", "1.2.0"),
        ("printing", "1.0.0"),
    ] {
        registry.installed.push(manifest(id, version));
    }

    let mut a_calentar = registry.handlers_to_warm_up();
    a_calentar.sort_by(|a, b| a.0.cmp(&b.0));

    let ids: Vec<&str> = a_calentar.iter().map(|(id, _, _)| id.as_str()).collect();
    assert_eq!(ids, vec!["invoice", "sales"], "un módulo, una compilación");
    let versiones: Vec<&str> = a_calentar.iter().map(|(_, v, _)| v.as_str()).collect();
    assert_eq!(
        versiones,
        vec!["1.2.0", "2.14.1"],
        "cada uno con SU versión instalada"
    );
    assert!(a_calentar.iter().all(|(_, _, w)| w.is_some()));
}

/// The line the boot warm-up prints when it is over (hub#2693).
///
/// `/readyz` says UP BEFORE the handlers are compiled — on purpose (hub#926): in production
/// nobody waits for the warm-up. But whoever needs a WARM hub (the CI that runs the module
/// batteries against a real server, `scripts/ci/run-module-hub-batteries.sh`) has nothing else
/// to wait for: on a fresh runner the first sale raced Cranelift and `cash_register`'s battery
/// timed out in 2 of 3 runs. So the end of the warm-up is announced with a fixed, greppable line —
/// also when there was nothing to compile, or the waiter would sit until its timeout.
#[test]
fn the_warm_up_announces_its_end_with_a_fixed_line() {
    use erplora_runtime::wasm_cache::{warm_up_report, WARM_UP_DONE};

    let cache = WasmCache::default();
    let line = warm_up_report(
        &cache,
        &[
            modulo("sales", "2.14.1", true),
            modulo("invoice", "1.2.0", true),
        ],
        WasmLimits::default(),
    );
    assert!(
        line.starts_with(WARM_UP_DONE),
        "the line starts with the marker: {line}"
    );
    assert!(line.contains("2/2"), "and says how many compiled: {line}");
    assert_eq!(
        cache.len(),
        2,
        "the report IS the warm-up, not a description of it"
    );
}

#[test]
fn the_warm_up_announces_its_end_even_with_nothing_to_compile() {
    use erplora_runtime::wasm_cache::{warm_up_report, WARM_UP_DONE};

    let line = warm_up_report(&WasmCache::default(), &[], WasmLimits::default());
    assert!(
        line.starts_with(WARM_UP_DONE),
        "a hub without handlers is warm too: {line}"
    );
    assert!(line.contains("0/0"), "{line}");
}

#[test]
fn a_broken_handler_still_ends_the_warm_up() {
    use erplora_runtime::wasm_cache::{warm_up_report, WARM_UP_DONE};

    let line = warm_up_report(
        &WasmCache::default(),
        &[
            (
                "broken".to_string(),
                "1.0.0".to_string(),
                Some(vec![0u8, 1, 2, 3]),
            ),
            modulo("sales", "2.14.1", true),
        ],
        WasmLimits::default(),
    );
    assert!(line.starts_with(WARM_UP_DONE), "{line}");
    assert!(
        line.contains("1/2"),
        "only the one that compiled counts: {line}"
    );
}
