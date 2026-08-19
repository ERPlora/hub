//! Personal = **core** (ADR-0191): la pantalla de Personal del Hub lista los usuarios REALES del
//! hub (`hub_user`), no los miembros del módulo `staff`. El módulo `staff` es otra cosa (profesional
//! reservable, comisiones, horarios) y trae su propia navegación; el core no depende de él.
//!
//! Lo que estos tests fijan: **todo** usuario de la BD del hub sale en la lista — incluido el
//! owner/administrador, que entra por Cloud y NO tiene PIN (antes solo salía si era la sesión
//! activa), y los inactivos, marcados como tales.
use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::hub_users::{NewHubUser, UpdateHubUser};
use erplora_runtime::{RequestContext, Runtime};

async fn runtime(hub_id: &str) -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

async fn row(rt: &Runtime, id: &str) -> erplora_runtime::hub_users::HubUserRow {
    rt.list_hub_users()
        .await
        .unwrap()
        .into_iter()
        .find(|u| u.id == id)
        .expect("el usuario tiene que estar en la lista")
}

#[tokio::test]
async fn lists_every_user_of_the_hub_including_the_cloud_owner_without_pin() {
    let rt = runtime("hub-staff").await;
    // Owner: se provisiona en el primer login cloud, sin PIN local.
    let owner = rt
        .get_or_link_cloud_user("cloud-1", "Ioan Beilic", "owner", None, None)
        .await
        .unwrap();
    // Cajera: solo-local, con PIN.
    let cashier = rt
        .create_user("Marta Ruiz", "1234", "cashier", None)
        .await
        .unwrap();

    let users = rt.list_hub_users().await.unwrap();
    let ids: Vec<&str> = users.iter().map(|u| u.id.as_str()).collect();
    assert!(
        ids.contains(&owner.id.as_str()),
        "el owner cloud (sin PIN) tiene que salir en Personal"
    );
    assert!(ids.contains(&cashier.as_str()));

    let owner_row = users.iter().find(|u| u.id == owner.id).unwrap();
    assert_eq!(owner_row.role, "owner");
    assert_eq!(owner_row.cloud_user_id.as_deref(), Some("cloud-1"));
    assert!(!owner_row.has_pin, "el owner entra por Cloud, no por PIN");
    assert!(owner_row.is_active);
    assert!(!owner_row.created_at.is_empty());

    let cashier_row = users.iter().find(|u| u.id == cashier).unwrap();
    assert!(cashier_row.has_pin);
}

#[tokio::test]
async fn creates_updates_and_deactivates_users_with_their_email() {
    let rt = runtime("hub-staff").await;
    let id = rt
        .create_hub_user(&NewHubUser {
            name: "Marta Ruiz".into(),
            email: "marta@example.com".into(),
            // Un usuario de CUENTA lleva uno de los tres roles que el SaaS sabe poner en una
            // membresía (hub#356); `cashier` es de los que declara un módulo, y esos son del
            // personal LOCAL.
            role: "employee".into(),
            pin: "4821".into(),
            badge: String::new(),
            local: false,
        })
        .await
        .unwrap();

    let created = row(&rt, &id).await;
    assert_eq!(created.name, "Marta Ruiz");
    assert_eq!(created.email, "marta@example.com");
    assert_eq!(created.role, "employee");
    assert!(created.has_pin);
    assert!(
        rt.verify_pin("Marta Ruiz", "4821").await.unwrap().is_some(),
        "el PIN del alta sirve para entrar"
    );

    rt.update_hub_user(
        &id,
        &UpdateHubUser {
            name: Some("Marta Ruiz Gil".into()),
            email: Some("m.ruiz@example.com".into()),
            role: Some("manager".into()),
            ..UpdateHubUser::default()
        },
    )
    .await
    .unwrap();

    let updated = row(&rt, &id).await;
    assert_eq!(updated.name, "Marta Ruiz Gil");
    assert_eq!(updated.email, "m.ruiz@example.com");
    assert_eq!(updated.role, "manager");
    assert!(updated.has_pin, "editar el perfil no borra el PIN");

    // Baja = desactivar, nunca borrar: conserva historial y auditoría.
    rt.update_hub_user(
        &id,
        &UpdateHubUser {
            is_active: Some(false),
            ..UpdateHubUser::default()
        },
    )
    .await
    .unwrap();

    let inactive = row(&rt, &id).await;
    assert!(!inactive.is_active, "el inactivo sigue listado, marcado");
    assert!(
        rt.verify_pin("Marta Ruiz Gil", "4821")
            .await
            .unwrap()
            .is_none(),
        "un usuario inactivo no puede entrar"
    );
}

