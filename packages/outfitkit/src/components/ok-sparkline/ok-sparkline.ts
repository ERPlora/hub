import { LitElement, html, css, svg } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-sparkline — mini-gráfico inline en SVG (sin ejes, sin librerías de charts).
// AUTOCONTENIDO y CSP-safe: dibuja el SVG a mano (polyline/área o barras) escalando los valores
// a su min/max. Pensado para incrustarse en línea de texto, celdas de tabla o tarjetas KPI.
//   • prop `.values`  → number[] (los datos; se aporta desde JS asignando la propiedad)
//   • prop `type`     → 'line' | 'bar' (def 'line')
//   • prop `color`    → color del trazo/relleno (def --ok-primary → --ion-color-primary)
//   • prop `width`    → ancho del SVG en px (def 120)
//   • prop `height`   → alto del SVG en px (def 32)
//   • prop `filled`   → en 'line', pinta el área bajo la línea (def false)
// Es puramente presentacional: no emite eventos.
export class OkSparkline extends LitElement {
  static styles = css`
    :host {
      /* Color por defecto: cadena --ok-* → --ion-* → hex. */
      --color: var(--ok-primary, var(--ion-color-primary, #3880ff));

      /* Sparkline = inline, fluye con el texto. */
      display: inline-block;
      line-height: 0;
      vertical-align: middle;
    }
    svg {
      display: block;
      overflow: visible;
    }
  `;

  /** Serie de datos a representar. */
  @property({ attribute: false }) values: number[] = [];
  /** Tipo de gráfico: línea o barras. */
  @property() type: 'line' | 'bar' = 'line';
  /** Color del trazo/relleno; cae al token del componente si no se da. */
  @property() color = '';
  /** Ancho del SVG en px. */
  @property({ type: Number }) width = 120;
  /** Alto del SVG en px. */
  @property({ type: Number }) height = 32;
  /** En modo línea, rellena el área bajo la curva. */
  @property({ type: Boolean }) filled = false;

  // Padding interno para que el trazo no se recorte en los bordes.
  private get pad(): number {
    return 2;
  }

  // Color efectivo: prop explícita o el token del componente (--color).
  private get stroke(): string {
    return this.color || 'var(--color)';
  }

  // Mapea cada valor a coordenadas {x, y} dentro del área útil del SVG.
  private points(): Array<{ x: number; y: number }> {
    const data = this.values ?? [];
    const n = data.length;
    if (!n) return [];
    const pad = this.pad;
    const w = this.width - pad * 2;
    const h = this.height - pad * 2;
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1; // evita división por cero (serie plana)
    // Con un solo punto, lo centramos.
    const step = n > 1 ? w / (n - 1) : 0;
    return data.map((value, i) => {
      const x = n > 1 ? pad + i * step : pad + w / 2;
      // Y invertida: valores altos arriba.
      const y = pad + (1 - (value - min) / range) * h;
      return { x, y };
    });
  }

  // Render de la serie como línea (polyline) + área opcional.
  private renderLine(): unknown {
    const pts = this.points();
    if (pts.length < 2) {
      // Con 0 o 1 punto no hay línea; pinta un punto si lo hay.
      return pts.length === 1
        ? svg`<circle cx=${pts[0].x} cy=${pts[0].y} r="2" fill=${this.stroke} />`
        : svg``;
    }
    const line = pts.map((p) => `${p.x},${p.y}`).join(' ');
    const baseY = this.height - this.pad;
    const area = `${pts[0].x},${baseY} ${line} ${pts[pts.length - 1].x},${baseY}`;
    return svg`
      ${this.filled
        ? svg`<polygon points=${area} fill=${this.stroke} fill-opacity="0.15" stroke="none" />`
        : svg``}
      <polyline
        points=${line}
        fill="none"
        stroke=${this.stroke}
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    `;
  }

  // Render de la serie como barras escaladas a min/max.
  private renderBars(): unknown {
    const data = this.values ?? [];
    const n = data.length;
    if (!n) return svg``;
    const pad = this.pad;
    const w = this.width - pad * 2;
    const h = this.height - pad * 2;
    const min = Math.min(...data, 0); // incluye 0 para que las barras crezcan desde la base
    const max = Math.max(...data);
    const range = max - min || 1;
    const slot = w / n;
    const gap = slot * 0.25;
    const barW = Math.max(slot - gap, 1);
    const baseY = this.height - pad;
    return data.map((value, i) => {
      const barH = ((value - min) / range) * h;
      const x = pad + i * slot + gap / 2;
      const y = baseY - barH;
      return svg`<rect
        x=${x}
        y=${y}
        width=${barW}
        height=${Math.max(barH, 0.5)}
        rx="1"
        fill=${this.stroke}
      />`;
    });
  }

  render(): unknown {
    return html`<svg
      width=${this.width}
      height=${this.height}
      viewBox=${`0 0 ${this.width} ${this.height}`}
      preserveAspectRatio="none"
      role="img"
      aria-hidden="true"
    >
      ${this.type === 'bar' ? this.renderBars() : this.renderLine()}
    </svg>`;
  }
}

define('ok-sparkline', OkSparkline);

declare global {
  interface HTMLElementTagNameMap {
    'ok-sparkline': OkSparkline;
  }
}
