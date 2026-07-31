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

    /// El guest agotó su presupuesto de **instrucciones** (fuel). Es el corte determinista
    /// contra un handler que no termina (`while(1){}`) — hub#241.
    #[error("wasm call to `{function}` exceeded its instruction budget ({fuel} fuel)")]
    OutOfFuel {
        /// Nombre de la función exportada que se intentó invocar.
        function: String,
        /// Presupuesto de instrucciones que se agotó.
        fuel: u64,
    },

    /// El guest superó su **tiempo de reloj** máximo y wasmtime lo interrumpió (epoch).
    #[error("wasm call to `{function}` timed out after {timeout_ms} ms")]
    Timeout {
        /// Nombre de la función exportada que se intentó invocar.
        function: String,
        /// Tope de reloj aplicado, en milisegundos.
        timeout_ms: u64,
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

/// Presupuesto de **instrucciones** (fuel de wasmtime) por llamada, cuando no se
/// configura otra cosa. Es el corte **determinista** (no depende de lo rápida que
/// sea la máquina) contra un handler que no termina.
///
/// 200 M de instrucciones son ~3 órdenes de magnitud más de lo que consume un
/// handler real (un ticket de 256 líneas resuelve en decenas de miles), y aun así
/// un `while(1){}` se queda sin fuel en una fracción de segundo. hub#241.
#[cfg_attr(not(feature = "extism"), allow(dead_code))]
const DEFAULT_WASM_FUEL: u64 = 200_000_000;

/// Variable de entorno para sobreescribir [`DEFAULT_WASM_FUEL`]. `0`/inválido ⇒ default.
#[cfg_attr(not(feature = "extism"), allow(dead_code))]
const WASM_FUEL_ENV: &str = "HUB_WASM_FUEL";

/// Tope de **reloj** por llamada (ms) cuando no se configura otra cosa. Complementa al fuel:
/// el fuel cuenta instrucciones del guest; el reloj cubre el resto (y es lo que el operador
/// entiende). 5 s es holgadísimo para un handler puro y muy por debajo de lo que un cajero
/// aguanta mirando el TPV. hub#241.
#[cfg_attr(not(feature = "extism"), allow(dead_code))]
const DEFAULT_WASM_TIMEOUT_MS: u64 = 5_000;

/// Variable de entorno para sobreescribir [`DEFAULT_WASM_TIMEOUT_MS`]. `0`/inválido ⇒ default
/// (`0` **no** significa «sin timeout»: sería reabrir el agujero).
#[cfg_attr(not(feature = "extism"), allow(dead_code))]
const WASM_TIMEOUT_MS_ENV: &str = "HUB_WASM_TIMEOUT_MS";

/// Topes del sandbox aplicados a **cada** plugin WASM (hub#204 + hub#241).
///
/// Los tres son fail-closed: un valor ausente o inválido cae al default, y `0` nunca
/// significa «ilimitado». Se resuelven una vez por carga con [`WasmLimits::from_env`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct WasmLimits {
    /// Tope de memoria lineal del guest, en MB.
    pub memory_max_mb: u32,
    /// Presupuesto de instrucciones por llamada (fuel de wasmtime).
    pub fuel: u64,
    /// Tope de reloj por llamada, en milisegundos (epoch interruption).
    pub timeout_ms: u64,
}

impl Default for WasmLimits {
    fn default() -> Self {
        WasmLimits {
            memory_max_mb: DEFAULT_WASM_MEMORY_MAX_MB,
            fuel: DEFAULT_WASM_FUEL,
            timeout_ms: DEFAULT_WASM_TIMEOUT_MS,
        }
    }
}

impl WasmLimits {
    /// Resuelve los topes desde el entorno (`HUB_WASM_MEMORY_MAX_MB`, `HUB_WASM_FUEL`,
    /// `HUB_WASM_TIMEOUT_MS`), cayendo a los defaults ante ausencia o valor inválido.
    pub fn from_env() -> Self {
        WasmLimits {
            memory_max_mb: resolved_memory_max_mb(),
            fuel: resolved_env_u64(WASM_FUEL_ENV, DEFAULT_WASM_FUEL),
            timeout_ms: resolved_env_u64(WASM_TIMEOUT_MS_ENV, DEFAULT_WASM_TIMEOUT_MS),
        }
    }
}

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

