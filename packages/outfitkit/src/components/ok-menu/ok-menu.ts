import { LitElement, html, css, nothing } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';
import { computeAnchor } from '../../base/anchor.js';

// Entrada de un menú desplegable / contextual. La aporta el consumidor vía la prop `.items`.
// Puede ser una acción (hoja), un divisor, una etiqueta de sección, o un submenú (`children`).
export interface OkMenuEntry {
  /** Identificador único de la entrada (clave que se emite en `ok-select`). */
  id?: string;
  /** Texto visible de la entrada. */
  label?: string;
  /** Nombre de un ionicon (o SVG/`data:` ya resuelto) pintado antes del label. */
  icon?: string;
  /** Atajo de teclado mostrado a la derecha en mono (decorativo, p.ej. "⌘S"). */
  shortcut?: string;
  /** Pinta la entrada en color de peligro (borrar, etc.). */
  danger?: boolean;
  /** Deshabilita la entrada (no seleccionable, no abre submenú). */
  disabled?: boolean;
  /** Estado marcado para roles checkbox/radio (dibuja el check a la izquierda). */
  checked?: boolean;
  /** Rol ARIA del item: por defecto `menuitem`. */
  role?: 'menuitem' | 'checkbox' | 'radio';
  /** Si es `true`, dibuja una línea divisoria en lugar de una entrada. */
  divider?: boolean;
  /** Si está presente (sin `id`/acción), dibuja una etiqueta de sección en mayúsculas. */
  section?: string;
  /** Hijos: si tiene, la entrada abre un submenú en cascada (chevron, hover/teclado). */
  children?: OkMenuEntry[];
}

/** Lado horizontal/vertical de anclaje del panel respecto al disparador. */
export type OkMenuAnchor = 'br' | 'bl' | 'tr' | 'tl';
/** Ancho mínimo del panel. */
export type OkMenuWidth = 'sm' | 'md' | 'lg';
/** Modo de disparo: click en el trigger, o contextmenu (click derecho) en el área. */
export type OkMenuTrigger = 'click' | 'context';

