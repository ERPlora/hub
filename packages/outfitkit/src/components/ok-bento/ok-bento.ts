import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-bento — rejilla "bento" modular (tendencia 2026): contenedor de celdas de tamaños
// variados. Las celdas son <ok-bento-item> (o cualquier elemento con grid-column/row).
// En móvil colapsa a 1 columna automáticamente.
//
//   <ok-bento cols="6" gap="1rem">
//     <ok-bento-item cols="4" rows="2" glass> … </ok-bento-item>
//     <ok-bento-item cols="2"> … </ok-bento-item>
//   </ok-bento>
export class OkBento extends LitElement {
  static styles = css`
    :host {
      display: grid;
      width: 100%;
      grid-template-columns: repeat(var(--cols, 6), minmax(0, 1fr));
      grid-auto-rows: var(--row-height, minmax(120px, auto));
      gap: var(--gap, 1rem);
    }
    @media (max-width: 900px) {
      :host {
        grid-template-columns: repeat(var(--cols-md, 4), minmax(0, 1fr));
      }
    }
    @media (max-width: 560px) {
      :host {
        grid-template-columns: 1fr;
        grid-auto-rows: auto;
      }
    }
  `;

  /** Nº de columnas de la rejilla en escritorio (def 6). */
  @property({ type: Number }) cols = 6;
  /** Nº de columnas en tablet (≤900px, def 4). */
  @property({ type: Number, attribute: 'cols-md' }) colsMd = 4;
  /** Separación entre celdas (CSS length, def 1rem). */
  @property() gap = '1rem';

  updated(): void {
    this.style.setProperty('--cols', String(this.cols));
    this.style.setProperty('--cols-md', String(this.colsMd));
    this.style.setProperty('--gap', this.gap);
  }

  render(): unknown {
    return html`<slot></slot>`;
  }
}

define('ok-bento', OkBento);

declare global {
  interface HTMLElementTagNameMap {
    'ok-bento': OkBento;
  }
}
