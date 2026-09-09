//! **The rules the CUSTOMER writes** (ERPlora/hub#1701, ADR-0476).
//!
//! Design doc: `architecture/hub/policies.md`. The as-built order of the funnel's gates lives in
//! `architecture/hub/runtime-dispatcher.md` §2.0 and is **not copied here** — it is referenced,
//! which is exactly the anti-regression guard architecture#733 put in after ADR-0476 wrote that
//! order from memory and published it inverted.
//!
//! # The three pieces
//!
//! 1. **The module declares the checkpoint**, by folder convention:
//!    `<module>/policies/<name>.checkpoint.json`. Not a new manifest key: the root is
//!    `additionalProperties: false` (ADR-0286) and a new key would put a hub version floor on every
//!    module that declared it (same reasoning as `flows/`, ADR-0463).
//! 2. **The owner writes the rule** into `_policy`, with the **already frozen** condition language
//!    of the flows ([`crate::flows::Condition`], nine operators in AND, a closed set). No new DSL
//!    ships.
//! 3. **The runtime applies it** at one exact point of the funnel, [`enforce`], called from
//!    [`crate::commands::execute_at`] after the schema block and before the tier fork.
//!
//! # Why [`enforce`] does NOT receive the database
//!
//! Not an oversight: it is the **bounded-cost** guard written into the type system. The gate runs
//! on **every** command, and one read per command is paid on every sale — on top of holding the
//! runtime's shared guard, which is fair (`crates/server/src/boot.rs`), so a slow reader leaves the
//! pending writer and the readers behind it waiting. A signature without `db` makes it
//! **impossible** to add I/O here in passing; the rows come from [`PolicyIndex`], an in-memory map
//! refreshed at boot and on every write of the CRUD.
//!
//! # Fails CLOSED, and why it does not inherit the neighbour's behaviour
//!
//! `protects` — the gate next door — degrades **open**, and for its case that is correct: a till
//! that stops charging because of a broken read is a worse failure than one sale slipping through.
//! A policy is the opposite: it exists to **forbid**, so degrading it open in silence turns it into
//! decoration. Here, what cannot be evaluated **DENIES** (`policies.md` §6.1).
//!
//! 🔴 And the missing fact is detected by **checking presence BEFORE evaluating**, never by reading
//! the result of the evaluation: [`crate::flows::Condition::matches`] returns a bare `bool` and an
//! absent path yields `false`, **the same value** as «the condition did not match». A gate acting
//! on that `bool` could not tell them apart, and since a policy is «if it matches → `block`», the
//! missing fact would make it **not fire and let the command through**: a silent fail-open through
//! the back door.
use std::collections::{BTreeMap, HashMap};
use std::path::Path;
use std::sync::RwLock;

use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::flows::def::{resolve_path, Op};
use crate::flows::Condition;
use crate::manifest::Manifest;
use crate::registry::{new_id, now_rfc3339};

/// Suffix of the documents in the `policies/` folder.
const CHECKPOINT_SUFFIX: &str = ".checkpoint.json";

/// The document cannot be read out of the package.
pub const DISCARD_UNREADABLE_DOCUMENT: &str = "unreadable_document";
/// The document does not read as JSON, or its fields do not have the shape of the contract.
pub const DISCARD_INVALID_DOCUMENT: &str = "invalid_document";
/// The `command` is not declared by this module's manifest.
pub const DISCARD_COMMAND_NOT_DECLARED: &str = "command_not_declared";
/// The `command` belongs to ANOTHER module. A module only speaks in its own namespace (hub#139,
/// hub#351); stopping another module's commands already has its declared and consented door, and
/// that door is `protects` (hub#775).
pub const DISCARD_FOREIGN_COMMAND: &str = "foreign_command";
/// The command declares no payload schema, so there are no `facts` it could supply.
pub const DISCARD_COMMAND_WITHOUT_SCHEMA: &str = "command_without_schema";
/// A `fact` whose root the command's schema does not declare. **This is the valve** that makes the
/// gate's fail-closed denial safe: it shows up at install time, not in the middle of a sale.
pub const DISCARD_FACT_NOT_DECLARED: &str = "fact_not_declared";
/// A `fact` that is not a dotted path of the frozen language (`lines[].x`, `a..b`, empty).
pub const DISCARD_INVALID_FACT_PATH: &str = "invalid_fact_path";
/// The checkpoint declares no `fact`: there is nothing to reason about.
pub const DISCARD_NO_FACTS: &str = "no_facts";
/// An `outcome` outside the closed vocabulary (`block`, `elevate:<permission>`).
pub const DISCARD_UNKNOWN_OUTCOME: &str = "unknown_outcome";
/// The checkpoint declares no `outcome`.
pub const DISCARD_NO_OUTCOMES: &str = "no_outcomes";
/// Another checkpoint of the module already hooked onto that command.
pub const DISCARD_DUPLICATE_COMMAND: &str = "duplicate_command";

