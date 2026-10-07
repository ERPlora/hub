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

/// **La resolución de la regla de impuesto** (hub#295). Qué tipo se aplica a
/// `(país, región, categoría, fecha)` y cómo se califica la operación. Antes vivía copiada en
/// `taxes`, `sales` e `invoice` — y con ella la posibilidad de cobrar una cosa y declarar otra.
pub mod tax;
pub mod units;

/// **La lectura de un teléfono en E.164** (appointments#313). Un número tecleado de cualquier
/// forma, leído con las reglas de libphonenumber en el país del negocio. Antes vivía en el handler
/// de `customers`, y Citas necesitaba la misma lectura para la copia del teléfono de cada cita.
pub mod phone;

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

/// Business rejection returned by a handler (hub#139).
///
/// `code` is stable and namespaced (`<module>.<snake_case>`); the UI translates against it via
/// the module i18n catalog. `message` is the human fallback for clients without that translation
/// yet. The host validates the namespace before exposing it and aborts the whole transaction.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DomainError {
    pub code: String,
    pub message: String,
}

impl DomainError {
    pub fn new(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
        }
    }
}

/// Resultado de un handler WASM: el conjunto de **intenciones** a aplicar.
///
/// El host valida y ejecuta `operations` en orden dentro de una transacción y luego emite
/// `events`. `error`, si viene, aborta la transacción entera ANTES de aplicar nada (hub#139).
/// `result`, si viene, viaja al caller como el **valor devuelto** por el handler (hub#70) sin
/// mezclarse con las intenciones. Nunca contiene SQL crudo ni filas de BD.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct Output {
    /// Operaciones SQL (por nombre de command + params) a ejecutar.
    #[serde(default)]
    pub operations: Vec<Operation>,
    /// Eventos a emitir tras ejecutar las operaciones.
    #[serde(default)]
    pub events: Vec<Event>,
    /// Structured business rejection (hub#139). Absent in older guests; when present, the host
    /// discards `operations`/`events` and surfaces the code to the caller.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub error: Option<DomainError>,
    /// **Value the handler RETURNS to the caller** (hub#70). Absent in older guests.
    ///
    /// Until this field existed the guest's computation was discarded: a command could only
    /// describe writes, so anything the caller needed to *know* (`schedules.is_open`, the id of
    /// the sale just created) had to be recomputed client-side over rows the caller itself
    /// supplied — which means the caller could forge it. That is a security property, not a
    /// convenience: the answer must come from the sandboxed handler over host-provided data.
    ///
    /// It is **not** an operation and **not** an event: it is never persisted, never emitted, and
    /// never contributes an id to `new_ids`. `Some(Value::Null)` ("no match") is a real answer and
    /// differs from `None` ("this handler returns nothing"). The host caps its serialised size and
    /// **rejects** an oversized result instead of truncating it (see
    /// `erplora_runtime::commands::MAX_RESULT_BYTES`): a silently shortened authoritative answer is
    /// worse than no answer.
    #[serde(
        default,
        deserialize_with = "deserialize_present_result",
        skip_serializing_if = "Option::is_none"
    )]
    pub result: Option<Value>,
}

