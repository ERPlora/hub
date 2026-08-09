//! **What a flow is allowed to do** (`_flow_grants`, ADR-0283 D2).
//!
//! A flow does not borrow anybody's role. The alternatives were both considered and both
//! discarded in the ADR: inheriting the creator's permissions breaks the day that employee is
//! deleted (and quietly changes what the flow may do every time somebody is promoted), and a `*`
//! wildcard is no containment at all. What is left is the same shape as module capabilities
//! (ADR-0079) — **default-deny by absence**: a row exists and is alive, or the answer is no.
//!
//! Three properties are the reason this is a table and not a field on the flow:
//!
//! 1. **Fresh at every step.** The gate reads this on each command a run executes, so revoking a
//!    grant while a run is in flight stops the run at its NEXT step. Not the current one — that
//!    one is already inside a transaction — which is the honest guarantee and the one this file's
//!    tests pin.
//! 2. **Revocation is auditable.** A revoked grant is soft-deleted with `revoked_by`, so "who
//!    could do what, and until when" survives. The unique index is partial for exactly this
//!    reason (see the v32 migration).
//! 3. **No elevation.** A grant opens the gate for the command it names and nothing else. It does
//!    not add a permission to a session, and a flow runs as [`crate::registry::Principal::Machine`],
//!    which can never be offered the manager's PIN (hub#361).
use std::collections::HashSet;

use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::registry::{new_id, now_rfc3339, Registry};

pub const ERR_GRANT_DENIED: &str = "flow.grant_denied";
pub const ERR_UNKNOWN_GRANT_KIND: &str = "flow.unknown_grant_kind";
pub const ERR_GRANT_KIND_NOT_AVAILABLE: &str = "flow.grant_kind_not_available";

/// The five kinds of ADR-0283 §2. The vocabulary is frozen here; only `command` can be created in
/// this delivery, because a grant for something the kernel cannot do yet would tell an owner that
/// their flow may call an URL or message a customer when it cannot.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum GrantKind {
    Command,
    Query,
    /// Reserved — hub#663 part 2 (`notify` per channel).
    Notify,
    /// Reserved — hub#662 (`http`, URL pattern).
    Http,
    /// Reserved — hub#663 part 2 (`<query>#<field>`, contacting customers of a module's tables).
    RecipientQuery,
}

impl GrantKind {
    pub fn as_str(self) -> &'static str {
        match self {
            GrantKind::Command => "command",
            GrantKind::Query => "query",
            GrantKind::Notify => "notify",
            GrantKind::Http => "http",
            GrantKind::RecipientQuery => "recipient_query",
        }
    }
    pub fn parse(s: &str) -> Option<Self> {
        Some(match s {
            "command" => GrantKind::Command,
            "query" => GrantKind::Query,
            "notify" => GrantKind::Notify,
            "http" => GrantKind::Http,
            "recipient_query" => GrantKind::RecipientQuery,
            _ => return None,
        })
    }
    /// Can this kind be created today? The others are refused by name, with the issue that brings
    /// them, instead of being stored as a promise nothing keeps.
    pub fn is_available(self) -> bool {
        matches!(self, GrantKind::Command)
    }
    pub const ALL: &'static [GrantKind] = &[
        GrantKind::Command,
        GrantKind::Query,
        GrantKind::Notify,
        GrantKind::Http,
        GrantKind::RecipientQuery,
    ];
}

/// One live grant, as the REST layer shows it.
#[derive(Debug, Clone, serde::Serialize)]
pub struct Grant {
    pub id: String,
    pub kind: String,
    pub value: String,
    pub granted_by: String,
    pub created_at: String,
}

/// The live grants of one flow, read once. Everything the gate and the context need comes from
/// this snapshot, so a step asks the database once and then answers consistently for that step.
#[derive(Debug, Clone, Default)]
pub struct Authority {
    granted: HashSet<(GrantKind, String)>,
}

