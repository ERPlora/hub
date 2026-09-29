//! hub#2356 — the checklist items that apps add speak the language of the person LOOKING at them.
//!
//! The dashboard list «Finish setting up your business» mixes two sources: the core items, which
//! the shell translates with its own i18n (and therefore in the language of the viewer's profile),
//! and the module items, which `hub.setup.status` resolves on the server from each module's
//! `locales/<lang>.json#setup`. The server used to pick that language from the HUB setting only, so
//! somebody whose profile said English saw «Your business details» next to «Tu numeración de
//! facturas» in the same list.
//!
//! The rule pinned here is the one the shell (`bootHubLanguage`) and the dispatcher's
//! `:caller_lang` (hub#1098) already follow: the viewer's own override (`hub_user_pref.language`)
//! → the hub setting (`hub_settings.language`) → the core default.

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::{json, Value as Json};

const HUB: &str = "hub-2356";
/// The `hub.` namespace gate every principal with a LOCAL session carries (see `setup_status.rs`).
const SESSION: &str = "hub.users.view";
const ADMINISTER: &str = erplora_runtime::hub_users::ADMINISTER_PERMISSION;

const TITLE_EN: &str = "Your invoice numbering";
const DESCRIPTION_EN: &str = "Choose how your invoices are numbered.";
const TITLE_ES: &str = "Tu numeración de facturas";
const DESCRIPTION_ES: &str = "Elige cómo se numeran tus facturas.";

async fn runtime() -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt
}

/// A module that ships its checklist item in English (the manifest, ADR-0055) with an `en` and an
/// `es` catalogue — exactly what `invoice` does in production.
fn translated_module() -> PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-setup-2356-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(dir.join("queries")).unwrap();
    std::fs::create_dir_all(dir.join("locales")).unwrap();
    let manifest = json!({
        "id": "numbering",
        "name": "numbering",
        "version": "1.0.0",
        "permissions": ["numbering.configure"],
        "queries": {
            "numbering.config.get": {
                "permission": "numbering.configure",
                "sql": "queries/config_get.sql"
            }
        },
        "setup": {
            "query": "numbering.config.get",
            "configured_when": [{ "field": "ready", "truthy": true }],
            "title": TITLE_EN,
            "description": DESCRIPTION_EN,
            "icon": "settings-outline",
            "route": "/m/numbering/settings",
            "permission": "numbering.configure"
        }
    });
    std::fs::write(dir.join("module.json"), manifest.to_string()).unwrap();
    std::fs::write(dir.join("queries/config_get.sql"), "SELECT 0 AS ready").unwrap();
    std::fs::write(
        dir.join("locales/en.json"),
        json!({ "setup": { "title": TITLE_EN, "description": DESCRIPTION_EN } }).to_string(),
    )
    .unwrap();
    std::fs::write(
        dir.join("locales/es.json"),
        json!({ "setup": { "title": TITLE_ES, "description": DESCRIPTION_ES } }).to_string(),
    )
    .unwrap();
    dir
}

async fn hub_with_module() -> Runtime {
    let mut rt = runtime().await;
    let dir = translated_module();
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();
    rt
}

async fn set_user_language(rt: &Runtime, user_id: &str, lang: &str) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert("user_id".into(), json!(user_id));
    p.insert("language".into(), json!(lang));
    rt.db_for_test()
        .execute(
            "INSERT INTO hub_user_pref (hub_id, user_id, language, theme_mode, theme_palette, updated_at) \
             VALUES (:hub_id, :user_id, :language, '', '', '2026-01-01T00:00:00Z')",
            &p,
        )
        .await
        .expect("seed the user's language override");
}

async fn set_hub_language(rt: &Runtime, lang: &str) {
    let mut updates = serde_json::Map::new();
    updates.insert("language".into(), json!(lang));
    rt.set_settings(&updates, "owner").await.unwrap();
}

/// The module item as `user_id` sees it: `(title, description)`.
async fn module_item_for(rt: &Runtime, user_id: &str) -> (String, String) {
    let ctx = RequestContext::new(
        HUB,
        user_id,
        [SESSION, ADMINISTER, "numbering.configure"]
            .iter()
            .map(|p| p.to_string()),
    );
    let rows = rt
        .execute_query("hub.setup.status", &Params::new(), &ctx)
        .await
        .expect("the core answers the setup status");
    let doc: &Json = rows.first().expect("one status document");
    let item = doc["items"]
        .as_array()
        .expect("`items` is an array")
        .iter()
        .find(|i| i["key"] == "numbering.setup")
        .unwrap_or_else(|| panic!("the module item is listed: {doc}"));
    (
        item["title"].as_str().unwrap_or_default().to_string(),
        item["description"].as_str().unwrap_or_default().to_string(),
    )
}

#[tokio::test]
async fn a_viewer_whose_profile_says_english_reads_the_app_items_in_english_hub2356() {
    // No `language` in the hub settings: the hub speaks its default (Spanish). The viewer chose
    // English in their profile — the whole list, core AND app items, must follow them.
    let rt = hub_with_module().await;
    set_user_language(&rt, "u-en", "en").await;

    assert_eq!(
        module_item_for(&rt, "u-en").await,
        (TITLE_EN.to_string(), DESCRIPTION_EN.to_string()),
        "the app item follows the viewer's profile, like the shell translates the core items"
    );
}

#[tokio::test]
async fn a_viewer_whose_profile_says_spanish_reads_them_in_spanish_in_an_english_hub_hub2356() {
    let rt = hub_with_module().await;
    set_hub_language(&rt, "en").await;
    set_user_language(&rt, "u-es", "es").await;

    assert_eq!(
        module_item_for(&rt, "u-es").await,
        (TITLE_ES.to_string(), DESCRIPTION_ES.to_string()),
        "the personal override wins over the hub setting in BOTH directions"
    );
}

#[tokio::test]
async fn two_people_on_the_same_hub_each_read_their_own_language_hub2356() {
    // Same hub, same request shape: only the person changes. A cached/shared locale would give
    // both of them the same answer.
    let rt = hub_with_module().await;
    set_hub_language(&rt, "es").await;
    set_user_language(&rt, "u-en", "en").await;

    assert_eq!(module_item_for(&rt, "u-en").await.0, TITLE_EN);
    assert_eq!(
        module_item_for(&rt, "u-nopref").await.0,
        TITLE_ES,
        "without a personal choice the viewer gets the hub's language"
    );
}

#[tokio::test]
async fn the_override_of_another_hub_does_not_leak_into_this_one_hub2356() {
    // `hub_user_pref` is keyed by (hub_id, user_id): the same person's choice in ANOTHER hub says
    // nothing about this one.
    let rt = hub_with_module().await;
    set_hub_language(&rt, "es").await;
    let mut p = Params::new();
    p.insert("user_id".into(), json!("u-shared"));
    rt.db_for_test()
        .execute(
            "INSERT INTO hub_user_pref (hub_id, user_id, language, theme_mode, theme_palette, updated_at) \
             VALUES ('some-other-hub', :user_id, 'en', '', '', '2026-01-01T00:00:00Z')",
            &p,
        )
        .await
        .unwrap();

    assert_eq!(module_item_for(&rt, "u-shared").await.0, TITLE_ES);
}
