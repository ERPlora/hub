import { LitElement, html, css } from 'lit';
import { property, query } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-signature — pad de firma sobre `<canvas>`.
// AUTOCONTENIDO: CSS propio en el shadow (sin Ionic salvo `ion-button`/`ion-icon` para los
// controles, que registra el host). Dibuja con pointer events trazando líneas suavizadas
// (interpolación cuadrática entre puntos). El canvas rellena el contenedor y se reescala a la
// densidad de píxeles del dispositivo (devicePixelRatio) para que la firma quede nítida.
// Props:
//   • `pen-color`  → color del trazo (def var(--ok-text))
//   • `line-width` → grosor del trazo (def 2.5)
//   • `background` → color de fondo del lienzo (def transparente)
//   • `height`     → altura del pad en px (responsive en ancho)
//   • `show-export`→ muestra el botón de exportar
// Métodos públicos:
//   • clear()                → limpia el lienzo
//   • toDataURL(type?)       → devuelve la firma como data URL (def 'image/png')
//   • isEmpty()              → true si no se ha dibujado nada
// Eventos (bubbles + composed):
//   • `ok-change` detail { empty } — al terminar un trazo
//   • `ok-clear`                   — al limpiar

// Textos i18n (default inglés). Pásalos desde fuera con `.labels`.
export interface OkSignatureLabels {
  /** Texto del botón de limpiar el lienzo. */
  clear: string;
  /** Texto del botón de exportar la firma. */
  export: string;
  /** Nombre de fichero al descargar la firma exportada. */
  exportFilename: string;
}

const DEFAULT_LABELS: OkSignatureLabels = {
  clear: 'Clear',
  export: 'Export',
  exportFilename: 'signature.png',
};

