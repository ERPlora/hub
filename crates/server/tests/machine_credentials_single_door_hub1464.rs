//! hub#1464: **las credenciales de ERPlora salen por UNA puerta** — `CloudClient::signed`, que es
//! la única que sabe adónde va la petición y por tanto la única que puede negarse (ADR-0431 §2).
//!
//! El compilador ya cierra la mitad grande: `Auth::headers` es `pub(crate)`, así que ningún crate
//! de fuera puede materializar una credencial. Lo que el compilador **no** ve es a alguien
//! escribiendo `.header("X-Hub-Token", …)` a mano sobre un `reqwest::RequestBuilder` — que es
//! exactamente como estaban `system.rs` y `usage_series.rs` cuando se abrió esta issue, y por lo
//! que el cuerpo original decía «un único punto» siendo tres.
//!
//! Alcance: código de PRODUCCIÓN de `crates/`. Los `tests/`, los `#[cfg(test)] mod` y los
//! comentarios quedan fuera: nombrar una cabecera para hablar de ella no es enviarla.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

/// Lo que no puede salir de casa sin pasar por la puerta (ADR-0003 + ADR-0431 §2).
const CREDENTIALS: [&str; 4] = [
    "X-Hub-Token",
    "X-Hub-Id",
    "X-Webhook-Secret",
    "Authorization",
];

/// Ficheros autorizados a adjuntar una credencial, con su porqué. La lista solo debería MENGUAR:
/// cada entrada nueva es una segunda puerta, y la lección de esta issue es que las segundas
/// puertas nacen sin que nadie las decida.
const DOORS: [(&str, &str); 2] = [
    (
        "crates/cloud-client/src/lib.rs",
        "LA puerta: `CloudClient::signed` comprueba el destino antes de firmar",
    ),
    (
        "crates/plugins/verifactu/src/gateway.rs",
        "El Bearer de la celda fiscal NO es credencial del hub: lo acuña nuestro propio Cloud \
         PARA esa celda, dura 300 s y su URL la sirve el plano de control (ADR-0425). Acotarlo \
         exige HUB_TRUSTED_HOSTS desplegada primero — hub#1470",
    ),
];

fn workspace_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

/// Líneas de producción que ADJUNTAN una credencial: la cabecera nombrada **y** una llamada que
/// la pone. Nombrarla en una doc-line o en una constante no cuenta.
fn attaching_lines(path: &Path) -> Vec<(usize, String)> {
    let text = fs::read_to_string(path).unwrap_or_default();
    let mut hits = Vec::new();
    let mut in_test = false;
    let mut pending_cfg = false;
    for (n, line) in text.lines().enumerate() {
        if in_test {
            if line == "}" {
                in_test = false;
            }
            continue;
        }
        let trimmed = line.trim_start();
        if trimmed == "#[cfg(test)]" {
            pending_cfg = true;
            continue;
        }
        if pending_cfg {
            // Una PILA de atributos entre `#[cfg(test)]` y `mod` es corriente
            // (`#[cfg(not(target_os = "android"))]` encima del módulo de tests) y NO puede
            // desactivar el salto: si lo hiciera, este guard leería un módulo de tests como
            // producción y avisaría de humo hasta que alguien aprendiese a ignorarlo.
            if trimmed.starts_with("#[") {
                continue;
            }
            pending_cfg = false;
            if trimmed.starts_with("mod ") {
                in_test = true;
                continue;
            }
        }
        if trimmed.starts_with("//") {
            continue;
        }
        let attaches = line.contains(".header(") || line.contains("headers.push");
        if attaches
            && CREDENTIALS
                .iter()
                .any(|c| line.contains(&format!("\"{c}\"")))
        {
            hits.push((n + 1, trimmed.to_string()));
        }
    }
    hits
}

fn scan(root: &Path) -> BTreeMap<String, Vec<(usize, String)>> {
    let mut out = BTreeMap::new();
    let mut stack = vec![root.join("crates")];
    while let Some(dir) = stack.pop() {
        let Ok(entries) = fs::read_dir(&dir) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            let name = entry.file_name().to_string_lossy().into_owned();
            if path.is_dir() {
                if name == "tests" || name == "target" {
                    continue;
                }
                stack.push(path);
            } else if name.ends_with(".rs") {
                let hits = attaching_lines(&path);
                if !hits.is_empty() {
                    let rel = path
                        .strip_prefix(root)
                        .unwrap_or(&path)
                        .to_string_lossy()
                        .replace('\\', "/");
                    out.insert(rel, hits);
                }
            }
        }
    }
    out
}

#[test]
fn hub1464_credentials_leave_by_one_door_only() {
    let doors: BTreeMap<&str, &str> = DOORS.iter().copied().collect();
    let mut violations = Vec::new();
    for (file, hits) in scan(&workspace_root()) {
        if doors.contains_key(file.as_str()) {
            continue;
        }
        let sample: Vec<String> = hits
            .iter()
            .take(4)
            .map(|(n, l)| format!("      {file}:{n}: {l}"))
            .collect();
        violations.push(format!(
            "  · {file}: {} línea(s) adjuntan una credencial\n{}",
            hits.len(),
            sample.join("\n")
        ));
    }
    assert!(
        violations.is_empty(),
        "\nhub#1464 — las credenciales de ERPlora salen por UNA puerta, `CloudClient::signed`, \
         que es la única que sabe el destino y puede negarse (ADR-0431 §2). Estos sitios las \
         adjuntan por su cuenta, así que ninguna comprobación de destino las alcanza:\n\n{}\n\n\
         Arreglo: construye la petición con `CloudClient` (`machine_request`, o el builder que \
         corresponda). Si de verdad es una puerta legítima, añádela a DOORS **en la misma PR** \
         con su porqué — y sabiendo que cada entrada es una comprobación que alguien deja de \
         tener.\n",
        violations.join("\n")
    );
}

/// Control positivo (regla de cero regresiones): una guardia que nunca vio rojo no guarda nada.
/// Se siembra la violación exacta que había en `usage_series.rs` — y, al lado, las formas que el
/// escáner DEBE ignorar.
#[test]
fn hub1464_the_check_catches_a_seeded_violation() {
    let root = std::env::temp_dir().join(format!("hub1464-seed-{}", std::process::id()));
    let src = root.join("crates/server/src");
    fs::create_dir_all(&src).unwrap();
    fs::write(
        src.join("leak.rs"),
        "// `X-Hub-Token` en un comentario es prosa, no un envío\n\
         const NAME: &str = \"X-Hub-Token\";\n\
         async fn call(http: &Client) {\n    \
             http.get(&url).header(\"X-Hub-Token\", token).send().await;\n\
         }\n\
         #[cfg(test)]\n\
         mod tests {\n    \
             fn t() { http.get(&u).header(\"X-Hub-Token\", t); }\n\
         }\n",
    )
    .unwrap();

    let found = scan(&root);
    let hits = found
        .get("crates/server/src/leak.rs")
        .expect("el escáner tiene que ver la fuga sembrada");

    assert_eq!(
        hits.len(),
        1,
        "una sola: ni el comentario, ni la constante, ni el `#[cfg(test)]` cuentan — {hits:?}"
    );
    assert!(hits[0].1.contains(".header(\"X-Hub-Token\""), "{hits:?}");
    fs::remove_dir_all(&root).ok();
}
