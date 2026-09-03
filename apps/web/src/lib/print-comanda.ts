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
// La cabecera de esa hoja lleva la etiqueta de sala, la ronda y —desde hub#1410— **quién disparó
// la ronda**: cocina tiene que saber a quién llamar cuando un plato sale mal o va tarde, sin
// buscar a nadie por la sala. El id viaja opaco en la comanda y el nombre lo resuelve `waiterName`
// contra `hub.users.list`, igual que la tarjeta del KDS (kitchen#63, ADR-0192).
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
  /**
   * Suplementos congelados en la fila (`kitchen_order_item.modifiers`, pm#93): «Sin cebolla»,
   * «Al punto». Texto ya compuesto, no una lista: el módulo decide cómo se lee y el papel lo copia.
   */
  modifiers?: string | null;
  /** kitchen#57 · el MENÚ del que esta línea es componente (ADR-0381); NULL a la carta. */
  combo_ref?: string | null;
  /** El nombre CONGELADO de ese menú. */
  combo_name?: string | null;
  station_id?: string | null;
  station_name?: string | null;
  /** `display` | `printer` | `both` — de la ESTACIÓN, no de la comanda. */
  destination?: string | null;
  /** ROL de impresora del Bridge (`kitchen`, `bar`, …), no un dispositivo. */
  printer_role?: string | null;
}

/**
 * Una línea tal y como sale al papel.
 *
 * ⚠️ **Contrato de dispositivo.** `erplora-app` ya desplegada consume esto y lee `quantity`,
 * `name` y `notes`. Los tres campos de hub#1156 se añaden **sólo cuando la fila los trae**: una
 * app vieja ignora las claves que no conoce e imprime exactamente la misma hoja de siempre, que
 * es el 99 % de las comandas. Poner `modifiers: ''` en todas cambiaría la forma para todo el
 * mundo a cambio de nada.
 */
export interface ComandaLine {
  name: string;
  quantity: number;
  notes?: string;
  modifiers?: string;
  combo_ref?: string;
  combo_name?: string;
}

