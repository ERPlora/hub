import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Item de un menú (puede ser hoja, separador, o submenú vía `children`).
// Lo aporta el consumidor vía la prop `.menus`.
export interface OkMenuItem {
  /** Identificador único del item (clave de selección). */
  id: string;
  /** Texto visible del item (ignorado si `separator`). */
  label?: string;
  /** Nombre de un ionicon opcional, mostrado antes del label. */
  icon?: string;
  /** Atajo de teclado mostrado a la derecha (solo decorativo, p.ej. "⌘S"). */
  shortcut?: string;
  /** Deshabilita el item (no seleccionable, no abre submenú). */
  disabled?: boolean;
  /** Si es `true`, dibuja una línea divisoria en lugar de un item. */
  separator?: boolean;
  /** Hijos: si tiene, el item abre un submenú al lado (hover/flecha). */
  children?: OkMenuItem[];
}

// Menú de nivel superior (un `label` en la barra con su lista de items).
export interface OkMenu {
  /** Identificador único del menú. */
  id: string;
  /** Texto visible en la barra (Archivo / Editar / Ver…). */
  label: string;
  /** Items del desplegable. */
  items: OkMenuItem[];
}

// ok-menubar — barra de menús de escritorio (estilo app: Archivo / Editar / Ver…).
// Barra horizontal con los `label` de cada menú; click abre un dropdown con sus items (icono
// opcional, atajo a la derecha, separadores y submenús que se abren al lado en hover).
// Comportamiento menubar clásico: con un menú abierto, pasar el ratón por otro lo cambia.
// Navegación con teclado (flechas, Enter, Esc). Cierra al click fuera o Esc.
// AUTOCONTENIDO: CSS propio en el shadow (sin Ionic salvo `ion-icon`, que registra el host).
// Responsive: en móvil colapsa a un botón hamburguesa que despliega los menús apilados (acordeón).
//   • prop `.menus` → Array<OkMenu>
// Eventos (bubbles + composed):
//   • `ok-select` detail { id, item } → click en un item hoja (no separador/disabled)
//   • `ok-open`   detail { open }     → apertura/cierre de cualquier menú

// Textos traducibles (default inglés). Pásalos desde fuera vía la prop `labels`.
export interface OkMenubarLabels {
  /** aria-label y texto del botón hamburguesa móvil. */
  menu: string;
}

const DEFAULT_LABELS: OkMenubarLabels = {
  menu: 'Menu',
};