#[tokio::test]
async fn resets_the_pin_and_clears_it_when_empty() {
    let rt = runtime("hub-staff").await;
    let id = rt
        .create_hub_user(&NewHubUser {
            name: "Ana Soto".into(),
            // Usuario de CUENTA sin PIN: entra con su cuenta de ERPlora y aquí se le pone uno
            // después, que es justo lo que este test recorre (hub#356: el PIN es opcional en las
            // dos identidades, el email solo lo pide la de cuenta).
            email: "ana@example.com".into(),
            role: "employee".into(),
            pin: String::new(),
            badge: String::new(),
            local: false,
        })
        .await
        .unwrap();
    assert!(!row(&rt, &id).await.has_pin, "alta sin PIN");

    rt.update_hub_user(
        &id,
        &UpdateHubUser {
            pin: Some("4242".into()),
            ..UpdateHubUser::default()
        },
    )
    .await
    .unwrap();
    assert!(row(&rt, &id).await.has_pin);
    assert!(rt.verify_pin("Ana Soto", "4242").await.unwrap().is_some());

    rt.update_hub_user(
        &id,
        &UpdateHubUser {
            pin: Some(String::new()),
            ..UpdateHubUser::default()
        },
    )
    .await
    .unwrap();
    assert!(!row(&rt, &id).await.has_pin, "PIN vacío = se retira");
}

#[tokio::test]
async fn rejects_an_empty_name_a_bad_pin_and_a_bad_email() {
    let rt = runtime("hub-staff").await;

    let err = rt
        .create_hub_user(&NewHubUser {
            name: "   ".into(),
            email: String::new(),
            role: "employee".into(),
            pin: String::new(),
            badge: String::new(),
            local: false,
        })
        .await
        .unwrap_err();
    assert!(err.to_string().contains("nombre"), "{err}");

    let err = rt
        .create_hub_user(&NewHubUser {
            name: "Ana".into(),
            email: String::new(),
            role: "employee".into(),
            pin: "12".into(),
            badge: String::new(),
            local: false,
        })
        .await
        .unwrap_err();
    assert!(err.to_string().contains("PIN"), "{err}");

    let err = rt
        .create_hub_user(&NewHubUser {
            name: "Ana".into(),
            email: "no-es-un-email".into(),
            role: "employee".into(),
            pin: String::new(),
            badge: String::new(),
            local: false,
        })
        .await
        .unwrap_err();
    assert!(err.to_string().contains("email"), "{err}");

    let err = rt
        .create_hub_user(&NewHubUser {
            name: "Ana".into(),
            email: String::new(),
            role: "  ".into(),
            pin: String::new(),
            badge: String::new(),
            local: false,
        })
        .await
        .unwrap_err();
    assert!(err.to_string().contains("rol"), "{err}");
}

#[tokio::test]
async fn roles_are_core_and_count_their_members() {
    let rt = runtime("hub-roles").await;
    rt.get_or_link_cloud_user("cloud-1", "Ioan", "admin", None, None)
        .await
        .unwrap();
    rt.create_user("Marta", "1111", "cashier", None)
        .await
        .unwrap();
    rt.create_user("Luis", "2222", "cashier", None)
        .await
        .unwrap();

    let roles = rt.list_hub_roles().await.unwrap();

    // Catálogo base del core: existe aunque no haya ningún módulo instalado.
    for base in ["admin", "manager", "employee"] {
        assert!(
            roles.iter().any(|r| r.name == base),
            "falta el rol base {base}"
        );
    }
    assert_eq!(
        roles.iter().find(|r| r.name == "admin").unwrap().members,
        1,
        "el administrador cuenta como miembro"
    );
    let cashier = roles
        .iter()
        .find(|r| r.name == "cashier")
        .expect("un rol en uso sale aunque no esté en el catálogo base");
    assert_eq!(cashier.members, 2);
    assert_eq!(
        roles.iter().find(|r| r.name == "manager").unwrap().members,
        0,
        "un rol del catálogo sin usuarios sale con 0"
    );
}

// ── The business plane tops out at `admin` (plan step 2b, hub#349) ────────────────────────────
//
// `owner` was a name collision between the two planes — the ACCOUNT role (SaaS) and the BUSINESS
// role (hub) shared the word — and it only ever worked because the core gate treated it as an
// admin: **no** module grants it anything (24/24 declare only admin/manager/employee). So it
// leaves the base catalogue and `admin` becomes the top of the business plane.
//
// What must NOT change is what somebody who already carries `owner` can do. Real hubs seeded it
// (`identity::seed_owner`, ADR-0157), so the rows exist; the v12 system migration renames them to
// `admin` — same effective permissions, since the gate already answered "yes" to both and
// `permissions_for_role` already aliased `owner` to `admin` — and the gate keeps recognising the
// old spelling for any row that arrives without going through the migration.

