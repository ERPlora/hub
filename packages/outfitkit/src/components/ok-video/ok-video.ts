import { LitElement, html, css } from 'lit';
import { property, state, query } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-video — reproductor de vídeo con controles PROPIOS sobre un `<video>` nativo (sin libs).
// AUTOCONTENIDO: CSS propio en el shadow; sólo usa `ion-button`/`ion-icon` (los registra el host).
// RESPONSIVE: ocupa el ancho del contenedor con aspect-ratio 16/9 por defecto.
//   • prop `src`     → URL del vídeo
//   • prop `poster`  → imagen de previsualización opcional
// Controles: overlay de play/pausa central, barra de progreso (seek), tiempo, volumen + mute,
// pantalla completa (API nativa `requestFullscreen`).
// Eventos (bubbles + composed):
//   • `ok-play`   detail { currentTime }
//   • `ok-pause`  detail { currentTime }
//   • `ok-ended`  detail { duration }

// Textos i18n (default inglés). Pásalos desde fuera con `.labels`.
export interface OkVideoLabels {
  /** aria-label del botón cuando está pausado (acción: reproducir). */
  play: string;
  /** aria-label del botón cuando reproduce (acción: pausar). */
  pause: string;
  /** aria-label del botón de mute cuando hay sonido (acción: silenciar). */
  mute: string;
  /** aria-label del botón de mute cuando está silenciado (acción: activar sonido). */
  unmute: string;
  /** aria-label del slider de volumen. */
  volume: string;
  /** aria-label del botón de pantalla completa. */
  fullscreen: string;
}

const DEFAULT_LABELS: OkVideoLabels = {
  play: 'Play',
  pause: 'Pause',
  mute: 'Mute',
  unmute: 'Unmute',
  volume: 'Volume',
  fullscreen: 'Fullscreen',
};

