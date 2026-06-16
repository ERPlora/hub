import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Item de la línea de tiempo. Lo aporta el consumidor vía la prop `.items`.
export interface OkTimelineItem {
  /** Identificador único del item. */
  id: string;
  /** Título visible del hito. */
  title: string;
  /** Texto secundario opcional bajo el título. */
  description?: string;
  /** Marca temporal/etiqueta opcional (se muestra atenuada). */
  time?: string;
  /** Nombre de un ionicon opcional, dibujado dentro del punto. */
  icon?: string;
  /** Color del punto (token Ionic p.ej. 'primary' o cualquier valor CSS p.ej. '#3880ff'). */
  color?: string;
  /** Estado del hito; afecta al color por defecto y al resaltado del `current`. */
  status?: 'done' | 'current' | 'pending';
}

// ok-timeline — línea de tiempo VERTICAL (Ionic no la trae). Render por DATOS (`items`):
// una línea vertical con un punto por item; cada punto toma color/icono según `status`/`color`.
// El item con `status:'current'` se resalta. AUTOCONTENIDO: CSS propio en el shadow (sin Ionic
// salvo `ion-icon`, que registra el host).
//   • prop `.items`  → Array<OkTimelineItem>
//   • prop `align`   → 'left' | 'alternate' (def 'left')
// Eventos (bubbles + composed):
//   • `ok-item-click`  detail { id, item }
export class OkTimeline extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* -> --ion-* -> hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.55));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --primary-contrast: var(--ok-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --done-color: var(--ok-success, var(--ion-color-success, #2dd36f));
      --pending-color: var(--ok-medium, var(--ion-color-medium, #92949c));
      --line-color: var(--ok-border-soft, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.14));
      --hover-bg: var(--ok-hover, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.06));
      --current-bg: var(
        --ok-current-bg,
        rgba(var(--ion-color-primary-rgb, 56, 128, 255), 0.1)
      );
      --border-radius: var(--ok-radius, 8px);
      --dot-size: var(--ok-timeline-dot, 28px);
      --gutter: var(--ok-timeline-gutter, 14px);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* Por defecto ocupa el ancho del contenedor y es responsive. */
      display: block;
      width: 100%;
      color: var(--color);
      font-family: var(--font);
      font-size: 0.95rem;
    }

    .timeline {
      position: relative;
      margin: 0;
      padding: 0;
      list-style: none;
    }

    /* Item: rejilla [punto | contenido]. La línea vertical se dibuja en la columna del punto. */
    .item {
      position: relative;
      display: grid;
      grid-template-columns: var(--dot-size) 1fr;
      column-gap: var(--gutter);
      padding: 0.15rem 0 0.9rem;
    }
    .item:last-child {
      padding-bottom: 0;
    }

    /* Columna del punto: contiene el dot y el segmento de línea que baja al siguiente. */
    .marker {
      position: relative;
      display: flex;
      justify-content: center;
    }
    /* Segmento de línea: arranca bajo el dot y llega al final del item. */
    .marker::before {
      content: '';
      position: absolute;
      top: var(--dot-size);
      bottom: calc(-0.9rem);
      left: 50%;
      width: 2px;
      transform: translateX(-50%);
      background: var(--line-color);
    }
    .item:last-child .marker::before {
      display: none;
    }

    .dot {
      position: relative;
      z-index: 1;
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: var(--dot-size);
      height: var(--dot-size);
      border-radius: 50%;
      background: var(--dot-color, var(--pending-color));
      color: var(--dot-contrast, #ffffff);
      box-shadow: 0 0 0 3px var(--ok-surface, var(--ion-background-color, #ffffff));
    }
    .dot ion-icon {
      font-size: calc(var(--dot-size) * 0.5);
    }

    /* Contenido del hito; es un botón accesible para emitir el click. */
    .content {
      min-width: 0;
      text-align: left;
      width: 100%;
      margin: 0;
      padding: 0.35rem 0.55rem;
      border: 0;
      background: none;
      color: inherit;
      font: inherit;
      cursor: pointer;
      border-radius: var(--border-radius);
      transition: background-color var(--ok-transition, 150ms ease),
        color var(--ok-transition, 150ms ease), border-color var(--ok-transition, 150ms ease),
        box-shadow var(--ok-transition, 150ms ease), transform 120ms ease;
    }
    @media (hover: hover) {
      .content:hover {
        background: var(--hover-bg);
      }
    }
    .content:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    @media (prefers-reduced-motion: reduce) {
      .content:active {
        transform: none;
      }
    }
    .item.current .content {
      background: var(--current-bg);
    }

    .head {
      display: flex;
      align-items: baseline;
      gap: 0.5rem;
      flex-wrap: wrap;
    }
    .title {
      font-weight: 600;
      min-width: 0;
    }
    .item.current .title {
      color: var(--primary-color);
    }
    .time {
      font-size: 0.8rem;
      color: var(--color-muted);
      white-space: nowrap;
    }
    .desc {
      margin-top: 0.2rem;
      color: var(--color-muted);
      font-size: 0.88rem;
      line-height: 1.35;
    }

    /* Modo alternado (solo en pantallas anchas): los items pares van a la derecha. */
    @media (min-width: 640px) {
      .timeline.alternate .item {
        grid-template-columns: 1fr var(--dot-size) 1fr;
      }
      .timeline.alternate .marker {
        grid-column: 2;
        order: 0;
      }
      .timeline.alternate .item .content {
        grid-column: 3;
      }
      .timeline.alternate .item.alt .content {
        grid-column: 1;
        text-align: right;
      }
      .timeline.alternate .item.alt .head {
        justify-content: flex-end;
      }
    }
  `;

  /** Items de la línea de tiempo (en orden cronológico de arriba a abajo). */
  @property({ attribute: false }) items: OkTimelineItem[] = [];
  /** Disposición: 'left' (todo a la derecha de la línea) o 'alternate' (zig-zag en desktop). */
  @property() align: 'left' | 'alternate' = 'left';

  // Resuelve el color del punto: explícito en el item, o derivado del status.
  private dotColor(item: OkTimelineItem): string {
    if (item.color) {
      // Permite tokens Ionic ('primary'->var(--ion-color-primary)) o valores CSS directos.
      return /^[a-z-]+$/.test(item.color)
        ? `var(--ion-color-${item.color}, ${item.color})`
        : item.color;
    }
    switch (item.status) {
      case 'done':
        return 'var(--done-color)';
      case 'current':
        return 'var(--primary-color)';
      default:
        return 'var(--pending-color)';
    }
  }

  // Emite `ok-item-click` con el item pulsado.
  private emitClick(item: OkTimelineItem): void {
    this.dispatchEvent(
      new CustomEvent('ok-item-click', {
        detail: { id: item.id, item },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private renderItem(item: OkTimelineItem, index: number): unknown {
    const isCurrent = item.status === 'current';
    const isAlt = this.align === 'alternate' && index % 2 === 1;
    const classes = ['item', isCurrent ? 'current' : '', isAlt ? 'alt' : '']
      .filter(Boolean)
      .join(' ');
    // Color del punto vía custom prop inline (no clases, valor dinámico por item).
    const dotStyle = `--dot-color: ${this.dotColor(item)}`;

    return html`<li class=${classes}>
      <span class="marker">
        <span class="dot" style=${dotStyle}>
          ${item.icon ? html`<ion-icon .name=${item.icon}></ion-icon>` : ''}
        </span>
      </span>
      <button
        type="button"
        class="content"
        @click=${() => this.emitClick(item)}
      >
        <span class="head">
          <span class="title">${item.title}</span>
          ${item.time ? html`<span class="time">${item.time}</span>` : ''}
        </span>
        ${item.description ? html`<div class="desc">${item.description}</div>` : ''}
      </button>
    </li>`;
  }

  render(): unknown {
    const listClass = `timeline ${this.align === 'alternate' ? 'alternate' : ''}`.trim();
    return html`<ul class=${listClass}>
      ${this.items.map((item, i) => this.renderItem(item, i))}
    </ul>`;
  }
}

define('ok-timeline', OkTimeline);

declare global {
  interface HTMLElementTagNameMap {
    'ok-timeline': OkTimeline;
  }
}
