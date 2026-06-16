import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Opción del combo. La aporta el consumidor vía la prop `.options`.
export interface OkComboOption {
  /** Valor interno (lo que se fija en `value`). */
  value: string;
  /** Texto visible en el input y en el dropdown. */
  label: string;
}

// ok-combo — combobox con búsqueda (Ionic NO tiene combobox nativo).
// Un `ion-input` de texto FILTRA la lista de `options` y muestra un dropdown propio;
// al elegir una opción rellena el input y fija `value`. AUTOCONTENIDO: CSS propio en el
// shadow (sin Ionic salvo `ion-input` para el campo y `ion-icon` para el chevron, que
// registra el host).
//   • prop `.options`    → Array<OkComboOption>
//   • prop `value`       → valor seleccionado (atributo `value`)
//   • prop `placeholder` → texto guía del input
//   • prop `label`       → etiqueta opcional sobre el campo
// Teclado: ArrowUp/ArrowDown navegan, Enter elige el resaltado, Esc cierra.
// Eventos (bubbles + composed):
//   • `ok-input`   detail { query }          — cada vez que cambia el texto
//   • `ok-change`  detail { value, label }   — al elegir una opción
// Cierra el dropdown al hacer click fuera del componente.

// Textos i18n del componente (default inglés). Pásalos vía la prop `.labels`.
export interface OkComboLabels {
  /** Texto guía del campo de búsqueda. */
  placeholder: string;
  /** Texto mostrado cuando ninguna opción casa con la búsqueda. */
  empty: string;
}

const DEFAULT_LABELS: OkComboLabels = {
  placeholder: 'Search…',
  empty: 'No results',
};