/// A checkpoint declared by a module: where the owner may put a rule, and what data it may reason
/// about.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct PolicyCheckpoint {
    /// `<module>/<name>` — the stable name a `_policy` row references it by. The same shape as
    /// `_flow.template_ref` (v60), and for the same reason: it is what the module already knows
    /// about itself and it does not change between its releases.
    pub id: String,
    pub module_id: String,
    /// The command this checkpoint gates. Always one of the module's own.
    pub command: String,
    /// The facts it may reason about: dotted paths inside the command's payload, **already
    /// validated, defaulted and coerced** (the gate runs after that block).
    pub facts: Vec<String>,
    /// The vocabulary this checkpoint accepts. `block` · `elevate:<permission>`.
    pub outcomes: Vec<String>,
}

/// What the `policies/` folder contributed and what it did **not**, with the reason (same contract
/// as [`crate::manifest::FlowTemplateScan`], hub#1649: best-effort is not mute).
#[derive(Debug, Clone, Default, serde::Serialize)]
pub struct CheckpointScan {
    pub checkpoints: Vec<PolicyCheckpoint>,
    pub discards: Vec<CheckpointDiscard>,
}

#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct CheckpointDiscard {
    /// The document's name (the part before `.checkpoint.json`).
    pub name: String,
    pub code: String,
    pub detail: String,
}

impl CheckpointScan {
    pub fn is_empty(&self) -> bool {
        self.checkpoints.is_empty() && self.discards.is_empty()
    }

    fn discard(&mut self, name: &str, code: &'static str, detail: String) {
        self.discards.push(CheckpointDiscard {
            name: name.to_string(),
            code: code.to_string(),
            detail,
        });
    }
}

/// The document exactly as it travels in the package.
#[derive(serde::Deserialize)]
struct CheckpointDoc {
    command: String,
    #[serde(default)]
    facts: Vec<String>,
    #[serde(default)]
    outcomes: Vec<String>,
}

/// Reads `<dir>/policies/*.checkpoint.json` and returns what this hub is going to offer.
///
/// **Best-effort and not mute**: a broken third-party package cannot stop the hub from coming up
/// (this runs on every boot through `rehydrate_installed`), but whatever is discarded comes out
/// with its code.
///
/// The result is **ordered by document name** so that two boots give the same thing: which of two
/// checkpoints over the same command survives depends on that order.
pub fn scan_checkpoints(dir: &Path, manifest: &Manifest) -> CheckpointScan {
    let mut scan = CheckpointScan::default();
    let Ok(entries) = std::fs::read_dir(dir.join("policies")) else {
        return scan;
    };

    // 1st pass: collect the documents by name. `BTreeMap` = stable order by bytes, which is what
    // makes the `DISCARD_DUPLICATE_COMMAND` tie-break deterministic.
    let mut docs: BTreeMap<String, std::path::PathBuf> = BTreeMap::new();
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_file() {
            continue;
        }
        let Some(name) = path.file_name().and_then(|s| s.to_str()) else {
            continue;
        };
        if let Some(stem) = name.strip_suffix(CHECKPOINT_SUFFIX) {
            if !stem.is_empty() {
                docs.insert(stem.to_string(), path);
            }
        }
    }

    // Cache of the schemas already read: two checkpoints of the same command do not re-read the
    // file.
    let mut schema_props: HashMap<String, Option<Vec<String>>> = HashMap::new();
    let mut taken: HashMap<String, String> = HashMap::new();

    for (name, path) in docs {
        let Ok(text) = std::fs::read_to_string(&path) else {
            scan.discard(
                &name,
                DISCARD_UNREADABLE_DOCUMENT,
                format!("`{name}{CHECKPOINT_SUFFIX}` no se puede leer del paquete"),
            );
            continue;
        };
        let doc = match serde_json::from_str::<CheckpointDoc>(&text) {
            Ok(doc) => doc,
            Err(err) => {
                scan.discard(
                    &name,
                    DISCARD_INVALID_DOCUMENT,
                    format!(
                        "`{name}{CHECKPOINT_SUFFIX}` no tiene la forma del contrato \
                         (`command`, `facts`, `outcomes`): {err}"
                    ),
                );
                continue;
            }
        };

        // (1) Namespace BEFORE anything else: another module's `command` is none of this
        // document's business, and telling it «you do not declare it» would send it to look at the
        // wrong file.
        if !is_own_command(&manifest.id, &doc.command) {
            scan.discard(
                &name,
                DISCARD_FOREIGN_COMMAND,
                format!(
                    "`{}` es un command de otro módulo. Un checkpoint solo gatea commands de \
                     `{}`; para parar los de otro está `protects`, que el módulo protegido declara",
                    doc.command, manifest.id
                ),
            );
            continue;
        }
        let Some(command) = manifest.commands.get(&doc.command) else {
            scan.discard(
                &name,
                DISCARD_COMMAND_NOT_DECLARED,
                format!("`{}` no es un command de este manifest", doc.command),
            );
            continue;
        };

        // (2) The vocabulary of consequences, closed.
        if doc.outcomes.is_empty() {
            scan.discard(
                &name,
                DISCARD_NO_OUTCOMES,
                "un checkpoint sin `outcomes` no admite ninguna norma".to_string(),
            );
            continue;
        }
        if let Some(bad) = doc.outcomes.iter().find(|o| Outcome::parse(o).is_none()) {
            scan.discard(
                &name,
                DISCARD_UNKNOWN_OUTCOME,
                format!(
                    "`{bad}` no es una consecuencia del vocabulario cerrado: `block` o \
                     `elevate:<permiso>`"
                ),
            );
            continue;
        }

        // (3) The facts. The valve of the fail-closed denial: if the command cannot supply them,
        // it shows up HERE — at install time — and not in the middle of a sale.
        if doc.facts.is_empty() {
            scan.discard(
                &name,
                DISCARD_NO_FACTS,
                "un checkpoint sin `facts` no da nada sobre lo que razonar".to_string(),
            );
            continue;
        }
        if let Some(bad) = doc.facts.iter().find(|f| !is_plain_path(f)) {
            scan.discard(
                &name,
                DISCARD_INVALID_FACT_PATH,
                format!(
                    "`{bad}` no es un camino punteado del lenguaje congelado de los flujos. El \
                     gate resuelve con `resolve_path`, que no entiende colecciones (`x[].y`): un \
                     hecho así no se podría leer NUNCA y la política denegaría siempre"
                ),
            );
            continue;
        }
        let props = schema_props
            .entry(doc.command.clone())
            .or_insert_with(|| command.schema.as_deref().and_then(|rel| schema_roots(dir, rel)));
        let Some(props) = props.as_ref() else {
            scan.discard(
                &name,
                DISCARD_COMMAND_WITHOUT_SCHEMA,
                format!(
                    "`{}` no declara un schema de payload legible, así que no hay `facts` que el \
                     command pueda aportar",
                    doc.command
                ),
            );
            continue;
        };
        if let Some(bad) = doc
            .facts
            .iter()
            .find(|f| !props.iter().any(|p| p == fact_root(f)))
        {
            scan.discard(
                &name,
                DISCARD_FACT_NOT_DECLARED,
                format!(
                    "`{bad}`: el schema de `{}` no declara `{}`. El gate DENIEGA si al ejecutar \
                     falta un hecho declarado, así que un hecho que el command no puede aportar se \
                     rechaza aquí y no en mitad de una venta",
                    doc.command,
                    fact_root(bad)
                ),
            );
            continue;
        }

        // (4) One command, one gate. Otherwise which rule applies would depend on directory order.
        if let Some(first) = taken.get(&doc.command) {
            scan.discard(
                &name,
                DISCARD_DUPLICATE_COMMAND,
                format!(
                    "`{}` ya lo gatea `{first}`. Dos checkpoints sobre el mismo command harían que \
                     la norma aplicada dependiese del orden del sistema de ficheros",
                    doc.command
                ),
            );
            continue;
        }
        taken.insert(doc.command.clone(), name.clone());
        scan.checkpoints.push(PolicyCheckpoint {
            id: format!("{}/{}", manifest.id, name),
            module_id: manifest.id.clone(),
            command: doc.command,
            facts: doc.facts,
            outcomes: doc.outcomes,
        });
    }
    scan
}

