//! **A quién le damos NUESTRAS credenciales** (hub#1464, ADR-0431 §2).
//!
//! El hub no bloquea destinos —eso lo derogó ADR-0431 §1: la URL de un módulo es asunto del
//! módulo—, pero sí acota a quién le entrega lo suyo. `X-Hub-Token`, `X-Hub-Id`, el
//! `Authorization: Bearer` del usuario y `X-Webhook-Secret` (ADR-0003) solo viajan a **hosts de
//! ERPlora**: el de `HUB_CLOUD_API_URL` más los de `HUB_TRUSTED_HOSTS`.
//!
//! **Falla cerrado por construcción**: la lista extra vacía —el estado de un hub que no la
//! configuró, de un test y de un runtime embebido— deja como único host de confianza el de la
//! propia nube del hub, que es exactamente adonde va hoy todo el tráfico con credencial. Un guard
//! que por no estar configurado se vuelve un no-op es un guard que no existe.

use std::sync::OnceLock;

/// El host de una URL, en minúsculas y sin puerto. `None` si no se puede leer uno.
///
/// Sin dependencias nuevas: interesa el trozo entre `://` y el primer `/`, `?` o `#`, quitándole
/// el `user@` y el `:puerto`. Un parser completo de URL no compra nada aquí y sí trae superficie.
pub fn host_of(url: &str) -> Option<String> {
    let after_scheme = url.split_once("://")?.1;
    let authority = after_scheme
        .split(['/', '?', '#'])
        .next()
        .filter(|a| !a.is_empty())?;
    let host_port = authority.rsplit_once('@').map_or(authority, |(_, h)| h);
    // IPv6 literal: `[::1]:8080` — el puerto va DESPUÉS del corchete.
    let host = if let Some(rest) = host_port.strip_prefix('[') {
        let (inside, _) = rest.split_once(']')?;
        inside.to_string()
    } else {
        host_port.split(':').next()?.to_string()
    };
    if host.is_empty() {
        return None;
    }
    Some(host.to_ascii_lowercase())
}

/// Una entrada de `HUB_TRUSTED_HOSTS`: `erplora.com` (exacta) o `*.erplora.com` (subdominios).
fn matches(pattern: &str, host: &str) -> bool {
    match pattern.strip_prefix("*.") {
        // `*.erplora.com` cubre `pre.erplora.com`, NO `erplora.com` (para eso está la entrada
        // exacta o `HUB_CLOUD_API_URL`) y NO `erplora.com.evil.example`: el sufijo tiene que
        // TERMINAR el host, con su punto delante.
        Some(suffix) => !suffix.is_empty() && host.ends_with(&format!(".{suffix}")),
        None => host == pattern,
    }
}

/// Parsea `HUB_TRUSTED_HOSTS`: coma-separada, sin espacios, en minúsculas, sin vacíos.
pub fn parse_trusted_hosts(raw: &str) -> Vec<String> {
    raw.split(',')
        .map(|entry| entry.trim().to_ascii_lowercase())
        .filter(|entry| !entry.is_empty())
        .collect()
}

/// `HUB_TRUSTED_HOSTS` del entorno, leída UNA vez. Ausente = lista vacía (falla cerrado: solo la
/// nube del propio hub).
pub fn trusted_from_env() -> &'static [String] {
    static HOSTS: OnceLock<Vec<String>> = OnceLock::new();
    HOSTS.get_or_init(|| {
        parse_trusted_hosts(&std::env::var("HUB_TRUSTED_HOSTS").unwrap_or_default())
    })
}

/// ¿Le entregamos nuestras credenciales a esta URL?
///
/// `cloud_base_url` es `HUB_CLOUD_API_URL` y **siempre** es de confianza: es la nube de este hub.
/// `extra` son los patrones de `HUB_TRUSTED_HOSTS`.
pub fn is_ours(url: &str, cloud_base_url: &str, extra: &[String]) -> bool {
    let Some(host) = host_of(url) else {
        return false;
    };
    if host_of(cloud_base_url).is_some_and(|ours| ours == host) {
        return true;
    }
    extra.iter().any(|pattern| matches(pattern, &host))
}

#[cfg(test)]
mod tests {
    use super::*;

    const CLOUD: &str = "https://erplora.com";

