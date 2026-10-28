// The assistant's dictation (BASE-F94), base's one for every screen that dictates to the assistant (the composer's
// «Dictate by voice», the till's «Speak»): a tap records — one recording per tap, also while the browser still asks
// for the microphone —, the next one stops; erplora.com transcribes up to 2 MB; the words land in the assistant's box
// after what was written and its panel opens; nothing is sent. What stops a dictation is said by its reason.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import { flush, memoryStorage, mountBase } from '../__tests__/mount-base';
import { type Assistant, createAssistant, installAssistant } from './assistant';
import { MAX_RECORDING_MS, type VoiceEnv } from './assistant-input';
import type { TurnBody } from './assistant-stream';
import { type Dictation, type DictationProblem, MAX_AUDIO_BYTES, useDictation } from './dictation';

let assistant: Assistant;
let posted: TurnBody[];
/** The hosts still mounted at the end of the test. */
const mounted: { unmount(): void }[] = [];

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
  FakeRecorder.clip = new Blob(['voz'], { type: 'audio/webm' });
});

afterEach(() => {
  // No recording outlives its test (nor its two-minute timer): unmounting throws each one away.
  for (const host of mounted.splice(0)) host.unmount();
  vi.useRealTimers();
  vi.restoreAllMocks();
  installAssistant(undefined);
  document.body.innerHTML = '';
});

class FakeRecorder {
  static isTypeSupported = () => true;
  static last: FakeRecorder;
  /** What the next recording holds. */
  static clip: Blob;
  state = 'inactive';
  mimeType = 'audio/webm;codecs=opus';
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor() {
    FakeRecorder.last = this;
  }
  start() {
    this.state = 'recording';
  }
  stop() {
    this.state = 'inactive';
    this.ondataavailable?.({ data: FakeRecorder.clip });
    this.onstop?.();
  }
}

function microphone() {
  const track = { stop: vi.fn() };
  const stream = { getTracks: () => [track] } as unknown as MediaStream;
  return { track, stream, getUserMedia: vi.fn(async () => stream), MediaRecorder: FakeRecorder as never };
}

/** A microphone the browser is still asking for: `allow()` answers. */
function askingMicrophone() {
  const mic = microphone();
  let answer: (stream: MediaStream) => void = () => undefined;
  const getUserMedia = vi.fn(() => new Promise<MediaStream>((resolve) => (answer = resolve)));
  return { ...mic, getUserMedia, allow: () => answer(mic.stream) };
}

type Sent = { url: string; body: Record<string, unknown> };

let dictation: Dictation;
let problems: DictationProblem[];

const Host = defineComponent({
  props: { voice: { type: Object, required: true } },
  setup(props) {
    dictation = useDictation({ voice: () => props.voice as VoiceEnv, onProblem: (problem) => problems.push(problem) });
    return () => h('div');
  },
});

async function host(voice: VoiceEnv, answer: (sent: Sent) => Response | Promise<Response> = () => Response.json({ text: 'dos cafés', language: 'es' })) {
  problems = [];
  const sent: Sent[] = [];
  const m = await mountBase(Host, {
    locale: 'es',
    props: { voice },
    onApi: ({ url, init }) => {
      const call = { url: url.replace(/^.*\/api/, '/api'), body: JSON.parse(String(init.body ?? '{}')) as Record<string, unknown> };
      sent.push(call);
      return answer(call);
    },
  });
  const unmount = () => {
    const index = mounted.indexOf(handle);
    if (index >= 0) mounted.splice(index, 1);
    m.wrapper.unmount();
  };
  const handle = { unmount };
  mounted.push(handle);
  return { ...m, sent, unmount };
}

async function settle(): Promise<void> {
  for (let i = 0; i < 6; i += 1) await flush();
}

/** Records and stops one dictation. */
async function dictate(): Promise<void> {
  await dictation.toggle();
  await dictation.toggle();
  await settle();
}

