// Cliente del asistente del Hub. Decisión del humano (3): pipeline COMPLETO; nuestra parte es
// la UI de chat + el consumo del stream SSE contra la ruta del Hub. El Hub NUNCA habla con LLMs
// directamente: la ruta del runtime proxya al Cloud, que mide coste. ARQUITECTURA.md §9.
//
// Contrato backend:
//   POST /api/assistant/chat/stream  {messages:[{role,content}]}
//   -> SSE: líneas `data: {"type":"token","text":"…"}` … `data: {"type":"done"}`
import { RUNTIME_URL, getClient, runtimeHeaders } from './runtime';
import { auditTurn, type ExecutedTool, type TurnAudit } from './assistant-grounding';
import { SETUP_STATUS_QUERY } from './setup-status';

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
  /** Stable client-generated id (crypto.randomUUID), used to reference the message when
   *  reporting it (hub#946). Optional: history persisted before ids existed has none. */
  id?: string;
  /** The runtime's grounding verdict on this answer (hub#1038, #1039). Present only when the
   *  turn's receipts did NOT back what it claimed; the drawer renders it as a system notice. */
  grounding?: TurnAudit;
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
  | {
      type: 'error';
      message?: string;
      error?: string;
      code?: string;
      limit?: number;
      used?: number;
      tier?: string;
      kind?: string;
      upgrade_required?: boolean;
      resets_at?: string;
    }
  | {
      type: 'usage';
      tier?: string;
      tier_name?: string;
      messages_used?: number;
      messages_limit?: number;
      resets_at?: string;
    }
  | { type: string; [k: string]: unknown };

/** El código que el SaaS manda cuando el turno murió por cuota (`QUOTA_EXCEEDED_CODE`,
 *  saas#1540). Es un HECHO legible por máquina; `upgrade_required` es solo la recomendación
 *  comercial que lo acompaña, y decidir por ella confunde «no te quedan mensajes» con «te
 *  convendría otro plan». */
export const QUOTA_EXCEEDED_CODE = 'quota_exceeded';

/**
 * Consumo del mes tal y como lo cierra el SaaS (frame `usage`, saas#1540).
 *
 * Tiene que ser un FRAME y no la cabecera `X-Assistant-Usage`: una cabecera se escribe antes del
 * cuerpo, así que en un stream va siempre un mensaje por detrás y el contador de la pantalla
 * quedaría desfasado un turno para siempre.
 */
export interface AssistantUsage {
  tier?: string;
  tierName?: string;
  messagesUsed?: number;
  messagesLimit?: number;
  /** ISO-8601: cuándo vuelven los mensajes. Un consumo sin horizonte no deja decidir nada. */
  resetsAt?: string;
}

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
  onConfirm?: (call: {
    name: string;
    arguments: string;
    kind: string;
    risk?: string;
    moneyFields?: string[];
  }) => Promise<boolean>;
  /**
   * The turn's grounding verdict, emitted once the answer is complete (hub#1038, #1039).
   * The runtime holds the receipts — which tools ran and how they ended — so it, not the
   * model, decides whether the answer is allowed to say a change happened. The drawer turns
   * a flagged verdict into a SYSTEM notice; it is never text the model wrote.
   */
  onAudit?: (audit: TurnAudit) => void;
  /**
   * Los contadores POST-turno que cierran el stream (frame `usage`, saas#1540 · hub#1183). El
   * drawer los usa para avisar ANTES de agotar la cuota: sin esto el hub no conocía su plan
   * hasta que lo gastaba, y el dueño se enteraba del límite en el peor momento posible.
   */
  onUsage?: (usage: AssistantUsage) => void;
  /** The hub's real navigation map, so a named screen can be checked (hub#1047, #1048). */
  knownRoutes?: string[];
}

/**
 * Por qué falló el turno, con lo que el SaaS ya sabía (saas#1540).
 *
 * La cuota agotada NO es una avería, y presentarla como tal convierte el único momento de
 * conversión del tier gratuito en un fallo del producto: el dueño leía «No se pudo contactar con
 * el asistente» y creía que estaba roto. El SaaS manda `{error, limit, used, tier, kind,
 * upgrade_required}`; aquí se perdía entero — y hasta el texto, porque se leía `message` cuando la
 * clave que viaja es `error`.
 */