impl Authority {
    /// May this flow run this command RIGHT NOW? Default-deny: an unknown flow, a flow with no
    /// grants and a flow whose grant was revoked a second ago all answer the same.
    pub fn allows_command(&self, command: &str) -> bool {
        self.granted
            .contains(&(GrantKind::Command, command.to_string()))
    }

    /// The permissions a run carries in its [`crate::registry::RequestContext`]: **only** the
    /// `permission` of the commands this flow was granted.
    ///
    /// It is NOT what opens the gate — that is [`Authority::allows_command`], which names the
    /// COMMAND, not a permission, so being granted `crm.note.add` never opens its neighbour just
    /// because they share a permission. What this list is for is everything downstream that still
    /// asks a context what it may do: a handler's preloaded `reads`, a nested command resolved
    /// through `validate_operation`.
    ///
    /// The original design (ADR-0283 §2) justified this union with the CASCADES — «so that a flow
    /// creating a sale does not have its invoice listener die in dead-letter». That reason was a
    /// **bug**, not a requirement, and it is gone: since ADR-0288 (hub#686) a listener runs with
    /// the authority of its OWN module instead of the reconstructed permissions of whoever emitted
    /// the event. So a flow's context no longer has to carry other modules' listeners on its back;
    /// it carries exactly what it was granted, which is what the decision wanted all along.
    pub fn permissions(&self, registry: &Registry) -> HashSet<String> {
        self.granted
            .iter()
            .filter(|(kind, _)| *kind == GrantKind::Command)
            .filter_map(|(_, name)| registry.get_command(name))
            .map(|cmd| cmd.def.permission.clone())
            .filter(|p| !p.is_empty() && p != "*")
            .collect()
    }

    pub fn is_empty(&self) -> bool {
        self.granted.is_empty()
    }
}

/// Reads the live grants of a flow. One query, and the caller decides what to ask of the result.
pub async fn authority(db: &dyn DatabaseAdapter, hub_id: &str, flow_id: &str) -> Result<Authority> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("flow_id".into(), json!(flow_id));
    let res = db
        .query(
            "SELECT kind, value FROM _flow_grants \
             WHERE hub_id = :hub_id AND flow_id = :flow_id AND deleted_at IS NULL",
            &p,
        )
        .await?;
    let granted = res
        .rows
        .iter()
        .filter_map(|r| {
            let kind = GrantKind::parse(r["kind"].as_str().unwrap_or_default())?;
            Some((kind, r["value"].as_str().unwrap_or_default().to_string()))
        })
        .collect();
    Ok(Authority { granted })
}

/// **The gate**, as the dispatcher calls it (`commands::execute_at` under
/// [`crate::commands::Origin::Automation`]). A fresh read on purpose: this is what makes a
/// revocation take effect at the next step of a running flow instead of at the next restart.
pub async fn check_command_grant(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
    command: &str,
) -> Result<()> {
    if authority(db, hub_id, flow_id).await?.allows_command(command) {
        return Ok(());
    }
    Err(RuntimeError::Domain {
        code: ERR_GRANT_DENIED.to_string(),
        message: format!(
            "flow `{flow_id}` has no live grant for command `{command}`. A flow runs with its own \
             explicit grants (ADR-0283 D2), never with the role of whoever created it."
        ),
    })
}

