//! **La unidad de un producto, y cuántos decimales tiene.**
//!
//! Una cantidad de ERPlora es un entero de **UNIDADES MÍNIMAS**, no «gramos» ni «piezas». La
//! distinción parece pedante hasta que el mismo TPV vende cañas y gambas al peso — y las vende:
//! un bar es exactamente eso.
//!
//! Cuántos decimales tiene una cantidad lo dice **la unidad**, no el número:
//!
//! | Unidad | Decimales | `2500` significa |
//! |---|---|---|
//! | **ud** | **0** | **2500 unidades** (¡no 2,5!) |
//! | kg, l | 3 | 2,5 kg · 2,5 l |
//! | g, ml | 0 | 2500 g · 2500 ml |
//! | min | 0 | 2500 minutos |
//! | h | 2 | 25 horas |
//!
//! Es el mismo diseño que [`crate::currency`], un piso más abajo, y por el mismo motivo. Dos
//! alternativas se descartaron:
//!
//! * **Truncar a entero** (`as_i64`): convertía 2,5 kg vendidos en 2, y 0,5 kg en **0** — con lo
//!   que el stock no se descontaba **en silencio**. Es el bug que abrió todo esto.
//! * **Escala fija ×1000**: obliga a guardar dos cañas como `2000` para poder pesar gambas.
//!   Infla toda la aritmética del caso mayoritario por un caso minoritario.
//!
//! # Lo que NO cambia: la aritmética
//!
//! Multiplicar por el precio, aplicar un descuento o restar lo ya despachado opera **siempre en
//! unidades mínimas** y funciona **igual** con exponente 0 o 3 — no sabe ni le importa cuál es la
//! unidad. El exponente solo hace falta en **dos fronteras**: cuando un humano **teclea** una
//! cantidad y cuando se **pinta**. Ahí, y en ningún sitio más.
//!
//! # La unidad viaja con la LÍNEA, no con el hub
//!
//! Diferencia con la moneda: hay **una** moneda por hub, pero **una unidad por producto**. Así que
//! la línea guarda su unidad, **congelada**: si mañana las gambas pasan de `kg` a `ud`, la comanda
//! de ayer tiene que seguir diciendo 0,5 kg. Mismo criterio que el destino histórico de una
//! comanda ya disparada (ADR-0145).
//!
//! # Unidades fuera del registro
//!
//! [`decimals_for`] devuelve `None` para una unidad que no conoce — **a propósito**. Adivinar «3»
//! en silencio es exactamente cómo se acaba descontando mil veces mal de stock. Un hub que venda
//! por quintales **puede hacerlo igual**: declara sus decimales a mano. El registro dice lo que
//! sabe; no es una lista blanca.

use rust_decimal::Decimal;

/// Unidades con **0 decimales**: la unidad mínima es ella misma (no hay «medio gramo» que valga la
/// pena modelar en un TPV, ni media caña).
const ZERO_DECIMALS: &[&str] = &["ud", "g", "ml", "min", "pax"];

/// Unidades con **3 decimales** (milésimas: gramos dentro del kilo, mililitros dentro del litro).
const THREE_DECIMALS: &[&str] = &["kg", "l"];

/// Unidades con **2 decimales**. La hora se factura en cuartos (0,25 h); no da para milésimas.
const TWO_DECIMALS: &[&str] = &["h"];

/// ¿Es un código de unidad bien formado? Letras ASCII, 1–8, y ya.
///
/// Ojo: esto NO es una lista blanca de unidades conocidas. Un hub puede usar una unidad que el
/// registro no conozca (declarando sus decimales a mano); lo que no puede es usar `"kg/m2"` o `""`.
pub fn is_valid_code(code: &str) -> bool {
    let c = code.trim();
    !c.is_empty() && c.len() <= 8 && c.chars().all(|ch| ch.is_ascii_alphabetic())
}

/// Normaliza el código a su forma canónica (minúsculas, sin espacios). `None` si no es válido.
pub fn normalize_code(code: &str) -> Option<String> {
    let c = code.trim();
    if is_valid_code(c) { Some(c.to_ascii_lowercase()) } else { None }
}

/// Los decimales de una unidad, o `None` si el registro no la conoce.
///
/// **No adivina.** Un `None` significa «pregúntale al hub cuántos decimales tiene esto», no
/// «asume el valor de siempre»: asumir es cómo el `/100` del dinero se convirtió en un bug
/// esperando a que alguien pusiera su hub en yenes.
///
/// Exige el código **ya normalizado**: `"KG "` devuelve `None`, igual que en la moneda. Quien lee
/// del payload pasa antes por [`normalize_code`].
pub fn decimals_for(code: &str) -> Option<u32> {
    if ZERO_DECIMALS.contains(&code) {
        Some(0)
    } else if THREE_DECIMALS.contains(&code) {
        Some(3)
    } else if TWO_DECIMALS.contains(&code) {
        Some(2)
    } else {
        None
    }
}

/// **Frontera de entrada:** lo que teclea (o pesa) un humano → unidades mínimas.
///
/// `decimals` son los de la unidad del PRODUCTO ([`decimals_for`]), no una constante: en `ud` son
/// 0, así que dos cañas son `2` y no `2000`.
pub fn major_to_minor(quantity: Decimal, decimals: u32) -> i64 {
    crate::money::round(quantity * pow10(decimals))
}

/// **Frontera de salida:** unidades mínimas → lo que se pinta en pantalla o en el papel.
pub fn minor_to_major(quantity: i64, decimals: u32) -> Decimal {
    Decimal::from(quantity) / pow10(decimals)
}

fn pow10(decimals: u32) -> Decimal {
    Decimal::from(10_i64.pow(decimals))
}