/// Does `command` belong to `module_id`'s namespace? Same criterion as the rest of the kernel: a
/// command's name starts with its module's id and a dot.
fn is_own_command(module_id: &str, command: &str) -> bool {
    command
        .strip_prefix(module_id)
        .is_some_and(|rest| rest.starts_with('.'))
}

/// The root of a dotted path: `order.total` → `order`.
fn fact_root(fact: &str) -> &str {
    fact.split('.').next().unwrap_or(fact)
}

/// Is it a dotted path [`resolve_path`] knows how to resolve? No empty segments and nothing that is
/// not an object key (the language does not understand indices or collections).
fn is_plain_path(path: &str) -> bool {
    !path.is_empty()
        && path.split('.').all(|s| {
            !s.is_empty()
                && s.chars()
                    .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
        })
}

/// The first-level properties of a command's JSON Schema. `None` if there is no readable schema or
/// if it declares no `properties` — in both cases there is nothing to validate the `facts` against.
fn schema_roots(dir: &Path, rel: &str) -> Option<Vec<String>> {
    let text = std::fs::read_to_string(dir.join(rel)).ok()?;
    let doc: Json = serde_json::from_str(&text).ok()?;
    let props = doc.get("properties")?.as_object()?;
    if props.is_empty() {
        return None;
    }
    Some(props.keys().cloned().collect())
}

/// The consequence the owner picks. **Closed vocabulary**: an unknown one is not guessed at.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Outcome {
    /// Do not allow it. Comes out through the domain error channel (ADR-0205) with the owner's
    /// message.
    Block,
    /// Ask the manager for it. **This core does not run it yet** (hub#1710): it is recognised so
    /// that a checkpoint declaring it does not lose its `block`, and writing such a policy is
    /// refused.
    Elevate(String),
}

impl Outcome {
    pub fn parse(raw: &str) -> Option<Self> {
        if raw == "block" {
            return Some(Outcome::Block);
        }
        raw.strip_prefix("elevate:")
            .filter(|p| !p.is_empty())
            .map(|p| Outcome::Elevate(p.to_string()))
    }

