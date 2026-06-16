import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-keyboard — teclado virtual / on-screen para kiosko, POS y pantallas táctiles.
// Porta el look del antiguo .ux-osk (kiosk QWERTY) + .ux-vkb (mobile denso):
// teclas con doble borde inferior, tecla enter con color de marca, shift toggle
// que pone en mayúsculas, anchos por flex-grow (wide/xwide/space/enter) y modo
// numérico en rejilla de 3 columnas. Incluye una tira de display opcional con
// label + valor + caret parpadeante cuando está vacío.

/** Distribución del teclado. */
export type OkKeyboardLayout = 'qwerty' | 'numeric' | 'symbol';
/** Densidad: touch (kiosko, teclas grandes) o compact (denso, mobile). */
export type OkKeyboardDensity = 'touch' | 'compact';

/** Tipo de tecla especial para estilizado y comportamiento. */
type SpecialKind = 'del' | 'enter' | 'space' | 'shift' | 'num' | 'mod' | undefined;

/** Una tecla declarativa de una fila. */
interface KeyDef {
  /** Carácter base (minúscula) que se inserta; vacío para teclas de acción. */
  base: string;
  /** Etiqueta a mostrar; si falta se usa `base`. */
  label?: string;
  /** Tipo especial (estilo + comportamiento). */
  kind?: SpecialKind;
}

// Filas QWERTY: número, qwerty, asdf, zxcv + ⌫, barra de acciones.
const QWERTY: KeyDef[][] = [
  '1234567890'.split('').map((c) => ({ base: c })),
  [...'qwertyuiop'.split('').map((c) => ({ base: c })), { base: '', label: '⌫', kind: 'del' as const }],
  'asdfghjkl'.split('').map((c) => ({ base: c })),
  [
    { base: '', label: '⇧', kind: 'shift' as const },
    ...'zxcvbnm'.split('').map((c) => ({ base: c })),
    { base: ',' },
    { base: '.' },
    { base: '\n', label: '↵', kind: 'enter' as const },
  ],
  [
    { base: '', label: '123', kind: 'num' as const },
    { base: ' ', label: 'espacio', kind: 'space' as const },
    { base: '@', label: '@', kind: 'mod' as const },
  ],
];

// Símbolos (densos, fuente mono en el original).
const SYMBOL: KeyDef[][] = [
  '1234567890'.split('').map((c) => ({ base: c })),
  '@#$_&-+()/'.split('').map((c) => ({ base: c })),
  [
    { base: '', label: 'ABC', kind: 'num' as const },
    ...'*"\':;!?'.split('').map((c) => ({ base: c })),
    { base: '', label: '⌫', kind: 'del' as const },
  ],
  [
    { base: ' ', label: 'espacio', kind: 'space' as const },
    { base: '.' },
    { base: ',' },
    { base: '\n', label: '↵', kind: 'enter' as const },
  ],
];

// Numérico: rejilla 3 columnas (1-9, ⌫, 0, ↵).
const NUMERIC: KeyDef[][] = [
  [{ base: '1' }, { base: '2' }, { base: '3' }],
  [{ base: '4' }, { base: '5' }, { base: '6' }],
  [{ base: '7' }, { base: '8' }, { base: '9' }],
  [
    { base: '', label: '⌫', kind: 'del' as const },
    { base: '0' },
    { base: '\n', label: '↵', kind: 'enter' as const },
  ],
];

