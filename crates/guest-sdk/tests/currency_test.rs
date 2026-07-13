//! Contrato de la MONEDA (ADR-0123 §7).
//!
//! El dinero de ERPlora es un entero de **UNIDADES MÍNIMAS** — no «céntimos». La diferencia importa
//! en cuanto el hub sale del euro, y sale: **la app es gratuita y la usa quien quiera**.
//!
//! La unidad mínima **depende de la moneda** (ISO-4217 lo fija):
//!
//! * **EUR, USD** → 2 decimales. 1 unidad mínima = 1 céntimo. `1999` = 19,99 €.
//! * **JPY** → **0 decimales**. La unidad mínima ES el yen. `1999` = **1999 ¥**, no 19,99.
//! * **KWD, BHD, TND** → **3 decimales**. `1999` = 1,999 KWD.
//!
//! Por eso el `/100` que había clavado en la capa de dinero es un bug en cuanto alguien pone su hub
//! en yenes: **mostraría y cobraría 100 veces mal**. La escala sale de la MONEDA, no de una
//! constante.
//!
//! LO QUE **NO** CAMBIA: la aritmética. `percent_of`, `mul_qty`, `split_tax_included`… todas operan
//! en unidades mínimas y funcionan **igual** con exponente 0, 2 o 3. El exponente solo hace falta en
//! **dos fronteras**: cuando un humano teclea un importe, y cuando se pinta.

use erplora_guest_sdk::currency::{decimals_for, is_valid_code, normalize_code, DEFAULT_DECIMALS};
use erplora_guest_sdk::money::{major_to_minor, minor_to_major};
use rust_decimal_macros::dec;

// ── Cuántos decimales tiene cada moneda ─────────────────────────────────────────────────
#[test]
fn el_euro_y_el_dolar_tienen_2_decimales() {
    assert_eq!(decimals_for("EUR"), Some(2));
    assert_eq!(decimals_for("USD"), Some(2));
    assert_eq!(decimals_for("GBP"), Some(2));
}

#[test]
fn el_yen_NO_tiene_decimales() {
    // El caso que rompe el `/100`: en JPY la unidad mínima es el yen. 1999 son 1999 ¥.
    assert_eq!(decimals_for("JPY"), Some(0));
    assert_eq!(decimals_for("KRW"), Some(0));
}

#[test]
fn el_dinar_kuwaiti_tiene_3() {
    assert_eq!(decimals_for("KWD"), Some(3));
    assert_eq!(decimals_for("BHD"), Some(3));
    assert_eq!(decimals_for("TND"), Some(3));
}

#[test]
fn una_moneda_desconocida_no_se_inventa_los_decimales() {
    // Devuelve `None` a propósito: quien la use tendrá que declararlos a mano (`currency_decimals`
    // en los settings del hub). Adivinar «2» en silencio es cómo se cobra 100× de más en un yen.
    assert_eq!(decimals_for("XYZ"), None);
    assert_eq!(decimals_for("BTC"), None);
    // Y hay un default explícito, para quien decida usarlo CONSCIENTEMENTE.
    assert_eq!(DEFAULT_DECIMALS, 2);
}

// ── El código de moneda ─────────────────────────────────────────────────────────────────
#[test]
fn el_codigo_es_ISO_4217_tres_letras() {
    assert!(is_valid_code("EUR"));
    assert!(is_valid_code("JPY"));
    assert!(!is_valid_code("EU"), "dos letras no");
    assert!(!is_valid_code("EURO"), "cuatro tampoco");
    assert!(!is_valid_code("E1R"), "ni dígitos");
    assert!(!is_valid_code(""), "ni vacío");
}

#[test]
fn el_codigo_se_normaliza_a_mayusculas() {
    assert_eq!(normalize_code(" eur "), Some("EUR".to_string()));
    assert_eq!(normalize_code("jpy"), Some("JPY".to_string()));
    assert_eq!(normalize_code("nope"), None);
}

#[test]
fn una_moneda_que_no_esta_en_el_registro_SIGUE_SIENDO_VALIDA() {
    // «Si la moneda no existe en el hub, se debería poder añadir a mano.» El registro dice cuántos
    // decimales tiene una moneda CONOCIDA; no es una lista blanca que impida usar otra.
    assert!(is_valid_code("XPF"));
    assert_eq!(normalize_code("xaf"), Some("XAF".to_string()));
}

// ── Las DOS fronteras: teclear y pintar ─────────────────────────────────────────────────
#[test]
fn teclear_un_importe_depende_de_la_moneda() {
    // 19,99 € → 1999 unidades mínimas (céntimos).
    assert_eq!(major_to_minor(dec!(19.99), 2), 1999);
    // 1999 ¥ → 1999 unidades mínimas (yenes). NO 199900.
    assert_eq!(major_to_minor(dec!(1999), 0), 1999);
    // 1,999 KWD → 1999 unidades mínimas (fils).
    assert_eq!(major_to_minor(dec!(1.999), 3), 1999);
}

#[test]
fn pintar_un_importe_tambien() {
    assert_eq!(minor_to_major(1999, 2), dec!(19.99));
    assert_eq!(minor_to_major(1999, 0), dec!(1999), "en yenes NO se divide entre 100");
    assert_eq!(minor_to_major(1999, 3), dec!(1.999));
}

#[test]
fn el_mismo_entero_significa_cosas_distintas_segun_la_moneda() {
    // Es LA razón de todo esto: `1999` no significa nada sin su moneda.
    let minor = 1999;
    assert_eq!(minor_to_major(minor, 2), dec!(19.99)); //  19,99 €
    assert_eq!(minor_to_major(minor, 0), dec!(1999)); // 1999   ¥
    assert_eq!(minor_to_major(minor, 3), dec!(1.999)); //  1,999 KWD
}

#[test]
fn la_frontera_redondea_a_la_unidad_minima_de_SU_moneda() {
    // Teclear más decimales de los que la moneda admite → se redondea (HALF_UP), no se trunca.
    assert_eq!(major_to_minor(dec!(19.999), 2), 2000, "19,999 € → 20,00 €");
    assert_eq!(major_to_minor(dec!(1999.5), 0), 2000, "no hay medio yen");
    // Y el céntimo no se pierde: en f64, 0.29 * 100 = 28.999… → 28. En Decimal, 29.
    assert_eq!(major_to_minor(dec!(0.29), 2), 29);
}
