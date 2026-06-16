import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Item del menú desplegable. Lo aporta el consumidor vía la prop `.items`.
export interface OkSplitButtonItem {
  /** Identificador único del item (clave de selección). */
  id: string;
  /** Texto visible del item. */
  label: string;
  /** Nombre de un ionicon opcional, mostrado antes del label. */
  icon?: string;
}

// ok-split-button — botón con acción principal + desplegable: un botón principal (emite `ok-main`)
// pegado a un botón flecha (caret) que abre un MENÚ con los items (cada uno emite `ok-select`).
// Usa `ion-button` interno para el aspecto Ionic (color/fill); el menú es un popover propio
// autocontenido. Es INLINE (no ancho completo): ocupa solo lo que miden los botones. Cierra al
// click fuera o Esc.
//   • prop `label`   → texto del botón principal
//   • prop `color`   → color Ionic (primary, danger, …) propagado a los ion-button
//   • prop `fill`    → fill Ionic (solid | outline | clear) propagado a los ion-button
//   • prop `.items`  → Array<OkSplitButtonItem>
// Eventos (bubbles + composed):
//   • `ok-main`   detail {}            → click en la acción principal
//   • `ok-select` detail { id, item }  → click en un item del menú
//   • `ok-open`   detail { open }      → apertura/cierre del menú

// Textos traducibles (default inglés). Pásalos desde fuera vía la prop `labels`.
export interface OkSplitButtonLabels {
  /** aria-label del botón caret que abre el menú. */
  more: string;
  /** aria-label del menú desplegable. */
  menu: string;
  /** Texto mostrado cuando no hay items. */
  empty: string;
}

const DEFAULT_LABELS: OkSplitButtonLabels = {
  more: 'More actions',
  menu: 'Actions',
  empty: 'No actions',
};

