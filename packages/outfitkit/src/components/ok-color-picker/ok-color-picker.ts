import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Componente RGB simple (canales 0–255). Lo emite el evento `ok-change` junto al hex.
export interface OkRgb {
  /** Canal rojo (0–255). */
  r: number;
  /** Canal verde (0–255). */
  g: number;
  /** Canal azul (0–255). */
  b: number;
}

// Paleta por defecto (alineada con los colores estándar de Ionic) si el consumidor no pasa presets.
const DEFAULT_PRESETS = [
  '#3880ff', // primary
  '#3dc2ff', // secondary
  '#5260ff', // tertiary
  '#2dd36f', // success
  '#ffc409', // warning
  '#eb445a', // danger
  '#92949c', // medium
  '#222428', // dark
  '#ffffff', // white
  '#000000', // black
];

// --- Conversiones de color en JS puro (sin librerías, CSP-safe) ---

// Limita un número al rango [min, max].
function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n));
}

// HSV (h: 0–360, s/v: 0–1) → RGB (0–255). Algoritmo estándar de sectores de tono.
function hsvToRgb(h: number, s: number, v: number): OkRgb {
  const c = v * s;
  const hh = (((h % 360) + 360) % 360) / 60;
  const x = c * (1 - Math.abs((hh % 2) - 1));
  let r1 = 0;
  let g1 = 0;
  let b1 = 0;
  if (hh >= 0 && hh < 1) [r1, g1, b1] = [c, x, 0];
  else if (hh < 2) [r1, g1, b1] = [x, c, 0];
  else if (hh < 3) [r1, g1, b1] = [0, c, x];
  else if (hh < 4) [r1, g1, b1] = [0, x, c];
  else if (hh < 5) [r1, g1, b1] = [x, 0, c];
  else [r1, g1, b1] = [c, 0, x];
  const m = v - c;
  return {
    r: Math.round((r1 + m) * 255),
    g: Math.round((g1 + m) * 255),
    b: Math.round((b1 + m) * 255),
  };
}

// RGB (0–255) → HSV (h: 0–360, s/v: 0–1).
function rgbToHsv(r: number, g: number, b: number): { h: number; s: number; v: number } {
  const rn = r / 255;
  const gn = g / 255;
  const bn = b / 255;
  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const delta = max - min;
  let h = 0;
  if (delta !== 0) {
    if (max === rn) h = ((gn - bn) / delta) % 6;
    else if (max === gn) h = (bn - rn) / delta + 2;
    else h = (rn - gn) / delta + 4;
    h *= 60;
    if (h < 0) h += 360;
  }
  const s = max === 0 ? 0 : delta / max;
  return { h, s, v: max };
}

// Convierte un componente (0–255) a su par hexadecimal con padding.
function toHex2(n: number): string {
  return clamp(Math.round(n), 0, 255).toString(16).padStart(2, '0');
}

// RGB → hex (#rrggbb).
function rgbToHex({ r, g, b }: OkRgb): string {
  return `#${toHex2(r)}${toHex2(g)}${toHex2(b)}`;
}

// hex (#rgb o #rrggbb, con o sin almohadilla) → RGB. Devuelve null si no es válido.
function hexToRgb(hex: string): OkRgb | null {
  let h = hex.trim().replace(/^#/, '');
  if (/^[0-9a-fA-F]{3}$/.test(h)) {
    // Expande forma corta: cada dígito se duplica.
    h = h
      .split('')
      .map((c) => c + c)
      .join('');
  }
  if (!/^[0-9a-fA-F]{6}$/.test(h)) return null;
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
  };
}

// Normaliza un hex de entrada a la forma canónica #rrggbb en minúsculas, o null si no es válido.
function normalizeHex(hex: string): string | null {
  const rgb = hexToRgb(hex);
  return rgb ? rgbToHex(rgb) : null;
}

