// Voice input for the assistant drawer (hub#629): microphone → MediaRecorder → the SaaS speech
// proxy (Whisper) → text into the chat input. These tests exercise the REAL capture functions with
// the browser APIs stubbed at the API level — and, per the hub#770 lesson, the stubs fail exactly
// as the real APIs fail (a denied microphone rejects `getUserMedia` with a `NotAllowedError`, it
// does not return null).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./runtime', () => ({
  RUNTIME_URL: '',
  getClient: () => ({ query: vi.fn(), command: vi.fn() }),
  runtimeHeaders: () => ({}),
}));
const { transcribeMock } = vi.hoisted(() => ({ transcribeMock: vi.fn() }));
vi.mock('./cloud', () => ({ cloudTranscribeSpeech: transcribeMock }));

import { MAX_AUDIO_BYTES, startVoiceRecording, transcribeAudio } from './assistant';

// ── Browser-API stubs (behaviour mirrors the real MediaRecorder contract) ───────────────────────

class FakeTrack {
  stopped = false;
  stop(): void {
    this.stopped = true;
  }
}

class FakeStream {
  tracks = [new FakeTrack()];
  getTracks(): FakeTrack[] {
    return this.tracks;
  }
}

let lastRecorder: FakeMediaRecorder | null = null;

class FakeMediaRecorder {
  static isTypeSupported(type: string): boolean {
    return type === 'audio/webm';
  }
  state: 'inactive' | 'recording' = 'inactive';
  mimeType: string;
  stream: FakeStream;
  private listeners = new Map<string, Array<{ fn: (ev: unknown) => void; once: boolean }>>();

  constructor(stream: FakeStream, opts?: { mimeType?: string }) {
    this.stream = stream;
    this.mimeType = opts?.mimeType ?? '';
    lastRecorder = this;
  }

  addEventListener(type: string, fn: (ev: unknown) => void, opts?: { once?: boolean }): void {
    const list = this.listeners.get(type) ?? [];
    list.push({ fn, once: opts?.once ?? false });
    this.listeners.set(type, list);
  }

  private emit(type: string, ev: unknown): void {
    const list = this.listeners.get(type) ?? [];
    this.listeners.set(type, list.filter((l) => !l.once));
    for (const l of list) l.fn(ev);
  }

  start(): void {
    this.state = 'recording';
  }

  // The real recorder flushes a final `dataavailable` and then fires `stop`.
  stop(): void {
    this.state = 'inactive';
    this.emit('dataavailable', { data: new Blob(['captured-audio'], { type: this.mimeType || 'audio/webm' }) });
    this.emit('stop', {});
  }
}

function stubMicrophone(getUserMedia: (c: unknown) => Promise<unknown>): void {
  vi.stubGlobal('MediaRecorder', FakeMediaRecorder as unknown as typeof MediaRecorder);
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } });
}

beforeEach(() => {
  lastRecorder = null;
  transcribeMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('startVoiceRecording', () => {
  it('rechaza como NO SOPORTADO cuando el navegador no trae MediaRecorder (sin pedir permiso)', async () => {
    const getUserMedia = vi.fn();
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } });
    // No MediaRecorder global at all — the real absence, not a null return.
    vi.stubGlobal('MediaRecorder', undefined);

    await expect(startVoiceRecording()).rejects.toThrow(/not supported/i);
    expect(getUserMedia).not.toHaveBeenCalled();
  });

  it('propaga la DENEGACIÓN del permiso tal cual la lanza el navegador (NotAllowedError)', async () => {
    // The stub fails as the real one fails (hub#770): getUserMedia REJECTS with a named error.
    const denial = Object.assign(new Error('Permission denied'), { name: 'NotAllowedError' });
    stubMicrophone(async () => {
      throw denial;
    });

    await expect(startVoiceRecording()).rejects.toMatchObject({ name: 'NotAllowedError' });
    expect(lastRecorder).toBeNull();
  });

  it('captura audio y al parar devuelve el Blob grabado Y suelta el micrófono', async () => {
    const stream = new FakeStream();
    stubMicrophone(async () => stream);

    const rec = await startVoiceRecording();
    expect(lastRecorder?.state).toBe('recording');

    const blob = await rec.stop();
    expect(blob.size).toBeGreaterThan(0);
    expect(blob.type).toContain('audio/');
    // The light of the mic goes OFF: every track of the stream is stopped.
    expect(stream.tracks.every((t) => t.stopped)).toBe(true);
  });

  it('cancel() suelta el micrófono sin transcribir nada', async () => {
    const stream = new FakeStream();
    stubMicrophone(async () => stream);

    const rec = await startVoiceRecording();
    rec.cancel();

    expect(stream.tracks.every((t) => t.stopped)).toBe(true);
    expect(transcribeMock).not.toHaveBeenCalled();
  });
});

describe('transcribeAudio', () => {
  it('rechaza un audio mayor que el cap del SaaS (2 MB) SIN tocar la red', async () => {
    const big = new Blob([new Uint8Array(MAX_AUDIO_BYTES + 1)], { type: 'audio/webm' });
    await expect(transcribeAudio(big, 'es')).rejects.toThrow(/too large/i);
    expect(transcribeMock).not.toHaveBeenCalled();
  });

  it('delega en el proxy speech del SaaS (NUNCA a un LLM/API externa) y devuelve el texto', async () => {
    transcribeMock.mockResolvedValue('dos cafés con leche');
    const clip = new Blob(['audio'], { type: 'audio/webm' });

    const text = await transcribeAudio(clip, 'es');

    expect(transcribeMock).toHaveBeenCalledWith(clip, 'es');
    expect(text).toBe('dos cafés con leche');
  });
});
