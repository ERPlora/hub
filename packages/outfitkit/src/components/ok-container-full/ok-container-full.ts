import { LitElement, html, css } from 'lit';
import { define } from '../../base/define.js';

// ok-container-full — full-bleed con padding lateral (estilo bootstrap `.container-fluid`).
// Para secciones a todo el ancho (hero de fondo, bandas de color). Var overridable: --padding.
export class OkContainerFull extends LitElement {
  static styles = css`
    :host {
      display: block;
      --padding: var(--ok-spacing, var(--ion-padding, 16px));
    }
    .c {
      width: 100%;
      padding-inline: var(--padding);
      box-sizing: border-box;
    }
  `;

  render(): unknown {
    return html`<div class="c"><slot></slot></div>`;
  }
}

define('ok-container-full', OkContainerFull);

declare global {
  interface HTMLElementTagNameMap {
    'ok-container-full': OkContainerFull;
  }
}
