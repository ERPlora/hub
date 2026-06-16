import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-cropper — UI de recorte de imagen. Construye lo que Ionic no trae: un viewport con
// checkerboard de transparencia + overlay oscuro, rectángulo de recorte arrastrable y
// redimensionable por 4 esquinas, guías rule-of-thirds, y una toolbar con presets de aspecto
// (Libre/1:1/4:3/16:9) + Cancelar/Recortar. El rect se expresa en porcentajes del viewport
// (0..100) para ser independiente del tamaño real de la imagen.
// Eventos: `ok-crop` { rect } al pulsar Recortar; `ok-cancel` al pulsar Cancelar.
// Diseño portado de la lib css-only `.ux-cropper` (multimedia.css).

/** Relaciones de aspecto admitidas para el recorte. */
export type OkCropperAspect = 'free' | '1:1' | '4:3' | '16:9';

/** Rectángulo de recorte en porcentaje del viewport (0..100). */
export interface OkCropRect {
  /** Borde izquierdo (% del ancho). */
  x: number;
  /** Borde superior (% del alto). */
  y: number;
  /** Ancho (% del ancho del viewport). */
  width: number;
  /** Alto (% del alto del viewport). */
  height: number;
}

/** Detalle del evento `ok-crop`. */
export interface OkCropDetail {
  rect: OkCropRect;
}

type DragMode = 'move' | 'tl' | 'tr' | 'bl' | 'br';

const ASPECTS: ReadonlyArray<{ key: OkCropperAspect; label: string; ratio: number | null }> = [
  { key: 'free', label: 'Libre', ratio: null },
  { key: '1:1', label: '1:1', ratio: 1 },
  { key: '4:3', label: '4:3', ratio: 4 / 3 },
  { key: '16:9', label: '16:9', ratio: 16 / 9 },
];

const MIN_PCT = 8; // tamaño mínimo del recorte (% del viewport)

