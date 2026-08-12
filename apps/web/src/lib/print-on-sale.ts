// Auto-impresión del ticket al completar una venta. Vive en el SHELL (no en el módulo `sales`)
// porque imprimir es client-side —el runtime no toca hardware (ARQUITECTURA.md §2.7)— y debe
// escuchar SIEMPRE, no solo cuando la pantalla de ventas está montada (ADR-0017).
//
// Flujo: escucha el evento de dominio `sale.completed` (ADR-0010) → lee los ajustes de `printing`
// → según los flags:
//   - `auto_print_on_sale` → tique por la PUERTA GLOBAL (`erplora.print`), rol `receipt`.
//   - `open_drawer_on_sale` → kick del cajón por la impresora con rol `receipt` (hardware directo:
//     un cajón no se puede encolar, o está aquí o no está).
//
// ⚠️ El tique va por la puerta y NO por `peripherals.print` (hub#862). Esta era la rama que dejaba
// al TPV sin papel con el interruptor puesto: aquí se resolvía rol→impresora a mano, así que con la
// impresora descubierta pero SIN ROL —lo que le pasa a toda impresora recién encontrada— no había
// `receiptPrinterId`, los dos `if` salían en falso y la función **volvía en silencio**: ni Bridge,
// ni cola del hub, ni navegador, ni aviso, ni una línea en el log. Igual con `getDevices()`
// lanzando (PWA en el navegador): `catch { return; }`. La puerta ya sabe hacer todo eso —impresora
// del rol, cola del hub si no hay, y decir la verdad cuando no ha entregado—, y esto solo tenía que
// llamarla.
//
// La COMANDA de cocina ya NO se imprime aquí (ADR-0144): colgaba de `sale.completed`, o sea que
// mandaba la comida a la plancha **cuando el cliente pagaba** — el final del servicio. Ahora sale
// al disparar el pedido, en `print-comanda.ts`, y se enruta con las estaciones de `kitchen`
// (`kitchen_station` + destino por estación) en vez de con `printing.routing` (categoría → texto
// libre `receipt|kitchen|bar`, sin relación con las estaciones reales).
// `printing.print_kitchen` y `printing.routing.*` quedan OBSOLETOS: no los lee nadie.
import type { BridgeDevice, ErploraClient } from '@erplora/module-sdk';
import { printerIdForRole, type PrintRequest, type PrintResult } from './print';
import { buildReceiptDocument, type ReceiptSettings, type SaleLine } from './receipt-document';

interface PrintingSettings extends ReceiptSettings {
  auto_print_on_sale?: number;
  open_drawer_on_sale?: number;
}

/** El tique que NO salió: lo que necesita la caja para enterarse y reimprimirlo. */
export interface SaleTicketFailure {
  saleId: string;
  error: string;
}

interface Deps {
  /** La puerta global del hub (`erplora.print`). La inyecta el shell, igual que en `print-comanda`. */
  print: (req: PrintRequest) => Promise<PrintResult>;
  /**
   * Aviso de que el tique no ha llegado a ningún sitio. Sin él el fallo es MUDO, que es justo lo
   * que se arregla: el cajero cierra la venta creyendo que el papel está saliendo.
   */
  onFailure?: (f: SaleTicketFailure) => void;
}

/** Arranca el escuchador en el boot del shell. Devuelve la función para cancelar. */
export function bootPrintOnSale(client: ErploraClient, deps: Deps): () => void {
  return client.on('sale.completed', (payload) => {
    void onSaleCompleted(client, deps, payload).catch((e) => console.warn('[print-on-sale]', e));
  });
}

async function onSaleCompleted(client: ErploraClient, deps: Deps, payload: unknown): Promise<void> {
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

  if (autoPrint) {
    // Por la PUERTA: impresora del rol `receipt` si la hay, cola del hub si no (un print host la
    // drena, ADR-0196 §6). El documento va ESTRUCTURADO (hub#501) — sin `html`, porque el respaldo
    // del navegador no es una forma de entregar un tique térmico: si la puerta no entrega, se avisa.
    let result: PrintResult;
    try {
      result = await deps.print({
        role: 'receipt',
        documentType: 'receipt',
        // Mismo tique reimpreso = mismo trabajo: la cola (y el equipo que la drena) deduplica.
        jobId: `sale-${saleId}`,
        data: buildReceiptDocument(settings, sale, lines),
      });
    } catch (e) {
      result = { via: 'none', role: 'receipt', error: e instanceof Error ? e.message : String(e) };
    }
    // Solo la impresora y la cola son entrega. `browser` en la app instalada no imprime nada, y
    // `none` es explícitamente «por ningún sitio»: las dos se avisan.
    if (result.via !== 'bridge' && result.via !== 'queue') {
      deps.onFailure?.({ saleId, error: result.error ?? 'sin impresora' });
    }
  }

  if (openDrawer) {
    // El cajón SÍ necesita hardware aquí y ahora: no hay cola para un kick ESC/POS. Si este equipo
    // no alcanza la impresora de tiques, no se abre — y no puede arrastrar al tique consigo, que es
    // lo que pasaba cuando los dos colgaban del mismo `receiptPrinterId`.
    let devices: BridgeDevice[] = [];
    try {
      devices = await client.peripherals.getDevices();
    } catch {
      devices = []; // Este equipo no llega al hardware (PWA en el navegador).
    }
    // Resolución rol→impresora COMPARTIDA con la puerta global (`printerIdForRole`): una sola
    // definición de «qué impresora es el rol receipt».
    const receiptPrinterId = printerIdForRole(devices, 'receipt');
    if (receiptPrinterId) await client.peripherals.openDrawer(receiptPrinterId).catch(() => undefined);
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
