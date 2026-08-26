// Formateo de dinero del Hub. Fuente de la MONEDA = settings del hub (hub-settings.ts → /api/settings
// y /api/hub/context). Centraliza lo que cada pantalla reinventaba con su propio `Intl.NumberFormat`
// con 'EUR' hardcodeado.
//
// La moneda es GLOBAL del hub (decisión del humano: sin override por usuario). El idioma de
// formateo (separadores de miles/decimales) sigue el locale ACTIVO del shell (i18n), que sí puede
// ser un override del usuario — un usuario en inglés ve "€1,234.50" y uno en español "1.234,50 €".
//
// Dos entradas:
//   - formatMoney(cents, opts?)  → importe en CÉNTIMOS (enteros del runtime; evita errores float).
//   - formatAmount(units, opts?) → importe ya en UNIDADES mayores (lo que hoy usan Dashboard/Billing).
// Ambas usan por defecto la moneda del hub; `opts.currency` la sobreescribe (p.ej. facturas Cloud
// que traen su propia divisa).
import { getLocale } from '../i18n';
import { hubSettings } from './hub-settings';

/** Moneda del hub resuelta en el boot, o 'EUR' mientras no se conozca (degradación elegante). */
export function hubCurrency(): string {
  return hubSettings.value?.currency ?? 'EUR';
}

/**
 * Los **decimales de la moneda del hub** — la escala del dinero (ADR-0123 §7).
 *
 * El dinero viaja en UNIDADES MÍNIMAS, y cuántas hay en una unidad mayor **depende de la moneda**:
 * EUR 2, **JPY 0** (la unidad mínima ES el yen), KWD 3. Dividir siempre entre 100 es un bug en cuanto
 * el hub sale del euro — y la app es gratuita, así que sale.
 *
 * Los resuelve el runtime (`/api/hub/context` → `currency_decimals`): registro ISO-4217, o lo que el
 * hub haya declarado a mano si su moneda no está en él.
 */
export function hubCurrencyDecimals(): number {
  const d = hubSettings.value?.currency_decimals;
  return typeof d === 'number' ? d : decimalsForCurrency(hubCurrency());
}

/** Espejo del registro de Rust (`erplora_guest_sdk::currency`), como último recurso. */
const ZERO_DECIMAL = new Set(['BIF','CLP','DJF','GNF','ISK','JPY','KMF','KRW','PYG','RWF','UGX','UYI','VND','VUV','XAF','XOF','XPF']);
const THREE_DECIMAL = new Set(['BHD','IQD','JOD','KWD','LYD','OMR','TND']);
const FOUR_DECIMAL = new Set(['CLF','UYW']);
function decimalsForCurrency(code: string): number {
  const c = code.trim().toUpperCase();
  if (ZERO_DECIMAL.has(c)) return 0;
  if (THREE_DECIMAL.has(c)) return 3;
  if (FOUR_DECIMAL.has(c)) return 4;
  return 2;
}

/**
 * Publica la moneda del hub en `globalThis.__erploraCurrency` (ADR-0059), de donde la lee el
 * `@erplora/module-sdk` (`erplora.currency` / `formatMoney` / `formatAmount`) como fallback cuando
 * el shell no le inyectó el getter. Mirror de cómo `erplora.locale` lee `localStorage('erplora.locale')`:
 * la moneda del hub es global (sin override por usuario), así que el shell la publica como dato.
 * La llama el boot (al sembrar settings desde el context) y la SettingsPage al guardar.
 */
export function publishHubCurrency(currency: string): void {
  try {
    (globalThis as { __erploraCurrency?: string }).__erploraCurrency = currency;
    // Y su ESCALA: sin esto, un WC de módulo en un hub en yenes seguiría dividiendo entre 100.
    (globalThis as { __erploraCurrencyDecimals?: number }).__erploraCurrencyDecimals =
      hubCurrencyDecimals();
  } catch {
    /* noop — degradación elegante */
  }
}

export interface FormatMoneyOptions {
  /** ISO-4217. Por defecto, la moneda del hub. */
  currency?: string;
  /** Locale BCP-47 para los separadores. Por defecto, el locale activo del shell. */
  locale?: string;
  /** Dígitos decimales (por defecto, los de la divisa: 2 para EUR/USD). */
  maximumFractionDigits?: number;
}

function intl(opts?: FormatMoneyOptions): Intl.NumberFormat {
  return new Intl.NumberFormat(opts?.locale ?? getLocale(), {
    style: 'currency',
    currency: opts?.currency ?? hubCurrency(),
    // hub#1090: CLDR deja SIN agrupar los importes de 4 dígitos en español
    // (`minimumGroupingDigits=2` → «1234,56 €»), pero la regla vinculante del CLAUDE.md raíz es la
    // del sector (Odoo, Dynamics, Shopify, Holded, glibc, Excel y el comercio español): agrupar
    // SIEMPRE desde 4 dígitos («1.234,56 €»), porque en una columna de dinero alineada a la
    // derecha 1234,56 y 12.345,60 no alinean sus separadores. `true` es la forma booleana del
    // `'always'` de MDN — fuerza el grupo aunque el locale prefiera lo contrario — y la única que
    // tipa contra la lib ES2022 de este proyecto (la unión de strings llega con ES2023).
    useGrouping: true,
    ...(opts?.maximumFractionDigits != null
      ? { maximumFractionDigits: opts.maximumFractionDigits }
      : {}),
  });
}

/**
 * Formatea un importe en **UNIDADES MÍNIMAS** (entero) con la moneda del hub (o `opts.currency`).
 * Es la entrada canónica: el runtime guarda dinero en enteros para no arrastrar error binario.
 *
 * **Ya no divide entre 100 a ciegas**: divide entre `10^decimales-de-la-moneda`. En **JPY no divide**
 * (`1999` son 1999 ¥, no 19,99). Ver `hubCurrencyDecimals`.
 */
export function formatMoney(minor: number, opts?: FormatMoneyOptions): string {
  return intl(opts).format((minor || 0) / 10 ** hubCurrencyDecimals());
}

/**
 * Formatea un importe ya en UNIDADES mayores (euros, no céntimos). Para datos que llegan en unidades
 * (KPIs del dashboard, totales de factura del Cloud). Misma resolución de moneda/locale.
 */
export function formatAmount(units: number, opts?: FormatMoneyOptions): string {
  return intl(opts).format(units || 0);
}
