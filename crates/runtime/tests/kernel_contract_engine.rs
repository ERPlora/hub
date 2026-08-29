//! `contracts/kernel/engine.snapshot` ≡ the declarative engine every module programs against —
//! ERPlora/hub#1235.
//!
//! Regression test for ERPlora/hub#1235. A module's SQL is written against the parameters the
//! runtime injects, the `hub.*` queries the core answers, the row gates it enforces and the
//! migration kinds it accepts. None of that lived anywhere a reviewer could see it change, so a
//! parameter could be renamed or a gate widened «de paso». Now it is a file, generated here.
//!
//! Sources, in the order the sections appear:
//!
//! - `[system_params]` — a REAL call to `erplora_runtime::system_params`, not a copy of its keys.
//! - `[core_queries]` — `hub_users::CORE_QUERIES`, the reserved `hub.*` namespace.
//! - `[capabilities]` — `CapabilityKind::ALL`, cross-checked against `schemas/module.schema.json`
//!   so a capability cannot exist in one and not the other.
//! - `[migration_not_expand]` — `migration_guard::NOT_EXPAND`, the verbs that take a migration
//!   out of `expand` (hub#1163).
//! - `[command_origins]`, `[migration_kinds]`, `[row_gates]` — read from the runtime's own source,
//!   because the items are `pub(crate)` and opening them for a test would widen the very surface
//!   this contract is closing.
//!
//! Update: `UPDATE_KERNEL_CONTRACT=1 cargo test -p erplora-runtime --test kernel_contract_engine`.

use std::collections::BTreeSet;

use erplora_db::Params;
use erplora_runtime::manifest::CapabilityKind;
use erplora_runtime::migration_guard::Kind;
use erplora_runtime::RequestContext;
use serde_json::json;

#[path = "support/kernel_snapshot.rs"]
mod kernel_snapshot;
#[path = "support/rust_source.rs"]
mod rust_source;

use rust_source::{item_members, runtime_source};

#[test]
fn engine_snapshot_matches_the_runtime_hub1235() {
    kernel_snapshot::assert_snapshot("engine.snapshot", &generate());
}

/// The closed capability set cannot live in two places that disagree.
///
/// `CapabilityKind` is what the host GATES with; `schemas/module.schema.json` is what
/// `erplora validate` lets an author DECLARE. A capability in one and not the other is either a
/// permission nobody can ask for or one nobody enforces — and the second is the dangerous half.
#[test]
fn every_capability_the_host_gates_is_declarable_in_the_schema_hub1235() {
    let path =
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../schemas/module.schema.json");
    let schema: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(&path).expect("schemas/module.schema.json"))
            .expect("schema válido");
    let declarable: BTreeSet<String> = schema
        .pointer("/properties/capabilities/properties")
        .and_then(|p| p.as_object())
        .expect("el schema declara `capabilities.properties`")
        .keys()
        .cloned()
        .collect();
    let gated: BTreeSet<String> = CapabilityKind::ALL
        .iter()
        .map(|k| k.as_str().to_string())
        .collect();
    assert_eq!(
        gated,
        declarable,
        "el set cerrado de capabilities difiere entre el host y el schema.\n  \
         solo en el host: {:?}\n  solo en el schema: {:?}",
        gated.difference(&declarable).collect::<Vec<_>>(),
        declarable.difference(&gated).collect::<Vec<_>>(),
    );
}

/// `CapabilityKind::ALL` has to name every variant the enum declares, or the check above passes
/// on a short list. The enum is read from the source, which is the only place that cannot lie.
#[test]
fn capability_kind_all_names_every_variant_hub1235() {
    let variants = item_members(&runtime_source("manifest"), "pub enum", "CapabilityKind");
    assert!(
        !variants.is_empty(),
        "no se han leído las variantes de `CapabilityKind`"
    );
    assert_eq!(
        variants.len(),
        CapabilityKind::ALL.len(),
        "`CapabilityKind::ALL` lista {} capabilities y el enum declara {}: {:?}",
        CapabilityKind::ALL.len(),
        variants.len(),
        variants,
    );
}

/// The wire name of `expect_rows.op` is the lower-case of its variant, same as a migration kind:
/// asserted by parsing it, so the snapshot states what a manifest may actually write.
#[test]
fn every_expect_rows_op_parses_from_its_lowercase_name_hub1235() {
    for op in expect_rows_ops() {
        let parsed: Result<erplora_runtime::manifest::ExpectRowsOp, _> =
            serde_json::from_value(serde_json::Value::String(op.clone()));
        assert!(
            parsed.is_ok(),
            "`op: \"{op}\"` no lo acepta el motor de guardas de fila"
        );
    }
}

/// The wire name of a migration `kind` is the lower-case of its variant — asserted by parsing it,
/// so the snapshot below states what a manifest may actually write.
#[test]
fn every_migration_kind_parses_from_its_lowercase_name_hub1235() {
    for variant in migration_kinds() {
        let parsed: Result<Kind, _> =
            serde_json::from_value(serde_json::Value::String(variant.clone()));
        assert!(
            parsed.is_ok(),
            "`kind: \"{variant}\"` no lo acepta el guard de migraciones"
        );
    }
}

