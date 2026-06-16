import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Orientación del splitter.
export type OkSplitterOrientation = 'horizontal' | 'vertical';
// Qué panel queda colapsado (oculto).
export type OkSplitterCollapsed = 'none' | 'start' | 'end';

// ok-splitter — split-pane redimensionable estilo IDE/editor.
// Dos paneles (slots `start`/`end`) separados por un divisor arrastrable con
// grip de puntos radiales. Arrastra para redimensionar (pointer events) y
// actualiza `size` (% del primer panel). Cursor col-resize/row-resize.
// Distinto de ion-split-pane (que es app-shell, no redimensionable).
export class OkSplitter extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --bg: var(--ok-surface, var(--ion-background-color, #ffffff));
      --divider-bg: var(--ok-surface-2, var(--ion-color-step-50, #f4f5f8));
      --divider-bg-hover: var(--ok-surface-3, var(--ion-color-step-100, #e9eaee));
      --line: var(--ok-border-color, var(--ion-border-color, #e0e0e0));
      --grip: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --radius: var(--ok-radius-lg, 12px);
      --divider-size: 6px;
      --min-height: 200px;
    }

    .split {
      display: flex;
      width: 100%;
      height: 100%;
      min-height: var(--min-height);
      background: var(--bg);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      overflow: hidden;
      box-sizing: border-box;
    }
    .split.vertical {
      flex-direction: column;
    }

    .pane {
      min-width: 0;
      min-height: 0;
      overflow: auto;
      box-sizing: border-box;
    }
    /* En arrastre, suprimir selección de texto. */
    :host([dragging]) {
      user-select: none;
    }
    :host([dragging]) .pane {
      pointer-events: none;
    }

    .divider {
      flex: 0 0 var(--divider-size);
      background: var(--divider-bg);
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: col-resize;
      transition: background 120ms ease-out;
      touch-action: none;
      align-self: stretch;
    }
    .split.vertical .divider {
      cursor: row-resize;
    }
    .divider:hover,
    :host([dragging]) .divider {
      background: var(--divider-bg-hover);
    }
    .divider::before {
      border-left: 1px solid var(--line);
    }
    .split.horizontal .divider {
      border-left: 1px solid var(--line);
      border-right: 1px solid var(--line);
    }
    .split.vertical .divider {
      border-top: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
    }

    /* Grip de puntos radiales (vertical para split horizontal). */
    .grip {
      pointer-events: none;
    }
    .split.horizontal .grip {
      width: 2px;
      height: 18px;
      background: radial-gradient(
          circle,
          var(--grip) 1px,
          transparent 1.5px
        )
        0 0 / 2px 5px repeat-y;
    }
    .split.vertical .grip {
      width: 18px;
      height: 2px;
      background: radial-gradient(
          circle,
          var(--grip) 1px,
          transparent 1.5px
        )
        0 0 / 5px 2px repeat-x;
    }

    /* Panel colapsado: ocupa todo, oculta divisor + otro panel. */
    .divider.hidden,
    .pane.hidden {
      display: none;
    }
  `;

  /** Orientación: horizontal (paneles lado a lado) o vertical (apilados). */
  @property({ reflect: true }) orientation: OkSplitterOrientation = 'horizontal';

  /** Tamaño del primer panel en % (0–100). */
  @property({ type: Number }) size = 50;

  /** Mínimo % permitido para el primer panel. */
  @property({ type: Number }) min = 10;

  /** Máximo % permitido para el primer panel. */
  @property({ type: Number }) max = 90;

  /** Colapsar un panel: none | start | end. */
  @property() collapsed: OkSplitterCollapsed = 'none';

  /** Estado de arrastre (reflejado para CSS). */
  @property({ type: Boolean, reflect: true }) dragging = false;

  @state() private _size = 50;

  // Referencia al contenedor para medir durante el arrastre.
  private _splitEl: HTMLElement | null = null;
  private _pointerId: number | null = null;

  connectedCallback(): void {
    super.connectedCallback();
    this._size = this._clamp(this.size);
  }

  protected willUpdate(changed: Map<string, unknown>): void {
    // Mantener el estado interno sincronizado con props públicas.
    if (changed.has('size') || changed.has('min') || changed.has('max')) {
      this._size = this._clamp(this.size);
    }
  }

  // Restringe el tamaño a [min, max] dentro de [0, 100].
  private _clamp(v: number): number {
    const lo = Math.max(0, Math.min(100, this.min));
    const hi = Math.max(lo, Math.min(100, this.max));
    return Math.max(lo, Math.min(hi, v));
  }

  private _onPointerDown(e: PointerEvent): void {
    if (this.collapsed !== 'none') return;
    e.preventDefault();
    const target = e.currentTarget as HTMLElement;
    this._splitEl = this.renderRoot.querySelector('.split');
    this._pointerId = e.pointerId;
    target.setPointerCapture(e.pointerId);
    this.dragging = true;
  }

  private _onPointerMove(e: PointerEvent): void {
    if (!this.dragging || !this._splitEl) return;
    const rect = this._splitEl.getBoundingClientRect();
    let pct: number;
    if (this.orientation === 'vertical') {
      const h = rect.height;
      pct = h > 0 ? ((e.clientY - rect.top) / h) * 100 : this._size;
    } else {
      const w = rect.width;
      pct = w > 0 ? ((e.clientX - rect.left) / w) * 100 : this._size;
    }
    const next = this._clamp(Math.round(pct * 10) / 10);
    if (next !== this._size) {
      this._size = next;
      this._emit();
    }
  }

  private _onPointerUp(e: PointerEvent): void {
    if (!this.dragging) return;
    const target = e.currentTarget as HTMLElement;
    if (this._pointerId !== null && target.hasPointerCapture?.(this._pointerId)) {
      target.releasePointerCapture(this._pointerId);
    }
    this._pointerId = null;
    this.dragging = false;
    // Reflejar el resultado en la prop pública.
    this.size = this._size;
  }

  // Permitir teclado en el divisor para accesibilidad.
  private _onKeyDown(e: KeyboardEvent): void {
    if (this.collapsed !== 'none') return;
    const horiz = this.orientation === 'horizontal';
    let delta = 0;
    if ((horiz && e.key === 'ArrowLeft') || (!horiz && e.key === 'ArrowUp')) delta = -2;
    else if ((horiz && e.key === 'ArrowRight') || (!horiz && e.key === 'ArrowDown')) delta = 2;
    else if (e.key === 'Home') {
      this._setSize(this.min);
      e.preventDefault();
      return;
    } else if (e.key === 'End') {
      this._setSize(this.max);
      e.preventDefault();
      return;
    } else return;
    e.preventDefault();
    this._setSize(this._size + delta);
  }

  private _setSize(v: number): void {
    const next = this._clamp(v);
    if (next !== this._size) {
      this._size = next;
      this.size = next;
      this._emit();
    }
  }

  // Emite ok-resize con el tamaño actual del primer panel (%).
  private _emit(): void {
    this.dispatchEvent(
      new CustomEvent<{ size: number }>('ok-resize', {
        detail: { size: this._size },
        bubbles: true,
        composed: true,
      }),
    );
  }

  render(): unknown {
    const horiz = this.orientation === 'horizontal';
    const startHidden = this.collapsed === 'start';
    const endHidden = this.collapsed === 'end';
    const dividerHidden = this.collapsed !== 'none';

    // Cuando hay un panel colapsado, el visible ocupa el 100%.
    const startFlex = startHidden ? '0 0 0' : endHidden ? '1 1 auto' : `0 0 ${this._size}%`;
    const endFlex = endHidden ? '0 0 0' : startHidden ? '1 1 auto' : '1 1 0';

    const axis = horiz ? 'horizontal' : 'vertical';

    return html`
      <div class="split ${axis}">
        <div
          class="pane start ${startHidden ? 'hidden' : ''}"
          style="flex:${startFlex}"
        >
          <slot name="start"></slot>
        </div>
        <div
          class="divider ${dividerHidden ? 'hidden' : ''}"
          role="separator"
          tabindex="0"
          aria-orientation=${horiz ? 'vertical' : 'horizontal'}
          aria-valuenow=${Math.round(this._size)}
          aria-valuemin=${Math.round(this.min)}
          aria-valuemax=${Math.round(this.max)}
          aria-label="Redimensionar paneles"
          @pointerdown=${this._onPointerDown}
          @pointermove=${this._onPointerMove}
          @pointerup=${this._onPointerUp}
          @pointercancel=${this._onPointerUp}
          @keydown=${this._onKeyDown}
        >
          <span class="grip"></span>
        </div>
        <div
          class="pane end ${endHidden ? 'hidden' : ''}"
          style="flex:${endFlex}"
        >
          <slot name="end"></slot>
        </div>
      </div>
    `;
  }
}

define('ok-splitter', OkSplitter);

declare global {
  interface HTMLElementTagNameMap {
    'ok-splitter': OkSplitter;
  }
}