export class OkKeyboard extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --bg: var(--ok-surface, var(--ion-background-color, #ffffff));
      --key-bg: var(--ok-key-bg, var(--ion-color-light, #f4f5f8));
      --key-bg-hover: var(--ok-key-bg-hover, var(--ion-color-light-shade, #e6e7ea));
      --special-bg: var(--ok-key-special-bg, var(--ion-color-light-shade, #e6e7ea));
      --line: var(--ok-border-color, var(--ion-border-color, #d7d8da));
      --ink: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --ink-muted: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --ink-faint: var(--ok-color-medium-tint, var(--ion-color-medium-tint, #b3b5bd));
      --brand: var(--ok-color-primary, var(--ion-color-primary, #0091ce));
      --brand-shade: var(--ok-color-primary-shade, var(--ion-color-primary-shade, #007fb5));
      --brand-fg: var(--ok-color-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --radius: var(--ok-radius, 12px);
      --key-radius: var(--ok-key-radius, 8px);

      /* Métricas de densidad touch (default). */
      --gap: 6px;
      --key-h: 48px;
      --key-min-w: 44px;
      --key-fs: 16px;
      --pad: 12px;
    }

    /* Densidad compacta (mobile / denso). */
    :host([density='compact']) {
      --gap: 4px;
      --key-h: 38px;
      --key-min-w: 34px;
      --key-fs: 14px;
      --pad: 8px;
      --radius: var(--ok-radius, 8px);
      --key-radius: var(--ok-key-radius, 6px);
    }

    .kb-wrap {
      display: flex;
      flex-direction: column;
      gap: var(--gap);
      box-sizing: border-box;
    }

    /* Tira de display (label + valor + caret). */
    .display {
      display: flex;
      align-items: center;
      gap: 8px;
      background: var(--key-bg);
      border: 1px solid var(--line);
      border-radius: var(--key-radius);
      padding: 8px 12px;
      min-height: 36px;
      box-sizing: border-box;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.95rem;
      color: var(--ink);
      font-variant-numeric: tabular-nums;
    }
    .display__label {
      font-size: 0.625rem;
      color: var(--ink-muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-family: inherit;
    }
    .display__value {
      flex: 1;
      color: var(--ink);
      letter-spacing: 0.05em;
      word-break: break-all;
      white-space: pre-wrap;
    }
    /* Caret parpadeante cuando el valor está vacío. */
    .display__caret {
      color: var(--ink-faint);
      animation: ok-kb-blink 1s step-end infinite;
    }
    @keyframes ok-kb-blink {
      50% {
        opacity: 0;
      }
    }

    .keys {
      display: flex;
      flex-direction: column;
      gap: var(--gap);
      padding: var(--pad);
      background: var(--bg);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      user-select: none;
      -webkit-user-select: none;
      touch-action: manipulation;
      box-sizing: border-box;
    }

    .row {
      display: flex;
      gap: var(--gap);
      width: 100%;
    }

    .key {
      flex: 1 1 var(--key-min-w);
      min-width: var(--key-min-w);
      height: var(--key-h);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: var(--key-bg);
      border: 1px solid var(--line);
      border-bottom-width: 2px;
      border-radius: var(--key-radius);
      color: var(--ink);
      font-family: inherit;
      font-size: var(--key-fs);
      font-weight: 500;
      cursor: pointer;
      padding: 0 2px;
      box-sizing: border-box;
      transition: background 120ms ease-out, transform 120ms ease-out,
        border-color 120ms ease-out;
      font-variant-numeric: tabular-nums;
    }
    .key:hover {
      background: var(--key-bg-hover);
    }
    .key:active {
      transform: scale(0.97);
    }
    .key:focus-visible {
      outline: 2px solid var(--brand);
      outline-offset: 2px;
    }

    /* Anchos relativos por flex-grow. */
    .key--wide {
      flex-grow: 1.5;
    }
    .key--xwide {
      flex-grow: 2;
    }
    .key--space {
      flex-grow: 6;
    }
    .key--enter {
      background: var(--brand);
      color: var(--brand-fg);
      border-color: transparent;
      flex-grow: 1.6;
    }
    .key--enter:hover {
      background: var(--brand-shade);
    }

    /* Teclas de acción/modificadores. */
    .key--shift,
    .key--del,
    .key--num,
    .key--mod {
      background: var(--special-bg);
      color: var(--ink-muted);
      font-size: 0.8125rem;
      font-weight: 500;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      flex-grow: 1.4;
    }
    .key--shift:hover,
    .key--del:hover,
    .key--num:hover,
    .key--mod:hover {
      background: var(--key-bg-hover);
      color: var(--ink);
    }

    /* Shift activo: la tecla shift se ilumina con marca. */
    :host([is-shift]) .key--shift {
      background: var(--brand);
      color: var(--brand-fg);
      border-color: transparent;
    }
    /* Shift activo: las teclas de carácter muestran mayúscula. */
    :host([is-shift]) .key--char {
      text-transform: uppercase;
    }

    /* Modo numérico: rejilla de 3 columnas centrada. */
    .keys--numeric {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: var(--gap);
      max-width: 320px;
    }
    .keys--numeric .row {
      display: contents;
    }
    .keys--numeric .key {
      flex: initial;
      font-size: 1.375rem;
      font-weight: 600;
    }
  `;

  /** Distribución: qwerty (texto completo), numeric (rejilla 3-col), symbol. */
  @property({ reflect: true }) layout: OkKeyboardLayout = 'qwerty';

  /** Densidad de las teclas. */
  @property({ reflect: true }) density: OkKeyboardDensity = 'touch';

  /** Valor actual del campo (controlado o no). */
  @property() value = '';

  /** Muestra la tira de display companion (label + valor + caret). */
  @property({ type: Boolean, attribute: 'show-display' }) showDisplay = false;

  /** Etiqueta de la tira de display. */
  @property({ attribute: 'display-label' }) displayLabel = 'Entrada';

  /** Estado de shift (mayúsculas). Reflejado para CSS. */
  @property({ type: Boolean, reflect: true, attribute: 'is-shift' }) isShift = false;

  /** Layout interno activo cuando el usuario alterna 123/ABC. */
  @state() private activeLayout: OkKeyboardLayout = 'qwerty';

  protected willUpdate(changed: Map<string, unknown>): void {
    // Sincroniza el layout interno cuando cambia la prop pública.
    if (changed.has('layout')) {
      this.activeLayout = this.layout;
    }
  }

  private get rows(): KeyDef[][] {
    switch (this.activeLayout) {
      case 'numeric':
        return NUMERIC;
      case 'symbol':
        return SYMBOL;
      default:
        return QWERTY;
    }
  }

  private emit<T>(name: string, detail: T): void {
    this.dispatchEvent(new CustomEvent<T>(name, { detail, bubbles: true, composed: true }));
  }

  private setValue(next: string): void {
    this.value = next;
    this.emit('ok-input', { value: next });
  }

  private handleKey(k: KeyDef): void {
    switch (k.kind) {
      case 'shift':
        this.isShift = !this.isShift;
        return;
      case 'del':
        this.setValue(this.value.slice(0, -1));
        this.emit('ok-key', { key: 'Backspace' });
        return;
      case 'enter':
        this.emit('ok-key', { key: 'Enter' });
        this.emit('ok-enter', { value: this.value });
        return;
      case 'num':
        // Alterna entre numérico/símbolos y QWERTY.
        this.activeLayout = this.activeLayout === 'qwerty' ? 'symbol' : 'qwerty';
        return;
      default: {
        // Tecla de carácter (incluye space, mod y los caracteres normales).
        let ch = k.base;
        if (this.isShift && ch.length === 1 && ch !== ' ' && ch !== '\n') {
          ch = ch.toUpperCase();
        }
        this.setValue(this.value + ch);
        this.emit('ok-key', { key: ch });
        // El shift en QWERTY es de una sola pulsación (como un teclado real táctil).
        if (this.isShift && k.kind !== 'mod') {
          this.isShift = false;
        }
      }
    }
  }

  private renderKey(k: KeyDef) {
    const isChar = !k.kind || k.kind === 'space' || k.kind === 'mod';
    const cls = [
      'key',
      isChar ? 'key--char' : '',
      k.kind ? `key--${k.kind}` : '',
    ]
      .filter(Boolean)
      .join(' ');

    let label = k.label ?? k.base;
    // En shift, las teclas de carácter de una letra muestran su mayúscula.
    if (this.isShift && isChar && k.base.length === 1 && k.base !== ' ' && k.base !== '\n') {
      label = k.base.toUpperCase();
    }

    return html`
      <button
        type="button"
        class=${cls}
        part="key"
        aria-label=${k.kind === 'space' ? 'espacio' : k.kind === 'del' ? 'borrar' : k.kind === 'enter' ? 'intro' : label}
        @click=${() => this.handleKey(k)}
      >
        ${label}
      </button>
    `;
  }

  private renderDisplay() {
    if (!this.showDisplay) return null;
    return html`
      <div class="display" part="display">
        <span class="display__label">${this.displayLabel}</span>
        <span class="display__value"
          >${this.value}${this.value.length === 0
            ? html`<span class="display__caret">_</span>`
            : null}</span
        >
      </div>
    `;
  }

  render(): unknown {
    const numeric = this.activeLayout === 'numeric';
    return html`
      <div class="kb-wrap">
        ${this.renderDisplay()}
        <div
          class=${`keys${numeric ? ' keys--numeric' : ''}`}
          role="group"
          aria-label="Teclado en pantalla"
        >
          ${this.rows.map(
            (row) => html`<div class="row" role="row">${row.map((k) => this.renderKey(k))}</div>`
          )}
        </div>
      </div>
    `;
  }
}

define('ok-keyboard', OkKeyboard);

declare global {
  interface HTMLElementTagNameMap {
    'ok-keyboard': OkKeyboard;
  }
}
