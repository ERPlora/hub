// Auto-impresión del ticket al completar una venta. Vive en el SHELL (no en el módulo `sales`)
// porque imprimir es client-side —el runtime no toca hardware (ARQUITECTURA.md §2.7)— y debe
// escuchar SIEMPRE, no solo cuando la pantalla de ventas está montada.
//
// Flujo: escucha el evento de dominio `sale.completed` → lee los ajustes de `printing` → busca la
// impresora con rol `receipt` en el Bridge → manda el recibo por `erplora.peripherals.print`.
// Todo defensivo: si falta el módulo printing, los ajustes, o el Bridge → no-op silencioso.
import type { ErploraClient } from '@erplora/module-sdk';

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
    const rows = await client.query<PrintingSettings[]>('printing.settings.get');
    settings = Array.isArray(rows) ? rows[0] : (rows as PrintingSettings | undefined);
  } catch {
    return;
  }
  if (!settings || Number(settings.auto_print_on_sale) !== 1) return;

  // Impresora con rol 'receipt' en el registro del Bridge.
  let receiptPrinterId: string | undefined;
  try {
    const devices = await client.peripherals.getDevices();
    const d = devices.find((x) => x.role === 'receipt');
    if (d) receiptPrinterId = `network:${d.ip}:${d.port}`;
  } catch {
    return; // Bridge no disponible
  }
  if (!receiptPrinterId) return;

  const sale = await client.query<Record<string, unknown>>('sales.get', { id: saleId });
  const lines = await client.query<SaleLine[]>('sales.lines', { id: saleId }).catch(() => [] as SaleLine[]);

  await client.peripherals.print(receiptPrinterId, 'receipt', buildReceipt(settings, sale, lines), `sale-${saleId}`);

  if (Number(settings.open_drawer_on_sale) === 1) {
    await client.peripherals.openDrawer(receiptPrinterId).catch(() => undefined);
  }
}

function saleIdOf(payload: unknown): string | undefined {
  if (payload && typeof payload === 'object') {
    const p = payload as Record<string, unknown>;
    const id = p.id ?? p.sale_id;
    return id != null ? String(id) : undefined;
  }
  return undefined;
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
    receipt_id: (sale.sale_number ?? sale.id ?? '') as string,
    items: (lines ?? []).map((l) => ({
      name: l.name ?? l.product_name ?? '',
      quantity: num(l.quantity ?? 1),
      total: num(l.total ?? l.line_total),
      notes: l.notes,
    })),
    subtotal: num(sale.subtotal),
    tax_amount: num(sale.tax_amount),
    total: num(sale.total),
    payment_method: (sale.payment_method_name ?? sale.payment_method ?? '') as string,
    paid: sale.paid != null ? num(sale.paid) : undefined,
    change: sale.change != null ? num(sale.change) : undefined,
    receipt_footer: settings.receipt_footer || undefined,
  };
}
