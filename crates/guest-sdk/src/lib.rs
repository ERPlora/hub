//! # erplora-guest-sdk
//!
//! Tipos del **contrato host↔guest** del Tier 2 (lógica WASM) de ERPlora
//! (ARQUITECTURA.md §5.3, §7.3).
//!
//! Un *command* de módulo puede resolverse con un handler WASM en vez de SQL.
//! El handler corre en un **sandbox** y **NO** toca la base de datos: recibe un
//! [`Input`] JSON y devuelve un [`Output`] que describe **intenciones** — una
//! lista de [`Operation`]s SQL (referenciadas por nombre de command/plantilla +
//! params) y una lista de [`Event`]s a emitir. El **host** (Rust) valida cada
//! operación contra los commands permitidos y la ejecuta en transacción.
//!
//! Este crate es la librería que usan los **autores de plugins**. Define el
//! contrato con `serde` para que:
//!
//! * el **host** (`erplora-wasm-host`) deserialice el [`Output`] que el guest
//!   produce, y
//! * el **guest** (compilado a `wasm32`) serialice su [`Output`] e interprete el
//!   [`Input`] entrante.
//!
//! Los tipos compilan en target **nativo** (para que el host los use) y tienen
//! tests de (de)serialización; no requieren `no_std`.
//!
//! ## Escribir un plugin con `extism-pdk`
//!
//! `extism-pdk` solo se compila para target wasm, por eso **no** es una
//! dependencia de este crate. Un autor de plugin lo añade en *su* crate y usa
//! estos tipos así:
//!
//! ```ignore
//! // En el Cargo.toml del plugin (crate cdylib, target wasm32-unknown-unknown):
//! //   [dependencies]
//! //   erplora-guest-sdk = "0.1"
//! //   extism-pdk = "1"
//! use erplora_guest_sdk::{Input, Output, Operation, Event};
//! use extism_pdk::*;
//!
//! #[plugin_fn]
//! pub fn handle(input: Json<Input>) -> FnResult<Json<Output>> {
//!     let input = input.into_inner();
//!     // ... lógica pura, sin BD ...
//!     let out = Output::new()
//!         .with_operation(Operation::sql("create_sale_line", serde_json::Map::new()))
//!         .with_event(Event::new("sale.line_added", serde_json::json!({"qty": 1})));
//!     Ok(Json(out))
//! }
//! ```
//!
//! Alternativamente, sin macros, con el helper [`run`]:
//!
//! ```ignore
//! use erplora_guest_sdk::{run, Input, Output};
//! use extism_pdk::*;
//!
//! #[plugin_fn]
//! pub fn handle(input: Json<Input>) -> FnResult<Json<Output>> {
//!     Ok(Json(run(input.into_inner(), |inp: Input| {
//!         // ... handler puro ...
//!         Output::new()
//!     })))
//! }
//! ```

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

/// **La aritmética del dinero** (ADR-0123). Céntimos enteros, un solo modo de redondeo, y la
/// distinción entre dinero, tasa y cantidad. Antes vivía copiada en 7 handlers.
pub mod currency;
pub mod money;
pub mod units;

/// Entrada arbitraria que el host pasa al handler WASM.
///
/// Es un wrapper transparente sobre un [`serde_json::Value`]; el guest decide
/// cómo interpretarlo. Serializa exactamente como el valor JSON que envuelve.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
#[serde(transparent)]
pub struct Input(pub Value);

impl Input {
    /// Crea un [`Input`] a partir de cualquier valor serializable a JSON.
    pub fn new(value: impl Into<Value>) -> Self {
        Input(value.into())
    }

    /// Referencia al valor JSON subyacente.
    pub fn value(&self) -> &Value {
        &self.0
    }

    /// Consume el `Input` y devuelve el valor JSON subyacente.
    pub fn into_value(self) -> Value {
        self.0
    }
}

impl From<Value> for Input {
    fn from(v: Value) -> Self {
        Input(v)
    }
}

/// Una **intención** de operación que el host ejecutará si la valida.
///
/// Hoy solo existe `kind = "sql"`: referencia un *command*/plantilla SQL por
/// nombre (`command`) y aporta sus `params`. El host resuelve el command, valida
/// que esté permitido para el módulo y lo ejecuta en transacción. El guest nunca
/// emite SQL crudo — solo nombres de command + params.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Operation {
    /// Discriminante del tipo de operación. Por ahora siempre `"sql"`.
    pub kind: String,
    /// Nombre del command/plantilla SQL a ejecutar.
    pub command: String,
    /// Parámetros para el command.
    #[serde(default)]
    pub params: Map<String, Value>,
}

