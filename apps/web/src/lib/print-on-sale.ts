// Auto-impresión del ticket al completar una venta. Vive en el SHELL (no en el módulo `sales`)
// porque imprimir es client-side —el runtime no toca hardware (ARQUITECTURA.md §2.7)— y debe
// escuchar SIEMPRE, no solo cuando la pantalla de ventas está montada (ADR-0017).
//
// Flujo: escucha el evento de dominio `sale.completed` (ADR-0010) → lee los ajustes de `printing`
// → resuelve impresoras por ROL en el Bridge (`receipt`/`kitchen`/`bar`) → según los flags:
//   - `auto_print_on_sale` → ticket por la impresora con rol `receipt` (formato `receipt` ESC/POS).
//   - `open_drawer_on_sale` → kick del cajón por la misma impresora de recibo.
// Todo defensivo: si falta el módulo printing, los ajustes, o el Bridge → no-op silencioso.
//
// La COMANDA de cocina ya NO se imprime aquí (ADR-0144): colgaba de `sale.completed`, o sea que
// mandaba la comida a la plancha **cuando el cliente pagaba** — el final del servicio. Ahora sale
// al disparar el pedido, en `print-comanda.ts`, y se enruta con las estaciones de `kitchen`
// (`kitchen_station` + destino por estación) en vez de con `printing.routing` (categoría → texto
// libre `receipt|kitchen|bar`, sin relación con las estaciones reales).
// `printing.print_kitchen` y `printing.routing.*` quedan OBSOLETOS: no los lee nadie.
import type { BridgeDevice, ErploraClient } from '@erplora/module-sdk';
import { printerIdForRole } from './print';

interface PrintingSettings {
  receipt_header?: string;
  receipt_footer?: string;
  auto_print_on_sale?: number;
  open_drawer_on_sale?: number;
}

interface SaleLine {
  name?: string;
  product_name?: string;
  quantity?: number;
  total?: number;
  line_total?: number;
  is_service?: number | boolean;
  notes?: string;
}

/** Arranca el escuchador en el boot del shell. Devuelve la función para cancelar. */
export function bootPrintOnSale(client: ErploraClient): () => void {
  return client.on('sale.completed', (payload) => {
    void onSaleCompleted(client, payload).catch((e) => console.warn('[print-on-sale]', e));
  });
}

async function onSaleCompleted(client: ErploraClient, payload: unknown): Promise<void> {
  const saleId = saleIdOf(payload);
  if (!saleId) return;

  // Ajustes de printing (si el módulo no está instalado, la query falla → no-op).
  let settings: PrintingSettings | undefined;
  try {
    settings = first(await client.query<PrintingSettings[] | PrintingSettings>('printing.settings.get'));
  } catch {
    return;
  }
  if (!settings) return;
  const autoPrint = flag(settings.auto_print_on_sale);
  const openDrawer = flag(settings.open_drawer_on_sale);
  if (!autoPrint && !openDrawer) return;

  // Impresoras por ROL desde el registro del Bridge. El rol físico vive en el Bridge
  // (devices.json); printing solo decide QUÉ se imprime y a QUÉ estación lógica va.
  let devices: BridgeDevice[];
  try {
    devices = await client.peripherals.getDevices();
  } catch {
    return; // Bridge no disponible
  }
  // Resolución rol→impresora COMPARTIDA con la puerta global `erplora.print` (lib/print.ts):
  // una sola definición de "qué impresora es el rol receipt/kitchen/bar".
  const printerByRole = (role: string): string | undefined => printerIdForRole(devices, role);

  // Datos autoritativos de la venta (el payload del evento es un resumen, no la fuente).
  const sale = first(
    await client
      .query<Record<string, unknown>[] | Record<string, unknown>>('sales.get', { sale_id: saleId })
      .catch(() => undefined),
  );
  if (!sale) return;
  const lines = await client
    .query<SaleLine[]>('sales.lines', { sale_id: saleId })
    .catch(() => [] as SaleLine[]);

  const receiptPrinterId = printerByRole('receipt');

  if (autoPrint && receiptPrinterId) {
    await client.peripherals
      .print(receiptPrinterId, 'receipt', buildReceipt(settings, sale, lines), `sale-${saleId}`)
      .catch((e) => console.warn('[print-on-sale] ticket', e));
  }

  if (openDrawer && receiptPrinterId) {
    await client.peripherals.openDrawer(receiptPrinterId).catch(() => undefined);
  }
}

function saleIdOf(payload: unknown): string | undefined {
  if (payload && typeof payload === 'object') {
    const p = payload as Record<string, unknown>;
    const id = p.sale_id ?? p.id;
    return id != null ? String(id) : undefined;
  }
  return undefined;
}

function first<T>(v: T[] | T | undefined): T | undefined {
  return Array.isArray(v) ? v[0] : v;
}

function flag(v: unknown): boolean {
  return v === true || Number(v ?? 0) === 1;
}

function num(v: unknown): number {
  return typeof v === 'number' ? v : Number(v ?? 0) || 0;
}

function buildReceipt(
  settings: PrintingSettings,
  sale: Record<string, unknown>,
  lines: SaleLine[],
): Record<string, unknown> {
  return {
    business_name: settings.receipt_header || 'ERPlora',
    receipt_id: String(sale.sale_number ?? sale.id ?? ''),
    customer_name: (sale.customer_name as string) || undefined,
    items: (lines ?? []).map((l) => ({
      name: l.name ?? l.product_name ?? '',
      quantity: num(l.quantity ?? 1),
      total: num(l.total ?? l.line_total),
      notes: l.notes,
    })),
    subtotal: num(sale.subtotal),
    tax_amount: num(sale.tax_amount),
    discount: sale.discount_amount != null ? num(sale.discount_amount) : undefined,
    total: num(sale.total),
    payment_method: String(sale.payment_method_name ?? sale.payment_method ?? ''),
    paid: sale.amount_tendered != null ? num(sale.amount_tendered) : undefined,
    change: sale.change_due != null ? num(sale.change_due) : undefined,
    receipt_footer: settings.receipt_footer || undefined,
  };
}
