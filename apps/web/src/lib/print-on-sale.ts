// Auto-impresión del ticket al completar una venta. Vive en el SHELL (no en el módulo `sales`)
// porque imprimir es client-side —el runtime no toca hardware (ARQUITECTURA.md §2.7)— y debe
// escuchar SIEMPRE, no solo cuando la pantalla de ventas está montada (ADR-0017).
//
// Flujo: escucha el evento de dominio `sale.completed` (ADR-0010) → lee los ajustes de `printing`
// → según los flags:
//   - `auto_print_on_sale` (or the sale's own `print_receipt`, the till's switch — it wins, sales#283)
//     → tique por la PUERTA GLOBAL (`erplora.print`), rol `receipt`. The paper
//     is the one the ticket screen's print button prints, composed by the sales module
//     (`saleDocument`, hub#1921) — never rebuilt here from the raw sale rows.
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
//
// SOLO LA CAJA QUE COBRÓ (hub#1980). Todos los shells abiertos oyen todos los `sale.completed` (el
// hub emite un solo canal), así que con dos cajas y una impresora cada una el tique salía en las
// dos, y el cajón se abría en las dos. El hub sella el frame con la pestaña que mandó el cobro
// (`clientInstance`, de su `X-Client-Instance`); aquí solo se actúa sobre las ventas propias. Una
// venta que no cobró ningún shell (API, flujo) no la imprime ninguna caja.
import type { BridgeDevice, ErploraClient, EventMeta } from '@erplora/module-sdk';
import { CLIENT_INSTANCE } from './client-instance';
import { printerIdForRole, type PrintRequest, type PrintResult } from './print';

interface PrintingSettings {
  auto_print_on_sale?: number;
  open_drawer_on_sale?: number;
}

/** El tique que NO salió: lo que necesita la caja para enterarse y reimprimirlo. */
export interface SaleTicketFailure {
  saleId: string;
  error: string;
  /**
   * El tique está ENCOLADO y no hay ningún equipo dado de alta para sacarlo (hub#1731).
   *
   * Separa los dos avisos, que no son el mismo: aquí el papel no se ha perdido —sale solo en
   * cuanto se dé de alta la impresora— y lo que hay que hacer es darla de alta, no reimprimir.
   * Quien pinta el aviso elige la frase con esto; sin distinguirlo, la única salida era decir «NO
   * se imprimió», que manda al cajero a buscar un fallo que no existe.
   */
  awaitingHost?: boolean;
  /**
   * The paper itself could not be made: the sales module did not compose the ticket (hub#1921).
   * Nothing reached the printer or the queue, so the way out is reprinting from the ticket screen,
   * and the till says that in words — `error` carries the code for the log, never for the screen.
   */
  notComposed?: boolean;
}

interface Deps {
  /** La puerta global del hub (`erplora.print`). La inyecta el shell, igual que en `print-comanda`. */
  print: (req: PrintRequest) => Promise<PrintResult>;
  /**
   * The sale's ticket as the sales module prints it (`sale-document.ts`, hub#1921): the same paper
   * as the ticket screen's print button, once it carries the fiscal number and QR (hub#1867).
   * Rejects with an error code when it cannot be composed.
   */
  saleDocument: (saleId: string) => Promise<{ document: Record<string, unknown>; complete: boolean }>;
  /**
   * Aviso de que el tique no ha llegado a ningún sitio. Sin él el fallo es MUDO, que es justo lo
   * que se arregla: el cajero cierra la venta creyendo que el papel está saliendo.
   */
  onFailure?: (f: SaleTicketFailure) => void;
  /**
   * hub#1867 — the ticket DID come out, but before its fiscal number or VeriFactu QR were ready (the
   * viewer's wait ran out on a slow AEAT). The customer's copy lacks them; the receipt screen's
   * print button gives the complete one. Not a failure: the paper is in the customer's hand.
   */
  onPrintedWithoutFiscal?: (saleId: string) => void;
}

