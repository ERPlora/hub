// The display's chime (KITCHEN-F16): two short notes made with Web Audio — no sound file to fetch (CSP:
// nothing from the network) — with the tone and the volume of the settings. One AudioContext per screen
// (browsers cap how many a page opens). Every path is non-fatal: a display that stops showing tickets
// because the browser would not give it a speaker is far worse than a silent one.
import type { SoundTone } from '../operations';

interface AudioParamLike {
  value: number;
  setValueAtTime(value: number, at: number): void;
  linearRampToValueAtTime?(value: number, at: number): void;
}

interface AudioContextLike {
  state: string;
  currentTime: number;
  destination: unknown;
  resume(): Promise<void>;
  createGain(): { gain: AudioParamLike & { linearRampToValueAtTime(value: number, at: number): void }; connect(target: unknown): void };
  createOscillator(): {
    type: string;
    frequency: AudioParamLike;
    connect(target: unknown): void;
    start(at: number): void;
    stop(at: number): void;
  };
}

type AudioContextCtor = new () => AudioContextLike;

const TONE_SECONDS = 0.12;
const GAP_SECONDS = 0.03;
/** The gain at volume 100; the factory volume (70) gives 0.35, the old module's chime. */
const PEAK_GAIN_AT_MAX_VOLUME = 0.5;
const DEFAULT_VOLUME = 70;

const TONES = {
  /** The rising pair the kitchen has always rung. */
  chime: { wave: 'sine', notes: [880, 1320] },
  /** Brighter and higher, for a line where the chime blends into the room. */
  bell: { wave: 'triangle', notes: [1568, 2349] },
  /** Low, harsh and repeated: it carries over a hood at full blast. */
  buzzer: { wave: 'square', notes: [330, 330] },
} as const satisfies Record<SoundTone, { wave: string; notes: readonly number[] }>;

export const CHIME_TONES = Object.keys(TONES) as SoundTone[];

export interface ChimeOptions {
  tone: SoundTone;
  /** 0–100; out of range is clamped. */
  volume: number;
}

export interface Ring {
  peak: number;
  wave: string;
  notes: number[];
}

/** The ring of the settings: an unknown tone rings the chime; zero stays zero (silence chosen). */
export function ringFor(options: ChimeOptions): Ring {
  const spec = TONES[options.tone] ?? TONES.chime;
  const volume = Number.isFinite(options.volume) ? Math.min(100, Math.max(0, options.volume)) : DEFAULT_VOLUME;
  return { peak: (volume / 100) * PEAK_GAIN_AT_MAX_VOLUME, wave: spec.wave, notes: [...spec.notes] };
}

function audioContextCtor(): AudioContextCtor | undefined {
  const scope = globalThis as { AudioContext?: AudioContextCtor; webkitAudioContext?: AudioContextCtor };
  return scope.AudioContext ?? scope.webkitAudioContext;
}

export class Chime {
  private context?: AudioContextLike;
  private reported = false;
  private unlockArmed = false;

  /** Rings; `false` only when this browser has no Web Audio at all (no retry will ever sound). */
  play(options: ChimeOptions): boolean {
    const context = this.audio();
    if (!context) return false;
    const ring = ringFor(options);
    if (context.state === 'suspended') {
      context
        .resume()
        .then(() => (context.state === 'suspended' ? this.armUnlock(context) : this.ring(context, ring)))
        .catch(() => this.armUnlock(context));
      return true;
    }
    this.ring(context, ring);
    return true;
  }

  private audio(): AudioContextLike | undefined {
    if (this.context) return this.context;
    const Ctor = audioContextCtor();
    try {
      if (Ctor) this.context = new Ctor();
    } catch {
      this.context = undefined;
    }
    if (!this.context && !this.reported) {
      this.reported = true;
      console.warn('[kitchen] this browser gives no Web Audio: the display cannot ring on a new ticket');
    }
    return this.context;
  }

  /** The browser wants a gesture first: the next touch or key unlocks it for the rest of the shift. */
  private armUnlock(context: AudioContextLike): void {
    if (this.unlockArmed) return;
    this.unlockArmed = true;
    const unlock = () => void context.resume().catch(() => undefined);
    document.addEventListener('pointerdown', unlock, { once: true });
    document.addEventListener('keydown', unlock, { once: true });
  }

  private ring(context: AudioContextLike, { peak, wave, notes }: Ring): void {
    if (peak <= 0) return;
    try {
      let at = context.currentTime;
      for (const note of notes) {
        const gain = context.createGain();
        gain.gain.setValueAtTime(0, at);
        gain.gain.linearRampToValueAtTime(peak, at + 0.01);
        gain.gain.linearRampToValueAtTime(0, at + TONE_SECONDS);
        gain.connect(context.destination);
        const oscillator = context.createOscillator();
        oscillator.type = wave;
        oscillator.frequency.setValueAtTime(note, at);
        oscillator.connect(gain);
        oscillator.start(at);
        oscillator.stop(at + TONE_SECONDS);
        at += TONE_SECONDS + GAP_SECONDS;
      }
    } catch (error) {
      console.warn('[kitchen] the chime could not ring', error);
    }
  }
}