#[tokio::test]
async fn owner_is_no_longer_offered_as_a_base_role() {
    assert_eq!(
        erplora_runtime::hub_users::BASE_ROLES,
        ["admin", "manager", "employee"].as_slice(),
        "the business plane tops out at `admin`; `owner` belongs to the account plane"
    );

    // And it is not in the catalogue a fresh hub offers, so nobody can be given it from Personal.
    let rt = runtime("hub-roles-base").await;
    let roles = rt.list_hub_roles().await.unwrap();
    assert!(
        !roles.iter().any(|r| r.name == "owner"),
        "a hub where nobody carries `owner` must not offer it: {:?}",
        roles.iter().map(|r| &r.name).collect::<Vec<_>>()
    );
}

#[tokio::test]
async fn a_row_that_still_carries_owner_keeps_every_administrative_power() {
    // Legacy compatibility, resolved on the conservative side: a row that reaches the hub without
    // going through the v12 migration — a restored backup, an import, a runtime still pinned to an
    // older image writing into the hub database — must not silently lose the hub. The gate keeps
    // saying yes, and the catalogue keeps listing the role because somebody is using it.
    assert!(
        erplora_runtime::hub_users::is_admin_role("owner"),
        "a legacy `owner` still administers the hub"
    );

    let rt = runtime("hub-roles-legacy").await;
    let legacy = rt.create_user("Boss", "9876", "owner", None).await.unwrap();
    assert_eq!(row(&rt, &legacy).await.role, "owner");

    let roles = rt.list_hub_roles().await.unwrap();
    let owner = roles
        .iter()
        .find(|r| r.name == "owner")
        .expect("a role in use is listed even when it left the base catalogue");
    assert_eq!(owner.members, 1);
}

// ── El core como proveedor del dispatcher: namespace reservado `hub.` ───────────────────────
// Un módulo (p. ej. `staff`, que vincula su ficha de profesional a un usuario del Hub) no puede
// pegar a rutas HTTP del core: el contrato es WC → SDK → dispatcher. Así que la identidad se
// expone como una query más, en un namespace que ningún módulo puede ocupar.

#[tokio::test]
async fn a_module_reads_the_hub_users_through_the_dispatcher() {
    let rt = runtime("hub-dispatch").await;
    rt.get_or_link_cloud_user("cloud-1", "Ioan Beilic", "owner", None, None)
        .await
        .unwrap();
    // Personal de barra: nombre + PIN y nada en el SaaS (hub#355). Es lo que un módulo ve por el
    // dispatcher, y el rol `cashier` —declarado, no del catálogo del SaaS— es justamente el de
    // alguien que solo existe en este hub.
    rt.create_hub_user(&NewHubUser {
        name: "Marta Ruiz".into(),
        role: "cashier".into(),
        pin: "4821".into(),
        badge: String::new(),
        local: true,
        ..NewHubUser::default()
    })
    .await
    .unwrap();

    let ctx = RequestContext::new("hub-dispatch", "u1", ["hub.users.view".to_string()]);
    let rows = rt
        .execute_query("hub.users.list", &Params::new(), &ctx)
        .await
        .expect("el core responde como un proveedor más");

    let marta = rows
        .iter()
        .find(|r| r["name"] == "Marta Ruiz")
        .expect("los usuarios del hub salen por el dispatcher");
    assert_eq!(marta["role"], "cashier");
    assert_eq!(marta["is_active"], true);
    assert!(marta["id"].is_string());
    assert!(
        marta.get("email").is_none(),
        "un módulo no necesita el email para vincular: no se le da"
    );
    assert!(rows.iter().any(|r| r["name"] == "Ioan Beilic"));
}

#[tokio::test]
async fn only_locally_authenticated_principals_read_the_users() {
    let rt = runtime("hub-dispatch").await;
    // Una API key de un tercero tiene permisos de SU scope de módulos: no lista el personal.
    let stranger = RequestContext::new(
        "hub-dispatch",
        "apikey:1",
        ["inventory.view_product".to_string()],
    );
    let err = rt
        .execute_query("hub.users.list", &Params::new(), &stranger)
        .await
        .unwrap_err();
    assert!(err.to_string().to_lowercase().contains("permis"), "{err}");

    // Cualquier usuario con SESIÓN local sí lo tiene: la lista ya es pública en el grid de PIN del
    // login. Se concede al abrir la sesión, no en el catálogo de roles.
    for role in ["owner", "admin", "manager", "employee", "cashier"] {
        assert!(
            rt.session_permissions(role).contains("hub.users.view"),
            "una sesión con rol {role} tiene que poder leer el personal"
        );
    }
}

