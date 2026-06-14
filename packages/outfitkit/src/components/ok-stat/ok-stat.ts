import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-stat — métrica inline simple y compacta (más ligera que ok-kpi).
// Útil en filas de stats: label muted arriba, value destacado, hint muted opcional debajo.
export class OkStat extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --color: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --label-color: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --hint-color: var(--ok-color-medium, var(--ion-color-medium, #92949c));
    }

    .stat {
      display: flex;
      flex-direction: column;
      gap: 0.125rem;
      width: 100%;
      box-sizing: border-box;
    }

    .label {
      margin: 0;
      font-size: 0.75rem;
      font-weight: 500;
      color: var(--label-color);
    }

    .value {
      margin: 0;
      font-size: 1.25rem;
      font-weight: 700;
      line-height: 1.15;
      color: var(--color);
    }

    .hint {
      margin: 0;
      font-size: 0.75rem;
      color: var(--hint-color);
    }
  `;

  /** Etiqueta de la métrica (muted). */
  @property() label?: string;

  /** Valor de la métrica. */
  @property() value?: string;

  /** Texto secundario opcional (muted) bajo el valor. */
  @property() hint?: string;

  render(): unknown {
    return html`
      <div class="stat">
        ${this.label ? html`<p class="label">${this.label}</p>` : null}
        ${this.value ? html`<p class="value">${this.value}</p>` : null}
        ${this.hint ? html`<p class="hint">${this.hint}</p>` : null}
      </div>
    `;
  }
}

define('ok-stat', OkStat);

declare global {
  interface HTMLElementTagNameMap {
    'ok-stat': OkStat;
  }
}