/// Parse robusto de un tope `u64` (fuel / timeout): vacío, no numérico o `0` ⇒ `default`
/// con un warning. Nunca devuelve `0` — desactivar un tope no puede ser un accidente
/// de configuración.
fn parse_u64_limit(raw: &str, default: u64, var: &str) -> u64 {
    match raw.trim().parse::<u64>() {
        Ok(v) if v > 0 => v,
        _ => {
            tracing::warn!(
                target: "erplora_wasm_host",
                value = %raw,
                var = %var,
                default,
                "límite del sandbox WASM inválido (0 NO significa ilimitado); \
                 usando el tope por defecto"
            );
            default
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

/// Resuelve un tope `u64` desde el entorno, cayendo a `default` si no está fijado.
fn resolved_env_u64(var: &str, default: u64) -> u64 {
    match std::env::var(var) {
        Ok(raw) => parse_u64_limit(&raw, default, var),
        Err(_) => default,
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
    /// Topes aplicados a este plugin — se conservan para poder explicarlos en el error.
    limits: WasmLimits,
}

#[cfg(feature = "extism")]
impl WasmHost {
    /// Carga un módulo WASM desde sus bytes (`.wasm` o WAT ya compilado).
    ///
    /// El módulo corre **sin WASI y sin host-functions extra** (sandbox puro) y con los tres
    /// topes de [`WasmLimits::from_env`]:
    ///
    /// * **memoria** — un handler glotón se queda dentro de su sandbox en vez de disparar el
    ///   OOM-killer del contenedor y tumbar el hub entero (hub#204);
    /// * **fuel** — un handler que no termina agota su presupuesto de instrucciones;
    /// * **timeout** — y, si el fuel no lo cortara, lo corta el reloj (hub#241).
    ///
    /// Sin los dos últimos, un `while(1){}` en un módulo de terceros colgaba el runtime del TPV
    /// hasta reiniciar el proceso.
    pub fn from_bytes(wasm: &[u8]) -> Result<Self, WasmError> {
        Self::from_bytes_with_limits(wasm, WasmLimits::from_env())
    }

    /// Igual que [`from_bytes`](Self::from_bytes) pero con los topes **explícitos** —
    /// determinista, sin leer el entorno. Lo usan los tests (y cualquier host que quiera
    /// fijar sus propios límites) para no depender de una variable de proceso compartida.
    pub fn from_bytes_with_limits(wasm: &[u8], limits: WasmLimits) -> Result<Self, WasmError> {
        let wasm_owned = extism::Wasm::data(wasm.to_vec());
        // `with_memory_max` fija `memory.max_pages`; el `ResourceLimiter` de Extism
        // atrapa (OOM) cualquier `memory.grow` que supere el tope. `with_timeout` arma la
        // interrupción por epoch de wasmtime: el guest se para aunque no haga syscalls.
        let manifest = extism::Manifest::new([wasm_owned])
            .with_memory_max(limits.memory_max_mb.saturating_mul(PAGES_PER_MB))
            .with_timeout(std::time::Duration::from_millis(limits.timeout_ms));
        // `with_wasi(false)` + sin host functions: se mantiene el sandbox cerrado (el guest no
        // tiene reloj, ni ficheros, ni red). `with_fuel_limit` activa `consume_fuel` en wasmtime.
        let plugin = extism::PluginBuilder::new(&manifest)
            .with_wasi(false)
            .with_fuel_limit(limits.fuel)
            .build()
            .map_err(|e| WasmError::Load(e.to_string()))?;
        Ok(WasmHost { plugin, limits })
    }

    /// Igual que [`from_bytes`](Self::from_bytes) pero con el tope de memoria explícito
    /// (el resto, defaults). Se conserva para los tests de memoria de hub#204.
    #[cfg(test)]
    fn from_bytes_with_memory_max_mb(wasm: &[u8], memory_max_mb: u32) -> Result<Self, WasmError> {
        Self::from_bytes_with_limits(
            wasm,
            WasmLimits {
                memory_max_mb,
                ..WasmLimits::default()
            },
        )
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
        let limits = self.limits;
        let raw: &[u8] = self
            .plugin
            .call::<&[u8], &[u8]>(function, &payload)
            .map_err(|e| map_call_error(function, limits, e))?;
        decode_output(raw)
    }

    /// Topes efectivos de este plugin (memoria/fuel/timeout). El runtime los usa para dar
    /// un margen de gracia al esperar la llamada desde su hilo bloqueante.
    pub fn limits(&self) -> WasmLimits {
        self.limits
    }
}

/// Traduce el error crudo de Extism al [`WasmError`] del host.
///
/// Extism/wasmtime señalan los tres cortes del sandbox con causas raíz reconocibles:
/// `"oom"` (memoria), `"plugin ran out of fuel"` (instrucciones) y `"timeout"` (reloj,
/// interrupción por epoch). Se mapean a variantes propias con el tope aplicado, **sin**
/// exponer internals del runtime; cualquier otro fallo mantiene la causa subyacente.
#[cfg(feature = "extism")]
fn map_call_error(function: &str, limits: WasmLimits, err: extism::Error) -> WasmError {
    let root = err.root_cause().to_string().to_ascii_lowercase();
    if root.contains("out of fuel") {
        WasmError::OutOfFuel {
            function: function.to_string(),
            fuel: limits.fuel,
        }
    } else if root.contains("timeout") {
        WasmError::Timeout {
            function: function.to_string(),
            timeout_ms: limits.timeout_ms,
        }
    } else if root.contains("oom") {
        WasmError::Call {
            function: function.to_string(),
            reason: format!(
                "wasm handler exceeded memory limit ({} MB)",
                limits.memory_max_mb
            ),
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

    /// Topes del sandbox (los del entorno; sin runtime WASM no se aplican a nada).
    pub fn limits(&self) -> WasmLimits {
        WasmLimits::from_env()
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

    // ---------------------------------------------------------------------
    // Reloj y fuel: un handler que no termina NO puede colgar el runtime (hub#241).
    //
    // Sin fuel ni timeout, un `while(1){}` en un handler de módulo se comía un
    // worker de Tokio para siempre: el TPV dejaba de responder y solo se
    // recuperaba reiniciando el proceso. Los dos topes son complementarios:
    // el **fuel** acota el número de instrucciones (determinista, independiente
    // de la máquina) y el **timeout** acota el reloj (cubre lo que el fuel no
    // ve, p. ej. una llamada al host que tarda).
    // ---------------------------------------------------------------------

    /// Guest que no termina nunca: bucle vacío.
    #[cfg(feature = "extism")]
    const SPINNING_GUEST_WAT: &str = r#"
        (module
          (memory 1)
          (func (export "handle") (result i32)
            (loop $forever (br $forever))
            (i32.const 0)))
    "#;

    /// Un handler que no termina se queda **sin fuel** y devuelve un error controlado.
    /// Sin este tope el `call` no volvía jamás.
    #[cfg(feature = "extism")]
    #[test]
    fn spinning_guest_runs_out_of_fuel() {
        let wasm = compile_wat(SPINNING_GUEST_WAT);
        // Fuel pequeño y timeout enorme: así el que corta es el fuel, no el reloj.
        let limits = WasmLimits {
            memory_max_mb: 32,
            fuel: 1_000_000,
            timeout_ms: 60_000,
        };
        let mut host = WasmHost::from_bytes_with_limits(&wasm, limits).expect("cargar guest");
        match host.call("handle", &json!({})) {
            Ok(_) => panic!("un bucle infinito no puede devolver Ok"),
            Err(WasmError::OutOfFuel { fuel, .. }) => assert_eq!(fuel, 1_000_000),
            Err(other) => panic!("esperaba OutOfFuel; got: {other:?}"),
        }
    }

    /// Con fuel de sobra, el que corta es el **reloj**: el guest se interrumpe al vencer
    /// `timeout_ms` y el host devuelve `Timeout` (no se cuelga).
    #[cfg(feature = "extism")]
    #[test]
    fn spinning_guest_is_interrupted_by_timeout() {
        let wasm = compile_wat(SPINNING_GUEST_WAT);
        let limits = WasmLimits {
            memory_max_mb: 32,
            fuel: u64::MAX / 2, // fuel "infinito" a efectos prácticos
            timeout_ms: 200,
        };
        let mut host = WasmHost::from_bytes_with_limits(&wasm, limits).expect("cargar guest");
        let started = std::time::Instant::now();
        match host.call("handle", &json!({})) {
            Ok(_) => panic!("un bucle infinito no puede devolver Ok"),
            Err(WasmError::Timeout { timeout_ms, .. }) => assert_eq!(timeout_ms, 200),
            Err(other) => panic!("esperaba Timeout; got: {other:?}"),
        }
        assert!(
            started.elapsed() < std::time::Duration::from_secs(10),
            "el timeout debe cortar en ~200ms, no dejar correr el guest"
        );
    }

    /// Un handler normal (poquísimas instrucciones) NO se ve afectado por los topes por defecto.
    #[cfg(feature = "extism")]
    #[test]
    fn normal_guest_is_unaffected_by_default_limits() {
        let wasm = compile_wat(NORMAL_GUEST_WAT);
        let mut host =
            WasmHost::from_bytes_with_limits(&wasm, WasmLimits::default()).expect("cargar guest");
        let out = host.call("handle", &json!({})).expect("handler normal en verde");
        assert!(out.operations.is_empty());
    }

    // -- Parse de los overrides por entorno (puro, determinista, sin tocar el env). --

    #[test]
    fn default_limits_are_sane() {
        let d = WasmLimits::default();
        assert_eq!(d.memory_max_mb, DEFAULT_WASM_MEMORY_MAX_MB);
        assert_eq!(d.fuel, DEFAULT_WASM_FUEL);
        assert_eq!(d.timeout_ms, DEFAULT_WASM_TIMEOUT_MS);
        assert!(d.timeout_ms > 0, "0 NO puede significar «sin timeout»");
        assert!(d.fuel > 0, "0 NO puede significar «fuel ilimitado»");
    }

    #[test]
    fn parse_timeout_ms_valid_value_is_used() {
        assert_eq!(parse_u64_limit("2500", DEFAULT_WASM_TIMEOUT_MS, "x"), 2500);
        assert_eq!(parse_u64_limit(" 750 ", DEFAULT_WASM_TIMEOUT_MS, "x"), 750);
    }

    /// `0` NO desactiva el tope (sería reabrir el agujero): cae al default.
    #[test]
    fn parse_u64_limit_zero_or_invalid_falls_back_to_default() {
        for raw in ["0", "", "abc", "-5", "1.5"] {
            assert_eq!(
                parse_u64_limit(raw, DEFAULT_WASM_TIMEOUT_MS, "x"),
                DEFAULT_WASM_TIMEOUT_MS,
                "`{raw}` no puede desactivar el tope"
            );
        }
    }

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
