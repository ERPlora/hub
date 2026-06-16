import { LitElement, html, css, svg } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-donut — gráfico de proporción donut/pie (lo que Ionic no trae), dibujado a mano en SVG.
// AUTOCONTENIDO y CSP-safe: apila círculos con stroke-dasharray/dashoffset sobre un track,
// rotados -90deg para arrancar arriba; cada slice anima su dasharray. El centro muestra un
// valor grande + label en mayúsculas. La leyenda lista filas: cuadradito de color + nombre +
// porcentaje (calculado) en negrita a la derecha.
//   • prop `.slices`      → OkDonutSlice[] {label, value, color?}
//   • prop `size`         → diámetro del SVG en px (def 140)
//   • prop `thickness`    → grosor del anillo en px (def 16); 0 ⇒ pie (círculo macizo)
//   • prop `center-label` → texto en mayúsculas bajo el valor central
//   • prop `center-value` → valor grande central (si no se da, no se pinta texto central)
//   • prop `legend`       → muestra la leyenda (def true)
//   • prop `legend-side`  → 'side' (a la derecha) | 'bottom' (debajo)  (def 'side')
// Es puramente presentacional: no emite eventos.

/** Un segmento del donut. */
export interface OkDonutSlice {
  /** Nombre del segmento (se muestra en la leyenda). */
  label: string;
  /** Valor numérico; el porcentaje se calcula sobre el total. */
  value: number;
  /** Color del segmento; si falta, cae a la paleta por defecto por índice. */
  color?: string;
}

// Paleta por defecto cuando un slice no trae color (cadena --ok-* → --ion-* → hex).
const DEFAULT_PALETTE = [
  'var(--ok-primary, var(--ion-color-primary, #3880ff))',
  'var(--ok-success, var(--ion-color-success, #2dd36f))',
  'var(--ok-warning, var(--ion-color-warning, #ffc409))',
  'var(--ok-tertiary, var(--ion-color-tertiary, #5260ff))',
  'var(--ok-danger, var(--ion-color-danger, #eb445a))',
  'var(--ok-secondary, var(--ion-color-secondary, #3dc2ff))',
];

