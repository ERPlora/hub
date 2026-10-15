// The display's chime (KITCHEN-F16): Web Audio only, no sound files; the tone and volume of the
// settings; a volume of 0 is silence by choice; a browser that will not start audio until a touch rings
// from the first touch on; no Web Audio at all is silence, never an error.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Chime, CHIME_TONES, ringFor } from './chime';

class FakeContext {
  static made = 0;
  state = 'running';
  currentTime = 0;
  destination = {};
  oscillators: { type: string; notes: number[] }[] = [];
  gains: number[] = [];
  constructor() {
    FakeContext.made += 1;
  }
  resume = vi.fn(async () => {
    this.state = 'running';
  });
  createGain() {
    const gains = this.gains;
    return {
      gain: {
        value: 0,
        setValueAtTime: vi.fn(),
        linearRampToValueAtTime: (value: number) => {
          if (value > 0) gains.push(value);
        },
      },
      connect: vi.fn(),
    };
  }
  createOscillator() {
    const oscillator = { type: '', notes: [] as number[] };
    this.oscillators.push(oscillator);
    return {
      set type(value: string) {
        oscillator.type = value;
      },
      frequency: { value: 0, setValueAtTime: (value: number) => oscillator.notes.push(value) },
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
    };
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  FakeContext.made = 0;
});

describe('ringFor', () => {
  it('is the tone and the volume of the settings; an unknown tone rings the chime, zero is silence', () => {
    expect(CHIME_TONES).toEqual(['chime', 'bell', 'buzzer']);
    expect(ringFor({ tone: 'buzzer', volume: 100 })).toEqual({ peak: 0.5, wave: 'square', notes: [330, 330] });
    expect(ringFor({ tone: 'siren' as never, volume: 70 }).wave).toBe('sine');
    expect(ringFor({ tone: 'bell', volume: 0 }).peak).toBe(0);
    expect(ringFor({ tone: 'bell', volume: 250 }).peak).toBe(0.5);
  });
});

describe('Chime', () => {
  it('rings two notes with one audio context for the whole shift', () => {
    vi.stubGlobal('AudioContext', FakeContext);
    const chime = new Chime();
    expect(chime.play({ tone: 'chime', volume: 70 })).toBe(true);
    expect(chime.play({ tone: 'chime', volume: 70 })).toBe(true);
    expect(FakeContext.made).toBe(1);
  });

  it('a volume of 0 is silence by choice, not a failure', () => {
    vi.stubGlobal('AudioContext', FakeContext);
    const chime = new Chime();
    expect(chime.play({ tone: 'chime', volume: 0 })).toBe(true);
  });

  it('without Web Audio it stays silent and says so once', () => {
    vi.stubGlobal('AudioContext', undefined);
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const chime = new Chime();
    expect(chime.play({ tone: 'chime', volume: 70 })).toBe(false);
    expect(chime.play({ tone: 'chime', volume: 70 })).toBe(false);
    expect(warn).toHaveBeenCalledTimes(1);
  });
});
