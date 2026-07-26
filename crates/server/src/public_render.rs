//! Renderer de la presencia web pública del Hub (ADR-0160): convierte el JSON de bloques
//! (formato Editor.js) que se guarda por página a **HTML seguro**, SIN ejecutar NUNCA JS del
//! usuario. Este módulo ES la frontera de seguridad de la página pública.
//!
//! Principio: **default-deny**. Solo una allowlist de tipos de bloque se renderiza; cualquier
//! `type` desconocido se OMITE (no rompe la página). El HTML inline que guardan los tools
//! (`<b> <i> <a> <mark> <code>`) se sanea con `ammonia` (allowlist basada en html5ever); todo lo
//! demás se escapa. Nunca se emite `<script>`, `<iframe>`, atributos `on*` ni `style` del usuario.

use serde_json::Value;
use std::collections::{HashMap, HashSet};

/// Renderiza el documento de bloques (Editor.js) a HTML seguro. El documento es el JSON que guarda
/// el editor (`{ "blocks": [ { "type", "data" }, … ] }`); cada bloque conocido se renderiza y
/// cualquier `type` desconocido se OMITE (default-deny). Entrada sin `blocks` (o que no sea un
/// objeto con ese array) → cadena vacía, sin panic. **No ejecuta NUNCA JS del usuario**: el HTML
/// inline se sanea con [`sanitize_inline`] y el resto se escapa.
pub fn render_blocks(doc: &Value) -> String {
    let Some(blocks) = doc.get("blocks").and_then(Value::as_array) else {
        return String::new();
    };
    let mut out: Vec<String> = Vec::with_capacity(blocks.len());
    for block in blocks {
        if let Some(html) = render_block(block) {
            out.push(html);
        }
    }
    out.join("\n")
}

/// Renderiza UN bloque según su `type`. `None` ⇒ el bloque se omite: tipo desconocido (default-deny)
/// o `image` con un `src` no permitido. El `data` ausente se trata como `null` (campos → vacío).
fn render_block(block: &Value) -> Option<String> {
    let kind = block.get("type").and_then(Value::as_str)?;
    let null = Value::Null;
    let data = block.get("data").unwrap_or(&null);
    match kind {
        "header" => Some(render_header(data)),
        "paragraph" => Some(format!("<p>{}</p>", sanitize_inline(str_field(data, "text")))),
        "list" => Some(render_list(data)),
        "quote" => Some(render_quote(data)),
        "delimiter" => Some("<hr>".to_string()),
        "table" => Some(render_table(data)),
        "image" => render_image(data),
        // Default-deny: `raw`, `embed`, `code` de bloque, o cualquier tool nuevo → NO se renderiza.
        _ => None,
    }
}

/// `<h1>`–`<h6>` con el nivel ACOTADO a 1..=6 (un `level` fuera de rango o ausente no puede emitir
/// un tag inválido). Texto saneado como inline.
fn render_header(data: &Value) -> String {
    let level = data
        .get("level")
        .and_then(Value::as_i64)
        .unwrap_or(2)
        .clamp(1, 6);
    let text = sanitize_inline(str_field(data, "text"));
    format!("<h{level}>{text}</h{level}>")
}

/// `<ul>`/`<ol>` (según `style == "ordered"`). Cada item puede ser un string (Editor.js clásico) o
/// `{ content, items }` (listas anidadas); las sub-listas se renderizan recursivamente.
fn render_list(data: &Value) -> String {
    let ordered = data.get("style").and_then(Value::as_str) == Some("ordered");
    let tag = if ordered { "ol" } else { "ul" };
    let empty = Vec::new();
    let items = data
        .get("items")
        .and_then(Value::as_array)
        .unwrap_or(&empty);
    format!("<{tag}>{}</{tag}>", render_list_items(items))
}

fn render_list_items(items: &[Value]) -> String {
    let mut out = String::new();
    for item in items {
        let (content, children) = match item {
            Value::String(s) => (s.as_str(), None),
            Value::Object(_) => (
                item.get("content").and_then(Value::as_str).unwrap_or(""),
                item.get("items").and_then(Value::as_array),
            ),
            _ => ("", None),
        };
        out.push_str("<li>");
        out.push_str(&sanitize_inline(content));
        if let Some(children) = children.filter(|c| !c.is_empty()) {
            out.push_str("<ul>");
            out.push_str(&render_list_items(children));
            out.push_str("</ul>");
        }
        out.push_str("</li>");
    }
    out
}

