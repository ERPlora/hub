import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-kbd — chip(s) de keycap (tecla de teclado). Presentacional, sin comportamiento.
// Porta el look de `.ux-keyboard__key` (mono, borde inferior grueso = relieve 3D, mods uppercase).
// Uso: <ok-kbd keys="cmd k"></ok-kbd> → renderiza ⌘ + K como caps unidas por "+".

/** Tamaño del keycap. */
export type OkKbdSize = 'sm' | 'md';

// Teclas modificadoras: bg más pesado, negrita, uppercase.
const MOD_KEYS = new Set(['cmd', 'command', 'ctrl', 'control', 'shift', 'alt', 'option', 'opt', 'meta', 'win', 'super']);

// Símbolos bonitos para teclas comunes (mantiene la entrada en texto plano).
const GLYPHS: Record<string, string> = {
  cmd: '⌘',
  command: '⌘',
  meta: '⌘',
  super: '⌘',
  win: '⊞',
  ctrl: 'Ctrl',
  control: 'Ctrl',
  shift: 'Shift',
  alt: 'Alt',
  option: '⌥',
  opt: '⌥',
  enter: '↵',
  return: '↵',
  esc: 'Esc',
  escape: 'Esc',
  tab: 'Tab',
  space: 'space',
  up: '↑',
  down: '↓',
  left: '←',
  right: '→',
  del: '⌫',
  delete: '⌫',
  backspace: '⌫',
};

export class OkKbd extends LitElement {
  static styles = css`
    :host {
      /* Átomo inline: ocupa solo su contenido. */
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      vertical-align: middle;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --bg: var(--ok-kbd-bg, var(--ion-color-light, #f4f5f8));
      --bg-mod: var(--ok-kbd-bg-mod, var(--ion-color-light-shade, #d7d8da));
      --border-color: var(--ok-kbd-border, var(--ion-border-color, #c8c9cc));
      --color: var(--ok-kbd-color, var(--ion-color-medium-shade, #808289));
      --color-mod: var(--ok-kbd-color-mod, var(--ion-text-color, #1f2933));
      --radius: var(--ok-kbd-radius, 4px);
      --font-mono: var(--ok-kbd-font, ui-monospace, 'SFMono-Regular', 'Menlo', 'Consolas', monospace);
    }

    .key {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      box-sizing: border-box;
      min-width: 22px;
      height: 22px;
      padding: 0 5px;
      background: var(--bg);
      border: 1px solid var(--border-color);
      /* Relieve 3D: borde inferior más grueso. */
      border-bottom-width: 3px;
      border-radius: var(--radius);
      font-family: var(--font-mono);
      font-size: 11px;
      font-weight: 500;
      line-height: 1;
      color: var(--color);
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }

    /* Tamaño compacto. */
    :host([size='sm']) .key {
      min-width: 18px;
      height: 18px;
      padding: 0 4px;
      font-size: 10px;
      border-bottom-width: 2px;
    }

    /* Modificadores: fondo más pesado, negrita, uppercase. */
    .key.mod {
      background: var(--bg-mod);
      color: var(--color-mod);
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      font-size: 10px;
    }

    :host([size='sm']) .key.mod {
      font-size: 9px;
    }

    /* Separador "+" entre teclas en modo combo. */
    .plus {
      font-size: 10px;
      color: var(--color);
      opacity: 0.6;
      user-select: none;
    }
  `;

  /** Teclas separadas por espacio (p.ej. "cmd k" o "ctrl shift n"). */
  @property() keys = '';

  /** Tamaño del keycap. */
  @property({ reflect: true }) size: OkKbdSize = 'md';

  /** Si es combo, inserta separadores "+" entre teclas. Por defecto true. */
  @property({ type: Boolean }) combo = true;

  // Divide `keys` en tokens normalizados (sin vacíos).
  private parseKeys(): string[] {
    return this.keys
      .split(/\s+/)
      .map((k) => k.trim())
      .filter((k) => k.length > 0);
  }

  // ¿Es una tecla modificadora?
  private isMod(token: string): boolean {
    return MOD_KEYS.has(token.toLowerCase());
  }

  // Etiqueta visible: glifo bonito si existe, si no la tecla tal cual (en mayúscula si es 1 char).
  private label(token: string): string {
    const glyph = GLYPHS[token.toLowerCase()];
    if (glyph) return glyph;
    return token.length === 1 ? token.toUpperCase() : token;
  }

  render(): unknown {
    const tokens = this.parseKeys();
    return tokens.map((token, i) => {
      const mod = this.isMod(token);
      const cap = html`<kbd
        class="key ${mod ? 'mod' : ''}"
        aria-label=${token}
        >${this.label(token)}</kbd
      >`;
      // Inserta "+" entre teclas cuando combo está activo.
      const sep = this.combo && i < tokens.length - 1 ? html`<span class="plus" aria-hidden="true">+</span>` : null;
      return html`${cap}${sep}`;
    });
  }
}

define('ok-kbd', OkKbd);

declare global {
  interface HTMLElementTagNameMap {
    'ok-kbd': OkKbd;
  }
}
