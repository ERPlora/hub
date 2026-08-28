// La cuota agotada NO es una avería (saas#1540).
//
// Al gastar los 30 mensajes del plan gratuito, el dueño veía exactamente esto y nada más:
// «No se pudo contactar con el asistente.» Ni que había gastado los 30, ni cuál es su plan, ni
// cuándo se renueva, ni un botón para pagar. El mensaje dice que el asistente está CAÍDO — y el
// único momento de conversión del tier gratuito se presenta como un fallo del producto.
//
// El SaaS ya manda todo lo necesario: `check_quota` construye `{error, limit, used, tier, kind,
// upgrade_required}` y el stream lo emite entero. Se pierde AQUÍ, dos veces:
//   1. el frame se lee buscando `message`, pero la clave que viaja es `error` — así que hasta el
//      texto se perdía y llegaba un genérico;
//   2. el resto de campos ni se miraban.

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { queryMock, commandMock } = vi.hoisted(() => ({ queryMock: vi.fn(), commandMock: vi.fn() }));

vi.mock('./runtime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  RUNTIME_URL: '',
  getClient: () => ({ query: queryMock, command: commandMock }),
  runtimeHeaders: () => ({ 'X-Hub-Id': 'h1', 'X-Hub-Session': 'sesion' }),
}));
vi.mock('./config', () => ({ config: { hubId: 'h1' } }));
vi.mock('./cloud', () => ({ getAccessToken: () => 'tok' }));

import { streamAssistant, type AssistantFailure, type AssistantUsage } from './assistant';

function sseStream(lines: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(c) {
      for (const l of lines) c.enqueue(enc.encode(l));
      c.close();
    },
  });
}

/** El frame EXACTO que emite el SaaS al agotarse la cuota (`QuotaExceeded.to_dict()`). */
const QUOTA_FRAME =
  'data: ' +
  JSON.stringify({
    type: 'error',
    error: 'Monthly message quota exhausted',
    limit: 30,
    used: 30,
    tier: 'free',
    kind: 'messages',
    upgrade_required: true,
  }) +
  '\n\n';

/** El frame de cuota tal y como viaja HOY (`QuotaExceeded.to_dict()`, saas#1540 ya desplegado):
 *  con `code` legible por máquina y con `resets_at`. */
const QUOTA_FRAME_WITH_CODE =
  'data: ' +
  JSON.stringify({
    type: 'error',
    error: 'Monthly message quota exhausted',
    code: 'quota_exceeded',
    limit: 30,
    used: 30,
    tier: 'free',
    kind: 'messages',
    upgrade_required: true,
    resets_at: '2026-09-01T00:00:00+00:00',
  }) +
  '\n\n';

/** El frame POST-turno que cierra cada stream (saas#1540). */
const USAGE_FRAME =
  'data: ' +
  JSON.stringify({
    type: 'usage',
    tier: 'free',
    tier_name: 'Free',
    sessions_used: 3,
    sessions_limit: 10,
    messages_used: 25,
    messages_limit: 30,
    resets_at: '2026-09-01T00:00:00+00:00',
  }) +
  '\n\n';

function runAndCaptureFailure(lines: string[]): Promise<unknown> {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, body: sseStream(lines) }) as unknown as Response),
  );
  return new Promise((resolve) => {
    let captured: unknown;
    streamAssistant([{ role: 'user', content: '¿Cuánto he vendido hoy?' }] as never, {
      onToken: () => {},
      onError: (e: unknown) => {
        captured = e;
      },
      onDone: () => resolve(captured),
    } as never);
    setTimeout(() => resolve(captured), 50);
  });
}

describe('la cuota agotada llega con su plan y su salida', () => {
  beforeEach(() => vi.clearAllMocks());

  it('el turno agotado se distingue de una caída de red', async () => {
    const failure = (await runAndCaptureFailure([QUOTA_FRAME])) as AssistantFailure;

    expect(failure?.quota, 'sin esto el dueño lee «no se pudo contactar» y cree que está roto').toBeTruthy();
    expect(failure!.quota!.upgradeRequired).toBe(true);
  });

  it('trae el plan y el consumo, que es lo que hace la frase útil', async () => {
    const failure = (await runAndCaptureFailure([QUOTA_FRAME])) as AssistantFailure;

    expect(failure!.quota!.tier).toBe('free');
    expect(failure!.quota!.used).toBe(30);
    expect(failure!.quota!.limit).toBe(30);
  });

  // El defecto de dos capas: la clave que viaja es `error`, no `message`. Leyendo la equivocada
  // se perdía hasta el texto del SaaS.
  it('lee la clave que el SaaS manda de verdad', async () => {
    const failure = (await runAndCaptureFailure([QUOTA_FRAME])) as AssistantFailure;

    expect(failure?.message).toContain('quota');
  });

  // Y lo que NO puede pasar: que un error de transporte se pinte como si fuera de cuota, con un
  // botón de pagar que no arregla nada.
  it('un error que no es de cuota no finge serlo', async () => {
    const other = 'data: ' + JSON.stringify({ type: 'error', error: 'upstream exploded' }) + '\n\n';

    const failure = (await runAndCaptureFailure([other])) as AssistantFailure;

    expect(failure?.quota).toBeUndefined();
    expect(failure?.message).toContain('upstream');
  });
});

