//! **La cantidad: valor decimal exacto en una unidad de medida** (ADR-0147).
//!
//! Una cantidad **es** 0,5 kg. El entero de este módulo es solo cómo se persiste — punto fijo con
//! **escala GLOBAL de 6 decimales**, para que SQLite y Postgres den exactamente el mismo número.
//!
//! Esto **no** es el contrato del dinero, y el vocabulario no se mezcla a propósito: aquí no hay
//! `major` ni `minor`. Confundir «unidad mínima de la moneda» con «unidad de medida del producto»
//! fue el error de la primera versión de este contrato.
//!
//! # De dónde sale
//!
//! `as_i64(0.5)` = 0. Medio kilo de gambas llegaba a cocina como «0 × Gambas» y, peor, en
//! `inventory` el guarda `qty <= 0 → continue` hacía que vender al peso **no descontara stock, en
//! silencio**. Un `f64` redondeado a 3 decimales (`as_qty`, #10) tapaba el truncado pero dejaba la
//! coma flotante dentro del contrato — y con ella `2.675 == 2.6749999999999998` y
//! `8 % 1.6 = 1.5999999999999996`, que es la clase de problema que un punto fijo entero **no
//! gestiona porque no tiene**.
//!
//! # Las cuatro piezas
//!
//! | | Qué es | Ejemplo |
//! |---|---|---|
//! | Escala | GLOBAL, 10⁶. Solo representación | `500_000` = 0,5 |
//! | [`ConversionFactor`] | fracción **exacta** hacia la unidad base | 1 t = `1000/1` kg · 1 min = `1/60` h |
//! | [`QuantityIncrement`] | el escalón permitido. **Validación, no redondeo** | pieza `1` · kg `0,001` · hora `0,25` |
//! | Precio | importe **entero** por una cantidad de precio | «0,37 € por 100 ud» |
//!
//! # Lo que NUNCA hace este módulo
//!
//! **Redondear una cantidad en silencio.** Si 20 minutos no caben en una unidad configurada en
//! cuartos de hora, se **rechaza**: convertirlo en 15 o en 30 modificaría calladamente lo vendido,
//! lo trabajado, el stock, el importe y las estadísticas. El único redondeo del módulo es el del
//! **importe**, que es HALF_UP, explícito y una sola vez por línea (ADR-0123).

use rust_decimal::Decimal;

/// Escala global de las cantidades: seis decimales. `cantidad_lógica = raw / QUANTITY_SCALE`.
///
/// Global **a propósito**: con escala por unidad, el factor de conversión tendría que viajar hasta
/// el punto donde se multiplica el dinero para no errar por mil. Con una sola escala, un evento
/// entre módulos lleva `500000` y el receptor no necesita saber nada más.
///
/// `i64` a esta escala da ~9,2 × 10¹² unidades: no es una restricción real.
pub const QUANTITY_SCALE: i64 = 1_000_000;

const SCALE_DIGITS: u32 = 6;

/// Cantidad en punto fijo. El `i64` interno es la representación, no el significado.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct QuantityValue(i64);

impl QuantityValue {
    pub const ZERO: QuantityValue = QuantityValue(0);

    /// Desde la representación cruda (lo que hay en la columna).
    pub const fn from_raw(raw: i64) -> Self {
        QuantityValue(raw)
    }
    /// La representación cruda, para persistir.
    pub const fn raw(self) -> i64 {
        self.0
    }
    pub const fn is_zero(self) -> bool {
        self.0 == 0
    }
}

/// Factor de conversión hacia la unidad base, como **fracción exacta**.
///
/// Nunca un decimal: `1 min = 1/60 h` no tiene representación decimal finita, y aproximarlo mete
/// error en cada conversión. SAP guarda sus conversiones así (`MARM-UMREZ`/`UMREN`, dos enteros)
/// por este mismo motivo.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ConversionFactor {
    pub numerator: i64,
    pub denominator: i64,
}

/// El escalón permitido de una unidad, en la escala global. Es una **restricción de validación**.
///
/// Odoo tenía esto por unidad (`rounding`) y en la 19 lo centralizó en una precisión global — pero
/// al fundir escala e incremento **perdió el escalón arbitrario** (`0,25`, «se vende de 6 en 6»).
/// Aquí van separados justamente por eso.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct QuantityIncrement {
    pub value: i64,
}

