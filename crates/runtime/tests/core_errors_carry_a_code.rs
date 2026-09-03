//! Every refusal the core can hand a caller carries a STABLE CODE (hub#1241).
//!
//! This is the guard the family never left behind. Sixteen fixes — #39 → #273 → #762 → #768 →
//! #781 → #863 → #868 → #869 → #959 → #1070 → #1094 → #1102 → #1159 → #1178 → #1190 — all of the
//! same shape: a screen with nothing to branch on, so it painted the runtime's own sentence. Once
//! a refusal has a code, the shell translates it (ADR-0055) and the prose is only a log's fallback.
//!
//! hub#1074 + ADR-0412 made the mapping exhaustive; this test PINS it, and pins the two properties
//! a code has to have to be usable at all:
//!
//!   1. every `RuntimeError` variant maps to a non-empty code, and
//!   2. no variant falls back into the flat `"error"` bucket — the one that forced the UI to read
//!      `error.message` in the first place.
//!
//! The census is checked against the SOURCE of the enum (`include_str!` of `errors.rs`), not
//! against a number written here: a variant added tomorrow fails this test by name instead of
//! slipping through a count nobody updates.
use std::collections::BTreeSet;

use erplora_db::{testutil::fresh_db, DatabaseAdapter, Params};
use erplora_runtime::error_registry::error_code_of;
use erplora_runtime::errors::{AffectedKind, DemoLock};
use erplora_runtime::RuntimeError;

/// The `RuntimeError` enum as written. The ground truth of "which variants exist".
const ERRORS_SOURCE: &str = include_str!("../src/errors.rs");

/// Variant names declared by `pub enum RuntimeError`, read from the source.
fn declared_variants() -> BTreeSet<String> {
    let body = ERRORS_SOURCE
        .split_once("pub enum RuntimeError {")
        .expect("`pub enum RuntimeError {` is the enum this test is about")
        .1;
    let body = body.split("\n}\n").next().expect("the enum closes");
    body.lines()
        .filter_map(|line| {
            // A variant is declared at exactly one level of indentation: `    Name(…`, `    Name {`
            // or `    Name,`. Doc comments, attributes and field lines are all excluded by shape.
            let rest = line.strip_prefix("    ")?;
            if rest.starts_with(' ') || rest.starts_with("//") || rest.starts_with('#') {
                return None;
            }
            let name: String = rest
                .chars()
                .take_while(char::is_ascii_alphanumeric)
                .collect();
            let tail = &rest[name.len()..];
            let declares = tail.starts_with('(') || tail.starts_with(" {") || tail.starts_with(',');
            (!name.is_empty() && name.starts_with(char::is_uppercase) && declares).then_some(name)
        })
        .collect()
}

/// The variant an error IS. The match is EXHAUSTIVE on purpose: a new variant does not compile
/// until whoever adds it names it here, and the census below then has to grow a sample for it.
fn variant_of(e: &RuntimeError) -> &'static str {
    use RuntimeError as E;
    match e {
        E::Io(_) => "Io",
        E::Manifest { .. } => "Manifest",
        E::ManifestUnknownField { .. } => "ManifestUnknownField",
        E::CoreVersionTooOld { .. } => "CoreVersionTooOld",
        E::ManifestCoreFloorUnreadable { .. } => "ManifestCoreFloorUnreadable",
        E::Db(_) => "Db",
        E::QueryNotFound(_) => "QueryNotFound",
        E::ModuleNotInstalled { .. } => "ModuleNotInstalled",
        E::ModuleInactive { .. } => "ModuleInactive",
        E::CommandNotFound(_) => "CommandNotFound",
        E::InternalCommand(_) => "InternalCommand",
        E::MinAffectedRows { .. } => "MinAffectedRows",
        E::Domain { .. } => "Domain",
        E::PermissionDenied(_) => "PermissionDenied",
        E::RequiresElevation { .. } => "RequiresElevation",
        E::CapabilityDenied { .. } => "CapabilityDenied",
        E::MissingDependency { .. } => "MissingDependency",
        E::HasDependents { .. } => "HasDependents",
        E::DependencyTooOld { .. } => "DependencyTooOld",
        E::DependencyFloorUnreadable { .. } => "DependencyFloorUnreadable",
        E::DependencyCycle { .. } => "DependencyCycle",
        E::EventLoop => "EventLoop",
        E::EventNotDeclared { .. } => "EventNotDeclared",
        E::NotImplemented(_) => "NotImplemented",
        E::Wasm(_) => "Wasm",
        E::Native(_) => "Native",
        E::InvalidPayload { .. } => "InvalidPayload",
        E::Schema { .. } => "Schema",
        E::MissingRequiredParam { .. } => "MissingRequiredParam",
        E::UnknownFilter { .. } => "UnknownFilter",
        E::Notify(_) => "Notify",
        E::Print(_) => "Print",
        E::Storage(_) => "Storage",
        E::Certificate(_) => "Certificate",
        E::InvalidField { .. } => "InvalidField",
        E::ManifestRejected { .. } => "ManifestRejected",
        E::ReadUnavailable { .. } => "ReadUnavailable",
        E::ProtectsGuard { .. } => "ProtectsGuard",
        E::FiscalPrecondition { .. } => "FiscalPrecondition",
        E::InvalidTaxId { .. } => "InvalidTaxId",
        E::BusinessTaxIdFrozen { .. } => "BusinessTaxIdFrozen",
        E::HubCountryFrozen { .. } => "HubCountryFrozen",
        E::DemoLocked { .. } => "DemoLocked",
        E::MoneyUnitAmbiguous { .. } => "MoneyUnitAmbiguous",
        E::Other(_) => "Other",
    }
}

