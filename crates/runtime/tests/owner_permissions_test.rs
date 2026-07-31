//! ERPlora/hub#257 (P0): el PROPIETARIO del hub no veía ningún dato de módulo.
//!
//! El provisioning siembra al creador con rol `owner` (`identity::seed_owner`, ADR-0157) y
//! `auth.rs` ya lo trata como admin para el gate FUERTE (ajustes, certificado, import/export).
//! Pero **ningún** módulo del catálogo declara `role_permissions.owner` —los 24 solo conocen
//! `admin`/`manager`/`employee`—, así que `identity::permissions_for_role(reg, "owner")`
//! devolvía el conjunto **vacío** y toda query de módulo respondía `permission_denied` (21 x
//! `403 POST /api/query` en consola tras importar un blueprint con 280 productos).
//!
//! `permissions_for_role` ahora resuelve `owner` como `admin`: no amplía privilegios, es
//! estrictamente menos de lo que ya le concede el gate admin. Estos tests lo fijan.

use erplora_runtime::identity::permissions_for_role;
use erplora_runtime::manifest::Manifest;
use erplora_runtime::registry::{ModuleStatus, Registry};

/// Manifiesto como los 24 reales del catálogo: conceden permisos a
/// `admin`/`manager`/`employee`, NINGUNO declara `owner`. Se parsea como un `module.json` real
/// (la única forma pública de construir un `Manifest`).
fn modulo_con_roles_habituales() -> Registry {
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
    .expect("manifiesto de prueba");
    let mut reg = Registry::new();
    reg.status
        .insert("inventory".into(), ModuleStatus::Active);
    reg.installed.push(manifest);
    reg
}

/// El PROPIETARIO del hub ve exactamente lo mismo que un admin: `permissions_for_role` resuelve
/// `owner` como `admin`. Sin este alias el dueño se quedaba con el conjunto vacío (ningún módulo
/// declara `role_permissions.owner`) y toda query de módulo le respondía `permission_denied`.
#[test]
fn owner_inherits_admin_module_permissions() {
    let reg = modulo_con_roles_habituales();

    let admin = permissions_for_role(&reg, "admin");
    let owner = permissions_for_role(&reg, "owner");

    assert!(!admin.is_empty(), "el fixture debe conceder permisos a admin");
    assert_eq!(
        owner, admin,
        "el owner debe ver el mismo conjunto de permisos de módulo que un admin"
    );
    // El permiso canónico que fallaba en el informe del cliente (21 x 403 POST /api/query).
    assert!(
        owner.contains("inventory.view_product"),
        "el owner debe tener inventory.view_product (la query que devolvía permission_denied)"
    );
}

/// El alias es insensible a mayúsculas/minúsculas (consistente con el gate owner/admin de
/// `auth.rs`, que compara con `to_ascii_lowercase`).
#[test]
fn owner_alias_is_case_insensitive() {
    let reg = modulo_con_roles_habituales();
    let admin = permissions_for_role(&reg, "admin");

    for variant in ["owner", "Owner", "OWNER"] {
        assert_eq!(
            permissions_for_role(&reg, variant),
            admin,
            "`{variant}` debe resolverse como admin"
        );
    }
}

/// `owner` es el ÚNICO alias: el resto de roles no cambia. Un rol que ningún módulo declara
/// (p. ej. `cajero`) sigue sin permisos — esto no abre una barra libre.
#[test]
fn only_owner_is_aliased_other_roles_unchanged() {
    let reg = modulo_con_roles_habituales();

    assert_eq!(
        permissions_for_role(&reg, "manager").len(),
        1,
        "manager sigue con su conjunto habitual (1 permiso)"
    );
    assert!(
        permissions_for_role(&reg, "employee").contains("inventory.view_product"),
        "employee mantiene su permiso de visualización"
    );
    assert!(
        permissions_for_role(&reg, "cajero").is_empty(),
        "un rol que ningún módulo declara no recibe permisos (owner es el único alias)"
    );
}

/// Un módulo **inactivo** no aporta permisos aunque declare el rol: `permissions_for_role` solo
/// agrega los de los módulos ACTIVOS (ARQUITECTURA.md §9.2). El alias owner→admin no lo cambia.
#[test]
fn inactive_module_grants_nothing_even_for_owner() {
    let reg = modulo_con_roles_habituales();
    // Desactivamos el único módulo del fixture.
    let mut inactive = reg;
    inactive
        .status
        .insert("inventory".into(), ModuleStatus::Inactive);

    assert!(
        permissions_for_role(&inactive, "owner").is_empty(),
        "un módulo inactivo no concede permisos (ni al owner)"
    );
    assert!(
        permissions_for_role(&inactive, "admin").is_empty(),
        "un módulo inactivo no concede permisos (ni al admin)"
    );
}
