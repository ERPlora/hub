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
use serde_json::{json, Value as Json};

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
    // Bloque rectificativo (hub#1023). El `xs:sequence` oficial intercala `FacturasSustituidas`
    // entre las rectificadas y el importe: no es un bloque contiguo, y emitirlo como tal sería
    // un 4102.
    "TipoRectificativa",
    "FacturasRectificadas",
    "FacturasSustituidas",
    "ImporteRectificacion",
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

/// `ClaveTipoRectificativaType` (hub#1023): `S` sustitutiva · `I` incremental (por diferencias).
/// Público para que `tests/rectificativa.rs` lo contraste contra el XSD oficial vendorizado.
pub const TIPO_RECTIFICATIVA: &[&str] = &["S", "I"];

/// Tipos de factura que **son** una rectificativa. Fuera de ellos, informar `TipoRectificativa`,
/// `FacturasRectificadas` o `ImporteRectificacion` es un rechazo de la AEAT.
const TIPOS_RECTIFICATIVOS: &[&str] = &["R1", "R2", "R3", "R4", "R5"];

// ── DetalleDesglose ────────────────────────────────────────────────────────────────────────
//
// Aquí es donde el XSD se queda corto y hay que poner reglas a mano. El esquema admite
// cualquier combinación de calificación con tipo y cuota: los cuatro casos que la AEAT rechaza
// —N1/N2 con tipo (1237), exenta con cuota (§15.5), S2 sin ceros (§15.4), régimen 08 sin N2
// (§15.6.6)— validan contra `DetalleType` igual de bien que una venta nacional correcta. Las
// referencias son al documento «Validaciones · Sistemas Informáticos de Facturación y Sistemas
// VERI*FACTU» v1.2.2 (08/04/2026), no a listados de errores de terceros (que llevan desfasados
// desde que en 2025 se eliminaron la excepción del régimen 17 y la restricción del régimen 18).

/// Orden del `xs:sequence` de `DetalleType`, con el `<choice>` intercalado en su sitio.
/// `tests/xsd.rs` lo contrasta contra el XSD oficial.
pub const ORDER_DETALLE: &[&str] = &[
    "Impuesto",
    "ClaveRegimen",
    // `<choice>`: uno de los dos, nunca los dos ni ninguno.
    "CalificacionOperacion",
    "OperacionExenta",
    "TipoImpositivo",
    "BaseImponibleOimporteNoSujeto",
    "BaseImponibleACoste",
    "CuotaRepercutida",
    "TipoRecargoEquivalencia",
    "CuotaRecargoEquivalencia",
];

/// `ImpuestoType` (L1): 01 IVA · 02 IPSI · 03 IGIC · 05 Otros.
pub const IMPUESTO: &[&str] = &["01", "02", "03", "05"];

/// `CalificacionOperacionType` (L9).
pub const CALIFICACION: &[&str] = &["S1", "S2", "N1", "N2"];

/// `OperacionExentaType` (L10 + E7/E8, que son exenciones **de IGIC**).
pub const OPERACION_EXENTA: &[&str] = &["E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"];

/// `IdOperacionesTrascendenciaTributariaType` — la unión de L8A (IVA) y L8B (IGIC).
pub const CLAVE_REGIMEN: &[&str] = &[
    "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "14", "15", "17", "18", "19",
    "20", "21",
];

/// Causas de exención que **solo** existen con IGIC (§15.5).
const EXENTA_SOLO_IGIC: &[&str] = &["E7", "E8"];

/// §15.1 — tipos de IVA admitidos con `Impuesto 01` y `CalificacionOperacion S1`. La lista es
/// cerrada, y es donde aterrizaba el recargo de equivalencia cuando salía como línea propia con
/// un `TipoImpositivo` del 5,20 %. (Los tipos 2 / 5 / 7,5 tuvieron ventanas de vigencia; no se
/// comprueban aquí porque acotar de más bloquearía rectificativas de aquellos periodos.)
const TIPOS_IVA: &[f64] = &[0.0, 2.0, 4.0, 5.0, 7.5, 10.0, 21.0];

/// §15.3 — tipos de recargo de equivalencia admitidos con IVA y `S1`.
const TIPOS_RECARGO: &[f64] = &[0.0, 0.26, 0.5, 0.62, 1.0, 1.4, 1.75, 5.2];

/// `DesgloseType` limita `DetalleDesglose` a `maxOccurs="12"`.
const MAX_DETALLES: usize = 12;

/// Tipos que exigen el bloque `Destinatarios`: sin él la AEAT responde **1189**.
const TIPOS_CON_DESTINATARIO: &[&str] = &["F1", "F3", "R1", "R2", "R3", "R4"];

/// `IdSistemaInformatico` está limitado a 2 caracteres (la AEAT responde 1100 si se pasa).
const MAX_ID_SISTEMA_INFORMATICO: usize = 2;

/// First element that switches §15.8 off: a billing agreement.
const EXEMPTION_BILLING_AGREEMENT: &str = "NumRegistroAcuerdoFacturacion";

/// The second one. The validations document writes `Articulo61d`; the **schema** says `Art61d`,
/// and the schema is what travels on the wire.
const EXEMPTION_ART_61D: &str = "FacturaSinIdentifDestinatarioArt61d";

/// Both, so that `tests/xsd.rs` can contrast the names the validator really looks for against the
/// official XSD: a name that never matches is an exemption that never applies — and an exemption
/// that never applies blocks a legitimate sale.
pub const F2_LIMIT_EXEMPTIONS: &[&str] = &[EXEMPTION_BILLING_AGREEMENT, EXEMPTION_ART_61D];

/// §15.8 — ceiling for Σ(`BaseImponibleOimporteNoSujeto` + `CuotaRepercutida`) of an `F2`, in
/// cents.
const MAX_F2_CENTS: i64 = 3_000 * 100;

/// …plus the +10,00 € margin the AEAT admits on top of it. The effective ceiling is therefore
/// 3.010,00 € **inclusive**: 3.010,00 passes, 3.010,01 does not.
const F2_TOLERANCE_CENTS: i64 = 10 * 100;

/// The §15.8 ceiling as ONE number, so the ingest gate (hub#1104) and this validator cannot
/// drift apart. `validate_limite_f2` refuses an over-the-ceiling `F2` at transmission time —
/// which is already too late when the `F2` was *manufactured* by downgrading an `F1` with no
/// recipient: by then the chain number is spent. The engine asks here BEFORE sealing.
pub(crate) const F2_CEILING_CENTS: i64 = MAX_F2_CENTS + F2_TOLERANCE_CENTS;

/// Only this value of `FacturaSinIdentifDestinatarioArt61d` exempts. The enumeration also has
/// `"N"`, which is a plain F2 and keeps the ceiling.
const ART_61D_EXEMPT: &str = "S";

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