/// Por qué una cantidad no es válida. Ninguna variante se «arregla sola».
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum QuantityError {
    /// Más decimales de los que admite la escala global.
    NotRepresentable { text: String },
    /// No cae en la rejilla del incremento. Lleva ambos valores para que la UI pueda decir
    /// «20 minutos no vale en una unidad configurada en incrementos de 15 minutos».
    OffGrid { value: i64, increment: i64 },
    /// La conversión no divide exacta (1/3 periódico) — truncar sería un error silencioso.
    InexactConversion { value: i64, numerator: i64, denominator: i64 },
    /// La configuración de la unidad es inválida: se detecta AL CREARLA, no al vender.
    InvalidIncrement { increment: i64, reason: &'static str },
    /// No cabe. Se dice, no se da la vuelta.
    Overflow,
    /// Texto que no es un número.
    Malformed { text: String },
}

/// **Frontera de entrada:** lo que teclea (o pesa) un humano → cantidad.
///
/// Rechaza lo que no quepa en la escala global en vez de truncarlo: aceptar `0.1234567` y quedarse
/// con seis decimales es exactamente cómo empezó todo esto.
pub fn parse_quantity(text: &str) -> Result<QuantityValue, QuantityError> {
    let t = text.trim();
    let dec: Decimal = t.parse().map_err(|_| QuantityError::Malformed { text: t.to_string() })?;
    if dec.scale() > SCALE_DIGITS {
        return Err(QuantityError::NotRepresentable { text: t.to_string() });
    }
    let escalado = dec * Decimal::from(QUANTITY_SCALE);
    // `scale() <= 6` garantiza que esto ya es entero; si no cabe en i64, es Overflow.
    let raw = i64::try_from(escalado.trunc()).map_err(|_| QuantityError::Overflow)?;
    Ok(QuantityValue(raw))
}

/// **Frontera de salida:** cantidad → lo que se pinta. Sin ceros de adorno: `2`, no `2.000000`.
pub fn format_quantity(q: QuantityValue) -> String {
    let mut dec = Decimal::from(q.0) / Decimal::from(QUANTITY_SCALE);
    dec.normalize_assign();
    dec.to_string()
}

/// ¿Cae la cantidad en la rejilla de la unidad?
///
/// **No redondea.** Devolver `Ok` o `Err` es todo lo que hace: quien llama decide si rechaza el
/// comando (lo normal) o si ofrece al usuario un ajuste explícito y confirmado.
pub fn validate_increment(
    q: QuantityValue,
    increment: QuantityIncrement,
) -> Result<(), QuantityError> {
    if increment.value <= 0 {
        return Err(QuantityError::InvalidIncrement {
            increment: increment.value,
            reason: "el incremento debe ser positivo",
        });
    }
    if q.0 % increment.value != 0 {
        return Err(QuantityError::OffGrid { value: q.0, increment: increment.value });
    }
    Ok(())
}

/// Convierte a otra unidad aplicando la fracción exacta. Rechaza lo que no divide exacto.
///
/// Todo en `i128`: `raw × numerador` se sale de `i64` mucho antes de que la cantidad sea irreal.
pub fn convert_quantity_exact(
    q: QuantityValue,
    factor: ConversionFactor,
) -> Result<QuantityValue, QuantityError> {
    if factor.denominator == 0 {
        return Err(QuantityError::InvalidIncrement {
            increment: 0,
            reason: "el denominador del factor no puede ser cero",
        });
    }
    let producto =
        (q.0 as i128).checked_mul(factor.numerator as i128).ok_or(QuantityError::Overflow)?;
    let den = factor.denominator as i128;
    if producto % den != 0 {
        // 20 min → h es 1/3 periódico. Truncar a 0,333333 metería error en el importe y el stock.
        return Err(QuantityError::InexactConversion {
            value: q.0,
            numerator: factor.numerator,
            denominator: factor.denominator,
        });
    }
    let raw = i64::try_from(producto / den).map_err(|_| QuantityError::Overflow)?;
    Ok(QuantityValue(raw))
}

/// Importe de línea: **dinero entero por una cantidad de precio** (modelo `KPEIN` de SAP).
///
/// ```text
/// importe = HALF_UP( price_amount × cantidad ÷ price_quantity )
/// ```
///
/// Las escalas de `quantity` y `price_quantity` se cancelan, así que el resultado sale directamente
/// en la unidad mínima de la moneda. El redondeo es **uno solo, por LÍNEA** — nunca al total, que
/// es la disciplina de Stripe (*«each is rounded up before summing up the total»*).
///
/// Así «0,37 € por 100 ud» expresa un precio de 0,0037 €/ud **sin** meter decimales en el tipo del
/// dinero, y por tanto sin tocar la frontera fiscal (ADR-0123).
pub fn calculate_line_amount(
    price_amount: i64,
    quantity: QuantityValue,
    price_quantity: QuantityValue,
) -> Result<i64, QuantityError> {
    if price_quantity.0 == 0 {
        return Err(QuantityError::InvalidIncrement {
            increment: 0,
            reason: "la cantidad de precio no puede ser cero",
        });
    }
    let numerador =
        (price_amount as i128).checked_mul(quantity.0 as i128).ok_or(QuantityError::Overflow)?;
    let den = price_quantity.0 as i128;

    // HALF_UP sobre enteros: se redondea |n|/d y se devuelve el signo. `floor(|n|/d + 1/2)`
    // expresado sin decimales como `(2|n| + d) / 2d`.
    let negativo = (numerador < 0) != (den < 0);
    let n_abs = numerador.unsigned_abs();
    let d_abs = den.unsigned_abs();
    let doble = n_abs.checked_mul(2).ok_or(QuantityError::Overflow)?;
    let suma = doble.checked_add(d_abs).ok_or(QuantityError::Overflow)?;
    let redondeado = suma / (d_abs * 2);
    let valor = i128::try_from(redondeado).map_err(|_| QuantityError::Overflow)?;
    i64::try_from(if negativo { -valor } else { valor }).map_err(|_| QuantityError::Overflow)
}

/// Valida la configuración de una unidad **antes de usarla**.
///
/// `incremento × factor` debe (a) ser exacto en la escala global y (b) caer en la rejilla de la
/// unidad base. Una unidad incompatible se detecta así **al darla de alta**, no al cerrar una venta
/// con el cliente delante.
pub fn validate_unit_config(
    increment: QuantityIncrement,
    factor: ConversionFactor,
    base_increment: QuantityIncrement,
) -> Result<(), QuantityError> {
    if increment.value <= 0 || base_increment.value <= 0 {
        return Err(QuantityError::InvalidIncrement {
            increment: increment.value,
            reason: "el incremento debe ser positivo",
        });
    }
    let en_base = convert_quantity_exact(QuantityValue(increment.value), factor).map_err(|_| {
        QuantityError::InvalidIncrement {
            increment: increment.value,
            reason: "el incremento no es representable en la unidad base con la escala global",
        }
    })?;
    if en_base.0 % base_increment.value != 0 {
        return Err(QuantityError::InvalidIncrement {
            increment: increment.value,
            reason: "el incremento no es múltiplo del incremento de la unidad base",
        });
    }
    Ok(())
}
