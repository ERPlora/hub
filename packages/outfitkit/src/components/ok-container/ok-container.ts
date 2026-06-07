import { LitElement, html, css } from 'lit';
import { define } from '../../base/define.js';

// ok-container — ancho máximo centrado (estilo bootstrap `.container`). Contenido por slot
// (light DOM → crawlable para SEO). Vars overridable (estilo Ionic): --max-width, --padding.
export class OkContainer extends LitElement {
  static styles = css`
    :host {
      display: block;
      --max-width: var(--ok-container-max, 1140px);
      --padding: var(--ok-spacing, var(--ion-padding, 16px));
    }
    .c {
      max-width: var(--max-width);
      margin-inline: auto;
      padding-inline: var(--padding);
      width: 100%;
      box-sizing: border-box;
    }
  `;

  render(): unknown {
    return html`<div class="c"><slot></slot></div>`;
  }
}

define('ok-container', OkContainer);

declare global {
  interface HTMLElementTagNameMap {
    'ok-container': OkContainer;
  }
}
