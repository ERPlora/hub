// What the assistant's composer takes (BASE-G111, G112):
// - `enterSends`: Enter sends on a keyboard (Shift+Enter is a new line, an IME composition is left alone); on a touch
//   screen Enter is a new line and the send button sends, as the messaging apps do;
// - `fileProblem`: the files erplora.com reads (assistant/attachments.py of the SaaS: images, PDF, Word, Excel, text,
//   CSV, Markdown, JSON), at most 8 MB each (its door takes about 9) and 20 MB per question, refused with the key of
//   the reason; `base64Of` reads one in the browser, nothing is uploaded until the question goes;
// - `recordVoice`: the dictation with the microphone (`getUserMedia` + `MediaRecorder`), in a type erplora.com
//   transcribes, at most two minutes (its door takes 2 MB), the microphone freed as soon as it stops.

export const MAX_FILE_BYTES = 8 * 1024 * 1024;
export const MAX_QUESTION_BYTES = 20 * 1024 * 1024;
export const MAX_RECORDING_MS = 120_000;

const WORD = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const SHEET = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const IMAGES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif'];
const BY_EXTENSION: Record<string, string> = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  webp: 'image/webp',
  gif: 'image/gif',
  pdf: 'application/pdf',
  docx: WORD,
  xlsx: SHEET,
  txt: 'text/plain',
  csv: 'text/csv',
  md: 'text/markdown',
  json: 'application/json',
};
const READ = new Set([...IMAGES, 'application/pdf', WORD, SHEET, 'text/plain', 'text/csv', 'text/markdown', 'application/json']);

/** The file picker's `accept`: what erplora.com reads. */
export const ACCEPT = [...IMAGES, 'application/pdf', '.docx', '.xlsx', '.txt', '.csv', '.md', '.json'].join(',');

export function enterSends(event: KeyboardEvent, coarse: boolean): boolean {
  return event.key === 'Enter' && !event.shiftKey && !event.isComposing && !coarse;
}

function extension(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot < 0 ? '' : name.slice(dot + 1).toLowerCase();
}

/** The file's type, by its extension when the browser gives none (a `.md` or a `.csv` often come without). */
export function mimeOf(file: { name: string; type: string }): string {
  const type = file.type.split(';')[0].trim().toLowerCase();
  return type && READ.has(type) ? type : (BY_EXTENSION[extension(file.name)] ?? type);
}

export interface Problem {
  key: string;
  values: Record<string, unknown>;
}

/** Why `file` cannot go with the question that already carries `total` bytes, or `null`. */
export function fileProblem(file: { name: string; type: string; size: number }, total: number): Problem | null {
  if (!READ.has(mimeOf(file))) return { key: 'base.assistant.files.unsupported', values: { name: file.name } };
  if (file.size > MAX_FILE_BYTES) return { key: 'base.assistant.files.tooLarge', values: { name: file.name } };
  if (total + file.size > MAX_QUESTION_BYTES) return { key: 'base.assistant.files.tooMuch', values: {} };
  return null;
}

/** The bytes of `blob` in base64, without a `data:` prefix. */
export async function base64Of(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

/** How many bytes a base64 text stands for. */
export function bytesOf(data: string): number {
  return Math.floor((data.length * 3) / 4);
}

export interface VoiceEnv {
  getUserMedia?: (constraints: MediaStreamConstraints) => Promise<MediaStream>;
  MediaRecorder?: typeof MediaRecorder;
}

/** The browser's microphone and recorder, when it has them. */
export function browserVoice(): VoiceEnv {
  const devices = globalThis.navigator?.mediaDevices;
  return {
    getUserMedia: typeof devices?.getUserMedia === 'function' ? (constraints) => devices.getUserMedia(constraints) : undefined,
    MediaRecorder: typeof globalThis.MediaRecorder === 'function' ? globalThis.MediaRecorder : undefined,
  };
}

export function canDictate(env: VoiceEnv): boolean {
  return typeof env.getUserMedia === 'function' && typeof env.MediaRecorder === 'function';
}

/** The types erplora.com transcribes, in the order a browser is asked for them (Chrome, Firefox, Safari). */
const RECORDING_TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];

export interface Recording {
  /** Ends it: the clip and its type, without codecs (`audio/webm`). */
  stop(): Promise<{ blob: Blob; mime: string }>;
  /** Throws it away. */
  cancel(): void;
}

/** Starts recording; `ended` is called if it stops by itself (two minutes). Throws if the microphone is refused. */
export async function recordVoice(env: VoiceEnv, ended?: () => void): Promise<Recording> {
  if (!env.getUserMedia || !env.MediaRecorder) throw new Error('assistant: dictation is not available');
  const Recorder = env.MediaRecorder;
  const stream = await env.getUserMedia({ audio: true });
  const mimeType = RECORDING_TYPES.find((type) => Recorder.isTypeSupported?.(type));
  const recorder = new Recorder(stream, mimeType ? { mimeType } : {});
  const chunks: Blob[] = [];
  const release = () => stream.getTracks().forEach((track) => track.stop());
  let finished: ((clip: { blob: Blob; mime: string }) => void) | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  recorder.ondataavailable = (event: BlobEvent | { data: Blob }) => {
    if (event.data.size > 0) chunks.push(event.data);
  };
  recorder.onstop = () => {
    if (timer) clearTimeout(timer);
    release();
    const mime = (recorder.mimeType || mimeType || 'audio/webm').split(';')[0].trim();
    finished?.({ blob: new Blob(chunks, { type: mime }), mime });
  };
  recorder.start();
  const result = new Promise<{ blob: Blob; mime: string }>((resolve) => {
    finished = resolve;
  });
  timer = setTimeout(() => {
    if (recorder.state !== 'inactive') {
      recorder.stop();
      ended?.();
    }
  }, MAX_RECORDING_MS);
  return {
    stop() {
      if (recorder.state !== 'inactive') recorder.stop();
      return result;
    },
    cancel() {
      finished = null;
      if (recorder.state !== 'inactive') recorder.stop();
      else release();
    },
  };
}