/// Replaces the whole grant list of a flow (the `PUT …/grants` contract): what disappears is
/// **revoked** (soft-delete + `revoked_by`), what stays is left alone with its original
/// `granted_by`, and what is new is inserted.
///
/// A replace and not a patch because the question an owner answers is "what may this flow do?",
/// and that is a list they see whole. Re-granting something already live is a no-op rather than a
/// conflict — otherwise saving the same screen twice would fail on the unique index.
pub async fn replace(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
    registry: &Registry,
    wanted: &[(GrantKind, String)],
    granted_by: &str,
) -> Result<()> {
    for (kind, value) in wanted {
        if !kind.is_available() {
            return Err(RuntimeError::Domain {
                code: ERR_GRANT_KIND_NOT_AVAILABLE.to_string(),
                message: format!(
                    "grants of kind `{}` cannot be created yet (http: hub#662, notify and \
                     recipient_query: hub#663 part 2, query tools: hub#665). Refused rather than \
                     stored as a permission nothing enforces.",
                    kind.as_str()
                ),
            });
        }
        // A grant naming a command that does not exist is a promise about nothing — and, worse, it
        // reads as authorisation on the screen. `PUT …/grants` refuses the whole list (§9).
        if *kind == GrantKind::Command && registry.get_command(value).is_none() {
            return Err(RuntimeError::CommandNotFound(value.clone()));
        }
    }

    let live = list(db, hub_id, flow_id).await?;
    let now = now_rfc3339();

    for grant in &live {
        let still_wanted = wanted
            .iter()
            .any(|(k, v)| k.as_str() == grant.kind && v == &grant.value);
        if !still_wanted {
            let mut p = Params::new();
            p.insert("id".into(), json!(grant.id));
            p.insert("now".into(), json!(now));
            p.insert("by".into(), json!(granted_by));
            db.execute(
                "UPDATE _flow_grants SET deleted_at = :now, revoked_by = :by WHERE id = :id",
                &p,
            )
            .await?;
        }
    }

    for (kind, value) in wanted {
        if live
            .iter()
            .any(|g| g.kind == kind.as_str() && &g.value == value)
        {
            continue; // already live: keep the original `granted_by`/`created_at`.
        }
        let mut p = Params::new();
        p.insert("id".into(), json!(new_id()));
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("flow_id".into(), json!(flow_id));
        p.insert("kind".into(), json!(kind.as_str()));
        p.insert("value".into(), json!(value));
        p.insert("now".into(), json!(now));
        p.insert("by".into(), json!(granted_by));
        db.execute(
            "INSERT INTO _flow_grants (id, hub_id, flow_id, kind, value, created_at, granted_by) \
             VALUES (:id, :hub_id, :flow_id, :kind, :value, :now, :by)",
            &p,
        )
        .await?;
    }
    Ok(())
}

/// Live grants of a flow, oldest first.
pub async fn list(db: &dyn DatabaseAdapter, hub_id: &str, flow_id: &str) -> Result<Vec<Grant>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("flow_id".into(), json!(flow_id));
    let res = db
        .query(
            "SELECT id, kind, value, granted_by, created_at FROM _flow_grants \
             WHERE hub_id = :hub_id AND flow_id = :flow_id AND deleted_at IS NULL \
             ORDER BY created_at, id",
            &p,
        )
        .await?;
    Ok(res.rows.iter().map(grant_row).collect())
}

/// Revokes every grant of a flow (used when the flow itself is deleted): the flow stops being
/// able to act the moment it stops existing, without waiting for anything to notice.
pub async fn revoke_all(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
    revoked_by: &str,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("flow_id".into(), json!(flow_id));
    p.insert("now".into(), json!(now_rfc3339()));
    p.insert("by".into(), json!(revoked_by));
    db.execute(
        "UPDATE _flow_grants SET deleted_at = :now, revoked_by = :by \
         WHERE hub_id = :hub_id AND flow_id = :flow_id AND deleted_at IS NULL",
        &p,
    )
    .await?;
    Ok(())
}

fn grant_row(row: &Json) -> Grant {
    let text = |k: &str| row[k].as_str().unwrap_or_default().to_string();
    Grant {
        id: text("id"),
        kind: text("kind"),
        value: text("value"),
        granted_by: text("granted_by"),
        created_at: text("created_at"),
    }
}

