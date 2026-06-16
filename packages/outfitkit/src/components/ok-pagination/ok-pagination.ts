import { LitElement, html, css, nothing } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';
// Internamente usa ion-button / ion-icon / ion-select NATIVOS (los registra el host). OutfitKit
// construye SOBRE Ionic; no envolvemos lo que Ionic ya da.

// ok-pagination — paginador numerado (port del antiguo .ux-pagination/.ux-paginator/.ux-pager).
// Chevrons prev/next + botones numerados con colapso por elipsis (siblingCount/boundaryCount),
// aria-current en la página activa, deshabilitado en los límites. Variante `compact` muestra solo
// prev/value/next. Opcionalmente: info "X–Y de Z" y selector de filas por página (ion-select).
//
// El WC es PRESENTACIONAL/controlado: no guarda estado propio de página; emite eventos y el
// consumidor actualiza `page`/`page-size` y re-renderiza.

/** Token especial en el rango de páginas para representar una elipsis colapsada. */
type PageToken = number | 'ellipsis-start' | 'ellipsis-end';

export type PaginationVariant = 'default' | 'compact';

export class OkPagination extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --bg: var(--ok-surface, var(--ion-background-color, #ffffff));
      --bg-soft: var(--ok-surface-soft, var(--ion-color-light, #f4f5f8));
      --line: var(--ok-border-color, var(--ion-border-color, #e0e2e7));
      --line-strong: var(--ok-border-color-strong, var(--ion-color-step-200, #cdd0d6));
      --ink: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --ink-2: var(--ok-text-color-soft, var(--ion-color-step-650, #545b66));
      --ink-3: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --brand: var(--ok-color-primary, var(--ion-color-primary, #3880ff));
      --brand-fg: var(--ok-color-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --radius: var(--ok-radius, var(--ion-border-radius, 8px));
      --radius-sm: calc(var(--radius) - 2px);
    }

    .wrap {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 14px;
      width: 100%;
      box-sizing: border-box;
      font-size: 0.875rem;
      color: var(--ink-3);
    }

    /* La info y el page-size quedan a los extremos; el paginador empuja al centro/derecha. */
    .info {
      font-variant-numeric: tabular-nums;
    }
    .info b {
      color: var(--ink-2);
      font-weight: 500;
    }

    .spacer {
      flex: 1 1 auto;
    }

    .nav {
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .nav.compact {
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 1px;
      background: var(--bg-soft);
      gap: 0;
    }

    /* Botón de página: ion-button fill=clear restyleado a la estética del paginador. */
    ion-button.page {
      --padding-start: 8px;
      --padding-end: 8px;
      --border-radius: var(--radius-sm);
      --background-hover: var(--bg-soft);
      --color: var(--ink-2);
      --color-hover: var(--ink);
      min-width: 32px;
      height: 32px;
      margin: 0;
      font-size: 0.875rem;
      font-variant-numeric: tabular-nums;
      --border-width: 1px;
      --border-style: solid;
      --border-color: var(--line);
      --background: var(--bg);
    }

    /* Chevrons prev/next: sin borde de caja, look ligero. */
    ion-button.chev {
      --border-width: 0;
      --background: transparent;
    }

    /* Página activa: relleno de marca. */
    ion-button.page.active {
      --background: var(--brand);
      --background-hover: var(--brand);
      --border-color: var(--brand);
      --color: var(--brand-fg);
      --color-hover: var(--brand-fg);
      font-weight: 600;
    }

    .nav.compact ion-button.page {
      --border-width: 0;
      --background: transparent;
    }
    .nav.compact .value {
      min-width: 56px;
      height: 32px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-variant-numeric: tabular-nums;
      color: var(--ink);
      font-weight: 500;
      user-select: none;
      padding: 0 8px;
    }

    .gap {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 28px;
      height: 32px;
      color: var(--ink-3);
      user-select: none;
    }

    .pgsize {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 0.8125rem;
    }
    ion-select.pgsize-select {
      --padding-start: 8px;
      --padding-end: 4px;
      min-height: 30px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--bg-soft);
      color: var(--ink);
      font-size: 0.8125rem;
    }

    @media (max-width: 480px) {
      .info {
        order: 3;
        width: 100%;
        text-align: center;
      }
    }
  `;

  /** Total de elementos (no de páginas). */
  @property({ type: Number }) total = 0;

  /** Página actual (base 1). */
  @property({ type: Number }) page = 1;

  /** Tamaño de página (elementos por página). */
  @property({ type: Number, attribute: 'page-size' }) pageSize = 20;

  /** Nº de páginas vecinas mostradas a cada lado de la activa. */
  @property({ type: Number, attribute: 'sibling-count' }) siblingCount = 1;

  /** Nº de páginas fijas mostradas en cada extremo (inicio/fin). */
  @property({ type: Number, attribute: 'boundary-count' }) boundaryCount = 1;

  /** Variante visual: numerada completa o compacta (prev/valor/next). */
  @property() variant: PaginationVariant = 'default';

  /** Muestra el texto informativo "X–Y de Z". */
  @property({ type: Boolean }) info = false;

  /** Opciones de filas por página; si se pasan, muestra un ion-select. */
  @property({ type: Array, attribute: 'page-size-options' }) pageSizeOptions?: number[];

  /** Etiqueta accesible del nav. */
  @property() label = 'Paginación';

  /** Nº total de páginas (mínimo 1). */
  private get pageCount(): number {
    const size = Math.max(1, this.pageSize);
    return Math.max(1, Math.ceil(Math.max(0, this.total) / size));
  }

  /** Página actual saneada al rango [1, pageCount]. */
  private get current(): number {
    return Math.min(Math.max(1, this.page), this.pageCount);
  }

  /** Construye la lista de tokens (números + elipsis) según sibling/boundary counts. */
  private get range(): PageToken[] {
    const count = this.pageCount;
    const current = this.current;
    const siblings = Math.max(0, this.siblingCount);
    const boundaries = Math.max(1, this.boundaryCount);

    // Nº total de slots: extremos + activa + vecinos + 2 posibles elipsis.
    const totalSlots = boundaries * 2 + siblings * 2 + 3;
    if (count <= totalSlots) {
      return this.seq(1, count);
    }

    const leftSibling = Math.max(current - siblings, boundaries + 2);
    const rightSibling = Math.min(current + siblings, count - boundaries - 1);

    const showLeftGap = leftSibling > boundaries + 2;
    const showRightGap = rightSibling < count - boundaries - 1;

    const tokens: PageToken[] = [];
    tokens.push(...this.seq(1, boundaries));

    if (showLeftGap) {
      tokens.push('ellipsis-start');
    } else {
      // Sin hueco: rellena hasta el vecino izquierdo de forma contigua.
      tokens.push(...this.seq(boundaries + 1, leftSibling - 1));
    }

    tokens.push(...this.seq(leftSibling, rightSibling));

    if (showRightGap) {
      tokens.push('ellipsis-end');
    } else {
      tokens.push(...this.seq(rightSibling + 1, count - boundaries));
    }

    tokens.push(...this.seq(count - boundaries + 1, count));
    return tokens;
  }

  /** Rango entero [from, to] como array (vacío si from > to). */
  private seq(from: number, to: number): number[] {
    const out: number[] = [];
    for (let i = from; i <= to; i++) out.push(i);
    return out;
  }

  private goTo(target: number): void {
    const next = Math.min(Math.max(1, target), this.pageCount);
    if (next === this.current) return;
    this.dispatchEvent(
      new CustomEvent('ok-page-change', {
        detail: { page: next },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private onSizeChange(value: number): void {
    if (!Number.isFinite(value) || value === this.pageSize) return;
    this.dispatchEvent(
      new CustomEvent('ok-page-size-change', {
        detail: { size: value },
        bubbles: true,
        composed: true,
      }),
    );
  }

  /** Chevron SVG (izq/der) dibujado a mano. */
  private chevron(dir: 'prev' | 'next'): unknown {
    const d = dir === 'prev' ? 'M15 18l-6-6 6-6' : 'M9 6l6 6-6 6';
    return html`<svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <path d="${d}"></path>
    </svg>`;
  }

  private renderInfo(): unknown {
    if (!this.info) return nothing;
    if (this.total <= 0) {
      return html`<span class="info"><b>0</b> elementos</span>`;
    }
    const size = Math.max(1, this.pageSize);
    const from = (this.current - 1) * size + 1;
    const to = Math.min(this.current * size, this.total);
    return html`<span class="info"><b>${from}–${to}</b> de <b>${this.total}</b></span>`;
  }

  private renderPageSize(): unknown {
    const opts = this.pageSizeOptions;
    if (!opts || opts.length === 0) return nothing;
    return html`<span class="pgsize">
      <span>Filas</span>
      <ion-select
        class="pgsize-select"
        interface="popover"
        aria-label="Filas por página"
        .value=${this.pageSize}
        @ionChange=${(e: CustomEvent) => this.onSizeChange(Number((e.target as HTMLElement & { value?: unknown }).value))}
      >
        ${opts.map((n) => html`<ion-select-option .value=${n}>${n}</ion-select-option>`)}
      </ion-select>
    </span>`;
  }

  private renderNav(): unknown {
    const current = this.current;
    const count = this.pageCount;
    const atStart = current <= 1;
    const atEnd = current >= count;

    const prev = html`<ion-button
      class="page chev"
      fill="clear"
      aria-label="Página anterior"
      ?disabled=${atStart}
      @click=${() => this.goTo(current - 1)}
      >${this.chevron('prev')}</ion-button
    >`;
    const next = html`<ion-button
      class="page chev"
      fill="clear"
      aria-label="Página siguiente"
      ?disabled=${atEnd}
      @click=${() => this.goTo(current + 1)}
      >${this.chevron('next')}</ion-button
    >`;

    if (this.variant === 'compact') {
      return html`<nav class="nav compact" role="navigation" aria-label=${this.label}>
        ${prev}
        <span class="value" aria-current="page" aria-live="polite">${current} / ${count}</span>
        ${next}
      </nav>`;
    }

    return html`<nav class="nav" role="navigation" aria-label=${this.label}>
      ${prev}
      ${this.range.map((tok) => {
        if (tok === 'ellipsis-start' || tok === 'ellipsis-end') {
          return html`<span class="gap" aria-hidden="true">…</span>`;
        }
        const active = tok === current;
        return html`<ion-button
          class="page ${active ? 'active' : ''}"
          fill="clear"
          aria-label="Página ${tok}"
          aria-current=${active ? 'page' : nothing}
          @click=${() => this.goTo(tok)}
          >${tok}</ion-button
        >`;
      })}
      ${next}
    </nav>`;
  }

  render(): unknown {
    return html`
      <div class="wrap">
        ${this.renderInfo()}
        <span class="spacer"></span>
        ${this.renderNav()}
        ${this.renderPageSize()}
      </div>
    `;
  }
}

define('ok-pagination', OkPagination);

declare global {
  interface HTMLElementTagNameMap {
    'ok-pagination': OkPagination;
  }
}
