/**
 * Contrato frontend de cantidades de ERPlora (ADR-0147).
 *
 * Una cantidad viaja y se persiste como un entero con escala global 10⁶. Estas funciones son
 * la frontera compartida entre ese wire exacto y el valor decimal que una persona ve o escribe.
 * Son el espejo TypeScript de `erplora_guest_sdk::units`, expuesto desde
 * `@erplora/module-sdk` para que Sales, Inventory, Invoice y el resto de módulos no mantengan
 * copias que puedan divergir.
 */

/** Escala global de cantidades: `cantidad_lógica = raw / QUANTITY_SCALE`. */
export const QUANTITY_SCALE = 1_000_000;

/** UI lógica → entero 10⁶. El redondeo absorbe únicamente el ruido IEEE-754 de la UI. */
export function toMicro(quantity: number): number {
  return Math.round(quantity * QUANTITY_SCALE);
}

/** Entero 10⁶ → cantidad lógica para operar o pintar en la UI. */
export function fromMicro(raw: number): number {
  return raw / QUANTITY_SCALE;
}

/**
 * Texto introducido por una persona → entero 10⁶.
 *
 * Acepta coma o punto decimal y rechaza más de seis decimales en vez de truncarlos. Esta
 * frontera de UI solo admite cantidades no negativas; los deltas firmados del ledger se crean
 * en la lógica de dominio Rust, no desde un campo de cantidad editable.
 */
export function parseQuantity(text: string): number | null {
  const normalized = text.trim().replace(',', '.');
  const match = /^(\d+)(?:\.(\d{1,6}))?$/.exec(normalized);
  if (!match) return null;

  // Parseo decimal exacto: evita convertir primero a float y acepta solo lo que cabe en el
  // `number` entero seguro que usa el wire JSON del navegador.
  const fraction = (match[2] ?? '').padEnd(6, '0');
  const raw = BigInt(match[1]) * BigInt(QUANTITY_SCALE) + BigInt(fraction || '0');
  return raw <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(raw) : null;
}

/** Entero 10⁶ → texto decimal sin ceros de adorno (`2`, no `2.000000`). */
export function formatQuantity(raw: number): string {
  if (!Number.isSafeInteger(raw)) return String(raw);
  const sign = raw < 0 ? '-' : '';
  const absolute = Math.abs(raw);
  const units = Math.floor(absolute / QUANTITY_SCALE);
  const fraction = String(absolute % QUANTITY_SCALE).padStart(6, '0').replace(/0+$/, '');
  return fraction ? `${sign}${units}.${fraction}` : `${sign}${units}`;
}

/**
 * Comprueba si una cantidad cae en el incremento de su unidad. Valida, nunca redondea.
 * Un incremento ausente/no positivo conserva la compatibilidad de las unidades sin rejilla.
 */
export function onGrid(raw: number, increment: number): boolean {
  if (!Number.isFinite(increment) || increment <= 0) return true;
  return Number.isSafeInteger(raw) && Number.isSafeInteger(increment) && raw % increment === 0;
}
