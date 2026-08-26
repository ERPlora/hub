// hub#1038 / #1039 — the WIRING of the grounding audit. `auditTurn` being correct is worth
// nothing if nobody calls it: the QA pass read a drawer that printed "✅ Categoría creada"
// while the network panel showed no POST /api/command at all.
//
// The SSE transport and the runtime client are mocked the same way the sibling round-trip
// tests do it: what is under test is the LOOP (which tools ran, with what outcome, and what
// the turn then claimed), not the model and not the dispatcher.

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { queryMock, commandMock } = vi.hoisted(() => ({ queryMock: vi.fn(), commandMock: vi.fn() }));

vi.mock('./runtime', () => ({
  RUNTIME_URL: '',
  getClient: () => ({ query: queryMock, command: commandMock }),
  runtimeHeaders: () => ({ 'X-Hub-Id': 'h1', 'X-Hub-Session': 'sesion' }),
}));
vi.mock('./config', () => ({ config: { hubId: 'h1' } }));
vi.mock('./cloud', () => ({ getAccessToken: () => 'tok' }));

import { streamAssistant } from './assistant';
import type { TurnAudit } from './assistant-grounding';

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
function mockFetchRounds(rounds: string[][]): void {
  let n = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
      const lines = rounds[n++] ?? [sseLine({ type: 'done' })];
      return { ok: true, body: sseStream(lines) } as unknown as Response;
    }),
  );
}

function run(
  messages: { role: string; content: string }[],
  onConfirm?: () => Promise<boolean>,
): Promise<{ audit?: TurnAudit }> {
  return new Promise((resolve) => {
    let audit: TurnAudit | undefined;
    streamAssistant(messages as never, {
      onToken: () => {},
      onAudit: (a: TurnAudit) => {
        audit = a;
      },
      onDone: () => resolve({ audit }),
      onError: () => resolve({ audit }),
      onConfirm,
    } as never);
  });
}

describe('streamAssistant audits the turn it just produced', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // The exact shape of the hub#1038 session: the model answers in text, calls nothing, and
  // says it created a record.
  it('reports a success claim that no tool backed', async () => {
    mockFetchRounds([
      [sseLine({ type: 'token', text: '✅ Categoría creada con éxito. ID: `cat_9b4e7c1a`' }), sseLine({ type: 'done' })],
    ]);

    const { audit } = await run([{ role: 'user', content: 'Crea una categoría' }]);

    expect(audit?.claimedWithoutEffect).toBe(true);
    expect(audit?.unsourcedIds).toEqual(['cat_9b4e7c1a']);
  });

  // The honest path must stay clean, or the banner becomes wallpaper.
  it('stays clean when the write really ran', async () => {
    commandMock.mockResolvedValue({ id: '4e1c9b0a-2f8d-4a71-9c33-5b7e2a1d6f04' });
    mockFetchRounds([
      [
        sseLine({
          type: 'function_call',
          name: 'services.categories.create',
          call_id: 'c1',
          arguments: '{"name":"Barbería QA"}',
          kind: 'command',
        }),
        sseLine({ type: 'done' }),
      ],
      [sseLine({ type: 'token', text: '✅ Categoría creada con éxito.' }), sseLine({ type: 'done' })],
    ]);

    const { audit } = await run([{ role: 'user', content: 'Crea una categoría' }], async () => true);

    expect(commandMock).toHaveBeenCalled();
    expect(audit?.claimedWithoutEffect).toBe(false);
  });

  // hub#1038's real ending: the user pressed Cancel and the model said it was done anyway.
  it('reports a claim made after the user cancelled the card', async () => {
    mockFetchRounds([
      [
        sseLine({
          type: 'function_call',
          name: 'services.categories.create',
          call_id: 'c1',
          arguments: '{"name":"Barbería QA"}',
          kind: 'command',
        }),
        sseLine({ type: 'done' }),
      ],
      [sseLine({ type: 'token', text: 'Listo, ya he creado la categoría.' }), sseLine({ type: 'done' })],
    ]);

    const { audit } = await run([{ role: 'user', content: 'Crea una categoría' }], async () => false);

    expect(commandMock).not.toHaveBeenCalled();
    expect(audit?.claimedWithoutEffect).toBe(true);
  });
});
