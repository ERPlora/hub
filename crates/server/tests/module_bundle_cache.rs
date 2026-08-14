//! Contrato: **un módulo actualizado tiene que poder LLEGAR al navegador** (hub#935).
//!
//! El defecto no era del módulo ni del camino de actualización: era la ENTREGA. `serve_module_asset`
//! servía todas las versiones desde la MISMA URL (`/modules/<id>/dist/<id>.esm.js`) y **sin una sola
//! cabecera de caché**. Sin directiva de frescura sobre un `.js`, cachear es lo que hacen tanto el
//! borde (Cloudflare cachea `.js` por extensión cuando el origen no dice nada — `cf-cache-status:
//! HIT`, `age: 236`) como el propio navegador (frescura heurística). Resultado medido en un hub real
//! en la MISMA carga de página:
//!
//! ```text
//! fetch('/modules/flows/dist/flows.esm.js', {cache:'reload'}) → el código NUEVO
//! customElements.get('erp-flows-editor').prototype            → el código VIEJO
//! ```
//!
//! El manifest decía 0.1.7, el servidor servía 0.1.7, y la pantalla ejecutaba 0.1.6. Sin ningún
//! aviso. Eso hace INVISIBLE el arreglo de cualquier módulo de la flota.
//!
//! Un `?v=<version>` no vale: el borde de esta zona ignora la query para la clave de caché (probado:
//! `?v=$RANDOM` sigue dando `HIT`). Lo que no puede ignorar es una **ruta distinta**. Así que la
//! versión va en la RUTA, y entonces sí se puede declarar la verdad de cada una:
//!
//! - `/modules/<id>/v/<version>/<path>` — el contenido de una versión NUNCA cambia → `immutable`.
//! - `/modules/<id>/<path>` — la ruta sin versión sigue existiendo (compatibilidad y `module.json`,
//!   que es justamente quien dice la versión) y por eso **tiene que revalidarse siempre**.
//!
//! Los dos tests de abajo separan a propósito las dos cosas que el bug confundía: que el SERVIDOR
//! mande lo nuevo, y que lo nuevo llegue a una DIRECCIÓN que ninguna caché haya visto antes.

use axum::body::Body;
use axum::http::{header, Request, StatusCode};
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::Value;
use std::path::{Path, PathBuf};
use tower::ServiceExt; // oneshot

