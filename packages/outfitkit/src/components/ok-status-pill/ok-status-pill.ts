import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-status-pill — pill de estado con tinte semántico suave (el hueco que Ionic no cubre:
// ion-badge es color sólido y ion-chip es neutro/interactivo). Fondo al ~14% del color del tono
// + texto en el shade. Presentacional (sin eventos). Es la celda de estado típica dentro de
// ok-data-table (render de celda), reutilizable desde Cloud y Hub.
//   • prop `tone`  → 'success' | 'warning' | 'danger' | 'info' | 'primary' | 'neutral' (def 'neutral')
//   • prop `label` → texto (alternativa al slot; útil al crearla por JS en renders de celda)
//   • prop `icon`  → nombre de icono ion-icon opcional a la izquierda
//   • prop `dot`   → punto de color en vez de icono (estilo Linear)
//   • prop `size`  → 'sm' | 'md' (def 'md')
// Slot default → contenido del pill. Theming: `--ok-pill-bg-opacity` (def 0.14) + colores por la
// cadena --ok-* → --ion-color-{tone} → hex (mismo patrón que ok-inline-feedback).
export type OkStatusPillTone = 'success' | 'warning' | 'danger' | 'info' | 'primary' | 'neutral';
export type OkStatusPillSize = 'sm' | 'md';

export class OkStatusPill extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex.
         --tone-color (base: fondo/punto/icono) y --tone-shade (texto) se reasignan por tone abajo. */
      --tone-color: var(--ok-medium, var(--ion-color-medium, #5f5f5f));
      --tone-shade: var(--ok-medium, var(--ion-color-medium-shade, #545454));
      --background-opacity: var(--ok-pill-bg-opacity, 0.14);
      --border-radius: var(--ok-pill-radius, 999px);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* Inline: el pill vive en celdas de tabla, cabeceras y listados. */
      display: inline-flex;
      vertical-align: middle;
      font-family: var(--font);
      box-sizing: border-box;
    }

    /* Mapa de tonos → color Ionic (base + shade para el texto). */
    :host([tone='success']) {
      --tone-color: var(--ok-success, var(--ion-color-success, #2dd55b));
      --tone-shade: var(--ok-success, var(--ion-color-success-shade, #28bb50));
    }
    :host([tone='warning']) {
      --tone-color: var(--ok-warning, var(--ion-color-warning, #ffc409));
      --tone-shade: var(--ok-warning-shade, var(--ion-color-warning-shade, #e0ac08));
    }
    :host([tone='danger']) {
      --tone-color: var(--ok-danger, var(--ion-color-danger, #c5000f));
      --tone-shade: var(--ok-danger, var(--ion-color-danger-shade, #ad000d));
    }
    :host([tone='info']) {
      --tone-color: var(--ok-info, var(--ion-color-secondary, #0163aa));
      --tone-shade: var(--ok-info, var(--ion-color-secondary-shade, #015896));
    }
    :host([tone='primary']) {
      --tone-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --tone-shade: var(--ok-primary, var(--ion-color-primary-shade, #3171e0));
    }
    /* neutral / sin tono → medium (default ya aplicado en :host). */

    .pill {
      display: inline-flex;
      align-items: center;
      gap: 0.4em;
      padding: 0.25em 0.7em;
      border-radius: var(--border-radius);
      /* Fondo tonal: el color del tono con baja opacidad. */
      background: color-mix(in srgb, var(--tone-color) calc(var(--background-opacity) * 100%), transparent);
      color: var(--ok-pill-color, var(--tone-shade));
      font-size: 0.8125rem;
      font-weight: 600;
      line-height: 1.4;
      white-space: nowrap;
    }
    :host([size='sm']) .pill {
      font-size: 0.72rem;
      padding: 0.2em 0.6em;
    }

    ion-icon {
      flex: 0 0 auto;
      font-size: 1.05em;
      pointer-events: none;
    }

    /* Punto de color (estilo Linear) en vez de icono. */
    .dot {
      flex: 0 0 auto;
      width: 0.5em;
      height: 0.5em;
      border-radius: 50%;
      background: var(--tone-color);
    }
  `;

  /** Tono semántico del pill. */
  @property({ type: String, reflect: true }) tone: OkStatusPillTone = 'neutral';
  /** Texto del pill (alternativa al slot; útil al crearlo por JS en renders de celda). */
  @property({ type: String }) label?: string;
  /** Nombre de icono ion-icon opcional a la izquierda. */
  @property({ type: String }) icon?: string;
  /** Punto de color en vez de icono (estilo Linear). */
  @property({ type: Boolean, reflect: true }) dot = false;
  /** Tamaño. */
  @property({ type: String, reflect: true }) size: OkStatusPillSize = 'md';

  render(): unknown {
    return html`
      <span class="pill" part="pill">
        ${this.dot
          ? html`<span class="dot" part="dot" aria-hidden="true"></span>`
          : this.icon
            ? html`<ion-icon name=${this.icon} aria-hidden="true"></ion-icon>`
            : null}
        <slot>${this.label ?? ''}</slot>
      </span>
    `;
  }
}

define('ok-status-pill', OkStatusPill);

declare global {
  interface HTMLElementTagNameMap {
    'ok-status-pill': OkStatusPill;
  }
}
