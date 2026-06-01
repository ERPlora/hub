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
}

#[cfg(feature = "extism")]
impl WasmHost {
    /// Carga un módulo WASM desde sus bytes (`.wasm` o WAT ya compilado).
    ///
    /// El módulo corre sin WASI y sin host-functions extra: es un sandbox puro.
    pub fn from_bytes(wasm: &[u8]) -> Result<Self, WasmError> {
        let wasm_owned = extism::Wasm::data(wasm.to_vec());
        let manifest = extism::Manifest::new([wasm_owned]);
        let plugin = extism::Plugin::new(&manifest, [], false)
            .map_err(|e| WasmError::Load(e.to_string()))?;
        Ok(WasmHost { plugin })
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
        let raw: &[u8] = self
            .plugin
            .call::<&[u8], &[u8]>(function, &payload)
            .map_err(|e| WasmError::call(function, e))?;
        decode_output(raw)
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
}
