// Recolección y render genérico de los WIDGETS de dashboard que declaran los módulos instalados
// (contrato ADR-0054, ver architecture/hub/dashboard/widgets.md).
//
// REGLA RECTORA (CERO MOCKS): los MÓDULOS definen los widgets; cada widget de la vía declarativa
// consulta la BD REAL a través de una query declarativa del módulo. El shell NO inventa datos: si
// la query falla o no hay filas, el widget muestra un estado vacío/muted — nunca datos ficticios.
//
// El runtime sigue siendo un dispatcher genérico: aquí no hay lógica de negocio por widget. El
// shell solo:
//   1. reúne `manifest.widgets` de TODOS los módulos instalados (module.json crudo),
//   2. filtra por permiso de la sesión (la query revalida en server),
//   3. por cada widget produce un WidgetDef de <ok-widget-board> con un render(cell) imperativo,
//   4. para `kind` ejecuta la query y pinta el ok-* del kind (options primero, map sobreescribe),
//      para `component` carga el ESM del módulo y monta su WC (consulta solo),
//   5. deriva el preset "Recomendado" del sector del hub.
//
// Reutiliza los ok-* ya vendorizados (ok-kpi/ok-stat/ok-sparkline/ok-bar-list/ok-timeline/
// ok-chart). NO crea componentes nuevos. DOM imperativo sin innerHTML (CSP estricta: script-src
// 'self'). Datos tipados por PROPIEDAD JS, no por atributo (gotcha OutfitKit/Lit).

import type { ErploraClient } from '@erplora/module-sdk';
import type {
  ModuleManifest,
  WidgetManifestDef,
  WidgetSize,
} from '@erplora/module-types';
import type { WidgetDef, WidgetPreset } from '@erplora/outfitkit';

import { getLocale } from '../i18n';
import { formatMoney, hubCurrency, hubCurrencyDecimals } from './money';
import {
  loadInstalledManifests,
  loadModuleComponent,
  type InstalledManifest,
} from './module-loader';

// ── Tipos auxiliares ───────────────────────────────────────────────────────────────────────────

/** Una fila del resultado de una query (mapa columna → valor). */
type Row = Record<string, unknown>;

/** Resolución del permiso de la sesión: `true`/`false` decide; `null` = desconocido (no filtra). */
export type PermissionResolver = (permission: string) => boolean | null;

/** Texto opcional para los estados (vacío/error) del render. Default español. */
export interface WidgetRenderLabels {
  empty: string;
  error: string;
}

const DEFAULT_RENDER_LABELS: WidgetRenderLabels = {
  empty: 'Sin datos',
  error: 'No disponible',
};

/** Dependencias inyectadas a la recolección (cliente del Hub + sector + permiso + textos). */
export interface CollectWidgetsDeps {
  client: ErploraClient;
  /** Sector del hub para el preset "Recomendado" (o `null` si no se conoce → preset vacío). */
  sector: string | null;
  /** Resolución de permiso de la sesión. Por defecto: no filtra (la query revalida en server). */
  hasPermission?: PermissionResolver;
  /** Textos de los estados vacío/error. */
  labels?: Partial<WidgetRenderLabels>;
  /** Máx. de queries de widget en vuelo a la vez (T4). Por defecto `WIDGET_QUERY_CONCURRENCY`. */
  maxConcurrentQueries?: number;
}

/** Resultado de la recolección: catálogo de widgets + presets para <ok-widget-board>. */
export interface CollectedWidgets {
  /** CATÁLOGO completo: todo lo que el ⋮ ofrece activar. No es lo que se pinta de salida. */
  widgets: WidgetDef[];
  presets: WidgetPreset[];
  /**
   * Ids que arrancan ACTIVOS cuando el usuario aún no ha guardado un tablero propio (hub#1100).
   * Se entrega al board por `value`: sin esto, `ok-widget-board` cae a su último recurso
   * documentado —«sin `value` y sin presets ⇒ activa TODOS»— y un hub con 25 módulos abre con los
   * 20 widgets encendidos, los `default:false` incluidos. Contrato de ADR-0054 §4.
   */
  defaultActive: string[];
}

/**
 * Tope de widgets ACTIVOS de salida cuando el hub no tiene sector (hub#1100).
 *
 * Desde ADR-0087 el provisioning ya no inyecta `HUB_SECTOR`, así que «sin sector» dejó de ser el
 * caso raro para ser el normal: aplicar ahí la letra de ADR-0054 §4 («preset vacío») dejaría a
 * todos los hubs con un Inicio en blanco, que es justo lo que hub#367 vino a arreglar. Sin sector
 * no se puede saber QUÉ es relevante, así que se honra el `default` del autor del módulo y se
 * corta en un puñado legible: un Inicio que se lee de una ojeada, con el resto a un toque del ⋮.
 * Es lo que hacen Square, Shopify y Business Central — un puñado fijo y «Personalizar» al lado—;
 * ninguno pinta la unión de todo lo instalado.
 */
export const MAX_DEFAULT_ACTIVE_WITHOUT_SECTOR = 6;

