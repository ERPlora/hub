// Tests for the assistant function-calling round-trip (§9.2 keystone, paso 1: LEER).
// When the model asks to call a module tool, the runtime forwards a `function_call`
// event; streamAssistant runs it as a query with the user's session (getClient) and
// continues the turn with the result. Here we mock the SSE transport + the runtime
// client and assert the full loop.

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { queryMock, commandMock } = vi.hoisted(() => ({ queryMock: vi.fn(), commandMock: vi.fn() }));

vi.mock('./runtime', () => ({
  RUNTIME_URL: '',
  getClient: () => ({ query: queryMock, command: commandMock }),
  // El asistente usa el MISMO helper de cabeceras que el resto de `/api/*` (la sesión
  // local `X-Hub-Session` es la autoridad de permisos del runtime).
  runtimeHeaders: () => ({ 'X-Hub-Id': 'h1', 'X-Hub-Session': 'sesion' }),
}));
vi.mock('./config', () => ({ config: { hubId: 'h1' } }));
vi.mock('./cloud', () => ({ getAccessToken: () => 'tok' }));

import { streamAssistant } from './assistant';

function sseLine(obj: unknown): string {
  return `data: ${JSON.stringify(obj)}\n\n`;
}

function sseStream(lines: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const l of lines) controller.enqueue(enc.encode(l));
      controller.close();
    },
  });
}

/** Mock `fetch` to return one SSE body per call (round). Captures each request body. */
function mockFetchRounds(rounds: string[][]): { bodies: Array<{ messages: unknown[] }> } {
  const bodies: Array<{ messages: unknown[] }> = [];
  const fetchMock = vi.fn(async (_url: string, opts: { body: string }) => {
    bodies.push(JSON.parse(opts.body));
    const lines = rounds[bodies.length - 1] ?? [sseLine({ type: 'done' })];
    return { ok: true, body: sseStream(lines) } as unknown as Response;
  });
  vi.stubGlobal('fetch', fetchMock);
  return { bodies };
}

function run(
  messages: { role: string; content: string }[],
  onConfirm?: (call: { name: string; arguments: string; kind: string }) => Promise<boolean>,
) {
  const tokens: string[] = [];
  return new Promise<{ tokens: string[]; error?: unknown }>((resolve) => {
    streamAssistant(messages as never, {
      onToken: (t) => tokens.push(t),
      onDone: () => resolve({ tokens }),
      onError: (error) => resolve({ tokens, error }),
      onConfirm,
    });
  });
}