// ok-color-picker — selector de color (Ionic no lo trae). Un botón-muestra (swatch) abre un PANEL
// propio (popover autocontenido) con: área de Saturación/Valor arrastrable, slider de Tono, input
// de hex editable y una fila de swatches preset. AUTOCONTENIDO: CSS propio en el shadow (sin Ionic
// salvo `ion-icon`/`ion-input` internos, que registra el host). Es INLINE (solo lo que mide el
// swatch). Conversión HSV↔RGB↔hex en JS puro (CSP-safe). Cierra al click fuera o Esc.
//   • prop `value`    → string hex (p.ej. '#3880ff')
//   • prop `.presets` → string[] de hex (default: paleta razonable)
// Eventos (bubbles + composed):
//   • `ok-change` detail { value (hex), rgb { r, g, b } }
//   • `ok-open`   detail { open }

// Textos i18n del componente (default inglés). Pásalos vía la prop `.labels`.
// Solo hay texto en aria-labels (no hay texto visible salvo presets/hex, que son data/valores).
export interface OkColorPickerLabels {
  /** aria-label del botón swatch que abre el panel. */
  triggerLabel: string;
  /** aria-label del panel/popover. */
  panelLabel: string;
  /** aria-label del input de valor hexadecimal. */
  hexLabel: string;
}

const DEFAULT_LABELS: OkColorPickerLabels = {
  triggerLabel: 'Select color',
  panelLabel: 'Color picker',
  hexLabel: 'Hex value',
};

