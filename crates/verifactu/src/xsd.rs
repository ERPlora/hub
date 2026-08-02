//! Validación del sobre `RegFactuSistemaFacturacion` **antes** de transmitir a la AEAT.
//!
//! # Por qué antes, y por qué aquí
//!
//! La cadena fiscal es inmutable: cuando la AEAT contesta `Codigo[4102]. El XML no cumple el
//! esquema`, el registro **ya ha consumido su número**. Validar después de enviar no arregla
//! nada — hay que hacerlo antes de tocar la red.
//!
//! Y tiene que correr **en producción**. En el SaaS la validación existía pero su dependencia
//! (`xmlschema`) estaba en el grupo *dev*: la imagen desplegada no la instalaba y el código
//! degradaba, por diseño, a «se transmite sin validar» — la protección funcionaba en los tests y
//! era inerte donde importa (saas#1083). Aquí no hay nada que instalar: es código del propio
//! crate, sin dependencias opcionales ni `#[cfg(feature)]`. Si compila el binario, compila la
//! validación.
//!
//! # Qué es y qué NO es
//!
//! **No** es un motor XSD completo. Se descartó a propósito enlazar uno:
//!
//! - `libxml2` (la vía habitual en Rust) es una **dependencia nativa**, y este crate se compila
//!   también dentro de la app Tauri de escritorio y de **Android** (ADR-0180, misma app). Cruzar
//!   libxml2 a `aarch64-linux-android` convierte una salvaguarda fiscal en un proyecto de
//!   toolchain.
//! - Los validadores XSD en Rust puro publicados hoy son crates 0.1.x sin recorrido. Un **falso
//!   positivo** en la ruta fiscal no degrada: **para el TPV**. Es peor que el fallo que evita.
//!
//! Lo que hace es comprobar lo que la AEAT castiga de verdad, y lo hace **fiel al esquema**: la
//! tabla de obligatorios y el orden salen del XSD oficial vendorizado en `schemas/aeat/`, y
//! `tests/xsd.rs` los contrasta contra él en cada `cargo test` — el día que la AEAT publique una
//! versión nueva, ese test es el que se entera.
//!
//! Cubre: elementos obligatorios presentes y no vacíos · orden del `xs:sequence` · las
//! enumeraciones y formatos de los campos que este módulo emite · y las reglas de negocio con
//! código propio de la AEAT (1189 `Destinatarios`, 1100 `IdSistemaInformatico`).
//!
//! **No** cubre: tipos derivados que el módulo no emite, cardinalidades máximas, ni los bloques
//! opcionales que nunca se generan (`Subsanacion`, `Tercero`, `Cupon`, `ds:Signature`…). Un XML
//! que pase por aquí puede, en teoría, seguir siendo rechazado con 4102 por algo fuera de esa
//! lista; lo que ya no puede es salir con un obligatorio ausente o desordenado.
use crate::VerifactuError;

// ── Contrato del esquema (contrastado contra `schemas/aeat/` en tests/xsd.rs) ──────────────

/// Elementos `minOccurs="1"` del `xs:sequence` de `RegistroFacturacionAltaType`, en orden.
pub const REQUIRED_ALTA: &[&str] = &[
    "IDVersion",
    "NombreRazonEmisor",
    "TipoFactura",
    "DescripcionOperacion",
    "Desglose",
    "CuotaTotal",
    "ImporteTotal",
    "Encadenamiento",
    "SistemaInformatico",
    "FechaHoraHusoGenRegistro",
    "TipoHuella",
    "Huella",
];

/// Ídem para `RegistroFacturacionAnulacionType`.
pub const REQUIRED_ANULACION: &[&str] = &[
    "IDVersion",
    "Encadenamiento",
    "SistemaInformatico",
    "FechaHoraHusoGenRegistro",
    "TipoHuella",
    "Huella",
];

