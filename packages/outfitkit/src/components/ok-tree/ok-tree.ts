import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Nodo del árbol (recursivo). Lo aporta el consumidor vía la prop `.nodes`.
export interface OkTreeNode {
  /** Identificador único del nodo (clave de selección/expansión). */
  id: string;
  /** Texto visible del nodo. */
  label: string;
  /** Nombre de un ionicon opcional, mostrado antes del label. */
  icon?: string;
  /** Hijos del nodo; si tiene, se dibuja chevron expandible. */
  children?: OkTreeNode[];
  /** Estado inicial de expansión (se copia al estado interno la primera vez). */
  expanded?: boolean;
  /** Deshabilita la interacción (no expande ni selecciona). */
  disabled?: boolean;
}

// ok-tree — árbol expandible por DATOS (`nodes`), render recursivo con indentación por nivel.
// AUTOCONTENIDO: CSS propio en el shadow (sin Ionic salvo `ion-icon` para chevron/iconos, que
// registra el host). El estado de expansión se controla internamente (toggle) partiendo del
// campo `expanded` de cada nodo. Click en el chevron expande/colapsa; click en el label selecciona.
//   • prop `.nodes`      → Array<OkTreeNode> (recursivo)
//   • prop `selectable`  → habilita resaltado/selección de filas
//   • prop `active-id`   → id del nodo resaltado
// Eventos (bubbles + composed):
//   • `ok-toggle`  detail { id, expanded }
//   • `ok-select`  detail { id, node }

// Textos traducibles (default inglés). Pásalos desde fuera vía la prop `labels`.
export interface OkTreeLabels {
  /** aria-label del chevron cuando el nodo está colapsado. */
  expand: string;
  /** aria-label del chevron cuando el nodo está expandido. */
  collapse: string;
}

const DEFAULT_LABELS: OkTreeLabels = {
  expand: 'Expand',
  collapse: 'Collapse',
};

