import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-kpi — tarjeta KPI para dashboards: label (muted) + value (grande) + delta con color y flecha.
// Slot default opcional (p.ej. una sparkline) bajo el valor.
type OkKpiTrend = 'up' | 'down' | 'flat';

export class OkKpi extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --background: var(--ok-card-background, var(--ion-card-background, var(--ion-background-color, #ffffff)));
      --color: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --label-color: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --border-color: var(--ok-border-color, var(--ion-border-color, rgba(0, 0, 0, 0.08)));
      --border-radius: var(--ok-radius, 12px);
      --box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.04);
      --padding: 1rem 1.125rem;
      /* Colores de tendencia. */
      --trend-up-color: var(--ok-color-success, var(--ion-color-success, #2dd36f));
      --trend-down-color: var(--ok-color-danger, var(--ion-color-danger, #eb445a));
      --trend-flat-color: var(--ok-color-medium, var(--ion-color-medium, #92949c));
    }

    .card {
      box-sizing: border-box;
      width: 100%;
      background: var(--background);
      color: var(--color);
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
      box-shadow: var(--box-shadow);
      padding: var(--padding);
      display: flex;
      flex-direction: column;
      gap: 0.375rem;
    }

    /* Fila superior: label + icono opcional. */
    .top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
    }

    .label {
      margin: 0;
      font-size: 0.6875rem;
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: var(--label-color);
    }

    .label-icon {
      font-size: 1.25rem;
      color: var(--label-color);
      flex: 0 0 auto;
    }

    .value {
      margin: 0;
      font-size: 1.75rem;
      font-weight: 700;
      line-height: 1.1;
    }

    /* Delta: flecha + texto, coloreado según tendencia. */
    .delta {
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      font-size: 0.8125rem;
      font-weight: 600;
    }
    .delta ion-icon {
      font-size: 1rem;
    }
    .delta.up {
      color: var(--trend-up-color);
    }
    .delta.down {
      color: var(--trend-down-color);
    }
    .delta.flat {
      color: var(--trend-flat-color);
    }

    ::slotted(*) {
      margin-top: 0.25rem;
    }
  `;

  /** Etiqueta (muted, uppercase). */
  @property() label?: string;

  /** Valor principal (grande, bold). */
  @property() value?: string;

  /** Variación, p.ej. '+12%'. */
  @property() delta?: string;

  /** Tendencia: 'up' | 'down' | 'flat'. Controla color y flecha del delta. */
  @property() trend: OkKpiTrend = 'flat';

  /** Nombre de un ion-icon opcional mostrado junto al label. */
  @property() icon?: string;

  /** Devuelve el ion-icon de flecha según la tendencia. */
  private trendIcon(): string {
    if (this.trend === 'up') return 'trending-up';
    if (this.trend === 'down') return 'trending-down';
    return 'remove';
  }

  render(): unknown {
    return html`
      <div class="card">
        <div class="top">
          ${this.label ? html`<p class="label">${this.label}</p>` : null}
          ${this.icon ? html`<ion-icon class="label-icon" name=${this.icon} aria-hidden="true"></ion-icon>` : null}
        </div>
        ${this.value ? html`<p class="value">${this.value}</p>` : null}
        ${this.delta
          ? html`<span class="delta ${this.trend}">
              <ion-icon name=${this.trendIcon()} aria-hidden="true"></ion-icon>${this.delta}
            </span>`
          : null}
        <slot></slot>
      </div>
    `;
  }
}

define('ok-kpi', OkKpi);

declare global {
  interface HTMLElementTagNameMap {
    'ok-kpi': OkKpi;
  }
}