fn cfg(module_cache: PathBuf) -> HubConfig {
    HubConfig {
        demo: false,
        hub_id: "hub-bundle-cache".into(),
        cloud_base_url: "https://erplora.com".into(),
        module_cache,
        auth_mode: AuthMode::Dev,
        jwt_public_key: None,
        cloud_api_token: Some("test-machine-token".into()),
        device_trust_enforce: false,
        media_dir: std::env::temp_dir().join("erplora-test-media-bundle-cache"),
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

/// Escribe `cache/<id>/<version>/` con un bundle cuyo cuerpo DELATA la versión que lo sirvió.
fn write_module(cache: &Path, id: &str, version: &str) -> PathBuf {
    let dir = cache.join(id).join(version);
    std::fs::create_dir_all(dir.join("dist")).unwrap();
    std::fs::write(
        dir.join("module.json"),
        format!(r#"{{"id":"{id}","name":"{id}","version":"{version}"}}"#),
    )
    .unwrap();
    std::fs::write(
        dir.join("dist").join(format!("{id}.esm.js")),
        format!("export const version = '{version}';\n"),
    )
    .unwrap();
    dir
}

struct Res {
    status: StatusCode,
    cache_control: String,
    body: String,
}

async fn get(router: axum::Router, uri: &str) -> Res {
    let resp = router
        .oneshot(Request::get(uri).body(Body::empty()).unwrap())
        .await
        .unwrap();
    let status = resp.status();
    let cache_control = resp
        .headers()
        .get(header::CACHE_CONTROL)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string();
    let body =
        String::from_utf8(resp.into_body().collect().await.unwrap().to_bytes().to_vec()).unwrap();
    Res {
        status,
        cache_control,
        body,
    }
}

/// Un temp dir propio por test (los tests del crate corren en paralelo sobre el mismo tmp).
fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-bundle-cache-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    dir
}

/// Lo que el bug rompía: **la versión nueva tiene que vivir en otra DIRECCIÓN.**
///
/// Que el servidor mande los bytes nuevos no basta —eso ya pasaba— si la URL por la que el navegador
/// los pide es la misma que la caché tiene resuelta desde hace rato. Aquí se comprueba lo otro: que
/// cada versión instalada es alcanzable por una URL que solo puede ser suya.
#[tokio::test]
async fn each_version_of_a_module_is_served_from_its_own_url() {
    let cache = scratch("own-url");
    let old = write_module(&cache, "demo", "0.1.6");
    write_module(&cache, "demo", "0.1.7");

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    rt.install_from_dir(&old).await.unwrap(); // el hub está en 0.1.6…
    let state = AppState::with_config(rt, cfg(cache.clone()));

    // …y aun así la 0.1.7 (ya descargada en la caché) se sirve por SU url, distinta de la de 0.1.6.
    let new = get(app(state.clone()), "/modules/demo/v/0.1.7/dist/demo.esm.js").await;
    assert_eq!(new.status, StatusCode::OK, "la url versionada debe servir");
    assert!(
        new.body.contains("0.1.7"),
        "la url de 0.1.7 debe servir el bundle de 0.1.7, no el instalado: {}",
        new.body
    );

    let previous = get(app(state.clone()), "/modules/demo/v/0.1.6/dist/demo.esm.js").await;
    assert!(previous.body.contains("0.1.6"), "cada versión, lo suyo");

    // La ruta sin versión sigue viva (compatibilidad): sirve la INSTALADA.
    let unversioned = get(app(state.clone()), "/modules/demo/dist/demo.esm.js").await;
    assert_eq!(unversioned.status, StatusCode::OK);
    assert!(unversioned.body.contains("0.1.6"));

    // Una versión que no está descargada no se inventa.
    let absent = get(app(state.clone()), "/modules/demo/v/9.9.9/dist/demo.esm.js").await;
    assert_eq!(absent.status, StatusCode::NOT_FOUND);

    // El segmento de versión es tan hostil como el resto de la ruta: no puede salir del dir.
    for evil in [
        "/modules/demo/v/%2e%2e/%2e%2e/secret",
        "/modules/demo/v/..%2f..%2fetc/passwd",
    ] {
        assert_eq!(
            get(app(state.clone()), evil).await.status,
            StatusCode::NOT_FOUND,
            "{evil} no puede escapar del module_cache"
        );
    }

    let _ = std::fs::remove_dir_all(&cache);
}

/// Y con la dirección resuelta, cada ruta declara la verdad sobre su frescura.
///
/// Sin esto el arreglo anterior sería solo la mitad: el navegador seguiría llegando al `module.json`
/// —quien DICE qué versión toca— a través de una copia cacheada, y construiría la url versionada de
/// la versión vieja. La ruta sin versión se revalida SIEMPRE; la versionada, jamás hace falta.
#[tokio::test]
async fn versioned_assets_are_immutable_and_unversioned_ones_always_revalidate() {
    let cache = scratch("headers");
    let dir = write_module(&cache, "demo", "0.1.7");

    let mut rt = Runtime::new(Box::new(fresh_db().await));
    rt.install_from_dir(&dir).await.unwrap();
    let state = AppState::with_config(rt, cfg(cache.clone()));

    let versioned = get(app(state.clone()), "/modules/demo/v/0.1.7/dist/demo.esm.js").await;
    assert_eq!(versioned.status, StatusCode::OK);
    assert!(
        versioned.cache_control.contains("immutable"),
        "el contenido de una versión no cambia nunca: {}",
        versioned.cache_control
    );
    assert!(
        versioned.cache_control.contains("max-age=31536000"),
        "y por eso se puede guardar un año: {}",
        versioned.cache_control
    );

    // El manifest es quien dice la versión. Servirlo de una caché es servir la versión de ayer.
    let manifest = get(app(state.clone()), "/modules/demo/module.json").await;
    assert_eq!(manifest.status, StatusCode::OK);
    assert!(
        manifest.cache_control.contains("no-cache"),
        "el module.json tiene que revalidarse siempre: {:?}",
        manifest.cache_control
    );
    assert!(
        !manifest.cache_control.contains("immutable"),
        "y nunca puede declararse inmutable: {}",
        manifest.cache_control
    );

    // La ruta sin versión de un bundle es la que mordía: misma url para todas las versiones.
    let legacy = get(app(state.clone()), "/modules/demo/dist/demo.esm.js").await;
    assert!(
        legacy.cache_control.contains("no-cache"),
        "una url que sirve «la instalada» cambia de contenido: no se puede cachear a ciegas: {:?}",
        legacy.cache_control
    );

    let _ = std::fs::remove_dir_all(&cache);
}

/// El shell tiene que poder construir la url versionada sin depender de un `module.json` cacheado.
///
/// `/api/navigation` va autenticada y ninguna caché la toca, así que la versión que dice es la que
/// el runtime tiene AHORA. Es la fuente honesta para la url del bundle.
#[tokio::test]
async fn navigation_tells_the_shell_which_version_each_module_is_at() {
    let fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../runtime/tests/fixture_inventory");
    let mut rt = Runtime::new(Box::new(fresh_db().await));
    rt.install_from_dir(&fixture).await.unwrap();
    let installed = rt
        .modules()
        .into_iter()
        .find(|m| m.id == "inventory")
        .expect("el fixture se instala")
        .version;

    let resp = app(AppState::with_config(
        rt,
        HubConfig::from_env_with_auth(AuthMode::Dev),
    ))
    .oneshot(Request::get("/api/navigation").body(Body::empty()).unwrap())
    .await
    .unwrap();
    assert_eq!(resp.status(), StatusCode::OK);
    let j: Value =
        serde_json::from_slice(&resp.into_body().collect().await.unwrap().to_bytes()).unwrap();

    let first = &j["data"][0];
    assert_eq!(
        first["module_version"].as_str(),
        Some(installed.as_str()),
        "cada item de navegación dice la versión instalada de su módulo: {j}"
    );
}