/** Toma hasta `limit` elementos alternando entre grupos (1º de cada grupo, luego 2º de cada…). */
function roundRobin(groups: string[][], limit: number): string[] {
  const out: string[] = [];
  for (let round = 0; out.length < limit; round++) {
    let took = false;
    for (const g of groups) {
      if (round < g.length && out.length < limit) {
        out.push(g[round]!);
        took = true;
      }
    }
    if (!took) break;
  }
  return out;
}

// ── Normalización del resultado de una query ─────────────────────────────────────────────────────

/**
 * Normaliza el resultado de `client.query` a un array de filas. Una query de lista puede venir
 * como `{rows,total,limit,offset}` (motor de listas) o como array de filas (queries get/stats);
 * un escalar/objeto suelto se envuelve en una fila única. Robusto ante `null`/`undefined`.
 */
export function normalizeRows(result: unknown): Row[] {
  if (result == null) return [];
  if (Array.isArray(result)) return result as Row[];
  if (typeof result === 'object') {
    const obj = result as Record<string, unknown>;
    if (Array.isArray(obj.rows)) return obj.rows as Row[];
    return [obj as Row];
  }
  // Escalar (número/string/bool): una fila con la columna convencional `value`.
  return [{ value: result } as Row];
}

// ── Formateo de valores (Intl nativo, CSP-safe) ─────────────────────────────────────────────────

type ValueFormat = 'currency' | 'number' | 'percent' | 'compact';

function formatValue(
  value: unknown,
  format: ValueFormat | undefined,
  currency: string,
  locale: string | undefined,
): string {
  if (value == null) return '—';
  const num = typeof value === 'number' ? value : Number(value);
  if (!format || Number.isNaN(num)) {
    // Sin formato (o no numérico): muestra el valor crudo como texto.
    return String(value);
  }
  // Without a declared locale, the language of the UI — the same rule as `lib/money.ts` and as
  // `ok-bar-list` (which follows `<html lang>`), not a fixed es-ES (hub#2387).
  const loc = locale ?? getLocale();
  switch (format) {
    case 'currency':
      // Money travels in MINOR units of the hub currency (ADR-0007, ADR-0123 §7): `formatMoney`
      // scales by the decimals of that currency (EUR ÷100, JPY ÷1, KWD ÷1000), not a fixed ÷100
      // that paints 1999 ¥ as 19,99 (hub#2387).
      return formatMoney(num, { currency, locale: loc });
    case 'percent':
      return new Intl.NumberFormat(loc, { style: 'percent', maximumFractionDigits: 1 }).format(num);
    case 'compact':
      return new Intl.NumberFormat(loc, { notation: 'compact', maximumFractionDigits: 1 }).format(num);
    case 'number':
    default:
      return new Intl.NumberFormat(loc).format(num);
  }
}

// ── Card del widget: superficie consistente para TODOS los kinds + el escape hatch `component` ────
//
// Cada widget se pinta DENTRO de una card delimitada (fondo de card + borde 1px + radius + padding),
// con una cabecera compacta (title + icon) y un cuerpo que llena la celda del grid (altura 100% para
// no romper la cadena de altura — gotcha conocido: height, no min-height). El spinner de carga y el
// estado vacío/error viven DENTRO de la misma card, así el contenedor se ve aunque no haya datos.
// DOM imperativo sin innerHTML (CSP estricta); reusa primitivos (ion-spinner/ok-empty-state) y los
// tokens --ion-*/--ok-* ya existentes. NO crea componentes OutfitKit nuevos.

/** Alineación vertical del cuerpo: `center` para KPIs/valores, `start` para listas/gráficos/cronologías. */
type CardAlign = 'center' | 'start';

/** Crea la card del widget (host + cabecera + cuerpo) y devuelve refs para pintar dentro del body. */
interface WidgetCard {
  /** El elemento raíz de la card (se añade a la celda). */
  root: HTMLElement;
  /** El contenedor del cuerpo donde van el ok-* / WC / spinner / estado vacío. */
  body: HTMLElement;
}

