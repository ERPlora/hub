// Cliente del asistente del Hub. Decisión del humano (3): pipeline COMPLETO; nuestra parte es
// la UI de chat + el consumo del stream SSE contra la ruta del Hub. El Hub NUNCA habla con LLMs
// directamente: la ruta del runtime proxya al Cloud, que mide coste. ARQUITECTURA.md §9.
//
// Contrato backend:
//   POST /api/assistant/chat/stream  {messages:[{role,content}]}
//   -> SSE: líneas `data: {"type":"token","text":"…"}` … `data: {"type":"done"}`
import { RUNTIME_URL, getClient, runtimeHeaders } from './runtime';

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
  /**
   * Pide confirmación antes de ejecutar una ESCRITURA (una tool `command`, que muta datos):
   * el drawer muestra una tarjeta con la acción y sus argumentos. Devuelve `true` para
   * ejecutar, `false` para cancelar. Si no se provee, las escrituras se **cancelan** (seguro
   * por defecto: nunca se muta sin confirmación). Las LECTURAS (`query`) no la usan.
   */
  onConfirm?: (call: { name: string; arguments: string; kind: string }) => Promise<boolean>;
}

/** A tool call the model asked for (forwarded by the runtime from the Cloud). */
interface FunctionCall {
  name: string;
  call_id: string;
  arguments: string; // JSON string of the arguments
  kind?: string; // 'query' (read, auto) | 'command' (write, needs confirm), tagged by the runtime
}

/** OpenAI-style tool_call, as the Cloud expects it back on the assistant message. */
interface ToolCallWire {
  id: string;
  type: 'function';
  function: { name: string; arguments: string };
}

/** Wire message — a ChatMessage plus the tool-round shapes the Cloud understands:
 *  an assistant message carrying `tool_calls`, and a `tool` result message. */
interface WireMessage {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: ChatContent;
  tool_calls?: ToolCallWire[];
  tool_call_id?: string;
}

/** Safety cap on tool round-trips per turn (mirrors the Cloud's own cap). Never
 *  limits a plain answer — only bounds a runaway call/answer loop. */
const MAX_TOOL_ITERS = 6;

/**
 * Abre el turno del asistente y va invocando `onToken` por cada token. Si el modelo pide
 * **ejecutar una función de módulo** (§9.2), el runtime nos reenvía un evento
 * `function_call`: ejecutamos la operación con la **sesión del usuario**
 * (`getClient().query` → mismo gate de permisos que la UI), añadimos el resultado al array
 * y **continuamos el turno** hasta que el modelo responde en texto. Devuelve un `abort()`
 * para cancelar. SSE parseado a mano sobre el ReadableStream (POST + cabeceras de auth).
 *
 * Paso 1 — solo LECTURA: toda función se ejecuta como **query** (lectura, sin efectos). Una
 * función de escritura (command) falla aquí como "query desconocida" y degrada a una nota
 * para el modelo; las mutaciones con tarjeta de confirmación llegan en el paso 2.
 */
export function streamAssistant(messages: ChatMessage[], cb: StreamCallbacks): () => void {
  const ctrl = new AbortController();

  void (async () => {
    try {
      let convo: WireMessage[] = messages.map((m) => ({ role: m.role, content: m.content }));

      for (let iter = 0; ; iter++) {
        const round = await streamRound(convo, cb, ctrl.signal);
        if (round.errored) return; // streamRound ya llamó a onError
        if (round.functionCalls.length === 0) {
          cb.onDone?.();
          return;
        }
        if (iter >= MAX_TOOL_ITERS) {
          cb.onError?.(new Error('assistant: too many tool calls'));
          return;
        }
        // Reconstruye el mensaje assistant que llevaba los tool_calls, ejecuta cada tool
        // con la sesión del usuario y añade su resultado — el Cloud continúa el turno.
        // (El Cloud emite una tool call por ronda — parallel_tool_calls=False — así que no
        // hay confirmaciones concurrentes.)
        const results = await Promise.all(round.functionCalls.map((fc) => runToolCall(fc, cb)));
        convo = [
          ...convo,
          {
            role: 'assistant',
            content: round.text,
            tool_calls: round.functionCalls.map((fc) => ({
              id: fc.call_id,
              type: 'function',
              function: { name: fc.name, arguments: fc.arguments },
            })),
          },
          ...results,
        ];
      }
    } catch (err) {
      if ((err as { name?: string }).name === 'AbortError') return;
      cb.onError?.(err);
    }
  })();

  return () => ctrl.abort();
}

