import { LitElement, html, css } from 'lit';
import { property, state, query } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Comando (entrada de la paleta). Lo aporta el consumidor vía la prop `.commands`.
export interface OkCommand {
  /** Identificador único del comando (clave de selección). */
  id: string;
  /** Texto visible principal del comando. */
  label: string;
  /** Texto secundario tenue a la derecha del label (descripción corta). */
  hint?: string;
  /** Nombre de un ionicon opcional, mostrado a la izquierda. */
  icon?: string;
  /** Grupo bajo el que se agrupa el comando (cabecera de sección). */
  group?: string;
  /** Atajo de teclado a mostrar a la derecha (decorativo, p.ej. "Cmd N"). */
  shortcut?: string;
  /** Palabras clave extra que también casan con la búsqueda (además del label). */
  keywords?: string[];
}

// ok-command-palette — paleta de comandos estilo Cmd+K (Ionic no la trae). Es un OVERLAY PROPIO
// (scrim + panel centrado-arriba) con un input de búsqueda que FILTRA por substring sobre label +
// keywords (case-insensitive) los comandos AGRUPADOS por `group`. Navegación con teclado
// (flechas mueven el resaltado, Enter ejecuta, Esc cierra) y click. AUTOCONTENIDO: CSS propio en el
// shadow (sin Ionic salvo `ion-icon`, que registra el host).
//   • prop `.commands`  → Array<OkCommand>
//   • prop `open`       → abierto/cerrado (reflejado a atributo)
//   • prop `placeholder`→ texto del input de búsqueda
//   • prop `hotkey`     → si true (def), Cmd/Ctrl+K abre/cierra globalmente
// El host es `display:contents` (el overlay va a position:fixed sobre todo).
// Métodos públicos: open() / close() / toggle().
// Eventos (bubbles + composed):
//   • `ok-select` detail { id, command }   al ejecutar un comando
//   • `ok-open`   detail { open }          al abrir/cerrar
/** Textos humanos de ok-command-palette (i18n; default inglés, override vía prop `labels`). */
export interface OkCommandPaletteLabels {
  /** Placeholder del input de búsqueda. */
  searchPlaceholder: string;
  /** aria-label del overlay (dialog). */
  dialogLabel: string;
  /** Pista visual del atajo para cerrar (tecla Escape). */
  escHint: string;
  /** Estado vacío: ningún comando coincide. */
  noMatches: string;
}

const DEFAULT_LABELS: OkCommandPaletteLabels = {
  searchPlaceholder: 'Search command…',
  dialogLabel: 'Command palette',
  escHint: 'Esc',
  noMatches: 'No matches',
};