function createCard(title: string, icon?: string, align: CardAlign = 'start'): WidgetCard {
  const root = document.createElement('div');
  // A11y (T5): cada widget es un grupo etiquetado. El nombre accesible arranca en el título; los
  // renderers de valor (kpi/stat) lo enriquecen con el valor real tras pintar (`title: valor`).
  root.setAttribute('role', 'group');
  root.setAttribute('aria-label', title);
  // Superficie de card consistente sobre tokens Ionic (paridad con ok-kpi/ion-card).
  root.style.cssText = [
    'box-sizing:border-box',
    'height:100%',
    'display:flex',
    'flex-direction:column',
    'gap:.5rem',
    'background:var(--ion-card-background, var(--ion-background-color, #fff))',
    'border:1px solid var(--ion-border-color, rgba(0,0,0,.08))',
    'border-radius:var(--ok-radius, 12px)',
    'box-shadow:0 1px 3px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.04)',
    'padding:1rem 1.125rem',
    'overflow:hidden',
  ].join(';');

  const head = document.createElement('div');
  head.style.cssText =
    'display:flex;align-items:center;justify-content:space-between;gap:.5rem;flex:0 0 auto';
  const titleEl = document.createElement('span');
  titleEl.textContent = title;
  titleEl.style.cssText =
    'font-size:.6875rem;font-weight:600;letter-spacing:.05em;text-transform:uppercase;' +
    'color:var(--ion-color-medium, #92949c);overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
  head.appendChild(titleEl);
  if (icon) {
    const ic = document.createElement('ion-icon');
    ic.setAttribute('name', icon);
    ic.setAttribute('aria-hidden', 'true');
    ic.style.cssText = 'font-size:1.25rem;color:var(--ion-color-medium, #92949c);flex:0 0 auto';
    head.appendChild(ic);
  }
  root.appendChild(head);

  const body = document.createElement('div');
  // El cuerpo llena el espacio restante de la card; su contenido (ok-*) ocupa el ancho.
  body.style.cssText =
    'flex:1 1 auto;min-height:0;display:flex;flex-direction:column;justify-content:' +
    (align === 'center' ? 'center' : 'flex-start');
  root.appendChild(body);

  return { root, body };
}

// ── Estados de celda (spinner / vacío / error) DENTRO de la card, DOM imperativo sin innerHTML ────

function clear(el: HTMLElement): void {
  el.replaceChildren();
}

function showSpinner(body: HTMLElement): void {
  clear(body);
  const wrap = document.createElement('div');
  wrap.style.cssText = 'display:flex;align-items:center;gap:.5rem;opacity:.6';
  const spinner = document.createElement('ion-spinner');
  spinner.setAttribute('name', 'crescent');
  wrap.appendChild(spinner);
  body.appendChild(wrap);
}

function showMuted(body: HTMLElement, text: string): void {
  clear(body);
  const empty = document.createElement('ok-empty-state');
  // ok-empty-state expone `title`/`message`/`icon` por propiedad; un mensaje muted basta aquí.
  (empty as HTMLElement & { message?: string; icon?: string }).message = text;
  (empty as HTMLElement & { message?: string; icon?: string }).icon = 'file-tray-outline';
  body.appendChild(empty);
}

// ── Helpers de map / options ─────────────────────────────────────────────────────────────────────

const TRENDS = new Set(['up', 'down', 'flat']);

/** Severities que tienen color de tono propio (`normal` usa el color de texto por defecto). */
const SEVERITY_TONES = new Set(['info', 'success', 'warning', 'danger']);

function trendOf(value: unknown): 'up' | 'down' | 'flat' {
  const s = String(value ?? '').toLowerCase();
  if (TRENDS.has(s)) return s as 'up' | 'down' | 'flat';
  // Tolerante: un delta numérico positivo/negativo deriva la tendencia.
  const n = Number(value);
  if (!Number.isNaN(n)) return n > 0 ? 'up' : n < 0 ? 'down' : 'flat';
  return 'flat';
}

/** Lee una columna del map desde una fila (o `undefined` si la prop no está mapeada). */
function mapped(row: Row, map: Record<string, string> | undefined, prop: string): unknown {
  const col = map?.[prop];
  return col != null ? row[col] : undefined;
}

// ── Renderers por kind ───────────────────────────────────────────────────────────────────────────
//
// Cada renderer recibe la celda + las filas normalizadas + map/options del widget y construye el
// ok-* correspondiente con datos por PROPIEDAD. Devuelve `false` si no hay datos suficientes (el
// llamante muestra el estado vacío). El shell parte de `options` y luego sobreescribe con `map`.

type Opts = Record<string, unknown>;

function str(opts: Opts, key: string): string | undefined {
  const v = opts[key];
  return v == null ? undefined : String(v);
}
function bool(opts: Opts, key: string): boolean {
  return opts[key] === true || opts[key] === 'true';
}

/**
 * `ok-kpi` trae su PROPIA superficie de card (borde/fondo/sombra/padding vía CSS vars). Dentro de
 * `createCard` eso dobla el marco (marco-dentro-de-marco). Lo aplanamos neutralizando esas vars para
 * que quede plano como `ok-stat` — la card exterior ya aporta la superficie. (P2 de hub-qa.)
 */
function flattenCardSurface(el: HTMLElement): void {
  el.style.setProperty('--background', 'transparent');
  el.style.setProperty('--border-color', 'transparent');
  el.style.setProperty('--box-shadow', 'none');
  el.style.setProperty('--padding', '0');
}