impl Operation {
    /// Construye una operación SQL (`kind = "sql"`).
    pub fn sql(command: impl Into<String>, params: Map<String, Value>) -> Self {
        Operation {
            kind: "sql".to_string(),
            command: command.into(),
            params,
        }
    }
}

/// Un evento de dominio que el host emitirá tras ejecutar las operaciones.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Event {
    /// Nombre del evento (p.ej. `"sale.line_added"`).
    pub name: String,
    /// Payload arbitrario del evento.
    #[serde(default)]
    pub payload: Value,
}

impl Event {
    /// Construye un evento con nombre y payload.
    pub fn new(name: impl Into<String>, payload: impl Into<Value>) -> Self {
        Event {
            name: name.into(),
            payload: payload.into(),
        }
    }
}

/// Resultado de un handler WASM: el conjunto de **intenciones** a aplicar.
///
/// El host valida y ejecuta `operations` en orden dentro de una transacción y
/// luego emite `events`. Nunca contiene SQL crudo ni filas de BD.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct Output {
    /// Operaciones SQL (por nombre de command + params) a ejecutar.
    #[serde(default)]
    pub operations: Vec<Operation>,
    /// Eventos a emitir tras ejecutar las operaciones.
    #[serde(default)]
    pub events: Vec<Event>,
}

impl Output {
    /// Crea un [`Output`] vacío.
    pub fn new() -> Self {
        Output::default()
    }

    /// Añade una operación (builder).
    pub fn with_operation(mut self, op: Operation) -> Self {
        self.operations.push(op);
        self
    }

    /// Añade un evento (builder).
    pub fn with_event(mut self, ev: Event) -> Self {
        self.events.push(ev);
        self
    }
}

/// Helper ergonómico para autores de plugins: aplica `handler` a un [`Input`] y
/// devuelve el [`Output`].
///
/// Pensado para envolverse en el punto de entrada `extism_pdk::plugin_fn` del
/// guest, manteniendo la lógica de negocio como una función pura
/// `Fn(Input) -> Output` fácil de testear sin WASM.
pub fn run(input: Input, handler: impl Fn(Input) -> Output) -> Output {
    handler(input)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn sample_output() -> Output {
        let mut params = Map::new();
        params.insert("product_id".to_string(), json!(42));
        params.insert("qty".to_string(), json!(3));
        Output::new()
            .with_operation(Operation::sql("create_sale_line", params))
            .with_event(Event::new("sale.line_added", json!({"qty": 3})))
    }

    #[test]
    fn input_is_transparent_json() {
        let inp = Input::new(json!({"cart": [1, 2, 3]}));
        let s = serde_json::to_string(&inp).unwrap();
        assert_eq!(s, r#"{"cart":[1,2,3]}"#);
        let back: Input = serde_json::from_str(&s).unwrap();
        assert_eq!(back, inp);
        assert_eq!(back.value(), &json!({"cart": [1, 2, 3]}));
    }

    #[test]
    fn output_round_trips() {
        let out = sample_output();
        let s = serde_json::to_string(&out).unwrap();
        let back: Output = serde_json::from_str(&s).unwrap();
        assert_eq!(back, out);
    }

    #[test]
    fn output_serializes_expected_shape() {
        let out = sample_output();
        let v: Value = serde_json::to_value(&out).unwrap();
        assert_eq!(v["operations"][0]["kind"], "sql");
        assert_eq!(v["operations"][0]["command"], "create_sale_line");
        assert_eq!(v["operations"][0]["params"]["qty"], 3);
        assert_eq!(v["events"][0]["name"], "sale.line_added");
    }

    #[test]
    fn output_defaults_fill_missing_fields() {
        let out: Output = serde_json::from_str("{}").unwrap();
        assert!(out.operations.is_empty());
        assert!(out.events.is_empty());

        let op: Operation =
            serde_json::from_str(r#"{"kind":"sql","command":"noop"}"#).unwrap();
        assert!(op.params.is_empty());
    }

    #[test]
    fn operation_sql_constructor_sets_kind() {
        let op = Operation::sql("do_thing", Map::new());
        assert_eq!(op.kind, "sql");
        assert_eq!(op.command, "do_thing");
    }

    #[test]
    fn run_helper_invokes_handler() {
        let out = run(Input::new(json!({"n": 2})), |inp| {
            let n = inp.value()["n"].as_i64().unwrap();
            Output::new().with_event(Event::new("doubled", json!(n * 2)))
        });
        assert_eq!(out.events.len(), 1);
        assert_eq!(out.events[0].payload, json!(4));
    }
}