export class OkTree extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.55));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --primary-contrast: var(--ok-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --hover-bg: var(--ok-hover, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.06));
      --guide-color: var(--ok-border-soft, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.12));
      --border-radius: var(--ok-radius, 8px);
      --indent: var(--ok-tree-indent, 18px);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* Por defecto ocupa el ancho del contenedor y es responsive. */
      display: block;
      width: 100%;
      color: var(--color);
      font-family: var(--font);
      font-size: 0.95rem;
    }
    [role='tree'],
    [role='group'] {
      margin: 0;
      padding: 0;
      list-style: none;
    }
    /* Cada subnivel se indenta y dibuja una línea guía sutil a la izquierda. */
    [role='group'] {
      margin-left: calc(var(--indent) / 2 + 8px);
      padding-left: calc(var(--indent) / 2);
      border-left: 1px solid var(--guide-color);
    }
    .row {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      width: 100%;
      box-sizing: border-box;
      padding: 0.38rem 0.5rem;
      border-radius: var(--border-radius);
      cursor: default;
      user-select: none;
      transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease), box-shadow var(--ok-transition, 150ms ease),
        transform 120ms ease;
    }
    .row.selectable {
      cursor: pointer;
    }
    @media (hover: hover) {
      .row.selectable:hover {
        background: var(--hover-bg);
      }
    }
    .row.selectable:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    .row.active {
      background: var(--primary-color);
      color: var(--primary-contrast);
    }
    .row.disabled {
      opacity: 0.45;
      cursor: not-allowed;
      pointer-events: none;
    }
    /* Botón del chevron: expande/colapsa. Reserva hueco aunque el nodo sea hoja. */
    .chevron {
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 20px;
      height: 20px;
      padding: 0;
      margin: 0;
      border: 0;
      background: none;
      color: inherit;
      cursor: pointer;
      border-radius: 4px;
      transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease), box-shadow var(--ok-transition, 150ms ease),
        transform 120ms ease;
    }
    @media (hover: hover) {
      .chevron:not(.leaf):hover {
        background: var(--hover-bg);
      }
    }
    .chevron:not(.leaf):active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    .chevron.leaf {
      visibility: hidden;
      cursor: default;
    }
    .chevron ion-icon {
      font-size: 1rem;
      transition: transform 0.18s ease;
    }
    .chevron.open ion-icon {
      transform: rotate(90deg);
    }
    .icon {
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      font-size: 1.05rem;
      color: var(--color-muted);
    }
    .row.active .icon {
      color: inherit;
    }
    .label {
      flex: 1 1 auto;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    @media (prefers-reduced-motion: reduce) {
      .row.selectable:hover,
      .row.selectable:active,
      .chevron:not(.leaf):hover,
      .chevron:not(.leaf):active {
        transform: none;
      }
    }
  `;

  /** Nodos raíz del árbol (recursivo vía `children`). */
  @property({ attribute: false }) nodes: OkTreeNode[] = [];
  /** Si está activo, las filas son clicables y emiten `ok-select`. */
  @property({ type: Boolean }) selectable = false;
  /** Id del nodo resaltado. */
  @property({ attribute: 'active-id' }) activeId = '';
  /** Textos traducibles (merge sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkTreeLabels> = {};

  // Textos efectivos: defaults en inglés + overrides del consumidor.
  private get t(): OkTreeLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Estado interno de expansión por id. Se inicializa de forma perezosa a partir de `expanded`.
  @state() private expandedIds = new Set<string>();
  // Marca para sembrar el estado inicial solo una vez (los `expanded` de los datos).
  private seeded = false;

  // Siembra el estado de expansión a partir del campo `expanded` de cada nodo (una sola vez).
  private seedExpanded(nodes: OkTreeNode[]): void {
    for (const n of nodes) {
      if (n.expanded) this.expandedIds.add(n.id);
      if (n.children?.length) this.seedExpanded(n.children);
    }
  }

  private isExpanded(node: OkTreeNode): boolean {
    return this.expandedIds.has(node.id);
  }

  // Expande/colapsa un nodo y emite `ok-toggle`.
  private toggle(node: OkTreeNode): void {
    if (node.disabled) return;
    const next = new Set(this.expandedIds);
    const open = !next.has(node.id);
    if (open) next.add(node.id);
    else next.delete(node.id);
    this.expandedIds = next;
    this.dispatchEvent(
      new CustomEvent('ok-toggle', {
        detail: { id: node.id, expanded: open },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Selecciona un nodo (si `selectable`) y emite `ok-select`.
  private select(node: OkTreeNode): void {
    if (node.disabled || !this.selectable) return;
    this.dispatchEvent(
      new CustomEvent('ok-select', {
        detail: { id: node.id, node },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Render recursivo de un nodo (li[treeitem] + grupo de hijos si está expandido).
  private renderNode(node: OkTreeNode): unknown {
    const hasChildren = !!node.children?.length;
    const expanded = hasChildren && this.isExpanded(node);
    const active = this.selectable && node.id === this.activeId;
    const rowClasses = [
      'row',
      this.selectable ? 'selectable' : '',
      active ? 'active' : '',
      node.disabled ? 'disabled' : '',
    ]
      .filter(Boolean)
      .join(' ');

    return html`<li
      role="treeitem"
      aria-expanded=${hasChildren ? String(expanded) : ''}
      aria-disabled=${node.disabled ? 'true' : 'false'}
    >
      <div class=${rowClasses}>
        <button
          type="button"
          class=${`chevron ${hasChildren ? '' : 'leaf'} ${expanded ? 'open' : ''}`.trim()}
          aria-hidden=${hasChildren ? 'false' : 'true'}
          tabindex=${hasChildren ? '0' : '-1'}
          aria-label=${expanded ? this.t.collapse : this.t.expand}
          @click=${(e: Event) => {
            e.stopPropagation();
            this.toggle(node);
          }}
        >
          <ion-icon name="chevron-forward-outline"></ion-icon>
        </button>
        ${node.icon
          ? html`<span class="icon"><ion-icon .name=${node.icon}></ion-icon></span>`
          : ''}
        <span class="label" @click=${() => this.select(node)}>${node.label}</span>
      </div>
      ${expanded
        ? html`<ul role="group">
            ${node.children!.map((child) => this.renderNode(child))}
          </ul>`
        : ''}
    </li>`;
  }

  render(): unknown {
    // Siembra perezosa del estado inicial a partir de los datos.
    if (!this.seeded && this.nodes.length) {
      this.seedExpanded(this.nodes);
      this.seeded = true;
    }
    return html`<ul role="tree">
      ${this.nodes.map((node) => this.renderNode(node))}
    </ul>`;
  }
}

define('ok-tree', OkTree);

declare global {
  interface HTMLElementTagNameMap {
    'ok-tree': OkTree;
  }
}
