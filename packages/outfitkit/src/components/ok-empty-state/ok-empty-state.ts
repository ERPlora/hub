import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-empty-state — estado vacío centrado (sin datos, sin resultados, etc.).
// Icono grande atenuado + título + mensaje muted + acción opcional.
// Slots: default (contenido extra), `action` (típicamente un ok-button).
export class OkEmptyState extends LitElement {
  static styles = css`
    /* Ancho máximo del contenedor; bloque a 100%. */
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --icon-color: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --heading-color: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --message-color: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --icon-size: 64px;
      --padding: 2.5rem 1.25rem;
    }

    /* Centrado vertical y horizontal del contenido. */
    .wrap {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      gap: 0.5rem;
      padding: var(--padding);
      box-sizing: border-box;
      width: 100%;
    }

    ion-icon {
      font-size: var(--icon-size);
      color: var(--icon-color);
      opacity: 0.5; /* atenuado */
      margin-bottom: 0.25rem;
    }

    .heading {
      margin: 0;
      font-size: 1.125rem;
      font-weight: 600;
      color: var(--heading-color);
    }

    .message {
      margin: 0;
      font-size: 0.9375rem;
      color: var(--message-color);
      max-width: 38ch;
    }

    /* Acción debajo del texto. */
    .action {
      margin-top: 1rem;
    }

    /* Oculta los wrappers si no hay contenido. */
    .heading:empty,
    .message:empty {
      display: none;
    }
  `;

  /** Nombre de un ion-icon (def 'file-tray-outline'). */
  @property() icon = 'file-tray-outline';

  /** Título principal del estado vacío. */
  @property() heading?: string;

  /** Mensaje secundario (muted). */
  @property() message?: string;

  render(): unknown {
    return html`
      <div class="wrap">
        <ion-icon name=${this.icon} aria-hidden="true"></ion-icon>
        ${this.heading ? html`<h2 class="heading">${this.heading}</h2>` : null}
        ${this.message ? html`<p class="message">${this.message}</p>` : null}
        <slot></slot>
        <div class="action">
          <slot name="action"></slot>
        </div>
      </div>
    `;
  }
}

define('ok-empty-state', OkEmptyState);

declare global {
  interface HTMLElementTagNameMap {
    'ok-empty-state': OkEmptyState;
  }
}