    pub fn as_str(&self) -> String {
        match self {
            Outcome::Block => "block".to_string(),
            Outcome::Elevate(p) => format!("elevate:{p}"),
        }
    }
}

/// `warn` warns; `enforce` forbids. The mandatory ramp before putting a rule into force — what
/// Stripe Radar calls *Review*, and for the same reason: a rule that blocks wrongly in a POS
/// **stops the till**, and the owner wrote it without being able to try it against their real day.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    Warn,
    Enforce,
}

impl Mode {
    pub fn parse(raw: &str) -> Option<Self> {
        match raw {
            "warn" => Some(Mode::Warn),
            "enforce" => Some(Mode::Enforce),
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Mode::Warn => "warn",
            Mode::Enforce => "enforce",
        }
    }
}

/// One of the owner's rules exactly as it is stored, ready to be evaluated **without touching the
/// database**.
///
/// It does not carry the `facts`: those belong to the **checkpoint**, and the checkpoint lives in
/// the module's package. Reading them from the Registry at the moment of applying — instead of
/// freezing them here at load time — is what makes uninstalling the module stop applying its rules
/// and reinstalling it put them back in force, without anyone having to remember to refresh
/// anything.
#[derive(Debug, Clone)]
pub struct ActivePolicy {
    pub id: String,
    pub hub_id: String,
    pub checkpoint: String,
    /// `None` = the stored condition cannot be read by this core → **denies** (fail-closed).
    pub condition: Option<Condition>,
    /// `None` = this core does not know how to run the stored consequence → **denies**.
    pub outcome: Option<Outcome>,
    pub message: String,
    pub mode: Mode,
}

/// Ceiling of rules per checkpoint (**bounded-cost** guard). The gate compares in memory, but the
/// comparison is still work per command: with no ceiling, a hub with a hundred rules over
/// `sales.complete_sale` pays for them on every sale.
pub const MAX_POLICIES_PER_CHECKPOINT: usize = 20;

/// The in-memory index [`enforce`] reads from: `checkpoint → active rules`.
///
/// It lives in the [`crate::registry::Registry`] for the same reason `demo_hub` lives there: it is
/// the only authority that reaches `commands::execute_at` through **every** path (HTTP, public API,
/// assistant, outbox relay, scheduler) and that no caller can fabricate. One more parameter on the
/// signature would be a label the next new door could forget to attach, and forgetting it here
/// means leaving the gate open.
///
/// 🔴 **It is indexed by CHECKPOINT and not by command, and that is not a detail.** With an index
/// by command, the map would depend on two things that change through different paths — the
/// `_policy` rows and the installed modules — so it would have to be rebuilt in `install`,
/// `update`, `activate`, `deactivate`, `uninstall` and the boot re-hydration too: **eight places**
/// where forgetting one line leaves rules unapplied without saying anything. Indexed by checkpoint
/// it depends only on the rows, so it is refreshed where the rows change (boot and every write of
/// the CRUD) and the Registry resolves the rest at the moment of applying.
#[derive(Debug, Default)]
pub struct PolicyIndex {
    by_checkpoint: RwLock<HashMap<String, Vec<ActivePolicy>>>,
}

impl PolicyIndex {
    /// Replaces the whole index. Called by boot and by **every write of the CRUD**: a rule the
    /// owner has just saved has to be in force on the next sale, not on the next restart.
    pub fn replace(&self, by_checkpoint: HashMap<String, Vec<ActivePolicy>>) {
        match self.by_checkpoint.write() {
            Ok(mut guard) => *guard = by_checkpoint,
            // A poisoned `RwLock` means a thread panicked while holding the guard. There is no
            // state to save here — the index is rebuilt whole — so it recovers instead of
            // propagating the panic to boot.
            Err(poisoned) => *poisoned.into_inner() = by_checkpoint,
        }
    }

    /// The rules of one checkpoint. Empty = there is no gate and nothing is paid for.
    fn for_checkpoint<T>(&self, checkpoint: &str, f: impl FnOnce(&[ActivePolicy]) -> T) -> T {
        let guard = match self.by_checkpoint.read() {
            Ok(guard) => guard,
            Err(poisoned) => poisoned.into_inner(),
        };
        f(guard.get(checkpoint).map(Vec::as_slice).unwrap_or(&[]))
    }