fn s(text: &str) -> String {
    text.to_string()
}

/// One instance of every variant. `Db` is the only one that cannot be built by hand (its inner
/// error belongs to the driver), so it comes from a REAL failing statement — which is also the
/// honest sample: it is the shape that leaked `sqlx` to a till before hub#1074.
fn census(db: RuntimeError) -> Vec<RuntimeError> {
    use RuntimeError as E;
    vec![
        E::Io(std::io::Error::other("disk gone")),
        E::Manifest {
            path: s("module.json"),
            source: serde_json::from_str::<i32>("nope").unwrap_err(),
        },
        E::ManifestUnknownField {
            module: s("sales"),
            path: s("commands.x.zzz"),
            core: s("1.0.0"),
        },
        E::CoreVersionTooOld {
            module: s("sales"),
            required: s("2.0.0"),
            core: s("1.0.0"),
        },
        E::ManifestCoreFloorUnreadable {
            module: s("sales"),
            declared: s("latest"),
        },
        db,
        E::QueryNotFound(s("sales.list")),
        E::ModuleNotInstalled {
            module: s("taxes"),
            operation: s("sales.complete_sale"),
        },
        E::ModuleInactive {
            module: s("taxes"),
            operation: s("sales.complete_sale"),
        },
        E::CommandNotFound(s("sales.nope")),
        E::InternalCommand(s("sales._relay")),
        E::MinAffectedRows {
            command: s("sales.confirm"),
            required: 1,
            affected: 0,
            kind: AffectedKind::NotFound,
        },
        E::Domain {
            code: s("sales.already_paid"),
            message: s("already paid"),
        },
        E::PermissionDenied(s("sales.write")),
        E::RequiresElevation {
            permission: s("sales.discount"),
        },
        E::CapabilityDenied {
            module: s("verifactu"),
            capability: s("certificate"),
        },
        E::MissingDependency {
            module: s("sales"),
            dep: s("taxes"),
        },
        E::HasDependents {
            module: s("taxes"),
            dependents: vec![s("sales")],
        },
        E::DependencyTooOld {
            module: s("sales"),
            dep: s("taxes"),
            required: s("2.0.0"),
            installed: s("1.0.0"),
        },
        E::DependencyFloorUnreadable {
            module: s("sales"),
            dep: s("taxes"),
            declared: s("new"),
        },
        E::DependencyCycle { module: s("sales") },
        E::EventLoop,
        E::EventNotDeclared {
            module: s("sales"),
            event: s("sales.sold"),
        },
        E::NotImplemented("the drawer"),
        E::Wasm(s("trap")),
        E::Native(s("plugin failed")),
        E::InvalidPayload {
            name: s("sales.create"),
            detail: s("`total` is required"),
        },
        E::Schema {
            name: s("sales.create"),
            detail: s("not a schema"),
        },
        E::MissingRequiredParam {
            query: s("sales.list"),
            param: s("hub_id"),
        },
        E::UnknownFilter {
            query: s("sales.list"),
            param: s("colour"),
            accepted: vec![s("limit")],
        },
        E::Notify(s("smtp refused")),
        E::Print(s("no host")),
        E::Storage(s("read-only")),
        E::Certificate(s("bad password")),
        E::InvalidField {
            name: s("hub.users"),
            field: s("name"),
            reason: s("required"),
            detail: s("the name is required"),
        },
        E::ManifestRejected {
            module: s("sales"),
            at: s("roles[0]"),
            code: s("role_grants_admin"),
            detail: s("a module cannot grant admin"),
        },
        E::ReadUnavailable {
            query: s("taxes.rules.list"),
        },
        E::ProtectsGuard {
            declaring_module: s("cash_register"),
            protected_module: s("sales"),
            guard_query: s("cash_register.current_session"),
        },
        E::FiscalPrecondition {
            missing: vec!["business_tax_id"],
        },
        E::InvalidTaxId {
            code: "invalid_tax_id_control",
            message: s("control letter"),
        },
        E::BusinessTaxIdFrozen {
            frozen_to: s("B12345678"),
            since: s("2026-08-01"),
        },
        E::HubCountryFrozen {
            frozen_to: s("ES"),
            since: s("2026-08-01"),
        },
        E::DemoLocked {
            lock: DemoLock::FiscalIdentity,
        },
        // hub#1209: the half-migrated hub the euros→cents backfill refuses to guess about.
        E::MoneyUnitAmbiguous {
            cents: s("sales_sale.total"),
            euros: s("payments_payment.amount"),
        },
        E::Other(s("hasher failed")),
    ]
}

