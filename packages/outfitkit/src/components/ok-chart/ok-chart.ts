import { LitElement, html, css, svg } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-chart — gráfico declarativo en SVG inline (línea / área / barras).
// AUTOCONTENIDO y CSP-safe: dibuja el SVG a mano, sin librerías de charts.
// Porta el look del antiguo .ux-chart (rejilla fina, eje de valor a la izquierda,
// etiquetas X en mono abajo, área con degradado .5→0, serie de proyección punteada,
// barras redondeadas rx=2 con variante "mute").
//
//   • prop type        → 'line' | 'area' | 'bar' (def 'line')
//   • prop .series     → OkChartSeries[]  (cada serie: {name,color,data,dashed?,mute?})
//   • prop .labels     → string[]  (etiquetas del eje X)
//   • prop gridlines   → boolean (líneas horizontales de fondo, def true)
//   • prop .axis       → string[] (etiquetas del eje de valor; arriba→abajo)
//   • prop height      → alto del SVG en px (def 200)
//   • prop endpoint    → boolean (punto + etiqueta de valor al final de la 1ª línea)
//   • prop endpointLabel → texto de esa etiqueta (si no, usa el último valor)
//
// Presentacional: no emite eventos.

/** Una serie de datos del gráfico. */
export interface OkChartSeries {
  /** Nombre (para la leyenda). */
  name?: string;
  /** Color del trazo/relleno/barra; cae a la cadena de tokens si se omite. */
  color?: string;
  /** Valores numéricos de la serie. */
  data: number[];
  /** En línea/área: dibuja la serie como trazo punteado (proyección). */
  dashed?: boolean;
  /** En barras: pinta esta serie/columna atenuada (variante mute). */
  mute?: boolean;
}

export type OkChartType = 'line' | 'area' | 'bar';