/** Arranca el escuchador en el boot del shell. Devuelve la función para cancelar. */
export function bootPrintOnSale(client: ErploraClient, deps: Deps): () => void {
  return client.onEvent('sale.completed', (payload, meta: EventMeta) => {
    // hub#1980: the till next door's sale is not ours — no paper, no drawer, no warning.
    if (meta.clientInstance !== CLIENT_INSTANCE) return;
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
  // ERPlora/sales#283 — the charge sheet's «Print receipt» switch travels with the sale and wins
  // over the setting for THAT sale, both ways (the setting is only the switch's default). A sale
  // from anywhere else carries no choice, and then the setting decides as it always did.
  const autoPrint = receiptChoiceOf(payload) ?? flag(settings.auto_print_on_sale);
  const openDrawer = flag(settings.open_drawer_on_sale);
  if (!autoPrint && !openDrawer) return;

  // The ticket and the drawer are independent: the cash goes in the drawer whatever happens to the
  // paper, and the drawer does not wait while the paper is being composed.
  await Promise.all([autoPrint && printTicket(deps, saleId), openDrawer && kickDrawer(client)]);
}

async function printTicket(deps: Deps, saleId: string): Promise<void> {
  // The paper the ticket screen prints (hub#1921). Built here from the raw `sales.get` rows it
  // came out with the amounts ×100 and the quantity in millionths; if the sales module cannot
  // compose it, nothing is printed and the till is told — the ticket screen reprints it.
  let data: Record<string, unknown>;
  let complete: boolean;
  try {
    ({ document: data, complete } = await deps.saleDocument(saleId));
  } catch (e) {
    deps.onFailure?.({ saleId, error: e instanceof Error ? e.message : String(e), notComposed: true });
    return;
  }

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
      data,
      // DESATENDIDA, igual que la comanda: nadie ha pedido imprimir, se ha cobrado. Un diálogo del
      // navegador aquí sacaría la app en un folio (este camino no manda `html`) y dejaría la caja
      // esperando un clic. Sin sitio donde imprimir se AVISA, que es lo que sirve al cajero.
      fallbackToBrowser: false,
    });
  } catch (e) {
    result = { via: 'none', role: 'receipt', error: e instanceof Error ? e.message : String(e) };
  }
  // La impresora entrega. La cola entrega **si alguien la drena**: encolar en un hub sin ningún
  // equipo dado de alta para la estación es lo que hacía MUDO el fallo de hub#1731 —se cobraba,
  // se decía «aquí tienes» y no salía nada—, porque `via:'queue'` se leía igual que impreso.
  // `browser` en la app instalada no imprime nada y `none` es «por ningún sitio»: las dos avisan.
  if (result.via === 'queue') {
    // `awaitingHost` solo es `true` cuando el runtime CONTESTÓ que no hay nadie. Que no lo
    // conteste no es un «no» (ver `PrintResult.awaitingHost`).
    if (result.awaitingHost) {
      deps.onFailure?.({ saleId, error: result.error ?? 'no printer set up for this station', awaitingHost: true });
      return;
    }
  } else if (result.via !== 'bridge') {
    deps.onFailure?.({ saleId, error: result.error ?? 'sin impresora' });
    return;
  }
  // Delivered. If it went out before its fiscal number or QR, the till hears where the complete
  // copy is (hub#1867) — only now, so a paper that never came out gets one warning, not two.
  if (!complete) deps.onPrintedWithoutFiscal?.(saleId);
}

async function kickDrawer(client: ErploraClient): Promise<void> {
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

/** The cashier's receipt choice for this sale (sales#283). Only a real boolean counts. */
function receiptChoiceOf(payload: unknown): boolean | undefined {
  const v = payload && typeof payload === 'object' ? (payload as Record<string, unknown>).print_receipt : undefined;
  return typeof v === 'boolean' ? v : undefined;
}

function flag(v: unknown): boolean {
  return v === true || Number(v ?? 0) === 1;
}
