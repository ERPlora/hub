// The till's «Speak» key (WORKBOOK «Vender»; PLAN §30 point 4, PLAN-HUB §8 round 2026-10-22b): open the assistant by
// dictating. Only to whoever may use the assistant (`base.view_home`) on a device that can record; offline it stays,
// greyed, and a tap says why. A first tap records («Listening…», the key turns «Stop»), a second one stops; the words
// are transcribed by erplora.com, land in the assistant's box after what was written and the panel opens: the person
// sees what was understood and sends it. Nothing is sent by itself. A refusal, an empty or too long dictation and a
// failure are a toast.
import { type SessionMe, toast } from '@erplora/ui/shell';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { type Assistant, createAssistant, installAssistant } from '../../../../../base/frontend/lib/assistant';
import { ASSISTANT_ICONS } from '../../../../../base/frontend/lib/assistant-icons';
import type { TurnBody } from '../../../../../base/frontend/lib/assistant-stream';
import { EMPLOYEE, mountSale, settle } from '../../__tests__/mount-sale';
import SpeakKey from './SpeakKey.vue';

vi.mock('@erplora/ui/shell', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/shell')>()),
  toast: vi.fn(() => Promise.resolve()),
}));

/** A cashier who may use the assistant: it answers to whoever sees the Home. */
const CASHIER: SessionMe = { ...EMPLOYEE, permissions: [...EMPLOYEE.permissions, 'base.view_home'] };

function memoryStorage(): Storage {
  const store = new Map<string, string>();
  return {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (key) => store.get(key) ?? null,
    key: (index) => [...store.keys()][index] ?? null,
    removeItem: (key) => void store.delete(key),
    setItem: (key, value) => void store.set(key, value),
  };
}

let assistant: Assistant;
let posted: TurnBody[];

beforeEach(() => {
  posted = [];
  assistant = createAssistant({
    storage: memoryStorage(),
    openStorage: memoryStorage(),
    post: async (body: TurnBody) => {
      posted.push(body);
    },
  });
  assistant.forUser('u1');
  installAssistant(assistant);
});

afterEach(() => {
  installAssistant(undefined);
  vi.mocked(toast).mockClear();
  vi.restoreAllMocks();
});

class Recorder {
  static isTypeSupported = () => true;
  static clip: Blob = new Blob(['voz'], { type: 'audio/webm' });
  state = 'inactive';
  mimeType = 'audio/webm;codecs=opus';
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  start() {
    this.state = 'recording';
  }
  stop() {
    this.state = 'inactive';
    this.ondataavailable?.({ data: Recorder.clip });
    this.onstop?.();
  }
}

function microphone() {
  const released = vi.fn();
  return {
    released,
    getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: released }] }) as unknown as MediaStream),
    MediaRecorder: Recorder as never,
  };
}

/** The icon a key paints: `ion-icon`'s `src` is a property, not an attribute. */
const iconOf = (el: Element): string | undefined => (el.querySelector('ion-icon') as (HTMLElement & { src?: string }) | null)?.src;

interface Options {
  voice?: object;
  session?: SessionMe;
  locale?: 'en' | 'es';
  answer?: { status: number; body: unknown };
}

async function key(options: Options = {}) {
  Recorder.clip = new Blob(['voz'], { type: 'audio/webm' });
  const m = await mountSale(SpeakKey, {
    props: { voice: options.voice ?? microphone() },
    session: options.session ?? CASHIER,
    locale: options.locale ?? 'es',
    answer: options.answer ?? { status: 200, body: { text: 'cobra la mesa 4', language: 'es' } },
  });
  const button = () => m.find('pos-speak');
  const press = async () => {
    await button().trigger('click');
    await settle();
  };
  const transcriptions = () => m.sent().filter((call) => call.path === '/api/assistant/transcribe');
  return { ...m, button, press, transcriptions };
}