    /// How many rules are in force in total. For `/readyz` and the tests; not on the hot path.
    pub fn len(&self) -> usize {
        let guard = match self.by_checkpoint.read() {
            Ok(guard) => guard,
            Err(poisoned) => poisoned.into_inner(),
        };
        guard.values().map(Vec::len).sum()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

/// Domain code (ADR-0205) of a command a business rule **forbids**. Stable and namespaced; the text
/// the person reads is the one the owner wrote and it travels in `message`.
pub const ERR_BLOCKED: &str = "policy.blocked";
/// A fact the checkpoint declares is missing. **Denies** — see §6.1 of the doc.
pub const ERR_FACT_MISSING: &str = "policy.fact_missing";
/// The stored rule names a consequence this core does not know how to run (e.g. `elevate:` on a hub
/// that was rolled back). **Denies**: a policy that cannot be applied is not ignored.
pub const ERR_OUTCOME_NOT_AVAILABLE: &str = "policy.outcome_not_available";
/// The stored condition cannot be read by this core. **Denies**, for the same reason.
pub const ERR_CONDITION_UNREADABLE: &str = "policy.condition_unreadable";
/// The condition judges the CLOCK (`within_last`, hub#1713) and a policy's scope carries none.
/// **Denies** when stored, and is refused when written: the same two moments as
/// [`ERR_OUTCOME_NOT_AVAILABLE`], and for the same reason — reading the bare `false` that a window
/// answers without a clock would let a rule the owner wrote to block silently never fire.
pub const ERR_CONDITION_NEEDS_CLOCK: &str = "policy.condition_needs_clock";

// ── Codes of the WRITE door (the CRUD) ────────────────────────────────────────────────────────
/// There is no rule with that id in this hub.
pub const ERR_NOT_FOUND: &str = "policy.not_found";
/// The checkpoint already holds [`MAX_POLICIES_PER_CHECKPOINT`] rules.
pub const ERR_TOO_MANY: &str = "policy.too_many";
/// No installed and active module offers that checkpoint.
pub const ERR_CHECKPOINT_NOT_FOUND: &str = "policy.checkpoint_not_found";
/// The condition names a datum the checkpoint does not declare as a `fact`.
pub const ERR_FACT_NOT_DECLARED: &str = "policy.fact_not_declared";
/// The checkpoint does not offer that consequence.
pub const ERR_OUTCOME_NOT_OFFERED: &str = "policy.outcome_not_offered";
/// A `block` with no message would be a mute refusal.
pub const ERR_MESSAGE_REQUIRED: &str = "policy.message_required";
/// `mode` outside `warn`/`enforce`.
pub const ERR_UNKNOWN_MODE: &str = "policy.unknown_mode";
/// An empty condition matches ALWAYS.
pub const ERR_EMPTY_CONDITION: &str = "policy.empty_condition";

fn domain(code: &str, message: String) -> RuntimeError {
    RuntimeError::Domain {
        code: code.to_string(),
        message,
    }
}

/// **The gate.** Runs in [`crate::commands::execute_at`] after the schema block and before the tier
/// fork — see `runtime-dispatcher.md` §2.0 for the full order and `policies.md` §4.3 for why that
/// point is not negotiable.
///
/// Without `db` on purpose: see the module note. `payload` is the **already validated, defaulted and
/// coerced** one, which is what makes a missing fact really mean «the module did not supply it» and
/// not «the caller omitted it and the schema was going to fill it in».
///
/// Returns the verdicts of `mode: warn` — the ones that warned without forbidding — so the ramp is
/// observable without the gate writing to the database.
pub fn enforce(
    registry: &crate::registry::Registry,
    command: &str,
    payload: &Params,
    hub_id: &str,
) -> Result<Vec<Verdict>> {
    // No active module declares a checkpoint over this command: there is no gate, and the only
    // thing paid for is one map lookup.
    let Some(checkpoint) = registry.policy_checkpoint_for_command(command) else {
        return Ok(Vec::new());
    };
    registry.policies.for_checkpoint(&checkpoint.id, |policies| {
        if policies.is_empty() {
            return Ok(Vec::new());
        }
        let scope = Json::Object(payload.clone().into_iter().collect());
        let mut warned = Vec::new();
        for policy in policies {
            // Tenancy before anything else: the rules belong to the hub that wrote them (row
            // contract).
            if policy.hub_id != hub_id {
                continue;
            }
            match evaluate(policy, &checkpoint.facts, &scope) {
                Some(refusal) if policy.mode == Mode::Enforce => return Err(refusal.into_error()),
                Some(refusal) => {
                    // `warn`: it is logged and NEVER forbids. It is the ramp the owner uses to see
                    // what would fire before putting it into force.
                    eprintln!(
                        "[policy] warn {} ({}) sobre `{command}`: {} — {}",
                        refusal.policy_id, refusal.checkpoint, refusal.code, refusal.message
                    );
                    warned.push(refusal);
                }
                None => {}
            }
        }
        Ok(warned)
    })
}

/// What a rule ruled. Returned so that `warn` is observable without the gate writing to the
/// database (bounded-cost guard).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Verdict {
    pub policy_id: String,
    pub checkpoint: String,
    pub code: &'static str,
    pub message: String,
}

impl Verdict {
    fn into_error(self) -> RuntimeError {
        RuntimeError::Domain {
            code: self.code.to_string(),
            message: self.message,
        }
    }
}

/// Does the condition judge the CLOCK? (`within_last`, hub#1713)
///
/// [`Condition::matches`] reads the instant from `now.iso` **in the scope**, and a policy's scope is
/// the command payload — there is no clock in it. Without one the window answers a bare `false`,
/// the very same `false` as «it did not match», so a `block` the owner wrote would silently never
/// fire. Asked as its own question, and never read off the result, for the same reason the presence
/// of the facts is checked BEFORE evaluating.
///
/// 🔴 The `match` is exhaustive **on purpose and with no `_` arm**: an operator added to the frozen
/// language stops compiling right here until someone says whether it judges the clock. That is what
/// keeps the next `within_last` from landing in a policy as a silent fail-open, the way this one
/// did.
fn needs_clock(condition: &Condition) -> bool {
    condition.0.values().flatten().any(|(op, _)| match op {
        Op::WithinLast => true,
        Op::Eq | Op::Neq | Op::In | Op::Exists | Op::Contains | Op::Gt | Op::Gte | Op::Lt
        | Op::Lte => false,
    })
}

/// `Some(v)` = this rule says NO. `None` = it lets it through.
///
/// 🔴 The order matters and it is half the fix: **first the presence of the declared facts**, and
/// only then the condition. [`Condition::matches`] returns a bare `bool` and an absent path yields
/// `false`, exactly like «it did not match»; reading that `bool` to decide would make a missing fact
/// let the command through.
fn evaluate(policy: &ActivePolicy, facts: &[String], scope: &Json) -> Option<Verdict> {
    let refuse = |code: &'static str, message: String| {
        Some(Verdict {
            policy_id: policy.id.clone(),
            checkpoint: policy.checkpoint.clone(),
            code,
            message,
        })
    };
    for fact in facts {
        if resolve_path(fact, scope).filter(|v| !v.is_null()).is_none() {
            return refuse(
                ERR_FACT_MISSING,
                format!(
                    "la norma «{}» necesita `{fact}` y el comando no lo aporta",
                    policy.message
                ),
            );
        }
    }
    let Some(condition) = &policy.condition else {
        return refuse(
            ERR_CONDITION_UNREADABLE,
            format!("la norma «{}» no se puede leer con este core", policy.message),
        );
    };
    if needs_clock(condition) {
        return refuse(
            ERR_CONDITION_NEEDS_CLOCK,
            format!(
                "la norma «{}» juzga el reloj y este hub todavía no sabe aplicarlo aquí",
                policy.message
            ),
        );
    }
    let Some(outcome) = &policy.outcome else {
        return refuse(
            ERR_OUTCOME_NOT_AVAILABLE,
            format!(
                "la norma «{}» pide una consecuencia que este hub no sabe aplicar",
                policy.message
            ),
        );
    };
    if !condition.matches(scope) {
        return None;
    }
    match outcome {
        Outcome::Block => refuse(ERR_BLOCKED, policy.message.clone()),
        // An `elevate:` that reached the table (rolled-back hub) is not ignored: it denies.
        Outcome::Elevate(_) => refuse(
            ERR_OUTCOME_NOT_AVAILABLE,
            format!(
                "la norma «{}» pide una consecuencia que este hub no sabe aplicar",
                policy.message
            ),
        ),
    }
}

