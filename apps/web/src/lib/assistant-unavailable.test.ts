// El asistente que NO contesta y el asistente al que no se pudo LLAMAR no son el mismo fallo
// — ERPlora/hub#1738.
//
// Reproducido en PRE (banco-pre, 10/09) con la sesión local del hub:
//
//   POST https://banco-pre.a.erplora.com/api/assistant/chat/stream  → HTTP/2 200
//   data: {"error":"No active credential for provider 'openai'","type":"error"}
//   data: {"type":"usage", ...}
//
// erplora.com contestó — en 200, con su motivo escrito — y aun así el dueño leía «No se pudo
// contactar con el asistente»: un diagnóstico FALSO que le manda a mirar su conexión, a reiniciar
// el TPV y a pulsar «Denunciar un problema», cuando nada de lo suyo está roto. Es el mismo error
// que ya costó una vez con la cuota (saas#1540): colapsar todo lo que no sea un `done` en «no se
// pudo contactar».
//
// El motivo por el que murió el turno viaja desde aquí: el frame que emite el RUNTIME cuando de
// verdad no alcanzó a erplora.com lleva `code: "cloud_unreachable"` (hub#1689, hub#1763); el que
// reenvía el SaaS es una NEGATIVA del servicio, que sí contestó.
import { describe, expect, it, vi } from 'vitest';

vi.mock('./runtime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  RUNTIME_URL: '',
  getClient: () => ({ query: vi.fn(), command: vi.fn() }),
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

function frame(payload: Record<string, unknown>): string {
  return `data: ${JSON.stringify(payload)}\n\n`;
}

/** El frame EXACTO capturado en PRE: el SaaS contestó 200 y dijo por qué no atiende. */
const SERVICE_REFUSAL = frame({
  type: 'error',
  error: "No active credential for provider 'openai'",
});

/** El frame que emite el RUNTIME del hub cuando erplora.com no le contesta (hub#1689). */
const UNREACHABLE = frame({ type: 'error', error: 'cloud_unreachable', code: 'cloud_unreachable' });

const QUOTA = frame({
  type: 'error',
  error: 'Monthly message quota exhausted',
  code: 'quota_exceeded',
  limit: 30,
  used: 30,
  tier: 'free',
  kind: 'messages',
  upgrade_required: true,
});

/** Corre un turno cuyo stream trae `lines` y devuelve el fallo que llegó a `onError`. */
async function failureOf(lines: string[]): Promise<AssistantFailure> {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(sseStream(lines), { status: 200 })),
  );
  let failure: unknown;
  await new Promise<void>((resolve) => {
    streamAssistant([{ role: 'user', content: 'hola' }], {
      onToken: () => {},
      onError: (e) => {
        failure = e;
        resolve();
      },
      onDone: () => resolve(),
    });
  });
  return failure as AssistantFailure;
}

describe('hub#1738 — por qué murió el turno', () => {
  it('una negativa del servicio NO es un fallo de conexión', async () => {
    const failure = await failureOf([SERVICE_REFUSAL]);

    expect(
      failure.reason,
      'el SaaS contestó 200 y dijo su motivo: llamarlo «no se pudo contactar» manda al dueño a mirar su red',
    ).toBe('service');
  });

  // El control del control: si TODO se clasificara como negativa del servicio, el test de arriba
  // pasaría y el mensaje de conexión —que sí es cierto cuando erplora.com no contesta— moriría.
  it('el frame del runtime sí es un fallo de conexión', async () => {
    const failure = await failureOf([UNREACHABLE]);

    expect(failure.reason).toBe('unreachable');
  });

  it('quedarse sin mensajes sigue siendo cuota, no una avería', async () => {
    const failure = await failureOf([QUOTA]);

    expect(failure.reason).toBe('quota');
    expect(failure.quota?.used).toBe(30);
  });
});
