//! **La moneda del hub, y cuántos decimales tiene.**
//!
//! El dinero de ERPlora es un entero de **UNIDADES MÍNIMAS**, no de «céntimos». La distinción parece
//! pedante hasta que el hub sale del euro — y sale: **la app es gratuita y la usa quien quiera**.
//!
//! ISO-4217 fija cuántos decimales tiene cada moneda, y **no son siempre dos**:
//!
//! | Moneda | Decimales | `1999` significa |
//! |---|---|---|
//! | EUR, USD, GBP | 2 | 19,99 € |
//! | **JPY**, KRW | **0** | **1999 ¥** (¡no 19,99!) |
//! | **KWD**, BHD, TND | **3** | 1,999 KWD |
//!
//! Por eso el `/ 100` que estaba clavado en la capa de dinero era un bug esperando a que alguien
//! pusiera su hub en yenes: **habría mostrado y cobrado 100 veces mal**.
//!
//! # Lo que NO cambia: la aritmética
//!
//! [`crate::money`] opera **siempre en unidades mínimas**, así que `percent_of`, `mul_qty` o
//! `split_tax_included` funcionan **igual** con exponente 0, 2 o 3 — no saben ni les importa cuál es
//! la moneda. El exponente solo hace falta en **dos fronteras**: cuando un humano **teclea** un
//! importe y cuando se **pinta**. Ahí, y en ningún sitio más.
//!
//! # Monedas fuera del registro
//!
//! [`decimals_for`] devuelve `None` para una moneda que no conoce — **a propósito**. Adivinar «2» en
//! silencio es exactamente cómo se acaba cobrando 100× de más en yenes. Un hub cuya moneda no esté
//! aquí **puede usarla igual**: declara sus decimales a mano (`hub_settings.currency_decimals`). El
//! registro dice lo que sabe; no es una lista blanca.

/// Los decimales que se asumen cuando nadie dice otra cosa. **Úsalo consciente**, no por descarte.
pub const DEFAULT_DECIMALS: u32 = 2;

/// Monedas con **0 decimales**: la unidad mínima es la propia moneda (no hay «céntimo de yen»).
const ZERO_DECIMALS: &[&str] = &[
    "BIF", "CLP", "DJF", "GNF", "ISK", "JPY", "KMF", "KRW", "PYG", "RWF", "UGX", "UYI", "VND",
    "VUV", "XAF", "XOF", "XPF",
];

/// Monedas con **3 decimales** (milésimas: fils, millimes).
const THREE_DECIMALS: &[&str] = &["BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"];

/// Monedas con **4 decimales** (las raras de ISO-4217).
const FOUR_DECIMALS: &[&str] = &["CLF", "UYW"];

/// Las de **2 decimales**. No están todas listadas: son la inmensa mayoría, así que se resuelven
/// por descarte *solo si la moneda es una que conocemos*. Esta lista es la de las comunes, para que
/// una moneda real no caiga en `None` y obligue a configurarla a mano sin motivo.
const TWO_DECIMALS: &[&str] = &[
    "AED", "ARS", "AUD", "BGN", "BRL", "CAD", "CHF", "CNY", "COP", "CZK", "DKK", "EGP", "EUR",
    "GBP", "HKD", "HRK", "HUF", "IDR", "ILS", "INR", "MAD", "MXN", "MYR", "NGN", "NOK", "NZD",
    "PEN", "PHP", "PLN", "RON", "RSD", "RUB", "SAR", "SEK", "SGD", "THB", "TRY", "TWD", "UAH",
    "USD", "UYU", "VES", "ZAR",
];

/// ¿Es un código ISO-4217 bien formado? **Tres letras**, y ya.
///
/// Ojo: esto NO es una lista blanca de monedas conocidas. Un hub puede usar una moneda que el
/// registro no conozca (declarando sus decimales a mano); lo que no puede es usar `"EURO"` o `"€"`.
pub fn is_valid_code(code: &str) -> bool {
    let c = code.trim();
    c.len() == 3 && c.chars().all(|ch| ch.is_ascii_alphabetic())
}

/// Normaliza un código a MAYÚSCULAS. `None` si no es un ISO-4217 bien formado.
pub fn normalize_code(code: &str) -> Option<String> {
    let c = code.trim();
    is_valid_code(c).then(|| c.to_ascii_uppercase())
}

/// Los decimales de una moneda **conocida**. `None` si no la conocemos.
///
/// Devolver `None` es deliberado: quien no esté en el registro tendrá que **declararlo a mano**.
/// Suponer 2 en silencio es cómo se cobra 100× de más en una moneda de 0 decimales.
pub fn decimals_for(code: &str) -> Option<u32> {
    let c = normalize_code(code)?;
    let c = c.as_str();
    if ZERO_DECIMALS.contains(&c) {
        Some(0)
    } else if THREE_DECIMALS.contains(&c) {
        Some(3)
    } else if FOUR_DECIMALS.contains(&c) {
        Some(4)
    } else if TWO_DECIMALS.contains(&c) {
        Some(2)
    } else {
        None
    }
}