/// Los elementos del documento como `(nombre local, texto, profundidad)`, en orden. Ignora
/// prefijos de namespace, cierres, declaración y comentarios.
///
/// **La profundidad no es decorativa.** `Encadenamiento/RegistroAnterior` repite nombres que
/// también están en la secuencia exterior (`IDEmisorFactura`, `NumSerieFactura`,
/// `FechaExpedicionFactura` y `Huella`). Sin saber a qué nivel cuelga cada uno, el validador
/// confundía la huella del registro ANTERIOR con la del registro que se está enviando: rechazaba
/// por «fuera de orden» toda factura encadenada —es decir, todas menos la primera— y comprobaba
/// el formato de la huella equivocada.
fn walk(xml: &str) -> Vec<(&str, &str, usize)> {
    let bytes = xml.as_bytes();
    let mut out = Vec::new();
    let mut depth = 0usize;
    let mut i = 0;
    while let Some(rel) = xml[i..].find('<') {
        let lt = i + rel;
        match bytes.get(lt + 1) {
            // Cierre `</tag>`: se sube un nivel.
            Some(&b'/') => {
                depth = depth.saturating_sub(1);
                i = lt + 1;
                continue;
            }
            Some(&b'?') | Some(&b'!') | None => {
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
        // `<tag/>` abre y cierra: no cambia la profundidad de lo que viene después.
        let self_closing = after[..gt].ends_with('/');
        let text = if self_closing {
            ""
        } else {
            let start = lt + 1 + gt + 1;
            match xml[start..].find('<') {
                Some(j) => xml[start..start + j].trim(),
                None => "",
            }
        };
        if !local.is_empty() {
            out.push((local, text, depth));
            if !self_closing {
                depth += 1;
            }
        }
        i = lt + 1 + gt;
    }
    out
}

fn err(msg: impl Into<String>) -> VerifactuError {
    VerifactuError::Payload(msg.into())
}

/// The same refusal as [`err`], plus the **stable code + facts** a module can translate
/// (hub#1576) — identical prose, identical `Display`, so nothing that reads the sentence moves.
///
/// It is added beside `err` rather than replacing it: `err` still serves the validators of the
/// desglose, the rectificativa and the F2 limit, which are unreachable from the diagnostic sample
/// and stay on the fallback prose for now (hub#1590).
fn named(code: &'static str, facts: Json, msg: impl Into<String>) -> VerifactuError {
    VerifactuError::Schema {
        code,
        facts,
        prose: msg.into(),
    }
}

type Element<'a> = (&'a str, &'a str, usize);

/// El `xs:sequence` de `CabeceraType`, escrito una vez: las dos formas de romperlo (el
/// representante delante del obligado, o detrás de la remisión voluntaria) publican el MISMO
/// código y los mismos hechos, así que la secuencia que viaja en ellos no puede divergir.
const CABECERA_SEQUENCE: &str = "ObligadoEmision → Representante → RemisionVoluntaria";

/// Posición del primer elemento con ese nombre, en orden de documento. Es lo que permite mirar
/// los hijos INMEDIATOS de un elemento cuando la profundidad no basta para distinguirlo de un
/// hermano del mismo tipo — `ObligadoEmision` y `Representante` son los dos
/// `PersonaFisicaJuridicaESType` y cuelgan del mismo nivel con las mismas etiquetas dentro.
fn index_of(elements: &[Element<'_>], tag: &str) -> Option<usize> {
    elements.iter().position(|(t, _, _)| *t == tag)
}

/// Primer elemento con ese nombre, a cualquier profundidad.
fn text_of<'a>(elements: &[Element<'a>], tag: &str) -> Option<&'a str> {
    elements
        .iter()
        .find(|(t, _, _)| *t == tag)
        .map(|(_, v, _)| *v)
}

/// Profundidad del primer elemento con ese nombre.
fn depth_of(elements: &[Element<'_>], tag: &str) -> Option<usize> {
    elements
        .iter()
        .find(|(t, _, _)| *t == tag)
        .map(|(_, _, d)| *d)
}

/// Primer elemento con ese nombre **a esa profundidad exacta**. Es lo que separa el
/// `Huella` del registro del `Huella` de su `RegistroAnterior`.
fn text_at<'a>(elements: &[Element<'a>], tag: &str, depth: usize) -> Option<&'a str> {
    elements
        .iter()
        .find(|(t, _, d)| *t == tag && *d == depth)
        .map(|(_, v, _)| *v)
}