describe('SpeakKey: who sees it', () => {
  it('shows «Hablar» with the microphone to whoever may use the assistant on a device that records', async () => {
    const k = await key();
    expect(k.button().exists()).toBe(true);
    expect(k.button().text()).toBe('Hablar');
    expect(k.button().attributes('aria-pressed')).toBe('false');
    // The assistant composer's own microphone.
    expect(iconOf(k.button().element)).toBe(ASSISTANT_ICONS.mic);
  });

  it('speaks English: «Speak»', async () => {
    const k = await key({ locale: 'en' });
    expect(k.button().text()).toBe('Speak');
  });

  it('is not there for a person who may not use the assistant', async () => {
    const k = await key({ session: EMPLOYEE });
    expect(k.button().exists()).toBe(false);
  });

  it('is not there where the device cannot record', async () => {
    const k = await key({ voice: {} });
    expect(k.button().exists()).toBe(false);
  });
});

describe('SpeakKey: dictating into the assistant', () => {
  it('records, stops on the second tap, and leaves the words in the box with the panel open: nothing is sent', async () => {
    const voice = microphone();
    const k = await key({ voice });
    assistant.state.draft = 'y luego';
    await k.press();
    expect(voice.getUserMedia).toHaveBeenCalledWith({ audio: true });
    expect(k.button().text()).toBe('Parar');
    expect(k.button().attributes('aria-pressed')).toBe('true');
    expect(iconOf(k.button().element)).toBe(ASSISTANT_ICONS.stop);
    expect(k.find('pos-speak-status').text()).toBe('Escuchando…');
    expect(assistant.state.open).toBe(false);

    await k.press();
    expect(k.transcriptions().map((call) => call.body)).toEqual([{ audio: 'dm96', mime_type: 'audio/webm', language: 'es' }]);
    expect(voice.released).toHaveBeenCalled();
    expect(assistant.state.draft).toBe('y luego cobra la mesa 4');
    expect(assistant.state.open).toBe(true);
    expect(posted).toEqual([]);
    expect(assistant.state.thread.bubbles).toEqual([]);
    expect(k.button().text()).toBe('Hablar');
    expect(k.find('pos-speak-status').exists()).toBe(false);
    expect(toast).not.toHaveBeenCalled();
  });

  it('says «Transcribiendo…» and takes no tap while erplora.com transcribes', async () => {
    let finish: (response: Response) => void = () => undefined;
    const k = await key();
    k.net.onApi(() => new Promise<Response>((resolve) => (finish = resolve)));
    await k.press();
    await k.press();
    expect(k.find('pos-speak-status').text()).toBe('Transcribiendo…');
    expect(k.button().attributes('disabled')).toBeDefined();
    finish(Response.json({ text: 'dos cafés', language: 'es' }));
    await settle();
    expect(assistant.state.draft).toBe('dos cafés');
    expect(k.button().attributes('disabled')).toBeUndefined();
  });

  it('an empty dictation is a toast: the box and the panel stay as they were', async () => {
    const k = await key({ answer: { status: 200, body: { text: '   ', language: 'es' } } });
    await k.press();
    await k.press();
    expect(toast).toHaveBeenCalledWith('No se ha oído nada. Inténtalo de nuevo más cerca del micrófono.', 'warning');
    expect(assistant.state.draft).toBe('');
    expect(assistant.state.open).toBe(false);
  });

  it('a failed transcription is a toast and opens nothing', async () => {
    const k = await key({
      answer: { status: 502, body: { code: 'base.assistant_transcribe_failed', message: 'The audio could not be transcribed: try again.' } },
    });
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    await k.press();
    await k.press();
    expect(toast).toHaveBeenCalledWith('No se ha podido transcribir el audio. Inténtalo de nuevo.', 'danger');
    expect(assistant.state.open).toBe(false);
    expect(k.button().text()).toBe('Hablar');
  });

  it('a recording longer than erplora.com takes is not sent: a toast says to say something shorter', async () => {
    const k = await key();
    Recorder.clip = new Blob([new Uint8Array(2 * 1024 * 1024 + 1)], { type: 'audio/webm' });
    await k.press();
    await k.press();
    expect(k.transcriptions()).toEqual([]);
    expect(toast).toHaveBeenCalledWith('La grabación es demasiado larga: di algo más corto.', 'warning');
  });

  it('a microphone the browser refuses is a toast that says how to allow it', async () => {
    const voice = { ...microphone(), getUserMedia: vi.fn(async () => Promise.reject(new DOMException('no', 'NotAllowedError'))) };
    const k = await key({ voice });
    await k.press();
    expect(toast).toHaveBeenCalledWith('El acceso al micrófono está denegado. Permítelo en tu navegador para hablar.', 'warning');
    expect(k.button().text()).toBe('Hablar');
    expect(k.find('pos-speak-status').exists()).toBe(false);
  });

  // The installed app (Android, Windows) has no browser bar: there a refused microphone is allowed again in the
  // device's settings (as the assistant's composer, BASE-F94). Tauri does not run here: its bridge is simulated.
  it('a microphone refused inside the installed app is a toast that points to the device settings', async () => {
    const win = window as unknown as { __TAURI__?: unknown };
    const refusal = async (locale: 'en' | 'es') => {
      const voice = { ...microphone(), getUserMedia: vi.fn(async () => Promise.reject(new DOMException('no', 'NotAllowedError'))) };
      const k = await key({ voice, locale });
      await k.press();
      expect(k.find('pos-speak-status').exists()).toBe(false);
      k.wrapper.unmount();
    };
    win.__TAURI__ = { core: { invoke: vi.fn(async () => null) } };
    try {
      await refusal('es');
      expect(toast).toHaveBeenLastCalledWith('El acceso al micrófono está denegado. Permítelo en los ajustes del dispositivo para hablar.', 'warning');
      await refusal('en');
      expect(toast).toHaveBeenLastCalledWith('Microphone access is blocked. Allow it in your device settings to speak.', 'warning');
    } finally {
      delete win.__TAURI__;
    }
    await refusal('en');
    expect(toast).toHaveBeenLastCalledWith('Microphone access is blocked. Allow it in your browser to speak.', 'warning');
  });

  it('leaving the till while recording frees the microphone and transcribes nothing', async () => {
    const voice = microphone();
    const k = await key({ voice });
    await k.press();
    k.wrapper.unmount();
    expect(voice.released).toHaveBeenCalled();
    expect(k.transcriptions()).toEqual([]);
  });

  it('a second tap while the browser still asks for the microphone opens no second recording', async () => {
    let grant: (stream: MediaStream) => void = () => undefined;
    const released = vi.fn();
    const voice = {
      ...microphone(),
      getUserMedia: vi.fn(() => new Promise<MediaStream>((resolve) => (grant = resolve))),
    };
    const k = await key({ voice });
    await k.press();
    await k.press();
    expect(voice.getUserMedia).toHaveBeenCalledTimes(1);
    grant({ getTracks: () => [{ stop: released }] } as unknown as MediaStream);
    await settle();
    expect(k.button().text()).toBe('Parar');
    await k.press();
    expect(released).toHaveBeenCalledTimes(1);
    expect(k.transcriptions()).toHaveLength(1);
  });
});

describe('SpeakKey: without connection', () => {
  it('stays greyed, and a tap says why instead of recording; back online it records again', async () => {
    const online = vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
    const voice = microphone();
    const k = await key({ voice });
    expect(k.button().attributes('aria-disabled')).toBe('true');
    expect(k.button().attributes('title')).toBe('Sin conexión: para hablar con el asistente hace falta internet.');
    await k.press();
    expect(voice.getUserMedia).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith('Sin conexión: para hablar con el asistente hace falta internet.', 'warning');

    online.mockReturnValue(true);
    window.dispatchEvent(new Event('online'));
    await settle();
    expect(k.button().attributes('aria-disabled')).toBe('false');
    await k.press();
    expect(voice.getUserMedia).toHaveBeenCalled();
    await k.press();
  });
});