/// `IDFactura` es obligatorio en ambos tipos, pero se comprueba aparte: su contenido cambia entre
/// alta (`IDEmisorFactura`/`NumSerieFactura`/`FechaExpedicionFactura`) y anulación (los mismos
/// con sufijo `Anulada`), así que no encaja en la tabla plana de arriba.
const REQUIRED_ID_FACTURA_ALTA: &[&str] = &[
    "IDEmisorFactura",
    "NumSerieFactura",
    "FechaExpedicionFactura",
];
const REQUIRED_ID_FACTURA_ANULACION: &[&str] = &[
    "IDEmisorFacturaAnulada",
    "NumSerieFacturaAnulada",
    "FechaExpedicionFacturaAnulada",
];

/// Orden en que este módulo emite los elementos del `RegistroAlta`. Es una **subsecuencia** del
/// `xs:sequence` oficial (lo comprueba `tests/xsd.rs`).
pub const ORDER_ALTA: &[&str] = &[
    "IDVersion",
    "IDFactura",
    "NombreRazonEmisor",
    "TipoFactura",
    "FacturasSustituidas",
    "DescripcionOperacion",
    "Destinatarios",
    "Desglose",
    "CuotaTotal",
    "ImporteTotal",
    "Encadenamiento",
    "SistemaInformatico",
    "FechaHoraHusoGenRegistro",
    "TipoHuella",
    "Huella",
];

/// Ídem para el `RegistroAnulacion`.
const ORDER_ANULACION: &[&str] = &[
    "IDVersion",
    "IDFactura",
    "Encadenamiento",
    "SistemaInformatico",
    "FechaHoraHusoGenRegistro",
    "TipoHuella",
    "Huella",
];

/// `ClaveTipoFacturaType`. F1–F3 y R1–R5 son los que emite el módulo (`INVOICE_TYPES`).
const TIPO_FACTURA: &[&str] = &["F1", "F2", "F3", "R1", "R2", "R3", "R4", "R5"];

/// Tipos que exigen el bloque `Destinatarios`: sin él la AEAT responde **1189**.
const TIPOS_CON_DESTINATARIO: &[&str] = &["F1", "F3", "R1", "R2", "R3", "R4"];

/// `IdSistemaInformatico` está limitado a 2 caracteres (la AEAT responde 1100 si se pasa).
const MAX_ID_SISTEMA_INFORMATICO: usize = 2;

/// Elementos obligatorios que son **contenedores** (llevan hijos, no texto propio): exigirles
/// contenido los daría por vacíos siempre.
const CONTAINERS: &[&str] = &[
    "IDFactura",
    "Desglose",
    "Encadenamiento",
    "SistemaInformatico",
    "Destinatarios",
];

// ── Recorrido del XML ─────────────────────────────────────────────────────────────────────

/// Los elementos del documento como `(nombre local, texto)`, en orden. Ignora prefijos de
/// namespace, cierres, declaración y comentarios.
fn walk(xml: &str) -> Vec<(&str, &str)> {
    let bytes = xml.as_bytes();
    let mut out = Vec::new();
    let mut i = 0;
    while let Some(rel) = xml[i..].find('<') {
        let lt = i + rel;
        match bytes.get(lt + 1) {
            Some(&b'/') | Some(&b'?') | Some(&b'!') | None => {
                i = lt + 1;
                continue;
            }
            _ => {}
        }
        let after = &xml[lt + 1..];
        let Some(gt) = after.find('>') else { break };
        let name_end = after[..gt].find(['/', ' ', '\t', '\n', '\r']).unwrap_or(gt);
        let raw = &after[..name_end];
        let local = raw.rsplit(':').next().unwrap_or(raw);
        let text = if after[..gt].ends_with('/') {
            ""
        } else {
            let start = lt + 1 + gt + 1;
            match xml[start..].find('<') {
                Some(j) => xml[start..start + j].trim(),
                None => "",
            }
        };
        if !local.is_empty() {
            out.push((local, text));
        }
        i = lt + 1 + gt;
    }
    out
}

