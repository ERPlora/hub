// The assistant's composer (BASE-G111, G112): write and send with Enter (a new line with Shift+Enter, and on a touch
// screen); attach what erplora.com reads, each file a chip that can be removed, a refusal said in a line; dictate —
// the words land in the box and nothing is sent until the person sends; «Stop» while the answer comes.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { accessibleName, flush, memoryStorage, mountBase } from '../../__tests__/mount-base';
import { type Assistant, createAssistant, installAssistant } from '../../lib/assistant';
import type { TurnBody, TurnOptions } from '../../lib/assistant-stream';
import AssistantComposer from './AssistantComposer.vue';

let assistant: Assistant;
let posted: TurnBody[];

beforeEach(() => {
  posted = [];
  assistant = createAssistant({
    storage: memoryStorage(),
    openStorage: memoryStorage(),
    post: (body: TurnBody, options: TurnOptions) => {
      posted.push(body);
      // The answer never comes: only «Stop» ends the turn.
      return new Promise<void>((_resolve, reject) => {
        options.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
      });
    },
  });
  assistant.forUser('u1');
  installAssistant(assistant);
});

afterEach(() => {
  installAssistant(undefined);
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
});

class Recorder {
  static isTypeSupported = () => true;
  static current: Recorder;
  state = 'inactive';
  mimeType = 'audio/webm;codecs=opus';
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor() {
    Recorder.current = this;
  }
  start() {
    this.state = 'recording';
  }
  stop() {
    this.state = 'inactive';
    this.ondataavailable?.({ data: new Blob(['voz'], { type: 'audio/webm' }) });
    this.onstop?.();
  }
}

const microphone = () => ({
  getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: () => undefined }] }) as unknown as MediaStream),
  MediaRecorder: Recorder as never,
});

type Sent = { url: string; body: Record<string, unknown> };

async function composer(
  options: { offline?: boolean; voice?: object; answer?: (sent: Sent) => Response; locale?: 'en' | 'es' } = {},
) {
  const sent: Sent[] = [];
  const m = await mountBase(AssistantComposer, {
    locale: options.locale ?? 'es',
    props: { offline: options.offline ?? false, voice: options.voice ?? {} },
    onApi: ({ url, init }) => {
      const call = { url, body: JSON.parse(String(init.body ?? '{}')) as Record<string, unknown> };
      sent.push(call);
      return (options.answer ?? (() => Response.json({ text: 'dos cafés', language: 'es' })))(call);
    },
  });
  return { ...m, sent };
}

const box = (m: Awaited<ReturnType<typeof composer>>) => m.wrapper.get('[data-testid="assistant-input"]');

async function type(m: Awaited<ReturnType<typeof composer>>, text: string) {
  box(m).element.dispatchEvent(new CustomEvent('ionInput', { detail: { value: text } }));
  await flush();
}

function key(m: Awaited<ReturnType<typeof composer>>, fields: KeyboardEventInit) {
  const event = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true, ...fields });
  box(m).element.dispatchEvent(event);
  return event;
}

async function attach(m: Awaited<ReturnType<typeof composer>>, ...files: File[]) {
  const input = m.wrapper.get('[data-testid="assistant-attach-input"]').element as HTMLInputElement;
  Object.defineProperty(input, 'files', { value: files, configurable: true });
  input.dispatchEvent(new Event('change'));
  for (let i = 0; i < 4; i += 1) await flush();
}

