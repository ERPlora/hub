//! ERPlora/hub#257 (P0): the hub OWNER could not see a single row of module data.
//!
//! Provisioning used to seed the creator with the `owner` role (`identity::seed_owner`, ADR-0157)
//! and `auth.rs` already treated it as an admin for the STRONG gate (settings, certificate,
//! import/export). But **no** module in the catalogue declares `role_permissions.owner` — the 24 of
//! them only know `admin`/`manager`/`employee` — so `identity::permissions_for_role(reg, "owner")`
//! returned the **empty** set and every module query answered `permission_denied` (21 x
//! `403 POST /api/query` in the console after importing a blueprint with 280 products).
//!
//! `permissions_for_role` resolves `owner` as `admin`: it does not widen anything, it is strictly
//! less than what the admin gate already grants. These tests pin that down.
//!
//! Since hub#349 the role is **legacy**: `owner` left the hub role catalogue (`hub_users::
//! BASE_ROLES`), new hubs are seeded with `admin` and system migration v12 renames the rows that
//! carried it. The alias stays for the rows that reach the hub without going through the migration
//! — a restored backup, an import, a runtime still pinned to an older image — because dropping it
//! would take the hub away from an owner nobody can let back in.

use erplora_runtime::identity::permissions_for_role;
use erplora_runtime::manifest::Manifest;
use erplora_runtime::registry::{ModuleStatus, Registry};

/// A manifest like the 24 real ones in the catalogue: it grants permissions to
/// `admin`/`manager`/`employee`, and NONE of them declares `owner`. Parsed as a real `module.json`
/// (the only public way to build a `Manifest`).
fn module_with_the_usual_roles() -> Registry {
    let manifest: Manifest = serde_json::from_value(serde_json::json!({
        "id": "inventory",
        "name": "Inventory",
        "version": "1.0.0",
        "role_permissions": {
            "admin": ["inventory.view_product", "inventory.add_product"],
            "manager": ["inventory.view_product"],
            "employee": ["inventory.view_product"],
        },
    }))
    .expect("test manifest");
    let mut reg = Registry::new();
    reg.status.insert("inventory".into(), ModuleStatus::Active);
    reg.installed.push(manifest);
    reg
}

/// A row that still carries `owner` sees exactly what an admin sees: `permissions_for_role`
/// resolves it as `admin`. Without the alias the owner was left with the empty set (no module
/// declares `role_permissions.owner`) and every module query answered `permission_denied`.
#[test]
fn owner_inherits_admin_module_permissions() {
    let reg = module_with_the_usual_roles();

    let admin = permissions_for_role(&reg, "admin");
    let owner = permissions_for_role(&reg, "owner");

    assert!(!admin.is_empty(), "the fixture must grant permissions to admin");
    assert_eq!(
        owner, admin,
        "an owner must see the same set of module permissions as an admin"
    );
    // The canonical permission that failed in the customer report (21 x 403 POST /api/query).
    assert!(
        owner.contains("inventory.view_product"),
        "the owner must have inventory.view_product (the query that answered permission_denied)"
    );
}

/// The alias is case-insensitive (consistent with the owner/admin gate in `hub_users::
/// is_admin_role`, which compares with `to_ascii_lowercase`), and so is the v12 migration that
/// renames those rows.
#[test]
fn owner_alias_is_case_insensitive() {
    let reg = module_with_the_usual_roles();
    let admin = permissions_for_role(&reg, "admin");

    for variant in ["owner", "Owner", "OWNER"] {
        assert_eq!(
            permissions_for_role(&reg, variant),
            admin,
            "`{variant}` must resolve as admin"
        );
    }
}

/// `owner` is the ONLY alias: every other role is unchanged. A role no module declares (say
/// `cashier`) still gets nothing — this does not open a free-for-all.
#[test]
fn only_owner_is_aliased_other_roles_unchanged() {
    let reg = module_with_the_usual_roles();

    assert_eq!(
        permissions_for_role(&reg, "manager").len(),
        1,
        "manager keeps its usual set (1 permission)"
    );
    assert!(
        permissions_for_role(&reg, "employee").contains("inventory.view_product"),
        "employee keeps its view permission"
    );
    assert!(
        permissions_for_role(&reg, "cashier").is_empty(),
        "a role no module declares gets no permissions (owner is the only alias)"
    );
}

/// An **inactive** module grants nothing even if it declares the role: `permissions_for_role` only
/// aggregates ACTIVE modules (ARQUITECTURA.md §9.2). The owner→admin alias does not change that.
#[test]
fn inactive_module_grants_nothing_even_for_owner() {
    let reg = module_with_the_usual_roles();
    // Deactivate the only module in the fixture.
    let mut inactive = reg;
    inactive
        .status
        .insert("inventory".into(), ModuleStatus::Inactive);

    assert!(
        permissions_for_role(&inactive, "owner").is_empty(),
        "an inactive module grants nothing (not even to an owner)"
    );
    assert!(
        permissions_for_role(&inactive, "admin").is_empty(),
        "an inactive module grants nothing (not even to an admin)"
    );
}