export class OkMenubar extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.55));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --primary-contrast: var(--ok-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --hover-bg: var(--ok-hover, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.06));
      --bar-bg: var(--ok-surface, var(--ion-toolbar-background, var(--ion-background-color, #ffffff)));
      --panel-bg: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #ffffff)));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.12));
      --border-radius: var(--ok-radius, 8px);
      --shadow: var(--ok-shadow, 0 8px 28px rgba(0, 0, 0, 0.18));
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
      --mobile-breakpoint: var(--ok-menubar-mobile, 640px);

      /* Por defecto ocupa el ancho del contenedor (barra de escritorio). */
      display: block;
      width: 100%;
      color: var(--color);
      font-family: var(--font);
      font-size: 0.92rem;
    }

    /* ─── Barra horizontal (desktop) ─────────────────────────────────────── */
    .bar {
      display: flex;
      align-items: stretch;
      gap: 0.1rem;
      width: 100%;
      box-sizing: border-box;
      padding: 0.15rem 0.25rem;
      background: var(--bar-bg);
      border-bottom: 1px solid var(--border-color);
    }
    /* Botón de cada menú de nivel superior. */
    .top {
      position: relative;
      display: inline-flex;
      align-items: center;
      padding: 0.35rem 0.7rem;
      border: 0;
      background: none;
      color: inherit;
      font: inherit;
      cursor: pointer;
      border-radius: var(--border-radius);
      white-space: nowrap;
      transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease), box-shadow var(--ok-transition, 150ms ease),
        transform 120ms ease;
    }
    .top.open {
      background: var(--hover-bg);
    }
    @media (hover: hover) {
      .top:hover {
        background: var(--hover-bg);
      }
    }
    .top:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    .top.open {
      background: var(--primary-color);
      color: var(--primary-contrast);
    }

    /* ─── Dropdown / submenú (panel propio) ──────────────────────────────── */
    .panel {
      position: absolute;
      z-index: 1000;
      min-width: 220px;
      max-width: 340px;
      padding: 0.3rem;
      background: var(--panel-bg);
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
      box-shadow: var(--shadow);
      box-sizing: border-box;
    }
    /* Dropdown de un menú de la barra: bajo el botón, alineado a la izquierda. */
    .panel.root {
      top: calc(100% + 4px);
      left: 0;
    }
    /* Submenú: al lado derecho del item padre. */
    .panel.sub {
      top: -0.3rem;
      left: calc(100% + 2px);
    }

    .item {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      width: 100%;
      box-sizing: border-box;
      padding: 0.45rem 0.6rem;
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
    .item.active:not(.disabled) {
      background: var(--hover-bg);
    }
    @media (hover: hover) {
      .item:hover:not(.disabled) {
        background: var(--hover-bg);
      }
    }
    .item:active:not(.disabled) {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    .item.disabled {
      opacity: 0.45;
      cursor: not-allowed;
    }
    /* Hueco fijo para el icono (alinea labels aunque algunos no tengan icono). */
    .item .icon {
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 1.15rem;
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
    /* Atajo de teclado a la derecha (tenue). */
    .item .shortcut {
      flex: 0 0 auto;
      margin-left: 1rem;
      font-size: 0.8em;
      color: var(--color-muted);
      letter-spacing: 0.02em;
    }
    /* Flecha de submenú. */
    .item .caret {
      flex: 0 0 auto;
      margin-left: auto;
      font-size: 0.9rem;
      color: var(--color-muted);
    }
    .item .shortcut + .caret {
      margin-left: 0.4rem;
    }
    /* Separador entre items. */
    .separator {
      height: 1px;
      margin: 0.25rem 0.4rem;
      background: var(--border-color);
    }
    .item-wrap {
      position: relative;
    }

    /* ─── Móvil (hamburguesa + acordeón) ─────────────────────────────────── */
    .burger {
      display: none;
      align-items: center;
      gap: 0.5rem;
      padding: 0.45rem 0.7rem;
      border: 0;
      background: none;
      color: inherit;
      font: inherit;
      cursor: pointer;
      border-radius: var(--border-radius);
      transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease), box-shadow var(--ok-transition, 150ms ease),
        transform 120ms ease;
    }
    @media (hover: hover) {
      .burger:hover {
        background: var(--hover-bg);
      }
    }
    .burger:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    @media (prefers-reduced-motion: reduce) {
      .top:hover,
      .top:active,
      .item:hover,
      .item:active,
      .burger:hover,
      .burger:active,
      .acc-head:hover,
      .acc-head:active {
        transform: none;
      }
    }
    .burger ion-icon {
      font-size: 1.25rem;
    }
    .accordion {
      display: none;
      flex-direction: column;
      padding: 0.25rem;
      background: var(--panel-bg);
      border-bottom: 1px solid var(--border-color);
    }
    /* Cabecera de cada menú dentro del acordeón. */
    .acc-head {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      width: 100%;
      box-sizing: border-box;
      padding: 0.55rem 0.6rem;
      border: 0;
      background: none;
      color: inherit;
      font: inherit;
      font-weight: 600;
      text-align: left;
      cursor: pointer;
      border-radius: 6px;
      transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease), box-shadow var(--ok-transition, 150ms ease),
        transform 120ms ease;
    }
    @media (hover: hover) {
      .acc-head:hover {
        background: var(--hover-bg);
      }
    }
    .acc-head:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    .acc-head .caret {
      margin-left: auto;
      transition: transform 0.18s ease;
    }
    .acc-head.open .caret {
      transform: rotate(90deg);
    }
    /* En el acordeón los items (y subitems) se indentan; sin paneles flotantes. */
    .accordion .item {
      padding-left: 1.4rem;
    }
    .accordion .item.depth-1 {
      padding-left: 2.4rem;
    }
    .accordion .item.depth-2 {
      padding-left: 3.4rem;
    }

    /* Cambio a layout móvil bajo el breakpoint. */
    @container (max-width: 640px) {
      .bar {
        display: none;
      }
      .burger {
        display: inline-flex;
      }
      .accordion {
        display: flex;
      }
    }
    /* Fallback sin container-queries: clase forzada por JS según el ancho. */
    :host(.is-mobile) .bar {
      display: none;
    }
    :host(.is-mobile) .burger {
      display: inline-flex;
    }
    :host(.is-mobile) .accordion {
      display: flex;
    }
  `;

  /** Menús de la barra (cada uno con su lista de items). */
  @property({ attribute: false }) menus: OkMenu[] = [];
  /** Textos traducibles (merge sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkMenubarLabels> = {};

  // Textos efectivos: defaults en inglés + overrides del consumidor.
  private get t(): OkMenubarLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Id del menú de la barra abierto (desktop). '' = ninguno.
  @state() private openMenuId = '';
  // Ruta de submenús abiertos (ids de items con children), del más externo al más interno.
  @state() private openPath: string[] = [];
  // Item resaltado por teclado dentro del dropdown activo (id de item).
  @state() private activeItemId = '';
  // Panel móvil (hamburguesa) abierto/cerrado.
  @state() private mobileOpen = false;
  // Menús expandidos en el acordeón móvil (set de ids).
  @state() private accExpanded = new Set<string>();
  // Modo móvil detectado por ancho (fallback sin container-queries).
  @state() private isMobile = false;

  // Observa el ancho del host para conmutar a layout móvil sin container-queries.
  private ro?: ResizeObserver;

  connectedCallback(): void {
    super.connectedCallback();
    if (typeof ResizeObserver !== 'undefined') {
      this.ro = new ResizeObserver((entries) => {
        const w = entries[0]?.contentRect.width ?? 0;
        const mobile = w > 0 && w < 640;
        if (mobile !== this.isMobile) {
          this.isMobile = mobile;
          this.classList.toggle('is-mobile', mobile);
          // Al cambiar de modo, cerramos todo para evitar estados huérfanos.
          this.closeAll();
        }
      });
      this.ro.observe(this);
    }
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.ro?.disconnect();
    this.unbind();
  }

  // ─── Listeners globales (solo activos con algo abierto) ──────────────────
  private readonly onDocClick = (e: MouseEvent): void => {
    if (!e.composedPath().includes(this)) this.closeAll();
  };
  private readonly onKeydown = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      this.closeAll();
    }
  };

  private bind(): void {
    document.addEventListener('click', this.onDocClick, true);
    document.addEventListener('keydown', this.onKeydown);
  }
  private unbind(): void {
    document.removeEventListener('click', this.onDocClick, true);
    document.removeEventListener('keydown', this.onKeydown);
  }

  // ─── Apertura/cierre de menús de la barra ───────────────────────────────
  private openMenu(menu: OkMenu): void {
    if (this.openMenuId === menu.id) return;
    const wasOpen = this.openMenuId !== '';
    this.openMenuId = menu.id;
    this.openPath = [];
    this.activeItemId = '';
    if (!wasOpen) this.bind();
    this.emitOpen(true);
  }

  private toggleMenu(menu: OkMenu): void {
    if (this.openMenuId === menu.id) this.closeAll();
    else this.openMenu(menu);
  }

  // Comportamiento menubar clásico: con un menú ya abierto, hover sobre otro lo cambia.
  private hoverMenu(menu: OkMenu): void {
    if (this.openMenuId && this.openMenuId !== menu.id) this.openMenu(menu);
  }

  private closeAll(): void {
    const wasOpen = this.openMenuId !== '' || this.mobileOpen;
    this.openMenuId = '';
    this.openPath = [];
    this.activeItemId = '';
    this.mobileOpen = false;
    this.unbind();
    if (wasOpen) this.emitOpen(false);
  }

  private emitOpen(open: boolean): void {
    this.dispatchEvent(
      new CustomEvent('ok-open', { detail: { open }, bubbles: true, composed: true }),
    );
  }

  // Abre el submenú de un item (recortando la ruta al nivel actual + este item).
  private openSub(itemId: string, level: number): void {
    this.openPath = [...this.openPath.slice(0, level), itemId];
  }
  // Al pasar el ratón por un item de nivel `level`, recorta cualquier submenú más profundo.
  private hoverItem(item: OkMenuItem, level: number): void {
    if (item.disabled || item.separator) return;
    this.activeItemId = item.id;
    if (item.children?.length) this.openSub(item.id, level);
    else this.openPath = this.openPath.slice(0, level);
  }

  // ─── Selección de un item hoja ──────────────────────────────────────────
  private selectItem(item: OkMenuItem): void {
    if (item.disabled || item.separator) return;
    if (item.children?.length) return; // los nodos con hijos no emiten select
    this.dispatchEvent(
      new CustomEvent('ok-select', {
        detail: { id: item.id, item },
        bubbles: true,
        composed: true,
      }),
    );
    this.closeAll();
  }

  // ─── Navegación con teclado dentro del dropdown activo ───────────────────
  // Lista plana de items "enfocables" (no separadores/disabled) del menú raíz abierto.
  private focusableItems(): OkMenuItem[] {
    const menu = this.menus.find((m) => m.id === this.openMenuId);
    if (!menu) return [];
    return menu.items.filter((it) => !it.separator && !it.disabled);
  }

  private moveActive(delta: number): void {
    const items = this.focusableItems();
    if (!items.length) return;
    const idx = items.findIndex((it) => it.id === this.activeItemId);
    const next = (idx + delta + items.length) % items.length;
    this.activeItemId = items[next].id;
  }

  // Maneja teclas dentro del dropdown (flechas/Enter). Esc lo gestiona el listener global.
  private onMenuKeydown(e: KeyboardEvent): void {
    if (!this.openMenuId) return;
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        this.moveActive(1);
        break;
      case 'ArrowUp':
        e.preventDefault();
        this.moveActive(-1);
        break;
      case 'ArrowRight': {
        // Abre submenú del item activo si lo tiene; si no, pasa al siguiente menú de la barra.
        const item = this.focusableItems().find((it) => it.id === this.activeItemId);
        if (item?.children?.length) {
          e.preventDefault();
          this.openSub(item.id, 0);
          const first = item.children.find((c) => !c.separator && !c.disabled);
          if (first) this.activeItemId = first.id;
        } else {
          e.preventDefault();
          this.cycleTopMenu(1);
        }
        break;
      }
      case 'ArrowLeft':
        e.preventDefault();
        if (this.openPath.length) this.openPath = this.openPath.slice(0, -1);
        else this.cycleTopMenu(-1);
        break;
      case 'Enter':
      case ' ': {
        const item = this.focusableItems().find((it) => it.id === this.activeItemId);
        if (item) {
          e.preventDefault();
          if (item.children?.length) this.openSub(item.id, 0);
          else this.selectItem(item);
        }
        break;
      }
    }
  }

  // Cambia al menú de la barra anterior/siguiente (con teclado).
  private cycleTopMenu(delta: number): void {
    if (!this.menus.length) return;
    const idx = this.menus.findIndex((m) => m.id === this.openMenuId);
    const next = (idx + delta + this.menus.length) % this.menus.length;
    this.openMenu(this.menus[next]);
  }

  // ─── Acordeón móvil ─────────────────────────────────────────────────────
  private toggleMobile(): void {
    if (this.mobileOpen) {
      this.closeAll();
    } else {
      this.mobileOpen = true;
      this.bind();
      this.emitOpen(true);
    }
  }

  private toggleAccordion(menuId: string): void {
    const next = new Set(this.accExpanded);
    next.has(menuId) ? next.delete(menuId) : next.add(menuId);
    this.accExpanded = next;
  }

  // ─── Render: dropdown (desktop) ─────────────────────────────────────────
  private renderItem(item: OkMenuItem, level: number): unknown {
    if (item.separator) return html`<div class="separator" role="separator"></div>`;
    const hasChildren = !!item.children?.length;
    const subOpen = hasChildren && this.openPath[level] === item.id;
    const active = item.id === this.activeItemId;
    const cls = ['item', item.disabled ? 'disabled' : '', active ? 'active' : '']
      .filter(Boolean)
      .join(' ');

    return html`<div class="item-wrap" @mouseenter=${() => this.hoverItem(item, level)}>
      <button
        type="button"
        class=${cls}
        role="menuitem"
        aria-haspopup=${hasChildren ? 'menu' : 'false'}
        aria-expanded=${hasChildren ? String(subOpen) : ''}
        aria-disabled=${item.disabled ? 'true' : 'false'}
        @click=${() => (hasChildren ? this.openSub(item.id, level) : this.selectItem(item))}
      >
        <span class="icon">${item.icon ? html`<ion-icon .name=${item.icon}></ion-icon>` : ''}</span>
        <span class="label">${item.label ?? ''}</span>
        ${item.shortcut ? html`<span class="shortcut">${item.shortcut}</span>` : ''}
        ${hasChildren
          ? html`<span class="caret"><ion-icon name="chevron-forward-outline"></ion-icon></span>`
          : ''}
      </button>
      ${subOpen
        ? html`<div class="panel sub" role="menu">
            ${item.children!.map((child) => this.renderItem(child, level + 1))}
          </div>`
        : ''}
    </div>`;
  }

  private renderBar(): unknown {
    return html`<div class="bar" role="menubar" @keydown=${(e: KeyboardEvent) => this.onMenuKeydown(e)}>
      ${this.menus.map((menu) => {
        const isOpen = this.openMenuId === menu.id;
        return html`<div class="item-wrap">
          <button
            type="button"
            class=${`top ${isOpen ? 'open' : ''}`.trim()}
            role="menuitem"
            aria-haspopup="menu"
            aria-expanded=${isOpen ? 'true' : 'false'}
            @click=${() => this.toggleMenu(menu)}
            @mouseenter=${() => this.hoverMenu(menu)}
          >
            ${menu.label}
          </button>
          ${isOpen
            ? html`<div class="panel root" role="menu" aria-label=${menu.label}>
                ${menu.items.map((item) => this.renderItem(item, 0))}
              </div>`
            : ''}
        </div>`;
      })}
    </div>`;
  }

  // ─── Render: acordeón móvil ─────────────────────────────────────────────
  // Render plano de items del acordeón (con indentación por profundidad).
  private renderAccItem(item: OkMenuItem, depth: number): unknown {
    if (item.separator) return html`<div class="separator" role="separator"></div>`;
    const hasChildren = !!item.children?.length;
    const cls = ['item', `depth-${Math.min(depth, 2)}`, item.disabled ? 'disabled' : '']
      .filter(Boolean)
      .join(' ');
    return html`
      <button
        type="button"
        class=${cls}
        role="menuitem"
        aria-disabled=${item.disabled ? 'true' : 'false'}
        @click=${() => this.selectItem(item)}
      >
        <span class="icon">${item.icon ? html`<ion-icon .name=${item.icon}></ion-icon>` : ''}</span>
        <span class="label">${item.label ?? ''}</span>
        ${item.shortcut ? html`<span class="shortcut">${item.shortcut}</span>` : ''}
      </button>
      ${hasChildren ? item.children!.map((c) => this.renderAccItem(c, depth + 1)) : ''}
    `;
  }

  private renderMobile(): unknown {
    return html`
      <button
        type="button"
        class="burger"
        aria-haspopup="menu"
        aria-expanded=${this.mobileOpen ? 'true' : 'false'}
        aria-label=${this.t.menu}
        @click=${() => this.toggleMobile()}
      >
        <ion-icon name="menu-outline"></ion-icon>
        <span>${this.t.menu}</span>
      </button>
      ${this.mobileOpen
        ? html`<div class="accordion" role="menu">
            ${this.menus.map((menu) => {
              const expanded = this.accExpanded.has(menu.id);
              return html`
                <button
                  type="button"
                  class=${`acc-head ${expanded ? 'open' : ''}`.trim()}
                  aria-expanded=${expanded ? 'true' : 'false'}
                  @click=${() => this.toggleAccordion(menu.id)}
                >
                  <span class="label">${menu.label}</span>
                  <span class="caret"><ion-icon name="chevron-forward-outline"></ion-icon></span>
                </button>
                ${expanded ? menu.items.map((item) => this.renderAccItem(item, 0)) : ''}
              `;
            })}
          </div>`
        : ''}
    `;
  }

  render(): unknown {
    // Se renderizan ambos layouts; el CSS (container-query o `.is-mobile`) muestra el adecuado.
    return html`${this.renderBar()}${this.renderMobile()}`;
  }

  // Activa container-queries sobre el propio host (para el breakpoint responsive del CSS).
  protected firstUpdated(): void {
    this.style.setProperty('container-type', 'inline-size');
  }
}

define('ok-menubar', OkMenubar);

declare global {
  interface HTMLElementTagNameMap {
    'ok-menubar': OkMenubar;
  }
}
