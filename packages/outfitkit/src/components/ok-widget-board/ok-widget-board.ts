import { LitElement, html, css, nothing } from 'lit';
import { property, state } from 'lit/decorators.js';
import { repeat } from 'lit/directives/repeat.js';
import { define } from '../../base/define.js';

// ok-widget-board — panel de widgets configurable por el usuario.
//
// El HOST declara un CATÁLOGO de widgets (`widgets`) y, opcionalmente, PRESETS por
// sector/rol. El componente aporta: rejilla responsive de los widgets activos, un botón
// ⋮ que abre un modal para activar/desactivar, REORDENAR (arrastrar) y aplicar presets,
// y PERSISTENCIA opcional en localStorage. Cada widget trae un `render(cell)` IMPERATIVO:
// el host construye el cuerpo del widget con SUS propios datos (CSP-safe: es una función
// del host, nunca un string evaluado), de modo que cada página o MÓDULO alimenta el board
// con su fuente de datos (un ok-data-table, un ok-chart, KPIs…) reutilizando lo que ya hay.
//
// Eventos: `ok-change` (detail { value }) al cambiar los widgets activos / su orden.

/** Tamaño de celda en la rejilla de 12 columnas (desktop): sm=3, md=6, lg=8. */
export type WidgetSize = 'sm' | 'md' | 'lg';

/** Definición de un widget del catálogo. */
export interface WidgetDef {
  /** Id estable (clave de activación/orden/persistencia). */
  id: string;
  /** Título legible (se muestra en el selector). */
  title: string;
  /** Icono ionicons para el selector. */
  icon?: string;
  /** Categoría/grupo (se muestra como subtítulo en el selector). */
  category?: string;
  /** Tamaño de celda (def 'md'). */
  size?: WidgetSize;
  /** Monta el cuerpo del widget DENTRO de `cell` (el host añade sus ok/ion con sus datos). */
  render: (cell: HTMLElement) => void;
}

/** Preset = conjunto recomendado de widgets para un sector/rol. */
export interface WidgetPreset {
  id: string;
  label: string;
  widgets: string[];
}

/** Textos del selector (default inglés; override por `.labels`). */
export interface OkWidgetBoardLabels {
  customize: string;
  close: string;
  presets: string;
  active: string;
  available: string;
  empty: string;
}

const DEFAULT_LABELS: OkWidgetBoardLabels = {
  customize: 'Customize panel',
  close: 'Close',
  presets: 'Start from a preset',
  active: 'Active · drag to reorder',
  available: 'Available',
  empty: 'Empty panel. Tap ⋮ to add widgets.',
};

export class OkWidgetBoard extends LitElement {
  static styles = css`
    :host { display: block; width: 100%; }
    .bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; min-height: 28px; }
    .title { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; color: var(--ion-color-medium, #6b7280); }
    .grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: var(--ok-widget-gap, 16px); align-items: start; }
    .cell { min-width: 0; grid-column: span 12; }
    @media (min-width: 768px) {
      .cell[data-size='sm'] { grid-column: span 3; }
      .cell[data-size='md'] { grid-column: span 6; }
      .cell[data-size='lg'] { grid-column: span 8; }
    }
    .empty { grid-column: span 12; border: 1px dashed var(--ion-border-color, rgba(127,127,127,0.3)); border-radius: 12px; padding: 32px; text-align: center; color: var(--ion-color-medium, #6b7280); }
  `;

  /** Catálogo de widgets disponibles. */
  @property({ attribute: false }) widgets: WidgetDef[] = [];
  /** Presets por sector/rol (opcional). */
  @property({ attribute: false }) presets: WidgetPreset[] = [];
  /** Ids activos y ordenados. Si no se pasa, deriva del 1er preset o de todos. */
  @property({ attribute: false }) value: string[] = [];
  /** Muestra el botón ⋮ de configuración. */
  @property({ type: Boolean }) editable = false;
  /** Si se da, persiste el `value` en localStorage bajo `okwb:{storageKey}`. */
  @property({ attribute: 'storage-key' }) storageKey = '';
  /** Textos del selector (parcial; lo no pasado cae al default inglés). */
  @property({ attribute: false }) labels: Partial<OkWidgetBoardLabels> = {};

  @state() private initialized = false;
  private modal?: HTMLElement & { present?: () => void; dismiss?: () => void };
  private reorderEl?: HTMLElement;
  private availEl?: HTMLElement;