#[tokio::test]
async fn the_core_permission_does_not_pollute_the_role_catalogue() {
    // `permissions_for_role` responde «qué conceden los MÓDULOS a este rol»: es lo que cuenta la
    // pestaña Roles y lo que hereda `owner` de `admin`. Meter ahí el permiso del core hacía que
    // hasta un rol que no existe en ningún manifest recibiera permisos — y que la pestaña Roles
    // pintara un permiso fantasma para todos. El permiso del core se concede en la SESIÓN.
    let rt = runtime("hub-dispatch").await;
    for role in ["owner", "employee", "un-rol-que-nadie-declara"] {
        assert!(
            rt.permissions_for_role(role).is_empty(),
            "sin módulos instalados, el catálogo no concede nada a {role}"
        );
    }
    assert!(rt.session_permissions("employee").contains("hub.users.view"));

    // Y el catálogo de roles no cuenta ese permiso como si lo diera un módulo.
    let roles = rt.list_hub_roles().await.unwrap();
    assert_eq!(
        roles.iter().find(|r| r.name == "employee").unwrap().permissions,
        0,
        "un rol sin módulos que le concedan nada muestra 0 permisos"
    );
}

#[tokio::test]
async fn the_hub_namespace_is_reserved_for_the_core() {
    let rt = runtime("hub-dispatch").await;
    // Una query inexistente del namespace del core NO se reporta como «módulo hub no instalado»
    // (eso haría que `queryOptional` se la tragase como ausencia): es un contrato roto.
    let ctx = RequestContext::new("hub-dispatch", "u1", ["hub.users.view".to_string()]);
    let err = rt
        .execute_query("hub.nope.list", &Params::new(), &ctx)
        .await
        .unwrap_err();
    assert!(err.to_string().contains("hub.nope.list"), "{err}");
    assert!(!err.to_string().contains("no instalado"), "{err}");
}

#[tokio::test]
async fn a_module_cannot_squat_the_core_namespace() {
    // Un `module.json` con id `hub` haría que sus queries `hub.*` fuesen inalcanzables (el
    // dispatcher resuelve el core antes) — y peor: parecería que las sirve él. Se rechaza al
    // instalar, que es la frontera hostil (un zip de terceros).
    let dir = std::env::temp_dir().join(format!("erplora-squat-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("module.json"),
        serde_json::json!({
            "id": "hub",
            "name": "Impostor",
            "version": "1.0.0",
            "queries": {},
            "commands": {}
        })
        .to_string(),
    )
    .unwrap();

    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "hub-squat");
    rt.ensure_system_tables().await.unwrap();
    let err = rt.install_from_dir(&dir).await.unwrap_err();
    assert!(
        err.to_string().contains("hub"),
        "el id reservado debe nombrarse en el error: {err}"
    );
    std::fs::remove_dir_all(&dir).ok();
}

/// The self-service door (`POST /api/auth/set-pin` → `Runtime::set_pin`) is the OTHER place a PIN
/// is chosen in clear — right after the first cloud login. It hashed whatever arrived: `0000`,
/// `1234`, two digits, letters. Same digits, same rules as Personal (hub#974): length, digits only,
/// and not one of the shapes anybody tries first (hub#355).
#[tokio::test]
async fn the_self_service_pin_door_applies_the_same_rules_as_personal() {
    let rt = runtime("hub-staff").await;
    let id = rt
        .create_hub_user(&NewHubUser {
            name: "Ana Soto".into(),
            email: "ana@example.com".into(),
            role: "employee".into(),
            pin: String::new(),
            badge: String::new(),
            local: false,
        })
        .await
        .unwrap();

    for bad in ["1234", "0000", "12", "abcd", "123456789"] {
        let err = rt
            .set_pin(&id, bad)
            .await
            .expect_err(&format!("`{bad}` must be refused at the self-service door"));
        let msg = format!("{err}");
        assert!(
            msg.contains("PIN") || msg.contains("pin"),
            "the refusal names the PIN: {msg}"
        );
        assert!(!row(&rt, &id).await.has_pin, "`{bad}` must not have been stored");
    }

    rt.set_pin(&id, "2580").await.unwrap();
    assert!(row(&rt, &id).await.has_pin);
    assert!(rt.verify_pin("Ana Soto", "2580").await.unwrap().is_some());

    // Empty still clears it (a user going back to account-only login).
    rt.set_pin(&id, "").await.unwrap();
    assert!(!row(&rt, &id).await.has_pin);
}
