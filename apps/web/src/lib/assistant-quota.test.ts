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

import { streamAssistant, type AssistantFailure } from './assistant';

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