// ok-menu — menú desplegable / contextual reutilizable construido sobre primitivos propios
// (Ionic solo para `ion-icon`, que registra el host). Soporta:
//   • items declarativos (acción, divisor, sección, checkbox/radio con check CSS, submenú);
//   • modo `click` (panel anclado al disparador del slot) o `context` (abre en el cursor con
//     animación scale+fade sobre el contenido del slot por defecto);
//   • submenús en cascada con chevron, hover y navegación por teclado;
//   • atajos mono alineados a la derecha (look de ok-kbd) y entradas peligro;
//   • cabecera opcional de usuario vía el slot `header`.
// El panel es `position:absolute` (NO fixed) y usa `computeAnchor` para voltear de lado si no
// cabe en el viewport. CSP-safe (sin eval/new Function). Accesible (role=menu, flechas, Esc).
// Eventos (bubbles + composed):
//   • `ok-select` detail { id } — al activar una entrada hoja.
//   • `ok-open`   detail { open } — al abrir/cerrar.
export class OkMenu extends LitElement {
  static styles = css`
    :host {
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --bg: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #ffffff)));
      --color: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --color-muted: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --hover-bg: var(--ok-hover, rgba(var(--ion-text-color-rgb, 31, 41, 51), 0.06));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 31, 41, 51), 0.12));
      --divider-color: var(--ok-divider, rgba(var(--ion-text-color-rgb, 31, 41, 51), 0.1));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --danger-color: var(--ok-danger, var(--ion-color-danger, #eb445a));
      --radius: var(--ok-radius, 12px);
      --radius-item: var(--ok-radius-item, 8px);
      --shadow: var(--ok-shadow, 0 8px 28px rgba(0, 0, 0, 0.16));
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
      --font-mono: var(--ok-font-mono, ui-monospace, 'SF Mono', 'Roboto Mono', monospace);

      display: block;
      width: 100%;
      position: relative;
      color: var(--color);
      font-family: var(--font);
    }

    /* Envoltorio del disparador (slot por defecto). Inline-block para no estirar el trigger. */
    .anchor {
      display: contents;
    }

    /* Panel flotante: absolute respecto al host (NO fixed, evita problemas con ancestros
       transformados). El lado se decide con computeAnchor (.end / .above). */
    .panel {
      position: absolute;
      z-index: 1000;
      min-width: 200px;
      background: var(--bg);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 6px;
      box-sizing: border-box;
      font-size: 0.875rem;
      /* Posición base por anchor; computeAnchor puede voltear vía .end/.above. */
    }
    .panel.sm {
      min-width: 160px;
    }
    .panel.md {
      min-width: 200px;
    }
    .panel.lg {
      min-width: 240px;
    }

    /* Anchors básicos (modo click). El default abre abajo-izquierda. */
    .panel.bl {
      left: 0;
      top: 100%;
      margin-top: 4px;
    }
    .panel.br {
      right: 0;
      top: 100%;
      margin-top: 4px;
    }
    .panel.tl {
      left: 0;
      bottom: 100%;
      margin-bottom: 4px;
    }
    .panel.tr {
      right: 0;
      bottom: 100%;
      margin-bottom: 4px;
    }
    /* Volteos calculados en runtime por computeAnchor. */
    .panel.flip-end {
      left: auto;
      right: 0;
    }
    .panel.flip-start {
      right: auto;
      left: 0;
    }
    .panel.flip-above {
      top: auto;
      bottom: 100%;
      margin-top: 0;
      margin-bottom: 4px;
    }
    .panel.flip-below {
      bottom: auto;
      top: 100%;
      margin-bottom: 0;
      margin-top: 4px;
    }

    /* Modo contextual: posicionado por coordenadas; animación pop scale+fade. */
    .panel.context {
      top: var(--ctx-y, 0);
      left: var(--ctx-x, 0);
      margin: 0;
      animation: ok-menu-pop 120ms ease-out;
    }
    @keyframes ok-menu-pop {
      from {
        opacity: 0;
        transform: scale(0.96) translateY(-2px);
      }
      to {
        opacity: 1;
        transform: scale(1) translateY(0);
      }
    }
    @media (prefers-reduced-motion: reduce) {
      .panel.context {
        animation: none;
      }
    }

    /* Cabecera de usuario opcional (slot=header). */
    .header {
      padding: 8px 10px 10px;
      margin: -2px 0 4px;
      border-bottom: 1px solid var(--divider-color);
    }
    .header::slotted(*) {
      font-size: 0.8125rem;
    }

    ul {
      list-style: none;
      margin: 0;
      padding: 0;
    }

    /* Entrada de menú (botón). */
    .item {
      display: flex;
      align-items: center;
      gap: 10px;
      width: 100%;
      box-sizing: border-box;
      padding: 7px 10px;
      border: 0;
      background: transparent;
      color: inherit;
      font: inherit;
      text-align: left;
      cursor: pointer;
      border-radius: var(--radius-item);
      position: relative;
    }
    .item:hover:not(.disabled),
    .item:focus-visible:not(.disabled) {
      background: var(--hover-bg);
      outline: none;
    }
    .item.disabled {
      opacity: 0.4;
      cursor: default;
      pointer-events: none;
    }
    .item.danger {
      color: var(--danger-color);
    }
    .item ion-icon {
      width: 16px;
      height: 16px;
      font-size: 16px;
      flex-shrink: 0;
      color: var(--color-muted);
    }
    .item.danger ion-icon {
      color: var(--danger-color);
    }
    .label {
      flex: 1;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    /* Atajo mono alineado a la derecha (look ok-kbd). */
    .shortcut {
      margin-left: auto;
      flex-shrink: 0;
      font-family: var(--font-mono);
      font-size: 0.6875rem;
      line-height: 1;
      color: var(--color-muted);
      padding: 2px 5px;
      border: 1px solid var(--border-color);
      border-radius: 5px;
      background: var(--hover-bg);
    }

    /* Sangrado y check para checkbox/radio. */
    .item.checkable {
      padding-left: 30px;
    }
    .check {
      position: absolute;
      left: 10px;
      top: 50%;
      transform: translateY(-50%);
      width: 13px;
      height: 13px;
      flex-shrink: 0;
    }
    .check.radio {
      border-radius: 50%;
    }
    .check.checked.checkbox {
      /* Tick dibujado con dos gradientes (sin SVG, CSP-safe). */
      background: linear-gradient(45deg, transparent 28%, var(--primary-color) 28% 40%, transparent 40%)
          bottom left / 55% 60% no-repeat,
        linear-gradient(-45deg, transparent 28%, var(--primary-color) 28% 40%, transparent 40%) top right /
          70% 70% no-repeat;
    }
    .check.checked.radio {
      background: var(--primary-color);
      box-shadow: inset 0 0 0 3px var(--bg), inset 0 0 0 4px var(--primary-color);
    }

    /* Chevron de submenú. */
    .chevron {
      margin-left: auto;
      flex-shrink: 0;
      width: 7px;
      height: 7px;
      border-right: 1.5px solid var(--color-muted);
      border-top: 1.5px solid var(--color-muted);
      transform: rotate(45deg);
    }
    .item.has-sub {
      padding-right: 20px;
    }

    /* Divisor y etiqueta de sección. */
    .divider {
      height: 1px;
      background: var(--divider-color);
      margin: 6px 4px;
    }
    .section {
      padding: 6px 10px 4px;
      font-size: 0.6875rem;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--color-muted);
    }

    /* Submenú en cascada: absolute al lado de su <li> padre. */
    li.sub-host {
      position: relative;
    }
    .submenu {
      position: absolute;
      top: -7px;
      left: calc(100% + 4px);
      min-width: 190px;
      background: var(--bg);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 6px;
      box-sizing: border-box;
      z-index: 1;
    }
    .submenu.left {
      left: auto;
      right: calc(100% + 4px);
    }
  `;

