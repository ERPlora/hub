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
        .get_or_link_cloud_user("cloud-1", "Ioan Beilic", "owner", None)
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
            role: "cashier".into(),
            pin: "1234".into(),
        })
        .await
        .unwrap();

    let created = row(&rt, &id).await;
    assert_eq!(created.name, "Marta Ruiz");
    assert_eq!(created.email, "marta@example.com");
    assert_eq!(created.role, "cashier");
    assert!(created.has_pin);
    assert!(
        rt.verify_pin("Marta Ruiz", "1234").await.unwrap().is_some(),
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
        rt.verify_pin("Marta Ruiz Gil", "1234")
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
            email: String::new(),
            role: "employee".into(),
            pin: String::new(),
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
        })
        .await
        .unwrap_err();
    assert!(err.to_string().contains("rol"), "{err}");
}

#[tokio::test]
async fn roles_are_core_and_count_their_members() {
    let rt = runtime("hub-roles").await;
    rt.get_or_link_cloud_user("cloud-1", "Ioan", "owner", None)
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
    for base in ["owner", "admin", "manager", "employee"] {
        assert!(
            roles.iter().any(|r| r.name == base),
            "falta el rol base {base}"
        );
    }
    assert_eq!(
        roles.iter().find(|r| r.name == "owner").unwrap().members,
        1,
        "el owner cuenta como miembro"
    );
    let cashier = roles
        .iter()
        .find(|r| r.name == "cashier")
        .expect("un rol en uso sale aunque no esté en el catálogo base");
    assert_eq!(cashier.members, 2);
    assert_eq!(
        roles.iter().find(|r| r.name == "admin").unwrap().members,
        0,
        "un rol del catálogo sin usuarios sale con 0"
    );
}

// ── El core como proveedor del dispatcher: namespace reservado `hub.` ───────────────────────
// Un módulo (p. ej. `staff`, que vincula su ficha de profesional a un usuario del Hub) no puede
// pegar a rutas HTTP del core: el contrato es WC → SDK → dispatcher. Así que la identidad se
// expone como una query más, en un namespace que ningún módulo puede ocupar.

#[tokio::test]
async fn a_module_reads_the_hub_users_through_the_dispatcher() {
    let rt = runtime("hub-dispatch").await;
    rt.get_or_link_cloud_user("cloud-1", "Ioan Beilic", "owner", None)
        .await
        .unwrap();
    rt.create_hub_user(&NewHubUser {
        name: "Marta Ruiz".into(),
        email: "marta@example.com".into(),
        role: "cashier".into(),
        pin: "1234".into(),
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

    // Cualquier ROL local sí lo tiene: la lista ya es pública en el grid de PIN del login. Y solo
    // eso: `permissions_for_role` no inventa ningún otro permiso del core.
    for role in ["owner", "admin", "manager", "employee", "cashier"] {
        let perms = rt.permissions_for_role(role);
        assert!(
            perms.contains("hub.users.view"),
            "el rol {role} tiene que poder leer el personal"
        );
        assert_eq!(
            perms.len(),
            1,
            "sin módulos instalados, {role} solo gana el permiso del core"
        );
    }
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
