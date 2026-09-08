//! **Turning a factory recipe on, in one tap** (hub#1677, ADR-0470).
//!
//! A module publishes its automations in its `flows/` folder, the installer registers them and
//! `GET /api/hub/flows/templates` serves them (hub#1611). Until here, *using* one meant leaving the
//! module's screen for the gallery, «using» the card, opening the Permissions tab, authorising
//! fourteen raw grants and flipping the switch: nine screens and about fifteen taps, measured on
//! `banco-pre` on 2026-09-08 with a hairdresser who had already been through Meta's twelve.
//!
//! This is the other way in. It **amends [ADR-0463] §5** («grants are SHOWN, not granted») for this
//! one path and nothing else: the recipe is the module's own, its permissions are the ones its
//! publisher declared and signed, `erplora validate` checked them before publication, and the owner
//! consents to them in one sentence the module paints. What it does **not** touch is
//! [ADR-0283] D2 — the grants are still explicit, per flow, default-deny, no inheritance and no
//! wildcards — nor the pin validation of ADR-0466/0468, which happens here through the very same
//! `grants::replace`.
//!
//! 🔴 **The order is the guarantee, and it is not a transaction.** `DatabaseAdapter` only offers
//! `execute_tx(&[(String, Params)])` — a list of statements built up front — and creating the flow,
//! seeding its triggers and replacing its grants all READ in between, so they do not fit in one
//! without a second copy of their logic living here. What is done instead gives the property that
//! matters: **validate everything → create or reuse PAUSED → replace the grants (already all-or-
//! nothing) → enable**. A failure anywhere in the middle leaves exactly the state ADR-0463 §5 calls
//! normal — a paused flow with no permissions — and the next `activate` reuses it. What can never
//! happen is the opposite one: an automation RUNNING with half its permissions.
//!
//! [ADR-0463]: ../../../../architecture/00-overview/decision-log.md
//! [ADR-0283]: ../../../../architecture/00-overview/decision-log.md
use erplora_db::DatabaseAdapter;
use serde_json::json;

use crate::errors::{Result, RuntimeError};
use crate::manifest::ModuleFlowTemplate;
use crate::registry::Registry;

use crate::flows::grants::{self, GrantKind, GrantSpec};
use crate::flows::store::{self, Flow, NewFlow};

/// No installed module ships this `<module>/<family>`, and no discard explains it either. `404`
/// through [`crate::flows::store::ERR_FLOW_NOT_FOUND`]'s own rule: the family suffix is what
/// `flow_status` reads.
pub const ERR_TEMPLATE_NOT_FOUND: &str = "flow.template_not_found";

/// The request named a module in `x-erplora-module` that is not the one in the path. `403`: a
/// module may only turn on **its own** recipes (ADR-0470 §1).
pub const ERR_TEMPLATE_NOT_YOURS: &str = "flow.template_not_yours";

/// The reference stored in `_flow.template_ref`, and the key «is this one already on?» is asked by.
pub fn template_ref(module: &str, family: &str) -> String {
    format!("{module}/{family}")
}

/// What an activation did, so the door can answer `201` for a recipe it built and `200` for one it
/// found. The difference is not cosmetic: the module's screen shows «activated» once and «already
/// on» afterwards, and a second tap that answered `201` would read as a second automation.
pub struct Activation {
    pub flow: Flow,
    pub created: bool,
}

/// The recipe `<module>/<family>` as this hub serves it today, or the reason it does not.
///
/// The two refusals are deliberately different: a family this hub **discarded** comes back with the
/// discard's own code (`template_floor_module_too_old`, `template_owner_paused`…) so the module can
/// paint the reason, while a family nobody ships is a plain `not_found`. Answering `not_found` to a
/// discarded one would send its publisher looking for a file that is right there.
fn template_of<'a>(
    registry: &'a Registry,
    module: &str,
    family: &str,
) -> Result<&'a ModuleFlowTemplate> {
    if let Some((_, tpl)) = registry
        .flow_templates()
        .into_iter()
        .find(|(m, t)| *m == module && t.family == family)
    {
        return Ok(tpl);
    }
    if let Some((_, discard)) = registry
        .flow_template_discards()
        .into_iter()
        .find(|(m, d)| *m == module && d.family == family)
    {
        // Not a `flow.*` code on purpose: it is the SAME code the listing already serves for this
        // family, and the screen that reads one reads the other.
        return Err(RuntimeError::Domain {
            code: discard.code,
            message: discard.detail,
        });
    }
    Err(RuntimeError::Domain {
        code: ERR_TEMPLATE_NOT_FOUND.to_string(),
        message: format!("no module ships the automation `{module}/{family}`"),
    })
}