fn present(elements: &[Element<'_>], tag: &str) -> bool {
    elements.iter().any(|(t, _, _)| *t == tag)
}

fn present_at(elements: &[Element<'_>], tag: &str, depth: usize) -> bool {
    elements.iter().any(|(t, _, d)| *t == tag && *d == depth)
}

/// Valida el sobre SOAP `RegFactuSistemaFacturacion` completo (cabecera + un registro).
///
/// Devuelve el **primer** problema encontrado, nombrando el elemento, para que el evento que se
/// persiste diga qué arreglar sin tener que releer el XML.
pub fn validate_registro(xml: &str) -> Result<(), VerifactuError> {
    let elements = walk(xml);
    if elements.is_empty() {
        return Err(named(
            "schema_envelope_empty",
            json!({}),
            "el XML a transmitir está vacío o no es XML",
        ));
    }
    if !present(&elements, "RegFactuSistemaFacturacion") {
        return Err(named(
            "schema_envelope_not_regfactu",
            json!({}),
            "el sobre no es un RegFactuSistemaFacturacion (SuministroLR.xsd)",
        ));
    }

    // ── Cabecera: ObligadoEmision exige NombreRazon y NIF ────────────────────────────────
    if !present(&elements, "ObligadoEmision") {
        return Err(named(
            "schema_header_issuer_missing",
            json!({}),
            "falta Cabecera/ObligadoEmision",
        ));
    }
    // El `Representante` (hub#1460) es el OTRO `PersonaFisicaJuridicaESType` de la cabecera y
    // lleva las mismas dos etiquetas dentro, así que se comprueba su posición ANTES de leer las
    // del obligado por nombre: si se colara delante, `text_of` estaría midiendo al representante
    // y dando por buena una identidad fiscal del negocio que nadie ha mirado.
    let representante = index_of(&elements, "Representante");
    if let (Some(rep), Some(obligado)) = (representante, index_of(&elements, "ObligadoEmision")) {
        if rep < obligado {
            return Err(named(
                "schema_element_out_of_order",
                json!({ "element": "Representante", "sequence": CABECERA_SEQUENCE }),
                "Representante va delante de ObligadoEmision; el xs:sequence de CabeceraType es \
                 ObligadoEmision → Representante → RemisionVoluntaria",
            ));
        }
    }
    for tag in ["NombreRazon", "NIF"] {
        match text_of(&elements, tag) {
            Some(v) if !v.is_empty() => {}
            _ => {
                return Err(named(
                    "schema_issuer_identity_incomplete",
                    json!({ "element": tag }),
                    format!(
                        "ObligadoEmision/{tag} es obligatorio y viene vacío (identidad fiscal \
                         del negocio sin configurar)"
                    ),
                ))
            }
        }
    }

    // ── Cabecera: Representante (minOccurs=0, pero completo si está) ─────────────────────────
    //
    // `PersonaFisicaJuridicaESType` exige `NombreRazon` **y** `NIF`, en ese orden. Medio
    // representante es un 4102 de la AEAT con el número de cadena ya gastado, y ese es justo el
    // fallo que este validador existe para adelantar: aquí el registro se marca `rejected`
    // localmente con el motivo, sin quemar el eslabón.
    if let Some(at) = representante {
        let depth = elements[at].2;
        for (offset, tag) in ["NombreRazon", "NIF"].into_iter().enumerate() {
            match elements.get(at + 1 + offset) {
                Some((t, v, d)) if *t == tag && *d == depth + 1 && !v.is_empty() => {}
                _ => {
                    return Err(named(
                        "schema_representative_incomplete",
                        json!({ "element": tag }),
                        format!(
                            "Representante/{tag} es obligatorio y falta o viene vacío \
                             (PersonaFisicaJuridicaESType exige NombreRazon y NIF, en ese orden)"
                        ),
                    ))
                }
            }
        }
        if let Some(voluntaria) = index_of(&elements, "RemisionVoluntaria") {
            if voluntaria < at {
                return Err(named(
                    "schema_element_out_of_order",
                    json!({ "element": "Representante", "sequence": CABECERA_SEQUENCE }),
                    "Representante va detrás de RemisionVoluntaria; el xs:sequence de \
                     CabeceraType es ObligadoEmision → Representante → RemisionVoluntaria",
                ));
            }
        }
    }

    // ── El registro: alta o anulación ────────────────────────────────────────────────────
    let anulacion = present(&elements, "RegistroAnulacion");
    if !anulacion && !present(&elements, "RegistroAlta") {
        return Err(named(
            "schema_record_missing",
            json!({}),
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

    // Todo lo que sigue se mide sobre los hijos DIRECTOS del registro. Sin ese anclaje, el
    // `RegistroAnterior` de una factura encadenada se cuela en la secuencia exterior.
    let registro_tag = if anulacion {
        "RegistroAnulacion"
    } else {
        "RegistroAlta"
    };
    let nivel = depth_of(&elements, registro_tag).unwrap_or(0) + 1;

    // Obligatorios presentes y NO vacíos. Un elemento obligatorio vacío es exactamente lo que la
    // AEAT rechaza con «Falta informar campo obligatorio».
    if !present_at(&elements, "IDFactura", nivel) {
        return Err(named(
            "schema_element_missing",
            json!({ "element": "IDFactura" }),
            "falta IDFactura",
        ));
    }
    for tag in id_factura {
        match text_at(&elements, tag, nivel + 1) {
            Some(v) if !v.is_empty() => {}
            _ => {
                return Err(named(
                    "schema_element_missing_or_empty",
                    json!({ "element": tag }),
                    format!("IDFactura/{tag} es obligatorio y falta o va vacío"),
                ))
            }
        }
    }
    for tag in required {
        // Contenedores: su texto propio está vacío por definición (llevan hijos), así que basta
        // con que el elemento esté presente.
        let contenedor = CONTAINERS.contains(tag);
        match text_at(&elements, tag, nivel) {
            Some(v) if contenedor || !v.is_empty() => {}
            Some(_) => {
                return Err(named(
                    "schema_element_empty",
                    json!({ "element": tag }),
                    format!("{tag} es obligatorio y viene vacío"),
                ))
            }
            None => {
                return Err(named(
                    "schema_element_missing",
                    json!({ "element": tag }),
                    format!("{tag} es obligatorio y no está en el registro"),
                ))
            }
        }
    }

    // ── Orden: los tipos de la AEAT son xs:sequence ──────────────────────────────────────
    let emitidos: Vec<&str> = elements
        .iter()
        .filter(|(_, _, d)| *d == nivel)
        .map(|(t, _, _)| *t)
        .filter(|t| order.contains(t))
        .collect();
    let mut esperado = order.iter();
    for tag in &emitidos {
        if !esperado.any(|e| e == tag) {
            return Err(VerifactuError::OutOfOrder {
                tag: tag.to_string(),
                sequence: order.join(" → "),
            });
        }
    }

    // ── Enumeraciones, formatos y reglas con código propio de la AEAT ────────────────────
    let tipo = text_at(&elements, "TipoFactura", nivel).unwrap_or_default();
    if !anulacion {
        if !TIPO_FACTURA.contains(&tipo) {
            return Err(named(
                "schema_value_not_in_enum",
                json!({
                    "element": "TipoFactura",
                    "value": tipo,
                    "allowed": TIPO_FACTURA.join("|"),
                }),
                format!(
                    "TipoFactura `{tipo}` no está en la enumeración del esquema ({})",
                    TIPO_FACTURA.join("|")
                ),
            ));
        }
        // Error 1189: los tipos que identifican destinatario NO pueden ir sin el bloque.
        if TIPOS_CON_DESTINATARIO.contains(&tipo) && !present_at(&elements, "Destinatarios", nivel)
        {
            return Err(named(
                "schema_recipient_block_required",
                json!({ "invoice_type": tipo }),
                format!(
                    "una factura {tipo} exige el bloque Destinatarios; la AEAT la rechaza con el \
                     error 1189 (una venta sin NIF de cliente es una simplificada F2)"
                ),
            ));
        }
        validate_rectificativa(&elements, tipo, nivel)?;
    }

    let id_si = text_of(&elements, "IdSistemaInformatico").unwrap_or_default();
    if id_si.chars().count() > MAX_ID_SISTEMA_INFORMATICO {
        return Err(named(
            "schema_value_too_long",
            json!({
                "element": "IdSistemaInformatico",
                "value": id_si,
                "max": MAX_ID_SISTEMA_INFORMATICO,
            }),
            format!(
                "IdSistemaInformatico `{id_si}` pasa de {MAX_ID_SISTEMA_INFORMATICO} caracteres; \
                 la AEAT lo rechaza con el error 1100"
            ),
        ));
    }

    // ── Desglose: la calificación, que el XSD deja pasar ─────────────────────────────────
    if !anulacion {
        validate_desglose(&elements)?;
        // Después del desglose a propósito: un detalle mal formado se nombra por lo que le pasa,
        // no por una suma que sale rara.
        validate_limite_f2(&elements, tipo, nivel)?;
    }

    let tipo_huella = text_at(&elements, "TipoHuella", nivel).unwrap_or_default();
    if tipo_huella != "01" {
        return Err(named(
            "schema_hash_type_unsupported",
            json!({ "value": tipo_huella }),
            "TipoHuella solo admite `01` (SHA-256)",
        ));
    }
    // La huella PROPIA del registro, no la de su `RegistroAnterior` (mismo nombre, un nivel más
    // abajo): comprobar la del anterior daba por buena una huella propia corrupta o vacía.
    let huella = text_at(&elements, "Huella", nivel).unwrap_or_default();
    if huella.len() != 64 || !huella.chars().all(|c| c.is_ascii_hexdigit()) {
        return Err(named(
            "schema_hash_malformed",
            json!({}),
            "Huella debe ser un SHA-256 en hexadecimal (64 caracteres)",
        ));
    }

    Ok(())
}

/// El bloque **rectificativo** del `RegistroAlta` (hub#1023) — las tres reglas que el XSD deja
/// pasar porque sus tres elementos son `minOccurs="0"`.
///
/// El esquema admite una R1 sin `TipoRectificativa`, una F1 con él, y una rectificativa por
/// diferencias que además declara el importe sustituido. La AEAT no: rechaza las tres, y para
/// entonces el registro **ya ha gastado su número de cadena**.
///
/// 1. **Toda R1–R5 declara `TipoRectificativa`.** Es lo que dice si los importes del registro son
///    los corregidos (`S`) o el delta (`I`); sin él, Hacienda no puede leer la devolución.
/// 2. **Nada rectificativo fuera de una R.** `TipoRectificativa`, `FacturasRectificadas` e
///    `ImporteRectificacion` solo son informables en una rectificativa.
/// 3. **`ImporteRectificacion` ⇔ `S`.** Es el desglose de lo que se sustituye: en una `S` es
///    obligatorio, y en una `I` —donde el registro ya declara el delta— sobra.
///
/// `FacturasRectificadas` se queda opcional a propósito: el esquema lo permite, y una R5 de un
/// tique puede no identificar el original. Exigirlo pararía el TPV por algo que la AEAT acepta.
fn validate_rectificativa(
    elements: &[Element<'_>],
    tipo: &str,
    nivel: usize,
) -> Result<(), VerifactuError> {
    let rectificativa = TIPOS_RECTIFICATIVOS.contains(&tipo);
    let tipo_rect = text_at(elements, "TipoRectificativa", nivel);
    let importe = present_at(elements, "ImporteRectificacion", nivel);

    if !rectificativa {
        for tag in [
            "TipoRectificativa",
            "FacturasRectificadas",
            "ImporteRectificacion",
        ] {
            if present_at(elements, tag, nivel) {
                return Err(err(format!(
                    "una factura {tipo} no rectifica nada, así que no puede informar {tag}: la \
                     AEAT solo lo admite con TipoFactura {}",
                    TIPOS_RECTIFICATIVOS.join("|")
                )));
            }
        }
        return Ok(());
    }

    let tipo_rect = match tipo_rect {
        Some(v) if !v.is_empty() => v,
        _ => {
            return Err(err(format!(
                "una rectificativa {tipo} exige TipoRectificativa ({}): sin él la AEAT la rechaza \
                 y el registro ya ha gastado su número de cadena",
                TIPO_RECTIFICATIVA.join("|")
            )))
        }
    };
    if !TIPO_RECTIFICATIVA.contains(&tipo_rect) {
        return Err(err(format!(
            "TipoRectificativa `{tipo_rect}` no está en la enumeración del esquema ({})",
            TIPO_RECTIFICATIVA.join("|")
        )));
    }

    match (tipo_rect, importe) {
        // Sustitutiva: el desglose de lo que sustituye es obligatorio.
        ("S", false) => Err(err(
            "una rectificativa por sustitución (TipoRectificativa=S) exige ImporteRectificacion \
             con la base y la cuota rectificadas",
        )),
        // Por diferencias: el registro YA declara el delta; el bloque sobra.
        ("I", true) => Err(err(
            "una rectificativa por diferencias (TipoRectificativa=I) ya declara el delta en sus \
             propios importes: ImporteRectificacion solo se informa con TipoRectificativa=S",
        )),
        _ => Ok(()),
    }
}

// ── Desglose / DetalleDesglose ─────────────────────────────────────────────────────────────

/// Trocea el documento en un grupo de elementos por cada `DetalleDesglose`.
fn detalles<'a>(elements: &[Element<'a>]) -> Vec<Vec<(&'a str, &'a str)>> {
    let mut out: Vec<Vec<(&str, &str)>> = Vec::new();
    let mut abierto = false;
    // La profundidad no hace falta aquí: `DetalleDesglose` abre el grupo y el primer elemento
    // ajeno a `ORDER_DETALLE` lo cierra, así que el troceo ya es por bloque.
    for (tag, text, _) in elements {
        if *tag == "DetalleDesglose" {
            out.push(Vec::new());
            abierto = true;
        } else if abierto && ORDER_DETALLE.contains(tag) {
            out.last_mut().expect("grupo abierto").push((tag, text));
        } else if abierto {
            abierto = false; // el detalle se cerró (llegó CuotaTotal, ImporteTotal…)
        }
    }
    out
}

/// Lee un importe/tipo de la AEAT (`21.00`) como `f64`.
fn num(v: &str) -> Option<f64> {
    v.trim().parse().ok()
}

/// ¿Coincide con alguno de los valores permitidos? Compara en céntesimas para no depender de la
/// representación binaria de `7.5` o `5.2`.
fn en_lista(v: f64, permitidos: &[f64]) -> bool {
    permitidos.iter().any(|p| ((p - v) * 100.0).abs() < 0.5)
}

/// Valida el bloque `Desglose` de un registro de alta.
fn validate_desglose(elements: &[Element<'_>]) -> Result<(), VerifactuError> {
    let grupos = detalles(elements);
    if grupos.is_empty() {
        return Err(err(
            "Desglose no lleva ningún DetalleDesglose: la AEAT no admite un desglose vacío",
        ));
    }
    if grupos.len() > MAX_DETALLES {
        return Err(err(format!(
            "el Desglose lleva {} líneas y el esquema admite {MAX_DETALLES} \
             (DesgloseType/DetalleDesglose maxOccurs=12)",
            grupos.len()
        )));
    }

    for (i, g) in grupos.iter().enumerate() {
        let n = i + 1;
        let get = |tag: &str| g.iter().find(|(t, _)| *t == tag).map(|(_, v)| *v);
        let hay = |tag: &str| get(tag).is_some();

        // Orden: `DetalleType` es un xs:sequence.
        let mut esperado = ORDER_DETALLE.iter();
        for (tag, _) in g {
            if !esperado.any(|e| e == tag) {
                return Err(VerifactuError::OutOfOrder {
                    tag: tag.to_string(),
                    sequence: format!("DetalleDesglose #{n}: {}", ORDER_DETALLE.join(" → ")),
                });
            }
        }

        // Impuesto (ausente ⇒ IVA, es el default explícito de la AEAT).
        let impuesto = get("Impuesto").unwrap_or("01");
        if !IMPUESTO.contains(&impuesto) {
            return Err(err(format!(
                "DetalleDesglose #{n}: Impuesto `{impuesto}` no está en la enumeración ({})",
                IMPUESTO.join("|")
            )));
        }
        let es_iva = impuesto == "01";
        let es_igic = impuesto == "03";

        // ClaveRegimen (§15.6): solo con IVA/IPSI/IGIC, y obligatoria con IVA e IGIC.
        let regimen = get("ClaveRegimen");
        match regimen {
            Some(r) if !CLAVE_REGIMEN.contains(&r) => {
                return Err(err(format!(
                    "DetalleDesglose #{n}: ClaveRegimen `{r}` no está en las listas L8A/L8B"
                )))
            }
            Some(_) if impuesto == "05" => {
                return Err(err(format!(
                    "DetalleDesglose #{n}: ClaveRegimen solo se admite con Impuesto 01, 02 o 03"
                )))
            }
            None if es_iva || es_igic => {
                return Err(err(format!(
                    "DetalleDesglose #{n}: ClaveRegimen es obligatoria con Impuesto \
                     {impuesto}; sin ella la AEAT responde 1245"
                )))
            }
            _ => {}
        }

        // El `<choice>`: CalificacionOperacion **o** OperacionExenta.
        let calificacion = get("CalificacionOperacion");
        let exenta = get("OperacionExenta");
        match (calificacion, exenta) {
            (Some(_), Some(_)) => {
                return Err(err(format!(
                    "DetalleDesglose #{n}: CalificacionOperacion y OperacionExenta son un \
                     <choice> del esquema — van una o la otra, no las dos"
                )))
            }
            (None, None) => {
                return Err(err(format!(
                    "DetalleDesglose #{n}: falta CalificacionOperacion u OperacionExenta \
                     (el <choice> exige una de las dos)"
                )))
            }
            _ => {}
        }
        if let Some(c) = calificacion {
            if !CALIFICACION.contains(&c) {
                return Err(err(format!(
                    "DetalleDesglose #{n}: CalificacionOperacion `{c}` no está en la \
                     enumeración ({})",
                    CALIFICACION.join("|")
                )));
            }
        }
        if let Some(e) = exenta {
            if !OPERACION_EXENTA.contains(&e) {
                return Err(err(format!(
                    "DetalleDesglose #{n}: OperacionExenta `{e}` no está en la enumeración ({})",
                    OPERACION_EXENTA.join("|")
                )));
            }
            if EXENTA_SOLO_IGIC.contains(&e) && !es_igic {
                return Err(err(format!(
                    "DetalleDesglose #{n}: OperacionExenta `{e}` solo existe con Impuesto 03 \
                     (IGIC); con IVA la lista es E1–E6"
                )));
            }
        }

        if !hay("BaseImponibleOimporteNoSujeto") {
            return Err(err(format!(
                "DetalleDesglose #{n}: BaseImponibleOimporteNoSujeto es obligatorio"
            )));
        }

        // Los cuatro campos que dependen de la calificación.
        let importes = [
            "TipoImpositivo",
            "CuotaRepercutida",
            "TipoRecargoEquivalencia",
            "CuotaRecargoEquivalencia",
        ];

        // §15.5 — con OperacionExenta no se informa ninguno.
        if exenta.is_some() {
            if let Some(t) = importes.iter().find(|t| hay(t)) {
                return Err(err(format!(
                    "DetalleDesglose #{n}: una línea con OperacionExenta no puede informar \
                     `{t}` (validaciones AEAT §15.5)"
                )));
            }
        }

        if let Some(c) = calificacion {
            // **Error 1237** — con N1/N2 no se informa ninguno de los cuatro.
            //
            // Sin excepción por `ClaveRegimen 17`: la revisión v1.0.6 (25/04/2025) del documento
            // de validaciones eliminó esa referencia, y §15.7 no admite cuota distinta de cero
            // fuera de S1 para ningún impuesto.
            if matches!(c, "N1" | "N2") {
                if let Some(t) = importes.iter().find(|t| hay(t)) {
                    return Err(err(format!(
                        "DetalleDesglose #{n}: con CalificacionOperacion `{c}` no se puede \
                         informar `{t}` — es el error 1237 de la AEAT, y el régimen 17 dejó de \
                         ser una excepción en abril de 2025"
                    )));
                }
            }

            // §15.4 — S2 es el caso al revés: los ceros van EXPLÍCITOS.
            if c == "S2" {
                for tag in ["TipoImpositivo", "CuotaRepercutida"] {
                    match get(tag).and_then(num) {
                        Some(v) if v == 0.0 => {}
                        Some(v) => {
                            return Err(err(format!(
                                "DetalleDesglose #{n}: con S2 (inversión del sujeto pasivo) \
                                 `{tag}` tiene que ser 0 y vale {v}"
                            )))
                        }
                        None => {
                            return Err(err(format!(
                                "DetalleDesglose #{n}: con S2 (inversión del sujeto pasivo) \
                                 `{tag}` es obligatorio y va a 0 — no se omite (§15.4)"
                            )))
                        }
                    }
                }
            }

            // §15.6.6 — la clave 08 (operación localizada en Canarias/Ceuta/Melilla) obliga a N2.
            if regimen == Some("08") && c != "N2" {
                return Err(err(format!(
                    "DetalleDesglose #{n}: ClaveRegimen 08 exige CalificacionOperacion N2 y \
                     lleva `{c}` (§15.6.6)"
                )));
            }
            // §15.6.10 — ídem para la clave 20 de IGIC (operaciones sujetas al IPSI).
            if es_igic && regimen == Some("20") && c != "N2" {
                return Err(err(format!(
                    "DetalleDesglose #{n}: con IGIC, ClaveRegimen 20 exige \
                     CalificacionOperacion N2 y lleva `{c}` (§15.6.10)"
                )));
            }

            // §15.1 / §15.3 — las listas cerradas de tipos. Acotadas a IVA: los tipos de IGIC
            // (7 %, 9,5 %, 15 %…) y de IPSI no están —ni tienen por qué— en la lista del IVA.
            if es_iva && c == "S1" {
                if let Some(t) = get("TipoImpositivo").and_then(num) {
                    if !en_lista(t, TIPOS_IVA) {
                        return Err(err(format!(
                            "DetalleDesglose #{n}: TipoImpositivo {t} no es un tipo de IVA; la \
                             AEAT solo admite 0; 2; 4; 5; 7,5; 10 y 21 (§15.1)"
                        )));
                    }
                }
                if let Some(t) = get("TipoRecargoEquivalencia").and_then(num) {
                    if !en_lista(t, TIPOS_RECARGO) {
                        return Err(err(format!(
                            "DetalleDesglose #{n}: TipoRecargoEquivalencia {t} no es un tipo de \
                             recargo; la AEAT admite 0; 0,26; 0,5; 0,62; 1; 1,4; 1,75 y 5,2 (§15.3)"
                        )));
                    }
                }
            }
        }
    }
    Ok(())
}

// ── §15.8: el techo de 3.000 € de la factura simplificada ──────────────────────────────────

/// Reads an AEAT amount (`3000.00`) as whole cents. Amounts are added up in integers on purpose:
/// the rule turns on a single cent (3.010,00 passes, 3.010,01 does not) and `f64` addition of
/// twelve lines does not survive that.
fn cents(v: &str) -> Option<i64> {
    num(v).map(|n| (n * 100.0).round() as i64)
}

/// §15.8 — «Cuando TipoFactura sea "F2", se validará que Ʃ (BaseImponibleOimporteNoSujeto +
/// CuotaRepercutida) de todas las líneas de detalle no sea superior a 3.000,00 euros. Se admitirá
/// un error de +10,00 euros.»
///
/// # Por qué se para aquí y el límite de los 400 € no
///
/// [ADR-0184] dejó escrito que el límite legal de la simplificada (400 €, 3.000 € en hostelería y
/// peluquería) **no** se comprueba: es un incumplimiento del comerciante, y bloquear la venta era
/// peor que dejarlo pasar. Este techo es otra cosa: no es una norma que el comerciante decide si
/// cumple, es un **rechazo seguro del servicio**. Y un rechazo llega con el número de la cadena ya
/// gastado, que es justo lo que este validador existe para evitar.
///
/// La regla **no aplica** con acuerdo de facturación (`NumRegistroAcuerdoFacturacion`) ni con
/// `FacturaSinIdentifDestinatarioArt61d = "S"`. El módulo no emite hoy ninguno de los dos, pero la
/// excepción va escrita: el día que se emitan, sin ella la regla bloquearía ventas legítimas.
fn validate_limite_f2(
    elements: &[Element<'_>],
    tipo: &str,
    nivel: usize,
) -> Result<(), VerifactuError> {
    if tipo != "F2" {
        return Ok(());
    }
    // Las excepciones se leen a nivel del registro: `text_at`, no `text_of`, para que un elemento
    // homónimo anidado no exima por accidente.
    if text_at(elements, EXEMPTION_BILLING_AGREEMENT, nivel).is_some_and(|v| !v.is_empty()) {
        return Ok(());
    }
    if text_at(elements, EXEMPTION_ART_61D, nivel) == Some(ART_61D_EXEMPT) {
        return Ok(());
    }

    // Σ de TODAS las líneas: por línea suelta, un ticket de dos líneas se colaría.
    let total: i64 = detalles(elements)
        .iter()
        .map(|g| {
            let get = |tag: &str| {
                g.iter()
                    .find(|(t, _)| *t == tag)
                    .and_then(|(_, v)| cents(v))
            };
            get("BaseImponibleOimporteNoSujeto").unwrap_or(0) + get("CuotaRepercutida").unwrap_or(0)
        })
        .sum();

    let techo = F2_CEILING_CENTS;
    if total > techo {
        return Err(err(format!(
            "una factura simplificada F2 no puede pasar de 3.000,00 € (más los 10,00 € de \
             tolerancia) sumando base y cuota de todas las líneas, y suma {:.2} €: la AEAT la \
             rechaza (§15.8). Con este importe hay que emitir factura completa identificando al \
             destinatario",
            total as f64 / 100.0
        )));
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

/// Valores de las `<enumeration>` del `simpleType` `type_name`, en orden de documento.
///
/// Mismo propósito que `sequence_of`: que las listas cerradas del validador se contrasten contra
/// el esquema oficial en cada `cargo test`, en vez de envejecer a mano. La copia vendorizada que
/// había antes ya se había quedado sin `E7`/`E8` (exenciones de IGIC) ni la clave de régimen `21`,
/// y nadie se enteró.
pub fn enumeration_of(xsd_src: &str, type_name: &str) -> Option<Vec<String>> {
    let start = xsd_src.find(&format!("simpleType name=\"{type_name}\""))?;
    let rest = &xsd_src[start..];
    let end = rest.find("</simpleType>")?;
    let cuerpo = &rest[..end];

    let mut out = Vec::new();
    let mut i = 0;
    while let Some(rel) = cuerpo[i..].find("<enumeration ") {
        let lt = i + rel;
        let after = &cuerpo[lt..];
        let gt = after.find('>')?;
        if let Some(v) = attr(&after[..gt], "value") {
            out.push(v);
        }
        i = lt + gt;
    }
    Some(out)
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

    // ── hub#1576: every refusal of `validate_registro` travels as a CODE ────────────────────
    //
    // The verdict of the diagnostic was translated by hub#1575, but its last half was not: the
    // reason `sample_record_schema_invalid` carries is `{detail}`, and the detail is whatever
    // sentence THIS validator wrote — in Spanish. A business running in English read «…the AEAT
    // schema refused the test record: Descripcion es obligatorio y viene vacío», with the only
    // actionable half in a language it did not choose.
    //
    // So each refusal now carries a stable code plus the element it is about, as DATA. The
    // Spanish stays as the prose (`Display`), which is what a hub on an older module still paints.

    /// Every case this table drives, mutated out of the one envelope that passes. Written as a
    /// table on purpose: fifteen separate tests would let a new refusal land with no code and
    /// nobody notice — here the count itself is an assertion.
    fn refusals() -> Vec<(&'static str, String, &'static str, Json)> {
        let base = envelope_with("");
        let swap = |from: &str, to: &str| base.replace(from, to);
        vec![
            (
                "an empty document",
                String::new(),
                "schema_envelope_empty",
                json!({}),
            ),
            (
                "a document that is not a RegFactu envelope",
                "<sum:Otra><sum1:Cosa>1</sum1:Cosa></sum:Otra>".to_owned(),
                "schema_envelope_not_regfactu",
                json!({}),
            ),
            (
                "a header with no ObligadoEmision",
                swap("<sum1:ObligadoEmision>", "<sum1:ObligadoOtro>")
                    .replace("</sum1:ObligadoEmision>", "</sum1:ObligadoOtro>"),
                "schema_header_issuer_missing",
                json!({}),
            ),
            (
                "an issuer with no tax name",
                swap(
                    "<sum1:NombreRazon>CLIENTE SL</sum1:NombreRazon>",
                    "<sum1:NombreRazon></sum1:NombreRazon>",
                ),
                "schema_issuer_identity_incomplete",
                json!({ "element": "NombreRazon" }),
            ),
            (
                "a representative missing its tax ID",
                envelope_with(
                    "<sum1:Representante><sum1:NombreRazon>GESTORIA SL</sum1:NombreRazon>\
                     </sum1:Representante>",
                ),
                "schema_representative_incomplete",
                json!({ "element": "NIF" }),
            ),
            (
                "a representative filed ahead of the issuer",
                base.replace(
                    "<sum:Cabecera><sum1:ObligadoEmision>",
                    "<sum:Cabecera><sum1:Representante><sum1:NombreRazon>GESTORIA SL\
                     </sum1:NombreRazon><sum1:NIF>B99999999</sum1:NIF></sum1:Representante>\
                     <sum1:ObligadoEmision>",
                ),
                "schema_element_out_of_order",
                json!({
                    "element": "Representante",
                    "sequence": "ObligadoEmision → Representante → RemisionVoluntaria",
                }),
            ),
            (
                "an envelope carrying neither an alta nor an anulacion",
                swap("<sum1:RegistroAlta>", "<sum1:RegistroOtro>")
                    .replace("</sum1:RegistroAlta>", "</sum1:RegistroOtro>"),
                "schema_record_missing",
                json!({}),
            ),
            (
                "a record with no IDFactura at all",
                swap("<sum1:IDFactura>", "<sum1:IDFacturaOtra>")
                    .replace("</sum1:IDFactura>", "</sum1:IDFacturaOtra>"),
                "schema_element_missing",
                json!({ "element": "IDFactura" }),
            ),
            (
                "an invoice number that came in empty",
                swap(
                    "<sum1:NumSerieFactura>A-1</sum1:NumSerieFactura>",
                    "<sum1:NumSerieFactura></sum1:NumSerieFactura>",
                ),
                "schema_element_missing_or_empty",
                json!({ "element": "NumSerieFactura" }),
            ),
            (
                "a required element that came in empty",
                swap(
                    "<sum1:DescripcionOperacion>Servicio</sum1:DescripcionOperacion>",
                    "<sum1:DescripcionOperacion></sum1:DescripcionOperacion>",
                ),
                "schema_element_empty",
                json!({ "element": "DescripcionOperacion" }),
            ),
            (
                "a required element that is not in the record",
                swap("<sum1:CuotaTotal>21.00</sum1:CuotaTotal>", ""),
                "schema_element_missing",
                json!({ "element": "CuotaTotal" }),
            ),
            (
                "an invoice type outside the enumeration",
                swap(
                    "<sum1:TipoFactura>F1</sum1:TipoFactura>",
                    "<sum1:TipoFactura>XX</sum1:TipoFactura>",
                ),
                "schema_value_not_in_enum",
                json!({
                    "element": "TipoFactura",
                    "value": "XX",
                    "allowed": TIPO_FACTURA.join("|"),
                }),
            ),
            (
                "an F1 with no recipient block",
                swap(
                    "<sum1:Destinatarios><sum1:IDDestinatario>\
             <sum1:NombreRazon>OTRO SL</sum1:NombreRazon><sum1:NIF>B87654321</sum1:NIF>\
             </sum1:IDDestinatario></sum1:Destinatarios>",
                    "",
                ),
                "schema_recipient_block_required",
                json!({ "invoice_type": "F1" }),
            ),
            (
                "a software id longer than the AEAT allows",
                swap(
                    "<sum1:IdSistemaInformatico>EC</sum1:IdSistemaInformatico>",
                    "<sum1:IdSistemaInformatico>ERPLORA</sum1:IdSistemaInformatico>",
                ),
                "schema_value_too_long",
                json!({
                    "element": "IdSistemaInformatico",
                    "value": "ERPLORA",
                    "max": MAX_ID_SISTEMA_INFORMATICO,
                }),
            ),
            (
                "a hash algorithm the schema does not admit",
                swap(
                    "<sum1:TipoHuella>01</sum1:TipoHuella>",
                    "<sum1:TipoHuella>02</sum1:TipoHuella>",
                ),
                "schema_hash_type_unsupported",
                json!({ "value": "02" }),
            ),
            (
                "a hash that is not a SHA-256 in hexadecimal",
                swap(&"A".repeat(64), "ZZZ"),
                "schema_hash_malformed",
                json!({}),
            ),
        ]
    }

    /// 🔴 **RED de hub#1576.** Each refusal names a stable code and carries the element it is
    /// about as DATA, so the module can say the sentence in the reader's language instead of
    /// interpolating this file's Spanish into an English screen.
    #[test]
    fn every_schema_refusal_travels_as_a_code_hub1576() {
        for (what, xml, code, facts) in refusals() {
            let e = validate_registro(&xml)
                .expect_err(&format!("{what} has to be refused, or the case measures nothing"));
            let (got_code, got_facts) = e
                .as_reason()
                .unwrap_or_else(|| panic!("{what}: the refusal carries no code — `{e}`"));
            assert_eq!(got_code, code, "{what}: `{e}`");
            assert_eq!(got_facts, facts, "{what}: `{e}`");
        }
    }

    /// 🔒 The prose does NOT go away. It is the fallback a hub whose module predates this change
    /// still paints, exactly the contract `cert_message` has had since hub#1575 — and it keeps
    /// naming the element, because half an empty sentence is worse than a Spanish one.
    #[test]
    fn a_coded_refusal_still_says_it_in_prose_hub1576() {
        for (what, xml, _, facts) in refusals() {
            let e = validate_registro(&xml).expect_err(what);
            let prose = e.to_string();
            assert!(
                !prose.is_empty(),
                "{what}: a refusal with no prose leaves an older module with nothing to paint"
            );
            if let Some(element) = facts.get("element").and_then(Json::as_str) {
                assert!(
                    prose.contains(element),
                    "{what}: the prose has to keep naming what to fix — `{prose}`"
                );
            }
        }
    }

    /// 🔒 And the codes are DISTINCT per family: a table that mapped everything to one code would
    /// pass the test above and leave the reader with one sentence for fifteen different faults.
    #[test]
    fn the_schema_codes_are_not_all_the_same_one_hub1576() {
        let mut codes: Vec<&str> = refusals()
            .iter()
            .map(|(_, xml, _, _)| {
                validate_registro(xml)
                    .expect_err("every case in the table is a refusal")
                    .as_reason()
                    .expect("every refusal carries a code")
                    .0
            })
            .collect();
        codes.sort_unstable();
        codes.dedup();
        assert_eq!(
            codes.len(),
            15,
            "fifteen families of refusal, fifteen sentences to write: {codes:?}"
        );
    }

    /// Un sobre completo y válido, con el `Representante` que hub#1460 estampa, para medir sobre
    /// él lo que el validador dice del bloque nuevo.
    fn envelope_with(representante: &str) -> String {
        format!(
            "<sum:RegFactuSistemaFacturacion><sum:Cabecera>\
             <sum1:ObligadoEmision><sum1:NombreRazon>CLIENTE SL</sum1:NombreRazon>\
             <sum1:NIF>B12345678</sum1:NIF></sum1:ObligadoEmision>{representante}\
             </sum:Cabecera><sum:RegistroFactura><sum1:RegistroAlta>\
             <sum1:IDVersion>1.0</sum1:IDVersion>\
             <sum1:IDFactura><sum1:IDEmisorFactura>B12345678</sum1:IDEmisorFactura>\
             <sum1:NumSerieFactura>A-1</sum1:NumSerieFactura>\
             <sum1:FechaExpedicionFactura>02-09-2026</sum1:FechaExpedicionFactura>\
             </sum1:IDFactura>\
             <sum1:NombreRazonEmisor>CLIENTE SL</sum1:NombreRazonEmisor>\
             <sum1:TipoFactura>F1</sum1:TipoFactura>\
             <sum1:DescripcionOperacion>Servicio</sum1:DescripcionOperacion>\
             <sum1:Destinatarios><sum1:IDDestinatario>\
             <sum1:NombreRazon>OTRO SL</sum1:NombreRazon><sum1:NIF>B87654321</sum1:NIF>\
             </sum1:IDDestinatario></sum1:Destinatarios>\
             <sum1:Desglose><sum1:DetalleDesglose>\
             <sum1:Impuesto>01</sum1:Impuesto><sum1:ClaveRegimen>01</sum1:ClaveRegimen>\
             <sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>\
             <sum1:TipoImpositivo>21.00</sum1:TipoImpositivo>\
             <sum1:BaseImponibleOimporteNoSujeto>100.00</sum1:BaseImponibleOimporteNoSujeto>\
             <sum1:CuotaRepercutida>21.00</sum1:CuotaRepercutida>\
             </sum1:DetalleDesglose></sum1:Desglose>\
             <sum1:CuotaTotal>21.00</sum1:CuotaTotal>\
             <sum1:ImporteTotal>121.00</sum1:ImporteTotal>\
             <sum1:Encadenamiento><sum1:PrimerRegistro>S</sum1:PrimerRegistro></sum1:Encadenamiento>\
             <sum1:SistemaInformatico><sum1:NombreRazon>ERPLORA CLOUD SL</sum1:NombreRazon>\
             <sum1:NIF>B27593136</sum1:NIF>\
             <sum1:NombreSistemaInformatico>ERPlora Hub</sum1:NombreSistemaInformatico>\
             <sum1:IdSistemaInformatico>EC</sum1:IdSistemaInformatico>\
             <sum1:Version>1.0</sum1:Version>\
             <sum1:NumeroInstalacion>hub-1</sum1:NumeroInstalacion>\
             <sum1:TipoUsoPosibleSoloVerifactu>S</sum1:TipoUsoPosibleSoloVerifactu>\
             <sum1:TipoUsoPosibleMultiOT>S</sum1:TipoUsoPosibleMultiOT>\
             <sum1:IndicadorMultiplesOT>N</sum1:IndicadorMultiplesOT>\
             </sum1:SistemaInformatico>\
             <sum1:FechaHoraHusoGenRegistro>2026-09-02T10:00:00+02:00</sum1:FechaHoraHusoGenRegistro>\
             <sum1:TipoHuella>01</sum1:TipoHuella>\
             <sum1:Huella>AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA</sum1:Huella>\
             </sum1:RegistroAlta></sum:RegistroFactura></sum:RegFactuSistemaFacturacion>"
        )
    }

    /// Sin `Representante` el sobre sigue siendo el de siempre: el bloque es `minOccurs=0`.
    #[test]
    fn un_sobre_sin_representante_sigue_siendo_valido() {
        validate_registro(&envelope_with("")).expect("Representante es opcional");
    }

    /// Con `Representante` bien formado, tampoco molesta — y en particular el chequeo de
    /// `ObligadoEmision/NombreRazon`+`NIF` sigue mirando al OBLIGADO, que va primero en el
    /// documento, no al representante que ahora comparte esos mismos nombres de etiqueta.
    #[test]
    fn un_representante_bien_formado_valida() {
        let xml = envelope_with(
            "<sum1:Representante><sum1:NombreRazon>ERPLORA CLOUD SL</sum1:NombreRazon>\
             <sum1:NIF>B27593136</sum1:NIF></sum1:Representante>",
        );
        validate_registro(&xml).expect("un representante completo es válido");
    }

    /// 🔒 hub#1460: el bloque nuevo también se valida ANTES de la red. `PersonaFisicaJuridicaESType`
    /// exige `NombreRazon` **y** `NIF`, en ese orden; medio representante es un 4102 con el número
    /// de cadena ya gastado, y ese es justo el fallo que este validador existe para evitar.
    #[test]
    fn un_representante_a_medias_no_llega_a_la_red() {
        for (bloque, esperado) in [
            (
                "<sum1:Representante><sum1:NIF>B27593136</sum1:NIF></sum1:Representante>",
                "NombreRazon",
            ),
            (
                "<sum1:Representante><sum1:NombreRazon>ERPLORA CLOUD SL</sum1:NombreRazon>\
                 </sum1:Representante>",
                "NIF",
            ),
            (
                "<sum1:Representante><sum1:NombreRazon></sum1:NombreRazon>\
                 <sum1:NIF>B27593136</sum1:NIF></sum1:Representante>",
                "NombreRazon",
            ),
        ] {
            let error = validate_registro(&envelope_with(bloque))
                .expect_err("medio representante no puede transmitirse");
            let message = error.to_string();
            assert!(
                message.contains("Representante") && message.contains(esperado),
                "el motivo tiene que nombrar el elemento que falta: {message}"
            );
        }
    }

    /// El orden del `xs:sequence` de `CabeceraType` también se mide: ObligadoEmision →
    /// Representante → RemisionVoluntaria. Un `Representante` detrás de la incidencia es un 4102.
    #[test]
    fn un_representante_fuera_de_secuencia_no_llega_a_la_red() {
        let xml = envelope_with(
            "<sum1:RemisionVoluntaria><sum1:Incidencia>S</sum1:Incidencia></sum1:RemisionVoluntaria>\
             <sum1:Representante><sum1:NombreRazon>ERPLORA CLOUD SL</sum1:NombreRazon>\
             <sum1:NIF>B27593136</sum1:NIF></sum1:Representante>",
        );
        let message = validate_registro(&xml)
            .expect_err("fuera de secuencia es un rechazo del esquema")
            .to_string();
        assert!(message.contains("Representante"), "{message}");
    }

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
        assert_eq!(els, vec![("X", "1", 0), ("Y", "", 0), ("Z", "2", 0)]);
    }

    /// La profundidad es lo que distingue el `Huella` del registro del `Huella` de su
    /// `RegistroAnterior`. Una autocerrada no abre nivel; un cierre lo baja.
    #[test]
    fn walk_anota_la_profundidad_de_cada_elemento() {
        let els = walk(
            "<R><IDFactura><Huella>propia</Huella></IDFactura><Vacio/><Huella>otra</Huella></R>",
        );
        assert_eq!(
            els,
            vec![
                ("R", "", 0),
                ("IDFactura", "", 1),
                ("Huella", "propia", 2),
                ("Vacio", "", 1),
                ("Huella", "otra", 1),
            ]
        );
        assert_eq!(text_at(&els, "Huella", 1), Some("otra"));
        assert_eq!(text_at(&els, "Huella", 2), Some("propia"));
    }
}