// ─────────────────────────────────────────────────────────────────────────────────────────────
// The WRITE door: what the owner stores in `_policy`
// ─────────────────────────────────────────────────────────────────────────────────────────────

/// A rule as the API sees it. `condition` travels as a document, not as a string: the caller sent
/// JSON and gets JSON back.
#[derive(Debug, Clone, serde::Serialize)]
pub struct Policy {
    pub id: String,
    pub checkpoint: String,
    pub condition: Json,
    pub outcome: String,
    pub message: String,
    pub mode: String,
    pub is_active: bool,
    pub created_at: String,
    pub created_by: String,
    pub updated_at: String,
    pub updated_by: String,
}

/// What a `POST`/`PUT` carries.
#[derive(Debug, Clone, serde::Deserialize)]
pub struct NewPolicy {
    pub checkpoint: String,
    pub condition: Json,
    pub outcome: String,
    pub message: String,
    pub mode: String,
    #[serde(default = "default_true")]
    pub is_active: bool,
}

fn default_true() -> bool {
    true
}

const COLUMNS: &str = "id, checkpoint, condition, outcome, message, mode, is_active, \
                       created_at, created_by, updated_at, updated_by";

fn policy_row(row: &Json) -> Policy {
    let text = |k: &str| row.get(k).and_then(Json::as_str).unwrap_or("").to_string();
    Policy {
        id: text("id"),
        checkpoint: text("checkpoint"),
        // An unreadable condition is returned as `null` instead of blowing up the read: the owner's
        // screen has to be able to SHOW the odd rule so that someone can delete it. The gate already
        // trata aparte, y denegando.
        condition: serde_json::from_str(&text("condition")).unwrap_or(Json::Null),
        outcome: text("outcome"),
        message: text("message"),
        mode: text("mode"),
        is_active: row
            .get("is_active")
            .and_then(Json::as_i64)
            .is_some_and(|v| v != 0),
        created_at: text("created_at"),
        created_by: text("created_by"),
        updated_at: text("updated_at"),
        updated_by: text("updated_by"),
    }
}