  /** Entradas del menú (array declarativo). */
  @property({ attribute: false }) items: OkMenuEntry[] = [];

  /** Modo de disparo: `click` (sobre el slot) o `context` (click derecho). */
  @property() trigger: OkMenuTrigger = 'click';

  /** Lado de anclaje en modo click. */
  @property() anchor: OkMenuAnchor = 'bl';

  /** Ancho mínimo del panel. */
  @property() width: OkMenuWidth = 'md';

  /** Estado abierto/cerrado (reflejado). */
  @property({ type: Boolean, reflect: true }) open = false;

  /** Volteo horizontal calculado por computeAnchor (true → alinear a la derecha). */
  @state() private flipEnd = false;
  /** Volteo vertical calculado por computeAnchor (true → abrir hacia arriba). */
  @state() private flipAbove = false;
  /** Coordenadas del cursor en modo contextual (relativas al host). */
  @state() private ctxX = 0;
  @state() private ctxY = 0;
  /** id del submenú abierto (uno por nivel raíz). */
  @state() private openSub: string | null = null;

  private onDocPointer = (e: Event): void => {
    if (!this.open) return;
    const path = e.composedPath();
    if (!path.includes(this)) this.close();
  };

  private onKeydown = (e: KeyboardEvent): void => {
    if (!this.open) return;
    if (e.key === 'Escape') {
      e.stopPropagation();
      this.close();
      return;
    }
    const focusables = this.focusableItems();
    if (focusables.length === 0) return;
    const active = (this.shadowRoot?.activeElement ?? null) as HTMLElement | null;
    const idx = active ? focusables.indexOf(active) : -1;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      focusables[(idx + 1) % focusables.length].focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      focusables[(idx - 1 + focusables.length) % focusables.length].focus();
    } else if (e.key === 'Home') {
      e.preventDefault();
      focusables[0].focus();
    } else if (e.key === 'End') {
      e.preventDefault();
      focusables[focusables.length - 1].focus();
    }
  };

  private focusableItems(): HTMLElement[] {
    return Array.from(
      this.renderRoot.querySelectorAll<HTMLElement>('.panel > ul > li > .item:not(.disabled)'),
    );
  }

  connectedCallback(): void {
    super.connectedCallback();
    document.addEventListener('pointerdown', this.onDocPointer, true);
    document.addEventListener('keydown', this.onKeydown, true);
    this.addEventListener('contextmenu', this.onContextMenu);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    document.removeEventListener('pointerdown', this.onDocPointer, true);
    document.removeEventListener('keydown', this.onKeydown, true);
    this.removeEventListener('contextmenu', this.onContextMenu);
  }

  private onContextMenu = (e: MouseEvent): void => {
    if (this.trigger !== 'context') return;
    e.preventDefault();
    const rect = this.getBoundingClientRect();
    this.ctxX = e.clientX - rect.left;
    this.ctxY = e.clientY - rect.top;
    this.openMenu();
  };

  // Toggle del modo click: invocado desde el slot por defecto.
  private onTriggerClick = (): void => {
    if (this.trigger !== 'click') return;
    this.open ? this.close() : this.openMenu();
  };

  private openMenu(): void {
    if (this.open) return;
    this.openSub = null;
    this.open = true;
    this.dispatchEvent(
      new CustomEvent('ok-open', { detail: { open: true }, bubbles: true, composed: true }),
    );
    // Tras montar el panel, recalcular el lado de anclaje (solo modo click).
    this.updateComplete.then(() => {
      this.measureAnchor();
      const first = this.focusableItems()[0];
      first?.focus();
    });
  }

  private close(): void {
    if (!this.open) return;
    this.open = false;
    this.openSub = null;
    this.dispatchEvent(
      new CustomEvent('ok-open', { detail: { open: false }, bubbles: true, composed: true }),
    );
  }

  // Recalcula volteo con computeAnchor (modo click). En contextual se respeta el cursor.
  private measureAnchor(): void {
    if (this.trigger === 'context') return;
    const panel = this.renderRoot.querySelector('.panel') as HTMLElement | null;
    if (!panel) return;
    const side = computeAnchor(this, panel, { gap: 4 });
    this.flipEnd = side.end;
    this.flipAbove = side.above;
  }

  // Activa una entrada hoja: emite ok-select y cierra. Submenús/divisores/secciones no aplican.
  private activate(entry: OkMenuEntry): void {
    if (entry.disabled || entry.divider || entry.section != null) return;
    if (entry.children && entry.children.length) return;
    if (entry.id != null) {
      this.dispatchEvent(
        new CustomEvent('ok-select', { detail: { id: entry.id }, bubbles: true, composed: true }),
      );
    }
    this.close();
  }

  // Un icono es «SVG ya resuelto» si empieza por `<` o es `data:` → va a la prop `icon` de ion-icon.
  private isResolvedSvg(icon: string): boolean {
    return /^\s*</.test(icon) || icon.startsWith('data:');
  }

  private renderIcon(icon: string): unknown {
    return this.isResolvedSvg(icon)
      ? html`<ion-icon .icon=${icon}></ion-icon>`
      : html`<ion-icon .name=${icon}></ion-icon>`;
  }

  private renderEntry(entry: OkMenuEntry, key: string): unknown {
    if (entry.divider) return html`<li><div class="divider" role="separator"></div></li>`;
    if (entry.section != null)
      return html`<li><div class="section">${entry.section}</div></li>`;

    const hasSub = !!(entry.children && entry.children.length);
    const checkable = entry.role === 'checkbox' || entry.role === 'radio';
    const ariaRole =
      entry.role === 'checkbox'
        ? 'menuitemcheckbox'
        : entry.role === 'radio'
          ? 'menuitemradio'
          : 'menuitem';

    return html`<li class=${hasSub ? 'sub-host' : ''}>
      <button
        type="button"
        class="item${entry.danger ? ' danger' : ''}${entry.disabled ? ' disabled' : ''}${checkable
          ? ' checkable'
          : ''}${hasSub ? ' has-sub' : ''}"
        role=${ariaRole}
        aria-disabled=${entry.disabled ? 'true' : 'false'}
        aria-checked=${checkable ? (entry.checked ? 'true' : 'false') : nothing}
        aria-haspopup=${hasSub ? 'menu' : nothing}
        aria-expanded=${hasSub ? (this.openSub === key ? 'true' : 'false') : nothing}
        tabindex=${entry.disabled ? -1 : 0}
        @click=${() => (hasSub ? this.toggleSub(key) : this.activate(entry))}
        @mouseenter=${() => hasSub && (this.openSub = key)}
        @focus=${() => hasSub && (this.openSub = key)}
        @keydown=${(e: KeyboardEvent) => this.onItemKeydown(e, entry, key, hasSub)}
      >
        ${checkable
          ? html`<span
              class="check ${entry.role} ${entry.checked ? 'checked' : ''}"
              aria-hidden="true"
            ></span>`
          : entry.icon
            ? this.renderIcon(entry.icon)
            : nothing}
        <span class="label">${entry.label ?? ''}</span>
        ${entry.shortcut ? html`<kbd class="shortcut">${entry.shortcut}</kbd>` : nothing}
        ${hasSub ? html`<span class="chevron" aria-hidden="true"></span>` : nothing}
      </button>
      ${hasSub && this.openSub === key
        ? html`<ul class="submenu${this.flipEnd ? ' left' : ''}" role="menu">
            ${entry.children!.map((child, i) => this.renderEntry(child, `${key}.${i}`))}
          </ul>`
        : nothing}
    </li>`;
  }

  private toggleSub(key: string): void {
    this.openSub = this.openSub === key ? null : key;
  }

  private onItemKeydown(
    e: KeyboardEvent,
    entry: OkMenuEntry,
    key: string,
    hasSub: boolean,
  ): void {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      hasSub ? this.toggleSub(key) : this.activate(entry);
    } else if (e.key === 'ArrowRight' && hasSub) {
      e.preventDefault();
      this.openSub = key;
      this.updateComplete.then(() => {
        const first = this.renderRoot.querySelector<HTMLElement>('.submenu .item:not(.disabled)');
        first?.focus();
      });
    } else if (e.key === 'ArrowLeft' && key.includes('.')) {
      e.preventDefault();
      this.openSub = null;
    }
  }

  render(): unknown {
    const panelClasses = ['panel', this.width];
    if (this.trigger === 'context') {
      panelClasses.push('context');
    } else {
      panelClasses.push(this.anchor);
      if (this.flipEnd) panelClasses.push('flip-end');
      if (this.flipAbove) panelClasses.push('flip-above');
    }

    const panelStyle =
      this.trigger === 'context' ? `--ctx-x:${this.ctxX}px;--ctx-y:${this.ctxY}px` : '';

    return html`
      <span class="anchor" @click=${this.onTriggerClick}>
        <slot></slot>
      </span>
      ${this.open
        ? html`<div
            class=${panelClasses.join(' ')}
            style=${panelStyle}
            role="menu"
            @click=${(e: Event) => e.stopPropagation()}
          >
            <div class="header"><slot name="header"></slot></div>
            <ul>
              ${this.items.map((entry, i) => this.renderEntry(entry, String(i)))}
            </ul>
          </div>`
        : nothing}
    `;
  }
}

define('ok-menu', OkMenu);

declare global {
  interface HTMLElementTagNameMap {
    'ok-menu': OkMenu;
  }
}