export class OkSignature extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.18));
      --bg: var(--ok-surface, var(--ion-background-color, #ffffff));
      --border-radius: var(--ok-radius, 10px);
      --height: 200px;
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* Ocupa el ancho del contenedor y es responsive. */
      display: block;
      width: 100%;
      color: var(--color);
      font-family: var(--font);
    }
    /* Marco del lienzo. */
    .pad {
      position: relative;
      width: 100%;
      height: var(--height);
      box-sizing: border-box;
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
      background: var(--bg);
      overflow: hidden;
    }
    canvas {
      display: block;
      width: 100%;
      height: 100%;
      /* Evita que el navegador interprete el gesto como scroll/zoom mientras se firma. */
      touch-action: none;
      cursor: crosshair;
    }
    /* Barra de acciones bajo el lienzo. */
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
      justify-content: flex-end;
      margin-top: 0.5rem;
    }
    ion-button {
      margin: 0;
    }
  `;

  /** Color del trazo. */
  @property({ attribute: 'pen-color' }) penColor = '';
  /** Grosor del trazo en px. */
  @property({ type: Number, attribute: 'line-width' }) lineWidth = 2.5;
  /** Color de fondo del lienzo (vacío = transparente). */
  @property() background = '';
  /** Altura del pad en px. */
  @property({ type: Number }) height = 200;
  /** Muestra el botón de exportar. */
  @property({ type: Boolean, attribute: 'show-export' }) showExport = false;
  /** Textos i18n (parcial; se mezclan sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkSignatureLabels> = {};

  private get t(): OkSignatureLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  @query('canvas') private canvas!: HTMLCanvasElement;

  private ctx: CanvasRenderingContext2D | null = null;
  // Estado del trazo en curso.
  private drawing = false;
  private lastX = 0;
  private lastY = 0;
  // Marca si el lienzo tiene algún trazo (para isEmpty / eventos).
  private hasInk = false;
  // Observa cambios de tamaño del contenedor para re-escalar el canvas.
  private ro?: ResizeObserver;

  firstUpdated(): void {
    this.ctx = this.canvas.getContext('2d');
    this.setupCanvas();
    // Reescala (y conserva la firma) cuando cambia el tamaño del contenedor.
    this.ro = new ResizeObserver(() => this.setupCanvas(true));
    this.ro.observe(this.canvas);
  }

  updated(changed: Map<string, unknown>): void {
    // Si cambia la altura por prop, refleja la var CSS del pad.
    if (changed.has('height')) {
      this.style.setProperty('--height', `${this.height}px`);
    }
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.ro?.disconnect();
  }

  // Ajusta la resolución interna del canvas a devicePixelRatio (nitidez) y reaplica el fondo
  // y los estilos de trazo. Si `preserve`, conserva la firma actual reescalándola.
  private setupCanvas(preserve = false): void {
    if (!this.canvas || !this.ctx) return;
    const rect = this.canvas.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    const dpr = window.devicePixelRatio || 1;

    // Guarda el contenido previo si hay que preservarlo.
    let snapshot: ImageData | null = null;
    if (preserve && this.canvas.width > 0 && this.canvas.height > 0) {
      try {
        snapshot = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
      } catch {
        snapshot = null;
      }
    }

    this.canvas.width = Math.round(rect.width * dpr);
    this.canvas.height = Math.round(rect.height * dpr);
    // Trabaja en coordenadas CSS: escala el contexto al ratio de píxeles.
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    this.paintBackground();
    if (snapshot) {
      // Restaura la firma previa (en píxeles físicos: reset de transform para volcar 1:1).
      this.ctx.save();
      this.ctx.setTransform(1, 0, 0, 1, 0, 0);
      this.ctx.putImageData(snapshot, 0, 0);
      this.ctx.restore();
    }
    this.applyStroke();
  }

  // Pinta el fondo (si se definió un color); si no, queda transparente.
  private paintBackground(): void {
    if (!this.ctx || !this.canvas) return;
    const rect = this.canvas.getBoundingClientRect();
    this.ctx.clearRect(0, 0, rect.width, rect.height);
    if (this.background) {
      this.ctx.fillStyle = this.background;
      this.ctx.fillRect(0, 0, rect.width, rect.height);
    }
  }

  // Configura el estilo del trazo (color, grosor, uniones redondeadas para suavizar).
  private applyStroke(): void {
    if (!this.ctx) return;
    this.ctx.lineWidth = this.lineWidth;
    this.ctx.lineCap = 'round';
    this.ctx.lineJoin = 'round';
    // Resuelve el color del lápiz: prop explícita o el token --color del host.
    this.ctx.strokeStyle =
      this.penColor ||
      getComputedStyle(this).getPropertyValue('--color').trim() ||
      '#1c1b17';
  }

  // Convierte el evento de puntero a coordenadas CSS relativas al canvas.
  private pos(e: PointerEvent): { x: number; y: number } {
    const rect = this.canvas.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  }

  private onPointerDown(e: PointerEvent): void {
    if (!this.ctx) return;
    e.preventDefault();
    this.drawing = true;
    this.applyStroke();
    const { x, y } = this.pos(e);
    this.lastX = x;
    this.lastY = y;
    // Punto inicial: un pequeño "dot" para registrar toques sin arrastre.
    this.ctx.beginPath();
    this.ctx.moveTo(x, y);
    this.ctx.lineTo(x + 0.01, y + 0.01);
    this.ctx.stroke();
    this.canvas.setPointerCapture?.(e.pointerId);
  }

  private onPointerMove(e: PointerEvent): void {
    if (!this.drawing || !this.ctx) return;
    e.preventDefault();
    const { x, y } = this.pos(e);
    // Suavizado: curva cuadrática hasta el punto medio entre el último punto y el actual.
    const midX = (this.lastX + x) / 2;
    const midY = (this.lastY + y) / 2;
    this.ctx.beginPath();
    this.ctx.moveTo(this.lastX, this.lastY);
    this.ctx.quadraticCurveTo(this.lastX, this.lastY, midX, midY);
    this.ctx.stroke();
    this.lastX = x;
    this.lastY = y;
    this.hasInk = true;
  }

  private onPointerUp(e: PointerEvent): void {
    if (!this.drawing) return;
    this.drawing = false;
    this.canvas.releasePointerCapture?.(e.pointerId);
    // Al terminar un trazo notifica el estado (vacío/no vacío).
    this.dispatchEvent(
      new CustomEvent('ok-change', {
        detail: { empty: !this.hasInk },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // ---- API pública --------------------------------------------------------

  /** Limpia el lienzo y emite `ok-clear`. */
  clear(): void {
    this.hasInk = false;
    this.paintBackground();
    this.applyStroke();
    this.dispatchEvent(new CustomEvent('ok-clear', { bubbles: true, composed: true }));
  }

  /** Devuelve la firma como data URL (def 'image/png'). */
  toDataURL(type = 'image/png'): string {
    return this.canvas ? this.canvas.toDataURL(type) : '';
  }

  /** True si no se ha dibujado nada todavía. */
  isEmpty(): boolean {
    return !this.hasInk;
  }

  render(): unknown {
    return html`
      <div class="pad">
        <canvas
          @pointerdown=${this.onPointerDown}
          @pointermove=${this.onPointerMove}
          @pointerup=${this.onPointerUp}
          @pointercancel=${this.onPointerUp}
          @pointerleave=${this.onPointerUp}
        ></canvas>
      </div>
      <div class="actions">
        <ion-button fill="clear" size="small" @click=${() => this.clear()}>
          <ion-icon slot="start" name="trash-outline"></ion-icon>
          ${this.t.clear}
        </ion-button>
        ${this.showExport
          ? html`<ion-button
              fill="solid"
              size="small"
              @click=${() => this.onExport()}
            >
              <ion-icon slot="start" name="download-outline"></ion-icon>
              ${this.t.export}
            </ion-button>`
          : ''}
      </div>
    `;
  }

  // Dispara la descarga de la firma como PNG (solo si hay tinta).
  private onExport(): void {
    if (this.isEmpty()) return;
    const url = this.toDataURL();
    const a = document.createElement('a');
    a.href = url;
    a.download = this.t.exportFilename;
    a.click();
  }
}

define('ok-signature', OkSignature);

declare global {
  interface HTMLElementTagNameMap {
    'ok-signature': OkSignature;
  }
}
