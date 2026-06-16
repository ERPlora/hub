import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-page-header — cabecera de página IN-CONTENT típica de un ERP: título de sección + descripción
// + bloque de acciones + breadcrumbs, alineada con el ancho del contenido. Ionic resuelve la
// topbar (ion-header/ion-toolbar/ion-title) pero NO esta cabecera dentro del contenido;
// ok-section/ok-hero son de marketing. LAYOUT PURO: sin eventos, sin fondo propio (transparente
// sobre --ok-bg), tipografía heredada, responsive integrado (stack < 640px).
//   • `heading`     → título (h1/h2 según `level`).
//   • `level`       → 1 (def) | 2 — nivel semántico del heading.
//   • `description` → subtítulo atenuado bajo el título.
//   • `compact`     → variante densa para sub-páginas.
// Slots:
//   • `breadcrumbs` → pensado para <ion-breadcrumbs> (Ionic ya los trae; aquí solo tienen hueco).
//   • `meta`        → línea de metadatos (fechas, ids) bajo el título.
//   • `actions`     → botones a la derecha (ion-button); en móvil bajan debajo del título.
//   • default       → contenido extra bajo la descripción (chips de filtros, ok-status-pill…).
export class OkPageHeader extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.6));
      --spacing: var(--ok-spacing, 1rem);

      /* Bloque a ancho completo del contenedor, sin fondo propio. */
      display: block;
      width: 100%;
      color: var(--color);
      padding-block: var(--spacing);
      box-sizing: border-box;
    }
    :host([compact]) {
      padding-block: calc(var(--spacing) * 0.5);
    }

    /* Breadcrumbs encima del título (hueco para ion-breadcrumbs). */
    .crumbs {
      margin-bottom: calc(var(--spacing) * 0.5);
    }
    .crumbs.empty {
      display: none;
    }

    /* Fila principal: texto a la izquierda, acciones a la derecha. */
    .row {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: var(--spacing);
      flex-wrap: wrap;
    }
    .text {
      flex: 1 1 24rem;
      min-width: 0;
    }

    .heading {
      margin: 0;
      font-size: 1.65rem;
      font-weight: 700;
      line-height: 1.2;
      letter-spacing: -0.015em;
      overflow-wrap: break-word;
    }
    /* Sub-página (level=2) y variante compacta: título algo menor. */
    .heading.h2,
    :host([compact]) .heading {
      font-size: 1.3rem;
    }

    .description {
      margin: 0.35rem 0 0;
      font-size: 0.95rem;
      color: var(--color-muted);
      max-width: 70ch;
    }

    /* Línea de metadatos (fechas, ids…) bajo el título/descipción. */
    .meta {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.35rem 1rem;
      margin-top: 0.45rem;
      font-size: 0.85rem;
      color: var(--color-muted);
    }
    .meta.empty {
      display: none;
    }

    /* Acciones a la derecha (ion-button); en móvil bajan debajo del título. */
    .actions {
      flex: 0 0 auto;
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.5rem;
    }
    .actions.empty {
      display: none;
    }

    /* Contenido extra bajo la descripción (chips de filtros, pills…). */
    .extra {
      margin-top: calc(var(--spacing) * 0.75);
    }
    .extra.empty {
      display: none;
    }

    /* < 640px: stack vertical (acciones bajo el título, ancho completo). */
    @media (max-width: 640px) {
      .row {
        flex-direction: column;
        align-items: stretch;
      }
      .actions {
        justify-content: flex-start;
      }
    }
  `;

  /** Título de la página/sección. */
  @property() heading = '';
  /** Nivel semántico del heading: 1 (def, h1) | 2 (h2, sub-página). */
  @property({ type: Number }) level: 1 | 2 = 1;
  /** Subtítulo atenuado bajo el título. */
  @property() description?: string;
  /** Variante densa para sub-páginas (reflejado para CSS). */
  @property({ type: Boolean, reflect: true }) compact = false;

  // Flags de slots con contenido (ocultan los wrappers vacíos para no dejar huecos).
  @state() private hasBreadcrumbs = false;
  @state() private hasMeta = false;
  @state() private hasActions = false;
  @state() private hasExtra = false;

  // slotchange genérico → actualiza el flag del slot correspondiente.
  private onSlotChange(e: Event): void {
    const slot = e.target as HTMLSlotElement;
    const has = slot.assignedNodes({ flatten: true }).some(
      (n) => n.nodeType === Node.ELEMENT_NODE || (n.textContent ?? '').trim().length > 0,
    );
    switch (slot.name) {
      case 'breadcrumbs':
        this.hasBreadcrumbs = has;
        break;
      case 'meta':
        this.hasMeta = has;
        break;
      case 'actions':
        this.hasActions = has;
        break;
      default:
        this.hasExtra = has;
    }
  }

  render(): unknown {
    const onSlot = (e: Event): void => this.onSlotChange(e);
    return html`
      <div class=${this.hasBreadcrumbs ? 'crumbs' : 'crumbs empty'}>
        <slot name="breadcrumbs" @slotchange=${onSlot}></slot>
      </div>
      <div class="row">
        <div class="text">
          ${this.level === 2
            ? html`<h2 class="heading h2">${this.heading}</h2>`
            : html`<h1 class="heading">${this.heading}</h1>`}
          ${this.description ? html`<p class="description">${this.description}</p>` : ''}
          <div class=${this.hasMeta ? 'meta' : 'meta empty'}>
            <slot name="meta" @slotchange=${onSlot}></slot>
          </div>
        </div>
        <div class=${this.hasActions ? 'actions' : 'actions empty'}>
          <slot name="actions" @slotchange=${onSlot}></slot>
        </div>
      </div>
      <div class=${this.hasExtra ? 'extra' : 'extra empty'}>
        <slot @slotchange=${onSlot}></slot>
      </div>
    `;
  }
}

define('ok-page-header', OkPageHeader);

declare global {
  interface HTMLElementTagNameMap {
    'ok-page-header': OkPageHeader;
  }
}