export interface AssistantFailure {
  message: string;
  /** Presente SOLO si el turno murió por cuota. Un error de transporte no la lleva: pintar un
   *  botón de pagar sobre una caída de red no arregla nada y encima cobra. */
  quota?: {
    limit?: number;
    used?: number;
    tier?: string;
    kind?: string;
    upgradeRequired: boolean;
    /** ISO-8601 de la renovación (saas#1540, hub#1183). «Has gastado 30 de 30» sin fecha es un
     *  callejón: no se puede decidir entre esperar y pagar. */
    resetsAt?: string;
  };
}

/** A tool call the model asked for (forwarded by the runtime from the Cloud). */
interface FunctionCall {
  name: string;
  call_id: string;
  arguments: string; // JSON string of the arguments
  kind?: string; // 'query' | 'command' — which dispatcher door the call goes through
  /** Whether running this tool can change what the hub holds (hub#1594), resolved by the runtime
   *  from the catalogue. `kind` says which door; THIS says whether the user confirms first — an
   *  availability answer is declared as a `command` only because that is the one shape that can
   *  cross another module's data, and asking a question is not a change. Only a literal `true`
   *  skips the card: anything else (absent, a string, a number) is treated as a write. */
  read_only?: unknown;
  /** How dangerous the module says this operation is (hub#1042). */
  risk?: string;
  /** Which arguments are money, resolved by the runtime from the command's schema (hub#1040).
   *  The card formats ONLY these: guessing from a field name would invent an amount. */
  money_fields?: string[];
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

      // The receipts of THIS turn: what actually ran and how it ended. The audit at the end
      // is built from these, never from what the answer says about itself (hub#1038).
      const executed: ExecutedTool[] = [];
      let spokenText = '';
      const lastUser = [...messages].reverse().find((m) => m.role === 'user');
      const userText = typeof lastUser?.content === 'string' ? lastUser.content : undefined;
      const audit = (): void => {
        cb.onAudit?.(
          auditTurn({ text: spokenText, executed, userText, knownRoutes: cb.knownRoutes }),
        );
      };

      for (let iter = 0; ; iter++) {
        const round = await streamRound(convo, cb, ctrl.signal);
        spokenText += round.text;
        if (round.errored) return; // streamRound ya llamó a onError
        if (round.functionCalls.length === 0) {
          audit();
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
        const ran = await Promise.all(round.functionCalls.map((fc) => runToolCall(fc, cb)));
        for (const r of ran) executed.push(r.executed);
        const results = ran.map((r) => r.message);
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
        // Everything the runtime resolved about this tool travels WITH the call — the drawer has
        // no catalogue of its own to look it up in. Dropping any of it here silently disarms the
        // card: `risk` (hub#1042) and `money_fields` (hub#1040) were being parsed away, so the
        // card had been rendering neither the destructive warning nor «15,00 €».
        const fc = evt as {
          name?: string;
          call_id?: string;
          arguments?: string;
          kind?: string;
          read_only?: unknown;
          risk?: string;
          money_fields?: unknown;
        };
        functionCalls.push({
          name: fc.name ?? '',
          call_id: fc.call_id ?? '',
          arguments: typeof fc.arguments === 'string' ? fc.arguments : '{}',
          kind: typeof fc.kind === 'string' ? fc.kind : undefined,
          read_only: fc.read_only,
          risk: typeof fc.risk === 'string' ? fc.risk : undefined,
          money_fields: Array.isArray(fc.money_fields)
            ? fc.money_fields.filter((f): f is string => typeof f === 'string')
            : undefined,
        });
      } else if (evt.type === 'usage') {
        // Contadores POST-turno (saas#1540, hub#1183). Nunca texto: es chrome del plan, no algo
        // que el modelo haya dicho. El runtime los reenvía verbatim (`translate_sse_line`).
        const u = evt as {
          tier?: string;
          tier_name?: string;
          messages_used?: number;
          messages_limit?: number;
          resets_at?: string;
        };
        cb.onUsage?.({
          tier: u.tier,
          tierName: u.tier_name,
          messagesUsed: u.messages_used,
          messagesLimit: u.messages_limit,
          resetsAt: u.resets_at,
        });
      } else if (evt.type === 'done') {
        return { functionCalls, text, errored: false };
      } else if (evt.type === 'error') {
        // La clave del texto es `error`, no `message`: leyendo la equivocada se perdía hasta la
        // frase que el SaaS había escrito. `message` se sigue aceptando por si algún emisor la usa.
        const e = evt as {
          message?: string;
          error?: string;
          code?: string;
          limit?: number;
          used?: number;
          tier?: string;
          kind?: string;
          upgrade_required?: boolean;
          resets_at?: string;
        };
        const failure: AssistantFailure = { message: e.error ?? e.message ?? 'assistant error' };
        // El motivo se LEE del `code` (hub#1183); `upgrade_required` se queda de respaldo para un
        // emisor que aún no lo mande. Inferir el estado de un flag comercial es cómo «no te
        // quedan mensajes» y «te convendría otro plan» acabaron siendo la misma cosa.
        if (e.code === QUOTA_EXCEEDED_CODE || e.upgrade_required) {
          failure.quota = {
            limit: e.limit,
            used: e.used,
            tier: e.tier,
            kind: e.kind,
            upgradeRequired: e.upgrade_required ?? true,
            resetsAt: e.resets_at,
          };
        }
        cb.onError?.(failure);
        return { functionCalls, text, errored: true };
      }
    }
  }
  // El cuerpo terminó sin un `done` explícito: fin de este pase.
  return { functionCalls, text, errored: false };
}