function renderKpi(
  cell: HTMLElement,
  rows: Row[],
  map: Record<string, string> | undefined,
  opts: Opts,
  title?: string,
): boolean {
  const row = rows[0];
  if (!row) return false;
  const rawValue = mapped(row, map, 'value');
  if (rawValue == null) return false;
  const currency = str(opts, 'currency') ?? hubCurrency();
  const locale = str(opts, 'locale');
  const format = str(opts, 'format') as ValueFormat | undefined;

  const el = document.createElement('ok-kpi') as HTMLElement & {
    label?: string; value?: string; delta?: string; trend?: string; icon?: string;
  };
  flattenCardSurface(el); // no doblar el marco de createCard (P2)
  // hub#1105: la `.label` de `ok-kpi` es otra CABECERA (uppercase, bold, con hueco de icono a su
  // derecha), no un subtítulo como la de `ok-stat`. Dentro del marco, que ya pinta título e icono,
  // eso son dos cabeceras apiladas — y en 4 de los 6 KPIs reales, el mismo icono dos veces. El
  // marco es el dueño de la cabecera: aquí sólo va el valor. Fuera del marco (sin `title`) el
  // componente conserva su cabecera propia.
  if (!title) {
    el.label = str(opts, 'label');
    el.icon = str(opts, 'icon');
  }
  el.value = formatValue(rawValue, format, currency, locale);
  const delta = mapped(row, map, 'delta');
  if (delta != null) {
    el.delta = String(delta);
    el.trend = trendOf(mapped(row, map, 'trend') ?? delta);
  }
  cell.appendChild(el);
  return true;
}

function renderStat(
  cell: HTMLElement,
  rows: Row[],
  map: Record<string, string> | undefined,
  opts: Opts,
  title?: string,
): boolean {
  const row = rows[0];
  if (!row) return false;
  const rawValue = mapped(row, map, 'value');
  if (rawValue == null) return false;
  const currency = str(opts, 'currency') ?? hubCurrency();
  const format = str(opts, 'format') as ValueFormat | undefined;

  const el = document.createElement('ok-stat') as HTMLElement & {
    label?: string; value?: string; hint?: string;
  };
  // `label` puede venir por columna (map) o literal (options); la columna tiene prioridad. La
  // cabecera de la card ya muestra el título → solo añadimos label si difiere (sin duplicar).
  const labelCol = mapped(row, map, 'label');
  el.label = captionLabel(labelCol != null ? String(labelCol) : str(opts, 'label'), title);
  el.value = formatValue(rawValue, format, currency, undefined);
  // `severity` (normal|info|success|warning|danger) NO es prop de ok-stat. En vez de mostrar el enum
  // crudo como texto ("danger"), lo reflejamos como TONO tintando el valor con la CSS var `--color`
  // que ok-stat expone. Un severity desconocido se ignora (no se inventa ni se filtra texto).
  const severity = String(mapped(row, map, 'severity') ?? '').toLowerCase();
  if (SEVERITY_TONES.has(severity)) {
    el.style.setProperty('--color', `var(--ion-color-${severity})`);
  }
  cell.appendChild(el);
  return true;
}

function renderSparkline(
  cell: HTMLElement,
  rows: Row[],
  map: Record<string, string> | undefined,
  opts: Opts,
  title?: string,
): boolean {
  const seriesCol = map?.series;
  if (!seriesCol) return false;
  const values = rows
    .map((r) => Number(r[seriesCol]))
    .filter((n) => !Number.isNaN(n));
  if (!values.length) return false;

  // Si hay `value`, lo presentamos como KPI con la sparkline en su slot; si no, sparkline suelto.
  const valueCol = map?.value;
  const spark = document.createElement('ok-sparkline') as HTMLElement & {
    values?: number[]; type?: string; filled?: boolean;
  };
  spark.values = values;
  spark.type = (str(opts, 'sparkType') as 'line' | 'bar' | undefined) ?? 'line';
  spark.filled = bool(opts, 'filled');

  if (valueCol) {
    const last = rows[rows.length - 1];
    const currency = str(opts, 'currency') ?? hubCurrency();
    const format = str(opts, 'format') as ValueFormat | undefined;
    const kpi = document.createElement('ok-kpi') as HTMLElement & {
      label?: string; value?: string; delta?: string; trend?: string; icon?: string;
    };
    flattenCardSurface(kpi); // no doblar el marco de createCard (P2)
    // Misma regla que `renderKpi` (hub#1105): dentro del marco, la cabecera ya está pintada.
    if (!title) {
      kpi.label = str(opts, 'label');
      kpi.icon = str(opts, 'icon');
    }
    kpi.value = formatValue(last?.[valueCol], format, currency, undefined);
    const deltaCol = map?.delta;
    if (deltaCol != null && last?.[deltaCol] != null) {
      kpi.delta = String(last[deltaCol]);
      kpi.trend = trendOf(map?.trend && last ? last[map.trend] : last?.[deltaCol]);
    } else if (map?.trend && last?.[map.trend] != null) {
      kpi.trend = trendOf(last[map.trend]);
    }
    spark.style.width = '100%';
    kpi.appendChild(spark);
    cell.appendChild(kpi);
  } else {
    spark.style.width = '100%';
    cell.appendChild(spark);
  }
  return true;
}

