//! # erplora-wasm-host
//!
//! Host del **Tier 2 (lógica WASM)** de ERPlora (ARQUITECTURA.md §5.3, §7.3,
//! §11). Carga y ejecuta handlers de módulo compilados a WebAssembly dentro de
//! un **sandbox** ([Extism] / wasmtime) y deserializa el contrato host↔guest
//! definido en [`erplora_guest_sdk`].
//!
//! Un handler WASM **NO** toca la base de datos: recibe un `Input` JSON y
//! devuelve un [`Output`] con **intenciones** (operaciones SQL por nombre de
//! command + params, y eventos). Este crate solo cubre **la ejecución sandbox y
//! la (de)serialización del contrato**. La validación de cada `Operation` contra
//! los commands permitidos y su ejecución en transacción la hace el *runtime*
//! del Hub, no este crate.
//!
//! ## API pública
//!
//! * [`WasmHost::from_bytes`] — carga un módulo WASM desde bytes.
//! * [`WasmHost::call`] — invoca una función exportada pasando un `Input` JSON y
//!   devuelve el [`Output`] deserializado.
//! * [`WasmError`] — `Load` / `Call` / `Decode`.
//!
//! ## Feature `extism` (activada por defecto)
//!
//! La ejecución real de WASM vive tras la feature **`extism`** (ON por defecto).
//! En este entorno `extism = "1"` (1.21, motor wasmtime) compila **sin** `cmake`
//! ni `llvm` externos, así que la ejecución real está activa.
//!
//! Si en algún entorno `extism` no compilara, se puede construir con
//! `--no-default-features`: entonces [`WasmHost::from_bytes`] y
//! [`WasmHost::call`] devuelven [`WasmError::Load`] explicando que la feature
//! está desactivada, y los **tests de contrato** (serde) siguen pasando. Así
//! `cargo test -p erplora-wasm-host` queda en verde con o sin runtime WASM.
//!
//! [Extism]: https://extism.org

use thiserror::Error;

pub use erplora_guest_sdk::{self as guest_sdk, Event, Input, Operation, Output};

/// Errores del host WASM.
#[derive(Debug, Error)]
pub enum WasmError {
    /// El módulo WASM no se pudo cargar/instanciar (bytes inválidos, ABI
    /// incompatible, o feature `extism` desactivada).
    #[error("failed to load wasm module: {0}")]
    Load(String),

    /// La llamada a la función exportada falló dentro del sandbox.
    #[error("wasm call to `{function}` failed: {reason}")]
    Call {
        /// Nombre de la función exportada que se intentó invocar.
        function: String,
        /// Causa subyacente (mensaje del runtime / del guest).
        reason: String,
    },

    /// El JSON intercambiado con el guest no se pudo (de)serializar.
    #[error("failed to decode wasm contract payload: {0}")]
    Decode(String),
}

impl WasmError {
    #[cfg_attr(not(feature = "extism"), allow(dead_code))]
    fn call(function: &str, reason: impl ToString) -> Self {
        WasmError::Call {
            function: function.to_string(),
            reason: reason.to_string(),
        }
    }
}

/// Páginas WASM (64 KiB cada una) que caben en 1 MiB.
///
/// 1 MiB / 64 KiB = 16 páginas ⇒ el tope de 32 MB son 512 páginas.
#[cfg_attr(not(feature = "extism"), allow(dead_code))]
const PAGES_PER_MB: u32 = 16;

/// Tope de memoria lineal por plugin WASM, en MB, cuando no se configura otra
/// cosa. Con 32 MB un handler glotón se queda dentro de su sandbox y **no**
/// dispara el OOM-killer del contenedor (que tumbaría el hub entero, hub#204).
#[cfg_attr(not(feature = "extism"), allow(dead_code))]
const DEFAULT_WASM_MEMORY_MAX_MB: u32 = 32;

/// Variable de entorno para sobreescribir [`DEFAULT_WASM_MEMORY_MAX_MB`].
///
/// **Importante:** `0` (o cualquier valor inválido) **no** significa «ilimitado»
/// — cae al default de 32 MB con un warning. Si algún día hiciera falta memoria
/// «sin tope», se configura un valor explícito enorme (p. ej. `4096`).
#[cfg_attr(not(feature = "extism"), allow(dead_code))]
const WASM_MEMORY_MAX_ENV: &str = "HUB_WASM_MEMORY_MAX_MB";