/** Ejecuta una tool call con la sesión del usuario y la envuelve como mensaje `tool`.
 *
 *  Dos decisiones INDEPENDIENTES, y confundirlas es lo que rompió hub#1594:
 *
 *  - **Por qué puerta va** la manda `kind`: `query` → `getClient().query`, `command` →
 *    `getClient().command`. Es el dispatcher del runtime; una operación no puede entrar por la
 *    otra puerta.
 *  - **Si el usuario confirma antes** lo manda `read_only`: una ESCRITURA pide confirmación con
 *    `onConfirm` y solo tras el `true` se ejecuta. Sin handler o si se cancela → NO se muta y se
 *    devuelve una nota `cancelled` para que el modelo se lo diga al usuario (seguro por defecto).
 *    Una LECTURA se corre directa, sea query o command: preguntar «¿qué huecos me quedan?» no es
 *    un cambio, y la tarjeta se guarda para lo que sí lo es.
 *
 *  El gate de PERMISOS no vive aquí: es el `permission` de la operación, que el runtime revalida
 *  server-side en cada llamada. La tarjeta evita la sorpresa, no la escalada.
 *
 *  Cualquier fallo degrada a una nota de error (nunca lanza): el turno sigue. */
async function runToolCall(
  fc: FunctionCall,
  cb: StreamCallbacks,
): Promise<{ message: WireMessage; executed: ExecutedTool }> {
  const params = safeParseArgs(fc.arguments);
  // Only a literal `true` is a read: an absent or malformed flag must never disarm the card.
  const readOnly = fc.read_only === true;
  const writes = fc.kind === 'command' && !readOnly;
  // The receipt says READ or WRITE — not which door was used. The turn audit (hub#1038) reads it
  // to decide whether the answer is allowed to claim a change happened, so a command that only
  // answered must not count as one.
  const kind: ExecutedTool['kind'] = writes ? 'command' : 'query';
  // The receipt the audit reads: a write only counts as done when the dispatcher answered
  // without error AND the user approved the card. Cancelled and failed are both "no effect".
  const receipt = (status: ExecutedTool['status'], result: unknown): ExecutedTool => ({
    name: fc.name,
    kind,
    status,
    result,
  });
  const done = (status: ExecutedTool['status'], payload: unknown) => ({
    message: toolMessage(fc.call_id, payload),
    executed: receipt(status, payload),
  });

  if (fc.kind === 'command') {
    if (writes) {
      const approved = cb.onConfirm
        ? await cb.onConfirm({
            name: fc.name,
            arguments: fc.arguments,
            kind: 'command',
            risk: fc.risk,
            moneyFields: fc.money_fields,
          })
        : false;
      if (!approved) {
        return done('cancelled', { status: 'cancelled', message: 'Action was not confirmed.' });
      }
    }
    try {
      // Host tool mutante (hub#631): instalar va por el MISMO endpoint que el botón de Apps
      // (`request-install`), que revalida admin server-side. Pasa por el confirm de arriba
      // como cualquier command — el modelo nunca instala sin el clic del usuario.
      if (fc.name === 'hub.modules.install') {
        return done('ok', await hostInstall(params));
      }
      // Host tool mutante (hub#631, pasos 2-3): aplicar un blueprint va por el MISMO pipeline que
      // la hero card del dashboard. Semántica verificada ANTES de exponerla: el import es ADITIVO
      // (import_sql.rs solo admite INSERT con guardas NOT EXISTS; ADR-0304 añade las claves
      // naturales del destino — una fila existente se SALTA, nunca se funde ni se pisa).
      if (fc.name === 'hub.blueprints.apply') {
        return done('ok', await hostBlueprintApply(params));
      }
      const data = await getClient().command(fc.name, params);
      return done('ok', data ?? null);
    } catch (err) {
      return done('error', { error: errMessage(err) });
    }
  }

  try {
    // Host tool de lectura (hub#631): el catálogo del marketplace no es una query de módulo —
    // se sirve por su endpoint real y se recorta a lo que el modelo necesita (id, nombre,
    // descripción, versión, precio, instalado) para no quemar contexto.
    if (fc.name === 'hub.marketplace.search') {
      return done('ok', await hostMarketplaceSearch(params));
    }
    // Host tool de lectura (hub#631): el catálogo de blueprints del SaaS, recortado a la ficha.
    if (fc.name === 'hub.blueprints.list') {
      return done('ok', await hostBlueprintsList());
    }
    const data = await getClient().query(fc.name, params);
    return done('ok', data ?? null);
  } catch (err) {
    return done('error', { error: errMessage(err) });
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

  // Lo que la plantilla NO deja hecho, leído del hub (hub#1041).
  //
  // Aplicarla instala módulos y siembra catálogo, pero no toca la identidad fiscal ni la
  // numeración — la descripción de esta misma tool ya lo dice: «it never imports people, fiscal
  // identity or another business's invoice numbering». Aun así el asistente contestó «Serie F1
  // activa · VeriFactu configurado · ya puedes emitir facturas», con 0 series y el runtime
  // bloqueando, porque describió el resultado desde el folleto de la plantilla en vez de leer el
  // hub. No había nada que leer: el resultado solo traía los módulos instalados.
  //
  // Ahora trae también lo que SIGUE bloqueando, así que no queda hueco que rellenar. Solo lo
  // bloqueante y solo lo pendiente: una lista de todo se vuelve ruido y deja de leerse.
  const result: Record<string, unknown> = {
    outcome: importOutcome(report),
    installed_modules: (report.installed_modules ?? []).map((m) => ({ id: m.id, status: m.status })),
  };
  try {
    // La query devuelve UNA fila con el documento entero (`architecture/hub/setup-status.md`),
    // así que se tipa aquí en vez de confiar en el genérico del cliente.
    type SetupRow = {
      items?: { key: string; state: string; level: string; title: string; route: string }[];
    };
    const rows = (await getClient().query(SETUP_STATUS_QUERY, {})) as SetupRow[] | null;
    const items = rows?.[0]?.items ?? [];
    result.still_blocking = items
      .filter((i) => i.state === 'pending' && (i.level === 'legal' || i.level === 'functional'))
      .map((i) => ({ key: i.key, level: i.level, title: i.title, route: i.route }));
  } catch {
    // Callar sería PEOR que fallar: sin el campo, el modelo lee «no hay nada bloqueando» y vuelve
    // a decir que ya se puede facturar. Se dice que no se sabe.
    result.setup_status_unavailable = true;
  }
  return result;
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