function renderBarList(
  cell: HTMLElement,
  rows: Row[],
  map: Record<string, string> | undefined,
  opts: Opts,
): boolean {
  const labelCol = map?.label;
  const valueCol = map?.value;
  if (!labelCol || !valueCol) return false;
  const colorCol = map?.color;
  const valueFormat = (str(opts, 'valueFormat') as string | undefined) ?? 'number';
  const valueDivisor = logicalDivisor(valueFormat, opts);
  const items = rows
    .map((r) => ({
      label: String(r[labelCol] ?? ''),
      value: (Number(r[valueCol]) || 0) / valueDivisor,
      color: colorCol ? (r[colorCol] as string | undefined) : undefined,
    }))
    .filter((i) => i.label !== '');
  if (!items.length) return false;

  const el = document.createElement('ok-bar-list') as HTMLElement & {
    items?: typeof items; valueFormat?: string; currency?: string; locale?: string; max?: number;
  };
  el.items = items;
  el.valueFormat = valueFormat;
  el.currency = str(opts, 'currency') ?? hubCurrency();
  el.locale = str(opts, 'locale') ?? getLocale();
  const max = opts.max != null ? Number(opts.max) : undefined;
  if (max != null && !Number.isNaN(max)) el.max = max;
  cell.appendChild(el);
  return true;
}

function renderTimeline(
  cell: HTMLElement,
  rows: Row[],
  map: Record<string, string> | undefined,
  opts: Opts,
): boolean {
  const titleCol = map?.title;
  if (!titleCol) return false;
  const items = rows
    .map((r, i) => {
      const get = (prop: string): string | undefined => {
        const col = map?.[prop];
        const v = col != null ? r[col] : undefined;
        return v == null ? undefined : String(v);
      };
      return {
        id: get('id') ?? String(i),
        title: String(r[titleCol] ?? ''),
        description: get('description'),
        time: get('time'),
        icon: get('icon'),
        color: get('color'),
        status: get('status') as 'done' | 'current' | 'pending' | undefined,
      };
    })
    .filter((i) => i.title !== '');
  if (!items.length) return false;

  const el = document.createElement('ok-timeline') as HTMLElement & {
    items?: typeof items; align?: string;
  };
  el.items = items;
  el.align = (str(opts, 'align') as 'left' | 'alternate' | undefined) ?? 'left';
  cell.appendChild(el);
  return true;
}

/**
 * The divisor that turns the stored value into the logical one the widget paints.
 *
 * Some magnitudes travel as fixed-point integers (quantities, ADR-0147 = scale 10⁶): the module
 * declares that boundary with `valueDivisor` and the shell stays generic. Money is the exception:
 * its scale belongs to the hub CURRENCY, not to the module (hub#2387) — the same ÷10^decimals as the
 * kpi, so a declared `valueDivisor: 100` neither divides twice nor turns 500 ¥ into 5 ¥.
 */
function logicalDivisor(format: string | undefined, opts: Opts): number {
  if (format === 'currency') return 10 ** hubCurrencyDecimals();
  const declared = Number(opts.valueDivisor ?? 1);
  return Number.isFinite(declared) && declared > 0 ? declared : 1;
}

/** Rounds away the binary noise of `k × step` (0.1 × 3 = 0.30000000000000004). */
const tidy = (n: number): number => Number(n.toPrecision(12));

/**
 * A round value scale (0, 500, 1.000…) that covers every value: `ok-chart` spaces its axis labels
 * evenly between `max` (top) and `min` (bottom), so the shell pins both to the ticks it labels.
 * Bars and areas grow from 0; a line starts at the lowest round value below its data.
 */
function niceScale(
  data: number[],
  fromZero: boolean,
  minStep: number,
): { min: number; max: number; ticks: number[] } {
  let lo = Math.min(...data);
  let hi = Math.max(...data);
  if (fromZero) {
    lo = Math.min(lo, 0);
    hi = Math.max(hi, 0);
  }
  if (hi === lo) hi = lo + Math.max(minStep, 1);
  // About four intervals, with a step of 1, 2, 2.5 or 5 × 10ⁿ.
  const rough = (hi - lo) / 4;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const norm = rough / magnitude;
  const nice = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
  const step = Math.max(nice * magnitude, minStep);
  const min = tidy(Math.floor(tidy(lo / step)) * step);
  const max = tidy(Math.ceil(tidy(hi / step)) * step);
  const ticks: number[] = [];
  for (let k = Math.round((max - min) / step); k >= 0; k--) ticks.push(tidy(min + k * step));
  return { min, max, ticks };
}