export interface ComandaGroup {
  role: string;
  items: ComandaLine[];
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
  /**
   * Notificación del SISTEMA al entrar la comanda. Opcional: sin ella todo sigue igual.
   *
   * El papel es una copia y el KDS es la fuente de verdad — pero una pantalla que nadie mira no
   * avisa de nada. En cocina caliente la tablet está apoyada, en otra vista o bloqueada, y la
   * notificación del SO es lo único que atraviesa eso.
   */
  notify?: (title: string, body: string) => Promise<void>;
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
    // El menú se marca en la LÍNEA, no en la hoja: así la cabecera se repite sola en cada
    // estación que reciba un componente (opción `11 - Send to Combo Parent Order Devices` de
    // Simphony) sin que este lado tenga que saber cuántas hojas hay. Un cocinero de la plancha
    // que no lee «MENÚ» no sabe que su entrecot va acoplado a un gazpacho, y lo saca cuando le
    // viene bien.
    const comboRef = str(item.combo_ref ?? '');
    const line: ComandaLine = {
      name: item.product_name ?? '',
      // La fila trae la cantidad en punto fijo 10⁶ (ADR-0147; kitchen ≥ 2.3, migración 005):
      // el papel habla lógico. 500000 µ → «0.5», nunca «500000 × Gambas».
      quantity: num(item.quantity ?? QUANTITY_SCALE) / QUANTITY_SCALE,
      ...(item.notes ? { notes: item.notes } : {}),
      // El suplemento es lo que hace que el plato VUELVA: se ve en el KDS y en la plancha, donde
      // nadie mira una pantalla con las manos ocupadas, hasta ahora no salía por ningún sitio.
      ...(item.modifiers ? { modifiers: str(item.modifiers) } : {}),
      ...(comboRef ? { combo_ref: comboRef, combo_name: str(item.combo_name ?? '') } : {}),
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
  const waiter = await waiterName(client, header);
  const priority = priorityFor(header);

  // El aviso va ANTES de la comprobación de hojas y ANTES de imprimir, a propósito:
  //  - antes de las hojas, porque una comanda de SOLO PANTALLA no genera ninguna y es justo el
  //    caso donde la notificación es el único aviso que existe;
  //  - antes de imprimir, porque avisar es instantáneo e imprimir puede tardar (o colgarse en una
  //    impresora sin papel), y cocina debe enterarse ya.
  // Best-effort: si falla, la comanda sigue su curso — igual que con el papel.
  if (deps.notify) {
    const titulo = label ? `Nueva comanda · ${label}` : 'Nueva comanda';
    const total = (items ?? []).length;
    const cuerpo = [orderNumber, total ? `${total} línea${total === 1 ? '' : 's'}` : '']
      .filter(Boolean)
      .join(' · ');
    await deps.notify(titulo, cuerpo).catch(() => {});
  }

  if (!groups.length) return; // todo era de pantalla, o la comanda venía vacía

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
          // Solo cuando hay nombre que poner: el renderizador ESC/POS omite la línea si el campo
          // no viene (`is_truthy(data, "waiter")`), y una app vieja ignora la clave que no conoce
          // — la hoja de siempre se sigue imprimiendo igual.
          ...(waiter ? { waiter } : {}),
          // Solo cuando hace falta el aviso: el renderizador ya asume NORMAL si el campo no viene
          // (`escpos.rs`), así que el 99 % de las comandas sigue sin la clave.
          ...(priority ? { priority } : {}),
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

/**
 * El NOMBRE de quien disparó la ronda, o `''` cuando no hay ninguno que poner (hub#1410, recorte
 * de kitchen#63).
 *
 * Cocina lo necesita para saber **a quién llamar** cuando un plato sale mal, va tarde o le falta
 * algo, sin salir a buscar a nadie por la sala; es lo que Toast, Square for Restaurants y
 * Lightspeed imprimen en la cabecera del chit. En pantalla ya estaba (la tarjeta del KDS lo pinta
 * desde kitchen#63); en el papel no salía porque su productor es este, no el módulo.
 *
 * El `waiter_id` de la comanda es **opaco**: `kitchen` no une con `hub_user` a propósito (ADR-0192
 * — el nombre es presentación y no debe atar el pase a la forma de las tablas del core), así que
 * lo resuelve el consumidor por `hub.users.list`. Misma puerta y misma política que la tarjeta.
 *
 * `''` cubre tres casos y los tres imprimen lo mismo —nada—: la ronda no trae camarero (comanda
 * vieja, disparo sin sesión), el hub ya no lista ese id (alguien que dejó el turno), o la lista no
 * se pudo cargar. Un UUID en el papel sería PEOR que el hueco: el cocinero lo lee a dos metros, no
 * puede usarlo y deja de fiarse de la cabecera.
 *
 * Sin `waiter_id` no se pregunta: sería una consulta más por cada comanda a cambio de nada.
 */
async function waiterName(client: ErploraClient, header: Record<string, unknown> | undefined): Promise<string> {
  const waiterId = str(header?.waiter_id);
  if (!waiterId) return '';
  const users = await client
    .query<{ id?: unknown; name?: unknown }[]>('hub.users.list')
    .catch(() => [] as { id?: unknown; name?: unknown }[]);
  const user = (Array.isArray(users) ? users : []).find((u) => u && str(u.id) === waiterId);
  return str(user?.name).trim();
}

/**
 * El aviso `!! URGENTE !!` del renderizador ESC/POS, o `''` cuando no aplica (hub#1411).
 *
 * El renderizador (`escpos.rs`) solo reacciona a la forma EXACTA `"HIGH"` — contrato de
 * dispositivo que no se toca, lo lee la `erplora-app` ya desplegada. `kitchen` habla su propio
 * vocabulario en minúsculas (`normal`/`rush`/`vip`, su contrato de datos, kitchen#39): el
 * adaptador es este productor, no el dispositivo ni el módulo.
 *
 * Solo `rush` dispara el aviso. `vip` queda fuera a propósito — es una prioridad de SALA (un
 * cliente a cuidar), no de cocina (un plato a sacar antes); si algún día tiene que sonar en el
 * pase es una decisión de negocio propia, no un efecto colateral de este mapeo.
 */
function priorityFor(header: Record<string, unknown> | undefined): string {
  return str(header?.priority) === 'rush' ? 'HIGH' : '';
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
