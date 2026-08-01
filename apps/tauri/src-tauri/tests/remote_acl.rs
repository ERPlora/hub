//! Guardia del ACL de orígenes REMOTOS (ADR-0159).
//!
//! El shell es un cliente fino: la webview navega a orígenes que NO son la app empaquetada, y
//! Tauri solo les deja llamar a `invoke` si el origen casa con algún patrón de
//! `capabilities/default.json` → `remote.urls`. Si un patrón no cubre la URL real de un hub, el
//! hardware queda MUERTO en producción — y no se nota hasta tener un hub real delante, porque en
//! dev se navega a loopback.
//!
//! Este test comprueba los patrones **declarados en el fichero real** (`include_str!`) con el
//! **mismo motor que Tauri usa en runtime** (`RemoteUrlPattern`, WHATWG URLPattern). Cubre el caso
//! que motivó el test: los hubs cloud viven en `https://{slug}.a.erplora.com` — **dos etiquetas**
//! bajo `erplora.com` (`Server.domain = "a.erplora.com"`), no una.

use std::str::FromStr;

use tauri::Url;
use tauri_utils::acl::RemoteUrlPattern;

/// El fichero de capabilities real, incrustado en compilación: si alguien lo edita y rompe el
/// matching, este test se cae en CI en vez de en el TPV de un cliente.
const CAPABILITY_JSON: &str = include_str!("../capabilities/default.json");

/// Patrones declarados en `remote.urls`, parseados igual que hace Tauri.
fn declared_patterns() -> Vec<RemoteUrlPattern> {
    let capability: serde_json::Value =
        serde_json::from_str(CAPABILITY_JSON).expect("capabilities/default.json no es JSON válido");

    capability["remote"]["urls"]
        .as_array()
        .expect("capabilities/default.json debe declarar remote.urls como array")
        .iter()
        .map(|value| {
            let raw = value.as_str().expect("cada remote.url debe ser un string");
            RemoteUrlPattern::from_str(raw)
                .unwrap_or_else(|e| panic!("patrón inválido {raw:?}: {e:?}"))
        })
        .collect()
}

/// `true` si ALGÚN patrón declarado autoriza esa URL (misma semántica que el ACL en runtime).
fn is_authorized(url: &str) -> bool {
    let parsed = Url::parse(url).unwrap_or_else(|e| panic!("URL de test inválida {url:?}: {e}"));
    declared_patterns().iter().any(|p| p.test(&parsed))
}

// ── Lo que DEBE estar autorizado ────────────────────────────────────────────────────────────────

#[test]
fn autoriza_un_hub_cloud_real_de_dos_etiquetas() {
    // Producción hoy: `Server.domain = "a.erplora.com"` → `https://{slug}.a.erplora.com`.
    // Si esto falla, `erplora_discover_printers` y compañía están rotos en el escritorio publicado.
    assert!(
        is_authorized("https://panaderia.a.erplora.com/"),
        "el ACL NO cubre un hub cloud real ({{slug}}.a.erplora.com) → el hardware está muerto en producción"
    );
}

#[test]
fn autoriza_cualquier_ruta_del_hub() {
    assert!(is_authorized("https://panaderia.a.erplora.com/pos/sale"));
    assert!(is_authorized("https://panaderia.a.erplora.com/?shell=1"));
}

#[test]
fn autoriza_las_urls_de_desarrollo() {
    assert!(is_authorized("http://127.0.0.1:5173/"), "PWA de Vite en dev");
    assert!(is_authorized("http://127.0.0.1:8787/"), "runtime local en dev");
}

// ── Lo que NO debe estar autorizado (controles negativos) ───────────────────────────────────────

#[test]
fn rechaza_un_origen_ajeno() {
    assert!(!is_authorized("https://example.com/"));
}

#[test]
fn rechaza_un_dominio_que_solo_contiene_el_nuestro_como_prefijo() {
    // El vector clásico de confusión de origen: un atacante registra `erplora.com.attacker.com`.
    assert!(
        !is_authorized("https://erplora.com.attacker.com/"),
        "un dominio atacante que EMPIEZA por erplora.com no puede pasar el ACL"
    );
}

#[test]
fn rechaza_http_remoto_no_loopback() {
    // Solo https en remoto; http queda para loopback de desarrollo.
    assert!(!is_authorized("http://panaderia.a.erplora.com/"));
}