    fn hosts(raw: &str) -> Vec<String> {
        parse_trusted_hosts(raw)
    }

    /// 🔒 Lo que esta guardia existe para impedir: la credencial de máquina no sale hacia un
    /// tercero. La AEAT es el caso real — el motor fiscal llama ahí a diario.
    #[test]
    fn a_foreign_host_never_gets_our_credentials() {
        for url in [
            "https://www2.agenciatributaria.gob.es/wlpl/SSII-FACT/ws/fe/SistemaFacturacion",
            "https://hooks.example.com/webhook",
            "http://169.254.169.254/latest/meta-data/",
        ] {
            assert!(
                !is_ours(url, CLOUD, &hosts("*.erplora.com")),
                "`{url}` no es nuestro"
            );
        }
    }

    /// Control positivo (regla de cero regresiones): una guardia que lo rechaza todo no guarda,
    /// rompe. Lo que hoy sí lleva credenciales tiene que seguir llevándolas.
    #[test]
    fn our_own_cloud_is_always_ours() {
        for url in [
            "https://erplora.com/api/v1/hub/device/heartbeat/",
            "https://erplora.com:8443/api/v1/hub/device/enroll/",
            "https://erplora.com/api/v1/hub/device/fiscal/gateway-token/",
        ] {
            assert!(is_ours(url, CLOUD, &[]), "`{url}` es nuestra nube");
        }
    }

    /// 🔒 El parecido no basta: los tres disfraces clásicos de un host ajeno.
    #[test]
    fn a_lookalike_host_is_not_ours() {
        for url in [
            "https://erplora.com.evil.example/api/v1/hub/device/heartbeat/",
            "https://noterplora.com/api/v1/hub/device/heartbeat/",
            "https://evil.example/?next=https://erplora.com/",
            "https://erplora.com@evil.example/api/",
        ] {
            assert!(
                !is_ours(url, CLOUD, &hosts("*.erplora.com,erplora.com")),
                "`{url}` NO es nuestro"
            );
        }
    }

    /// `*.erplora.com` cubre subdominios reales y solo eso.
    #[test]
    fn a_wildcard_covers_subdomains_and_nothing_else() {
        let list = hosts("*.erplora.com");
        assert!(is_ours("https://pre.erplora.com/api/", CLOUD, &list));
        assert!(is_ours(
            "https://verifactu-a.internal.erplora.com/v1/",
            CLOUD,
            &list
        ));
        assert!(!is_ours("https://evil-erplora.com/api/", CLOUD, &list));
        assert!(!is_ours(
            "https://erplora.com.evil.example/api/",
            CLOUD,
            &list
        ));
    }

    /// Sin `HUB_TRUSTED_HOSTS` solo hay un host de confianza: el de la propia nube. Falla CERRADO.
    #[test]
    fn without_the_env_list_only_our_own_cloud_is_trusted() {
        assert!(is_ours("https://erplora.com/api/", CLOUD, &[]));
        assert!(!is_ours("https://pre.erplora.com/api/", CLOUD, &[]));
    }

    /// El host del `cloud_base_url` se compara por HOST, no por prefijo de cadena: en dev es
    /// `http://localhost:8000` y en PRE otro, y los dos tienen que funcionar igual.
    #[test]
    fn the_cloud_base_url_is_compared_by_host() {
        assert!(is_ours(
            "http://localhost:8000/api/v1/hub/device/heartbeat/",
            "http://localhost:8000",
            &[]
        ));
        assert!(is_ours(
            "http://localhost:3000/api/",
            "http://localhost:8000/",
            &[]
        ));
        assert!(!is_ours(
            "http://otro-host:8000/api/",
            "http://localhost:8000",
            &[]
        ));
    }

    #[test]
    fn the_env_list_is_parsed_forgivingly() {
        assert_eq!(
            parse_trusted_hosts(" *.erplora.com , ERPlora.com ,, "),
            vec!["*.erplora.com".to_string(), "erplora.com".to_string()]
        );
        assert!(parse_trusted_hosts("").is_empty());
    }

    #[test]
    fn a_url_without_a_readable_host_is_never_ours() {
        for url in ["", "not-a-url", "https://", "/api/v1/relative/"] {
            assert!(!is_ours(url, CLOUD, &hosts("*.erplora.com")), "`{url}`");
        }
    }
}
