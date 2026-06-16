import { LitElement, html, css } from 'lit';
import { property, state, query } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-audio — reproductor de audio con controles PROPIOS sobre un `<audio>` nativo (sin libs).
// AUTOCONTENIDO: CSS propio en el shadow; sólo usa `ion-button`/`ion-icon` (los registra el host).
// Compacto y responsive (ocupa el ancho de su contenedor).
//   • prop `src`    → URL del audio
//   • prop `title`  → título opcional mostrado arriba
// Controles: play/pausa, barra de progreso clicable (seek), tiempo actual/total, volumen + mute.
// Eventos (bubbles + composed):
//   • `ok-play`   detail { currentTime }
//   • `ok-pause`  detail { currentTime }
//   • `ok-ended`  detail { duration }

// Textos i18n (default inglés). Pásalos desde fuera con `.labels`.
export interface OkAudioLabels {
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
}

const DEFAULT_LABELS: OkAudioLabels = {
  play: 'Play',
  pause: 'Pause',
  mute: 'Mute',
  unmute: 'Unmute',
  volume: 'Volume',
};

export class OkAudio extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.55));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --surface-bg: var(--ok-surface, var(--ion-card-background, #ffffff));
      --track-bg: var(--ok-border-soft, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.14));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.1));
      --border-radius: var(--ok-radius, 10px);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* Por defecto ocupa el ancho del contenedor y es responsive. */
      display: block;
      width: 100%;
      color: var(--color);
      font-family: var(--font);
    }
    .player {
      box-sizing: border-box;
      width: 100%;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      padding: 0.6rem 0.75rem;
      background: var(--surface-bg);
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
    }
    .title {
      font-size: 0.9rem;
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .controls {
      display: flex;
      align-items: center;
      gap: 0.6rem;
    }
    ion-button {
      --padding-start: 0;
      --padding-end: 0;
      margin: 0;
      flex: 0 0 auto;
    }
    .play ion-icon {
      font-size: 1.4rem;
    }
    /* Barra de progreso clicable: ocupa el espacio flexible disponible. */
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
      font-size: 0.78rem;
      color: var(--color-muted);
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    /* Bloque de volumen: el slider sólo se ve con espacio suficiente. */
    .volume {
      display: flex;
      align-items: center;
      gap: 0.25rem;
      flex: 0 0 auto;
    }
    .volume input[type='range'] {
      width: 70px;
      accent-color: var(--primary-color);
      cursor: pointer;
    }
    /* En contenedores estrechos se oculta el slider de volumen (queda el mute). */
    @media (max-width: 360px) {
      .volume input[type='range'] {
        display: none;
      }
    }
  `;

  /** URL del audio a reproducir. */
  @property() src = '';
  /** Título opcional mostrado sobre los controles. */
  @property() title = '';
  /** Textos i18n (parcial; se mezclan sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkAudioLabels> = {};

  private get t(): OkAudioLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Estado interno reflejado del elemento `<audio>` nativo.
  @state() private playing = false;
  @state() private current = 0;
  @state() private duration = 0;
  @state() private volume = 1;
  @state() private muted = false;

  @query('audio') private audioEl!: HTMLAudioElement;

  // Alterna play/pausa sobre el elemento nativo.
  private togglePlay(): void {
    if (!this.audioEl) return;
    if (this.audioEl.paused) this.audioEl.play();
    else this.audioEl.pause();
  }

  // Sincroniza el estado al darle play y re-emite `ok-play`.
  private onPlay(): void {
    this.playing = true;
    this.dispatchEvent(
      new CustomEvent('ok-play', {
        detail: { currentTime: this.audioEl?.currentTime ?? 0 },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Sincroniza el estado al pausar y re-emite `ok-pause`.
  private onPause(): void {
    this.playing = false;
    this.dispatchEvent(
      new CustomEvent('ok-pause', {
        detail: { currentTime: this.audioEl?.currentTime ?? 0 },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Fin de la reproducción: re-emite `ok-ended`.
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
    this.current = this.audioEl?.currentTime ?? 0;
  }

  private onLoadedMeta(): void {
    this.duration = this.audioEl?.duration ?? 0;
  }

  // Seek: traduce la posición del click dentro de la barra a un tiempo del audio.
  private seek(e: MouseEvent): void {
    const bar = e.currentTarget as HTMLElement;
    const rect = bar.getBoundingClientRect();
    const ratio = rect.width > 0 ? (e.clientX - rect.left) / rect.width : 0;
    const clamped = Math.min(1, Math.max(0, ratio));
    if (this.audioEl && this.duration) {
      this.audioEl.currentTime = clamped * this.duration;
    }
  }

  // Cambia el volumen desde el slider (0..1) y desactiva mute si subimos volumen.
  private onVolume(e: Event): void {
    const v = Number((e.target as HTMLInputElement).value);
    this.volume = v;
    if (this.audioEl) {
      this.audioEl.volume = v;
      this.audioEl.muted = v === 0;
    }
    this.muted = v === 0;
  }

  // Alterna mute conservando el último volumen.
  private toggleMute(): void {
    this.muted = !this.muted;
    if (this.audioEl) this.audioEl.muted = this.muted;
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
      <div class="player">
        ${this.title ? html`<div class="title">${this.title}</div>` : ''}
        <audio
          .src=${this.src}
          preload="metadata"
          @play=${this.onPlay}
          @pause=${this.onPause}
          @ended=${this.onEnded}
          @timeupdate=${this.onTimeUpdate}
          @loadedmetadata=${this.onLoadedMeta}
        ></audio>
        <div class="controls">
          <ion-button
            class="play"
            fill="clear"
            size="small"
            aria-label=${this.playing ? this.t.pause : this.t.play}
            @click=${this.togglePlay}
          >
            <ion-icon
              slot="icon-only"
              name=${this.playing ? 'pause' : 'play'}
            ></ion-icon>
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
        </div>
      </div>
    `;
  }
}

define('ok-audio', OkAudio);

declare global {
  interface HTMLElementTagNameMap {
    'ok-audio': OkAudio;
  }
}
