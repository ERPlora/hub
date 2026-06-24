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
 * Publica la moneda del hub en `globalThis.__erploraCurrency` (ADR-0059), de donde la lee el
 * `@erplora/module-sdk` (`erplora.currency` / `formatMoney` / `formatAmount`) como fallback cuando
 * el shell no le inyectó el getter. Mirror de cómo `erplora.locale` lee `localStorage('erplora.locale')`:
 * la moneda del hub es global (sin override por usuario), así que el shell la publica como dato.
 * La llama el boot (al sembrar settings desde el context) y la SettingsPage al guardar.
 */
export function publishHubCurrency(currency: string): void {
  try {
    (globalThis as { __erploraCurrency?: string }).__erploraCurrency = currency;
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
    ...(opts?.maximumFractionDigits != null
      ? { maximumFractionDigits: opts.maximumFractionDigits }
      : {}),
  });
}

/**
 * Formatea un importe en CÉNTIMOS (entero) con la moneda del hub (o `opts.currency`). El runtime
 * guarda dinero en céntimos para no arrastrar errores de coma flotante; esta es la entrada canónica.
 */
export function formatMoney(cents: number, opts?: FormatMoneyOptions): string {
  return intl(opts).format((cents || 0) / 100);
}

/**
 * Formatea un importe ya en UNIDADES mayores (euros, no céntimos). Para datos que llegan en unidades
 * (KPIs del dashboard, totales de factura del Cloud). Misma resolución de moneda/locale.
 */
export function formatAmount(units: number, opts?: FormatMoneyOptions): string {
  return intl(opts).format(units || 0);
}
