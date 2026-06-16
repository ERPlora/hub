import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Color de la pastilla: par (fondo soft + color de icono).
export type OkIconTileColor =
  | 'brand'
  | 'leaf'
  | 'warn'
  | 'danger'
  | 'info'
  | 'neutral';

// Tamaño del tile.
export type OkIconTileSize = 'md' | 'lg';

// Forma del recorte.
export type OkIconTileShape = 'rounded' | 'circle';

// ok-icon-tile — pastilla cuadrada coloreada con un icono dentro.
// Visual de cabecera para filas/cards/kpi (leading icon). Puramente presentacional.
// Porta el look de `.ux-icon-tile` (fondo soft + fg por color): md=32px / lg=40px,
// radio 8px (rounded) o pill (circle).
export class OkIconTile extends LitElement {
  static styles = css`
    :host {
      /* Inline atom: no ocupa el ancho del contenedor. */
      display: inline-flex;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --fg: var(--ok-text-color, var(--ion-text-color, #1f2933));
      /* Fondo SOFT derivado del PROPIO color del icono (lavado ~13%), no del --ion-color-*-tint
       * del tema (que suele ser saturado y tapaba el icono). Así el icono va a color pleno (--fg)
       * sobre un lavado apenas perceptible y SIEMPRE se ve. Override con --bg si se quiere otro. */
      --bg: color-mix(in srgb, var(--fg) 13%, transparent);
      --size: 2rem; /* 32px (md) */
      --radius: 0.5rem; /* 8px */
      --icon-size: 1.125rem; /* 18px */
    }

    /* Solo el color del icono (--fg); el fondo se deriva del lavado soft del propio --fg (arriba). */
    :host([color='brand'])   { --fg: var(--ok-brand,  var(--ion-color-primary,  #3880ff)); }
    :host([color='leaf'])    { --fg: var(--ok-leaf,   var(--ion-color-success,  #2dad62)); }
    :host([color='warn'])    { --fg: var(--ok-warn,   var(--ion-color-warning,  #c79100)); }
    :host([color='danger'])  { --fg: var(--ok-danger, var(--ion-color-danger,   #d8553f)); }
    :host([color='info'])    { --fg: var(--ok-info,   var(--ion-color-tertiary, #5b8cd9)); }
    :host([color='neutral']) { --fg: var(--ok-color-medium, var(--ion-color-medium, #6b7280)); }

    /* Tamaños. */
    :host([size='lg']) {
      --size: 2.5rem; /* 40px */
      --icon-size: 1.375rem; /* 22px */
    }

    /* Forma circular. */
    :host([shape='circle']) {
      --radius: 9999px;
    }

    .tile {
      display: inline-grid;
      place-items: center;
      width: var(--size);
      height: var(--size);
      border-radius: var(--radius);
      background: var(--bg);
      color: var(--fg);
      flex-shrink: 0;
    }

    /* Tanto ion-icon como iconify-icon respetan el tamaño. */
    ion-icon,
    iconify-icon,
    ::slotted(*) {
      font-size: var(--icon-size);
      width: var(--icon-size);
      height: var(--icon-size);
    }

    iconify-icon {
      display: inline-flex;
    }
  `;

  /** Nombre del icono (Iconify, p.ej. "ion:home-outline" o "home-outline"). */
  @property() icon?: string;

  /** Par de color (fondo soft + color del icono). */
  @property({ reflect: true }) color: OkIconTileColor = 'neutral';

  /** Tamaño del tile. */
  @property({ reflect: true }) size: OkIconTileSize = 'md';

  /** Forma del recorte. */
  @property({ reflect: true }) shape: OkIconTileShape = 'rounded';

  /** Etiqueta accesible; si falta, el tile es decorativo (aria-hidden). */
  @property() label?: string;

  // Render del icono: `iconify-icon` si el nombre trae prefijo de set ("set:name");
  // si no, `ion-icon` (que resuelve por nombre Ionicons). Ambos los registra el host.
  private renderIcon(): unknown {
    if (!this.icon) {
      // Sin icono declarado: deja un slot para componer un SVG/imagen a mano.
      return html`<slot></slot>`;
    }
    if (this.icon.includes(':')) {
      return html`<iconify-icon icon=${this.icon} aria-hidden="true"></iconify-icon>`;
    }
    return html`<ion-icon name=${this.icon} aria-hidden="true"></ion-icon>`;
  }

  render(): unknown {
    const decorative = !this.label;
    return html`
      <span
        class="tile"
        role="img"
        aria-hidden=${decorative ? 'true' : 'false'}
        aria-label=${this.label ?? ''}
      >
        ${this.renderIcon()}
      </span>
    `;
  }
}

define('ok-icon-tile', OkIconTile);

declare global {
  interface HTMLElementTagNameMap {
    'ok-icon-tile': OkIconTile;
  }
}
