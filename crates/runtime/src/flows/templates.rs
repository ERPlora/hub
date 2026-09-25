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
use std::collections::BTreeMap;

use erplora_db::DatabaseAdapter;
use serde_json::json;
use sha2::{Digest, Sha256};

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

/// The fingerprint of a factory recipe — WHAT it does, never who explained it or when it may run
/// (hub#2059). A flow's `template_digest` is one of these, taken the moment it was built; the
/// gallery flags it OUTDATED once the digest this hub serves TODAY for the same `<module>/<family>`
/// has moved on.
///
/// `documents` travels as a `BTreeMap` so the language keys sort the same way on every machine —
/// serde here has no `preserve_order`, so a `Value` object already serialises with sorted keys, and
/// this is the same guarantee one level up. `grants` keep the sidecar's own order (reordering two
/// permissions is only ever a no-op today, but nothing here should assume it always will be) and
/// only `kind`/`value`/`payload` travel: never `reason`, which is prose for the gallery and never
/// reaches `_flow_grants` either (hub#1654), and never [`ModuleFlowTemplate::requires`], which says
/// WHEN the recipe may run, not what it does — bumping a version floor must not make every hub that
/// activated it think the recipe itself changed.
pub fn recipe_digest(tpl: &ModuleFlowTemplate) -> String {
    let documents: BTreeMap<&str, &serde_json::Value> = tpl
        .documents
        .iter()
        .map(|(lang, doc)| (lang.as_str(), doc))
        .collect();
    let grants: Vec<_> = tpl
        .grants
        .iter()
        .map(|g| json!({ "kind": g.kind, "value": g.value, "payload": g.payload }))
        .collect();
    let canonical = json!({ "documents": documents, "grants": grants }).to_string();
    let mut hasher = Sha256::new();
    hasher.update(canonical.as_bytes());
    format!("{:x}", hasher.finalize())
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

/// Turns `<module>/<family>` on. The first time it builds it with exactly the sidecar's permissions
/// and leaves it running; afterwards it only switches the existing flow on, keeping what the owner
/// changed (hub#1684). Idempotent — the second tap lands on the same flow.
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

    let reference = template_ref(module, family);
    let Some(existing) = store::find_by_template_ref(db, hub_id, &reference).await? else {
        // ── build it PAUSED → exactly the sidecar's permissions → running ─────────────────────
        let paused = NewFlow {
            name,
            enabled: false,
            definition,
        };
        // The digest travels only on CREATION — reusing (below) is the switch hub#1684 made it,
        // never a rewrite of the document, so it has nothing new to stamp either.
        let digest = recipe_digest(tpl);
        let flow = store::create_from_template(
            db,
            hub_id,
            registry,
            &paused,
            by,
            Some(&reference),
            Some(&digest),
        )
        .await?;
        let flow = grant_then_enable(db, hub_id, registry, &flow.id, paused, &wanted, by).await?;
        return Ok(Activation {
            flow,
            created: true,
        });
    };

    // ── reuse: turning it back on is a SWITCH, not «restore the factory recipe» (hub#1684) ────
    // Its OWN document and its OWN permissions, the mirror of `deactivate`: after activating, the
    // owner may have edited the recipe, retired a permission or narrowed its limits in
    // Automations (ADR-0470 §4), and a tap on the module's screen must not undo that silently.
    // Getting the factory recipe back is an explicit gesture: delete it and activate again.
    let own = own_document(&existing);
    let paused = NewFlow {
        name: existing.name.clone(),
        enabled: false,
        definition: own,
    };
    // The one exception keeps the order's recovery promise: a recipe with NO permission at all —
    // an activation that fell between «paused» and «grants», or an owner who retired every one —
    // can do nothing, and «activate» means «leave it working», so it gets the module's.
    if grants::list(db, hub_id, &existing.id).await?.is_empty() {
        let flow = store::update(db, hub_id, &existing.id, registry, &paused, by).await?;
        let flow = grant_then_enable(db, hub_id, registry, &flow.id, paused, &wanted, by).await?;
        return Ok(Activation {
            flow,
            created: false,
        });
    }
    let running = NewFlow {
        enabled: true,
        ..paused
    };
    let flow = store::update(db, hub_id, &existing.id, registry, &running, by).await?;
    Ok(Activation {
        flow,
        created: false,
    })
}

/// The flow's own document, as `store::update` wants it back.
fn own_document(flow: &Flow) -> serde_json::Value {
    if flow.definition.is_null() {
        json!({})
    } else {
        flow.definition.clone()
    }
}

/// The tail of the guaranteed order: the flow is already PAUSED as `paused`; give it exactly
/// `wanted` (all-or-nothing, pins validated) and only then turn it on.
async fn grant_then_enable(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    registry: &Registry,
    flow_id: &str,
    paused: NewFlow,
    wanted: &[GrantSpec],
    by: &str,
) -> Result<Flow> {
    grants::replace(db, hub_id, flow_id, registry, wanted, by).await?;
    let running = NewFlow {
        enabled: true,
        ..paused
    };
    store::update(db, hub_id, flow_id, registry, &running, by).await
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
        definition: own_document(&flow),
    };
    store::update(db, hub_id, &flow.id, registry, &paused, by).await
}