/// Interpreta el valor crudo de [`WASM_MEMORY_MAX_ENV`] como MB.
///
/// Parse robusto: vacío / no numérico / `0` ⇒ [`DEFAULT_WASM_MEMORY_MAX_MB`] y un
/// warning por `tracing`. Nunca devuelve `0` (0 no es «ilimitado»).
#[cfg_attr(not(feature = "extism"), allow(dead_code))]
fn parse_memory_max_mb(raw: &str) -> u32 {
    match raw.trim().parse::<u32>() {
        Ok(mb) if mb > 0 => mb,
        _ => {
            tracing::warn!(
                target: "erplora_wasm_host",
                value = %raw,
                default_mb = DEFAULT_WASM_MEMORY_MAX_MB,
                "{WASM_MEMORY_MAX_ENV} inválido (0 NO significa ilimitado); \
                 usando el tope por defecto"
            );
            DEFAULT_WASM_MEMORY_MAX_MB
        }
    }
}

/// Resuelve el tope de memoria por plugin (MB): env si está fijado, si no el default.
#[cfg_attr(not(feature = "extism"), allow(dead_code))]
fn resolved_memory_max_mb() -> u32 {
    match std::env::var(WASM_MEMORY_MAX_ENV) {
        Ok(raw) => parse_memory_max_mb(&raw),
        Err(_) => DEFAULT_WASM_MEMORY_MAX_MB,
    }
}

/// Serializa el [`Input`] al JSON que se pasa al guest.
#[cfg_attr(not(feature = "extism"), allow(dead_code))]
fn encode_input(input: &serde_json::Value) -> Result<Vec<u8>, WasmError> {
    serde_json::to_vec(input).map_err(|e| WasmError::Decode(e.to_string()))
}

/// Deserializa el [`Output`] devuelto por el guest.
#[cfg_attr(not(feature = "extism"), allow(dead_code))]
fn decode_output(bytes: &[u8]) -> Result<Output, WasmError> {
    serde_json::from_slice(bytes).map_err(|e| WasmError::Decode(e.to_string()))
}

/// Host que carga un módulo WASM y ejecuta sus funciones en sandbox.
///
/// Se construye con [`WasmHost::from_bytes`] y se invoca con [`WasmHost::call`].
#[cfg(feature = "extism")]
pub struct WasmHost {
    plugin: extism::Plugin,
    /// Tope de memoria aplicado a este plugin (MB) — solo para el mensaje de error.
    memory_max_mb: u32,
}

#[cfg(feature = "extism")]
impl WasmHost {
    /// Carga un módulo WASM desde sus bytes (`.wasm` o WAT ya compilado).
    ///
    /// El módulo corre sin WASI y sin host-functions extra: es un sandbox puro,
    /// con un **tope de memoria lineal** de [`DEFAULT_WASM_MEMORY_MAX_MB`] MB
    /// (sobreescribible por [`WASM_MEMORY_MAX_ENV`]). Así un handler glotón se
    /// queda dentro de su sandbox en vez de disparar el OOM-killer del contenedor
    /// y tumbar el hub entero (hub#204).
    pub fn from_bytes(wasm: &[u8]) -> Result<Self, WasmError> {
        Self::from_bytes_with_memory_max_mb(wasm, resolved_memory_max_mb())
    }

    /// Igual que [`from_bytes`](Self::from_bytes) pero con el tope de memoria
    /// **explícito** en MB — determinista, sin leer el entorno. Se usa desde los
    /// tests para no depender de una variable de proceso compartida.
    fn from_bytes_with_memory_max_mb(wasm: &[u8], memory_max_mb: u32) -> Result<Self, WasmError> {
        let wasm_owned = extism::Wasm::data(wasm.to_vec());
        // `with_memory_max` fija `memory.max_pages`; el `ResourceLimiter` de Extism
        // atrapa (OOM) cualquier `memory.grow` que supere el tope.
        let manifest = extism::Manifest::new([wasm_owned])
            .with_memory_max(memory_max_mb.saturating_mul(PAGES_PER_MB));
        let plugin = extism::Plugin::new(&manifest, [], false)
            .map_err(|e| WasmError::Load(e.to_string()))?;
        Ok(WasmHost {
            plugin,
            memory_max_mb,
        })
    }

    /// Invoca la función exportada `function`, pasándole `input` como JSON, y
    /// devuelve el [`Output`] deserializado.
    ///
    /// El host **luego** valida cada [`Operation`] del `Output` contra los
    /// commands permitidos y las ejecuta en transacción — eso es trabajo del
    /// runtime del Hub, no de este método.
    pub fn call(
        &mut self,
        function: &str,
        input: &serde_json::Value,
    ) -> Result<Output, WasmError> {
        let payload = encode_input(input)?;
        let memory_max_mb = self.memory_max_mb;
        let raw: &[u8] = self
            .plugin
            .call::<&[u8], &[u8]>(function, &payload)
            .map_err(|e| map_call_error(function, memory_max_mb, e))?;
        decode_output(raw)
    }
}

