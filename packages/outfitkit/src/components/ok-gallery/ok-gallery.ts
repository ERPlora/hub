import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Una imagen del grid. La aporta el consumidor vía la prop `.images`.
export interface OkGalleryImage {
  /** URL de la imagen. Si se omite, se pinta el placeholder de rayas diagonales. */
  src?: string;
  /** Texto alternativo (accesibilidad). */
  alt?: string;
  /** Etiqueta opcional: caption inferior al hover y texto del placeholder. */
  label?: string;
  /** Id estable opcional. Si falta, se usa el índice como clave de selección. */
  id?: string | number;
}

// ok-gallery — grid de imágenes seleccionable que Ionic no trae.
// AUTOCONTENIDO: CSS propio en el shadow, grid auto-fill de items cuadrados, hover con escala +
// caption con gradiente inferior, y badge circular de selección arriba-derecha que se rellena de
// color de marca al seleccionar (con outline de 2px). Las imágenes sin `src` usan el placeholder
// de rayas diagonales. Empareja con `ok-lightbox` (emite `ok-open` con el índice al abrir).
//
// Props:
//   • `.images`     → Array<OkGalleryImage>
//   • `selectable`  → activa el badge de selección y el toggle por click
//   • `.selected`   → Array<string|number> de ids (o índices si no hay id) seleccionados
//   • `min-size`    → ancho mínimo del item para el auto-fill (default 160)
//   • `columns`     → fuerza un número fijo de columnas (ignora min-size si > 0)
// Eventos (bubbles + composed):
//   • `ok-select` detail { id, index, selected: Array<string|number> }
//   • `ok-open`   detail { id, index, image }
export class OkGallery extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens overridables estilo Ionic: cadena --ok-* → --ion-* → hex. */
      --gap: var(--ok-gallery-gap, 8px);
      --radius: var(--ok-gallery-radius, var(--ion-border-radius, 10px));
      --brand: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --brand-contrast: var(
        --ok-primary-contrast,
        var(--ion-color-primary-contrast, #ffffff)
      );
      --placeholder-bg: var(--ok-gallery-ph, var(--ion-color-light, #e6e8ec));
      --placeholder-bg-2: var(
        --ok-gallery-ph-2,
        var(--ion-color-light-shade, #cfd2d8)
      );
      --placeholder-ink: var(
        --ok-gallery-ph-ink,
        var(--ion-color-medium, #92949c)
      );
      --caption-color: var(--ok-gallery-caption, #ffffff);
      --min-size: 160px;
      --columns: 0;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(var(--min-size), 1fr));
      gap: var(--gap);
      width: 100%;
    }
    /* Cuando se fuerza un número fijo de columnas. */
    :host([columns]) .grid {
      grid-template-columns: repeat(var(--columns), 1fr);
    }

    .item {
      position: relative;
      aspect-ratio: 1;
      background: var(--placeholder-bg);
      border-radius: var(--radius);
      overflow: hidden;
      cursor: pointer;
      transition: transform 180ms ease-out;
      padding: 0;
      border: none;
      width: 100%;
      display: block;
      font: inherit;
      color: inherit;
      text-align: left;
    }
    .item:hover {
      transform: scale(1.02);
    }
    .item:focus-visible {
      outline: 2px solid var(--brand);
      outline-offset: 2px;
    }

    .item img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }

    /* Placeholder de rayas diagonales para imágenes sin src. */
    .item--ph {
      background: repeating-linear-gradient(
        45deg,
        var(--placeholder-bg) 0 8px,
        var(--placeholder-bg-2) 8px 16px
      );
    }
    .ph-label {
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: var(--ok-font-mono, ui-monospace, monospace);
      font-size: 10.5px;
      color: var(--placeholder-ink);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      padding: 4px;
      text-align: center;
    }

    /* Caption inferior con gradiente, aparece al hover. */
    .caption {
      position: absolute;
      inset: auto 0 0 0;
      padding: 24px 10px 8px;
      background: linear-gradient(to top, rgba(0, 0, 0, 0.72), transparent);
      color: var(--caption-color);
      font-size: 11.5px;
      font-weight: 500;
      opacity: 0;
      transition: opacity 180ms ease-out;
      pointer-events: none;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .item:hover .caption,
    .item:focus-visible .caption {
      opacity: 1;
    }

    /* Badge circular de selección arriba-derecha. */
    .select {
      position: absolute;
      top: 8px;
      right: 8px;
      width: 22px;
      height: 22px;
      border-radius: 50%;
      background: rgba(0, 0, 0, 0.45);
      border: 2px solid #ffffff;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: #ffffff;
      opacity: 0;
      cursor: pointer;
      padding: 0;
      transition: opacity 180ms ease-out, background 180ms ease-out;
    }
    .select svg {
      width: 13px;
      height: 13px;
      display: none;
    }
    .item:hover .select,
    .item:focus-within .select {
      opacity: 1;
    }
    .select:focus-visible {
      opacity: 1;
      outline: 2px solid var(--brand-contrast);
      outline-offset: 1px;
    }

    /* Estado seleccionado: badge relleno de marca + outline en el item. */
    .item--selected .select {
      opacity: 1;
      background: var(--brand);
      border-color: var(--brand);
      color: var(--brand-contrast);
    }
    .item--selected .select svg {
      display: block;
    }
    .item--selected {
      outline: 2px solid var(--brand);
      outline-offset: -2px;
    }

    @media (prefers-reduced-motion: reduce) {
      .item,
      .caption,
      .select {
        transition: none;
      }
      .item:hover {
        transform: none;
      }
    }
  `;

  /** Imágenes del grid (declarativas). */
  @property({ attribute: false }) images: OkGalleryImage[] = [];

  /** Activa el modo selección (badge + toggle por click). */
  @property({ type: Boolean, reflect: true }) selectable = false;

  /** Ids (o índices) actualmente seleccionados. */
  @property({ attribute: false }) selected: Array<string | number> = [];

  /** Ancho mínimo del item para el auto-fill (px). */
  @property({ type: Number, attribute: 'min-size' }) minSize = 160;

  /** Fuerza un número fijo de columnas (0 = auto-fill por min-size). */
  @property({ type: Number, reflect: true }) columns = 0;

  // Devuelve la clave de selección de una imagen: su id, o el índice como fallback.
  private keyOf(img: OkGalleryImage, index: number): string | number {
    return img.id ?? index;
  }

  private isSelected(key: string | number): boolean {
    return this.selected.includes(key);
  }

  // Alterna la selección y emite `ok-select` con la nueva lista.
  private toggle(img: OkGalleryImage, index: number, ev: Event): void {
    ev.stopPropagation();
    const key = this.keyOf(img, index);
    const next = this.isSelected(key)
      ? this.selected.filter((k) => k !== key)
      : [...this.selected, key];
    this.selected = next;
    this.dispatchEvent(
      new CustomEvent('ok-select', {
        detail: { id: key, index, selected: next },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Abre la imagen (para emparejar con ok-lightbox). Emite `ok-open`.
  private open(img: OkGalleryImage, index: number): void {
    this.dispatchEvent(
      new CustomEvent('ok-open', {
        detail: { id: this.keyOf(img, index), index, image: img },
        bubbles: true,
        composed: true,
      }),
    );
  }

  render(): unknown {
    return html`
      <div
        class="grid"
        role="${this.selectable ? 'listbox' : 'list'}"
        aria-multiselectable="${this.selectable ? 'true' : 'false'}"
        style="--min-size:${this.minSize}px;--columns:${this.columns};"
      >
        ${this.images.map((img, index) => {
          const key = this.keyOf(img, index);
          const sel = this.selectable && this.isSelected(key);
          const isPh = !img.src;
          return html`
            <button
              type="button"
              class="item ${isPh ? 'item--ph' : ''} ${sel ? 'item--selected' : ''}"
              role="${this.selectable ? 'option' : 'listitem'}"
              aria-selected="${this.selectable ? String(sel) : 'undefined'}"
              aria-label="${img.alt || img.label || `Imagen ${index + 1}`}"
              @click=${() => this.open(img, index)}
            >
              ${isPh
                ? html`<span class="ph-label">${img.label || ''}</span>`
                : html`<img src="${img.src as string}" alt="${img.alt || ''}" loading="lazy" />`}
              ${img.label
                ? html`<span class="caption">${img.label}</span>`
                : null}
              ${this.selectable
                ? html`<span
                    class="select"
                    role="checkbox"
                    aria-checked="${String(sel)}"
                    aria-label="Seleccionar"
                    tabindex="0"
                    @click=${(e: Event) => this.toggle(img, index, e)}
                    @keydown=${(e: KeyboardEvent) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        this.toggle(img, index, e);
                      }
                    }}
                    >${selectIcon}</span
                  >`
                : null}
            </button>
          `;
        })}
      </div>
    `;
  }
}

// Tilde SVG inline (sin dependencias) para el badge de selección.
const selectIcon = html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <path d="M5 13l4 4L19 7" />
</svg>`;

define('ok-gallery', OkGallery);

declare global {
  interface HTMLElementTagNameMap {
    'ok-gallery': OkGallery;
  }
}