describe('AssistantComposer', () => {
  // gh:hub#1811: the old box had no stable name, so no robot (nor screen reader) could write to the assistant.
  it('the box has a stable name and its placeholder, and Enter sends what was written', async () => {
    const m = await composer();
    // Ionic Vue sets these as the element's properties (the textarea inside reads them).
    const textarea = box(m).element as HTMLElement & { name?: string; placeholder?: string };
    expect([textarea.name, textarea.placeholder]).toEqual(['assistant-message', 'Escribe un mensaje…']);
    await type(m, '¿Cuánto he vendido hoy?');
    expect(key(m, {}).defaultPrevented).toBe(true);
    await flush();
    expect(posted[0].messages).toEqual([{ role: 'user', content: '¿Cuánto he vendido hoy?' }]);
    expect(assistant.state.draft).toBe('');
  });

  it('Shift+Enter is a new line; on a touch screen Enter is too, and the button sends', async () => {
    const m = await composer();
    await type(m, 'Hola');
    expect(key(m, { shiftKey: true }).defaultPrevented).toBe(false);
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: query === '(pointer: coarse)' }));
    expect(key(m, {}).defaultPrevented).toBe(false);
    expect(posted).toEqual([]);
    await m.wrapper.get('[data-testid="assistant-send"]').trigger('click');
    expect(posted).toHaveLength(1);
  });

  it('nothing to send with an empty box or without a connection', async () => {
    const empty = await composer();
    expect(empty.wrapper.get('[data-testid="assistant-send"]').attributes('disabled')).toBeDefined();
    empty.wrapper.unmount();
    const offline = await composer({ offline: true });
    await type(offline, 'Hola');
    expect(offline.wrapper.get('[data-testid="assistant-send"]').attributes('disabled')).toBeDefined();
    key(offline, {});
    expect(posted).toEqual([]);
  });

  it('while the answer comes, «Stop» instead of «Send», and it stops it', async () => {
    const m = await composer();
    await type(m, 'Hola');
    key(m, {});
    await flush();
    expect(m.wrapper.find('[data-testid="assistant-send"]').exists()).toBe(false);
    await m.wrapper.get('[data-testid="assistant-stop"]').trigger('click');
    for (let i = 0; i < 3; i += 1) await flush();
    expect(assistant.state.busy).toBe(false);
    expect(assistant.state.thread.bubbles.at(-1)?.stopped).toBe(true);
    expect(m.wrapper.find('[data-testid="assistant-send"]').exists()).toBe(true);
  });

  it('attaches what erplora.com reads, as chips that can be removed, and they go with the question', async () => {
    const m = await composer();
    await attach(m, new File(['hola'], 'notas.md', { type: '' }), new File(['%PDF'], 'carta.pdf', { type: 'application/pdf' }));
    const chips = m.wrapper.findAll('[data-testid="assistant-file"]');
    expect(chips.map((chip) => chip.text())).toEqual(['notas.md', 'carta.pdf']);
    await m.wrapper.get('[data-testid="assistant-file-remove-1"]').trigger('click');
    expect(m.wrapper.findAll('[data-testid="assistant-file"]').map((chip) => chip.text())).toEqual(['notas.md']);
    await m.wrapper.get('[data-testid="assistant-send"]').trigger('click');
    expect(posted[0].messages[0].content).toEqual([{ type: 'input_file', filename: 'notas.md', mime_type: 'text/markdown', data: 'aG9sYQ==' }]);
  });

  it('a file it cannot take is refused with its reason, and the rest stay', async () => {
    const m = await composer();
    const big = new File(['x'], 'enorme.pdf', { type: 'application/pdf' });
    Object.defineProperty(big, 'size', { value: 9 * 1024 * 1024 });
    await attach(m, new File(['x'], 'foto.heic', { type: 'image/heic' }), big, new File(['a,b'], 'datos.csv', { type: 'text/csv' }));
    expect(m.wrapper.get('[data-testid="assistant-composer-problem"]').text()).toBe(
      'foto.heic no se puede adjuntar: imágenes, PDF, Word, Excel, texto o CSV.',
    );
    expect(m.wrapper.findAll('[data-testid="assistant-file"]').map((chip) => chip.text())).toEqual(['datos.csv']);
  });

  it('no microphone where the browser cannot record', async () => {
    const m = await composer({ voice: {} });
    expect(m.wrapper.find('[data-testid="assistant-mic"]').exists()).toBe(false);
  });

  // gh:hub#629: the microphone in the panel, voice to text through erplora.com.
  it('dictating: the words land in the box after what was written, and nothing is sent', async () => {
    const voice = microphone();
    const m = await composer({ voice });
    await type(m, 'Apunta');
    const mic = m.wrapper.get('[data-testid="assistant-mic"]');
    expect(accessibleName(mic.element)).toBe('Dictar por voz');
    await mic.trigger('click');
    for (let i = 0; i < 3; i += 1) await flush();
    expect(accessibleName(m.wrapper.get('[data-testid="assistant-mic"]').element)).toBe('Detener la grabación');
    await m.wrapper.get('[data-testid="assistant-mic"]').trigger('click');
    for (let i = 0; i < 6; i += 1) await flush();
    expect(m.sent.map((s) => [s.url.replace(/^.*\/api/, '/api'), s.body])).toEqual([
      ['/api/assistant/transcribe', { audio: 'dm96', mime_type: 'audio/webm', language: 'es' }],
    ]);
    expect(assistant.state.draft).toBe('Apunta dos cafés');
    expect(posted).toEqual([]);
  });

  // FIX-HUB-BASE-ASSISTANT-MIC-DOUBLE-TAP-OPENS-TWO-RECORDINGS: a second tap while the browser still asks for the
  // microphone opened a second recording, and the first one stayed on, untranscribed, until its two minutes.
  it('two taps while the browser asks for the microphone open one recording, and the next tap transcribes it', async () => {
    let allow: (stream: MediaStream) => void = () => undefined;
    const voice = {
      ...microphone(),
      getUserMedia: vi.fn(() => new Promise<MediaStream>((resolve) => (allow = resolve))),
    };
    const m = await composer({ voice });
    await m.wrapper.get('[data-testid="assistant-mic"]').trigger('click');
    await m.wrapper.get('[data-testid="assistant-mic"]').trigger('click');
    await flush();
    expect(voice.getUserMedia).toHaveBeenCalledTimes(1);
    allow({ getTracks: () => [{ stop: () => undefined }] } as unknown as MediaStream);
    for (let i = 0; i < 3; i += 1) await flush();
    expect(accessibleName(m.wrapper.get('[data-testid="assistant-mic"]').element)).toBe('Detener la grabación');
    await m.wrapper.get('[data-testid="assistant-mic"]').trigger('click');
    for (let i = 0; i < 6; i += 1) await flush();
    expect(m.sent).toHaveLength(1);
    expect(assistant.state.draft).toBe('dos cafés');
    expect(voice.getUserMedia).toHaveBeenCalledTimes(1);
  });

  it('a microphone refused, or a dictation nobody said anything in, says so in a line', async () => {
    const denied = { ...microphone(), getUserMedia: vi.fn(async () => Promise.reject(new DOMException('no', 'NotAllowedError'))) };
    const m = await composer({ voice: denied });
    await m.wrapper.get('[data-testid="assistant-mic"]').trigger('click');
    for (let i = 0; i < 3; i += 1) await flush();
    expect(m.wrapper.get('[data-testid="assistant-composer-problem"]').text()).toBe(
      'El acceso al micrófono está denegado. Permítelo en tu navegador para dictar.',
    );
    m.wrapper.unmount();
    const silent = await composer({ voice: microphone(), answer: () => Response.json({ text: '  ', language: 'es' }) });
    await silent.wrapper.get('[data-testid="assistant-mic"]').trigger('click');
    for (let i = 0; i < 3; i += 1) await flush();
    await silent.wrapper.get('[data-testid="assistant-mic"]').trigger('click');
    for (let i = 0; i < 6; i += 1) await flush();
    expect(silent.wrapper.get('[data-testid="assistant-composer-problem"]').text()).toBe(
      'No se ha oído nada. Inténtalo de nuevo más cerca del micrófono.',
    );
  });

  // BASE-F94: the installed app (Android, Windows) has no browser bar, so a refused microphone is allowed again in the
  // device's settings; in a browser, in the browser.
  it('a microphone refused inside the installed app points to the device settings, in a browser to the browser', async () => {
    const win = window as unknown as { __TAURI__?: unknown };
    const refusal = async (locale: 'en' | 'es') => {
      const denied = { ...microphone(), getUserMedia: vi.fn(async () => Promise.reject(new DOMException('no', 'NotAllowedError'))) };
      const m = await composer({ voice: denied, locale });
      await m.wrapper.get('[data-testid="assistant-mic"]').trigger('click');
      for (let i = 0; i < 3; i += 1) await flush();
      const said = m.wrapper.get('[data-testid="assistant-composer-problem"]').text();
      m.wrapper.unmount();
      return said;
    };
    win.__TAURI__ = { core: { invoke: vi.fn(async () => null) } };
    try {
      expect(await refusal('es')).toBe('El acceso al micrófono está denegado. Permítelo en los ajustes del dispositivo para dictar.');
      expect(await refusal('en')).toBe('Microphone access is blocked. Allow it in your device settings to dictate.');
    } finally {
      delete win.__TAURI__;
    }
    expect(await refusal('es')).toBe('El acceso al micrófono está denegado. Permítelo en tu navegador para dictar.');
    expect(await refusal('en')).toBe('Microphone access is blocked. Allow it in your browser to dictate.');
  });
});