/// The document to install, in the hub's language, falling back to `en` (ADR-0055/0199).
///
/// `erplora validate` guarantees every language of a family declares the same steps in the same
/// order with the same machinery — only the prose differs — so this picks WORDS, never behaviour.
fn document(tpl: &ModuleFlowTemplate, language: &str) -> Result<serde_json::Value> {
    tpl.documents
        .get(language)
        .or_else(|| tpl.documents.get("en"))
        .cloned()
        .ok_or_else(|| RuntimeError::Domain {
            code: ERR_TEMPLATE_NOT_FOUND.to_string(),
            message: format!(
                "the automation `{}` ships no document in `{language}` nor in `en`",
                tpl.family
            ),
        })
}

/// The sidecar's grants, **pins included**, as the kernel's own vocabulary.
///
/// 🔴 The `payload` is what separates «may cancel appointments» from «may cancel appointments AS
/// THE CUSTOMER», and only the second is safe in an automation whose payload a model writes from a
/// stranger's message. Dropping it here would be a wide permission granted by an owner who read a
/// narrow sentence — and with no error anywhere (hub#1623/#1654).
fn wanted_grants(tpl: &ModuleFlowTemplate) -> Result<Vec<GrantSpec>> {
    tpl.grants
        .iter()
        .map(|g| {
            let kind = GrantKind::parse(&g.kind).ok_or_else(|| RuntimeError::Domain {
                code: grants::ERR_UNKNOWN_GRANT_KIND.to_string(),
                message: format!(
                    "the automation `{}` asks for a grant of kind `{}`, which this core does not \
                     have",
                    tpl.family, g.kind
                ),
            })?;
            Ok(GrantSpec {
                kind,
                value: g.value.clone(),
                payload: g.payload.clone(),
            })
        })
        .collect()
}

/// Turns `<module>/<family>` on: builds it or finds it, gives it exactly the sidecar's permissions,
/// and leaves it running. Idempotent — the second tap lands on the same flow.
pub async fn activate(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    registry: &Registry,
    module: &str,
    family: &str,
    language: &str,
    by: &str,
) -> Result<Activation> {
    // ── validate everything BEFORE the first write ────────────────────────────────────────────
    let tpl = template_of(registry, module, family)?;
    let definition = document(tpl, language)?;
    let wanted = wanted_grants(tpl)?;
    let name = definition
        .get("name")
        .and_then(|v| v.as_str())
        .unwrap_or(family)
        .to_string();

    // ── create or reuse, PAUSED ───────────────────────────────────────────────────────────────
    let reference = template_ref(module, family);
    let paused = NewFlow {
        name,
        enabled: false,
        definition,
    };
    let (flow, created) =
        match store::find_by_template_ref(db, hub_id, &reference).await? {
            // The recipe may have been republished since it was installed, so the document is
            // refreshed from the registry rather than left as it was: activating is «give me the
            // automation this module ships today».
            Some(existing) => (
                store::update(db, hub_id, &existing.id, registry, &paused, by).await?,
                false,
            ),
            None => (
                store::create_from_template(db, hub_id, registry, &paused, by, Some(&reference))
                    .await?,
                true,
            ),
        };

    // ── exactly the sidecar's permissions (all-or-nothing, and it validates the pins) ─────────
    grants::replace(db, hub_id, &flow.id, registry, &wanted, by).await?;

    // ── and only now, running ─────────────────────────────────────────────────────────────────
    let running = NewFlow {
        enabled: true,
        ..paused
    };
    let flow = store::update(db, hub_id, &flow.id, registry, &running, by).await?;
    Ok(Activation { flow, created })
}

/// Turns it off: a **pause**, never a delete.
///
/// The grants stay, and so does the history: what that automation did needs an owner that still
/// exists, and turning it back on must not ask a person to re-authorise what they already
/// authorised. A family that was never activated is a plain `flow.not_found` — there is nothing to
/// pause.
pub async fn deactivate(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    registry: &Registry,
    module: &str,
    family: &str,
    by: &str,
) -> Result<Flow> {
    let reference = template_ref(module, family);
    let Some(flow) = store::find_by_template_ref(db, hub_id, &reference).await? else {
        return Err(RuntimeError::Domain {
            code: store::ERR_FLOW_NOT_FOUND.to_string(),
            message: format!("this hub has no automation built from `{reference}`"),
        });
    };
    // Its OWN document, not the registry's: the owner may have edited it in the editor after
    // activating, and pausing is not the moment to overwrite what they wrote.
    let paused = NewFlow {
        name: flow.name.clone(),
        enabled: false,
        definition: if flow.definition.is_null() {
            json!({})
        } else {
            flow.definition.clone()
        },
    };
    store::update(db, hub_id, &flow.id, registry, &paused, by).await
}