/// `<blockquote>` con el texto en `<p>` y un `<cite>` opcional para el `caption`. Ambos saneados.
fn render_quote(data: &Value) -> String {
    let text = sanitize_inline(str_field(data, "text"));
    let caption = str_field(data, "caption");
    if caption.is_empty() {
        format!("<blockquote><p>{text}</p></blockquote>")
    } else {
        format!(
            "<blockquote><p>{text}</p><cite>{}</cite></blockquote>",
            sanitize_inline(caption)
        )
    }
}

/// `<table>` fila a fila. Si `withHeadings`, la primera fila usa `<th>`. Celdas saneadas como
/// inline (los tools guardan formato en las celdas). `content` ausente → tabla vacía.
fn render_table(data: &Value) -> String {
    let Some(rows) = data.get("content").and_then(Value::as_array) else {
        return String::new();
    };
    let with_headings = data
        .get("withHeadings")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let mut out = String::from("<table>");
    for (i, row) in rows.iter().enumerate() {
        let Some(cells) = row.as_array() else { continue };
        let cell_tag = if with_headings && i == 0 { "th" } else { "td" };
        out.push_str("<tr>");
        for cell in cells {
            let text = sanitize_inline(cell.as_str().unwrap_or(""));
            out.push_str(&format!("<{cell_tag}>{text}</{cell_tag}>"));
        }
        out.push_str("</tr>");
    }
    out.push_str("</table>");
    out
}

/// `<figure><img>` SOLO si el `src` referencia media del propio hub (ruta `/files`, ADR-0047).
/// Cualquier URL externa o esquema (`http(s)://…`, `javascript:`, `data:`…) ⇒ `None` (se descarta
/// la imagen entera). Soporta `data.file.url` (@editorjs/image) y `data.url` (@editorjs/simple-image).
/// `src` y `alt` se ESCAPAN (contexto de atributo/texto, no HTML inline).
fn render_image(data: &Value) -> Option<String> {
    let src = data
        .get("file")
        .and_then(|f| f.get("url"))
        .and_then(Value::as_str)
        .or_else(|| data.get("url").and_then(Value::as_str))
        .unwrap_or("");
    // Frontera: solo rutas de la carpeta media del hub. `starts_with("/files/")` evita que
    // `/filesX` (u otra ruta que comparta prefijo) cuele; `/files` exacto también se admite.
    if !(src == "/files" || src.starts_with("/files/")) {
        return None;
    }
    let src = escape_text(src);
    let alt = escape_text(str_field(data, "caption"));
    if alt.is_empty() {
        Some(format!("<figure><img src=\"{src}\" alt=\"\"></figure>"))
    } else {
        Some(format!(
            "<figure><img src=\"{src}\" alt=\"{alt}\"><figcaption>{alt}</figcaption></figure>"
        ))
    }
}

/// Lee un campo string del `data` de un bloque; ausente o no-string → `""`.
fn str_field<'a>(data: &'a Value, key: &str) -> &'a str {
    data.get(key).and_then(Value::as_str).unwrap_or("")
}

/// Escapa texto para insertarlo como contenido/atributo HTML (NO conserva ningún tag). Para los
/// campos que NO son HTML inline (p. ej. el `src`/`alt` de una imagen).
fn escape_text(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&#x27;"),
            _ => out.push(c),
        }
    }
    out
}