fn err(msg: impl Into<String>) -> VerifactuError {
    VerifactuError::Payload(msg.into())
}

fn text_of<'a>(elements: &[(&'a str, &'a str)], tag: &str) -> Option<&'a str> {
    elements.iter().find(|(t, _)| *t == tag).map(|(_, v)| *v)
}

fn present(elements: &[(&str, &str)], tag: &str) -> bool {
    elements.iter().any(|(t, _)| *t == tag)
}

/// Valida el sobre SOAP `RegFactuSistemaFacturacion` completo (cabecera + un registro).
///
/// Devuelve el **primer** problema encontrado, nombrando el elemento, para que el evento que se
/// persiste diga qué arreglar sin tener que releer el XML.
pub fn validate_registro(xml: &str) -> Result<(), VerifactuError> {
    let elements = walk(xml);
    if elements.is_empty() {
        return Err(err("el XML a transmitir está vacío o no es XML"));
    }
    if !present(&elements, "RegFactuSistemaFacturacion") {
        return Err(err(
            "el sobre no es un RegFactuSistemaFacturacion (SuministroLR.xsd)",
        ));
    }

    // ── Cabecera: ObligadoEmision exige NombreRazon y NIF ────────────────────────────────
    if !present(&elements, "ObligadoEmision") {
        return Err(err("falta Cabecera/ObligadoEmision"));
    }
    for tag in ["NombreRazon", "NIF"] {
        match text_of(&elements, tag) {
            Some(v) if !v.is_empty() => {}
            _ => {
                return Err(err(format!(
                    "ObligadoEmision/{tag} es obligatorio y viene vacío (identidad fiscal del \
                     negocio sin configurar)"
                )))
            }
        }
    }

    // ── El registro: alta o anulación ────────────────────────────────────────────────────
    let anulacion = present(&elements, "RegistroAnulacion");
    if !anulacion && !present(&elements, "RegistroAlta") {
        return Err(err(
            "el sobre no contiene ni RegistroAlta ni RegistroAnulacion",
        ));
    }
    let (required, order, id_factura) = if anulacion {
        (
            REQUIRED_ANULACION,
            ORDER_ANULACION,
            REQUIRED_ID_FACTURA_ANULACION,
        )
    } else {
        (REQUIRED_ALTA, ORDER_ALTA, REQUIRED_ID_FACTURA_ALTA)
    };

    // Obligatorios presentes y NO vacíos. Un elemento obligatorio vacío es exactamente lo que la
    // AEAT rechaza con «Falta informar campo obligatorio».
    if !present(&elements, "IDFactura") {
        return Err(err("falta IDFactura"));
    }
    for tag in id_factura {
        match text_of(&elements, tag) {
            Some(v) if !v.is_empty() => {}
            _ => {
                return Err(err(format!(
                    "IDFactura/{tag} es obligatorio y falta o va vacío"
                )))
            }
        }
    }
    for tag in required {
        // Contenedores: su texto propio está vacío por definición (llevan hijos), así que basta
        // con que el elemento esté presente.
        let contenedor = CONTAINERS.contains(tag);
        match text_of(&elements, tag) {
            Some(v) if contenedor || !v.is_empty() => {}
            Some(_) => return Err(err(format!("{tag} es obligatorio y viene vacío"))),
            None => {
                return Err(err(format!(
                    "{tag} es obligatorio y no está en el registro"
                )))
            }
        }
    }

    // ── Orden: los tipos de la AEAT son xs:sequence ──────────────────────────────────────
    let emitidos: Vec<&str> = elements
        .iter()
        .map(|(t, _)| *t)
        .filter(|t| order.contains(t))
        .collect();
    let mut esperado = order.iter();
    for tag in &emitidos {
        if !esperado.any(|e| e == tag) {
            return Err(err(format!(
                "`{tag}` va fuera de orden: la secuencia del esquema es {}",
                order.join(" → ")
            )));
        }
    }

    // ── Enumeraciones, formatos y reglas con código propio de la AEAT ────────────────────
    if !anulacion {
        let tipo = text_of(&elements, "TipoFactura").unwrap_or_default();
        if !TIPO_FACTURA.contains(&tipo) {
            return Err(err(format!(
                "TipoFactura `{tipo}` no está en la enumeración del esquema ({})",
                TIPO_FACTURA.join("|")
            )));
        }
        // Error 1189: los tipos que identifican destinatario NO pueden ir sin el bloque.
        if TIPOS_CON_DESTINATARIO.contains(&tipo) && !present(&elements, "Destinatarios") {
            return Err(err(format!(
                "una factura {tipo} exige el bloque Destinatarios; la AEAT la rechaza con el \
                 error 1189 (una venta sin NIF de cliente es una simplificada F2)"
            )));
        }
    }

    let id_si = text_of(&elements, "IdSistemaInformatico").unwrap_or_default();
    if id_si.chars().count() > MAX_ID_SISTEMA_INFORMATICO {
        return Err(err(format!(
            "IdSistemaInformatico `{id_si}` pasa de {MAX_ID_SISTEMA_INFORMATICO} caracteres; la \
             AEAT lo rechaza con el error 1100"
        )));
    }

    if text_of(&elements, "TipoHuella").unwrap_or_default() != "01" {
        return Err(err("TipoHuella solo admite `01` (SHA-256)"));
    }
    let huella = text_of(&elements, "Huella").unwrap_or_default();
    if huella.len() != 64 || !huella.chars().all(|c| c.is_ascii_hexdigit()) {
        return Err(err(
            "Huella debe ser un SHA-256 en hexadecimal (64 caracteres)",
        ));
    }

    Ok(())
}

