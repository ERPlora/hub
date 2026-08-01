// El asistente se autenticaba con la credencial EQUIVOCADA.
//
// `/api/assistant/chat/stream` lo sirve el RUNTIME del hub, y el runtime exige la sesión local
// (`X-Hub-Session`) — la autoridad de permisos local (ARQUITECTURA.md §2.9). `assistant.ts`
// montaba sus cabeceras a mano y mandaba `Authorization: Bearer <JWT del cloud>`, que es otra
// credencial y para otro interlocutor: el JWT cloud es el adaptador de LOGIN, no la sesión.
//
// Resultado en el producto: cada mensaje respondía
//     401 {"error":"falta sesión (cabecera X-Hub-Session)"}
// y el chat mostraba «No se pudo contactar con el asistente». Reproducido en Android contra
// producción el 2026-08-02; el mismo endpoint, llamado con `X-Hub-Session`, devolvía 200 y
// streameaba tokens con normalidad — o sea que el backend estaba bien y fallaba el cliente.
//
// El arreglo es usar `runtimeHeaders()`, el MISMO helper que el resto de `/api/*`.

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { queryMock, commandMock } = vi.hoisted(() => ({ queryMock: vi.fn(), commandMock: vi.fn() }));

vi.mock('./runtime', () => ({
  RUNTIME_URL: '',
  getClient: () => ({ query: queryMock, command: commandMock }),
  runtimeHeaders: () => ({ 'X-Hub-Id': 'h1', 'X-Hub-Session': 'sesion-local-abc' }),
}));
vi.mock('./config', () => ({ config: { hubId: 'h1' } }));
vi.mock('./cloud', () => ({ getAccessToken: () => 'jwt-del-cloud' }));

import { streamAssistant } from './assistant';

function sseStream(lines: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(c) {
      for (const l of lines) c.enqueue(enc.encode(l));
      c.close();
    },
  });
}

describe('credencial del asistente', () => {
  let cabeceras: Record<string, string>;

  beforeEach(() => {
    cabeceras = {};
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init: RequestInit) => {
        cabeceras = (init.headers ?? {}) as Record<string, string>;
        return {
          ok: true,
          status: 200,
          body: sseStream([`data: ${JSON.stringify({ type: 'done' })}\n\n`]),
        } as unknown as Response;
      }),
    );
  });

  it('manda la sesión local del runtime', async () => {
    await streamAssistant([{ role: 'user', content: 'hola' }], { onToken: () => {} });
    expect(cabeceras['X-Hub-Session']).toBe('sesion-local-abc');
  });

  it('sigue identificando el hub', async () => {
    await streamAssistant([{ role: 'user', content: 'hola' }], { onToken: () => {} });
    expect(cabeceras['X-Hub-Id']).toBe('h1');
  });

  it('pide el stream por SSE', async () => {
    // Sin esto el runtime no responde en streaming y el chat se queda mudo.
    await streamAssistant([{ role: 'user', content: 'hola' }], { onToken: () => {} });
    expect(cabeceras['Accept']).toBe('text/event-stream');
  });
});