fn generate() -> String {
    let mut out = String::from(
        "# Motor declarativo del kernel — generado desde `crates/runtime/src/**`, NO editar a mano.\n\
         # `UPDATE_KERNEL_CONTRACT=1 cargo test -p erplora-runtime --test kernel_contract_engine`\n\
         # Contrato del kernel: ADR «El Hub se CIERRA como KERNEL».\n",
    );

    // Los parámetros que el runtime INYECTA en el payload del llamador: disponibles como `:name`
    // en todo el SQL de un módulo y no falsificables desde la UI.
    out.push_str("\n[system_params]\n");
    let ctx = RequestContext::new("hub-contract", "user-contract", Vec::<String>::new());
    let injected = erplora_runtime::system_params(&Params::new(), &ctx);
    for name in injected.keys().cloned().collect::<BTreeSet<String>>() {
        out.push_str(&format!("{name}\n"));
    }

    // El namespace RESERVADO `hub.*`: lo que el core contesta sin que ningún módulo lo declare.
    out.push_str("\n[core_queries]\n");
    for query in erplora_runtime::hub_users::CORE_QUERIES {
        out.push_str(&format!("hub.{query}\n"));
    }

    // El set CERRADO de permisos que un módulo puede pedirle al host (ADR-0079).
    out.push_str("\n[capabilities]\n");
    for kind in CapabilityKind::ALL {
        out.push_str(&format!("{}\n", kind.as_str()));
    }

    // Las tres puertas del dispatcher (`commands::Origin`): quién invoca un command.
    out.push_str("\n[command_origins]\n");
    for variant in item_members(&runtime_source("commands"), "pub(crate) enum", "Origin") {
        out.push_str(&format!("{variant}\n"));
    }

    // Lo que un módulo puede declarar que hace su migración (`migration_guard::Kind`).
    out.push_str("\n[migration_kinds]\n");
    for kind in migration_kinds() {
        out.push_str(&format!("{kind}\n"));
    }

    // Y los verbos que SACAN una migración de `expand` (hub#1163). Es la mitad del contrato de
    // actualización que un módulo programa contra: con `start-first` la versión anterior sigue
    // sirviendo contra el esquema ya migrado, así que lo que no es aditivo tiene que declararse.
    // Congelarlos aquí es lo que hace visible en una PR que la puerta se ha ensanchado.
    out.push_str("\n[migration_not_expand]\n");
    for verb in erplora_runtime::migration_guard::NOT_EXPAND {
        out.push_str(&format!("{verb}\n"));
    }

    // Las guardas de FILA de un command: sin ellas un UPDATE que no casa nada devuelve `200 ok`.
    out.push_str("\n[row_gates]\n");
    let command_fields = erplora_runtime::manifest::known_fields("commands.*")
        .expect("tabla de campos de `commands.*`");
    for gate in ["min_affected_rows", "expect_rows"] {
        assert!(
            command_fields.contains(&gate),
            "`{gate}` ya no es un campo de command"
        );
        out.push_str(&format!("commands.*.{gate}\n"));
    }
    let manifest_src = runtime_source("manifest");
    for field in item_members(&manifest_src, "pub struct", "ExpectRows") {
        out.push_str(&format!("commands.*.expect_rows.{field}\n"));
    }
    for op in expect_rows_ops() {
        out.push_str(&format!("commands.*.expect_rows.op = {op}\n"));
    }

    // El contrato de deduplicación del outbox (hub#1076): `emit[]` acepta el nombre plano de
    // siempre O un objeto que además nombra `dedup_key`, verificado deserializando las DOS formas
    // de verdad en vez de copiar su shape a mano.
    out.push_str("\n[emit]\n");
    let plain: erplora_runtime::manifest::EmitDef = serde_json::from_value(json!("sale.completed"))
        .expect("la forma string de `emit[]` tiene que seguir parseando");
    assert_eq!(plain.event(), "sale.completed");
    assert!(
        plain.dedup_key().is_none(),
        "la forma string nunca declara `dedup_key`"
    );
    out.push_str("commands.*.emit[] = string\n");
    let dedup_fields = item_members(&manifest_src, "pub struct", "EmitDedupKey");
    assert!(
        !dedup_fields.is_empty(),
        "no se han leído los campos de `EmitDedupKey`"
    );
    for field in &dedup_fields {
        out.push_str(&format!("commands.*.emit[].{field}\n"));
    }
    let keyed: erplora_runtime::manifest::EmitDef = serde_json::from_value(
        json!({"event": "sale.completed", "dedup_key": "wa_message_id"}),
    )
    .expect("la forma objeto de `emit[]` tiene que parsear");
    assert_eq!(keyed.event(), "sale.completed");
    assert_eq!(keyed.dedup_key(), Some("wa_message_id"));

    out
}

fn migration_kinds() -> Vec<String> {
    let variants = item_members(&runtime_source("migration_guard"), "pub enum", "Kind");
    assert!(
        !variants.is_empty(),
        "no se han leído las variantes de `migration_guard::Kind`"
    );
    variants.into_iter().map(|v| v.to_lowercase()).collect()
}

/// The operators `expect_rows.op` accepts, on the wire (`serde(rename_all = "lowercase")`).
fn expect_rows_ops() -> Vec<String> {
    let variants = item_members(&runtime_source("manifest"), "pub enum", "ExpectRowsOp");
    assert!(
        !variants.is_empty(),
        "no se han leído las variantes de `ExpectRowsOp`"
    );
    variants.into_iter().map(|v| v.to_lowercase()).collect()
}
