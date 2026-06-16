import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-heatmap — heatmap de calendario/contribución (estilo GitHub) en CSS puro (grid de celdas).
// CONSTRUYE lo que Ionic no trae. AUTOCONTENIDO y CSP-safe: sin libs de fechas/charts; las
// intensidades se calculan con cuantiles propios y los colores se mezclan con color-mix.
//
// Dos layouts:
//   • 'weeks' (def): grid con flujo por columnas (grid-auto-flow: column), 7 filas (días de la
//     semana), una columna por semana — el clásico heatmap de actividad.
//   • 'year': 12 columnas (meses), cada una con un mini-grid de días.
//
// Datos (cualquiera de las dos formas):
//   • {date, value}  → la celda se ubica por fecha y el nivel se deriva de value (cuantiles).
//   • {key,  level}  → nivel explícito 0..levels-1 (sin fecha; orden de aparición).
//
// Cada celda lleva `title` nativo (tooltip) y `data-v` con el tier de intensidad 0..(levels-1).
export interface OkHeatmapCell {
  /** Fecha ISO (YYYY-MM-DD) o cualquier cosa parseable por Date; ubica la celda en el calendario. */
  date?: string;
  /** Valor crudo; se convierte a tier de intensidad por cuantiles. */
  value?: number;
  /** Clave libre para identificar la celda (modo sin fecha). */
  key?: string;
  /** Nivel/tier explícito 0..(levels-1); tiene prioridad sobre value. */
  level?: number;
  /** Tooltip opcional; si no, se autogenera (fecha · valor). */
  label?: string;
}

export type OkHeatmapLayout = 'weeks' | 'year';

// Celda ya resuelta y lista para pintar.
interface ResolvedCell {
  tier: number;
  title: string;
}

const MONTHS_ES = [
  'Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
  'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic',
];

