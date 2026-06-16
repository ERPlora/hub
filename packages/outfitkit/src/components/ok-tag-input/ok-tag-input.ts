import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-tag-input — entrada de chips/tags. El usuario escribe y pulsa Enter o coma para añadir
// un tag; Backspace con el input vacío borra el último; cada chip tiene una × para quitarlo.
// AUTOCONTENIDO: CSS propio en el shadow; los chips son propios (no `ion-chip`), pero el campo
// de texto usa `ion-input` y la × usa `ion-icon` (ambos los registra el host).
//   • prop `.value`        → string[] (tags actuales)
//   • prop `placeholder`   → texto guía del input
//   • prop `.suggestions`  → string[] opcional; muestra un dropdown filtrado al escribir
// Evento (bubbles + composed):
//   • `ok-change`  detail { tags }  — cada vez que cambia la lista de tags

// Textos i18n del componente (default inglés). Pásalos vía la prop `.labels`.
export interface OkTagInputLabels {
  /** Texto guía del input cuando no hay tags. */
  placeholder: string;
  /** aria-label del botón × de cada chip. Variable: {tag}. */
  removeLabel: string;
}

const DEFAULT_LABELS: OkTagInputLabels = {
  placeholder: 'Add tag…',
  removeLabel: 'Remove {tag}',
};

