//! **The flow contract, as bytes the hub can hand out** (hub#716).
//!
//! `schemas/flow.schema.json` is the frozen definition of what a flow document may say. It was a
//! file in the repository and nothing more: no HTTP route, no npm package. The visual editor
//! (pm#110) is a module installed from the marketplace and updated on its own clock (hub#516), so
//! the only thing it could do was **carry a copy** in its bundle — a photo of whichever core it
//! was built against, validating documents for a hub that may be one version ahead or behind.
//!
//! The runtime is already protected from drifting away from this file: `flows::def` is the
//! authority, and `crates/runtime/tests/flow_schema_matches_the_runtime.rs` goes red the day the
//! two lists disagree. What nothing checked was **schema ↔ consumer**.
//!
//! So the file is EMBEDDED here with [`include_str!`] and served from
//! `GET /api/hub/flows/schema`. That is the whole point of the constant: `include_str!` is
//! resolved by the compiler against the path in the source, so what a running hub serves is
//! byte-for-byte the file that was in the tree when its binary was built — the same one the
//! agreement test judges against `flows::def`. There is no second copy that could be edited, no
//! runtime file read that could find a stale schema next to the binary, and no deployment step
//! that could forget to ship it.
//!
//! The runtime still does **not** parse this to validate a flow. A till does not load 220 lines of
//! JSON Schema to judge a row; `flows::def` does that, and this is what the editor and the toolkit
//! judge against while somebody is writing.

use serde_json::Value;

/// The shipped contract, verbatim. Embedded at COMPILE time from `schemas/flow.schema.json`.
pub const FLOW_SCHEMA_JSON: &str = include_str!("../../../../schemas/flow.schema.json");

/// The contract as JSON, ready to go into a response envelope.
///
/// Parsed on every call rather than memoised: it is asked for once, when an editor opens, and a
/// `OnceLock` here would buy a hub nothing while making the failure mode («the schema shipped
/// broken») arrive at an arbitrary later moment instead of at the first request.
///
/// # Panics
///
/// If the embedded file is not valid JSON. That is not a runtime condition — the bytes are fixed
/// when the binary is built, and [`the_embedded_schema_is_the_contract`] fails the build's test
/// run before any hub could see it.
pub fn flow_schema() -> Value {
    serde_json::from_str(FLOW_SCHEMA_JSON)
        .expect("schemas/flow.schema.json is embedded at compile time and must be valid JSON")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flows::def::SCHEMA_VERSION;

    /// The embedded bytes parse, and they are the flow contract rather than some other schema that
    /// happened to be at that path. `$id` is the cheap identity check; `schema_version` being
    /// pinned to the version the runtime enforces is the one that matters — a schema that allowed
    /// a version this core refuses would have the editor writing documents the hub rejects.
    #[test]
    fn the_embedded_schema_is_the_contract() {
        let schema = flow_schema();
        assert_eq!(
            schema["$id"],
            serde_json::json!("https://erplora.com/schemas/flow.schema.json"),
            "this is not the flow contract: {}",
            schema["$id"]
        );
        assert_eq!(
            schema["properties"]["schema_version"]["const"],
            serde_json::json!(SCHEMA_VERSION),
            "the embedded schema pins a document version this core does not enforce"
        );
    }

    /// The file is embedded, not read from disk at runtime. A hub is a container with one binary
    /// in it: a `std::fs::read` here would work on a developer's machine and hand every deployed
    /// hub a `404` — the exact class of failure that only shows up in production.
    #[test]
    fn the_contract_travels_inside_the_binary() {
        assert!(
            !FLOW_SCHEMA_JSON.is_empty(),
            "the embedded contract is empty"
        );
        assert!(
            FLOW_SCHEMA_JSON.contains("\"$schema\""),
            "the embedded bytes are not a JSON Schema document"
        );
    }
}