/// Checks a rule **before** storing it, against the checkpoint it claims to gate.
///
/// It is the other half of failing closed: since a rule that cannot be evaluated DENIES, everything
/// that can be checked when writing it is checked HERE — on the screen where the owner is writing
/// it — and not in the middle of a sale.
fn validate(registry: &crate::registry::Registry, new: &NewPolicy) -> Result<()> {
    let Some(mode) = Mode::parse(&new.mode) else {
        return Err(domain(
            ERR_UNKNOWN_MODE,
            format!("`{}` no es un modo: `warn` avisa y `enforce` impide", new.mode),
        ));
    };
    let Some(checkpoint) = registry.policy_checkpoint_for_id(&new.checkpoint) else {
        return Err(domain(
            ERR_CHECKPOINT_NOT_FOUND,
            format!(
                "ningún módulo instalado y activo ofrece el punto de control `{}`",
                new.checkpoint
            ),
        ));
    };
    // A mute `block` would be worse than not having the feature at all: the person at the counter
    // has to be able to read WHY they are not being let through. `warn` goes through the same hoop
    // so that promoting the rule to `enforce` is not the moment the problem shows up.
    if new.message.trim().is_empty() {
        return Err(domain(
            ERR_MESSAGE_REQUIRED,
            "una norma tiene que decir por qué impide lo que impide".to_string(),
        ));
    }
    // An empty condition matches ALWAYS (it is the permissive default of the flows). In a policy
    // that is a rule blocking the whole command without saying so, and the owner wrote it believing
    // it filtered something.
    if new.condition.as_object().is_some_and(|o| o.is_empty()) {
        return Err(domain(
            ERR_EMPTY_CONDITION,
            "una condición vacía casaría con TODO: la norma impediría el comando entero".to_string(),
        ));
    }
    // The frozen language of the flows, with no new dialect: an operator it does not know returns
    // its own `flow.*`.
    let condition = Condition::parse(&new.condition)?;
    // The checkpoint says WHAT DATA may be reasoned about. A condition naming anything else reads
    // outside the vocabulary the module declared — the same hole hub#662 closed in the flows.
    if let Some(unknown) = condition
        .0
        .keys()
        .find(|path| !checkpoint.facts.iter().any(|f| f == *path))
    {
        return Err(domain(
            ERR_FACT_NOT_DECLARED,
            format!(
                "`{unknown}` no es uno de los datos que `{}` ofrece para razonar ({})",
                checkpoint.id,
                checkpoint.facts.join(", ")
            ),
        ));
    }
    // A window judges the clock, and the gate evaluates a policy against the command payload
    // alone. Refused at the door, and with the `elevate:` family's code and not the `400` family's:
    // the owner cannot fix this by rewriting the rule, only by waiting for a release.
    if needs_clock(&condition) {
        return Err(domain(
            ERR_CONDITION_NEEDS_CLOCK,
            "una norma no puede juzgar el reloj todavía: el gate solo ve lo que trae el comando"
                .to_string(),
        ));
    }
    // The consequence, two different doors on purpose: one is fixed by changing the rule and the
    // other by waiting for a release, and telling both the same thing would leave the owner not
    // knowing which one they are in.
    if !checkpoint.outcomes.iter().any(|o| o == &new.outcome) {
        return Err(domain(
            ERR_OUTCOME_NOT_OFFERED,
            format!(
                "`{}` no es una de las consecuencias que ofrece `{}` ({})",
                new.outcome,
                checkpoint.id,
                checkpoint.outcomes.join(", ")
            ),
        ));
    }
    match Outcome::parse(&new.outcome) {
        Some(Outcome::Block) => {}
        // `elevate:` is recognised and not run yet (hub#1710). It is refused at write time —
        // instead of being stored and denying at the till — because here there IS someone looking
        // at the screen.
        _ => {
            return Err(domain(
                ERR_OUTCOME_NOT_AVAILABLE,
                format!(
                    "este hub todavía no sabe aplicar `{}`: por ahora una norma solo puede impedir",
                    new.outcome
                ),
            ))
        }
    }
    let _ = mode;
    Ok(())
}

/// This hub's rules; the just-deleted one is not among them.
pub async fn list(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Vec<Policy>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            &format!(
                "SELECT {COLUMNS} FROM _policy \
                 WHERE hub_id = :hub_id AND deleted_at IS NULL ORDER BY created_at, id"
            ),
            &p,
        )
        .await?;
    Ok(res.rows.iter().map(policy_row).collect())
}

pub async fn get(db: &dyn DatabaseAdapter, hub_id: &str, id: &str) -> Result<Policy> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("id".into(), json!(id));
    let res = db
        .query(
            &format!(
                "SELECT {COLUMNS} FROM _policy \
                 WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL"
            ),
            &p,
        )
        .await?;
    res.rows
        .first()
        .map(policy_row)
        .ok_or_else(|| domain(ERR_NOT_FOUND, format!("no hay ninguna norma `{id}` en este hub")))
}