// ── Lectura del XSD oficial (la usa tests/xsd.rs para contrastar las tablas) ───────────────

/// Nombres del `xs:sequence` de primer nivel del `complexType` `type_name` en `xsd_src`, en
/// orden de documento.
///
/// Es un scraper deliberadamente pequeño —solo sabe de `<complexType>`, `<sequence>` y
/// `<element>`—, suficiente para lo único que hace: contrastar que las tablas de este fichero
/// siguen correspondiéndose con el esquema oficial. **No** forma parte de la validación.
pub fn sequence_of(xsd_src: &str, type_name: &str) -> Option<Vec<String>> {
    Some(
        top_level_elements(xsd_src, type_name)?
            .into_iter()
            .map(|(n, _)| n)
            .collect(),
    )
}

/// Ídem, quedándose solo con los `minOccurs>=1`.
pub fn required_elements_of(xsd_src: &str, type_name: &str) -> Option<Vec<String>> {
    Some(
        top_level_elements(xsd_src, type_name)?
            .into_iter()
            .filter(|(_, min)| *min >= 1)
            .map(|(n, _)| n)
            // `IDFactura` se valida aparte (su contenido difiere entre alta y anulación).
            .filter(|n| n != "IDFactura")
            .collect(),
    )
}

/// `(nombre, minOccurs)` de los `<element>` que cuelgan DIRECTAMENTE del `xs:sequence` de primer
/// nivel del `complexType` indicado. Los anidados (dentro de un `complexType` inline) se saltan
/// contando profundidad.
fn top_level_elements(xsd_src: &str, type_name: &str) -> Option<Vec<(String, u32)>> {
    let start = xsd_src.find(&format!("complexType name=\"{type_name}\""))?;
    let rest = &xsd_src[start..];

    let mut out = Vec::new();
    let mut depth: i32 = 0; // profundidad relativa dentro del complexType
    let mut seq_depth: Option<i32> = None;
    let mut i = 0;
    while let Some(rel) = rest[i..].find('<') {
        let lt = i + rel;
        let after = &rest[lt + 1..];
        let Some(gt) = after.find('>') else { break };
        let tag_body = &after[..gt];

        if tag_body.starts_with('/') {
            depth -= 1;
            if depth < 0 {
                break; // se cerró el complexType
            }
            i = lt + 1 + gt;
            continue;
        }
        if tag_body.starts_with('?') || tag_body.starts_with('!') {
            i = lt + 1 + gt;
            continue;
        }
        let self_closing = tag_body.ends_with('/');
        let name_end = tag_body
            .find(['/', ' ', '\t', '\n', '\r'])
            .unwrap_or(tag_body.len());
        let local = {
            let raw = &tag_body[..name_end];
            raw.rsplit(':').next().unwrap_or(raw)
        };

        // Los hijos DIRECTOS del `sequence` se ven mientras `depth` vale lo que valía justo
        // después de abrirlo. Un `sequence` anidado (dentro de un `complexType` inline) no
        // reemplaza al primero, así que sus elementos caen fuera de esta condición.
        if local == "sequence" && seq_depth.is_none() {
            seq_depth = Some(depth + 1);
        } else if local == "element" && Some(depth) == seq_depth {
            if let Some(name) = attr(tag_body, "name") {
                let min = attr(tag_body, "minOccurs")
                    .and_then(|v| v.parse().ok())
                    .unwrap_or(1);
                out.push((name, min));
            }
        }
        if !self_closing {
            depth += 1;
        }
        i = lt + 1 + gt;
    }
    Some(out)
}