export class OkTagInput extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.55));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --primary-contrast: var(--ok-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --background: var(--ok-surface, var(--ion-background-color, #ffffff));
      --chip-bg: var(--ok-chip-bg, rgba(var(--ion-color-primary-rgb, 56, 128, 255), 0.14));
      --chip-color: var(--ok-chip-color, var(--ion-color-primary, #3880ff));
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
    /* Caja contenedora: chips + campo de texto, con wrap responsive. */
    .box {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.4rem;
      width: 100%;
      box-sizing: border-box;
      min-height: 2.6rem;
      padding: 0.35rem 0.5rem;
      background: var(--background);
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
      cursor: text;
    }
    .box:focus-within {
      border-color: var(--primary-color);
    }
    /* Chip propio (no ion-chip). */
    .chip {
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      max-width: 100%;
      padding: 0.2rem 0.2rem 0.2rem 0.55rem;
      background: var(--chip-bg);
      color: var(--chip-color);
      border-radius: 999px;
      font-size: 0.85rem;
      line-height: 1.2;
      transition: background-color var(--ok-transition, 150ms ease),
        color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease),
        box-shadow var(--ok-transition, 150ms ease), transform 120ms ease;
    }
    .chip .text {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .chip .remove {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 1.15rem;
      height: 1.15rem;
      padding: 0;
      border: 0;
      border-radius: 999px;
      background: none;
      color: inherit;
      cursor: pointer;
      opacity: 0.7;
      transition: background-color var(--ok-transition, 150ms ease),
        color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease),
        box-shadow var(--ok-transition, 150ms ease), transform 120ms ease,
        opacity var(--ok-transition, 150ms ease);
    }
    @media (hover: hover) {
      .chip .remove:hover {
        opacity: 1;
        background: rgba(0, 0, 0, 0.08);
      }
    }
    .chip .remove:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    @media (prefers-reduced-motion: reduce) {
      .chip:active,
      .chip .remove:hover,
      .chip .remove:active {
        transform: none;
      }
    }
    .chip .remove ion-icon {
      font-size: 0.9rem;
    }
    /* El campo de texto crece para ocupar el resto de la fila. */
    ion-input {
      --background: transparent;
      --color: var(--color);
      --placeholder-color: var(--color-muted);
      --padding-start: 0.15rem;
      --padding-end: 0.15rem;
      flex: 1 1 6rem;
      min-width: 6rem;
    }
    /* Dropdown de sugerencias, ancho del contenedor. */
    .dropdown {
      position: absolute;
      left: 0;
      right: 0;
      top: calc(100% + 4px);
      z-index: 50;
      max-height: 14rem;
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
    .suggestion {
      display: block;
      width: 100%;
      box-sizing: border-box;
      padding: 0.5rem 0.6rem;
      border-radius: calc(var(--border-radius) - 2px);
      cursor: pointer;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      transition: background 0.12s ease, color 0.12s ease;
    }
    .suggestion:hover,
    .suggestion.active {
      background: var(--primary-color);
      color: var(--primary-contrast);
    }
  `;

  /** Tags actuales. */
  @property({ attribute: false }) value: string[] = [];
  /** Texto guía del campo. Si se deja vacío, usa `labels.placeholder` (inglés por defecto). */
  @property() placeholder = '';
  /** Sugerencias opcionales para el dropdown. */
  @property({ attribute: false }) suggestions?: string[];
  /** Textos i18n (default inglés); pasa solo las claves que quieras sobreescribir. */
  @property({ attribute: false }) labels: Partial<OkTagInputLabels> = {};

  // Textos efectivos: defaults inglés sobreescritos por los pasados desde fuera.
  private get t(): OkTagInputLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Placeholder efectivo: prop explícita si se pasó, si no el de los labels.
  private get effectivePlaceholder(): string {
    return this.placeholder || this.t.placeholder;
  }

  // Texto en curso (aún no convertido en tag).
  @state() private draft = '';
  // Dropdown de sugerencias abierto.
  @state() private open = false;
  // Índice de la sugerencia resaltada.
  @state() private activeIndex = -1;

  // Listener de click global para cerrar el dropdown al pulsar fuera.
  private onDocClick = (e: MouseEvent): void => {
    if (!this.open) return;
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

  private close(): void {
    this.open = false;
    this.activeIndex = -1;
  }

  // Sugerencias filtradas: casan con el draft y no están ya añadidas.
  private get filteredSuggestions(): string[] {
    if (!this.suggestions?.length) return [];
    const q = this.draft.trim().toLowerCase();
    return this.suggestions.filter(
      (s) => !this.value.includes(s) && (!q || s.toLowerCase().includes(q)),
    );
  }

  // Emite `ok-change` con la lista de tags actual.
  private emitChange(): void {
    this.dispatchEvent(
      new CustomEvent('ok-change', {
        detail: { tags: [...this.value] },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Añade un tag (recortado, sin duplicados ni vacíos) y emite cambio.
  private addTag(raw: string): void {
    const tag = raw.trim();
    if (!tag || this.value.includes(tag)) {
      this.draft = '';
      return;
    }
    this.value = [...this.value, tag];
    this.draft = '';
    this.close();
    this.emitChange();
  }

  // Quita el tag en el índice indicado y emite cambio.
  private removeAt(index: number): void {
    this.value = this.value.filter((_, i) => i !== index);
    this.emitChange();
  }

  private handleInput(e: Event): void {
    const detail = (e as CustomEvent).detail as { value?: string } | null;
    this.draft = detail?.value ?? '';
    this.open = !!this.filteredSuggestions.length;
    this.activeIndex = -1;
  }

  private handleKeydown(e: KeyboardEvent): void {
    const sugg = this.filteredSuggestions;
    switch (e.key) {
      case 'Enter':
        e.preventDefault();
        // Si hay una sugerencia resaltada, añade esa; si no, el texto en curso.
        if (this.open && this.activeIndex >= 0 && sugg[this.activeIndex]) {
          this.addTag(sugg[this.activeIndex]);
        } else if (this.draft.trim()) {
          this.addTag(this.draft);
        }
        break;
      case ',':
        // La coma actúa como separador: convierte el texto en tag.
        e.preventDefault();
        if (this.draft.trim()) this.addTag(this.draft);
        break;
      case 'Backspace':
        // Input vacío → borra el último tag.
        if (!this.draft && this.value.length) {
          e.preventDefault();
          this.removeAt(this.value.length - 1);
        }
        break;
      case 'ArrowDown':
        if (sugg.length) {
          e.preventDefault();
          this.open = true;
          this.activeIndex = (this.activeIndex + 1) % sugg.length;
        }
        break;
      case 'ArrowUp':
        if (sugg.length) {
          e.preventDefault();
          this.open = true;
          this.activeIndex = (this.activeIndex - 1 + sugg.length) % sugg.length;
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
    const sugg = this.filteredSuggestions;

    return html`<div
      class="box"
      @click=${(e: Event) => {
        // Click en zona vacía → enfoca el ion-input.
        const input = this.renderRoot.querySelector('ion-input') as
          | (HTMLElement & { setFocus?: () => void })
          | null;
        if (e.target === e.currentTarget) input?.setFocus?.();
      }}
    >
      ${this.value.map(
        (tag, i) => html`<span class="chip">
          <span class="text">${tag}</span>
          <button
            type="button"
            class="remove"
            aria-label=${this.t.removeLabel.replace('{tag}', tag)}
            @click=${(e: Event) => {
              e.stopPropagation();
              this.removeAt(i);
            }}
          >
            <ion-icon name="close-outline"></ion-icon>
          </button>
        </span>`,
      )}
      <ion-input
        .value=${this.draft}
        placeholder=${this.value.length ? '' : this.effectivePlaceholder}
        @ionInput=${(e: Event) => this.handleInput(e)}
        @keydown=${(e: KeyboardEvent) => this.handleKeydown(e)}
      ></ion-input>
    </div>
    ${this.open && sugg.length
      ? html`<ul class="dropdown" role="listbox">
          ${sugg.map(
            (s, i) => html`<li
              role="option"
              class=${`suggestion ${i === this.activeIndex ? 'active' : ''}`.trim()}
              @mouseenter=${() => {
                this.activeIndex = i;
              }}
              @click=${() => this.addTag(s)}
            >
              ${s}
            </li>`,
          )}
        </ul>`
      : ''}`;
  }
}

define('ok-tag-input', OkTagInput);

declare global {
  interface HTMLElementTagNameMap {
    'ok-tag-input': OkTagInput;
  }
}
