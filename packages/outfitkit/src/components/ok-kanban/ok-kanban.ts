import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Tarjeta de una columna del tablero. La aporta el consumidor vía `.columns`.
export interface OkKanbanCard {
  /** Identificador único de la tarjeta (clave de movimiento/click). */
  id: string;
  /** Título principal de la tarjeta. */
  title: string;
  /** Texto secundario opcional bajo el título. */
  subtitle?: string;
  /** Etiquetas opcionales mostradas como chips. */
  tags?: string[];
}

// Columna del tablero. Contiene una lista ordenada de tarjetas.
export interface OkKanbanColumn {
  /** Identificador único de la columna. */
  id: string;
  /** Título visible en la cabecera. */
  title: string;
  /** Color de acento opcional (cualquier valor CSS) para la franja/cabecera. */
  color?: string;
  /** Tarjetas de la columna, en orden. */
  cards: OkKanbanCard[];
}

// Textos i18n (default inglés). Pásalos desde fuera con `.labels`.
export interface OkKanbanLabels {
  /** Mensaje de columna sin tarjetas. */
  empty: string;
}

const DEFAULT_LABELS: OkKanbanLabels = {
  empty: 'No cards',
};

// Detalle interno del arrastre en curso (qué tarjeta y de qué columna sale).
interface DragState {
  cardId: string;
  fromColumn: string;
}