export class OkDonut extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      box-sizing: border-box;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --value-color: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --label-color: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --track-color: var(--ok-donut-track, var(--ion-color-step-100, #ebedf0));
      --legend-color: var(--ok-color-medium-shade, var(--ion-color-medium-shade, #808289));
    }

    .donut {
      display: grid;
      gap: 18px;
      align-items: center;
    }
    /* Leyenda al lado: SVG de ancho fijo + leyenda flexible. */
    .donut.side {
      grid-template-columns: auto 1fr;
    }
    /* Leyenda abajo: una sola columna, todo centrado. */
    .donut.bottom {
      grid-template-columns: 1fr;
      justify-items: center;
    }

    svg {
      display: block;
    }

    .track {
      fill: none;
      stroke: var(--track-color);
    }
    .slice {
      fill: none;
      transform: rotate(-90deg);
      transform-origin: center;
      /* Animación al cambiar proporciones (mismo espíritu que el CSS original). */
      transition: stroke-dasharray 0.6s cubic-bezier(0.22, 1, 0.36, 1);
    }
    /* Modo pie: el segmento se rellena en vez de trazarse. */
    .pie {
      stroke: none;
      transform: rotate(-90deg);
      transform-origin: center;
    }

    .center-value {
      fill: var(--value-color);
      text-anchor: middle;
      font-weight: 700;
      letter-spacing: -0.04em;
    }
    .center-label {
      fill: var(--label-color);
      text-anchor: middle;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }

    .legend {
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 12px;
      width: 100%;
    }
    .legend-row {
      display: grid;
      grid-template-columns: 10px 1fr auto;
      gap: 8px;
      align-items: center;
      color: var(--legend-color);
    }
    .legend-dot {
      width: 10px;
      height: 10px;
      border-radius: 3px;
    }
    .legend-pct {
      color: var(--value-color);
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }
  `;

  /** Segmentos a representar. Se aporta asignando la propiedad desde JS. */
  @property({ attribute: false }) slices: OkDonutSlice[] = [];
  /** Diámetro del SVG en px. */
  @property({ type: Number }) size = 140;
  /** Grosor del anillo en px; 0 ⇒ pie macizo. */
  @property({ type: Number }) thickness = 16;
  /** Texto en mayúsculas bajo el valor central. */
  @property({ attribute: 'center-label' }) centerLabel = '';
  /** Valor grande central; si está vacío no se pinta texto central. */
  @property({ attribute: 'center-value' }) centerValue = '';
  /** Muestra la leyenda. */
  @property({ type: Boolean }) legend = true;
  /** Posición de la leyenda. */
  @property({ attribute: 'legend-side' }) legendSide: 'side' | 'bottom' = 'side';

  // Total de los valores (sin negativos), con guarda contra 0.
  private get total(): number {
    const sum = (this.slices ?? []).reduce(
      (acc, s) => acc + Math.max(0, s.value || 0),
      0,
    );
    return sum;
  }

  // Color efectivo de un slice (su color o el de la paleta por índice).
  private colorAt(slice: OkDonutSlice, i: number): string {
    return slice.color || DEFAULT_PALETTE[i % DEFAULT_PALETTE.length];
  }

  // Porcentaje (0–100) de un slice sobre el total.
  private pct(value: number): number {
    const total = this.total;
    if (total <= 0) return 0;
    return (Math.max(0, value) / total) * 100;
  }

  // Dibuja el donut (anillos trazados) o el pie (cuñas macizas) según thickness.
  private renderChart(): unknown {
    const size = this.size;
    const cx = size / 2;
    const cy = size / 2;
    const isPie = this.thickness <= 0;
    const total = this.total;
    const slices = this.slices ?? [];

    // Radio del trazo: en donut, dejamos el grosor centrado en el borde.
    const stroke = isPie ? 0 : this.thickness;
    const r = isPie ? size / 2 : (size - stroke) / 2;
    const circumference = 2 * Math.PI * r;

    // Pie: cuñas macizas con conic-like usando stroke grueso = radio (truco clásico).
    // Para mantenerlo SVG-puro y CSP-safe, dibujamos el pie como anillo de grosor = radio,
    // de modo que el "agujero" desaparece y se ve macizo.
    const pieStroke = size / 2;
    const pieR = size / 4;
    const pieCircumference = 2 * Math.PI * pieR;

    let offset = 0; // acumulado para encadenar segmentos (dashoffset negativo).
    const segments = slices.map((s, i) => {
      const fraction = total > 0 ? Math.max(0, s.value) / total : 0;
      const dash = fraction * (isPie ? pieCircumference : circumference);
      const dashoffset = -offset;
      offset += dash;
      const color = this.colorAt(s, i);
      if (isPie) {
        return svg`<circle
          class="pie"
          cx=${cx}
          cy=${cy}
          r=${pieR}
          fill="none"
          stroke=${color}
          stroke-width=${pieStroke}
          stroke-dasharray=${`${dash} ${pieCircumference}`}
          stroke-dashoffset=${dashoffset}
        />`;
      }
      return svg`<circle
        class="slice"
        cx=${cx}
        cy=${cy}
        r=${r}
        stroke=${color}
        stroke-width=${stroke}
        stroke-dasharray=${`${dash} ${circumference}`}
        stroke-dashoffset=${dashoffset}
        stroke-linecap="butt"
      />`;
    });

    // Tamaños de texto central proporcionales al diámetro.
    const valueSize = Math.max(14, Math.round(size * 0.16));
    const labelSize = Math.max(8, Math.round(size * 0.065));
    const showCenter = !isPie && (this.centerValue || this.centerLabel);

    return svg`
      ${!isPie
        ? svg`<circle
            class="track"
            cx=${cx}
            cy=${cy}
            r=${r}
            stroke-width=${stroke}
          />`
        : svg``}
      ${segments}
      ${showCenter
        ? svg`
          ${this.centerValue
            ? svg`<text
                class="center-value"
                x=${cx}
                y=${this.centerLabel ? cy + valueSize * 0.05 : cy + valueSize * 0.35}
                font-size=${valueSize}
              >${this.centerValue}</text>`
            : svg``}
          ${this.centerLabel
            ? svg`<text
                class="center-label"
                x=${cx}
                y=${this.centerValue ? cy + valueSize * 0.7 : cy + labelSize * 0.35}
                font-size=${labelSize}
              >${this.centerLabel}</text>`
            : svg``}
        `
        : svg``}
    `;
  }

  // Filas de leyenda: cuadradito de color + nombre + porcentaje calculado.
  private renderLegend(): unknown {
    const slices = this.slices ?? [];
    if (!this.legend || slices.length === 0) return null;
    return html`
      <div class="legend" role="list">
        ${slices.map((s, i) => {
          const pct = this.pct(s.value);
          return html`
            <div class="legend-row" role="listitem">
              <span
                class="legend-dot"
                style=${`background:${this.colorAt(s, i)}`}
              ></span>
              <span>${s.label}</span>
              <span class="legend-pct">${Math.round(pct)}%</span>
            </div>
          `;
        })}
      </div>
    `;
  }

  render(): unknown {
    const size = this.size;
    const showLegend = this.legend && (this.slices ?? []).length > 0;
    const side = this.legendSide === 'bottom' ? 'bottom' : 'side';
    // Descripción accesible del gráfico para lectores de pantalla.
    const ariaLabel = (this.slices ?? [])
      .map((s) => `${s.label}: ${Math.round(this.pct(s.value))}%`)
      .join(', ');

    return html`
      <div class=${`donut ${showLegend ? side : 'bottom'}`}>
        <svg
          width=${size}
          height=${size}
          viewBox=${`0 0 ${size} ${size}`}
          role="img"
          aria-label=${ariaLabel || 'donut chart'}
        >
          ${this.renderChart()}
        </svg>
        ${showLegend ? this.renderLegend() : null}
      </div>
    `;
  }
}

define('ok-donut', OkDonut);

declare global {
  interface HTMLElementTagNameMap {
    'ok-donut': OkDonut;
  }
}