/// Keeps `"result": null` distinguishable from an absent `result`.
///
/// Plain `Option<Value>` collapses both to `None` (serde reads a JSON `null` as "no value"), which
/// would erase the difference between *"the handler answers: nothing matched"* and *"this handler
/// returns nothing"* the moment the output crossed the host↔guest wire. `#[serde(default)]` still
/// covers the absent case, so an old guest that never writes the key keeps deserialising.
fn deserialize_present_result<'de, D>(deserializer: D) -> Result<Option<Value>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    Value::deserialize(deserializer).map(Some)
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

    /// Rejects the command with a stable domain error. The host will not apply any operation or
    /// event present in this same output (hub#139).
    pub fn with_error(mut self, error: DomainError) -> Self {
        self.error = Some(error);
        self
    }

    /// Returns a value to the caller (hub#70), on top of whatever operations/events this output
    /// also carries. Setting it twice keeps the last value.
    pub fn with_result(mut self, result: impl Into<Value>) -> Self {
        self.result = Some(result.into());
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
    fn output_round_trips_a_domain_error() {
        // hub#139: a business rejection is a normal guest output, not a trap. The struct must
        // survive the host<->guest JSON boundary intact.
        let out = Output::new().with_error(DomainError::new(
            "inventory.insufficient_stock",
            "Not enough stock",
        ));
        let back: Output = serde_json::from_slice(&serde_json::to_vec(&out).unwrap()).unwrap();
        assert_eq!(back.error, out.error);
        assert_eq!(
            back.error.as_ref().unwrap().code,
            "inventory.insufficient_stock"
        );
    }

    #[test]
    fn error_field_is_backwards_compatible_with_old_guests_and_hosts() {
        // Old guests only serialize operations/events: the field must default to None…
        let out: Output = serde_json::from_str("{}").unwrap();
        assert!(out.error.is_none());
        // …and an Output without a rejection must not emit an `error` key at all, so old hosts
        // (which ignore unknown fields anyway) see exactly the same JSON as before.
        let v: Value = serde_json::to_value(sample_output()).unwrap();
        assert!(
            v.get("error").is_none(),
            "absent rejection must not serialize an `error` key"
        );
    }

    // ── hub#70: the result channel ───────────────────────────────────────────────────────────

    #[test]
    fn output_round_trips_a_result() {
        // A handler must be able to RETURN a computed value (`schedules.is_open`), not only
        // intentions. Without it the caller supplies the rows and can forge the answer.
        let out = Output::new().with_result(json!({"open": true, "closes_at": "20:00"}));
        let back: Output = serde_json::from_slice(&serde_json::to_vec(&out).unwrap()).unwrap();
        assert_eq!(back.result, out.result);
        assert_eq!(back.result.unwrap()["open"], json!(true));
    }

    #[test]
    fn result_accepts_any_json_shape_including_a_bare_scalar() {
        // `is_open` answers a bool, `bulk_create_special_days` a list, a checkout an object.
        for value in [json!(true), json!([1, 2, 3]), json!("ok"), json!(null)] {
            let out = Output::new().with_result(value.clone());
            let back: Output = serde_json::from_str(&serde_json::to_string(&out).unwrap()).unwrap();
            assert_eq!(back.result, Some(value));
        }
    }

    #[test]
    fn result_is_independent_of_operations_and_events() {
        // The result is NOT an operation and NOT an event: a handler can both write and answer.
        let out = sample_output().with_result(json!({"sale_id": "s-1"}));
        let v: Value = serde_json::to_value(&out).unwrap();
        assert_eq!(v["operations"].as_array().unwrap().len(), 1);
        assert_eq!(v["events"].as_array().unwrap().len(), 1);
        assert_eq!(v["result"]["sale_id"], "s-1");
    }

    #[test]
    fn result_field_is_backwards_compatible_with_old_guests_and_hosts() {
        // Same versioning pattern as `error` (hub#139): additive, `#[serde(default)]`, and absent
        // unless set — an old guest keeps deserialising, and an old host sees the same JSON.
        let out: Output = serde_json::from_str(r#"{"operations":[],"events":[]}"#).unwrap();
        assert!(out.result.is_none());
        let v: Value = serde_json::to_value(sample_output()).unwrap();
        assert!(
            v.get("result").is_none(),
            "a handler that returns nothing must not serialize a `result` key"
        );
    }

    #[test]
    fn a_null_result_is_distinguishable_from_no_result() {
        // `Some(Json::Null)` is an answer ("no match"), `None` is "this handler answers nothing".
        let explicit = Output::new().with_result(Value::Null);
        assert_eq!(explicit.result, Some(Value::Null));
        let v: Value = serde_json::to_value(&explicit).unwrap();
        assert!(v.get("result").is_some(), "an explicit null must be sent");
        assert!(v["result"].is_null());
        // …and it must survive the wire as an answer, not collapse back into "no answer".
        let back: Output = serde_json::from_str(r#"{"result":null}"#).unwrap();
        assert_eq!(back.result, Some(Value::Null));
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