/// Sanea un fragmento de HTML **inline** con `ammonia` (allowlist estricta). Es la única puerta por
/// la que pasa el texto que los tools guardan como HTML. Config:
///   - tags permitidos: SOLO `b, i, a, mark, code, br` (todo lo demás se elimina, conservando texto);
///   - `<a>`: único atributo `href`, y solo esquemas `http`/`https`/`mailto` (un `javascript:` u
///     otro esquema deja el enlace sin href → neutralizado);
///   - sin atributos genéricos (ni `class`/`style`/`title`) y sin `on*` (no están en la allowlist);
///   - `<script>`/`<style>` se eliminan CON su contenido (clean_content_tags por defecto de ammonia).
fn sanitize_inline(html: &str) -> String {
    let tags: HashSet<&str> = ["b", "i", "a", "mark", "code", "br"].into_iter().collect();
    let url_schemes: HashSet<&str> = ["http", "https", "mailto"].into_iter().collect();
    let mut tag_attributes: HashMap<&str, HashSet<&str>> = HashMap::new();
    tag_attributes.insert("a", ["href"].into_iter().collect());
    ammonia::Builder::default()
        .tags(tags)
        .url_schemes(url_schemes)
        .tag_attributes(tag_attributes)
        .generic_attributes(HashSet::new())
        .clean(html)
        .to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    // ── Bloques estructurales ────────────────────────────────────────────────────────────────

    #[test]
    fn header_renderiza_hn_con_nivel_acotado() {
        let doc = json!({ "blocks": [
            { "type": "header", "data": { "text": "Bienvenido", "level": 2 } },
        ]});
        let html = render_blocks(&doc);
        assert!(html.contains("<h2>"), "esperaba <h2>, salió: {html}");
        assert!(html.contains("Bienvenido"));
        assert!(html.contains("</h2>"));
    }

    #[test]
    fn header_nivel_fuera_de_rango_se_acota_a_1_6() {
        let alto = render_blocks(&json!({ "blocks": [
            { "type": "header", "data": { "text": "X", "level": 99 } },
        ]}));
        assert!(alto.contains("<h6>"), "nivel 99 debe acotarse a h6: {alto}");

        let bajo = render_blocks(&json!({ "blocks": [
            { "type": "header", "data": { "text": "X", "level": 0 } },
        ]}));
        assert!(bajo.contains("<h1>"), "nivel 0 debe acotarse a h1: {bajo}");
    }

    #[test]
    fn paragraph_renderiza_p() {
        let html = render_blocks(&json!({ "blocks": [
            { "type": "paragraph", "data": { "text": "Hola mundo" } },
        ]}));
        assert!(html.contains("<p>Hola mundo</p>"), "salió: {html}");
    }

    #[test]
    fn list_unordered_y_ordered() {
        let ul = render_blocks(&json!({ "blocks": [
            { "type": "list", "data": { "style": "unordered", "items": ["uno", "dos"] } },
        ]}));
        assert!(ul.contains("<ul>"), "salió: {ul}");
        assert!(ul.contains("<li>uno</li>"));
        assert!(ul.contains("<li>dos</li>"));
        assert!(ul.contains("</ul>"));

        let ol = render_blocks(&json!({ "blocks": [
            { "type": "list", "data": { "style": "ordered", "items": ["a", "b"] } },
        ]}));
        assert!(ol.contains("<ol>"), "salió: {ol}");
        assert!(ol.contains("<li>a</li>"));
        assert!(ol.contains("</ol>"));
    }

    #[test]
    fn quote_renderiza_blockquote() {
        let html = render_blocks(&json!({ "blocks": [
            { "type": "quote", "data": { "text": "La cita", "caption": "Autor" } },
        ]}));
        assert!(html.contains("<blockquote>"), "salió: {html}");
        assert!(html.contains("La cita"));
        assert!(html.contains("Autor"));
        assert!(html.contains("</blockquote>"));
    }

    #[test]
    fn delimiter_renderiza_hr() {
        let html = render_blocks(&json!({ "blocks": [
            { "type": "delimiter", "data": {} },
        ]}));
        assert!(html.contains("<hr"), "salió: {html}");
    }

    #[test]
    fn table_renderiza_filas_y_celdas() {
        let html = render_blocks(&json!({ "blocks": [
            { "type": "table", "data": { "content": [["r1c1", "r1c2"], ["r2c1", "r2c2"]] } },
        ]}));
        assert!(html.contains("<table>"), "salió: {html}");
        assert!(html.contains("r1c1"));
        assert!(html.contains("r2c2"));
        assert!(html.contains("</table>"));
    }

    #[test]
    fn table_con_headings_usa_th() {
        let html = render_blocks(&json!({ "blocks": [
            { "type": "table", "data": { "withHeadings": true, "content": [["H1", "H2"], ["a", "b"]] } },
        ]}));
        assert!(html.contains("<th>H1</th>"), "esperaba th en la cabecera: {html}");
        assert!(html.contains("<td>a</td>"));
    }

    // ── Frontera de seguridad: HTML inline saneado ──────────────────────────────────────────

    #[test]
    fn inline_bold_y_enlace_https_se_conservan() {
        let html = render_blocks(&json!({ "blocks": [
            { "type": "paragraph", "data": { "text": "hola <b>fuerte</b> y <a href=\"https://erplora.com\">enlace</a>" } },
        ]}));
        assert!(html.contains("<b>fuerte</b>"), "el negrita debe conservarse: {html}");
        assert!(
            html.contains("href=\"https://erplora.com\""),
            "el enlace https debe conservarse: {html}"
        );
    }

    #[test]
    fn inline_href_javascript_se_neutraliza() {
        let html = render_blocks(&json!({ "blocks": [
            { "type": "paragraph", "data": { "text": "<a href=\"javascript:alert(1)\">click</a>" } },
        ]}));
        assert!(
            !html.contains("javascript:"),
            "el esquema javascript: debe eliminarse: {html}"
        );
        // El texto del enlace sobrevive; solo el href peligroso desaparece.
        assert!(html.contains("click"), "el texto del enlace debe sobrevivir: {html}");
    }

    #[test]
    fn inline_script_se_elimina() {
        let html = render_blocks(&json!({ "blocks": [
            { "type": "paragraph", "data": { "text": "texto<script>alert(1)</script>fin" } },
        ]}));
        assert!(!html.contains("<script"), "el <script> debe eliminarse: {html}");
        assert!(!html.contains("alert(1)"), "el contenido del script debe eliminarse: {html}");
        assert!(html.contains("texto"));
        assert!(html.contains("fin"));
    }

    #[test]
    fn inline_atributo_onclick_se_elimina() {
        let html = render_blocks(&json!({ "blocks": [
            { "type": "paragraph", "data": { "text": "<b onclick=\"evil()\">x</b>" } },
        ]}));
        assert!(!html.contains("onclick"), "los handlers on* deben eliminarse: {html}");
        assert!(html.contains("<b>x</b>"), "el tag permitido se conserva sin el atributo: {html}");
    }

    // ── Default-deny: tipos desconocidos ────────────────────────────────────────────────────

    #[test]
    fn bloque_desconocido_se_omite() {
        let html = render_blocks(&json!({ "blocks": [
            { "type": "raw", "data": { "html": "<iframe src=\"//evil\"></iframe>" } },
            { "type": "embed", "data": { "embed": "https://evil/x" } },
            { "type": "paragraph", "data": { "text": "sí visible" } },
        ]}));
        assert!(!html.contains("<iframe"), "raw/embed no deben renderizarse: {html}");
        assert!(!html.contains("evil"));
        assert!(html.contains("sí visible"), "el bloque conocido sí se renderiza: {html}");
    }

    // ── Bloque image: solo media del hub (/files, ADR-0047) ─────────────────────────────────

    #[test]
    fn image_de_files_renderiza_img() {
        let html = render_blocks(&json!({ "blocks": [
            { "type": "image", "data": { "file": { "url": "/files/menu/foto.png" }, "caption": "Un plato" } },
        ]}));
        assert!(html.contains("<img"), "debe renderizar img: {html}");
        assert!(html.contains("src=\"/files/menu/foto.png\""), "salió: {html}");
        assert!(html.contains("Un plato"), "el caption escapado debe aparecer: {html}");
    }

    #[test]
    fn image_url_externa_no_renderiza() {
        let html = render_blocks(&json!({ "blocks": [
            { "type": "image", "data": { "file": { "url": "https://evil/x.png" } } },
        ]}));
        assert!(!html.contains("<img"), "una url externa debe descartarse: {html}");
        assert!(!html.contains("evil"));
    }

    #[test]
    fn image_src_javascript_no_renderiza() {
        let html = render_blocks(&json!({ "blocks": [
            { "type": "image", "data": { "url": "javascript:alert(1)" } },
        ]}));
        assert!(!html.contains("<img"), "un src javascript: debe descartarse: {html}");
        assert!(!html.contains("javascript:"));
    }

    // ── Robustez: entradas degeneradas ──────────────────────────────────────────────────────

    #[test]
    fn sin_blocks_devuelve_vacio_sin_panic() {
        assert_eq!(render_blocks(&json!({})), "");
        assert_eq!(render_blocks(&json!({ "blocks": [] })), "");
        assert_eq!(render_blocks(&json!(null)), "");
        assert_eq!(render_blocks(&json!("no soy un objeto")), "");
    }
}