export class OkCommandPalette extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.6));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --primary-contrast: var(--ok-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --hover-bg: var(--ok-hover, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.06));
      --active-bg: var(--ok-active, rgba(var(--ion-color-primary-rgb, 56, 128, 255), 0.14));
      --panel-bg: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #ffffff)));
      --scrim-bg: var(--ok-scrim, rgba(0, 0, 0, 0.4));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.12));
      --border-soft: var(--ok-border-soft, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.08));
      --border-radius: var(--ok-radius, 14px);
      --shadow: var(--ok-shadow, 0 18px 60px rgba(0, 0, 0, 0.28));
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* El host no ocupa caja: el overlay se posiciona fijo sobre todo. */
      display: contents;
    }

    /* Scrim a pantalla completa (cierra al click fuera del panel). */
    .scrim {
      position: fixed;
      inset: 0;
      z-index: 2000;
      display: flex;
      align-items: flex-start;
      justify-content: center;
      padding: 12vh 16px 16px;
      box-sizing: border-box;
      background: var(--scrim-bg);
      font-family: var(--font);
      color: var(--color);
    }

    /* Panel centrado-arriba: ancho web estrechado (max 560px), responsive. */
    .panel {
      width: 100%;
      max-width: 560px;
      max-height: 70vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      background: var(--panel-bg);
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
      box-shadow: var(--shadow);
      box-sizing: border-box;
    }

    /* Fila del input de búsqueda. */
    .search {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      padding: 0.85rem 1rem;
      border-bottom: 1px solid var(--border-soft);
      flex: 0 0 auto;
    }
    .search ion-icon {
      flex: 0 0 auto;
      font-size: 1.2rem;
      color: var(--color-muted);
    }
    .search input {
      flex: 1 1 auto;
      min-width: 0;
      border: 0;
      outline: none;
      background: none;
      color: inherit;
      font: inherit;
      font-size: 1rem;
    }
    .search input::placeholder {
      color: var(--color-muted);
    }
    /* Pista visual del atajo para cerrar. */
    .esc {
      flex: 0 0 auto;
      padding: 0.1rem 0.4rem;
      font-size: 0.72rem;
      color: var(--color-muted);
      border: 1px solid var(--border-color);
      border-radius: 6px;
    }

    /* Lista de resultados (scrollable). */
    .results {
      flex: 1 1 auto;
      overflow-y: auto;
      padding: 0.35rem 0;
      margin: 0;
      list-style: none;
    }
    /* Cabecera de grupo. */
    .group {
      padding: 0.5rem 1rem 0.25rem;
      font-size: 0.7rem;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--color-muted);
    }
    /* Item de comando. */
    .item {
      display: flex;
      align-items: center;
      gap: 0.7rem;
      width: 100%;
      box-sizing: border-box;
      padding: 0.55rem 1rem;
      cursor: pointer;
      user-select: none;
      transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease), box-shadow var(--ok-transition, 150ms ease),
        transform 120ms ease;
    }
    .item.active {
      background: var(--active-bg);
    }
    @media (hover: hover) {
      .item:hover {
        background: var(--hover-bg);
      }
      .item.active:hover {
        background: var(--active-bg);
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
    .item .icon {
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 22px;
      font-size: 1.15rem;
      color: var(--color-muted);
    }
    .item.active .icon {
      color: var(--primary-color);
    }
    .item .body {
      flex: 1 1 auto;
      min-width: 0;
      display: flex;
      align-items: baseline;
      gap: 0.5rem;
    }
    .item .label {
      flex: 0 1 auto;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .item .hint {
      flex: 1 1 auto;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 0.82rem;
      color: var(--color-muted);
    }
    /* Atajo del comando, alineado a la derecha. */
    .item .shortcut {
      flex: 0 0 auto;
      padding: 0.1rem 0.4rem;
      font-size: 0.72rem;
      color: var(--color-muted);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      white-space: nowrap;
    }

    /* Estado vacío (sin coincidencias). */
    .empty {
      padding: 1.5rem 1rem;
      text-align: center;
      font-size: 0.9rem;
      color: var(--color-muted);
    }

    /* En móvil el overlay es casi pantalla completa. */
    @media (max-width: 560px) {
      .scrim {
        padding: 0;
        align-items: stretch;
      }
      .panel {
        max-width: none;
        max-height: none;
        height: 100%;
        border: 0;
        border-radius: 0;
      }
    }
  `;

  /** Comandos disponibles en la paleta. */
  @property({ attribute: false }) commands: OkCommand[] = [];
  /** Abierto/cerrado (reflejado a atributo para CSS externo). */
  @property({ type: Boolean, reflect: true }) open = false;
  /** Texto guía del input de búsqueda. Si vacío, se deriva de `labels.searchPlaceholder`. */
  @property() placeholder = '';
  /** Si true, Cmd/Ctrl+K abre/cierra la paleta globalmente. */
  @property({ type: Boolean }) hotkey = true;
  /** Overrides de textos humanos (i18n). Se fusionan sobre los defaults en inglés. */
  @property({ attribute: false }) labels: Partial<OkCommandPaletteLabels> = {};

  /** Textos efectivos (defaults inglés + overrides). */
  private get t(): OkCommandPaletteLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  /** Placeholder efectivo: prop explícita o el de labels. */
  private get effectivePlaceholder(): string {
    return this.placeholder || this.t.searchPlaceholder;
  }

  // Texto de búsqueda actual.
  @state() private queryText = '';
  // Índice (sobre la lista YA filtrada y aplanada) del item resaltado.
  @state() private activeIndex = 0;

  @query('.search input') private searchInput?: HTMLInputElement;

  // Atajo global Cmd/Ctrl+K (se enlaza solo si `hotkey`).
  private readonly onGlobalKey = (e: KeyboardEvent): void => {
    if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      this.toggle();
    }
  };

  connectedCallback(): void {
    super.connectedCallback();
    if (this.hotkey) document.addEventListener('keydown', this.onGlobalKey);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    document.removeEventListener('keydown', this.onGlobalKey);
  }

  // ── API pública ──────────────────────────────────────────────────────────
  /** Abre la paleta (resetea búsqueda y resaltado, enfoca el input). */
  openPalette(): void {
    if (this.open) return;
    this.open = true;
    this.queryText = '';
    this.activeIndex = 0;
    this.emitOpen(true);
    // Enfoca el input una vez renderizado el overlay.
    this.updateComplete.then(() => this.searchInput?.focus());
  }

  /** Cierra la paleta. */
  close(): void {
    if (!this.open) return;
    this.open = false;
    this.emitOpen(false);
  }

  /** Alterna abierto/cerrado. */
  toggle(): void {
    this.open ? this.close() : this.openPalette();
  }

  private emitOpen(open: boolean): void {
    this.dispatchEvent(
      new CustomEvent('ok-open', { detail: { open }, bubbles: true, composed: true }),
    );
  }

  // ── Filtrado / agrupado ─────────────────────────────────────────────────
  // Decide si un comando casa con el texto de búsqueda (substring sobre label + keywords).
  // (No se llama `matches` para no chocar con `Element.matches` en el tipo del custom element.)
  private commandMatches(cmd: OkCommand, q: string): boolean {
    if (!q) return true;
    const hay = [cmd.label, cmd.hint ?? '', ...(cmd.keywords ?? [])].join(' ').toLowerCase();
    return hay.includes(q);
  }

  // Devuelve la lista filtrada y plana (en orden), conservando el orden de entrada.
  private filtered(): OkCommand[] {
    const q = this.queryText.trim().toLowerCase();
    return this.commands.filter((c) => this.commandMatches(c, q));
  }

  // Agrupa la lista filtrada por `group` preservando el orden de aparición de cada grupo.
  private grouped(list: OkCommand[]): Array<{ group: string; items: OkCommand[] }> {
    const order: string[] = [];
    const byGroup = new Map<string, OkCommand[]>();
    for (const cmd of list) {
      const g = cmd.group ?? '';
      if (!byGroup.has(g)) {
        byGroup.set(g, []);
        order.push(g);
      }
      byGroup.get(g)!.push(cmd);
    }
    return order.map((g) => ({ group: g, items: byGroup.get(g)! }));
  }

  // ── Interacción ──────────────────────────────────────────────────────────
  private onInput(e: Event): void {
    this.queryText = (e.target as HTMLInputElement).value;
    this.activeIndex = 0;
  }

  // Teclado dentro del panel: flechas mueven el resaltado, Enter ejecuta, Esc cierra.
  private onPanelKey(e: KeyboardEvent): void {
    const flat = this.filtered();
    if (e.key === 'Escape') {
      e.preventDefault();
      this.close();
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (flat.length) this.activeIndex = (this.activeIndex + 1) % flat.length;
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (flat.length) this.activeIndex = (this.activeIndex - 1 + flat.length) % flat.length;
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      const cmd = flat[this.activeIndex];
      if (cmd) this.execute(cmd);
    }
  }

  // Ejecuta un comando: emite `ok-select` y cierra la paleta.
  private execute(cmd: OkCommand): void {
    this.dispatchEvent(
      new CustomEvent('ok-select', {
        detail: { id: cmd.id, command: cmd },
        bubbles: true,
        composed: true,
      }),
    );
    this.close();
  }

  // Cierra al click en el scrim (fuera del panel).
  private onScrimClick(e: MouseEvent): void {
    if (e.target === e.currentTarget) this.close();
  }

  // ── Render ────────────────────────────────────────────────────────────────
  private renderItem(cmd: OkCommand, flatIndex: number): unknown {
    const active = flatIndex === this.activeIndex;
    return html`<li
      class=${active ? 'item active' : 'item'}
      role="option"
      aria-selected=${active ? 'true' : 'false'}
      @click=${() => this.execute(cmd)}
      @mousemove=${() => {
        if (this.activeIndex !== flatIndex) this.activeIndex = flatIndex;
      }}
    >
      <span class="icon">
        ${cmd.icon ? html`<ion-icon .name=${cmd.icon}></ion-icon>` : ''}
      </span>
      <span class="body">
        <span class="label">${cmd.label}</span>
        ${cmd.hint ? html`<span class="hint">${cmd.hint}</span>` : ''}
      </span>
      ${cmd.shortcut ? html`<span class="shortcut">${cmd.shortcut}</span>` : ''}
    </li>`;
  }

  render(): unknown {
    if (!this.open) return html``;

    const flat = this.filtered();
    const groups = this.grouped(flat);
    // Contador de índice plano compartido entre grupos (para casar con `activeIndex`).
    let flatIndex = -1;

    return html`<div
      class="scrim"
      role="dialog"
      aria-modal="true"
      aria-label=${this.t.dialogLabel}
      @click=${(e: MouseEvent) => this.onScrimClick(e)}
      @keydown=${(e: KeyboardEvent) => this.onPanelKey(e)}
    >
      <div class="panel">
        <div class="search">
          <ion-icon name="search-outline"></ion-icon>
          <input
            type="text"
            .value=${this.queryText}
            placeholder=${this.effectivePlaceholder}
            aria-label=${this.effectivePlaceholder}
            autocomplete="off"
            spellcheck="false"
            @input=${(e: Event) => this.onInput(e)}
          />
          <span class="esc">${this.t.escHint}</span>
        </div>
        ${flat.length
          ? html`<ul class="results" role="listbox">
              ${groups.map(
                (g) => html`
                  ${g.group ? html`<li class="group" role="presentation">${g.group}</li>` : ''}
                  ${g.items.map((cmd) => {
                    flatIndex += 1;
                    return this.renderItem(cmd, flatIndex);
                  })}
                `,
              )}
            </ul>`
          : html`<div class="empty">${this.t.noMatches}</div>`}
      </div>
    </div>`;
  }
}

define('ok-command-palette', OkCommandPalette);

declare global {
  interface HTMLElementTagNameMap {
    'ok-command-palette': OkCommandPalette;
  }
}