export class OkVideo extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --track-bg: rgba(255, 255, 255, 0.3);
      --bar-bg: var(--ok-video-bar, rgba(0, 0, 0, 0.55));
      --border-radius: var(--ok-radius, 10px);
      --aspect: var(--ok-video-aspect, 16 / 9);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* Responsive: bloque al ancho del contenedor. */
      display: block;
      width: 100%;
      color: var(--color);
      font-family: var(--font);
    }
    .stage {
      position: relative;
      width: 100%;
      aspect-ratio: var(--aspect);
      background: #000;
      border-radius: var(--border-radius);
      overflow: hidden;
    }
    video {
      display: block;
      width: 100%;
      height: 100%;
      object-fit: contain;
      background: #000;
    }
    /* Botón grande de play/pausa centrado sobre el vídeo. */
    .overlay {
      position: absolute;
      inset: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      background: transparent;
      border: 0;
      color: #fff;
      cursor: pointer;
    }
    .overlay .big {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 64px;
      height: 64px;
      border-radius: 50%;
      background: rgba(0, 0, 0, 0.45);
      transition: opacity 0.18s ease, transform 0.18s ease;
    }
    .overlay .big ion-icon {
      font-size: 2rem;
    }
    /* Mientras reproduce, el overlay se atenúa salvo al pasar el ratón. */
    .overlay.playing .big {
      opacity: 0;
    }
    .stage:hover .overlay.playing .big {
      opacity: 1;
    }
    /* Barra de controles inferior. */
    .bar {
      position: absolute;
      left: 0;
      right: 0;
      bottom: 0;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.4rem 0.6rem;
      background: linear-gradient(transparent, var(--bar-bg));
      color: #fff;
    }
    ion-button {
      --color: #fff;
      --padding-start: 0;
      --padding-end: 0;
      margin: 0;
      flex: 0 0 auto;
    }
    .progress {
      position: relative;
      flex: 1 1 auto;
      min-width: 0;
      height: 6px;
      border-radius: 999px;
      background: var(--track-bg);
      cursor: pointer;
    }
    .progress .fill {
      position: absolute;
      inset: 0 auto 0 0;
      height: 100%;
      border-radius: inherit;
      background: var(--primary-color);
      width: 0%;
    }
    .progress .knob {
      position: absolute;
      top: 50%;
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: var(--primary-color);
      transform: translate(-50%, -50%);
      left: 0%;
    }
    .time {
      flex: 0 0 auto;
      font-size: 0.75rem;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    .volume input[type='range'] {
      width: 64px;
      accent-color: var(--primary-color);
      cursor: pointer;
      vertical-align: middle;
    }
    /* En estrecho, se ocultan el slider de volumen y el reloj para no saturar. */
    @media (max-width: 420px) {
      .volume input[type='range'] {
        display: none;
      }
      .time {
        display: none;
      }
    }
  `;

  /** URL del vídeo a reproducir. */
  @property() src = '';
  /** Imagen de previsualización opcional. */
  @property() poster = '';
  /** Textos i18n (parcial; se mezclan sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkVideoLabels> = {};

  private get t(): OkVideoLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Estado interno reflejado del elemento `<video>` nativo.
  @state() private playing = false;
  @state() private current = 0;
  @state() private duration = 0;
  @state() private volume = 1;
  @state() private muted = false;

  @query('video') private videoEl!: HTMLVideoElement;
  @query('.stage') private stageEl!: HTMLElement;

  // Alterna play/pausa sobre el elemento nativo.
  private togglePlay(): void {
    if (!this.videoEl) return;
    if (this.videoEl.paused) this.videoEl.play();
    else this.videoEl.pause();
  }

  private onPlay(): void {
    this.playing = true;
    this.dispatchEvent(
      new CustomEvent('ok-play', {
        detail: { currentTime: this.videoEl?.currentTime ?? 0 },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private onPause(): void {
    this.playing = false;
    this.dispatchEvent(
      new CustomEvent('ok-pause', {
        detail: { currentTime: this.videoEl?.currentTime ?? 0 },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private onEnded(): void {
    this.playing = false;
    this.dispatchEvent(
      new CustomEvent('ok-ended', {
        detail: { duration: this.duration },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private onTimeUpdate(): void {
    this.current = this.videoEl?.currentTime ?? 0;
  }

  private onLoadedMeta(): void {
    this.duration = this.videoEl?.duration ?? 0;
  }

  // Seek: traduce la posición del click dentro de la barra a un tiempo del vídeo.
  private seek(e: MouseEvent): void {
    e.stopPropagation();
    const bar = e.currentTarget as HTMLElement;
    const rect = bar.getBoundingClientRect();
    const ratio = rect.width > 0 ? (e.clientX - rect.left) / rect.width : 0;
    const clamped = Math.min(1, Math.max(0, ratio));
    if (this.videoEl && this.duration) {
      this.videoEl.currentTime = clamped * this.duration;
    }
  }

  private onVolume(e: Event): void {
    const v = Number((e.target as HTMLInputElement).value);
    this.volume = v;
    if (this.videoEl) {
      this.videoEl.volume = v;
      this.videoEl.muted = v === 0;
    }
    this.muted = v === 0;
  }

  private toggleMute(): void {
    this.muted = !this.muted;
    if (this.videoEl) this.videoEl.muted = this.muted;
  }

  // Pantalla completa con la API nativa (sobre el contenedor, para conservar los controles).
  private toggleFullscreen(): void {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else if (this.stageEl?.requestFullscreen) {
      this.stageEl.requestFullscreen();
    }
  }

  // Formatea segundos a m:ss (sin libs de fechas).
  private fmt(secs: number): string {
    if (!isFinite(secs) || secs < 0) secs = 0;
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  render(): unknown {
    const pct = this.duration ? (this.current / this.duration) * 100 : 0;
    const volIcon = this.muted || this.volume === 0
      ? 'volume-mute-outline'
      : this.volume < 0.5
        ? 'volume-low-outline'
        : 'volume-high-outline';

    return html`
      <div class="stage">
        <video
          .src=${this.src}
          poster=${this.poster || ''}
          playsinline
          @play=${this.onPlay}
          @pause=${this.onPause}
          @ended=${this.onEnded}
          @timeupdate=${this.onTimeUpdate}
          @loadedmetadata=${this.onLoadedMeta}
          @click=${this.togglePlay}
        ></video>

        <button
          class=${`overlay ${this.playing ? 'playing' : ''}`}
          aria-label=${this.playing ? this.t.pause : this.t.play}
          @click=${this.togglePlay}
        >
          <span class="big">
            <ion-icon name=${this.playing ? 'pause' : 'play'}></ion-icon>
          </span>
        </button>

        <div class="bar">
          <ion-button
            fill="clear"
            size="small"
            aria-label=${this.playing ? this.t.pause : this.t.play}
            @click=${this.togglePlay}
          >
            <ion-icon slot="icon-only" name=${this.playing ? 'pause' : 'play'}></ion-icon>
          </ion-button>

          <div class="progress" @click=${this.seek}>
            <div class="fill" style=${`width:${pct}%`}></div>
            <div class="knob" style=${`left:${pct}%`}></div>
          </div>

          <span class="time">${this.fmt(this.current)} / ${this.fmt(this.duration)}</span>

          <div class="volume">
            <ion-button
              fill="clear"
              size="small"
              aria-label=${this.muted ? this.t.unmute : this.t.mute}
              @click=${this.toggleMute}
            >
              <ion-icon slot="icon-only" name=${volIcon}></ion-icon>
            </ion-button>
            <input
              type="range"
              min="0"
              max="1"
              step="0.01"
              .value=${String(this.muted ? 0 : this.volume)}
              @input=${this.onVolume}
              aria-label=${this.t.volume}
            />
          </div>

          <ion-button
            fill="clear"
            size="small"
            aria-label=${this.t.fullscreen}
            @click=${this.toggleFullscreen}
          >
            <ion-icon slot="icon-only" name="expand-outline"></ion-icon>
          </ion-button>
        </div>
      </div>
    `;
  }
}

define('ok-video', OkVideo);

declare global {
  interface HTMLElementTagNameMap {
    'ok-video': OkVideo;
  }
}