  private get t(): OkWidgetBoardLabels { return { ...DEFAULT_LABELS, ...this.labels }; }
  private get byId(): Map<string, WidgetDef> { return new Map(this.widgets.map((w) => [w.id, w])); }
  private get active(): string[] { const m = this.byId; return (this.value || []).filter((id) => m.has(id)); }

  willUpdate(): void {
    // Inicialización PEREZOSA: en cuanto el host ha poblado el catálogo (`widgets`), deriva el
    // estado inicial. Se hace aquí —no en connectedCallback— porque el host setea widgets/presets
    // DESPUÉS de conectar el elemento. Orden: localStorage → value dado → 1er preset → todos.
    if (this.initialized || !this.widgets.length) return;
    let initial: string[] | null = null;
    if (this.storageKey) {
      try {
        const saved = JSON.parse(localStorage.getItem(`okwb:${this.storageKey}`) || 'null');
        if (Array.isArray(saved)) initial = saved;
      } catch (_) { /* noop */ }
    }
    if (!initial) {
      if (this.value && this.value.length) initial = this.value.slice();
      else if (this.presets.length) initial = this.presets[0].widgets.slice();
      else initial = this.widgets.map((w) => w.id);
    }
    this.value = initial;
    this.initialized = true;
  }

  private persist(): void {
    if (!this.storageKey) return;
    try { localStorage.setItem(`okwb:${this.storageKey}`, JSON.stringify(this.value)); } catch (_) { /* noop */ }
  }

  /** Cambia el estado activo, persiste, re-renderiza el selector y emite `ok-change`. */
  private setValue(next: string[]): void {
    this.value = next.slice();
    this.persist();
    this.dispatchEvent(new CustomEvent('ok-change', { detail: { value: this.value.slice() }, bubbles: true, composed: true }));
    this.refreshModal();
  }

  render() {
    const items = this.active;
    return html`
      <div class="bar">
        <slot name="title"><span class="title"></span></slot>
        ${this.editable
          ? html`<ion-button fill="clear" size="small" aria-label=${this.t.customize} @click=${this.openConfig}>
              <ion-icon slot="icon-only" name="ellipsis-vertical"></ion-icon>
            </ion-button>`
          : nothing}
      </div>
      <div class="grid">
        ${items.length
          ? repeat(
              items,
              (id) => id,
              (id) => {
                const w = this.byId.get(id);
                return w ? html`<div class="cell" data-size=${w.size || 'md'} data-id=${id}></div>` : nothing;
              },
            )
          : html`<div class="empty">${this.t.empty}</div>`}
      </div>`;
  }

  updated(): void {
    // Monta el cuerpo imperativo de cada celda nueva (repeat con key preserva las ya montadas).
    const map = this.byId;
    this.renderRoot.querySelectorAll<HTMLElement>('.cell').forEach((cell) => {
      const id = cell.dataset.id || '';
      if (cell.dataset.mounted === id) return;
      cell.replaceChildren();
      try { map.get(id)?.render(cell); } catch (err) { console.error('[ok-widget-board]', id, err); }
      cell.dataset.mounted = id;
    });
  }

  // ── Selector (⋮ → ion-modal en light-DOM, para no chocar con el reparent de Ionic) ──
  private openConfig = (): void => {
    if (!this.modal) this.buildModal();
    this.modal?.present?.();
  };