export class OkColorPicker extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.6));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.18));
      --panel-bg: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #ffffff)));
      --border-radius: var(--ok-radius, 10px);
      --shadow: var(--ok-shadow, 0 8px 28px rgba(0, 0, 0, 0.18));
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
      --checker: var(
        --ok-checker,
        linear-gradient(45deg, #ccc 25%, transparent 25%),
        linear-gradient(-45deg, #ccc 25%, transparent 25%),
        linear-gradient(45deg, transparent 75%, #ccc 75%),
        linear-gradient(-45deg, transparent 75%, #ccc 75%)
      );

      /* INLINE: solo lo que mide el swatch disparador. */
      display: inline-block;
      position: relative;
      color: var(--color);
      font-family: var(--font);
    }
    /* Disparador: muestra cuadrada con el color actual (sobre damero para alfa visual). */
    .swatch {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      padding: 0;
      border: 1px solid var(--border-color);
      border-radius: 8px;
      cursor: pointer;
      overflow: hidden;
      background-color: #fff;
      background-image: var(--checker);
      background-size: 12px 12px;
      background-position: 0 0, 0 6px, 6px -6px, -6px 0;
      transition: background-color var(--ok-transition, 150ms ease),
        color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease),
        box-shadow var(--ok-transition, 150ms ease), transform 120ms ease;
    }
    @media (hover: hover) {
      .swatch:hover {
        border-color: var(--color-muted);
      }
    }
    .swatch:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    .swatch .fill {
      width: 100%;
      height: 100%;
    }
    /* Panel/popover propio bajo el swatch (ancho de menú web, no demasiado ancho). */
    .panel {
      position: absolute;
      top: calc(100% + 8px);
      left: 0;
      z-index: 1000;
      width: 240px;
      max-width: 90vw;
      padding: 0.75rem;
      background: var(--panel-bg);
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
      box-shadow: var(--shadow);
      box-sizing: border-box;
    }
    /* Área de Saturación (X: blanco→color) y Valor (Y: transparente→negro). */
    .sv {
      position: relative;
      width: 100%;
      height: 140px;
      border-radius: 6px;
      cursor: crosshair;
      touch-action: none;
      background-image: linear-gradient(to top, #000, transparent),
        linear-gradient(to right, #fff, var(--hue-color, #f00));
      overflow: hidden;
    }
    .sv .thumb {
      position: absolute;
      width: 14px;
      height: 14px;
      margin: -7px 0 0 -7px;
      border-radius: 50%;
      border: 2px solid #fff;
      box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.4);
      pointer-events: none;
    }
    /* Slider de Tono: barra arcoíris horizontal con thumb arrastrable. */
    .hue {
      position: relative;
      width: 100%;
      height: 14px;
      margin-top: 0.7rem;
      border-radius: 7px;
      cursor: pointer;
      touch-action: none;
      background: linear-gradient(
        to right,
        #f00 0%,
        #ff0 17%,
        #0f0 33%,
        #0ff 50%,
        #00f 67%,
        #f0f 83%,
        #f00 100%
      );
    }
    .hue .thumb {
      position: absolute;
      top: 50%;
      width: 14px;
      height: 14px;
      margin: -7px 0 0 -7px;
      border-radius: 50%;
      border: 2px solid #fff;
      box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.4);
      background: var(--hue-color, #f00);
      pointer-events: none;
    }
    /* Fila de hex (preview + input editable). */
    .hexrow {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-top: 0.7rem;
    }
    .hexrow .preview {
      flex: 0 0 auto;
      width: 28px;
      height: 28px;
      border-radius: 6px;
      border: 1px solid var(--border-color);
    }
    .hexrow input.hex {
      flex: 1 1 auto;
      min-width: 0;
      box-sizing: border-box;
      padding: 0.4rem 0.5rem;
      font: inherit;
      font-size: 0.85rem;
      color: var(--color);
      background: transparent;
      border: 1px solid var(--border-color);
      border-radius: 6px;
      text-transform: lowercase;
    }
    .hexrow input.hex:focus {
      outline: none;
      border-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
    }
    .hexrow input.hex.invalid {
      border-color: var(--ok-danger, var(--ion-color-danger, #eb445a));
    }
    /* Fila de swatches preset. */
    .presets {
      display: flex;
      flex-wrap: wrap;
      gap: 0.3rem;
      margin-top: 0.7rem;
    }
    .presets button {
      width: 20px;
      height: 20px;
      padding: 0;
      border: 1px solid var(--border-color);
      border-radius: 5px;
      cursor: pointer;
      transition: background-color var(--ok-transition, 150ms ease),
        color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease),
        box-shadow var(--ok-transition, 150ms ease), transform 120ms ease;
    }
    @media (hover: hover) {
      .presets button:hover {
        border-color: var(--color-muted);
      }
    }
    .presets button:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    .presets button.active {
      box-shadow: 0 0 0 2px var(--panel-bg), 0 0 0 4px var(--ok-primary, var(--ion-color-primary, #3880ff));
    }
    @media (prefers-reduced-motion: reduce) {
      .swatch:active,
      .presets button:active {
        transform: none;
      }
    }
  `;

  /** Color actual en hex (#rrggbb). */
  @property({ type: String }) value = '#3880ff';
  /** Swatches preset (array de hex). Si no se pasa, se usa una paleta razonable. */
  @property({ attribute: false }) presets: string[] = DEFAULT_PRESETS;
  /** Textos i18n (default inglés); pasa solo las claves que quieras sobreescribir. */
  @property({ attribute: false }) labels: Partial<OkColorPickerLabels> = {};

  // Textos efectivos: defaults inglés sobreescritos por los pasados desde fuera.
  private get t(): OkColorPickerLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Estado interno: panel abierto/cerrado.
  @state() private open = false;
  // Estado HSV interno (fuente de verdad mientras se manipulan los controles).
  @state() private h = 0;
  @state() private s = 0;
  @state() private v = 0;
  // Texto crudo del input hex (puede estar a medio escribir / inválido).
  @state() private hexInput = '#3880ff';
  // Marca de hex inválido para feedback visual.
  @state() private hexInvalid = false;

  // Arrastre activo: 'sv' | 'hue' | null (se enlaza a pointermove/up en document).
  private dragging: 'sv' | 'hue' | null = null;

  // Sincroniza el estado HSV interno desde la prop `value` (al conectar y en cambios externos).
  private syncFromValue(): void {
    const rgb = hexToRgb(this.value);
    if (!rgb) return;
    const { h, s, v } = rgbToHsv(rgb.r, rgb.g, rgb.b);
    this.h = h;
    this.s = s;
    this.v = v;
    this.hexInput = rgbToHex(rgb);
    this.hexInvalid = false;
  }

  connectedCallback(): void {
    super.connectedCallback();
    this.syncFromValue();
  }

  willUpdate(changed: Map<string, unknown>): void {
    // Si cambia `value` desde fuera, re-deriva el estado HSV interno.
    if (changed.has('value')) this.syncFromValue();
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.unbindGlobal();
    this.unbindDrag();
  }

  // --- Apertura / cierre del panel ---

  private readonly onDocClick = (e: MouseEvent): void => {
    // Si el click cae fuera del host, cierra.
    if (!e.composedPath().includes(this)) this.close();
  };

  private readonly onKeydown = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') this.close();
  };

  private bindGlobal(): void {
    document.addEventListener('click', this.onDocClick, true);
    document.addEventListener('keydown', this.onKeydown);
  }

  private unbindGlobal(): void {
    document.removeEventListener('click', this.onDocClick, true);
    document.removeEventListener('keydown', this.onKeydown);
  }

  private toggle(): void {
    this.open ? this.close() : this.openPanel();
  }

  private openPanel(): void {
    if (this.open) return;
    this.syncFromValue();
    this.open = true;
    this.bindGlobal();
    this.dispatchEvent(
      new CustomEvent('ok-open', { detail: { open: true }, bubbles: true, composed: true }),
    );
  }

  private close(): void {
    if (!this.open) return;
    this.open = false;
    this.unbindGlobal();
    this.unbindDrag();
    this.dispatchEvent(
      new CustomEvent('ok-open', { detail: { open: false }, bubbles: true, composed: true }),
    );
  }

  // --- Emisión del color resultante ---

  // Deriva el RGB/hex actual desde el HSV interno, actualiza `value` y emite `ok-change`.
  private commitFromHsv(): void {
    const rgb = hsvToRgb(this.h, this.s, this.v);
    const hex = rgbToHex(rgb);
    this.value = hex;
    this.hexInput = hex;
    this.hexInvalid = false;
    this.emit(hex, rgb);
  }

  private emit(hex: string, rgb: OkRgb): void {
    this.dispatchEvent(
      new CustomEvent('ok-change', {
        detail: { value: hex, rgb },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // --- Área Saturación/Valor (arrastre con pointer events) ---

  // Calcula S y V a partir de la posición del puntero dentro del área.
  private updateSvFromPointer(clientX: number, clientY: number): void {
    const area = this.renderRoot.querySelector('.sv') as HTMLElement | null;
    if (!area) return;
    const rect = area.getBoundingClientRect();
    // X → saturación (0 izq → 1 der); Y → valor (1 arriba → 0 abajo).
    this.s = clamp((clientX - rect.left) / rect.width, 0, 1);
    this.v = clamp(1 - (clientY - rect.top) / rect.height, 0, 1);
    this.commitFromHsv();
  }

  // Calcula el tono a partir de la posición X del puntero en la barra arcoíris.
  private updateHueFromPointer(clientX: number): void {
    const bar = this.renderRoot.querySelector('.hue') as HTMLElement | null;
    if (!bar) return;
    const rect = bar.getBoundingClientRect();
    this.h = clamp((clientX - rect.left) / rect.width, 0, 1) * 360;
    this.commitFromHsv();
  }

  // Handlers globales de arrastre (activos solo mientras se arrastra).
  private readonly onPointerMove = (e: PointerEvent): void => {
    if (this.dragging === 'sv') this.updateSvFromPointer(e.clientX, e.clientY);
    else if (this.dragging === 'hue') this.updateHueFromPointer(e.clientX);
  };

  private readonly onPointerUp = (): void => {
    this.unbindDrag();
  };

  private bindDrag(kind: 'sv' | 'hue'): void {
    this.dragging = kind;
    document.addEventListener('pointermove', this.onPointerMove);
    document.addEventListener('pointerup', this.onPointerUp);
  }

  private unbindDrag(): void {
    this.dragging = null;
    document.removeEventListener('pointermove', this.onPointerMove);
    document.removeEventListener('pointerup', this.onPointerUp);
  }

  private onSvPointerDown(e: PointerEvent): void {
    e.preventDefault();
    this.bindDrag('sv');
    this.updateSvFromPointer(e.clientX, e.clientY);
  }

  private onHuePointerDown(e: PointerEvent): void {
    e.preventDefault();
    this.bindDrag('hue');
    this.updateHueFromPointer(e.clientX);
  }

  // --- Input hex ---

  // Maneja la edición del input hex: valida y, si es correcto, deriva el HSV y emite.
  private onHexInput(raw: string): void {
    this.hexInput = raw;
    const norm = normalizeHex(raw);
    if (!norm) {
      this.hexInvalid = true;
      return;
    }
    this.hexInvalid = false;
    const rgb = hexToRgb(norm)!;
    const { h, s, v } = rgbToHsv(rgb.r, rgb.g, rgb.b);
    this.h = h;
    this.s = s;
    this.v = v;
    this.value = norm;
    this.emit(norm, rgb);
  }

  // --- Presets ---

  // Selecciona un swatch preset: deriva HSV/hex y emite.
  private selectPreset(hex: string): void {
    const norm = normalizeHex(hex);
    if (!norm) return;
    const rgb = hexToRgb(norm)!;
    const { h, s, v } = rgbToHsv(rgb.r, rgb.g, rgb.b);
    this.h = h;
    this.s = s;
    this.v = v;
    this.value = norm;
    this.hexInput = norm;
    this.hexInvalid = false;
    this.emit(norm, rgb);
  }

  render(): unknown {
    // Color "puro" del tono actual (S=1, V=1) para pintar el gradiente del área SV.
    const hueColor = rgbToHex(hsvToRgb(this.h, 1, 1));
    // Color resultante actual (para previews) desde el HSV interno.
    const current = rgbToHex(hsvToRgb(this.h, this.s, this.v));
    // Posición de los thumbs en porcentaje.
    const svLeft = `${this.s * 100}%`;
    const svTop = `${(1 - this.v) * 100}%`;
    const hueLeft = `${(this.h / 360) * 100}%`;

    return html`
      <button
        type="button"
        class="swatch"
        aria-haspopup="dialog"
        aria-expanded=${this.open ? 'true' : 'false'}
        aria-label=${this.t.triggerLabel}
        @click=${() => this.toggle()}
      >
        <span class="fill" style=${`background:${this.value}`}></span>
      </button>
      ${this.open
        ? html`<div
            class="panel"
            role="dialog"
            aria-label=${this.t.panelLabel}
            style=${`--hue-color:${hueColor}`}
          >
            <div
              class="sv"
              @pointerdown=${(e: PointerEvent) => this.onSvPointerDown(e)}
            >
              <span class="thumb" style=${`left:${svLeft};top:${svTop}`}></span>
            </div>
            <div
              class="hue"
              @pointerdown=${(e: PointerEvent) => this.onHuePointerDown(e)}
            >
              <span class="thumb" style=${`left:${hueLeft}`}></span>
            </div>
            <div class="hexrow">
              <span class="preview" style=${`background:${current}`}></span>
              <input
                class=${`hex ${this.hexInvalid ? 'invalid' : ''}`.trim()}
                type="text"
                spellcheck="false"
                autocomplete="off"
                aria-label=${this.t.hexLabel}
                .value=${this.hexInput}
                @input=${(e: Event) =>
                  this.onHexInput((e.target as HTMLInputElement).value)}
              />
            </div>
            ${this.presets.length
              ? html`<div class="presets">
                  ${this.presets.map((hex) => {
                    const norm = normalizeHex(hex);
                    const active = norm !== null && norm === this.value.toLowerCase();
                    return html`<button
                      type="button"
                      class=${active ? 'active' : ''}
                      style=${`background:${hex}`}
                      aria-label=${hex}
                      @click=${() => this.selectPreset(hex)}
                    ></button>`;
                  })}
                </div>`
              : ''}
          </div>`
        : ''}
    `;
  }
}

define('ok-color-picker', OkColorPicker);

declare global {
  interface HTMLElementTagNameMap {
    'ok-color-picker': OkColorPicker;
  }
}
