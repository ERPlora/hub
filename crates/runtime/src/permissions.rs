//! Comprobación de permisos. El gate es el mismo para UI, API y AI tools (ARQUITECTURA.md §9.2).
//! La autoridad real es siempre el runtime (Rust), nunca la UI.
use crate::errors::{Result, RuntimeError};
use crate::registry::{Principal, Registry, RequestContext};

/// The one role whose missing permissions can be approved on the spot (PLAN paso 2b, rule 5).
///
/// It is a base role of the frozen catalogue ([`crate::hub_users::BASE_ROLES`]) on purpose:
/// `admin` is excluded because its permissions — fiscal identity, plan, deletion, installing
/// apps — are the owner's own account, not a four-digit PIN typed in front of customers; and a
/// module-declared role is excluded because there is no such thing as "the shift lead on duty"
/// the way there is a manager.
const ELEVABLE_ROLE: &str = "manager";

/// El comodín: un contexto que lo lleva pasa cualquier gate de permiso. Lo usan los contextos que
/// el RUNTIME se construye a sí mismo, donde no hay rol humano que consultar — la tarea programada
/// ([`crate::scheduler`]), las `reads` precargadas de un handler y la entrega de un listener del
/// outbox ([`crate::outbox`], hub#686).
pub const WILDCARD: &str = "*";

/// Verifica que el contexto tenga el permiso requerido (o el comodín `*`).
pub fn check(ctx: &RequestContext, required: &str) -> Result<()> {
    if has(ctx, required) {
        Ok(())
    } else {
        Err(RuntimeError::PermissionDenied(required.to_string()))
    }
}

/// Same question as [`check`], asked without turning a "no" into an error.
///
/// It exists for the places that FILTER instead of rejecting — `hub.setup.status` only offers a
/// checklist item to whoever could act on it. Sharing the predicate keeps that filter and the real
/// gate from ever disagreeing about what a permission means.
pub fn has(ctx: &RequestContext, required: &str) -> bool {
    ctx.permissions.contains("*") || ctx.permissions.contains(required)
}

/// The **command** gate (hub#360, PLAN paso 2b rule 1). Same answer as [`check`] to the only
/// question that matters — may this context run this? — and a better-typed answer when it may
/// not: a refusal a manager could approve comes back as [`RuntimeError::RequiresElevation`]
/// naming the missing permission, instead of a flat `403` the UI cannot act on.
///
/// **It is a label on a refusal, never a permit.** Both branches deny; nothing runs, nothing is
/// written, and the PIN that actually authorises the action is hub#361. That property is what
/// makes this safe to add before the verification exists — the worst a wrong answer here can do
/// is offer a dialog that then refuses, never let something through.
///
/// **A machine principal is never offered the dialog** (hub#361): an API key
/// ([`Principal::Machine`]) has nobody standing at it, so «ask a manager to type their PIN» is an
/// instruction it cannot follow — and now that an approval GRANTS ([`crate::elevation`]), a
/// stored, copied, long-lived credential must not have a second way in. It gets the flat refusal.
///
/// Kept apart from [`check`] deliberately, so **queries keep refusing flat**. Elevation exists to
/// attribute an ACTION to the manager who approved it (rule 3: `created_by` / `approved_by`); a
/// PIN that unlocks a report leaves no such trace and would quietly turn the manager's PIN into a
/// see-everything key. Same reason the core `hub.*` namespace ([`crate::hub_users`]) stays on
/// [`check`]: administering the hub is not approved on the shop floor.
pub fn check_command(registry: &Registry, ctx: &RequestContext, required: &str) -> Result<()> {
    if has(ctx, required) {
        return Ok(());
    }
    if ctx.principal == Principal::Human && is_elevable(registry, required) {
        return Err(RuntimeError::RequiresElevation {
            permission: required.to_string(),
        });
    }
    Err(RuntimeError::PermissionDenied(required.to_string()))
}

/// Could a **manager** approve `permission`? Derived from the manifests, never declared by one —
/// there is no `requires_elevation` field a `module.json` could set, which is the whole point.
///
/// Rule 5 of the design says the level "is already in `role_permissions`", so this reads it back:
/// `permission` is elevable when the module that **owns** it grants it to [`ELEVABLE_ROLE`],
/// verbatim, while that module is **active**. Three guards, and each one closes a way a manifest
/// could otherwise mint privilege — the lesson of hub#351:
///
/// 1. **Ownership.** Only `<module_id>.…` counts, and only from that module's own manifest. A
///    third-party `module.zip` naming `till.manage_settings` or `hub.plan.change` in its
///    `role_permissions.manager` decides nothing about them. Same rule as the domain-error ABI
///    (hub#139): a module speaks only in its own namespace.
/// 2. **No wildcard.** `"*"` is a grant of everything to a session, not a statement that a
///    particular permission is manager-level. If it counted, one `role_permissions:{"manager":
///    ["*"]}` anywhere would make every permission in the hub — the admin ones included —
///    approvable by PIN.
/// 3. **Active only.** Same rule as [`crate::identity::permissions_for_role`]: a module that is
///    off grants nothing, so a PIN prompt can never point at a permission no live role holds.
///
/// Everything it cannot prove is elevable stays a flat refusal (default-deny).
pub fn is_elevable(registry: &Registry, permission: &str) -> bool {
    let Some((owner, action)) = permission.split_once('.') else {
        // No namespace, no owner: nothing to derive a level from (covers `""` and `"*"`).
        return false;
    };
    if owner.is_empty() || action.is_empty() {
        return false;
    }
    registry.installed.iter().any(|m| {
        m.id == owner
            && registry.is_active(&m.id)
            && m.role_permissions
                .get(ELEVABLE_ROLE)
                .is_some_and(|granted| granted.iter().any(|p| p == permission))
    })
}