// ── hub#1183 — el contrato NUEVO del SaaS tiene que LLEGAR, no caerse en el cliente ────────────
//
// saas#1540 dejó el stream diciendo tres cosas más que aquí nadie recogía: el `code` legible por
// máquina, la fecha en que vuelven los mensajes, y los contadores POST-turno. Sin ellas el drawer
// sabe que se acabó, pero no cuándo vuelve ni cuánto lleva gastado ANTES de agotarlo.

describe('hub#1183 — el motivo, la fecha y los contadores cruzan hasta la pantalla', () => {
  beforeEach(() => vi.clearAllMocks());

  // El motivo se LEE, no se infiere de un booleano cualquiera: `upgrade_required` es una
  // recomendación comercial y `code` es el hecho. Se queda como respaldo por si un emisor viejo
  // no manda `code` todavía (el test de arriba, con el frame sin `code`, es ese respaldo).
  it('reconoce la cuota por su `code`, aunque no venga `upgrade_required`', async () => {
    const frame =
      'data: ' +
      JSON.stringify({
        type: 'error',
        error: 'Monthly message quota exhausted',
        code: 'quota_exceeded',
        limit: 30,
        used: 30,
        tier: 'free',
      }) +
      '\n\n';

    const failure = (await runAndCaptureFailure([frame])) as AssistantFailure;

    expect(failure?.quota, 'el `code` es el hecho; el flag es solo la recomendación').toBeTruthy();
    expect(failure!.quota!.used).toBe(30);
  });

  // «Has gastado 30 de 30» sin fecha es un callejón: no se puede decidir si esperar o pagar.
  it('trae la fecha en que se renuevan los mensajes', async () => {
    const failure = (await runAndCaptureFailure([QUOTA_FRAME_WITH_CODE])) as AssistantFailure;

    expect(failure!.quota!.resetsAt).toBe('2026-09-01T00:00:00+00:00');
  });

  // El contador POST-turno: la cabecera `X-Assistant-Usage` va siempre un mensaje por detrás
  // (se escribe antes del cuerpo), así que el dato bueno es este frame.
  it('el frame `usage` que cierra el turno llega al llamador', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, body: sseStream([USAGE_FRAME, 'data: {"type":"done"}\n\n']) }) as unknown as Response),
    );

    const seen: AssistantUsage[] = [];
    await new Promise<void>((resolve) => {
      streamAssistant([{ role: 'user', content: 'hola' }] as never, {
        onToken: () => {},
        onUsage: (u: AssistantUsage) => seen.push(u),
        onDone: () => resolve(),
        onError: () => resolve(),
      } as never);
      setTimeout(resolve, 50);
    });

    expect(seen, 'sin este frame el contador del pie no se mueve hasta recargar').toHaveLength(1);
    expect(seen[0].messagesUsed).toBe(25);
    expect(seen[0].messagesLimit).toBe(30);
    expect(seen[0].tier).toBe('free');
    expect(seen[0].resetsAt).toBe('2026-09-01T00:00:00+00:00');
  });

  // Y lo que NO puede pasar: que el frame `usage` se pinte como si el modelo lo hubiera dicho.
  it('el frame `usage` no aporta ni un token al texto de la respuesta', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, body: sseStream([USAGE_FRAME, 'data: {"type":"done"}\n\n']) }) as unknown as Response),
    );

    let text = '';
    await new Promise<void>((resolve) => {
      streamAssistant([{ role: 'user', content: 'hola' }] as never, {
        onToken: (t: string) => {
          text += t;
        },
        onDone: () => resolve(),
        onError: () => resolve(),
      } as never);
      setTimeout(resolve, 50);
    });

    expect(text).toBe('');
  });
});
