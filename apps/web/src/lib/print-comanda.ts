// print-comanda — la comanda sale a papel al DISPARAR el pedido, no al cobrar (ADR-0144).
//
// Vive en el SHELL, no en el módulo `kitchen`, por lo mismo que `print-on-sale` (ADR-0017):
// imprimir es client-side —el runtime no toca hardware (ARQUITECTURA.md §2.7)— y tiene que
// escuchar SIEMPRE, no solo cuando la pantalla del KDS está montada. Si dependiera de la pantalla,
// un local que usa únicamente impresora (lo normal en cocina caliente) no imprimiría nada.
//
// Flujo: `kitchen.order.created` → líneas de la comanda (cada una arrastra el destino de SU
// estación) → una hoja por ROL de impresora → puerta global `erplora.print` (lib/print.ts).
//
// Dos reglas que no son negociables, las dos por lo mismo (un bar lleno):
//  - **Nunca bloquea.** La comanda ya está en la BD y el KDS es la fuente de verdad; el papel es
//    una copia. Si la impresora falla se avisa y se puede reimprimir, pero el camarero sigue.
//  - **Desatendida.** `fallbackToBrowser:false`: nadie está delante de la cocina para darle a
//    "Imprimir" en un diálogo del navegador, y ese diálogo bloquearía la tablet de la sala.
import type { ErploraClient } from '@erplora/module-sdk';
import type { PrintRequest, PrintResult } from './print';

/** Escala global de cantidades (ADR-0147): `lógico = raw / 10⁶`. La fila y el evento hablan µ. */
const QUANTITY_SCALE = 1_000_000;

/** Línea de comanda tal y como la proyecta `kitchen.orders.items` (con el destino de su estación). */
export interface ComandaItem {
  product_name?: string;
  quantity?: number;
  notes?: string;
  station_id?: string | null;
  station_name?: string | null;
  /** `display` | `printer` | `both` — de la ESTACIÓN, no de la comanda. */
  destination?: string | null;
  /** ROL de impresora del Bridge (`kitchen`, `bar`, …), no un dispositivo. */
  printer_role?: string | null;
}

export interface ComandaGroup {
  role: string;
  items: { name: string; quantity: number; notes?: string }[];
}

/** Fallo de impresión de una hoja: lo que necesita la sala para avisar y reimprimir. */
export interface ComandaPrintFailure {
  orderId: string;
  role: string;
  label: string;
  error: string;
}

interface Deps {
  print: (req: PrintRequest) => Promise<PrintResult>;
  onFailure?: (f: ComandaPrintFailure) => void;
}

/**
 * Agrupa las líneas en hojas de papel. Agrupa por **rol de impresora**, no por estación: dos
 * estaciones pueden compartir impresora (postres sale por la de barra) y eso es UNA hoja, no dos.
 *
 * Lo que es solo pantalla (`display`) no entra: ya se ve en el KDS e imprimirlo es tirar papel.
 * Una línea sin destino conocido —producto que nadie ha enrutado aún— se imprime: descartarla
 * dejaría comida sin cocinar sin que nadie se entere.
 */
export function buildComandaGroups(items: ComandaItem[]): ComandaGroup[] {
  const groups = new Map<string, ComandaGroup['items']>();
  for (const item of items ?? []) {
    const destination = item.destination ?? 'both';
    if (destination === 'display') continue;
    const role = item.printer_role || 'kitchen';
    const line = {
      name: item.product_name ?? '',
      // La fila trae la cantidad en punto fijo 10⁶ (ADR-0147; kitchen ≥ 2.3, migración 005):
      // el papel habla lógico. 500000 µ → «0.5», nunca «500000 × Gambas».
      quantity: num(item.quantity ?? QUANTITY_SCALE) / QUANTITY_SCALE,
      ...(item.notes ? { notes: item.notes } : {}),
    };
    const group = groups.get(role);
    if (group) group.push(line);
    else groups.set(role, [line]);
  }
  return [...groups].map(([role, items]) => ({ role, items }));
}

/** Arranca el escuchador en el boot del shell. Devuelve la función para cancelar. */
export function bootPrintComanda(client: ErploraClient, deps: Deps): () => void {
  return client.on('kitchen.order.created', (payload) => {
    void onKitchenOrderCreated(client, payload, deps).catch((e) => console.warn('[print-comanda]', e));
  });
}

export async function onKitchenOrderCreated(
  client: ErploraClient,
  payload: unknown,
  deps: Deps,
): Promise<void> {
  const orderId = orderIdOf(payload);
  if (!orderId) return;

  // Las líneas son la AUTORIDAD: el payload del evento es un resumen (`items_count`), y es la
  // query la que trae el destino de cada estación, que es lo que decide qué va a papel.
  const items = await client
    .query<ComandaItem[]>('kitchen.orders.items', { order_id: orderId })
    .catch(() => [] as ComandaItem[]);
  const groups = buildComandaGroups(items ?? []);
  if (!groups.length) return; // todo era de pantalla, o la comanda venía vacía

  const header = first(
    await client
      .query<Record<string, unknown>[]>('kitchen.orders.get', { order_id: orderId })
      .catch(() => undefined),
  );
  // La etiqueta es lo ÚNICO que cocina sabe de la sala y se imprime tal cual: "Mesa 4", "Barra",
  // "Recogida Ana" (ADR-0144). Cocina no sabe qué es una mesa, ni tiene por qué.
  const label = str(header?.label);
  const roundNumber = num(header?.round_number ?? 1);
  const orderNumber = str(header?.order_number);

  // En secuencia y cada una con su try: una impresora sin papel no puede impedir que la otra
  // estación reciba su comanda.
  for (const group of groups) {
    try {
      const result = await deps.print({
        role: group.role,
        documentType: 'kitchen_order',
        fallbackToBrowser: false,
        // Mismo disparo reimpreso = mismo trabajo: el Bridge deduplica en vez de sacar dos hojas.
        jobId: `kitchen-${orderId}-${group.role}`,
        data: {
          receipt_id: orderNumber,
          label,
          round_number: roundNumber,
          items: group.items,
        },
      });
      // `none` = el Bridge no tiene ninguna impresora con ese rol. NO se reencamina a otra: sacar
      // la comanda de cocina por la impresora de tiquets deja al camarero con el papel y a la
      // cocina sin comida.
      if (result.via === 'none') {
        deps.onFailure?.({ orderId, role: group.role, label, error: result.error ?? 'sin impresora' });
      }
    } catch (e) {
      deps.onFailure?.({
        orderId,
        role: group.role,
        label,
        error: e instanceof Error ? e.message : String(e),
      });
    }
  }
}

function orderIdOf(payload: unknown): string | undefined {
  if (payload && typeof payload === 'object') {
    const p = payload as Record<string, unknown>;
    const id = p.order_id ?? p.id;
    return id != null ? String(id) : undefined;
  }
  return undefined;
}

function first<T>(v: T[] | T | undefined): T | undefined {
  return Array.isArray(v) ? v[0] : v;
}

function num(v: unknown): number {
  return typeof v === 'number' ? v : Number(v ?? 0) || 0;
}

function str(v: unknown): string {
  return v == null ? '' : String(v);
}