/// **Restores the factory recipe** — the explicit gesture for a flow whose module has shipped a
/// better one since (hub#2059). Where re-activating (hub#1684) is a SWITCH that never touches the
/// document, this is the opposite on purpose: it OVERWRITES the flow's document and its grants with
/// exactly what the module ships TODAY. The owner's own edits are what «restore» throws away — that
/// is the whole point of asking for the factory one back.
///
/// Same flow id, never a new one: its run history needs an owner, and the module's card reads
/// `installed.flow_id` to know which automation this is. Same guaranteed order as `activate` —
/// validate everything → PAUSED with the factory doc/name → exactly the sidecar's grants → stamp
/// the fresh digest → running again, but **only if it already was**: restoring replaces WHAT the
/// automation does, never WHETHER it runs, so a paused flow that gets its recipe restored stays
/// paused. A family never activated in this hub is a plain `flow.not_found`: there is nothing to
/// restore, and building one from scratch is `activate`'s door, not this one.
pub async fn restore(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    registry: &Registry,
    module: &str,
    family: &str,
    language: &str,
    by: &str,
) -> Result<Flow> {
    // ── validate everything BEFORE the first write ────────────────────────────────────────────
    let tpl = template_of(registry, module, family)?;
    let definition = document(tpl, language)?;
    let wanted = wanted_grants(tpl)?;
    let name = definition
        .get("name")
        .and_then(|v| v.as_str())
        .unwrap_or(family)
        .to_string();
    let digest = recipe_digest(tpl);

    let reference = template_ref(module, family);
    let Some(existing) = store::find_by_template_ref(db, hub_id, &reference).await? else {
        return Err(RuntimeError::Domain {
            code: store::ERR_FLOW_NOT_FOUND.to_string(),
            message: format!("this hub has no automation built from `{reference}`"),
        });
    };
    let was_enabled = existing.enabled;

    // ── PAUSED with the factory doc/name → exactly the sidecar's grants → the fresh digest ────
    let paused = NewFlow {
        name,
        enabled: false,
        definition,
    };
    let flow = store::update(db, hub_id, &existing.id, registry, &paused, by).await?;
    grants::replace(db, hub_id, &flow.id, registry, &wanted, by).await?;
    store::set_template_digest(db, hub_id, &flow.id, &digest, by).await?;

    // ── back to running, but ONLY if it already was ────────────────────────────────────────────
    if !was_enabled {
        return store::get(db, hub_id, &flow.id).await;
    }
    let running = NewFlow {
        enabled: true,
        ..paused
    };
    store::update(db, hub_id, &flow.id, registry, &running, by).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::manifest::FlowTemplateGrant;
    use std::collections::HashMap;

    fn recipe() -> ModuleFlowTemplate {
        let mut documents = HashMap::new();
        documents.insert("en".to_string(), json!({ "name": "Book", "steps": [] }));
        documents.insert("es".to_string(), json!({ "name": "Reservar", "steps": [] }));
        ModuleFlowTemplate {
            family: "book".into(),
            documents,
            grants: vec![FlowTemplateGrant {
                kind: "command".into(),
                value: "appointments.appointments.cancel".into(),
                payload: serde_json::from_value(json!({ "channel": "customer" })).unwrap(),
                reason: Default::default(),
            }],
            requires: HashMap::new(),
        }
    }

    /// hub#2059: the fingerprint is WHAT the recipe does — its documents and its permissions.
    #[test]
    fn the_same_recipe_always_has_the_same_fingerprint() {
        assert_eq!(recipe_digest(&recipe()), recipe_digest(&recipe()));
        assert_eq!(recipe_digest(&recipe()).len(), 64, "a sha256 in hex");
    }

    #[test]
    fn different_words_in_any_language_are_a_different_recipe() {
        let mut improved = recipe();
        improved.documents.insert(
            "es".to_string(),
            json!({ "name": "Reservar ya", "steps": [] }),
        );
        assert_ne!(recipe_digest(&recipe()), recipe_digest(&improved));
    }

    /// 🔴 A release that only narrows a PIN changes what the permission says (hub#1623/#1654):
    /// that is a new recipe the owner has to be told about, even with identical documents.
    #[test]
    fn a_different_pin_is_a_different_recipe() {
        let mut narrowed = recipe();
        narrowed.grants[0].payload = serde_json::from_value(json!({ "channel": "staff" })).unwrap();
        assert_ne!(recipe_digest(&recipe()), recipe_digest(&narrowed));
    }

    /// The version floor is WHEN the recipe can run, not what it does: raising it is not a new
    /// recipe, and flagging it would invite the owner to throw away their edits for nothing.
    #[test]
    fn a_new_version_floor_is_not_a_new_recipe() {
        let mut floored = recipe();
        floored
            .requires
            .insert("appointments".to_string(), "9.9.9".to_string());
        assert_eq!(recipe_digest(&recipe()), recipe_digest(&floored));
    }

    /// The sentence that explains a permission is prose for the gallery and never reaches the flow
    /// (`_flow_grants` keeps kind/value/payload only): rewording it is not a new recipe either.
    #[test]
    fn rewording_a_permissions_explanation_is_not_a_new_recipe() {
        let mut reworded = recipe();
        reworded.grants[0].reason = Some(HashMap::from([(
            "en".to_string(),
            "Cancels the customer's own booking".to_string(),
        )]));
        assert_eq!(recipe_digest(&recipe()), recipe_digest(&reworded));
    }
}