/** Un pase del stream: emite tokens a `onToken`, y devuelve las tool calls que pidió el
 *  modelo + el texto que produjo antes de ellas. `errored` = ya se llamó a onError
 *  (error de transporte/backend) y el llamador debe parar. */
async function streamRound(
  convo: WireMessage[],
  cb: StreamCallbacks,
  signal: AbortSignal,
): Promise<{ functionCalls: FunctionCall[]; text: string; errored: boolean }> {
  const functionCalls: FunctionCall[] = [];
  let text = '';

  // `runtimeHeaders()`, el MISMO helper que el resto de `/api/*`, y NO cabeceras a mano: este
  // endpoint lo sirve el RUNTIME del hub, que exige la sesión local (`X-Hub-Session`, la autoridad
  // de permisos local, ARQUITECTURA.md §2.9). Aquí se montaba a mano y se mandaba
  // `Authorization: Bearer <JWT del cloud>` — otra credencial y para otro interlocutor: el JWT
  // cloud es el adaptador de LOGIN, no la sesión. Cada mensaje respondía
  // `401 {"error":"falta sesión (cabecera X-Hub-Session)"}` y el chat decía «No se pudo contactar
  // con el asistente». El helper sigue mandando el JWT como fallback hub-scoped, así que no se
  // pierde nada.
  const headers: Record<string, string> = {
    ...runtimeHeaders(),
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  };

  const res = await fetch(`${RUNTIME_URL}/api/assistant/chat/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ messages: convo }),
    signal,
  });
  if (!res.ok || !res.body) {
    cb.onError?.(new Error(`assistant stream → ${res.status}`));
    return { functionCalls, text, errored: true };
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
        const t = (evt as { text: string }).text;
        text += t;
        cb.onToken(t);
      } else if (evt.type === 'function_call') {
        const fc = evt as { name?: string; call_id?: string; arguments?: string; kind?: string };
        functionCalls.push({
          name: fc.name ?? '',
          call_id: fc.call_id ?? '',
          arguments: typeof fc.arguments === 'string' ? fc.arguments : '{}',
          kind: typeof fc.kind === 'string' ? fc.kind : undefined,
        });
      } else if (evt.type === 'done') {
        return { functionCalls, text, errored: false };
      } else if (evt.type === 'error') {
        cb.onError?.(new Error((evt as { message?: string }).message ?? 'assistant error'));
        return { functionCalls, text, errored: true };
      }
    }
  }
  // El cuerpo terminó sin un `done` explícito: fin de este pase.
  return { functionCalls, text, errored: false };
}

/** Ejecuta una tool call con la sesión del usuario y la envuelve como mensaje `tool`.
 *
 *  - LECTURA (`query`, o kind ausente): se corre directo (sin efectos), con el mismo gate
 *    de permisos que la UI (`getClient().query`).
 *  - ESCRITURA (`command`): pide confirmación con `onConfirm`; solo tras el `true` se
 *    ejecuta (`getClient().command`). Sin handler o si se cancela → NO se muta y se devuelve
 *    una nota `cancelled` para que el modelo se lo diga al usuario (seguro por defecto).
 *
 *  Cualquier fallo degrada a una nota de error (nunca lanza): el turno sigue. */
async function runToolCall(fc: FunctionCall, cb: StreamCallbacks): Promise<WireMessage> {
  const params = safeParseArgs(fc.arguments);

  if (fc.kind === 'command') {
    const approved = cb.onConfirm
      ? await cb.onConfirm({ name: fc.name, arguments: fc.arguments, kind: 'command' })
      : false;
    if (!approved) {
      return toolMessage(fc.call_id, { status: 'cancelled', message: 'Action was not confirmed.' });
    }
    try {
      // Host tool mutante (hub#631): instalar va por el MISMO endpoint que el botón de Apps
      // (`request-install`), que revalida admin server-side. Pasa por el confirm de arriba
      // como cualquier command — el modelo nunca instala sin el clic del usuario.
      if (fc.name === 'hub.modules.install') {
        return toolMessage(fc.call_id, await hostInstall(params));
      }
      // Host tool mutante (hub#631, pasos 2-3): aplicar un blueprint va por el MISMO pipeline que
      // la hero card del dashboard. Semántica verificada ANTES de exponerla: el import es ADITIVO
      // (import_sql.rs solo admite INSERT con guardas NOT EXISTS; ADR-0304 añade las claves
      // naturales del destino — una fila existente se SALTA, nunca se funde ni se pisa).
      if (fc.name === 'hub.blueprints.apply') {
        return toolMessage(fc.call_id, await hostBlueprintApply(params));
      }
      const data = await getClient().command(fc.name, params);
      return toolMessage(fc.call_id, data ?? null);
    } catch (err) {
      return toolMessage(fc.call_id, { error: errMessage(err) });
    }
  }

  try {
    // Host tool de lectura (hub#631): el catálogo del marketplace no es una query de módulo —
    // se sirve por su endpoint real y se recorta a lo que el modelo necesita (id, nombre,
    // descripción, versión, precio, instalado) para no quemar contexto.
    if (fc.name === 'hub.marketplace.search') {
      return toolMessage(fc.call_id, await hostMarketplaceSearch(params));
    }
    // Host tool de lectura (hub#631): el catálogo de blueprints del SaaS, recortado a la ficha.
    if (fc.name === 'hub.blueprints.list') {
      return toolMessage(fc.call_id, await hostBlueprintsList());
    }
    const data = await getClient().query(fc.name, params);
    return toolMessage(fc.call_id, data ?? null);
  } catch (err) {
    return toolMessage(fc.call_id, { error: errMessage(err) });
  }
}

/** `hub.marketplace.search`: catálogo real, filtrado por texto libre y recortado (cap 20). */
async function hostMarketplaceSearch(params: Record<string, unknown>): Promise<unknown> {
  const { cloudMarketplaceModules } = await import('./cloud');
  const all = await cloudMarketplaceModules();
  const q = String(params.search ?? '').trim().toLowerCase();
  const hit = (s: string | undefined) => (s ?? '').toLowerCase().includes(q);
  const filtered = q ? all.filter((m) => hit(m.id) || hit(m.name) || hit(m.description) || hit(m.category)) : all;
  return {
    modules: filtered.slice(0, 20).map((m) => ({
      module_id: m.id,
      name: m.name,
      description: m.description,
      version: m.version ?? null,
      price: m.priceLabel,
      installed: m.installed,
      available: m.available,
    })),
    total: filtered.length,
  };
}

/** `hub.modules.install`: resuelve la versión (la última publicada si no viene) e instala por
 *  `request-install` — el runtime valida admin, descarga, verifica SHA256, migra y activa. */
async function hostInstall(params: Record<string, unknown>): Promise<unknown> {
  const moduleId = String(params.module_id ?? '').trim();
  if (!moduleId) return { error: 'module_id is required' };
  let version = String(params.version ?? '').trim();
  if (!version) {
    const { cloudMarketplaceModules } = await import('./cloud');
    const found = (await cloudMarketplaceModules()).find((m) => m.id === moduleId);
    if (!found?.version) return { error: `module "${moduleId}" not found in the marketplace catalogue` };
    version = found.version;
  }
  const { requestInstall } = await import('./runtime');
  return await requestInstall(moduleId, version);
}

/** `hub.blueprints.list`: catálogo de plantillas del SaaS, recortado a lo que el modelo necesita
 *  (slug, nombre, descripción, idioma, país, versión) — sin plomería de checksums/tamaños. */
async function hostBlueprintsList(): Promise<unknown> {
  const { fetchBlueprintCatalog } = await import('./runtime');
  const catalog = await fetchBlueprintCatalog();
  return {
    blueprints: catalog.map((b) => ({
      slug: b.slug,
      name: b.name,
      description: b.description,
      locale: b.locale,
      country: b.country,
      version: b.latest_version,
    })),
  };
}

/** `hub.blueprints.apply`: el pipeline de la hero card (hub#368), reutilizado tal cual —
 *  descarga (el runtime verifica SHA256), inspecciona (staging + manifest) e importa con la
 *  selección one-click (`heroSelection`: nunca personas ni identidad fiscal, ADR-0195 §4/§5).
 *  El motor es best-effort y ADITIVO (ADR-0304): lo existente se conserva; se devuelve el
 *  `importOutcome` compacto para que el modelo cuente lo que pasó de verdad. */
async function hostBlueprintApply(params: Record<string, unknown>): Promise<unknown> {
  const slug = String(params.slug ?? '').trim();
  if (!slug) return { error: 'slug is required' };
  const { downloadBlueprint, inspectBlueprint, importBlueprint } = await import('./runtime');
  const { heroSelection, importOutcome } = await import('./blueprint-hero');
  const blob = await downloadBlueprint(slug);
  const inspection = await inspectBlueprint(blob);
  const report = await importBlueprint(inspection.upload_id, heroSelection(inspection.manifest));
  return {
    outcome: importOutcome(report),
    installed_modules: (report.installed_modules ?? []).map((m) => ({ id: m.id, status: m.status })),
  };
}

// ── Voice input (hub#629): microphone → MediaRecorder → SaaS speech proxy → text ────────────────

/** The SaaS transcribe cap (`saas/apps/speech`, MAX_AUDIO_SIZE = 2 MB). Checked BEFORE the wire:
 *  a clip the proxy would reject with a 400 should never leave the device. */
export const MAX_AUDIO_BYTES = 2 * 1024 * 1024;

/** Containers the SaaS accepts, in preference order; the first the browser supports wins
 *  (Chromium records webm, Safari mp4). */
const RECORDER_MIME_TYPES = ['audio/webm', 'audio/ogg', 'audio/mp4'];

/** A live microphone capture. `stop()` hands back the clip; both paths release the microphone —
 *  a mic light that stays on after the drawer is done with it is a bug, not a detail. */
export interface VoiceRecording {
  /** Stops recording, releases the microphone and resolves the captured audio. */
  stop(): Promise<Blob>;
  /** Abandons the capture: releases the microphone, discards the audio. */
  cancel(): void;
}

/**
 * Opens the microphone and starts recording.
 *
 * Failure surface is the browser's own, on purpose: no `MediaRecorder` → throws `not supported`;
 * a denied permission REJECTS with the browser's `NotAllowedError` untouched, so the caller can
 * tell "the user said no" (its own message) from "something broke" (a generic one).
 */
export async function startVoiceRecording(): Promise<VoiceRecording> {
  const Recorder = (globalThis as { MediaRecorder?: typeof MediaRecorder }).MediaRecorder;
  const media = (globalThis as { navigator?: Navigator }).navigator?.mediaDevices;
  if (!Recorder || !media?.getUserMedia) {
    throw new Error('voice recording is not supported in this browser');
  }
  const stream = await media.getUserMedia({ audio: true });
  const mimeType = RECORDER_MIME_TYPES.find((t) => Recorder.isTypeSupported?.(t));
  const recorder = new Recorder(stream, mimeType ? { mimeType } : undefined);
  const chunks: BlobPart[] = [];
  recorder.addEventListener('dataavailable', (ev) => {
    const data = (ev as BlobEvent).data;
    if (data && data.size > 0) chunks.push(data);
  });
  const release = (): void => stream.getTracks().forEach((t) => t.stop());
  recorder.start();

  return {
    stop: () =>
      new Promise<Blob>((resolve, reject) => {
        recorder.addEventListener(
          'stop',
          () => {
            release();
            resolve(new Blob(chunks, { type: recorder.mimeType || mimeType || 'audio/webm' }));
          },
          { once: true },
        );
        recorder.addEventListener(
          'error',
          (ev) => {
            release();
            reject((ev as { error?: Error }).error ?? new Error('recording failed'));
          },
          { once: true },
        );
        recorder.stop();
      }),
    cancel: () => {
      try {
        if (recorder.state !== 'inactive') recorder.stop();
      } catch {
        /* already inert */
      }
      release();
    },
  };
}

/**
 * Sends a recorded clip to the SaaS speech proxy (Whisper) and returns the transcription. The hub
 * NEVER talks to an LLM/API directly (§9.3): the SaaS is the proxy and meters the cost. Refuses
 * oversize clips before touching the network (the proxy's own cap is 2 MB).
 */
export async function transcribeAudio(audio: Blob, language?: string): Promise<string> {
  if (audio.size > MAX_AUDIO_BYTES) {
    throw new Error('audio clip too large');
  }
  const { cloudTranscribeSpeech } = await import('./cloud');
  return await cloudTranscribeSpeech(audio, language);
}

function safeParseArgs(s: string): Record<string, unknown> {
  try {
    return s ? (JSON.parse(s) as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function toolMessage(callId: string, content: unknown): WireMessage {
  return { role: 'tool', tool_call_id: callId, content: JSON.stringify(content) };
}

function errMessage(err: unknown): string {
  return (err as { message?: string })?.message ?? 'tool failed';
}