/// Parses the `{kind, value}` pairs of a `PUT …/grants` body. An unknown kind is refused by name:
/// a typo that silently dropped a grant would be read as "denied" and the flow would fail later,
/// far from the screen where it was typed.
pub fn parse_pairs(body: &Json) -> Result<Vec<(GrantKind, String)>> {
    let Some(items) = body.as_array() else {
        return Err(RuntimeError::Domain {
            code: ERR_UNKNOWN_GRANT_KIND.to_string(),
            message: "grants are a list of `{kind, value}`".to_string(),
        });
    };
    let mut out = Vec::new();
    for item in items {
        let kind = item
            .get("kind")
            .and_then(|k| k.as_str())
            .and_then(GrantKind::parse)
            .ok_or_else(|| RuntimeError::Domain {
                code: ERR_UNKNOWN_GRANT_KIND.to_string(),
                message: format!(
                    "a grant `kind` is one of {}",
                    GrantKind::ALL
                        .iter()
                        .map(|k| k.as_str())
                        .collect::<Vec<_>>()
                        .join(", ")
                ),
            })?;
        let value = item
            .get("value")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .trim()
            .to_string();
        if value.is_empty() {
            return Err(RuntimeError::Domain {
                code: ERR_UNKNOWN_GRANT_KIND.to_string(),
                message: format!("a `{}` grant needs a value", kind.as_str()),
            });
        }
        out.push((kind, value));
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::registry::ModuleStatus;
    use erplora_db::testutil::fresh_db;

    const HUB: &str = "hub-grants";
    const FLOW: &str = "flow-1";

    fn registry() -> Registry {
        let mut reg = Registry::new();
        reg.status.insert("sales".into(), ModuleStatus::Active);
        reg.commands.insert(
            "sales.sale.create".into(),
            crate::flows::test_support::command("sales", "sales.add_sale", "SELECT 1;", vec![]),
        );
        reg.commands.insert(
            "sales.sale.void".into(),
            crate::flows::test_support::command("sales", "sales.void_sale", "SELECT 1;", vec![]),
        );
        reg
    }

    async fn db_with_schema() -> impl DatabaseAdapter {
        let db = fresh_db().await;
        crate::flows::test_support::ensure_schema(&db, HUB).await;
        db
    }

    #[tokio::test]
    async fn a_flow_with_no_grants_may_run_nothing() {
        let db = db_with_schema().await;
        let err = check_command_grant(&db, HUB, FLOW, "sales.sale.create")
            .await
            .expect_err("default-deny: absence is the answer, not an empty allow-list");
        assert!(format!("{err}").contains("sales.sale.create"), "{err}");
    }

    #[tokio::test]
    async fn a_grant_opens_exactly_the_command_it_names() {
        let db = db_with_schema().await;
        let reg = registry();
        replace(
            &db,
            HUB,
            FLOW,
            &reg,
            &[(GrantKind::Command, "sales.sale.create".into())],
            "hub_user:1",
        )
        .await
        .unwrap();

        check_command_grant(&db, HUB, FLOW, "sales.sale.create")
            .await
            .expect("the granted command runs");
        // A sibling command of the same module is a different question with the same answer as
        // before: no.
        assert!(check_command_grant(&db, HUB, FLOW, "sales.sale.void")
            .await
            .is_err());
    }

    #[tokio::test]
    async fn a_grant_belongs_to_one_flow_and_one_hub() {
        let db = db_with_schema().await;
        let reg = registry();
        replace(
            &db,
            HUB,
            FLOW,
            &reg,
            &[(GrantKind::Command, "sales.sale.create".into())],
            "hub_user:1",
        )
        .await
        .unwrap();

        assert!(check_command_grant(&db, HUB, "flow-2", "sales.sale.create")
            .await
            .is_err(), "another flow of the same hub is not covered");
        assert!(check_command_grant(&db, "hub-other", FLOW, "sales.sale.create")
            .await
            .is_err(), "the same flow id in another tenant is not covered");
    }

    #[tokio::test]
    async fn revoking_is_a_soft_delete_and_takes_effect_on_the_next_read() {
        let db = db_with_schema().await;
        let reg = registry();
        let grants = [(GrantKind::Command, "sales.sale.create".to_string())];
        replace(&db, HUB, FLOW, &reg, &grants, "hub_user:1").await.unwrap();
        check_command_grant(&db, HUB, FLOW, "sales.sale.create").await.unwrap();

        // The owner empties the list — this is what `PUT …/grants` with `[]` does.
        replace(&db, HUB, FLOW, &reg, &[], "hub_user:2").await.unwrap();

        assert!(check_command_grant(&db, HUB, FLOW, "sales.sale.create").await.is_err());
        assert!(list(&db, HUB, FLOW).await.unwrap().is_empty());
        // The row survives, naming who took it away: that is the audit trail.
        let rows = db
            .query(
                "SELECT revoked_by FROM _flow_grants WHERE deleted_at IS NOT NULL",
                &Params::new(),
            )
            .await
            .unwrap()
            .rows;
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["revoked_by"], json!("hub_user:2"));
    }

    #[tokio::test]
    async fn re_saving_the_same_list_keeps_the_original_attribution() {
        let db = db_with_schema().await;
        let reg = registry();
        let grants = [(GrantKind::Command, "sales.sale.create".to_string())];
        replace(&db, HUB, FLOW, &reg, &grants, "hub_user:1").await.unwrap();
        replace(&db, HUB, FLOW, &reg, &grants, "hub_user:2").await.unwrap();

        let live = list(&db, HUB, FLOW).await.unwrap();
        assert_eq!(live.len(), 1, "saving the same screen twice is not a conflict");
        assert_eq!(live[0].granted_by, "hub_user:1", "who granted it first");
    }

    #[tokio::test]
    async fn a_grant_for_a_command_that_does_not_exist_is_refused() {
        let db = db_with_schema().await;
        let err = replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[(GrantKind::Command, "ghost.command".into())],
            "hub_user:1",
        )
        .await
        .expect_err("a grant naming nothing reads as authorisation on the screen");
        assert!(format!("{err}").contains("ghost.command"), "{err}");
    }

    #[tokio::test]
    async fn the_kinds_the_kernel_cannot_enforce_yet_are_refused_by_name() {
        let db = db_with_schema().await;
        for kind in [GrantKind::Http, GrantKind::Notify, GrantKind::RecipientQuery, GrantKind::Query] {
            let err = replace(&db, HUB, FLOW, &registry(), &[(kind, "x".into())], "hub_user:1")
                .await
                .expect_err("a permission nothing enforces must not be stored");
            assert!(format!("{err}").contains(kind.as_str()), "{err}");
        }
    }

    #[tokio::test]
    async fn the_context_permissions_are_the_union_of_the_granted_commands() {
        let db = db_with_schema().await;
        let reg = registry();
        replace(
            &db,
            HUB,
            FLOW,
            &reg,
            &[
                (GrantKind::Command, "sales.sale.create".into()),
                (GrantKind::Command, "sales.sale.void".into()),
            ],
            "hub_user:1",
        )
        .await
        .unwrap();

        let permissions = authority(&db, HUB, FLOW).await.unwrap().permissions(&reg);
        assert_eq!(
            permissions,
            HashSet::from(["sales.add_sale".to_string(), "sales.void_sale".to_string()]),
            "a flow behaves downstream like a user holding exactly these, and no wildcard"
        );
        assert!(!permissions.contains("*"), "a grant never becomes a wildcard");
    }

    #[test]
    fn an_unknown_grant_kind_is_refused_instead_of_dropped() {
        let err = parse_pairs(&json!([{ "kind": "commnd", "value": "sales.sale.create" }]))
            .expect_err("a typo must not become a silent denial noticed at 3 AM");
        assert!(format!("{err}").contains("command"), "{err}");
    }
}