describe('useDictation', () => {
  it('only where the browser can record', async () => {
    await host(microphone());
    expect(dictation.available.value).toBe(true);
    await host({});
    expect(dictation.available.value).toBe(false);
  });

  it('a tap records and the next stops: the words land in the box after what was written, the panel opens, nothing is sent', async () => {
    const m = await host(microphone());
    assistant.state.draft = 'Apunta ';
    await dictation.toggle();
    expect(dictation.recording.value).toBe(true);
    expect(assistant.state.open).toBe(false);
    const stopping = dictation.toggle();
    expect(dictation.transcribing.value).toBe(true);
    await stopping;
    await settle();
    expect(m.sent).toEqual([{ url: '/api/assistant/transcribe', body: { audio: 'dm96', mime_type: 'audio/webm', language: 'es' } }]);
    expect(assistant.state.draft).toBe('Apunta dos cafés');
    expect(assistant.state.open).toBe(true);
    expect([dictation.recording.value, dictation.transcribing.value]).toEqual([false, false]);
    expect(posted).toEqual([]);
    expect(problems).toEqual([]);
  });

  it('into an empty box the words land alone', async () => {
    await host(microphone());
    await dictate();
    expect(assistant.state.draft).toBe('dos cafés');
  });

  // FIX-HUB-BASE-ASSISTANT-MIC-DOUBLE-TAP-OPENS-TWO-RECORDINGS: one recording per tap.
  it('while the browser asks for the microphone, another tap opens no second recording', async () => {
    const mic = askingMicrophone();
    await host(mic);
    const first = dictation.toggle();
    expect(dictation.starting.value).toBe(true);
    const second = dictation.toggle();
    expect(mic.getUserMedia).toHaveBeenCalledTimes(1);
    mic.allow();
    await Promise.all([first, second]);
    expect([dictation.starting.value, dictation.recording.value]).toEqual([false, true]);
  });

  it('a recording over 2 MB is refused as too long, untranscribed, and the box and the panel stay as they were', async () => {
    const m = await host(microphone());
    assistant.state.draft = 'Apunta';
    FakeRecorder.clip = new Blob([new Uint8Array(MAX_AUDIO_BYTES + 1)], { type: 'audio/webm' });
    await dictate();
    expect(problems).toEqual(['tooLong']);
    expect(m.sent).toEqual([]);
    expect([assistant.state.draft, assistant.state.open]).toEqual(['Apunta', false]);
    expect(dictation.transcribing.value).toBe(false);
  });

  it('a recording of exactly 2 MB is transcribed', async () => {
    const m = await host(microphone());
    FakeRecorder.clip = new Blob([new Uint8Array(MAX_AUDIO_BYTES)], { type: 'audio/webm' });
    await dictate();
    expect(problems).toEqual([]);
    expect(m.sent).toHaveLength(1);
  });

  it('a dictation nobody said anything in is said as empty, and the box and the panel stay as they were', async () => {
    await host(microphone(), () => Response.json({ text: '  ', language: 'es' }));
    assistant.state.draft = 'Apunta';
    await dictate();
    expect(problems).toEqual(['empty']);
    expect([assistant.state.draft, assistant.state.open]).toEqual(['Apunta', false]);
  });

  it('a transcription that fails is said as failed, and the box and the panel stay as they were', async () => {
    const logged = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    await host(microphone(), () => Response.json({ code: 'unavailable', message: 'down' }, { status: 503 }));
    assistant.state.draft = 'Apunta';
    await dictate();
    expect(problems).toEqual(['failed']);
    expect([assistant.state.draft, assistant.state.open]).toEqual(['Apunta', false]);
    expect(dictation.transcribing.value).toBe(false);
    expect(logged).toHaveBeenCalled();
  });

  it('a refused microphone is denied, inside the installed app deniedInApp, and one that does not start failed', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const said: DictationProblem[] = [];
    const refusing = (error: Error) => ({ ...microphone(), getUserMedia: vi.fn(async () => Promise.reject(error)) });
    for (const [error, inApp] of [
      [new DOMException('no', 'NotAllowedError'), false],
      [new DOMException('no', 'SecurityError'), false],
      [new DOMException('no', 'NotAllowedError'), true],
      [new DOMException('busy', 'NotReadableError'), false],
    ] as const) {
      const win = window as unknown as { __TAURI__?: unknown };
      if (inApp) win.__TAURI__ = { core: { invoke: vi.fn(async () => null) } };
      try {
        await host(refusing(error));
        await dictation.toggle();
        said.push(...problems);
        expect([dictation.starting.value, dictation.recording.value]).toEqual([false, false]);
      } finally {
        delete win.__TAURI__;
      }
    }
    expect(said).toEqual(['denied', 'denied', 'deniedInApp', 'failed']);
  });

  it('at two minutes it stops by itself and what was said is transcribed', async () => {
    const m = await host(microphone());
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    await dictation.toggle();
    expect(dictation.recording.value).toBe(true);
    await vi.advanceTimersByTimeAsync(MAX_RECORDING_MS);
    vi.useRealTimers();
    await settle();
    expect(m.sent).toHaveLength(1);
    expect([dictation.recording.value, assistant.state.draft, assistant.state.open]).toEqual([false, 'dos cafés', true]);
  });

  it('cancel throws the recording away and frees the microphone, untranscribed', async () => {
    const mic = microphone();
    const m = await host(mic);
    await dictation.toggle();
    dictation.cancel();
    await settle();
    expect([dictation.recording.value, FakeRecorder.last.state]).toEqual([false, 'inactive']);
    expect(mic.track.stop).toHaveBeenCalled();
    expect(m.sent).toEqual([]);
  });

  it('leaving the screen throws the recording away, untranscribed', async () => {
    const mic = microphone();
    const m = await host(mic);
    await dictation.toggle();
    m.unmount();
    await settle();
    expect(FakeRecorder.last.state).toBe('inactive');
    expect(mic.track.stop).toHaveBeenCalled();
    expect(m.sent).toEqual([]);
  });

  // The composer leaves with the panel: closing it while «Transcribing…» keeps what was said in the box, as before, and
  // does not open the panel the person has just closed.
  it('leaving the screen while it transcribes: the words still land in the box, and the panel stays as it is', async () => {
    let reply: (response: Response) => void = () => undefined;
    const m = await host(microphone(), () => new Promise<Response>((resolve) => (reply = resolve)));
    await dictation.toggle();
    const stopping = dictation.toggle();
    await settle();
    expect(m.sent).toHaveLength(1);
    m.unmount();
    reply(Response.json({ text: 'dos cafés', language: 'es' }));
    await stopping;
    await settle();
    expect([assistant.state.draft, assistant.state.open]).toEqual(['dos cafés', false]);
  });

  it('leaving the screen while the browser asks for the microphone frees it as soon as it arrives', async () => {
    const mic = askingMicrophone();
    const m = await host(mic);
    const first = dictation.toggle();
    m.unmount();
    mic.allow();
    await first;
    await settle();
    expect(FakeRecorder.last.state).toBe('inactive');
    expect(mic.track.stop).toHaveBeenCalled();
    expect([dictation.recording.value, m.sent]).toEqual([false, []]);
  });
});