export class OkChart extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --primary: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --grid: var(--ok-border-color, var(--ion-border-color, #e0e0e0));
      --axis-color: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --value-color: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --mute: var(--ok-color-step-200, var(--ion-color-step-200, #cccccc));
      --surface: var(--ok-surface, var(--ion-background-color, #ffffff));
      --legend-color: var(--ok-color-medium, var(--ion-color-medium, #92949c));
    }

    .chart {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      width: 100%;
      box-sizing: border-box;
    }

    svg {
      display: block;
      width: 100%;
      overflow: visible;
      font-family: ui-monospace, 'SF Mono', 'Roboto Mono', Menlo, Consolas, monospace;
    }

    .grid line {
      stroke: var(--grid);
      stroke-width: 1;
      shape-rendering: crispEdges;
    }

    .axis text {
      fill: var(--axis-color);
      font-size: 10px;
      font-variant-numeric: tabular-nums;
    }

    .value-label {
      fill: var(--value-color);
      font-weight: 600;
      font-size: 11px;
      font-variant-numeric: tabular-nums;
    }

    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      font-size: 0.72rem;
      color: var(--legend-color);
    }
    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 0.375rem;
    }
    .legend-dot {
      width: 8px;
      height: 8px;
      border-radius: 2px;
      flex-shrink: 0;
    }
    .legend-dot.dashed {
      height: 2px;
      border-radius: 1px;
    }
  `;

  /** Tipo de gráfico. */
  @property() type: OkChartType = 'line';

  /** Series de datos. */
  @property({ attribute: false }) series: OkChartSeries[] = [];

  /** Etiquetas del eje X (debajo). */
  @property({ attribute: false }) labels: string[] = [];

  /** Etiquetas del eje de valor (izquierda), de arriba a abajo. */
  @property({ attribute: false }) axis: string[] = [];

  /** Pinta las líneas de rejilla horizontales. */
  @property({ type: Boolean }) gridlines = true;

  /** Alto del SVG en px. */
  @property({ type: Number }) height = 200;

  /** Punto + etiqueta de valor al final de la primera serie (líneas). */
  @property({ type: Boolean }) endpoint = false;

  /** Texto de la etiqueta del endpoint; si se omite usa el último dato. */
  @property() endpointLabel = '';

  // ---- Geometría del lienzo (viewBox ~600x200, preserveAspectRatio none) ----
  private readonly vbWidth = 600;
  private get vbHeight(): number {
    return this.height;
  }
  // Margen para dejar sitio al eje de valor (izq) y a las etiquetas X (abajo).
  private get pad() {
    return {
      left: this.axis.length ? 44 : 12,
      right: this.endpoint ? 56 : 12,
      top: 12,
      bottom: this.labels.length ? 22 : 12,
    };
  }
  private get plotW(): number {
    const p = this.pad;
    return this.vbWidth - p.left - p.right;
  }
  private get plotH(): number {
    const p = this.pad;
    return this.vbHeight - p.top - p.bottom;
  }

  // Mínimo/máximo global de todas las series (las barras crecen desde 0).
  private get bounds(): { min: number; max: number } {
    const all: number[] = [];
    for (const s of this.series ?? []) for (const v of s.data ?? []) all.push(v);
    if (!all.length) return { min: 0, max: 1 };
    let min = Math.min(...all);
    let max = Math.max(...all);
    if (this.type !== 'line') min = Math.min(min, 0); // área/barras incluyen la base 0
    if (min === max) max = min + 1; // serie plana
    return { min, max };
  }

  // Color efectivo de una serie (prop o el token primario del componente).
  private seriesColor(s: OkChartSeries, muted = false): string {
    if (s.mute || muted) return s.color ?? 'var(--mute)';
    return s.color || 'var(--primary)';
  }

  // Mapea (índice, valor) → coordenadas {x, y} del área de dibujo.
  private xAt(i: number, n: number): number {
    const p = this.pad;
    if (n <= 1) return p.left + this.plotW / 2;
    return p.left + (i / (n - 1)) * this.plotW;
  }
  private yAt(value: number): number {
    const { min, max } = this.bounds;
    const p = this.pad;
    return p.top + (1 - (value - min) / (max - min)) * this.plotH;
  }

  // ---- Rejilla horizontal ----
  private renderGrid(): unknown {
    if (!this.gridlines) return svg``;
    const p = this.pad;
    const rows = Math.max(this.axis.length || 4, 2);
    const lines = [];
    for (let i = 0; i < rows; i++) {
      const y = p.top + (i / (rows - 1)) * this.plotH;
      lines.push(svg`<line x1=${p.left} x2=${this.vbWidth - p.right} y1=${y} y2=${y} />`);
    }
    return svg`<g class="grid">${lines}</g>`;
  }

  // ---- Eje de valor (izquierda) ----
  private renderValueAxis(): unknown {
    if (!this.axis.length) return svg``;
    const p = this.pad;
    const n = this.axis.length;
    const ticks = this.axis.map((t, i) => {
      const y = n > 1 ? p.top + (i / (n - 1)) * this.plotH : p.top + this.plotH / 2;
      return svg`<text x=${p.left - 8} y=${y + 3} text-anchor="end">${t}</text>`;
    });
    return svg`<g class="axis">${ticks}</g>`;
  }

  // ---- Etiquetas del eje X (abajo) ----
  private renderXLabels(): unknown {
    if (!this.labels.length) return svg``;
    const n = this.labels.length;
    const y = this.vbHeight - this.pad.bottom + 14;
    const ticks = this.labels.map((t, i) => {
      const x = this.xAt(i, n);
      const anchor = i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle';
      return svg`<text x=${x} y=${y} text-anchor=${anchor}>${t}</text>`;
    });
    return svg`<g class="axis">${ticks}</g>`;
  }

  // ---- Líneas / áreas ----
  private renderLines(): unknown {
    const fillArea = this.type === 'area';
    const parts: unknown[] = [];
    (this.series ?? []).forEach((s, si) => {
      const data = s.data ?? [];
      const n = data.length;
      if (!n) return;
      const color = this.seriesColor(s);
      const pts = data.map((v, i) => `${this.xAt(i, n)},${this.yAt(v)}`);
      const linePath = `M${pts.join(' L')}`;

      // Área con degradado (solo en type=area y series no punteadas).
      if (fillArea && !s.dashed) {
        const baseY = this.pad.top + this.plotH;
        const x0 = this.xAt(0, n);
        const xEnd = this.xAt(n - 1, n);
        const areaPath = `${linePath} L${xEnd},${baseY} L${x0},${baseY} Z`;
        const gid = `ok-chart-grad-${si}`;
        parts.push(svg`
          <defs>
            <linearGradient id=${gid} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stop-color=${color} stop-opacity="0.5" />
              <stop offset="100%" stop-color=${color} stop-opacity="0" />
            </linearGradient>
          </defs>
          <path d=${areaPath} fill=${`url(#${gid})`} stroke="none" />
        `);
      }

      parts.push(svg`<path
        d=${linePath}
        fill="none"
        stroke=${color}
        stroke-width=${s.dashed ? 1.5 : 2}
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-dasharray=${s.dashed ? '4 4' : ''}
      />`);

      // Endpoint dot + etiqueta de valor (solo primera serie no punteada).
      if (this.endpoint && si === 0 && n) {
        const lastX = this.xAt(n - 1, n);
        const lastY = this.yAt(data[n - 1]);
        const label = this.endpointLabel || String(data[n - 1]);
        parts.push(svg`
          <circle cx=${lastX} cy=${lastY} r="4" fill=${color}
            stroke="var(--surface)" stroke-width="2" />
          <text class="value-label" x=${lastX + 10} y=${lastY + 3}>${label}</text>
        `);
      }
    });
    return svg`${parts}`;
  }

  // ---- Barras agrupadas (rounded rx=2, soporte mute por serie) ----
  private renderBars(): unknown {
    const series = this.series ?? [];
    const groups = Math.max(...series.map((s) => s.data?.length ?? 0), 0);
    if (!groups) return svg``;
    const p = this.pad;
    const baseY = this.yAt(this.bounds.min < 0 ? 0 : this.bounds.min);
    const groupW = this.plotW / groups;
    const innerGap = 0.28; // hueco entre grupos
    const usable = groupW * (1 - innerGap);
    const nSeries = series.length || 1;
    const barW = Math.max(usable / nSeries, 1);

    const rects: unknown[] = [];
    for (let g = 0; g < groups; g++) {
      series.forEach((s, si) => {
        const v = s.data?.[g];
        if (v == null) return;
        const x = p.left + g * groupW + (groupW - usable) / 2 + si * barW;
        const y = this.yAt(v);
        const top = Math.min(y, baseY);
        const h = Math.max(Math.abs(baseY - y), 0.5);
        const color = this.seriesColor(s);
        rects.push(svg`<rect
          x=${x + 0.5}
          y=${top}
          width=${Math.max(barW - 1, 1)}
          height=${h}
          rx="2"
          fill=${color}
        />`);
      });
    }
    return svg`<g>${rects}</g>`;
  }

  // ---- Leyenda (si alguna serie tiene nombre) ----
  private renderLegend(): unknown {
    const items = (this.series ?? []).filter((s) => s.name);
    if (!items.length) return null;
    return html`<div class="legend">
      ${items.map(
        (s) => html`<span class="legend-item">
          <span
            class=${s.dashed ? 'legend-dot dashed' : 'legend-dot'}
            style=${`background:${this.seriesColor(s)}`}
          ></span>
          ${s.name}
        </span>`,
      )}
    </div>`;
  }

  render(): unknown {
    const body =
      this.type === 'bar' ? this.renderBars() : this.renderLines();
    return html`
      <div class="chart">
        <svg
          viewBox=${`0 0 ${this.vbWidth} ${this.vbHeight}`}
          style=${`height:${this.height}px`}
          preserveAspectRatio="none"
          role="img"
          aria-label=${(this.series ?? []).map((s) => s.name).filter(Boolean).join(', ') ||
          'chart'}
        >
          ${this.renderGrid()} ${this.renderValueAxis()} ${this.renderXLabels()} ${body}
        </svg>
        ${this.renderLegend()}
      </div>
    `;
  }
}

define('ok-chart', OkChart);

declare global {
  interface HTMLElementTagNameMap {
    'ok-chart': OkChart;
  }
}