#[cfg(test)]
mod elevation_tests {
    use super::*;
    use crate::manifest::Manifest;
    use crate::registry::{ModuleStatus, Registry};

    fn registry(manifests: &[&str]) -> Registry {
        let mut reg = Registry::new();
        for json in manifests {
            let m: Manifest = serde_json::from_str(json).unwrap();
            reg.status.insert(m.id.clone(), ModuleStatus::Active);
            reg.installed.push(m);
        }
        reg
    }

    const TILL: &str = r#"{"id":"till","name":"Till","version":"1.0.0",
        "role_permissions":{"admin":["*"],
          "manager":["till.view_sale","till.take_payment"],
          "employee":["till.view_sale"]}}"#;

    #[test]
    fn a_permission_its_owner_grants_to_manager_is_elevable() {
        let reg = registry(&[TILL]);
        assert!(is_elevable(&reg, "till.take_payment"));
        // Granted to `employee` too — still elevable, the cashier just never needs it.
        assert!(is_elevable(&reg, "till.view_sale"));
        // Reaches `admin` only through its `"*"`: not manager territory (rule 5).
        assert!(!is_elevable(&reg, "till.manage_settings"));
    }

    #[test]
    fn a_deactivated_module_stops_offering_elevation() {
        // Same rule as `identity::permissions_for_role`: an inactive module grants nothing. If
        // elevability survived deactivation, turning a module off would leave a PIN prompt
        // pointing at a permission no live role holds any more.
        let mut reg = registry(&[TILL]);
        assert!(is_elevable(&reg, "till.take_payment"));
        reg.status
            .insert("till".to_string(), ModuleStatus::Inactive);
        assert!(!is_elevable(&reg, "till.take_payment"));
    }

    #[test]
    fn a_manifest_cannot_mint_elevability() {
        // `"*"` is not a grant of anything in particular, and a module only speaks for its own
        // namespace — the same rule the domain-error ABI enforces (hub#139). Otherwise any
        // `module.zip` would decide that the core's or another module's permissions are
        // approvable by a four-digit PIN.
        let reg = registry(&[
            TILL,
            r#"{"id":"greedy","name":"Greedy","version":"1.0.0",
                "role_permissions":{"manager":["*","till.manage_settings","hub.users.view",
                  "greedy.ok"]}}"#,
        ]);
        assert!(!is_elevable(&reg, "till.manage_settings"));
        assert!(!is_elevable(&reg, "hub.users.view"));
        assert!(!is_elevable(&reg, "*"));
        assert!(!is_elevable(&reg, "anything.at.all"));
        // Its own namespace is the one thing it does decide.
        assert!(is_elevable(&reg, "greedy.ok"));
    }

    #[test]
    fn only_the_manager_key_elevates() {
        // Neither an administrator's grant nor a role the module invented makes a permission
        // approvable: there has to be a MANAGER who could have done it.
        let reg = registry(&[r#"{"id":"kds","name":"KDS","version":"1.0.0",
            "roles":[{"key":"chef","label":"Chef","extends":"manager"}],
            "role_permissions":{"admin":["kds.purge"],"chef":["kds.bump"],
              "employee":["kds.view"]}}"#]);
        assert!(!is_elevable(&reg, "kds.purge"));
        assert!(!is_elevable(&reg, "kds.bump"));
        assert!(!is_elevable(&reg, "kds.view"));
    }

    #[test]
    fn a_permission_without_a_namespace_is_never_elevable() {
        // No owner, no elevation. Covers the empty permission a command may declare, too.
        let reg = registry(&[TILL]);
        assert!(!is_elevable(&reg, ""));
        assert!(!is_elevable(&reg, "till"));
        assert!(!is_elevable(&reg, ".take_payment"));
    }

    #[test]
    fn an_empty_segment_never_finds_an_owner() {
        // The schema says a module id is `^[a-z][a-z0-9_]*$`, but a `module.zip` is a hostile
        // border and this runs on whatever deserialised. A manifest that calls itself `""` must
        // not become the owner of every permission that starts with a dot, and a grant of a
        // permission with an empty action (`till.`) must not elevate either.
        let nameless = registry(&[r#"{"id":"","name":"Nameless","version":"1.0.0",
            "role_permissions":{"manager":[".take_payment"]}}"#]);
        assert!(!is_elevable(&nameless, ".take_payment"));

        let dangling = registry(&[r#"{"id":"till","name":"Till","version":"1.0.0",
            "role_permissions":{"manager":["till."]}}"#]);
        assert!(!is_elevable(&dangling, "till."));
    }

    #[test]
    fn the_grant_has_to_be_the_permission_itself_not_a_prefix_and_not_a_wildcard() {
        // A module makes elevable only what it grants LITERALLY, and that has to hold for its OWN
        // namespace too — the ownership guard is not what carries this.
        let reg = registry(&[r#"{"id":"till","name":"Till","version":"1.0.0",
            "role_permissions":{"manager":["till.void"]}}"#]);
        assert!(is_elevable(&reg, "till.void"));
        // A prefix is not a grant: `till.void` must not quietly elevate `till.void_all` as well.
        assert!(!is_elevable(&reg, "till.void_all"));

        // `"*"` in its own `manager` list is a session grant, not the statement that some
        // particular permission is manager-level. If it counted, one sloppy manifest would make
        // every permission of its own module approvable by a four-digit PIN.
        let loose = registry(&[r#"{"id":"loose","name":"Loose","version":"1.0.0",
            "role_permissions":{"manager":["*"]}}"#]);
        assert!(!is_elevable(&loose, "loose.anything"));
        assert!(!is_elevable(&loose, "*"));
    }

    #[test]
    fn the_owner_is_the_first_segment_however_many_the_permission_has() {
        // The published catalogue writes `<module>.<entity>.<action>` (`inventory.products.create`)
        // as often as `<module>.<action>`. The owner is the FIRST segment; reading the namespace
        // from the other end would leave every three-segment permission with no owner at all —
        // i.e. silently never elevable.
        let reg = registry(&[r#"{"id":"inventory","name":"Inventory","version":"1.0.0",
            "role_permissions":{"manager":["inventory.products.create"]}}"#]);
        assert!(is_elevable(&reg, "inventory.products.create"));
        assert!(!is_elevable(&reg, "inventory.products.delete"));
    }

    #[test]
    fn check_command_only_relabels_a_refusal_it_never_grants_one() {
        let reg = registry(&[TILL]);
        let cashier = RequestContext::new("h1", "u1", ["till.view_sale".to_string()]);

        // Held → allowed, exactly as `check`.
        assert!(check_command(&reg, &cashier, "till.view_sale").is_ok());
        // Manager-level and missing → the refusal that asks for approval.
        assert!(matches!(
            check_command(&reg, &cashier, "till.take_payment"),
            Err(RuntimeError::RequiresElevation { permission }) if permission == "till.take_payment"
        ));
        // Admin-level and missing → flat refusal.
        assert!(matches!(
            check_command(&reg, &cashier, "till.manage_settings"),
            Err(RuntimeError::PermissionDenied(p)) if p == "till.manage_settings"
        ));
        // Whatever the label, the two branches agree with `check` on the ONE thing that matters:
        // who gets in. Elevation never opens a door `check` keeps shut.
        for required in [
            "till.view_sale",
            "till.take_payment",
            "till.manage_settings",
            "",
        ] {
            assert_eq!(
                check(&cashier, required).is_ok(),
                check_command(&reg, &cashier, required).is_ok(),
                "`{required}` must be allowed by exactly the same rule as before"
            );
        }
    }

    #[test]
    fn a_machine_principal_is_never_invited_to_ask_the_manager() {
        // hub#360 left this open on purpose: an API key has nobody standing at it, so
        // `requires_elevation` was an instruction it could not follow. It was only an absurd
        // message while elevation granted nothing — hub#361 makes it a door, and a stored,
        // copied, long-lived credential must not have one.
        let reg = registry(&[TILL]);
        let integration =
            RequestContext::new("h1", "apikey:k1", ["till.view_sale".to_string()]).as_machine();

        assert!(matches!(
            check_command(&reg, &integration, "till.take_payment"),
            Err(RuntimeError::PermissionDenied(p)) if p == "till.take_payment"
        ));
        // Everything else about a machine principal is unchanged: it still gets in where it holds
        // the permission, and it still gets the flat refusal where a human would too.
        assert!(check_command(&reg, &integration, "till.view_sale").is_ok());
        assert!(matches!(
            check_command(&reg, &integration, "till.manage_settings"),
            Err(RuntimeError::PermissionDenied(p)) if p == "till.manage_settings"
        ));
    }

    #[test]
    fn a_human_is_the_default_so_a_surface_that_says_nothing_behaves_as_before() {
        // The only thing `Machine` ever does is take capability away, so the default has to be
        // the ordinary one: a caller that forgets to declare itself must not silently lose the
        // dialog. (Every surface but the API key builds the context with `new`.)
        let reg = registry(&[TILL]);
        let ctx = RequestContext::new("h1", "u1", ["till.view_sale".to_string()]);
        assert_eq!(ctx.principal, crate::registry::Principal::Human);
        assert!(matches!(
            check_command(&reg, &ctx, "till.take_payment"),
            Err(RuntimeError::RequiresElevation { .. })
        ));
    }
}