  private buildModal(): void {
    const t = this.t;
    const make = (tag: string, opts: { attrs?: Record<string, unknown>; props?: Record<string, unknown>; text?: string } = {}) => {
      const n = document.createElement(tag) as HTMLElement & Record<string, unknown>;
      for (const [k, v] of Object.entries(opts.attrs || {})) v === true ? n.setAttribute(k, '') : v != null && n.setAttribute(k, String(v));
      for (const [k, v] of Object.entries(opts.props || {})) (n as Record<string, unknown>)[k] = v;
      if (opts.text != null) n.textContent = opts.text;
      return n;
    };

    const modal = make('ion-modal') as HTMLElement & { present?: () => void; dismiss?: () => void; initialBreakpoint?: number; breakpoints?: number[] };
    modal.initialBreakpoint = 0.9;
    modal.breakpoints = [0, 0.9, 1];

    const header = make('ion-header');
    const tb = make('ion-toolbar');
    tb.appendChild(make('ion-title', { text: t.customize }));
    const endBtns = make('ion-buttons', { attrs: { slot: 'end' } });
    const closeBtn = make('ion-button', { text: t.close });
    closeBtn.addEventListener('click', () => modal.dismiss?.());
    endBtns.appendChild(closeBtn); tb.appendChild(endBtns); header.appendChild(tb); modal.appendChild(header);

    const content = make('ion-content');

    // Presets.
    if (this.presets.length) {
      content.appendChild(make('div', { attrs: { class: 'okwb-sub' }, text: t.presets }));
      const wrap = make('div', { attrs: { class: 'okwb-presets' } });
      for (const p of this.presets) {
        const chip = make('ion-chip', { attrs: { outline: true } });
        chip.appendChild(make('ion-label', { text: p.label }));
        chip.addEventListener('click', () => this.setValue(p.widgets.filter((id) => this.byId.has(id))));
        wrap.appendChild(chip);
      }
      content.appendChild(wrap);
    }

    // Activos (reordenables).
    content.appendChild(make('div', { attrs: { class: 'okwb-sub' }, text: t.active }));
    const activeList = make('ion-list');
    const reorder = make('ion-reorder-group', { props: { disabled: false } });
    reorder.addEventListener('ionItemReorder', (ev: Event) => {
      const e = ev as CustomEvent<{ from: number; to: number; complete: (data?: unknown) => void }>;
      const next = this.active;
      const moved = next.splice(e.detail.from, 1)[0];
      next.splice(e.detail.to, 0, moved);
      e.detail.complete();
      this.setValue(next);
    });
    activeList.appendChild(reorder); content.appendChild(activeList);

    // Disponibles.
    content.appendChild(make('div', { attrs: { class: 'okwb-sub' }, text: t.available }));
    const availList = make('ion-list'); content.appendChild(availList);

    // Estilos del modal (light-DOM): viven en un <style> propio del modal.
    const style = make('style', { text:
      `.okwb-sub{font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--ion-color-medium);padding:12px 16px 4px}` +
      `.okwb-presets{display:flex;gap:8px;flex-wrap:wrap;padding:12px 16px}` });
    modal.appendChild(style);
    modal.appendChild(content);
    document.body.appendChild(modal);

    this.modal = modal;
    this.reorderEl = reorder;
    this.availEl = availList;
    this.refreshModal();
  }

  /** Repinta las listas de activos/disponibles del modal según `value`. */
  private refreshModal(): void {
    const reorder = this.reorderEl;
    const availList = this.availEl;
    if (!reorder || !availList) return;
    const map = this.byId;

    const item = (w: WidgetDef, checked: boolean, onToggle: () => void, withHandle: boolean) => {
      const it = document.createElement('ion-item');
      if (w.icon) { const ic = document.createElement('ion-icon'); ic.setAttribute('slot', 'start'); ic.setAttribute('name', w.icon); it.appendChild(ic); }
      const lbl = document.createElement('ion-label');
      const h3 = document.createElement('h3'); h3.textContent = w.title; lbl.appendChild(h3);
      if (w.category) { const p = document.createElement('p'); p.textContent = w.category; lbl.appendChild(p); }
      it.appendChild(lbl);
      const tog = document.createElement('ion-toggle') as HTMLElement & { checked: boolean };
      tog.setAttribute('slot', 'end'); tog.checked = checked;
      tog.addEventListener('ionChange', onToggle);
      it.appendChild(tog);
      if (withHandle) { const r = document.createElement('ion-reorder'); r.setAttribute('slot', 'end'); it.appendChild(r); }
      return it;
    };

    reorder.replaceChildren();
    for (const id of this.active) {
      const w = map.get(id); if (!w) continue;
      reorder.appendChild(item(w, true, () => this.setValue(this.active.filter((x) => x !== id)), true));
    }
    availList.replaceChildren();
    for (const w of this.widgets) {
      if (this.active.includes(w.id)) continue;
      availList.appendChild(item(w, false, () => this.setValue([...this.active, w.id]), false));
    }
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.modal?.remove();
    this.modal = undefined;
  }
}

define('ok-widget-board', OkWidgetBoard);

declare global {
  interface HTMLElementTagNameMap {
    'ok-widget-board': OkWidgetBoard;
  }
}