// ok-kanban — tablero de tareas tipo Kanban por DATOS (`columns`). Ionic no tiene este componente.
// AUTOCONTENIDO: CSS propio en el shadow, drag & drop con la API NATIVA HTML5 (`draggable`,
// dragstart/dragover/drop), SIN librerías ni eval (CSP-safe). Solo usa `ion-icon` para el
// contador/handles, que registra el HOST (la app carga Ionic una vez).
//
// Al soltar una tarjeta en otra columna (o en otra posición), el componente actualiza su MODELO
// interno (`view`) y emite el evento. El consumidor puede sincronizar su estado escuchándolo.
//   • prop `.columns` → Array<OkKanbanColumn>
// Eventos (bubbles + composed):
//   • `ok-card-move`  detail { cardId, fromColumn, toColumn, toIndex }
//   • `ok-card-click` detail { id, card }
export class OkKanban extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable estilo Ionic: cadena --ok-* → --ion-* → hex. */
      --background: var(--ok-bg-soft, var(--ion-color-light, #f4f5f8));
      --column-background: var(--ok-surface, var(--ion-card-background, #ffffff));
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.55));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --border-color: var(--ok-border-soft, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.12));
      --card-background: var(--ok-card-bg, var(--ion-background-color, #ffffff));
      --drop-highlight: var(
        --ok-kanban-drop,
        rgba(var(--ion-color-primary-rgb, 56, 128, 255), 0.1)
      );
      --border-radius: var(--ok-radius, 10px);
      --column-width: var(--ok-kanban-column-width, 280px);
      --gap: var(--ok-kanban-gap, 0.9rem);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* Ocupa todo el contenedor; el scroll vive dentro (columnas y listas). */
      display: block;
      width: 100%;
      height: 100%;
      box-sizing: border-box;
      color: var(--color);
      font-family: var(--font);
      font-size: 0.95rem;
    }

    /* Fila de columnas con scroll horizontal (en móvil se desliza). */
    .board {
      display: flex;
      gap: var(--gap);
      align-items: flex-start;
      height: 100%;
      box-sizing: border-box;
      padding: var(--gap);
      overflow-x: auto;
      overflow-y: hidden;
      background: var(--background);
      -webkit-overflow-scrolling: touch;
      scroll-snap-type: x proximity;
    }

    /* Columna de ancho fijo; el contenido scrollea en vertical por dentro. */
    .column {
      flex: 0 0 var(--column-width);
      width: var(--column-width);
      max-height: 100%;
      display: flex;
      flex-direction: column;
      box-sizing: border-box;
      background: var(--column-background);
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
      scroll-snap-align: start;
      transition: background 0.15s ease, box-shadow 0.15s ease;
    }
    /* Resaltado de la columna destino mientras se arrastra sobre ella. */
    .column.drag-over {
      background: var(--drop-highlight);
      box-shadow: inset 0 0 0 2px var(--primary-color);
    }

    /* Cabecera: franja de color (si hay) + título + contador. */
    .column-header {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.7rem 0.85rem;
      border-bottom: 1px solid var(--border-color);
      border-top-left-radius: var(--border-radius);
      border-top-right-radius: var(--border-radius);
    }
    .swatch {
      flex: 0 0 auto;
      width: 10px;
      height: 10px;
      border-radius: 3px;
      background: var(--swatch-color, var(--primary-color));
    }
    .column-title {
      flex: 1 1 auto;
      min-width: 0;
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .count {
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 1.5rem;
      height: 1.5rem;
      padding: 0 0.45rem;
      border-radius: 999px;
      background: var(--background);
      color: var(--color-muted);
      font-size: 0.8rem;
      font-weight: 600;
    }

    /* Lista de tarjetas con scroll vertical propio. */
    .cards {
      flex: 1 1 auto;
      min-height: 2.5rem;
      display: flex;
      flex-direction: column;
      gap: 0.55rem;
      padding: 0.7rem;
      margin: 0;
      list-style: none;
      overflow-y: auto;
      -webkit-overflow-scrolling: touch;
    }
    .empty {
      flex: 1 1 auto;
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--color-muted);
      font-size: 0.85rem;
      text-align: center;
      padding: 0.8rem;
      border: 1px dashed var(--border-color);
      border-radius: var(--border-radius);
    }

    /* Tarjeta arrastrable. */
    .card {
      box-sizing: border-box;
      padding: 0.6rem 0.7rem;
      background: var(--card-background);
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
      cursor: grab;
      user-select: none;
      transition: background-color var(--ok-transition, 150ms ease),
        color var(--ok-transition, 150ms ease), border-color var(--ok-transition, 150ms ease),
        box-shadow var(--ok-transition, 150ms ease), transform 120ms ease, opacity 0.15s ease;
    }
    /* Hover sutil solo con ratón: la tarjeta se levanta ligeramente. */
    @media (hover: hover) {
      .card:not(.dragging):hover {
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        transform: translateY(-2px);
      }
    }
    .card:active {
      cursor: grabbing;
    }
    /* Press feedback solo cuando no se está arrastrando (no romper el drag&drop). */
    .card:not(.dragging):active {
      transform: translateY(0) scale(0.98);
    }
    .card.dragging {
      opacity: 0.45;
    }
    @media (prefers-reduced-motion: reduce) {
      .card:not(.dragging):hover,
      .card:not(.dragging):active {
        transform: none;
      }
    }
    /* Marcador del punto de inserción (placeholder) durante el dragover. */
    .card.drop-before {
      box-shadow: inset 0 3px 0 -1px var(--primary-color);
    }
    .card.drop-after {
      box-shadow: inset 0 -3px 0 -1px var(--primary-color);
    }
    .card-title {
      font-weight: 600;
      line-height: 1.3;
      word-break: break-word;
    }
    .card-subtitle {
      margin-top: 0.2rem;
      color: var(--color-muted);
      font-size: 0.85rem;
      line-height: 1.3;
      word-break: break-word;
    }
    .tags {
      display: flex;
      flex-wrap: wrap;
      gap: 0.3rem;
      margin-top: 0.5rem;
    }
    .tag {
      display: inline-flex;
      align-items: center;
      padding: 0.1rem 0.5rem;
      border-radius: 999px;
      background: var(--background);
      color: var(--color-muted);
      font-size: 0.72rem;
      font-weight: 600;
      line-height: 1.6;
    }
  `;

  /** Columnas del tablero (con sus tarjetas). El componente mantiene una copia interna `view`. */
  @property({ attribute: false }) columns: OkKanbanColumn[] = [];

  /** Textos traducibles (merge sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkKanbanLabels> = {};

  private get t(): OkKanbanLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Copia interna del modelo que el componente reordena al soltar. Se re-siembra cuando el
  // consumidor cambia la prop `columns` (identidad de array distinta).
  @state() private view: OkKanbanColumn[] = [];
  // Origen del arrastre en curso (null si no se está arrastrando).
  @state() private drag: DragState | null = null;
  // Columna actualmente resaltada como destino.
  @state() private overColumn: string | null = null;
  // Indicador de inserción: tarjeta sobre la que se está y si va antes/después.
  @state() private overCardId: string | null = null;
  @state() private overAfter = false;

  // Referencia al último array de prop sembrado, para detectar cambios desde fuera.
  private lastColumnsRef: OkKanbanColumn[] | null = null;

  // Clona en profundidad (solo los niveles que reordenamos) la prop hacia el estado interno.
  private syncFromProp(): void {
    this.view = this.columns.map((col) => ({
      ...col,
      cards: col.cards.map((card) => ({ ...card })),
    }));
    this.lastColumnsRef = this.columns;
  }

  // ---- Drag & drop nativo HTML5 ---------------------------------------------------------------

  private onDragStart(e: DragEvent, fromColumn: string, cardId: string): void {
    this.drag = { cardId, fromColumn };
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = 'move';
      // Algunos navegadores exigen datos para iniciar el arrastre.
      e.dataTransfer.setData('text/plain', cardId);
    }
  }

  private onDragEnd(): void {
    // Limpia indicadores aunque el drop ocurra fuera de una columna válida.
    this.drag = null;
    this.overColumn = null;
    this.overCardId = null;
    this.overAfter = false;
  }

  // Mientras se arrastra sobre una columna: permite soltar y resalta la columna.
  private onColumnDragOver(e: DragEvent, columnId: string): void {
    if (!this.drag) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    if (this.overColumn !== columnId) this.overColumn = columnId;
    // Soltar en zona vacía de la columna = al final.
    this.overCardId = null;
    this.overAfter = false;
  }

  // Mientras se arrastra sobre una tarjeta: calcula si la inserción va antes o después según
  // la posición vertical del puntero respecto al centro de la tarjeta.
  private onCardDragOver(e: DragEvent, columnId: string, cardId: string): void {
    if (!this.drag) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    const target = e.currentTarget as HTMLElement;
    const rect = target.getBoundingClientRect();
    const after = e.clientY > rect.top + rect.height / 2;
    if (this.overColumn !== columnId) this.overColumn = columnId;
    if (this.overCardId !== cardId || this.overAfter !== after) {
      this.overCardId = cardId;
      this.overAfter = after;
    }
  }

  // Suelta sobre la columna (zona vacía o tras propagación): inserta al final si no hay tarjeta diana.
  private onColumnDrop(e: DragEvent, toColumn: string): void {
    if (!this.drag) return;
    e.preventDefault();
    this.commitMove(toColumn);
  }

  // Suelta sobre una tarjeta concreta: inserta antes/después de ella.
  private onCardDrop(e: DragEvent, toColumn: string): void {
    if (!this.drag) return;
    e.preventDefault();
    e.stopPropagation();
    this.commitMove(toColumn);
  }

  // Aplica el movimiento en el modelo interno y emite `ok-card-move`.
  private commitMove(toColumn: string): void {
    const drag = this.drag;
    if (!drag) return;

    const fromCol = this.view.find((c) => c.id === drag.fromColumn);
    const toCol = this.view.find((c) => c.id === toColumn);
    if (!fromCol || !toCol) {
      this.onDragEnd();
      return;
    }

    const fromIndex = fromCol.cards.findIndex((c) => c.id === drag.cardId);
    if (fromIndex === -1) {
      this.onDragEnd();
      return;
    }

    // Índice de inserción objetivo según el indicador (tarjeta diana + antes/después).
    let toIndex = toCol.cards.length;
    if (this.overCardId) {
      const targetIndex = toCol.cards.findIndex((c) => c.id === this.overCardId);
      if (targetIndex !== -1) {
        toIndex = this.overAfter ? targetIndex + 1 : targetIndex;
      }
    }

    // Saca la tarjeta del origen.
    const [card] = fromCol.cards.splice(fromIndex, 1);

    // Si movemos dentro de la misma columna y quitamos un elemento previo al destino,
    // el índice destino se desplaza una posición a la izquierda.
    if (fromCol === toCol && fromIndex < toIndex) {
      toIndex -= 1;
    }

    // Inserta en el destino.
    toCol.cards.splice(toIndex, 0, card);

    // Nuevo identidad de array para forzar re-render reactivo.
    this.view = this.view.map((c) => ({ ...c, cards: [...c.cards] }));

    this.dispatchEvent(
      new CustomEvent('ok-card-move', {
        detail: {
          cardId: drag.cardId,
          fromColumn: drag.fromColumn,
          toColumn,
          toIndex,
        },
        bubbles: true,
        composed: true,
      }),
    );

    this.onDragEnd();
  }

  // Click en una tarjeta (no en arrastre): emite `ok-card-click`.
  private onCardClick(card: OkKanbanCard): void {
    this.dispatchEvent(
      new CustomEvent('ok-card-click', {
        detail: { id: card.id, card },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // ---- Render ---------------------------------------------------------------------------------

  private renderCard(column: OkKanbanColumn, card: OkKanbanCard): unknown {
    const dragging = this.drag?.cardId === card.id;
    const isOver = this.overCardId === card.id && this.overColumn === column.id;
    const classes = [
      'card',
      dragging ? 'dragging' : '',
      isOver && !this.overAfter ? 'drop-before' : '',
      isOver && this.overAfter ? 'drop-after' : '',
    ]
      .filter(Boolean)
      .join(' ');

    return html`<li
      class=${classes}
      draggable="true"
      @dragstart=${(e: DragEvent) => this.onDragStart(e, column.id, card.id)}
      @dragend=${() => this.onDragEnd()}
      @dragover=${(e: DragEvent) => this.onCardDragOver(e, column.id, card.id)}
      @drop=${(e: DragEvent) => this.onCardDrop(e, column.id)}
      @click=${() => this.onCardClick(card)}
    >
      <div class="card-title">${card.title}</div>
      ${card.subtitle ? html`<div class="card-subtitle">${card.subtitle}</div>` : ''}
      ${card.tags?.length
        ? html`<div class="tags">
            ${card.tags.map((tag) => html`<span class="tag">${tag}</span>`)}
          </div>`
        : ''}
    </li>`;
  }

  private renderColumn(column: OkKanbanColumn): unknown {
    const over = this.overColumn === column.id;
    const headerStyle = column.color ? `--swatch-color:${column.color}` : '';

    return html`<section
      class=${`column ${over ? 'drag-over' : ''}`.trim()}
      @dragover=${(e: DragEvent) => this.onColumnDragOver(e, column.id)}
      @drop=${(e: DragEvent) => this.onColumnDrop(e, column.id)}
    >
      <header class="column-header">
        <span class="swatch" style=${headerStyle}></span>
        <span class="column-title">${column.title}</span>
        <span class="count">${column.cards.length}</span>
      </header>
      ${column.cards.length
        ? html`<ul class="cards">
            ${column.cards.map((card) => this.renderCard(column, card))}
          </ul>`
        : html`<ul class="cards">
            <li class="empty">${this.t.empty}</li>
          </ul>`}
    </section>`;
  }

  render(): unknown {
    // Re-siembra el estado interno cuando el consumidor cambia la prop (identidad distinta).
    if (this.columns !== this.lastColumnsRef) {
      this.syncFromProp();
    }
    return html`<div class="board">
      ${this.view.map((column) => this.renderColumn(column))}
    </div>`;
  }
}

define('ok-kanban', OkKanban);

declare global {
  interface HTMLElementTagNameMap {
    'ok-kanban': OkKanban;
  }
}
