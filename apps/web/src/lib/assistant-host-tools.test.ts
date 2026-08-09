// Host tools del asistente (hub#631): `hub.marketplace.search` y `hub.modules.install`.
//
// La queja real que esto clava (2026-08-09): pedirle al asistente instalar un módulo y que se
// INVENTE una política de seguridad («solo tú puedes hacerlo desde tu Hub») — porque sin tool no
// hay camino, y un modelo sin camino racionaliza. El diseño verdadero: el asistente es otro
// caller CON LOS PERMISOS DEL USUARIO; instalar es una mutación como cualquier otra (confirm-card)
// y lo DESTRUCTIVO no se ofrece jamás (regla de Ioan — eso lo garantiza el catálogo Rust).
//
// Estas dos tools NO van por el dispatcher genérico (query/command de módulos): las ejecuta el
// shell contra sus endpoints HTTP reales — el catálogo del marketplace y `request-install`, que
// revalida admin server-side (`require_admin_session`). Aquí se prueba el MAPEO, con los mismos
// mocks que assistant.test.ts.

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { queryMock, commandMock, requestInstallMock, catalogMock } = vi.hoisted(() => ({
  queryMock: vi.fn(),
  commandMock: vi.fn(),
  requestInstallMock: vi.fn(),
  catalogMock: vi.fn(),
}));

vi.mock('./runtime', () => ({
  RUNTIME_URL: '',
  getClient: () => ({ query: queryMock, command: commandMock }),
  runtimeHeaders: () => ({ 'X-Hub-Id': 'h1', 'X-Hub-Session': 'sesion' }),
  requestInstall: requestInstallMock,
}));
vi.mock('./config', () => ({ config: { hubId: 'h1' } }));
vi.mock('./cloud', () => ({ getAccessToken: () => 'tok', cloudMarketplaceModules: catalogMock }));

import { streamAssistant } from './assistant';

function sseLine(obj: unknown): string {
  return `data: ${JSON.stringify(obj)}\n\n`;
}
function sseStream(lines: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(c) {
      for (const l of lines) c.enqueue(enc.encode(l));
      c.close();
    },
  });
}
function mockFetchRounds(rounds: string[][]): { bodies: Array<{ messages: unknown[] }> } {
  const bodies: Array<{ messages: unknown[] }> = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, opts: { body: string }) => {
      bodies.push(JSON.parse(opts.body));
      return { ok: true, body: sseStream(rounds[bodies.length - 1] ?? [sseLine({ type: 'done' })]) } as unknown as Response;
    }),
  );
  return { bodies };
}
function run(
  onConfirm?: (call: { name: string; arguments: string; kind?: string }) => Promise<boolean>,
) {
  return new Promise<{ done: boolean }>((resolve) => {
    streamAssistant([{ role: 'user', content: 'instala inventario' }] as never, {
      onToken: () => {},
      onDone: () => resolve({ done: true }),
      onError: () => resolve({ done: false }),
      onConfirm,
    });
  });
}

const CATALOG = [
  { id: 'inventory', name: 'Inventory', description: 'Products and stock', version: '1.2.19', priceLabel: 'Gratis', installed: false, available: true },
  { id: 'sales', name: 'Sales', description: 'POS sales', version: '3.0.1', priceLabel: 'Gratis', installed: true, available: true },
];

beforeEach(() => {
  vi.restoreAllMocks();
  queryMock.mockReset();
  commandMock.mockReset();
  requestInstallMock.mockReset();
  catalogMock.mockReset();
  catalogMock.mockResolvedValue(CATALOG);
  requestInstallMock.mockResolvedValue({ ok: true, module_id: 'inventory', version: '1.2.19' });
});

describe('hub.marketplace.search', () => {
  it('va al catálogo del marketplace, NUNCA al dispatcher de queries', async () => {
    const { bodies } = mockFetchRounds([
      [sseLine({ type: 'function_call', name: 'hub.marketplace.search', call_id: 'c1', arguments: '{"search":"invent"}' })],
      [sseLine({ type: 'done' })],
    ]);
    const r = await run();
    expect(r.done).toBe(true);
    expect(catalogMock).toHaveBeenCalled();
    expect(queryMock).not.toHaveBeenCalled();
    // El resultado que continúa el turno lleva el módulo filtrado, con su id y versión.
    const toolMsg = bodies[1].messages.find(
      (m) => (m as { role: string }).role === 'tool',
    ) as { content: string };
    expect(toolMsg.content).toContain('inventory');
    expect(toolMsg.content).toContain('1.2.19');
    expect(toolMsg.content).not.toContain('POS sales');
  });
});

describe('hub.modules.install', () => {
  it('tras CONFIRMAR, instala por request-install (admin revalidado server-side)', async () => {
    mockFetchRounds([
      [sseLine({ type: 'function_call', name: 'hub.modules.install', call_id: 'c2', kind: 'command', arguments: '{"module_id":"inventory"}' })],
      [sseLine({ type: 'done' })],
    ]);
    const confirm = vi.fn(async () => true);
    const r = await run(confirm);
    expect(r.done).toBe(true);
    expect(confirm).toHaveBeenCalledOnce();
    // Sin versión en los argumentos → la resuelve del catálogo (la última publicada).
    expect(requestInstallMock).toHaveBeenCalledWith('inventory', '1.2.19');
    expect(commandMock).not.toHaveBeenCalled();
  });

  it('sin confirmación NO instala — default-deny', async () => {
    mockFetchRounds([
      [sseLine({ type: 'function_call', name: 'hub.modules.install', call_id: 'c3', kind: 'command', arguments: '{"module_id":"inventory"}' })],
      [sseLine({ type: 'done' })],
    ]);
    const r = await run(async () => false);
    expect(r.done).toBe(true);
    expect(requestInstallMock).not.toHaveBeenCalled();
  });
});