describe('streamAssistant tool round-trip', () => {
  beforeEach(() => {
    queryMock.mockReset();
    commandMock.mockReset();
    vi.unstubAllGlobals();
  });

  it('runs a read tool with the user session and continues the turn with the result', async () => {
    queryMock.mockResolvedValue([{ total: 100 }]);
    const { bodies } = mockFetchRounds([
      [
        sseLine({
          type: 'function_call',
          name: 'sales.list',
          call_id: 'c1',
          arguments: JSON.stringify({ since: '2026-01-01' }),
        }),
        sseLine({ type: 'done' }),
      ],
      [sseLine({ type: 'token', text: 'Vendiste 100.' }), sseLine({ type: 'done' })],
    ]);

    const { tokens, error } = await run([{ role: 'user', content: '¿cuánto vendí?' }]);

    expect(error).toBeUndefined();
    // executed as a query (read-only) with the parsed args
    expect(queryMock).toHaveBeenCalledWith('sales.list', { since: '2026-01-01' });
    // final answer streamed
    expect(tokens.join('')).toBe('Vendiste 100.');
    // a second turn was sent, carrying the assistant tool_call + the tool result
    expect(bodies).toHaveLength(2);
    const round2 = bodies[1].messages as Array<Record<string, unknown>>;
    const asst = round2.find((m) => m.role === 'assistant' && m.tool_calls) as never as {
      tool_calls: Array<{ id: string; function: { name: string } }>;
    };
    expect(asst.tool_calls[0].id).toBe('c1');
    expect(asst.tool_calls[0].function.name).toBe('sales.list');
    const tool = round2.find((m) => m.role === 'tool') as { tool_call_id: string; content: string };
    expect(tool.tool_call_id).toBe('c1');
    expect(tool.content).toContain('100');
  });

  it('degrades gracefully when the tool fails (e.g. a write op is not a query)', async () => {
    queryMock.mockRejectedValue(new Error('unknown query'));
    const { bodies } = mockFetchRounds([
      [sseLine({ type: 'function_call', name: 'pos.sale.create', call_id: 'c2', arguments: '{}' }), sseLine({ type: 'done' })],
      [sseLine({ type: 'token', text: 'No pude hacerlo.' }), sseLine({ type: 'done' })],
    ]);

    const { tokens, error } = await run([{ role: 'user', content: 'crea una venta' }]);

    expect(error).toBeUndefined();
    expect(tokens.join('')).toBe('No pude hacerlo.');
    const tool = (bodies[1].messages as Array<Record<string, unknown>>).find((m) => m.role === 'tool') as {
      content: string;
    };
    expect(tool.content).toContain('error');
  });

  it('a plain answer (no tool) streams tokens and never calls a tool', async () => {
    mockFetchRounds([[sseLine({ type: 'token', text: 'Hola.' }), sseLine({ type: 'done' })]]);
    const { tokens } = await run([{ role: 'user', content: 'hola' }]);
    expect(tokens.join('')).toBe('Hola.');
    expect(queryMock).not.toHaveBeenCalled();
  });

  it('a write tool (command) runs only after onConfirm approves', async () => {
    commandMock.mockResolvedValue({ id: 42 });
    const { bodies } = mockFetchRounds([
      [
        sseLine({
          type: 'function_call',
          name: 'pos.sale.create',
          call_id: 'w1',
          arguments: JSON.stringify({ total: 9 }),
          kind: 'command',
        }),
        sseLine({ type: 'done' }),
      ],
      [sseLine({ type: 'token', text: 'Venta creada.' }), sseLine({ type: 'done' })],
    ]);
    const confirm = vi.fn().mockResolvedValue(true);

    const { tokens } = await run([{ role: 'user', content: 'crea una venta de 9' }], confirm);

    expect(confirm).toHaveBeenCalledWith({
      name: 'pos.sale.create',
      arguments: JSON.stringify({ total: 9 }),
      kind: 'command',
    });
    expect(commandMock).toHaveBeenCalledWith('pos.sale.create', { total: 9 });
    expect(queryMock).not.toHaveBeenCalled(); // a write must NOT go through the read path
    expect(tokens.join('')).toBe('Venta creada.');
    const tool = (bodies[1].messages as Array<Record<string, unknown>>).find((m) => m.role === 'tool') as {
      content: string;
    };
    expect(tool.content).toContain('42');
  });

  it('a write tool is NOT executed when onConfirm declines', async () => {
    const { bodies } = mockFetchRounds([
      [sseLine({ type: 'function_call', name: 'pos.sale.void', call_id: 'w2', arguments: '{}', kind: 'command' }), sseLine({ type: 'done' })],
      [sseLine({ type: 'token', text: 'Cancelado.' }), sseLine({ type: 'done' })],
    ]);

    await run([{ role: 'user', content: 'anula la venta' }], vi.fn().mockResolvedValue(false));

    expect(commandMock).not.toHaveBeenCalled();
    const tool = (bodies[1].messages as Array<Record<string, unknown>>).find((m) => m.role === 'tool') as {
      content: string;
    };
    expect(tool.content).toContain('cancelled');
  });

  it('a write tool is NOT executed without a confirm handler (safe default)', async () => {
    mockFetchRounds([
      [sseLine({ type: 'function_call', name: 'pos.sale.void', call_id: 'w3', arguments: '{}', kind: 'command' }), sseLine({ type: 'done' })],
      [sseLine({ type: 'token', text: 'ok' }), sseLine({ type: 'done' })],
    ]);
    await run([{ role: 'user', content: 'anula la venta' }]); // no onConfirm provided
    expect(commandMock).not.toHaveBeenCalled();
  });
});