export class OkSplitButton extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.6));
      --hover-bg: var(--ok-hover, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.06));
      --panel-bg: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #ffffff)));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.12));
      --border-radius: var(--ok-radius, 8px);
      --shadow: var(--ok-shadow, 0 8px 28px rgba(0, 0, 0, 0.18));
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* INLINE: solo lo que miden los botones. */
      display: inline-block;
      position: relative;
      color: var(--color);
      font-family: var(--font);
    }
    /* Grupo: botón principal + caret pegados, con separación visual entre ambos. */
    .group {
      display: inline-flex;
      align-items: stretch;
    }
    /* El botón principal pierde el redondeo derecho; el caret pierde el izquierdo. */
    .main {
      --border-radius: var(--border-radius) 0 0 var(--border-radius);
      margin: 0;
    }
    .caret {
      --border-radius: 0 var(--border-radius) var(--border-radius) 0;
      --padding-start: 6px;
      --padding-end: 6px;
      margin: 0;
      min-width: 0;
      border-left: 1px solid rgba(255, 255, 255, 0.25);
    }
    .caret ion-icon {
      font-size: 1rem;
    }
    /* Menú/popover propio, posicionado bajo el grupo y alineado a la izquierda. */
    .menu {
      position: absolute;
      top: calc(100% + 6px);
      left: 0;
      z-index: 1000;
      min-width: 180px;
      max-width: 280px;
      padding: 0.3rem;
      background: var(--panel-bg);
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
      box-shadow: var(--shadow);
      box-sizing: border-box;
    }
    .item {
      display: flex;
      align-items: center;
      gap: 0.55rem;
      width: 100%;
      box-sizing: border-box;
      padding: 0.5rem 0.6rem;
      border: 0;
      background: none;
      color: inherit;
      font: inherit;
      text-align: left;
      cursor: pointer;
      border-radius: 6px;
      transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease), box-shadow var(--ok-transition, 150ms ease),
        transform 120ms ease;
    }
    @media (hover: hover) {
      .item:hover {
        background: var(--hover-bg);
      }
    }
    .item:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    @media (prefers-reduced-motion: reduce) {
      .item:hover,
      .item:active {
        transform: none;
      }
    }
    .item ion-icon {
      flex: 0 0 auto;
      font-size: 1.05rem;
      color: var(--color-muted);
    }
    .item .label {
      flex: 1 1 auto;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .empty {
      padding: 0.5rem 0.6rem;
      font-size: 0.85rem;
      color: var(--color-muted);
    }
  `;

  /** Texto del botón principal. */
  @property() label = '';
  /** Color Ionic propagado a los `ion-button` (primary, danger, …). */
  @property() color = 'primary';
  /** Fill Ionic propagado a los `ion-button` (solid | outline | clear). */
  @property() fill: 'solid' | 'outline' | 'clear' | 'default' = 'solid';
  /** Items del menú desplegable. */
  @property({ attribute: false }) items: OkSplitButtonItem[] = [];
  /** Textos traducibles (merge sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkSplitButtonLabels> = {};

  // Textos efectivos: defaults en inglés + overrides del consumidor.
  private get t(): OkSplitButtonLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Estado interno: menú abierto/cerrado.
  @state() private open = false;

  // Handler de click fuera (se enlaza/desenlaza según abre/cierra).
  private readonly onDocClick = (e: MouseEvent): void => {
    if (!e.composedPath().includes(this)) this.close();
  };

  // Handler de tecla (Esc cierra).
  private readonly onKeydown = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') this.close();
  };

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.unbind();
  }

  private bind(): void {
    document.addEventListener('click', this.onDocClick, true);
    document.addEventListener('keydown', this.onKeydown);
  }

  private unbind(): void {
    document.removeEventListener('click', this.onDocClick, true);
    document.removeEventListener('keydown', this.onKeydown);
  }

  private toggle(): void {
    this.open ? this.close() : this.openMenu();
  }

  private openMenu(): void {
    if (this.open) return;
    this.open = true;
    this.bind();
    this.dispatchEvent(
      new CustomEvent('ok-open', { detail: { open: true }, bubbles: true, composed: true }),
    );
  }

  private close(): void {
    if (!this.open) return;
    this.open = false;
    this.unbind();
    this.dispatchEvent(
      new CustomEvent('ok-open', { detail: { open: false }, bubbles: true, composed: true }),
    );
  }

  // Click en la acción principal: emite `ok-main` (no abre el menú).
  private mainClick(): void {
    this.dispatchEvent(new CustomEvent('ok-main', { detail: {}, bubbles: true, composed: true }));
  }

  // Click en un item del menú: emite `ok-select` y cierra.
  private selectItem(item: OkSplitButtonItem): void {
    this.dispatchEvent(
      new CustomEvent('ok-select', {
        detail: { id: item.id, item },
        bubbles: true,
        composed: true,
      }),
    );
    this.close();
  }

  private renderItem(item: OkSplitButtonItem): unknown {
    return html`<button
      type="button"
      class="item"
      role="menuitem"
      @click=${() => this.selectItem(item)}
    >
      ${item.icon ? html`<ion-icon .name=${item.icon}></ion-icon>` : ''}
      <span class="label">${item.label}</span>
    </button>`;
  }

  render(): unknown {
    return html`
      <div class="group">
        <ion-button
          class="main"
          color=${this.color}
          fill=${this.fill}
          @click=${() => this.mainClick()}
        >
          ${this.label}
        </ion-button>
        <ion-button
          class="caret"
          color=${this.color}
          fill=${this.fill}
          aria-haspopup="menu"
          aria-expanded=${this.open ? 'true' : 'false'}
          aria-label=${this.t.more}
          @click=${() => this.toggle()}
        >
          <ion-icon slot="icon-only" name="chevron-down-outline"></ion-icon>
        </ion-button>
      </div>
      ${this.open
        ? html`<div class="menu" role="menu" aria-label=${this.t.menu}>
            ${this.items.length
              ? this.items.map((item) => this.renderItem(item))
              : html`<div class="empty">${this.t.empty}</div>`}
          </div>`
        : ''}
    `;
  }
}

define('ok-split-button', OkSplitButton);

declare global {
  interface HTMLElementTagNameMap {
    'ok-split-button': OkSplitButton;
  }
}