pub async fn create(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    registry: &crate::registry::Registry,
    new: &NewPolicy,
    by: &str,
) -> Result<Policy> {
    validate(registry, new)?;
    // The ceiling is checked with the rule already validated: one that is also badly written
    // deserves to be told what is wrong with it, not that the checkpoint is full.
    let live = count_live(db, hub_id, &new.checkpoint).await?;
    if live >= MAX_POLICIES_PER_CHECKPOINT as i64 {
        return Err(domain(
            ERR_TOO_MANY,
            format!(
                "`{}` ya tiene {MAX_POLICIES_PER_CHECKPOINT} normas: el gate las compara en CADA \
                 comando, así que la siguiente se paga en cada venta",
                new.checkpoint
            ),
        ));
    }
    let id = new_id();
    let now = now_rfc3339();
    let mut p = bind(new, by);
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("now".into(), json!(now));
    db.execute(
        "INSERT INTO _policy (id, hub_id, checkpoint, condition, outcome, message, mode, \
                              is_active, created_at, created_by, updated_at, updated_by) \
         VALUES (:id, :hub_id, :checkpoint, :condition, :outcome, :message, :mode, \
                 :is_active, :now, :by, :now, :by)",
        &p,
    )
    .await?;
    get(db, hub_id, &id).await
}

pub async fn update(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    id: &str,
    registry: &crate::registry::Registry,
    new: &NewPolicy,
    by: &str,
) -> Result<Policy> {
    validate(registry, new)?;
    get(db, hub_id, id).await?; // 404 antes de tocar nada, y acotado a este hub.
    // The ceiling is NOT checked here: an `update` does not add a row, and refusing to let the
    // owner edit the text of one of their 20 rules because «there are already 20» would leave them
    // unable to fix them.
    let mut p = bind(new, by);
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("now".into(), json!(now_rfc3339()));
    db.execute(
        "UPDATE _policy SET checkpoint = :checkpoint, condition = :condition, outcome = :outcome, \
                            message = :message, mode = :mode, is_active = :is_active, \
                            updated_at = :now, updated_by = :by \
         WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
        &p,
    )
    .await?;
    get(db, hub_id, id).await
}

/// **Soft** delete: a rule that forbade a sale is part of why that sale is not there, so the row is
/// marked and not lost.
pub async fn delete(db: &dyn DatabaseAdapter, hub_id: &str, id: &str, by: &str) -> Result<()> {
    get(db, hub_id, id).await?;
    let now = now_rfc3339();
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("now".into(), json!(now));
    p.insert("by".into(), json!(by));
    db.execute(
        "UPDATE _policy SET deleted_at = :now, deleted_by = :by, updated_at = :now, \
                            updated_by = :by \
         WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
        &p,
    )
    .await?;
    Ok(())
}

fn bind(new: &NewPolicy, by: &str) -> Params {
    let mut p = Params::new();
    p.insert("checkpoint".into(), json!(new.checkpoint));
    p.insert("condition".into(), json!(new.condition.to_string()));
    p.insert("outcome".into(), json!(new.outcome));
    p.insert("message".into(), json!(new.message));
    p.insert("mode".into(), json!(new.mode));
    p.insert("is_active".into(), json!(i64::from(new.is_active)));
    p.insert("by".into(), json!(by));
    p
}

async fn count_live(db: &dyn DatabaseAdapter, hub_id: &str, checkpoint: &str) -> Result<i64> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("checkpoint".into(), json!(checkpoint));
    let res = db
        .query(
            "SELECT COUNT(*) AS n FROM _policy \
             WHERE hub_id = :hub_id AND checkpoint = :checkpoint AND deleted_at IS NULL",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .first()
        .and_then(|r| r.get("n"))
        .and_then(Json::as_i64)
        .unwrap_or(0))
}

/// Rebuilds the in-memory index from this hub's LIVE and SWITCHED-ON rows.
///
/// Called by boot and by **every write** of the CRUD. A rule that is switched off (`is_active = 0`)
/// or deleted simply does not go in: switching it off has to stop gating on the very next command,
/// not on the next restart.
///
/// Rows this core does not understand DO go in, with their gap set to `None`, because the gate
/// handles them by **denying** (`policies.md` §6.1). Filtering them out here would be the fail-open
/// §6.1 closes: a rule the hub cannot read would disappear in silence.
pub async fn load_index(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<HashMap<String, Vec<ActivePolicy>>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT id, checkpoint, condition, outcome, message, mode FROM _policy \
             WHERE hub_id = :hub_id AND deleted_at IS NULL AND is_active <> 0 \
             ORDER BY created_at, id",
            &p,
        )
        .await?;
    let mut by_checkpoint: HashMap<String, Vec<ActivePolicy>> = HashMap::new();
    for row in &res.rows {
        let text = |k: &str| row.get(k).and_then(Json::as_str).unwrap_or("").to_string();
        let checkpoint = text("checkpoint");
        // A `mode` that is not understood is treated as `enforce`, which is the safe side: the
        // other option — treating it as `warn` — would turn a rule in force into a mute notice.
        let mode = Mode::parse(&text("mode")).unwrap_or(Mode::Enforce);
        let condition = serde_json::from_str::<Json>(&text("condition"))
            .ok()
            .and_then(|doc| Condition::parse(&doc).ok());
        by_checkpoint
            .entry(checkpoint.clone())
            .or_default()
            .push(ActivePolicy {
                id: text("id"),
                hub_id: hub_id.to_string(),
                checkpoint,
                condition,
                outcome: Outcome::parse(&text("outcome")),
                message: text("message"),
                mode,
            });
    }
    Ok(by_checkpoint)
}