export class OkCropper extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      box-sizing: border-box;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --bg: var(--ok-surface, var(--ion-background-color, #f7f7f9));
      --border-color: var(--ok-border-color, var(--ion-border-color, #e0e0e6));
      --radius: var(--ok-radius, 16px);
      --radius-viewport: var(--ok-radius-md, 10px);
      --check-a: var(--ok-checker-a, var(--ion-color-light, #ececed));
      --check-b: var(--ok-checker-b, var(--ion-color-light-shade, #d7d8da));
      --overlay: var(--ok-cropper-overlay, rgba(0, 0, 0, 0.55));
      --crop-border: var(--ok-cropper-frame, #ffffff);
      --guide: var(--ok-cropper-guide, rgba(255, 255, 255, 0.45));
    }

    .cropper {
      background: var(--bg);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      box-sizing: border-box;
    }

    .viewport {
      position: relative;
      aspect-ratio: 4 / 3;
      width: 100%;
      /* Checkerboard de transparencia (conic) + overlay oscuro encima via ::before. */
      background: repeating-conic-gradient(var(--check-a) 0% 25%, var(--check-b) 0% 50%) 0 0 /
        16px 16px;
      border-radius: var(--radius-viewport);
      overflow: hidden;
      touch-action: none;
      user-select: none;
    }

    .viewport__img {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: block;
      pointer-events: none;
    }

    /* Atenuado base del viewport (la zona fuera del crop se oscurece extra con el box-shadow). */
    .viewport::before {
      content: '';
      position: absolute;
      inset: 0;
      background: var(--overlay);
      pointer-events: none;
    }

    .crop {
      position: absolute;
      border: 2px solid var(--crop-border);
      background: transparent;
      /* Atenua todo lo de FUERA del recorte con una sombra gigantesca. */
      box-shadow: 0 0 0 9999px var(--overlay);
      cursor: move;
      box-sizing: border-box;
    }

    /* Guías rule-of-thirds (dashed): línea central horizontal y vertical. */
    .crop::before,
    .crop::after {
      content: '';
      position: absolute;
      inset: 0;
      border: 1px dashed var(--guide);
      pointer-events: none;
    }
    .crop::before {
      border-left: none;
      border-right: none;
      top: 33.33%;
      height: 33.34%;
    }
    .crop::after {
      border-top: none;
      border-bottom: none;
      left: 33.33%;
      width: 33.34%;
    }

    .handle {
      position: absolute;
      width: 8px;
      height: 8px;
      background: var(--crop-border);
      border-radius: 1px;
      box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.25);
    }
    .handle.tl {
      top: -5px;
      left: -5px;
      cursor: nwse-resize;
    }
    .handle.tr {
      top: -5px;
      right: -5px;
      cursor: nesw-resize;
    }
    .handle.bl {
      bottom: -5px;
      left: -5px;
      cursor: nesw-resize;
    }
    .handle.br {
      bottom: -5px;
      right: -5px;
      cursor: nwse-resize;
    }

    .toolbar {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
      padding-top: 10px;
      border-top: 1px solid var(--border-color);
    }
    .spacer {
      flex: 1;
    }

    ion-button {
      --padding-start: 12px;
      --padding-end: 12px;
    }
  `;

  /** URL de la imagen a recortar. */
  @property() src?: string;

  /** Relación de aspecto forzada del recorte. */
  @property() aspect: OkCropperAspect = 'free';

  /** Rect de recorte inicial (en % del viewport). Si no se da, se usa un recorte centrado. */
  @property({ attribute: false }) value?: OkCropRect;

  /** Texto del botón de cancelar. */
  @property({ attribute: 'cancel-label' }) cancelLabel = 'Cancelar';

  /** Texto del botón de recortar. */
  @property({ attribute: 'crop-label' }) cropLabel = 'Recortar';

  // Estado interno del rect (siempre normalizado en %).
  @state() private rect: OkCropRect = { x: 14, y: 18, width: 72, height: 64 };

  private dragMode: DragMode | null = null;
  private startX = 0;
  private startY = 0;
  private startRect: OkCropRect = { x: 0, y: 0, width: 0, height: 0 };
  private vpRect: DOMRect | null = null;
  private activePointer: number | null = null;

  willUpdate(changed: Map<string, unknown>): void {
    // Sembrar el rect desde `value` cuando llega de fuera.
    if (changed.has('value') && this.value) {
      this.rect = this.clampRect(this.value);
    }
    // Al cambiar el aspect, re-encajar el recorte respetando la nueva proporción.
    if (changed.has('aspect') && !changed.has('value')) {
      this.rect = this.applyAspect(this.rect);
    }
  }

  // --- Geometría -----------------------------------------------------------

  /** Limita un rect a los bordes [0..100] del viewport. */
  private clampRect(r: OkCropRect): OkCropRect {
    const width = Math.max(MIN_PCT, Math.min(100, r.width));
    const height = Math.max(MIN_PCT, Math.min(100, r.height));
    const x = Math.max(0, Math.min(100 - width, r.x));
    const y = Math.max(0, Math.min(100 - height, r.y));
    return { x, y, width, height };
  }

  /** Aspect ratio del viewport en px (para convertir proporciones de imagen ↔ % de viewport). */
  private vpAspect(): number {
    const r = this.vpRect ?? this.renderRoot.querySelector('.viewport')?.getBoundingClientRect();
    if (r && r.height > 0) return r.width / r.height;
    return 4 / 3; // fallback: aspect-ratio por defecto del viewport
  }

  /** Re-encaja un rect para cumplir el aspect ratio activo (anclado en su esquina top-left). */
  private applyAspect(r: OkCropRect): OkCropRect {
    const def = ASPECTS.find((a) => a.key === this.aspect);
    if (!def || def.ratio == null) return this.clampRect(r);
    // ratio es ancho/alto en píxeles; el viewport no es cuadrado, así que convertimos a %.
    const va = this.vpAspect();
    // anchoPct/altoPct deben cumplir: (anchoPct*va⁻¹...) — derivamos manteniendo el ancho.
    // px: w_px/h_px = ratio; w_px = (width/100)*VW, h_px = (height/100)*VH; VW/VH = va
    // => (width*va)/height = ratio => height = width*va/ratio
    let width = r.width;
    let height = (width * va) / def.ratio;
    if (height > 100) {
      height = 100;
      width = (height * def.ratio) / va;
    }
    const x = Math.max(0, Math.min(100 - width, r.x));
    const y = Math.max(0, Math.min(100 - height, r.y));
    return { x, y, width, height };
  }

  // --- Pointer drag / resize ----------------------------------------------

  private onPointerDown(mode: DragMode, ev: PointerEvent): void {
    ev.preventDefault();
    ev.stopPropagation();
    const vp = this.renderRoot.querySelector('.viewport') as HTMLElement | null;
    if (!vp) return;
    this.vpRect = vp.getBoundingClientRect();
    this.dragMode = mode;
    this.startX = ev.clientX;
    this.startY = ev.clientY;
    this.startRect = { ...this.rect };
    this.activePointer = ev.pointerId;
    (ev.currentTarget as HTMLElement).setPointerCapture?.(ev.pointerId);
    window.addEventListener('pointermove', this.onPointerMove);
    window.addEventListener('pointerup', this.onPointerUp);
    window.addEventListener('pointercancel', this.onPointerUp);
  }

  private onPointerMove = (ev: PointerEvent): void => {
    if (!this.dragMode || !this.vpRect) return;
    if (this.activePointer != null && ev.pointerId !== this.activePointer) return;
    // Delta del puntero convertido a % del viewport.
    const dxPct = ((ev.clientX - this.startX) / this.vpRect.width) * 100;
    const dyPct = ((ev.clientY - this.startY) / this.vpRect.height) * 100;
    const s = this.startRect;

    if (this.dragMode === 'move') {
      this.rect = this.clampRect({ ...s, x: s.x + dxPct, y: s.y + dyPct });
      return;
    }
    this.rect = this.resize(s, dxPct, dyPct, this.dragMode);
  };

  /** Redimensiona desde una esquina, respetando mínimo, bordes y aspect ratio. */
  private resize(s: OkCropRect, dx: number, dy: number, mode: DragMode): OkCropRect {
    let { x, y, width, height } = s;
    const right = s.x + s.width;
    const bottom = s.y + s.height;

    if (mode === 'tl') {
      x = Math.min(s.x + dx, right - MIN_PCT);
      y = Math.min(s.y + dy, bottom - MIN_PCT);
      x = Math.max(0, x);
      y = Math.max(0, y);
      width = right - x;
      height = bottom - y;
    } else if (mode === 'tr') {
      y = Math.min(s.y + dy, bottom - MIN_PCT);
      y = Math.max(0, y);
      width = Math.max(MIN_PCT, Math.min(100 - s.x, s.width + dx));
      height = bottom - y;
    } else if (mode === 'bl') {
      x = Math.min(s.x + dx, right - MIN_PCT);
      x = Math.max(0, x);
      width = right - x;
      height = Math.max(MIN_PCT, Math.min(100 - s.y, s.height + dy));
    } else {
      // br
      width = Math.max(MIN_PCT, Math.min(100 - s.x, s.width + dx));
      height = Math.max(MIN_PCT, Math.min(100 - s.y, s.height + dy));
    }

    let next: OkCropRect = { x, y, width, height };

    // Si hay aspect ratio fijo, recomputar la dimensión dependiente y reanclar la esquina.
    const def = ASPECTS.find((a) => a.key === this.aspect);
    if (def && def.ratio != null) {
      const va = this.vpAspect();
      // height = width*va/ratio (ver applyAspect)
      const newHeight = (next.width * va) / def.ratio;
      const fixTop = mode === 'tl' || mode === 'tr';
      const fixRight = mode === 'tr' || mode === 'br';
      let nx = fixRight ? right - next.width : x;
      let ny = fixTop ? bottom - newHeight : y;
      // Si se sale del viewport, limitar por height y recomputar width.
      let nh = newHeight;
      let nw = next.width;
      if (ny < 0 || ny + nh > 100) {
        nh = Math.min(fixTop ? bottom : 100 - ny, 100);
        nw = (nh * def.ratio) / va;
        nx = fixRight ? right - nw : x;
        ny = fixTop ? bottom - nh : y;
      }
      next = { x: nx, y: ny, width: nw, height: nh };
    }

    return this.clampRect(next);
  }

  private onPointerUp = (ev: PointerEvent): void => {
    if (this.activePointer != null && ev.pointerId !== this.activePointer) return;
    this.dragMode = null;
    this.activePointer = null;
    this.vpRect = null;
    window.removeEventListener('pointermove', this.onPointerMove);
    window.removeEventListener('pointerup', this.onPointerUp);
    window.removeEventListener('pointercancel', this.onPointerUp);
  };

  disconnectedCallback(): void {
    super.disconnectedCallback();
    window.removeEventListener('pointermove', this.onPointerMove);
    window.removeEventListener('pointerup', this.onPointerUp);
    window.removeEventListener('pointercancel', this.onPointerUp);
  }

  // --- Acciones ------------------------------------------------------------

  private setAspect(a: OkCropperAspect): void {
    this.aspect = a;
    this.rect = this.applyAspect(this.rect);
  }

  private emitCrop(): void {
    this.dispatchEvent(
      new CustomEvent<OkCropDetail>('ok-crop', {
        detail: { rect: { ...this.rect } },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private emitCancel(): void {
    this.dispatchEvent(new CustomEvent('ok-cancel', { bubbles: true, composed: true }));
  }

  render(): unknown {
    const r = this.rect;
    const cropStyle = `top:${r.y}%;left:${r.x}%;width:${r.width}%;height:${r.height}%`;
    return html`
      <div class="cropper" part="cropper">
        <div class="viewport" part="viewport">
          ${this.src
            ? html`<img class="viewport__img" src=${this.src} alt="" draggable="false" />`
            : null}
          <div
            class="crop"
            part="crop"
            style=${cropStyle}
            role="group"
            aria-label="Área de recorte"
            @pointerdown=${(e: PointerEvent) => this.onPointerDown('move', e)}
          >
            <span
              class="handle tl"
              part="handle"
              @pointerdown=${(e: PointerEvent) => this.onPointerDown('tl', e)}
            ></span>
            <span
              class="handle tr"
              part="handle"
              @pointerdown=${(e: PointerEvent) => this.onPointerDown('tr', e)}
            ></span>
            <span
              class="handle bl"
              part="handle"
              @pointerdown=${(e: PointerEvent) => this.onPointerDown('bl', e)}
            ></span>
            <span
              class="handle br"
              part="handle"
              @pointerdown=${(e: PointerEvent) => this.onPointerDown('br', e)}
            ></span>
          </div>
        </div>

        <div class="toolbar" part="toolbar" role="toolbar" aria-label="Opciones de recorte">
          ${ASPECTS.map(
            (a) => html`
              <ion-button
                size="small"
                fill=${this.aspect === a.key ? 'solid' : 'clear'}
                aria-pressed=${this.aspect === a.key ? 'true' : 'false'}
                @click=${() => this.setAspect(a.key)}
              >
                ${a.label}
              </ion-button>
            `,
          )}
          <span class="spacer"></span>
          <ion-button size="small" fill="clear" color="medium" @click=${() => this.emitCancel()}>
            ${this.cancelLabel}
          </ion-button>
          <ion-button size="small" fill="solid" @click=${() => this.emitCrop()}>
            ${this.cropLabel}
          </ion-button>
        </div>
      </div>
    `;
  }
}

define('ok-cropper', OkCropper);

declare global {
  interface HTMLElementTagNameMap {
    'ok-cropper': OkCropper;
  }
}
