import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-inline-feedback — banner/callout persistente en el flujo del contenido (el hueco que Ionic
// no cubre: ion-toast/ion-alert son efímeros/modales, no un aviso embebido y persistente).
// Estilo Bootstrap "alert" / Tailwind "callout". Slots:
//   • slot (default)  → mensaje/cuerpo
//   • slot="actions"  → botones de acción (a la derecha; bajan en móvil)
// Layout: [icono] | (heading + mensaje + actions) [· cerrar]. Atributos: `tone`, `heading`,
// `icon`, `dismissible`. Emite `ok-dismiss` (bubbles+composed) al cerrar.
export type OkInlineFeedbackTone = 'info' | 'success' | 'warning' | 'danger' | 'neutral';

// Textos traducibles (default inglés). Pásalos desde fuera vía la prop `labels`.
export interface OkInlineFeedbackLabels {
  /** aria-label del botón de cierre. */
  dismiss: string;
}

const DEFAULT_LABELS: OkInlineFeedbackLabels = {
  dismiss: 'Dismiss',
};

export class OkInlineFeedback extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex.
         --tone-color y --tone-icon se reasignan por tone abajo. */
      --tone-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --background-opacity: 0.1;
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --border-radius: var(--ok-radius, var(--ion-border-radius, 8px));
      --padding: var(--ok-spacing, var(--ion-padding, 16px));
      --accent-width: 4px;
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* Responsive: el banner ocupa el ancho del contenedor. */
      display: block;
      width: 100%;
      font-family: var(--font);
      box-sizing: border-box;
    }
    :host([hidden]) { display: none; }

    /* Mapa de tonos → color Ionic + icono por defecto. */
    :host([tone='success']) { --tone-color: var(--ok-success, var(--ion-color-success, #2dd55b)); }
    :host([tone='warning']) { --tone-color: var(--ok-warning, var(--ion-color-warning, #ffc409)); }
    :host([tone='danger'])  { --tone-color: var(--ok-danger, var(--ion-color-danger, #c5000f)); }
    :host([tone='neutral']) { --tone-color: var(--ok-medium, var(--ion-color-medium, #5f5f5f)); }
    /* info / sin tono → primary (default ya aplicado en :host). */

    .box {
      position: relative;
      display: flex;
      align-items: flex-start;
      gap: 0.75rem;
      padding: var(--padding);
      border-radius: var(--border-radius);
      border-inline-start: var(--accent-width) solid var(--tone-color);
      /* Fondo tonal: el color del tono con baja opacidad (color-mix con fallback al borde fino). */
      background: color-mix(in srgb, var(--tone-color) calc(var(--background-opacity) * 100%), transparent);
      color: var(--color);
    }

    .icon {
      flex: 0 0 auto;
      font-size: 1.4rem;
      line-height: 1;
      color: var(--tone-color);
      margin-top: 0.05rem;
    }

    .content {
      flex: 1 1 auto;
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }
    .row {
      display: flex;
      align-items: flex-start;
      gap: 1rem;
    }
    .text {
      flex: 1 1 auto;
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 0.2rem;
    }
    .heading {
      font-weight: 700;
      font-size: 0.98rem;
      line-height: 1.3;
    }
    .body {
      font-size: 0.92rem;
      line-height: 1.45;
    }
    .actions {
      flex: 0 0 auto;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    /* Si no hay actions, el slot queda vacío y no ocupa espacio. */
    .actions.empty { display: none; }

    .close {
      flex: 0 0 auto;
      background: none;
      border: 0;
      cursor: pointer;
      padding: 0.15rem;
      margin: -0.15rem -0.15rem 0 0;
      color: inherit;
      opacity: 0.6;
      font-size: 1.2rem;
      line-height: 1;
      border-radius: 4px;
      transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease), box-shadow var(--ok-transition, 150ms ease),
        opacity 0.15s ease, transform 120ms ease;
    }
    @media (hover: hover) {
      .close:hover { opacity: 1; background: rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.07); }
    }
    .close:active { transform: scale(var(--ok-press-scale, 0.97)); }

    /* Móvil: las actions bajan bajo el texto (apiladas a ancho completo). */
    @media (max-width: 640px) {
      .row { flex-direction: column; align-items: stretch; }
      .actions { width: 100%; }
    }
    @media (prefers-reduced-motion: reduce) {
      .close:hover,
      .close:active { transform: none; }
    }
  `;

  /** Tono del banner: define color e icono por defecto. */
  @property({ type: String, reflect: true }) tone: OkInlineFeedbackTone = 'info';
  /** Título en negrita (opcional). */
  @property({ type: String }) heading?: string;
  /** Nombre de icono ion-icon que sobrescribe el icono por defecto del tono (opcional). */
  @property({ type: String }) icon?: string;
  /** Muestra el botón de cierre. */
  @property({ type: Boolean, reflect: true }) dismissible = false;
  /** Oculta el banner (reflejado para CSS y consumidores externos). */
  @property({ type: Boolean, reflect: true }) hidden = false;
  /** Textos traducibles (merge sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkInlineFeedbackLabels> = {};

  // Textos efectivos: defaults en inglés + overrides del consumidor.
  private get t(): OkInlineFeedbackLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  /** Marca si el slot de actions tiene contenido (para colapsar el contenedor vacío). */
  @state() private hasActions = false;

  // Icono por defecto según el tono (overridable por la prop `icon`).
  private defaultIcon(): string {
    switch (this.tone) {
      case 'success': return 'checkmark-circle';
      case 'warning': return 'warning';
      case 'danger':  return 'alert-circle';
      case 'neutral': return 'information-circle';
      case 'info':
      default:        return 'information-circle';
    }
  }

  private onActionsSlotChange = (e: Event): void => {
    const slot = e.target as HTMLSlotElement;
    this.hasActions = slot.assignedNodes({ flatten: true }).length > 0;
  };

  // Oculta el banner y avisa al consumidor; éste puede revertir restaurando `hidden=false`.
  private dismiss(): void {
    this.hidden = true;
    this.dispatchEvent(new CustomEvent('ok-dismiss', { bubbles: true, composed: true }));
  }

  render(): unknown {
    const iconName = this.icon ?? this.defaultIcon();
    return html`
      <div class="box" role="status">
        <ion-icon class="icon" name=${iconName} aria-hidden="true"></ion-icon>
        <div class="content">
          <div class="row">
            <div class="text">
              ${this.heading ? html`<div class="heading">${this.heading}</div>` : null}
              <div class="body"><slot></slot></div>
            </div>
            <div class="actions ${this.hasActions ? '' : 'empty'}">
              <slot name="actions" @slotchange=${this.onActionsSlotChange}></slot>
            </div>
          </div>
        </div>
        ${this.dismissible
          ? html`
              <button class="close" aria-label=${this.t.dismiss} @click=${this.dismiss}>
                <ion-icon name="close" aria-hidden="true"></ion-icon>
              </button>
            `
          : null}
      </div>
    `;
  }
}

define('ok-inline-feedback', OkInlineFeedback);

declare global {
  interface HTMLElementTagNameMap {
    'ok-inline-feedback': OkInlineFeedback;
  }
}