/// Traduce el error crudo de Extism al [`WasmError`] del host.
///
/// Cuando el guest supera el tope de memoria, Extism/wasmtime propagan un error
/// cuya causa raíz es `"oom"`. Lo mapeamos a un mensaje claro con el tope en MB,
/// **sin** exponer internals del runtime; cualquier otro fallo mantiene la causa
/// subyacente.
#[cfg(feature = "extism")]
fn map_call_error(function: &str, memory_max_mb: u32, err: extism::Error) -> WasmError {
    if err
        .root_cause()
        .to_string()
        .to_ascii_lowercase()
        .contains("oom")
    {
        WasmError::Call {
            function: function.to_string(),
            reason: format!("wasm handler exceeded memory limit ({memory_max_mb} MB)"),
        }
    } else {
        WasmError::call(function, err)
    }
}

/// Fallback sin runtime WASM (build con `--no-default-features`).
///
/// Mantiene la API pública para que el resto del workspace compile, pero las
/// operaciones que requieren ejecutar WASM devuelven [`WasmError::Load`].
#[cfg(not(feature = "extism"))]
pub struct WasmHost {
    _private: (),
}

#[cfg(not(feature = "extism"))]
impl WasmHost {
    /// No disponible sin la feature `extism`: devuelve [`WasmError::Load`].
    pub fn from_bytes(_wasm: &[u8]) -> Result<Self, WasmError> {
        Err(WasmError::Load(
            "wasm execution disabled: build erplora-wasm-host with the `extism` feature".to_string(),
        ))
    }

