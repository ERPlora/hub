//! **La ficha de `staff` cuelga de un usuario del Hub** (ADR-0192).
//!
//! `staff` es una capa de negocio SOBRE la identidad del core: el profesional que atiende es (casi
//! siempre) alguien que existe en `hub_user`. La columna `staff_member.user_id` estaba en el
//! esquema desde el porteo del monolito pero **ningún command la escribía**, así que las dos listas
//! vivían de espaldas: no había forma de decir «esta ficha es esta persona».
//!
//! Aquí se fija el contrato de la costura de punta a punta contra el módulo REAL del disco.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::hub_users::NewHubUser;
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn mdir(n: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(n)
}
fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

/// El modulo vive en `modules-workspace`, un repo HERMANO que el CI del hub no clona. Igual que
/// `kitchen_e2e` y compañia: si no esta en disco, el test se SALTA con aviso en vez de romper el
/// pipeline. En local (con el workspace al lado) se ejecuta de verdad contra el modulo real.
fn staff_en_disco() -> bool {
    mdir("staff").join("module.json").exists()
}

async fn rt_staff() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&mdir("staff"))
        .await
        .expect("instalar staff");
    rt
}

/// Alta de miembro con el payload completo (el runtime aún no aplica defaults de schema).
fn member_payload(first: &str, user_id: Option<&str>) -> serde_json::Value {
    json!({
        "first_name": first, "last_name": "Pro", "email": "", "phone": "", "employee_id": "",
        "role_id": null, "user_id": user_id, "hire_date": null, "status": "active", "bio": "",
        "specialties": "", "is_bookable": 1, "color": "", "hourly_rate": 0,
        "commission_rate": 0.0, "notes": ""
    })
}

#[tokio::test]
async fn a_staff_member_is_linked_to_a_hub_user() {
    if !staff_en_disco() {
        eprintln!("SKIP: modules-workspace/modules/staff ausente (repo hermano)");
        return;
    }
    let rt = rt_staff().await;
    let ctx = admin();
    let marta = rt
        .create_hub_user(&NewHubUser {
            name: "Marta Ruiz".into(),
            email: "marta@example.com".into(),
            role: "employee".into(),
            pin: "4821".into(),
            badge: String::new(),
            local: false,
        })
        .await
        .unwrap();

    rt.execute_command(
        "staff.members.create",
        &params(member_payload("Marta", Some(&marta))),
        &ctx,
    )
    .await
    .expect("alta de miembro vinculada a un usuario del Hub");

    let rows = rt
        .execute_query("staff.members.list", &Params::new(), &ctx)
        .await
        .unwrap();
    let member = rows.iter().find(|r| r["first_name"] == "Marta").unwrap();
    assert_eq!(
        member["user_id"], marta,
        "la lista tiene que decir de quién es la ficha"
    );

    // Y el detalle también: es lo que abre el formulario de edición.
    let detail = rt
        .execute_query(
            "staff.members.get",
            &params(json!({ "staff_id": member["id"] })),
            &ctx,
        )
        .await
        .unwrap();
    assert_eq!(detail[0]["user_id"], marta);
}

#[tokio::test]
async fn the_link_can_be_set_and_cleared_later() {
    if !staff_en_disco() {
        eprintln!("SKIP: modules-workspace/modules/staff ausente (repo hermano)");
        return;
    }
    let rt = rt_staff().await;
    let ctx = admin();
    let luis = rt
        .create_hub_user(&NewHubUser {
            name: "Luis Prat".into(),
            // Usuario de CUENTA: entra con su cuenta de ERPlora, sin PIN (hub#356).
            email: "luis@example.com".into(),
            role: "employee".into(),
            pin: String::new(),
            badge: String::new(),
            local: false,
        })
        .await
        .unwrap();

    // Ficha sin usuario: un profesional puede existir antes de tener acceso (o no tenerlo nunca).
    rt.execute_command(
        "staff.members.create",
        &params(member_payload("Luis", None)),
        &ctx,
    )
    .await
    .unwrap();
    let rows = rt
        .execute_query("staff.members.list", &Params::new(), &ctx)
        .await
        .unwrap();
    let id = rows[0]["id"].as_str().unwrap().to_string();
    assert!(rows[0]["user_id"].is_null(), "sin vincular al crear");

    // Vincular después.
    rt.execute_command(
        "staff.members.update",
        &params(json!({ "staff_id": id, "user_id": luis })),
        &ctx,
    )
    .await
    .unwrap();
    let detail = rt
        .execute_query(
            "staff.members.get",
            &params(json!({ "staff_id": id })),
            &ctx,
        )
        .await
        .unwrap();
    assert_eq!(detail[0]["user_id"], luis);

    // Una edición que NO menciona `user_id` no lo pierde (patrón COALESCE del módulo).
    rt.execute_command(
        "staff.members.update",
        &params(json!({ "staff_id": id, "phone": "600123123" })),
        &ctx,
    )
    .await
    .unwrap();
    let detail = rt
        .execute_query(
            "staff.members.get",
            &params(json!({ "staff_id": id })),
            &ctx,
        )
        .await
        .unwrap();
    assert_eq!(
        detail[0]["user_id"], luis,
        "editar el teléfono no desvincula"
    );

    // Desvincular explícitamente: cadena vacía = «ninguno» (un NULL en COALESCE significa
    // «no lo toques», así que hace falta un centinela distinto para poder borrar el vínculo).
    rt.execute_command(
        "staff.members.update",
        &params(json!({ "staff_id": id, "user_id": "" })),
        &ctx,
    )
    .await
    .unwrap();
    let detail = rt
        .execute_query(
            "staff.members.get",
            &params(json!({ "staff_id": id })),
            &ctx,
        )
        .await
        .unwrap();
    assert!(detail[0]["user_id"].is_null(), "se puede desvincular");
}

#[tokio::test]
async fn the_module_reaches_the_hub_users_through_the_dispatcher() {
    if !staff_en_disco() {
        eprintln!("SKIP: modules-workspace/modules/staff ausente (repo hermano)");
        return;
    }
    // La UI del módulo necesita ofrecer «¿qué usuario es?»: los lee del core como una query más.
    let rt = rt_staff().await;
    rt.create_hub_user(&NewHubUser {
        name: "Ana Soto".into(),
        role: "manager".into(),
        pin: "4242".into(),
        // Personal de barra: nombre + PIN y nada en el SaaS (hub#355).
        badge: String::new(),
        local: true,
        ..NewHubUser::default()
    })
    .await
    .unwrap();

    let ctx = RequestContext::new("h1", "u1", ["hub.users.view".to_string()]);
    let users = rt
        .execute_query("hub.users.list", &Params::new(), &ctx)
        .await
        .unwrap();
    assert!(users.iter().any(|u| u["name"] == "Ana Soto"));
}