export class OkCombo extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.55));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --primary-contrast: var(--ok-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --background: var(--ok-surface, var(--ion-background-color, #ffffff));
      --hover-bg: var(--ok-hover, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.06));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.18));
      --border-radius: var(--ok-radius, 8px);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
      --shadow: var(--ok-shadow, 0 6px 24px rgba(0, 0, 0, 0.14));

      /* Por defecto ocupa el ancho del contenedor y es responsive. */
      display: block;
      width: 100%;
      max-width: 100%;
      position: relative;
      color: var(--color);
      font-family: var(--font);
      font-size: 0.95rem;
    }
    .field {
      position: relative;
      width: 100%;
    }
    /* El ion-input se estiliza vía sus propias vars (estilo Ionic). */
    ion-input {
      --background: var(--background);
      --color: var(--color);
      --placeholder-color: var(--color-muted);
      --border-radius: var(--border-radius);
      width: 100%;
    }
    /* Chevron decorativo a la derecha del campo. */
    .chevron {
      position: absolute;
      right: 0.6rem;
      top: 50%;
      transform: translateY(-50%);
      display: inline-flex;
      align-items: center;
      color: var(--color-muted);
      pointer-events: none;
      transition: transform 0.18s ease;
    }
    :host([data-open]) .chevron {
      transform: translateY(-50%) rotate(180deg);
    }
    /* Dropdown de resultados: posicionado bajo el campo, ancho del contenedor. */
    .dropdown {
      position: absolute;
      left: 0;
      right: 0;
      top: calc(100% + 4px);
      z-index: 50;
      max-height: 16rem;
      overflow-y: auto;
      margin: 0;
      padding: 0.25rem;
      list-style: none;
      background: var(--background);
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
      box-shadow: var(--shadow);
      box-sizing: border-box;
    }
    .option {
      display: block;
      width: 100%;
      box-sizing: border-box;
      padding: 0.5rem 0.6rem;
      border-radius: calc(var(--border-radius) - 2px);
      cursor: pointer;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      transition: background-color var(--ok-transition, 150ms ease),
        color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease),
        box-shadow var(--ok-transition, 150ms ease), transform 120ms ease;
    }
    @media (hover: hover) {
      .option:hover {
        background: var(--hover-bg);
      }
    }
    .option:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    .option.active {
      background: var(--primary-color);
      color: var(--primary-contrast);
    }
    @media (prefers-reduced-motion: reduce) {
      .option:hover,
      .option:active {
        transform: none;
      }
    }
    .empty {
      padding: 0.6rem;
      color: var(--color-muted);
      text-align: center;
    }
  `;

  /** Opciones disponibles. */
  @property({ attribute: false }) options: OkComboOption[] = [];
  /** Valor seleccionado actual. */
  @property() value = '';
  /** Texto guía del campo. Si se deja vacío, usa `labels.placeholder` (inglés por defecto). */
  @property() placeholder = '';
  /** Etiqueta opcional mostrada sobre el campo. */
  @property() label?: string;
  /** Textos i18n (default inglés); pasa solo las claves que quieras sobreescribir. */
  @property({ attribute: false }) labels: Partial<OkComboLabels> = {};

  // Textos efectivos: defaults inglés sobreescritos por los pasados desde fuera.
  private get t(): OkComboLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Placeholder efectivo: prop explícita si se pasó, si no el de los labels.
  private get effectivePlaceholder(): string {
    return this.placeholder || this.t.placeholder;
  }

  // Texto que el usuario ha tecleado (filtra las opciones).
  @state() private query = '';
  // Dropdown abierto/cerrado.
  @state() private open = false;
  // Índice de la opción resaltada (navegación con teclado).
  @state() private activeIndex = -1;

  // Listener de click global para cerrar al pulsar fuera (ligado al ciclo de vida).
  private onDocClick = (e: MouseEvent): void => {
    if (!this.open) return;
    // composedPath cruza el shadow: si el click no está dentro del host, cierra.
    if (!e.composedPath().includes(this)) this.close();
  };

  connectedCallback(): void {
    super.connectedCallback();
    document.addEventListener('click', this.onDocClick, true);
  }

  disconnectedCallback(): void {
    document.removeEventListener('click', this.onDocClick, true);
    super.disconnectedCallback();
  }

  // Texto a mostrar en el input: si está escribiendo usa la query, si no, el label del value.
  private get displayText(): string {
    if (this.open) return this.query;
    const current = this.options.find((o) => o.value === this.value);
    return current ? current.label : this.query;
  }

  // Opciones que casan con la query (case-insensitive, substring).
  private get filtered(): OkComboOption[] {
    const q = this.query.trim().toLowerCase();
    if (!q) return this.options;
    return this.options.filter((o) => o.label.toLowerCase().includes(q));
  }

  private close(): void {
    this.open = false;
    this.activeIndex = -1;
  }

  // Maneja la escritura en el ion-input: actualiza query, abre dropdown y emite `ok-input`.
  private handleInput(e: Event): void {
    const detail = (e as CustomEvent).detail as { value?: string } | null;
    const value = detail?.value ?? '';
    this.query = value;
    this.open = true;
    this.activeIndex = -1;
    this.dispatchEvent(
      new CustomEvent('ok-input', {
        detail: { query: value },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Elige una opción: fija value, rellena input, cierra y emite `ok-change`.
  private choose(option: OkComboOption): void {
    this.value = option.value;
    this.query = option.label;
    this.close();
    this.dispatchEvent(
      new CustomEvent('ok-change', {
        detail: { value: option.value, label: option.label },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Navegación por teclado sobre la lista filtrada.
  private handleKeydown(e: KeyboardEvent): void {
    const items = this.filtered;
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        if (!this.open) this.open = true;
        if (items.length) this.activeIndex = (this.activeIndex + 1) % items.length;
        break;
      case 'ArrowUp':
        e.preventDefault();
        if (!this.open) this.open = true;
        if (items.length)
          this.activeIndex = (this.activeIndex - 1 + items.length) % items.length;
        break;
      case 'Enter':
        if (this.open && this.activeIndex >= 0 && items[this.activeIndex]) {
          e.preventDefault();
          this.choose(items[this.activeIndex]);
        }
        break;
      case 'Escape':
        if (this.open) {
          e.preventDefault();
          this.close();
        }
        break;
    }
  }

  render(): unknown {
    const items = this.filtered;
    // Refleja el estado abierto al host para el CSS del chevron.
    this.toggleAttribute('data-open', this.open);

    return html`<div class="field">
      <ion-input
        .label=${this.label ?? ''}
        label-placement=${this.label ? 'stacked' : 'start'}
        fill="outline"
        .value=${this.displayText}
        placeholder=${this.effectivePlaceholder}
        @ionInput=${(e: Event) => this.handleInput(e)}
        @ionFocus=${() => {
          this.open = true;
        }}
        @keydown=${(e: KeyboardEvent) => this.handleKeydown(e)}
      ></ion-input>
      <span class="chevron">
        <ion-icon name="chevron-down-outline"></ion-icon>
      </span>
      ${this.open
        ? html`<ul class="dropdown" role="listbox">
            ${items.length
              ? items.map(
                  (option, i) => html`<li
                    role="option"
                    class=${`option ${i === this.activeIndex ? 'active' : ''}`.trim()}
                    aria-selected=${option.value === this.value ? 'true' : 'false'}
                    @mouseenter=${() => {
                      this.activeIndex = i;
                    }}
                    @click=${() => this.choose(option)}
                  >
                    ${option.label}
                  </li>`,
                )
              : html`<li class="empty">${this.t.empty}</li>`}
          </ul>`
        : ''}
    </div>`;
  }
}

define('ok-combo', OkCombo);

declare global {
  interface HTMLElementTagNameMap {
    'ok-combo': OkCombo;
  }
}
