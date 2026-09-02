//! # erplora-verifactu
//!
//! Motor fiscal **VeriFactu** (RD 1007/2023) como **plugin nativo first-party**
//! ([ADR-0009]): cadena de hash SHA-256 encadenada por `(hub_id, issuer_nif, environment)`
//! (ADR-0202 guarda R4: `production` y `testing` son dos cadenas paralelas independientes),
//! construcción del XML SOAP y transmisión a la AEAT con TLS mutua (PKCS#12).
//!
//! Es la "segunda clase de módulo" del sistema: el SQL declarativo y la UI del módulo
//! `verifactu` siguen el modelo normal; SOLO este motor va horneado en el runtime
//! (no es un `handler.wasm` descargable). Contrato idéntico al WASM Tier 2: nunca
//! escribe en la BD — lee vía [`NativeHost`] (solo SELECT) y devuelve *intenciones*
//! (ops sobre commands SQL internos del propio módulo: `verifactu._insert_record`,
//! `verifactu._insert_event`, `verifactu._enqueue_contingency`,
//! `verifactu._apply_transmission`) que el runtime valida y persiste en una transacción.
//!
//! Funciones (commands del manifest con `handler.type: "native"`):
//! - `create_record` (issue verifactu#2) — alta/anulación encadenada + QR.
//! - `transmit_record` (issue verifactu#3) — SOAP + TLS mutua + respuesta AEAT.
//! - `validate_chain` / `process_contingency_queue` — pendientes (issues #4 / #7).
//!
//! [ADR-0009]: ../../../architecture/00-overview/decision-log.md
use erplora_db::Params;
use erplora_runtime::certificate_refetch::RefetchSignal;
use erplora_runtime::native::{NativeHandler, NativeHost, PendingObligation};
use erplora_runtime::{Result, RuntimeError};
use erplora_wasm_host::{Event, Operation, Output};
use serde_json::{json, Value as Json};

pub mod aeat;
pub mod chain;
pub mod xsd;

// Engine split by function (hub#1405). `pub use <mod>::*` puts every item back at
// the crate root with its ORIGINAL visibility: the external API does not move.
mod config;
mod diagnostics;
mod engine;
mod events;
mod gateway;
mod ingest;
mod records;
mod recovery;
mod transmission;
mod util;
mod validation;

pub use config::*;
pub(crate) use diagnostics::*;
pub use engine::*;
pub use events::*;
pub(crate) use ingest::*;
pub use records::*;
pub(crate) use recovery::*;
pub(crate) use transmission::*;
pub(crate) use util::*;
pub(crate) use validation::*;