/// A `Db` error nobody had to fabricate: a statement against a table that is not there.
async fn real_db_error() -> RuntimeError {
    let db = fresh_db().await;
    let failure = db
        .query(
            "SELECT 1 FROM table_that_hub1241_never_created",
            &Params::new(),
        )
        .await
        .expect_err("a query against a table that does not exist has to fail");
    RuntimeError::from(failure)
}

#[tokio::test]
async fn core_errors_carry_a_code_hub1241() {
    let all = census(real_db_error().await);

    // 1 · The census really is one of EVERY variant — checked against the enum's own source, so a
    //     variant added tomorrow fails here by name instead of slipping past a hand-written count.
    let sampled: BTreeSet<String> = all.iter().map(|e| variant_of(e).to_string()).collect();
    let declared = declared_variants();
    assert!(
        declared.len() > 40,
        "the source parse found only {} variants — it stopped matching the enum's shape",
        declared.len()
    );
    let missing: Vec<&String> = declared.difference(&sampled).collect();
    assert!(
        missing.is_empty(),
        "these `RuntimeError` variants have no sample in this census, so nothing proves they carry \
         a code: {missing:?}"
    );
    assert_eq!(sampled.len(), all.len(), "the census repeats a variant");

    // 2 · Every one of them answers with a stable, machine-readable code.
    for error in &all {
        let name = variant_of(error);
        let code = error_code_of(error);
        assert!(
            !code.is_empty(),
            "`{name}` reaches a caller with an EMPTY code"
        );
        assert_ne!(
            code.as_ref(),
            "error",
            "`{name}` falls into the flat `error` bucket — the one that left a screen with nothing \
             to branch on but the prose (hub#1102)"
        );
        assert!(
            code.chars()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_' || c == '.'),
            "`{name}` publishes `{code}`, which is not a stable machine code (expected \
             `snake_case`, optionally namespaced with `.`)"
        );
    }
}

/// The two refusals hub#1190 and hub#1178 are about, at the level a SCREEN sees them.
///
/// hub#1190: a refused field travels as `field` + `reason` **beside** a stable code, so the shell
/// translates instead of painting the English sentence. hub#1178: the fiscal engine's own audit
/// rows are the same problem one layer up — a message with no code cannot be translated by anybody.
#[tokio::test]
async fn a_refused_field_travels_as_data_not_as_prose_hub1190() {
    let refusal = RuntimeError::InvalidField {
        name: s("hub.roles"),
        field: s("role_key"),
        reason: s("immutable"),
        detail: s("role `admin` is a base role of the hub"),
    };
    assert_eq!(error_code_of(&refusal).as_ref(), "invalid_field");

    let RuntimeError::InvalidField { field, reason, .. } = &refusal else {
        unreachable!("the variant is built two lines above");
    };
    // The pair the shell keys its catalogue on. Reading the sentence instead is what ADR-0055
    // forbids and what made «the name is required» reach a hub in Spanish.
    assert_eq!((field.as_str(), reason.as_str()), ("role_key", "immutable"));
}