fn attr(tag_body: &str, name: &str) -> Option<String> {
    let needle = format!("{name}=\"");
    let i = tag_body.find(&needle)? + needle.len();
    let j = tag_body[i..].find('"')? + i;
    Some(tag_body[i..j].to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    const XSD: &str = include_str!("../schemas/aeat/SuministroInformacion.xsd");

    /// El scraper tiene que quedarse en el primer nivel: `RegistroFacturacionAltaType` tiene
    /// `complexType` inline (`FacturasRectificadas`, `Destinatarios`, `Encadenamiento`), y colar
    /// sus hijos como si fueran hermanos rompería la tabla de obligatorios.
    #[test]
    fn el_scraper_del_xsd_no_se_mete_en_los_complextype_inline() {
        let seq = sequence_of(XSD, "RegistroFacturacionAltaType").expect("tipo presente");

        assert_eq!(seq.first().map(String::as_str), Some("IDVersion"));
        assert_eq!(seq.last().map(String::as_str), Some("Huella"));
        // Hijos de `Encadenamiento` (complexType inline): NO son elementos de primer nivel.
        assert!(!seq.iter().any(|n| n == "PrimerRegistro"), "{seq:?}");
        assert!(!seq.iter().any(|n| n == "RegistroAnterior"), "{seq:?}");
        // Hijo de `Destinatarios` (inline).
        assert!(!seq.iter().any(|n| n == "IDDestinatario"), "{seq:?}");
    }

    #[test]
    fn el_scraper_distingue_obligatorios_de_opcionales() {
        let req = required_elements_of(XSD, "RegistroFacturacionAltaType").expect("tipo presente");

        assert!(req.iter().any(|n| n == "DescripcionOperacion"));
        assert!(
            !req.iter().any(|n| n == "RefExterna"),
            "RefExterna es minOccurs=0"
        );
        assert!(
            !req.iter().any(|n| n == "Destinatarios"),
            "Destinatarios es minOccurs=0 en el esquema: lo exige una REGLA de la AEAT (1189), \
             no el XSD"
        );
    }

    #[test]
    fn un_tipo_que_no_existe_devuelve_none() {
        assert!(sequence_of(XSD, "NoExisteEsteTipo").is_none());
    }

    #[test]
    fn walk_ignora_cierres_declaracion_y_autocerradas() {
        let els = walk("<?xml version=\"1.0\"?><a:X>1</a:X><Y/><!-- c --><Z>2</Z>");
        assert_eq!(els, vec![("X", "1"), ("Y", ""), ("Z", "2")]);
    }
}