export class OkHeatmap extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      box-sizing: border-box;

      /* Tokens propios estilo Ionic: --ok-* → --ion-* → hex. */
      --brand: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --empty: var(--ok-surface-shade, var(--ion-color-light, #eceef1));
      --muted: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --cell: 12px;
      --radius: 2px;
      --gap: 3px;
    }

    .wrap {
      display: flex;
      flex-direction: column;
      gap: 10px;
      width: 100%;
      box-sizing: border-box;
    }

    /* ---- Layout 'weeks': 7 filas, flujo por columnas (una columna por semana) ---- */
    .heat {
      display: grid;
      grid-auto-flow: column;
      grid-template-rows: repeat(7, 1fr);
      gap: var(--gap);
      /* Permite scroll horizontal cuando hay muchas semanas en móvil. */
      overflow-x: auto;
      padding-bottom: 2px;
    }

    /* ---- Layout 'year': 12 columnas de meses, cada una un mini-grid de días ---- */
    .year {
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 8px;
    }
    .month {
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 0;
    }
    .month-label {
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
      text-align: center;
    }
    .days {
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 2px;
    }

    /* ---- Celda ---- */
    .cell {
      width: var(--cell);
      height: var(--cell);
      border-radius: var(--radius);
      background: var(--empty);
    }
    .year .cell {
      width: 100%;
      aspect-ratio: 1 / 1;
      height: auto;
      border-radius: 1px;
    }
    /* Intensidades: mezcla brand X% con el fondo vacío (escala progresiva). */
    .cell[data-v='1'] { background: color-mix(in srgb, var(--brand) 25%, var(--empty)); }
    .cell[data-v='2'] { background: color-mix(in srgb, var(--brand) 50%, var(--empty)); }
    .cell[data-v='3'] { background: color-mix(in srgb, var(--brand) 75%, var(--empty)); }
    .cell[data-v='4'] { background: var(--brand); }

    /* ---- Leyenda Menos → Más ---- */
    .legend {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 5px;
      font-size: 10.5px;
      color: var(--muted);
    }
    .legend .cell {
      width: var(--cell);
      height: var(--cell);
    }
  `;

  /** Datos a pintar: array de {date,value} o {key,level}. */
  @property({ attribute: false }) data: OkHeatmapCell[] = [];

  /** Número de niveles de intensidad (incluye el nivel 0 = vacío). Por defecto 5 (tiers 0..4). */
  @property({ type: Number }) levels = 5;

  /** Color base de la escala (sobrescribe el token --brand si se da). */
  @property() scale = '';

  /** Layout: 'weeks' (flujo por columnas) o 'year' (12 meses). */
  @property() layout: OkHeatmapLayout = 'weeks';

  /** Tamaño de celda en px (solo aplica al layout 'weeks'). */
  @property({ type: Number, attribute: 'cell-size' }) cellSize = 12;

  /** Muestra la leyenda Menos → Más. */
  @property({ type: Boolean }) legend = false;

  // Tier máximo pintable (los tiers se clampean a [0, maxTier]).
  private get maxTier(): number {
    return Math.max(1, this.levels - 1);
  }

  // Aplica el color de escala explícito como override del token de host.
  private hostStyle(): string {
    const parts: string[] = [`--cell:${this.cellSize}px`];
    if (this.scale) parts.push(`--brand:${this.scale}`);
    return parts.join(';');
  }

  // Calcula umbrales por cuantiles sobre los valores presentes (reparte tiers 1..maxTier).
  private thresholds(): number[] {
    const vals = (this.data ?? [])
      .map((d) => d.value)
      .filter((v): v is number => typeof v === 'number' && v > 0)
      .sort((a, b) => a - b);
    if (!vals.length) return [];
    const max = this.maxTier;
    const th: number[] = [];
    // El tier k (1..max) empieza en el cuantil k/(max+1) de los valores positivos.
    for (let k = 1; k <= max; k++) {
      const idx = Math.min(vals.length - 1, Math.floor((k / (max + 1)) * vals.length));
      th.push(vals[idx]);
    }
    return th;
  }

  // Deriva el tier de intensidad de una celda (level explícito, o value vía cuantiles).
  private tierOf(cell: OkHeatmapCell, th: number[]): number {
    if (typeof cell.level === 'number') {
      return Math.max(0, Math.min(this.maxTier, Math.round(cell.level)));
    }
    const v = cell.value ?? 0;
    if (v <= 0 || !th.length) return 0;
    let tier = 1;
    for (let k = 0; k < th.length; k++) {
      if (v >= th[k]) tier = k + 1;
    }
    return Math.min(this.maxTier, tier);
  }

  // Texto del tooltip: label explícito, o fecha/clave + valor.
  private titleOf(cell: OkHeatmapCell): string {
    if (cell.label) return cell.label;
    const head = cell.date ?? cell.key ?? '';
    const tail = typeof cell.value === 'number' ? `${cell.value}` : '';
    if (head && tail) return `${head} · ${tail}`;
    return head || tail || '';
  }

  // Resuelve cada celda de entrada (tier + title) preservando el orden.
  private resolve(): ResolvedCell[] {
    const th = this.thresholds();
    return (this.data ?? []).map((cell) => ({
      tier: this.tierOf(cell, th),
      title: this.titleOf(cell),
    }));
  }

  // Pinta una celda (con data-v si tiene intensidad).
  private renderCell(c: ResolvedCell): unknown {
    return html`<div
      class="cell"
      data-v=${c.tier > 0 ? String(c.tier) : ''}
      role="gridcell"
      title=${c.title || ''}
    ></div>`;
  }

  // Layout 'weeks': el grid se rellena por columnas automáticamente (grid-auto-flow: column).
  private renderWeeks(cells: ResolvedCell[]): unknown {
    return html`<div class="heat" role="grid" aria-label="Heatmap de actividad">
      ${cells.map((c) => this.renderCell(c))}
    </div>`;
  }

  // Layout 'year': agrupa por mes (de la fecha) y pinta 12 columnas de mini-grids.
  private renderYear(): unknown {
    const th = this.thresholds();
    // Cubeta por mes 0..11; cada celda conserva su día para ordenar dentro del mes.
    const buckets: Array<Array<{ day: number; cell: ResolvedCell }>> = Array.from(
      { length: 12 },
      () => [],
    );
    for (const raw of this.data ?? []) {
      const resolved: ResolvedCell = { tier: this.tierOf(raw, th), title: this.titleOf(raw) };
      let month = 0;
      let day = 0;
      if (raw.date) {
        const d = new Date(raw.date);
        if (!Number.isNaN(d.getTime())) {
          month = d.getMonth();
          day = d.getDate();
        }
      }
      buckets[month].push({ day, cell: resolved });
    }
    return html`<div class="year" role="grid" aria-label="Heatmap anual">
      ${buckets.map(
        (items, m) => html`<div class="month" role="row" aria-label=${MONTHS_ES[m]}>
          <div class="month-label">${MONTHS_ES[m]}</div>
          <div class="days">
            ${items
              .slice()
              .sort((a, b) => a.day - b.day)
              .map((it) => this.renderCell(it.cell))}
          </div>
        </div>`,
      )}
    </div>`;
  }

  // Leyenda Menos → [vacío, 1, 2, …, maxTier] → Más.
  private renderLegend(): unknown {
    const tiers = Array.from({ length: this.maxTier + 1 }, (_, i) => i);
    return html`<div class="legend" aria-hidden="true">
      <span>Menos</span>
      ${tiers.map(
        (t) => html`<div class="cell" data-v=${t > 0 ? String(t) : ''}></div>`,
      )}
      <span>Más</span>
    </div>`;
  }

  render(): unknown {
    const cells = this.layout === 'year' ? [] : this.resolve();
    return html`<div class="wrap" style=${this.hostStyle()}>
      ${this.layout === 'year' ? this.renderYear() : this.renderWeeks(cells)}
      ${this.legend ? this.renderLegend() : null}
    </div>`;
  }
}

define('ok-heatmap', OkHeatmap);

declare global {
  interface HTMLElementTagNameMap {
    'ok-heatmap': OkHeatmap;
  }
}
