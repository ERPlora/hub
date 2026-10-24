// What the assistant's composer takes (BASE-G111, G112): Enter sends on a keyboard and is a new line on a touch screen;
// the files erplora.com reads (images, PDF, Word, Excel, text, CSV, Markdown, JSON), at most 8 MB each and 20 MB per
// question, read in the browser as base64; and the dictation — recorded with the microphone, at most two minutes, in a
// type erplora.com transcribes.
import { describe, expect, it, vi } from 'vitest';

import {
  ACCEPT,
  base64Of,
  canDictate,
  enterSends,
  fileProblem,
  MAX_FILE_BYTES,
  MAX_QUESTION_BYTES,
  MAX_RECORDING_MS,
  mimeOf,
  recordVoice,
} from './assistant-input';

const MB = 1024 * 1024;
const file = (name: string, type: string, size = 10) => ({ name, type, size });

describe('enterSends', () => {
  const key = (fields: Partial<KeyboardEvent>) => ({ key: 'Enter', shiftKey: false, isComposing: false, ...fields }) as KeyboardEvent;

  it('Enter sends; Shift+Enter, a composition or another key do not', () => {
    expect(enterSends(key({}), false)).toBe(true);
    expect(enterSends(key({ shiftKey: true }), false)).toBe(false);
    expect(enterSends(key({ isComposing: true }), false)).toBe(false);
    expect(enterSends(key({ key: 'a' }), false)).toBe(false);
  });

  it('on a touch screen Enter is a new line: the send button sends', () => {
    expect(enterSends(key({}), true)).toBe(false);
  });
});

describe('files', () => {
  it('the types erplora.com reads, by type or by extension when the browser gives none', () => {
    expect(mimeOf(file('a.png', 'image/png'))).toBe('image/png');
    expect(mimeOf(file('notes.md', ''))).toBe('text/markdown');
    expect(mimeOf(file('data.csv', ''))).toBe('text/csv');
    expect(mimeOf(file('x.json', ''))).toBe('application/json');
    expect(mimeOf(file('carta.docx', ''))).toBe('application/vnd.openxmlformats-officedocument.wordprocessingml.document');
    expect(mimeOf(file('libro.xlsx', ''))).toBe('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    expect(ACCEPT).toContain('.docx');
    expect(ACCEPT).toContain('application/pdf');
  });

  it('takes what it reads and says why it refuses the rest', () => {
    expect(fileProblem(file('menu.pdf', 'application/pdf', 2 * MB), 0)).toBeNull();
    expect(fileProblem(file('foto.heic', 'image/heic'), 0)).toEqual({ key: 'base.assistant.files.unsupported', values: { name: 'foto.heic' } });
    expect(fileProblem(file('viejo.doc', 'application/msword'), 0)).toEqual({ key: 'base.assistant.files.unsupported', values: { name: 'viejo.doc' } });
    expect(fileProblem(file('big.pdf', 'application/pdf', MAX_FILE_BYTES + 1), 0)).toEqual({
      key: 'base.assistant.files.tooLarge',
      values: { name: 'big.pdf' },
    });
    expect(fileProblem(file('c.pdf', 'application/pdf', 3 * MB), MAX_QUESTION_BYTES - 2 * MB)).toEqual({
      key: 'base.assistant.files.tooMuch',
      values: {},
    });
  });

  it('reads a file as base64, without the data: prefix', async () => {
    expect(await base64Of(new Blob(['hola'], { type: 'text/plain' }))).toBe('aG9sYQ==');
  });
});

class FakeRecorder {
  static isTypeSupported = (type: string) => type === 'audio/webm;codecs=opus';
  static last: FakeRecorder;
  state: 'inactive' | 'recording' = 'inactive';
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(
    public stream: MediaStream,
    public options: { mimeType?: string },
  ) {
    FakeRecorder.last = this;
  }
  get mimeType() {
    return this.options.mimeType ?? '';
  }
  start() {
    this.state = 'recording';
  }
  stop() {
    this.state = 'inactive';
    this.ondataavailable?.({ data: new Blob(['voz'], { type: this.mimeType }) });
    this.onstop?.();
  }
}

function microphone() {
  const track = { stop: vi.fn() };
  const stream = { getTracks: () => [track] } as unknown as MediaStream;
  return { track, getUserMedia: vi.fn(async () => stream) };
}

describe('dictation', () => {
  it('only where the browser can record', () => {
    expect(canDictate({ getUserMedia: async () => ({}) as MediaStream, MediaRecorder: FakeRecorder as never })).toBe(true);
    expect(canDictate({ getUserMedia: undefined, MediaRecorder: FakeRecorder as never })).toBe(false);
    expect(canDictate({ getUserMedia: async () => ({}) as MediaStream, MediaRecorder: undefined })).toBe(false);
  });

  it('records in a type erplora.com transcribes and frees the microphone when it stops', async () => {
    const mic = microphone();
    const recording = await recordVoice({ getUserMedia: mic.getUserMedia, MediaRecorder: FakeRecorder as never });
    expect(mic.getUserMedia).toHaveBeenCalledWith({ audio: true });
    expect(FakeRecorder.last.state).toBe('recording');
    const clip = await recording.stop();
    expect(clip.mime).toBe('audio/webm');
    expect(clip.blob.size).toBe(3);
    expect(mic.track.stop).toHaveBeenCalled();
  });

  it('stops by itself after two minutes', async () => {
    vi.useFakeTimers();
    try {
      const mic = microphone();
      const ended = vi.fn();
      await recordVoice({ getUserMedia: mic.getUserMedia, MediaRecorder: FakeRecorder as never }, ended);
      vi.advanceTimersByTime(MAX_RECORDING_MS);
      expect(FakeRecorder.last.state).toBe('inactive');
      expect(ended).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('cancelling throws the recording away and frees the microphone', async () => {
    const mic = microphone();
    const recording = await recordVoice({ getUserMedia: mic.getUserMedia, MediaRecorder: FakeRecorder as never });
    recording.cancel();
    expect(FakeRecorder.last.state).toBe('inactive');
    expect(mic.track.stop).toHaveBeenCalled();
  });
});
