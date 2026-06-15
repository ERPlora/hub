// Auto-impresión del ticket al completar una venta. Vive en el SHELL (no en el módulo `sales`)
// porque imprimir es client-side —el runtime no toca hardware (ARQUITECTURA.md §2.7)— y debe
// escuchar SIEMPRE, no solo cuando la pantalla de ventas está montada (ADR-0017).
//
// Flujo: escucha el evento de dominio `sale.completed` (ADR-0010) → lee los ajustes de `printing`
// → resuelve impresoras por ROL en el Bridge (`receipt`/`kitchen`/`bar`) → según los flags:
//   - `auto_print_on_sale` → ticket por la impresora con rol `receipt` (formato `receipt` ESC/POS).
//   - `open_drawer_on_sale` → kick del cajón por la misma impresora de recibo.
//   - `print_kitchen`      → comandas: ítems enrutados por categoría a estaciones según
//                            `printing.routing.list`; sin regla, los productos (no servicios)
//                            van a `kitchen` por defecto; estación `receipt` = no comanda.
// Todo defensivo: si falta el módulo printing, los ajustes, o el Bridge → no-op silencioso.
import type { BridgeDevice, ErploraClient } from '@erplora/module-sdk';

interface PrintingSettings {
  receipt_header?: string;
  receipt_footer?: string;
  auto_print_on_sale?: number;
  open_drawer_on_sale?: number;
  print_kitchen?: number;
}

interface RoutingRule {
  category?: string;
  station?: string;
}

interface SaleLine {
  name?: string;
  product_name?: string;
  quantity?: number;
  total?: number;
  line_total?: number;
  is_service?: number | boolean;
  notes?: string;
  // `sales.lines` aún no proyecta categoría; se acepta si el contrato la añade (ver printing#1).
  category?: string;
  category_name?: string;
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
  const printKitchen = flag(settings.print_kitchen);
  if (!autoPrint && !openDrawer && !printKitchen) return;

  // Impresoras por ROL desde el registro del Bridge. El rol físico vive en el Bridge
  // (devices.json); printing solo decide QUÉ se imprime y a QUÉ estación lógica va.
  let devices: BridgeDevice[];
  try {
    devices = await client.peripherals.getDevices();
  } catch {
    return; // Bridge no disponible
  }
  const printerByRole = (role: string): string | undefined => {
    const d = devices.find((x) => x.role === role);
    return d ? `network:${d.ip}:${d.port}` : undefined;
  };

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

  if (printKitchen) {
    await printKitchenTickets(client, sale, lines, printerByRole, saleId);
  }
}

/**
 * Comandas a cocina/barra: agrupa los ítems por estación según `printing.routing.list`
 * (categoría → estación) y manda un `kitchen_order` por estación a la impresora con ese rol.
 * Reglas: categoría con regla → su estación; sin categoría/regla → `kitchen` (solo productos,
 * los servicios no se "cocinan"); estación `receipt` = excluido de comandas; estación sin
 * impresora con ese rol en el Bridge → se omite (no hay dónde imprimir).
 */
async function printKitchenTickets(
  client: ErploraClient,
  sale: Record<string, unknown>,
  lines: SaleLine[],
  printerByRole: (role: string) => string | undefined,
  saleId: string,
): Promise<void> {
  if (!lines.length) return;

  const rules = await client.query<RoutingRule[]>('printing.routing.list').catch(() => [] as RoutingRule[]);
  const stationByCategory = new Map<string, string>();
  for (const r of rules ?? []) {
    const cat = norm(r.category);
    if (cat && r.station) stationByCategory.set(cat, r.station);
  }

  const groups = new Map<string, SaleLine[]>();
  for (const line of lines) {
    const cat = norm(line.category ?? line.category_name);
    let station = cat ? stationByCategory.get(cat) : undefined;
    if (!station) {
      if (flag(line.is_service)) continue; // un servicio sin regla explícita no genera comanda
      station = 'kitchen';
    }
    if (station === 'receipt') continue;
    const group = groups.get(station);
    if (group) group.push(line);
    else groups.set(station, [line]);
  }

  const orderNumber = String(sale.sale_number ?? sale.id ?? saleId);
  for (const [station, items] of groups) {
    const printerId = printerByRole(station);
    if (!printerId) continue;
    const data = {
      receipt_id: orderNumber,
      items: items.map((l) => ({
        name: l.name ?? l.product_name ?? '',
        quantity: num(l.quantity ?? 1),
        notes: l.notes,
      })),
    };
    await client.peripherals
      .print(printerId, 'kitchen_order', data, `sale-${saleId}-${station}`)
      .catch((e) => console.warn(`[print-on-sale] comanda ${station}`, e));
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

function norm(v: unknown): string {
  return typeof v === 'string' ? v.trim().toLowerCase() : '';
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
