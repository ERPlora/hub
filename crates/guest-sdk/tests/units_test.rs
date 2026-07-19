//! Contrato de la CANTIDAD — espejo exacto del de la moneda (`currency_test.rs`, ADR-0123 §7).
//!
//! Una cantidad de ERPlora es un entero de **UNIDADES MÍNIMAS**. Cuántos decimales tiene esa
//! unidad **lo dice la unidad, no el número**: `500` no significa nada hasta saber si son cañas
//! (500 cañas) o kilos (0,5 kg).
//!
//! * **ud** → 0 decimales. Dos cañas se guardan `2`, **no** `2000`.
//! * **kg, l** → 3 decimales (gramos, mililitros). `2500` = 2,5 kg.
//! * **g, ml** → 0 decimales: la unidad mínima ES el gramo.
//!
//! Es el mismo bug que el `/100` clavado en la capa de dinero, un piso más abajo: una escala fija
//! ×1000 inflaría las cañas por poder pesar gambas, y truncar a entero convierte 2,5 kg vendidos
//! en 2 — que es exactamente lo que hacía `kitchen` hasta esta tanda.
//!
//! LO QUE **NO** CAMBIA: la aritmética. Multiplicar por el precio, aplicar un descuento o restar
//! lo ya despachado opera en unidades mínimas y funciona **igual** con exponente 0 o 3. El
//! exponente solo hace falta en **dos fronteras**: cuando un humano teclea una cantidad, y cuando
//! se pinta.

use erplora_guest_sdk::units::{decimals_for, is_valid_code, normalize_code};

// ── Cuántos decimales tiene cada unidad ─────────────────────────────────────────────────
#[test]
fn la_unidad_suelta_no_tiene_decimales() {
    // El caso mayoritario de un bar: cañas, platos, cafés. Dos cañas son `2`.
    assert_eq!(decimals_for("ud"), Some(0));
}

#[test]
fn el_kilo_y_el_litro_tienen_3() {
    // Precisión de gramo y de mililitro, que es lo que da una báscula de mostrador.
    assert_eq!(decimals_for("kg"), Some(3));
    assert_eq!(decimals_for("l"), Some(3));
}

#[test]
fn el_gramo_es_su_propia_unidad_minima() {
    // Quien prefiera teclear "500 g" en vez de "0,5 kg" no necesita decimales para nada.
    assert_eq!(decimals_for("g"), Some(0));
    assert_eq!(decimals_for("ml"), Some(0));
}

#[test]
fn una_unidad_desconocida_NO_se_adivina() {
    // Igual que con la moneda: adivinar por descarte es cómo se acaba descontando mil veces mal
    // de stock. El registro dice lo que sabe; el que use una unidad rara la declara a mano.
    assert_eq!(decimals_for("quintal"), None);
    assert_eq!(decimals_for(""), None);
    assert_eq!(decimals_for("KG "), None, "sin normalizar, no se resuelve");
}

// ── Códigos ─────────────────────────────────────────────────────────────────────────────
#[test]
fn el_codigo_se_normaliza_a_minusculas_y_sin_espacios() {
    assert_eq!(normalize_code(" Kg "), Some("kg".to_string()));
    assert_eq!(normalize_code("UD"), Some("ud".to_string()));
    assert_eq!(normalize_code("  "), None);
}

#[test]
fn is_valid_code_no_es_una_lista_blanca() {
    // Un hub puede usar una unidad que el registro no conozca (declarando sus decimales a mano);
    // lo que no puede es usar basura.
    assert!(is_valid_code("ud"));
    assert!(is_valid_code("quintal"), "desconocida pero bien formada");
    assert!(!is_valid_code(""));
    assert!(!is_valid_code("kg/m2"), "sin barras ni símbolos");
}

// ── Las dos fronteras (lo único que necesita el exponente) ──────────────────────────────
#[test]
fn frontera_de_entrada_lo_que_teclea_un_humano() {
    use erplora_guest_sdk::units::major_to_minor;
    use rust_decimal_macros::dec;

    // El camarero pesa y teclea 2,5 kg → 2500 unidades mínimas.
    assert_eq!(major_to_minor(dec!(2.5), 3), 2500);
    assert_eq!(major_to_minor(dec!(0.5), 3), 500);
    // Y teclea 2 cañas → 2. NO 2000: ése era el fallo de la escala fija.
    assert_eq!(major_to_minor(dec!(2), 0), 2);
}

#[test]
fn frontera_de_salida_lo_que_ve_el_cocinero() {
    use erplora_guest_sdk::units::minor_to_major;
    use rust_decimal_macros::dec;

    assert_eq!(minor_to_major(2500, 3), dec!(2.5));
    assert_eq!(minor_to_major(500, 3), dec!(0.5));
    assert_eq!(minor_to_major(2, 0), dec!(2));
}

#[test]
fn ida_y_vuelta_sin_perdida() {
    use erplora_guest_sdk::units::{major_to_minor, minor_to_major};
    use rust_decimal_macros::dec;

    for (cantidad, decimales) in [(dec!(2.5), 3u32), (dec!(0.125), 3), (dec!(2), 0), (dec!(0.75), 3)] {
        let minima = major_to_minor(cantidad, decimales);
        assert_eq!(minor_to_major(minima, decimales), cantidad, "{cantidad} con {decimales} dec.");
    }
}

#[test]
fn media_racion_de_gambas_no_se_convierte_en_cero() {
    use erplora_guest_sdk::units::major_to_minor;
    use rust_decimal_macros::dec;

    // El bug concreto que abrió todo esto: `as_i64(0.5)` = 0, y el stock nunca se descontaba.
    assert_eq!(major_to_minor(dec!(0.5), 3), 500);
    assert_ne!(major_to_minor(dec!(0.5), 3), 0);
}
