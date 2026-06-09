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

export interface ChatMessage {
  role: ChatRole;
  content: string;
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