/** An axis tick: short (compact) so it fits the gutter of the chart, in the panel's format. */
function formatAxisTick(
  value: number,
  format: ValueFormat | undefined,
  currency: string,
  locale: string,
): string {
  if (format === 'percent') {
    return new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 1 }).format(value);
  }
  return new Intl.NumberFormat(locale, {
    ...(format === 'currency' ? { style: 'currency', currency } : {}),
    notation: 'compact',
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(value);
}

const ISO_DAY = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * A category label: an ISO day (`2026-09-29`, what a query returns for a `date`) is written in the
 * language of the UI («29 sept», «Sep 29»); anything else is left as the module sends it. The day
 * is built on the LOCAL calendar: the query already returns the business day (sales#323), and
 * `new Date('2026-09-29')` is midnight UTC — the 28th west of Greenwich.
 */
function formatCategory(label: string, days: Intl.DateTimeFormat): string {
  const m = ISO_DAY.exec(label);
  if (!m) return label;
  return days.format(new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
}

function renderChart(
  cell: HTMLElement,
  rows: Row[],
  map: Record<string, string> | undefined,
  opts: Opts,
): boolean {
  const labelCol = map?.label;
  const valueCol = map?.value;
  if (!labelCol || !valueCol) return false;
  // The panel's format (hub#2392): money in the hub currency with its decimals, the language of
  // the UI unless the panel sets a locale — the same rule as the kpi and the bar-list (hub#2387).
  const format = str(opts, 'format') as ValueFormat | undefined;
  const currency = str(opts, 'currency') ?? hubCurrency();
  const locale = str(opts, 'locale') ?? getLocale();
  const divisor = logicalDivisor(format, opts);
  const days = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short' });
  const labels: string[] = [];
  const data: number[] = [];
  for (const r of rows) {
    labels.push(formatCategory(String(r[labelCol] ?? ''), days));
    data.push((Number(r[valueCol]) || 0) / divisor);
  }
  if (!data.length) return false;

  const el = document.createElement('ok-chart') as HTMLElement & {
    type?: string; series?: Array<{ name?: string; data: number[] }>; labels?: string[];
    gridlines?: boolean; height?: number; axis?: string[]; min?: number; max?: number;
  };
  const type = (str(opts, 'chartType') as 'bar' | 'line' | 'area' | undefined) ?? 'line';
  el.type = type;
  el.series = [{ name: str(opts, 'seriesName'), data }];
  el.labels = labels;
  // Never a tick finer than the minor unit of the currency (no «0,5 ¥»).
  const scale = niceScale(data, type !== 'line', format === 'currency' ? 1 / divisor : 0);
  el.min = scale.min;
  el.max = scale.max;
  el.axis = scale.ticks.map((t) => formatAxisTick(t, format, currency, locale));
  el.gridlines = opts.gridlines == null ? true : bool(opts, 'gridlines');
  const height = opts.height != null ? Number(opts.height) : undefined;
  if (height != null && !Number.isNaN(height)) el.height = height;
  cell.appendChild(el);
  return true;
}

type KindRenderer = (
  cell: HTMLElement,
  rows: Row[],
  map: Record<string, string> | undefined,
  opts: Opts,
  /** Título del widget (lo muestra la cabecera de la card); kpi/stat lo usan para no duplicarlo. */
  title?: string,
) => boolean;

/** Devuelve la etiqueta a usar dentro de un ok-stat, omitiéndola si coincide con el título de la card. */
function captionLabel(label: string | undefined, title: string | undefined): string | undefined {
  return label && label !== title ? label : undefined;
}

/**
 * Icono de la cabecera de la card: el del widget y, en su defecto, el de `options` (hub#1105).
 * Desde que el kind dejó de pintar `options.icon`, este es el único sitio donde puede salir.
 */
function headerIcon(def: WidgetManifestDef): string | undefined {
  return def.icon ?? str(def.options ?? {}, 'icon');
}

const KIND_RENDERERS: Record<string, KindRenderer> = {
  kpi: renderKpi,
  stat: renderStat,
  sparkline: renderSparkline,
  'bar-list': renderBarList,
  timeline: renderTimeline,
  chart: renderChart,
};

// ── Construcción del WidgetDef (render por kind / por component) ──────────────────────────────────

const VALID_SIZES = new Set<WidgetSize>(['sm', 'md', 'lg']);

/** Debounce del refresco en vivo: absorbe ráfagas de eventos (un TPV en hora punta) en 1 re-query. */
const REFRESH_DEBOUNCE_MS = 800;

/**
 * Máximo de queries de widget en vuelo a la vez (T4). N widgets montándose NO deben disparar N
 * queries simultáneas: satura el pool per-hub (fix #609) y compite con la ruta crítica del TPV (una
 * venta en curso). Se escalonan por un semáforo; todas se ejecutan, solo que de `max` en `max`.
 */
const WIDGET_QUERY_CONCURRENCY = 4;

/** Semáforo async: como mucho `max` funciones corriendo a la vez; el resto hace cola y entra al liberar. */
type QueryGate = <T>(fn: () => Promise<T>) => Promise<T>;

function createQueryGate(max: number): QueryGate {
  let active = 0;
  const queue: Array<() => void> = [];
  const pump = (): void => {
    while (active < max && queue.length > 0) {
      active += 1;
      queue.shift()!();
    }
  };
  return <T>(fn: () => Promise<T>): Promise<T> =>
    new Promise<T>((resolve, reject) => {
      queue.push(() => {
        fn()
          .then(resolve, reject)
          .finally(() => {
            active -= 1;
            pump();
          });
      });
      pump();
    });
}

/** La celda recuerda su limpieza de suscripciones para no fugar listeners al re-renderizar/desmontar. */
interface CellWithCleanup extends HTMLElement {
  __widgetCleanup?: () => void;
}

function buildKindRender(
  client: ErploraClient,
  def: WidgetManifestDef,
  labels: WidgetRenderLabels,
  gate: QueryGate,
): (cell: HTMLElement) => void {
  // KPIs/valores se centran en la card; listas/cronologías/gráficos van top-align.
  const align: CardAlign =
    def.kind === 'bar-list' || def.kind === 'timeline' || def.kind === 'chart' ? 'start' : 'center';
  return (cell: HTMLElement): void => {
    // Si el board re-renderiza la misma celda, corta la suscripción anterior antes de crear otra.
    (cell as CellWithCleanup).__widgetCleanup?.();

    // Cada widget vive DENTRO de su card (contenedor visible); el cuerpo aloja
    // spinner/contenido/estado vacío, así la card se ve aunque la query no devuelva datos.
    // El icono de la cabecera: el del widget y, si no lo declara, el de `options` — que hasta
    // hub#1105 pintaba el propio kind. Así el marco es la ÚNICA cabecera sin perder el icono.
    const card = createCard(def.title, headerIcon(def), align);
    cell.replaceChildren(card.root);
    const query = def.query;
    const renderer = KIND_RENDERERS[def.kind ?? ''];

    // Ejecuta la query y pinta el resultado en el cuerpo de la card. `showLoading`=true en la carga
    // inicial (spinner); en un REFRESCO en vivo va a false: mantiene el valor visible hasta que
    // llega el nuevo (sin parpadeo). Un fallo SIEMPRE muestra muted, nunca deja un valor viejo
    // haciéndose pasar por fresco (CERO MOCKS + contrato T1).
    const run = (showLoading: boolean): void => {
      if (showLoading) showSpinner(card.body);
      if (!query || !renderer) {
        showMuted(card.body, labels.error);
        return;
      }
      // La query pasa por el semáforo (T4): se escalona para no saturar el pool per-hub con N
      // widgets a la vez. El refresco en vivo también entra por aquí.
      gate(() => client.query(query, def.params ?? {}))
        .then((result) => {
          const rows = normalizeRows(result);
          if (!rows.length) {
            showMuted(card.body, labels.empty);
            return;
          }
          clear(card.body);
          // `def.title` se pasa para que kpi/stat NO repitan el título que ya muestra la cabecera.
          const ok = renderer(card.body, rows, def.map, def.options ?? {}, def.title);
          if (!ok) {
            showMuted(card.body, labels.empty);
            return;
          }
          // A11y (T5): enriquece el nombre accesible del grupo con el valor real pintado (kpi/stat);
          // los demás kinds se quedan con el título (su detalle ya es el contenido leíble).
          const valueEl = card.body.querySelector('ok-kpi, ok-stat') as
            | (HTMLElement & { value?: string })
            | null;
          if (valueEl?.value) card.root.setAttribute('aria-label', `${def.title}: ${valueEl.value}`);
        })
        .catch(() => {
          // CERO MOCKS: ante un fallo de la query mostramos estado muted, nunca datos inventados.
          showMuted(card.body, labels.error);
        });
    };

    run(true); // carga inicial

    // Refresco en vivo (ADR-0054 T1): suscribe la card a los eventos de dominio declarados en
    // `refresh_on` sobre el canal push ya existente (Outbox→broadcast, SDK subscribe) y re-consulta
    // con debounce. Sin `refresh_on` el widget se monta UNA vez (comportamiento previo intacto).
    const events = def.refresh_on;
    if (events?.length && typeof client.on === 'function') {
      let timer: ReturnType<typeof setTimeout> | undefined;
      const cleanup = (): void => {
        if (timer) clearTimeout(timer);
        for (const unsub of unsubs) unsub();
        (cell as CellWithCleanup).__widgetCleanup = undefined;
      };
      const onEvent = (): void => {
        // Celda ya desmontada → deja de escuchar (limpieza acotada, sin fugas de listeners).
        if (!card.root.isConnected) {
          cleanup();
          return;
        }
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => run(false), REFRESH_DEBOUNCE_MS);
      };
      const unsubs = events.map((ev) => client.on(ev, onEvent));
      (cell as CellWithCleanup).__widgetCleanup = cleanup;
    }
  };
}

function buildComponentRender(
  client: ErploraClient,
  mod: InstalledManifest,
  def: WidgetManifestDef,
  labels: WidgetRenderLabels,
): (cell: HTMLElement) => void {
  const tag = def.component as string;
  return (cell: HTMLElement): void => {
    // El WC del módulo también vive dentro de una card con la cabecera del widget (uniformidad).
    const card = createCard(def.title, headerIcon(def), 'start');
    cell.replaceChildren(card.root);
    showSpinner(card.body);
    loadModuleComponent(mod, tag)
      .then(() => {
        clear(card.body);
        // Mismo patrón que ModuleView/provides_slots: el WC recibe el cliente por propiedad y
        // consulta sus datos él mismo (WC → SDK → Rust; nunca toca la BD).
        const el = document.createElement(tag) as HTMLElement & { client?: unknown };
        // Con el scope de su módulo, igual que ModuleView (hub#714): el widget es tan módulo como
        // la página, y el id lo pone quien monta, no quien se monta.
        el.client = client.forModule(mod.moduleId);
        card.body.appendChild(el);
      })
      .catch(() => {
        showMuted(card.body, labels.error);
      });
  };
}

/** Valida que el widget tenga EXACTAMENTE UNO de {kind, component} (y query si hay kind). */
function isValidDef(def: WidgetManifestDef): boolean {
  if (!def.title) return false;
  const hasKind = def.kind != null;
  const hasComponent = def.component != null;
  if (hasKind === hasComponent) return false; // ni ambos ni ninguno
  if (hasKind && !def.query) return false;
  return true;
}

// ── Recolección ──────────────────────────────────────────────────────────────────────────────────

/**
 * Recolecta los widgets de TODOS los módulos instalados y devuelve el catálogo + presets para
 * <ok-widget-board>. Llama a `loadInstalledManifests()` por su cuenta.
 */
export async function collectDashboardWidgets(deps: CollectWidgetsDeps): Promise<CollectedWidgets> {
  const mods = await loadInstalledManifests();
  return buildWidgetsFromManifests(mods, deps);
}

/** Variante pura (sin I/O) para tests / cuando ya se tienen los manifests cargados. */
export function buildWidgetsFromManifests(
  mods: InstalledManifest[],
  deps: CollectWidgetsDeps,
): CollectedWidgets {
  const labels: WidgetRenderLabels = { ...DEFAULT_RENDER_LABELS, ...deps.labels };
  const hasPermission = deps.hasPermission;
  const sector = deps.sector;
  // Semáforo COMPARTIDO por todos los widgets de este board (T4): escalona sus queries.
  const gate = createQueryGate(deps.maxConcurrentQueries ?? WIDGET_QUERY_CONCURRENCY);

  const widgets: WidgetDef[] = [];
  const recommended: string[] = [];
  // `default:true` sin mirar el sector, AGRUPADOS por módulo: el respaldo de un hub que aún no
  // tiene sector (hub#1100). Se agrupan para que el recorte reparta entre módulos (ver abajo).
  const suggestedByModule = new Map<string, string[]>();

  for (const mod of mods) {
    const map = (mod.manifest as ModuleManifest).widgets;
    if (!map) continue;
    for (const [id, def] of Object.entries(map)) {
      if (!isValidDef(def)) continue;

      // Filtro por permiso EN CLIENTE (solo mostrar/ocultar; la query revalida en server). Si el
      // resolutor devuelve `null` (permiso desconocido), NO filtramos — degradación permisiva.
      if (def.permission && hasPermission) {
        const allowed = hasPermission(def.permission);
        if (allowed === false) continue;
      }

      const size: WidgetSize = def.size && VALID_SIZES.has(def.size) ? def.size : 'md';
      // i18n (ADR-0055): el título canónico (inglés) del manifest se traduce con el locale del
      // módulo para el idioma activo (`locale.widgets.<id>.title`/`.label`); sin entrada, se queda
      // el canónico. El `label` (caption dentro de kpi/stat) va en `options.label`.
      const tr = mod.locale?.widgets?.[id];
      const title = tr?.title ?? def.title;
      const label = tr?.label;
      let localizedDef: WidgetManifestDef = def;
      if (title !== def.title || label != null) {
        localizedDef = { ...def, title };
        if (label != null) localizedDef.options = { ...def.options, label };
      }
      const render =
        def.kind != null
          ? buildKindRender(deps.client, localizedDef, labels, gate)
          : buildComponentRender(deps.client, mod, localizedDef, labels);

      widgets.push({ id, title, icon: def.icon, category: def.category, size, render });

      // Preset "Recomendado": widgets con default===true cuyo sectors incluye el sector del hub
      // (o sin sectors = todos). Sin sector conocido → no se recomienda nada (preset vacío).
      if (def.default) {
        const bucket = suggestedByModule.get(mod.moduleId) ?? [];
        bucket.push(id);
        suggestedByModule.set(mod.moduleId, bucket);
        if (sector) {
          const sectors = def.sectors;
          const applies = !sectors || sectors.length === 0 || sectors.includes(sector as never);
          if (applies) recommended.push(id);
        }
      }
    }
  }

  const presets: WidgetPreset[] =
    recommended.length > 0
      ? [{ id: 'recommended', label: 'Recomendado', widgets: recommended }]
      : [];

  // Qué arranca ACTIVO (hub#1100). Con sector manda la elección informada del autor del módulo
  // (`default` ∩ `sectors`), sin tope. Sin sector no hay nada contra lo que casar `sectors`, así
  // que se cae a los `default:true` recortados a un puñado legible. Un `default:false` NUNCA entra
  // por ninguna de las dos vías: eso lo activa el usuario desde el ⋮.
  //
  // El recorte va en ROUND-ROBIN por módulo (el primer `default:true` de cada módulo antes que el
  // segundo de ninguno): un corte por orden de instalación dejaba, en el banco real, 3 de inventario
  // + 3 de personal y fuera «Ventas hoy» y «Caja» — un puñado legible tiene que ser representativo.
  const defaultActive = sector
    ? recommended
    : roundRobin([...suggestedByModule.values()], MAX_DEFAULT_ACTIVE_WITHOUT_SECTOR);

  return { widgets, presets, defaultActive };
}
