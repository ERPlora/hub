import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-funnel — embudo de conversión. Filas apiladas; cada una es un grid de 2
// columnas (barra / meta). La barra mide 32px de alto con gradiente horizontal
// brand→color-mix, ancho % decreciente según el valor relativo al primer paso,
// y la etiqueta dentro en brand-fg. La meta muestra el conteo absoluto en
// negrita y el % de conversión por-paso (auto, respecto al paso anterior).
// Reproduce el diseño de la antigua .ux-funnel (charts.css).

/** Variante de color de una barra del embudo. */
export type OkFunnelColor = 'brand' | 'leaf' | 'warn' | 'mute';

/** Un paso/etapa del embudo de conversión. */
export interface OkFunnelStep {
  /** Etiqueta visible dentro de la barra. */
  label: string;
  /** Valor absoluto de la etapa (usado para anchura y meta). */
  value: number;
  /** Variante de color opcional. */
  color?: OkFunnelColor;
}

export class OkFunnel extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --brand: var(--ok-color-primary, var(--ion-color-primary, #0091ce));
      --brand-fg: var(
        --ok-color-primary-contrast,
        var(--ion-color-primary-contrast, #ffffff)
      );
      --leaf: var(--ok-color-success, var(--ion-color-success, #2dd36f));
      --leaf-fg: var(
        --ok-color-success-contrast,
        var(--ion-color-success-contrast, #ffffff)
      );
      --warn: var(--ok-color-warning, var(--ion-color-warning, #ffc409));
      --warn-fg: var(
        --ok-color-warning-contrast,
        var(--ion-color-warning-contrast, #1f2933)
      );
      --bg-3: var(--ok-color-step-150, var(--ion-color-step-150, #e6e8ec));
      --ink: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --ink-2: var(--ok-color-medium, var(--ion-color-medium, #6b7280));
      --ink-3: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --radius: var(--ok-border-radius, var(--ion-border-radius, 6px));
    }

    .funnel {
      display: flex;
      flex-direction: column;
      gap: 4px;
      width: 100%;
      box-sizing: border-box;
    }

    .step {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: center;
    }

    .bar {
      height: 32px;
      box-sizing: border-box;
      background: linear-gradient(
        90deg,
        var(--brand),
        color-mix(in oklch, var(--brand) 60%, var(--bg-3))
      );
      border-radius: var(--radius);
      display: flex;
      align-items: center;
      padding: 0 12px;
      color: var(--brand-fg);
      font-size: 12px;
      font-weight: 500;
      min-width: 0;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
      transition: width 0.25s ease;
    }

    .bar--leaf {
      background: linear-gradient(
        90deg,
        var(--leaf),
        color-mix(in oklch, var(--leaf) 60%, var(--bg-3))
      );
      color: var(--leaf-fg);
    }

    .bar--warn {
      background: linear-gradient(
        90deg,
        var(--warn),
        color-mix(in oklch, var(--warn) 60%, var(--bg-3))
      );
      color: var(--warn-fg);
    }

    .bar--mute {
      background: var(--bg-3);
      color: var(--ink-2);
    }

    .meta {
      font-size: 11.5px;
      color: var(--ink-3);
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }

    .meta b {
      color: var(--ink);
      font-weight: 600;
    }
  `;

  /** Pasos del embudo (de mayor a menor por convención). */
  @property({ attribute: false }) steps: OkFunnelStep[] = [];

  /** Locale para formatear números (default: del navegador). */
  @property() locale?: string;

  /** Anchura mínima de barra en % para que la etiqueta siga siendo legible. */
  @property({ type: Number, attribute: 'min-width' }) minWidth = 12;

  /** Formatea un número absoluto con separadores de miles. */
  private fmtCount(n: number): string {
    return new Intl.NumberFormat(this.locale).format(n);
  }

  /** Formatea un porcentaje con un decimal. */
  private fmtPct(n: number): string {
    return new Intl.NumberFormat(this.locale, {
      maximumFractionDigits: 1,
    }).format(n);
  }

  render(): unknown {
    const steps = this.steps ?? [];
    // El primer paso (mayor valor) define el 100% de anchura.
    const top = steps.length ? steps[0].value : 0;

    return html`
      <div
        class="funnel"
        role="list"
        aria-label="Embudo de conversión"
      >
        ${steps.map((s, i) => {
          // Anchura proporcional al valor relativo al primer paso (acotada).
          const ratio = top > 0 ? s.value / top : 0;
          const width = Math.max(this.minWidth, Math.round(ratio * 100));
          // % global respecto al primer paso.
          const globalPct = top > 0 ? (s.value / top) * 100 : 0;
          // % de conversión por-paso: respecto al paso anterior.
          const prev = i > 0 ? steps[i - 1].value : s.value;
          const stepPct = prev > 0 ? (s.value / prev) * 100 : 0;
          const variant = s.color ?? 'brand';
          const cls =
            variant === 'brand' ? 'bar' : `bar bar--${variant}`;

          return html`
            <div
              class="step"
              role="listitem"
              aria-label=${`${s.label}: ${this.fmtCount(
                s.value,
              )} (${this.fmtPct(globalPct)}%)`}
            >
              <div class=${cls} style=${`width:${width}%`} title=${s.label}>
                ${s.label}
              </div>
              <span class="meta">
                <b>${this.fmtCount(s.value)}</b> ·
                ${i === 0
                  ? `${this.fmtPct(globalPct)}%`
                  : `${this.fmtPct(stepPct)}%`}
              </span>
            </div>
          `;
        })}
      </div>
    `;
  }
}

define('ok-funnel', OkFunnel);

declare global {
  interface HTMLElementTagNameMap {
    'ok-funnel': OkFunnel;
  }
}