    /// No disponible sin la feature `extism`: devuelve [`WasmError::Load`].
    pub fn call(
        &mut self,
        _function: &str,
        _input: &serde_json::Value,
    ) -> Result<Output, WasmError> {
        Err(WasmError::Load(
            "wasm execution disabled: build erplora-wasm-host with the `extism` feature".to_string(),
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn encode_input_serializes_json() {
        let bytes = encode_input(&json!({"a": 1})).unwrap();
        assert_eq!(bytes, br#"{"a":1}"#);
    }

    #[test]
    fn decode_output_parses_contract() {
        let raw = br#"{"operations":[{"kind":"sql","command":"create_sale_line","params":{"qty":2}}],"events":[{"name":"sale.line_added","payload":{"qty":2}}]}"#;
        let out = decode_output(raw).unwrap();
        assert_eq!(out.operations.len(), 1);
        assert_eq!(out.operations[0].kind, "sql");
        assert_eq!(out.operations[0].command, "create_sale_line");
        assert_eq!(out.operations[0].params["qty"], json!(2));
        assert_eq!(out.events.len(), 1);
        assert_eq!(out.events[0].name, "sale.line_added");
    }

    #[test]
    fn decode_output_empty_object_is_empty_intentions() {
        let out = decode_output(b"{}").unwrap();
        assert!(out.operations.is_empty());
        assert!(out.events.is_empty());
    }

    #[test]
    fn decode_output_invalid_json_is_decode_error() {
        let err = decode_output(b"not json").unwrap_err();
        assert!(matches!(err, WasmError::Decode(_)));
    }

    #[test]
    fn wasm_error_messages_are_descriptive() {
        let e = WasmError::call("handle", "boom");
        let msg = e.to_string();
        assert!(msg.contains("handle"));
        assert!(msg.contains("boom"));
    }

    /// Cargar bytes que no son WASM válido debe dar `WasmError::Load`.
    ///
    /// Con la feature `extism` (por defecto) ejercita el runtime real; sin ella,
    /// el fallback también devuelve `Load`. En ambos casos el resultado es el
    /// mismo, así que el test pasa con o sin runtime WASM. Se usa `match` en vez
    /// de `unwrap_err()` porque `WasmHost` no implementa `Debug` (envuelve un
    /// `extism::Plugin`).
    #[test]
    fn from_bytes_invalid_module_is_load_error() {
        match WasmHost::from_bytes(b"\x00\x01\x02 definitely not wasm") {
            Ok(_) => panic!("expected Load error for non-wasm bytes"),
            Err(e) => assert!(
                matches!(e, WasmError::Load(_)),
                "expected Load error, got {e:?}"
            ),
        }
    }

    /// Round-trip real Input→Output a través de un guest WASM compilado.
    ///
    /// Requiere un `.wasm` real que implemente la ABI de Extism (PDK) y exporte
    /// `handle`. No se puede generar a mano de forma fiable en `.wat` (la ABI de
    /// memoria del kernel de Extism no es estable entre versiones), por eso este
    /// test queda `#[ignore]`.
    ///
    /// Para correrlo:
    /// ```text
    /// # 1. Crea un guest crate (cdylib) que dependa de erplora-guest-sdk +
    /// #    extism-pdk y exporte `handle` (ver el doc de erplora-guest-sdk).
    /// # 2. cargo build --target wasm32-unknown-unknown --release
    /// # 3. export ERPLORA_TEST_WASM=/ruta/al/guest.wasm
    /// # 4. cargo test -p erplora-wasm-host -- --ignored roundtrip
    /// ```
    #[cfg(feature = "extism")]
    #[test]
    #[ignore = "requires a real Extism guest .wasm; set ERPLORA_TEST_WASM"]
    fn real_guest_roundtrip() {
        let path = std::env::var("ERPLORA_TEST_WASM")
            .expect("set ERPLORA_TEST_WASM to a compiled Extism guest .wasm");
        let bytes = std::fs::read(&path).expect("read wasm file");
        let mut host = WasmHost::from_bytes(&bytes).expect("load guest");
        let out = host
            .call("handle", &json!({"product_id": 42, "qty": 3}))
            .expect("call guest");
        assert!(!out.operations.is_empty());
    }

    // ---------------------------------------------------------------------
    // Límite de memoria por plugin (hub#204).
    //
    // Sin `memory_max`, la memoria lineal del guest solo la acota el cgroup del
    // contenedor: un handler que reserve suficiente dispara el OOM-killer y mata
    // el hub entero. Con el tope, un guest glotón recibe un error controlado y el
    // host sigue vivo. Los guests de prueba se compilan de WAT a wasm en el propio
    // test (dev-dep `wat`), sin `.wasm` externos ni target wasm32.
    // ---------------------------------------------------------------------

    /// Guest glotón: hace crecer su memoria lineal 1024 páginas (64 MiB), muy por
    /// encima del tope de 32 MB. Al superar el límite, `memory.grow` atrapa (OOM).
    #[cfg(feature = "extism")]
    const GREEDY_GUEST_WAT: &str = r#"
        (module
          (memory 1)
          (func (export "handle") (result i32)
            (drop (memory.grow (i32.const 1024)))
            (i32.const 0)))
    "#;

    /// Guest normal: crece 16 páginas (1 MiB, dentro del tope) y devuelve `{}` por
    /// el ABI de output de Extism (`alloc` + `store_u8` + `output_set`).
    #[cfg(feature = "extism")]
    const NORMAL_GUEST_WAT: &str = r#"
        (module
          (import "extism:host/env" "alloc"      (func $alloc      (param i64) (result i64)))
          (import "extism:host/env" "store_u8"   (func $store_u8   (param i64 i32)))
          (import "extism:host/env" "output_set" (func $output_set (param i64 i64)))
          (memory 1)
          (func (export "handle") (result i32)
            (local $p i64)
            (drop (memory.grow (i32.const 16)))
            (local.set $p (call $alloc (i64.const 2)))
            (call $store_u8 (local.get $p) (i32.const 123))                          ;; '{'
            (call $store_u8 (i64.add (local.get $p) (i64.const 1)) (i32.const 125))  ;; '}'
            (call $output_set (local.get $p) (i64.const 2))
            (i32.const 0)))
    "#;

    #[cfg(feature = "extism")]
    fn compile_wat(src: &str) -> Vec<u8> {
        wat::parse_str(src).expect("compilar WAT de prueba a wasm")
    }

    /// Un guest que intenta reservar > 32 MB recibe un error de asignación
    /// **controlado** (`call` devuelve `Err`), no un aborto del proceso. Tope
    /// explícito (32 MB) para no depender del entorno del proceso.
    #[cfg(feature = "extism")]
    #[test]
    fn greedy_guest_over_limit_is_controlled_call_error() {
        let wasm = compile_wat(GREEDY_GUEST_WAT);
        let mut host = WasmHost::from_bytes_with_memory_max_mb(&wasm, 32).expect("cargar glotón");
        let err = match host.call("handle", &json!({})) {
            Ok(_) => panic!("el guest glotón debería fallar al superar el tope de memoria"),
            Err(e) => e,
        };
        match err {
            WasmError::Call { reason, .. } => {
                assert!(
                    reason.contains("memory limit"),
                    "el error debe mencionar el límite de memoria; got: {reason}"
                );
                assert!(
                    reason.contains("(32 MB)"),
                    "el error debe indicar el tope en MB; got: {reason}"
                );
            }
            other => panic!("esperaba WasmError::Call por OOM; got: {other:?}"),
        }
    }

    /// Tras el OOM de un guest glotón, el host/runtime **sigue vivo**: un handler
    /// normal se ejecuta después y devuelve su `Output`. Si el OOM hubiera
    /// abortado el proceso, este test no llegaría al paso 2.
    #[cfg(feature = "extism")]
    #[test]
    fn host_survives_greedy_guest_and_runs_a_normal_handler_after() {
        // 1) glotón → error controlado.
        let greedy = compile_wat(GREEDY_GUEST_WAT);
        let mut h1 = WasmHost::from_bytes_with_memory_max_mb(&greedy, 32).unwrap();
        assert!(
            matches!(h1.call("handle", &json!({})), Err(WasmError::Call { .. })),
            "el glotón debe dar un Err controlado"
        );

        // 2) handler normal DESPUÉS → Output válido.
        let normal = compile_wat(NORMAL_GUEST_WAT);
        let mut h2 = WasmHost::from_bytes_with_memory_max_mb(&normal, 32).unwrap();
        let out = h2
            .call("handle", &json!({}))
            .expect("un handler normal (dentro del tope) debe devolver Output");
        assert!(out.operations.is_empty());
        assert!(out.events.is_empty());
    }

    // -- Parse del override por entorno (puro, determinista, sin tocar el env). --

    #[test]
    fn parse_memory_max_mb_valid_value_is_used() {
        assert_eq!(parse_memory_max_mb("64"), 64);
        assert_eq!(parse_memory_max_mb("  16 "), 16); // recorta espacios
    }

    #[test]
    fn parse_memory_max_mb_zero_is_default_not_unlimited() {
        // 0 NO significa ilimitado: cae al default.
        assert_eq!(parse_memory_max_mb("0"), DEFAULT_WASM_MEMORY_MAX_MB);
    }

    #[test]
    fn parse_memory_max_mb_invalid_falls_back_to_default() {
        assert_eq!(parse_memory_max_mb(""), DEFAULT_WASM_MEMORY_MAX_MB);
        assert_eq!(parse_memory_max_mb("abc"), DEFAULT_WASM_MEMORY_MAX_MB);
        assert_eq!(parse_memory_max_mb("-5"), DEFAULT_WASM_MEMORY_MAX_MB);
        assert_eq!(parse_memory_max_mb("12.5"), DEFAULT_WASM_MEMORY_MAX_MB);
    }

    /// El override por entorno **cablea con el tope real que se aplica**: con el
    /// default (env sin fijar) `from_bytes` usa 32 MB; con `HUB_WASM_MEMORY_MAX_MB=8`
    /// usa 8 MB — y el guest glotón lo refleja en el mensaje de error. Es el
    /// **único** test que toca la variable de entorno (evita carreras: los demás
    /// usan el tope explícito).
    #[cfg(feature = "extism")]
    #[test]
    fn env_override_wires_into_the_enforced_cap() {
        let greedy = compile_wat(GREEDY_GUEST_WAT);

        // Default (env sin fijar) → 32 MB.
        std::env::remove_var(WASM_MEMORY_MAX_ENV);
        assert_eq!(resolved_memory_max_mb(), DEFAULT_WASM_MEMORY_MAX_MB);
        match WasmHost::from_bytes(&greedy).unwrap().call("handle", &json!({})) {
            Err(WasmError::Call { reason, .. }) => assert!(
                reason.contains("(32 MB)"),
                "con el default el tope del error debe ser 32 MB; got: {reason}"
            ),
            other => panic!("el default debe topar al glotón por OOM; got: {other:?}"),
        }

        // Override a 8 MB.
        std::env::set_var(WASM_MEMORY_MAX_ENV, "8");
        assert_eq!(resolved_memory_max_mb(), 8);
        let res = WasmHost::from_bytes(&greedy).unwrap().call("handle", &json!({}));
        std::env::remove_var(WASM_MEMORY_MAX_ENV);
        match res {
            Err(WasmError::Call { reason, .. }) => assert!(
                reason.contains("(8 MB)"),
                "el override debe reflejarse en el tope del error; got: {reason}"
            ),
            other => panic!("con 8 MB el glotón debe dar OOM; got: {other:?}"),
        }
    }
}
