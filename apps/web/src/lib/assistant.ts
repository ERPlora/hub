// Cliente del asistente del Hub. Decisión del humano (3): pipeline COMPLETO; nuestra parte es
// la UI de chat + el consumo del stream SSE contra la ruta del Hub. El Hub NUNCA habla con LLMs
// directamente: la ruta del runtime proxya al Cloud, que mide coste. ARQUITECTURA.md §9.
//
// Contrato backend:
//   POST /api/assistant/chat/stream  {messages:[{role,content}]}
//   -> SSE: líneas `data: {"type":"token","text":"…"}` … `data: {"type":"done"}`
import { RUNTIME_URL } from './runtime';
import { config } from './config';
import { getAccessToken } from './cloud';

export type ChatRole = 'user' | 'assistant' | 'system';

/** Content parts (used when a turn carries attachments). Mirrors the shape the
 *  Cloud orchestrator understands: `text`, `image_url` (vision), `input_file`
 *  (base64 document the Cloud extracts text from). ADR-0156. */
export interface ChatTextPart {
  type: 'text';
  text: string;
}
export interface ChatImagePart {
  type: 'image_url';
  image_url: { url: string };
}
export interface ChatFilePart {
  type: 'input_file';
  data: string;
  mime_type: string;
  filename: string;
}
export type ChatContentPart = ChatTextPart | ChatImagePart | ChatFilePart;

/** A message's content: plain text, or a list of parts when it has attachments. */
export type ChatContent = string | ChatContentPart[];

export interface ChatMessage {
  role: ChatRole;
  content: ChatContent;
}

/** Keep well under the Cloud's per-attachment cap (base64 grows ~1.33×). */
export const MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024;

/**
 * Turn a picked File into a chat content part: images become a vision
 * `image_url` data URI; everything else an `input_file` (base64) whose text the
 * Cloud extracts (ADR-0156). Throws if the file is too large.
 */
export async function fileToContentPart(file: File): Promise<ChatContentPart> {
  if (file.size > MAX_ATTACHMENT_BYTES) {
    throw new Error('attachment too large');
  }
  const dataUri = await readAsDataURL(file);
  if (file.type.startsWith('image/')) {
    return { type: 'image_url', image_url: { url: dataUri } };
  }
  return {
    type: 'input_file',
    data: dataUri, // the Cloud accepts a `data:` prefix or raw base64
    mime_type: file.type || 'application/octet-stream',
    filename: file.name,
  };
}

function readAsDataURL(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error ?? new Error('read failed'));
    r.readAsDataURL(file);
  });
}

/** Plain-text view of a message's content (display + route extraction). */
export function messageText(content: ChatContent): string {
  if (typeof content === 'string') return content;
  return content
    .filter((p): p is ChatTextPart => p.type === 'text')
    .map((p) => p.text)
    .join(' ');
}

/** Attachment descriptors of a message, for rendering chips. */
export function messageAttachments(content: ChatContent): { kind: 'image' | 'file'; name: string }[] {
  if (typeof content === 'string') return [];
  const out: { kind: 'image' | 'file'; name: string }[] = [];
  for (const p of content) {
    if (p.type === 'image_url') out.push({ kind: 'image', name: 'image' });
    else if (p.type === 'input_file') out.push({ kind: 'file', name: p.filename });
  }
  return out;
}

/** Eventos que emite el stream del asistente (SSE `data:` JSON). */
export type AssistantEvent =
  | { type: 'token'; text: string }
  | { type: 'done' }
  | { type: 'error'; message?: string }
  | { type: string; [k: string]: unknown };

export interface StreamCallbacks {
  /** Un token de texto del modelo (se va concatenando en la burbuja viva). */
  onToken: (text: string) => void;
  /** Fin del stream (type:done o cierre del cuerpo). */
  onDone?: () => void;
  /** Error de transporte o evento de error del backend. */
  onError?: (err: unknown) => void;
}

/**
 * Abre el stream del asistente y va invocando `onToken` por cada token. Devuelve un `abort()`
 * para cancelar (el usuario navega o manda otro mensaje). Parsea SSE a mano sobre el
 * ReadableStream del fetch (no EventSource: necesitamos POST + cabeceras de auth).
 */
export function streamAssistant(messages: ChatMessage[], cb: StreamCallbacks): () => void {
  const ctrl = new AbortController();

  void (async () => {
    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      };
      if (config.hubId) headers['X-Hub-Id'] = config.hubId;
      const token = getAccessToken();
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const res = await fetch(`${RUNTIME_URL}/api/assistant/chat/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ messages }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) {
        cb.onError?.(new Error(`assistant stream → ${res.status}`));
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      // SSE: eventos separados por línea en blanco; cada evento trae 1+ líneas `data: …`.
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        let sep: number;
        while ((sep = buf.indexOf('\n\n')) !== -1) {
          const rawEvent = buf.slice(0, sep);
          buf = buf.slice(sep + 2);
          const data = rawEvent
            .split('\n')
            .filter((l) => l.startsWith('data:'))
            .map((l) => l.slice(5).trim())
            .join('\n');
          if (!data) continue;

          let evt: AssistantEvent;
          try {
            evt = JSON.parse(data) as AssistantEvent;
          } catch {
            continue; // línea no-JSON (keepalive/comentario)
          }
          if (evt.type === 'token' && typeof (evt as { text?: unknown }).text === 'string') {
            cb.onToken((evt as { text: string }).text);
          } else if (evt.type === 'done') {
            cb.onDone?.();
            return;
          } else if (evt.type === 'error') {
            cb.onError?.(new Error((evt as { message?: string }).message ?? 'assistant error'));
            return;
          }
        }
      }
      cb.onDone?.();
    } catch (err) {
      if ((err as { name?: string }).name === 'AbortError') return;
      cb.onError?.(err);
    }
  })();

  return () => ctrl.abort();
}
