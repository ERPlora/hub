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

const {
  queryMock,
  commandMock,
  requestInstallMock,
  catalogMock,
  blueprintCatalogMock,
  downloadBlueprintMock,
  inspectBlueprintMock,
  importBlueprintMock,
} = vi.hoisted(() => ({
  queryMock: vi.fn(),
  commandMock: vi.fn(),
  requestInstallMock: vi.fn(),
  catalogMock: vi.fn(),
  blueprintCatalogMock: vi.fn(),
  downloadBlueprintMock: vi.fn(),
  inspectBlueprintMock: vi.fn(),
  importBlueprintMock: vi.fn(),
}));

vi.mock('./runtime', () => ({
  RUNTIME_URL: '',
  getClient: () => ({ query: queryMock, command: commandMock }),
  runtimeHeaders: () => ({ 'X-Hub-Id': 'h1', 'X-Hub-Session': 'sesion' }),
  requestInstall: requestInstallMock,
  fetchBlueprintCatalog: blueprintCatalogMock,
  downloadBlueprint: downloadBlueprintMock,
  inspectBlueprint: inspectBlueprintMock,
  importBlueprint: importBlueprintMock,
  // `blueprint-hero` (real, imported by the apply flow) normalises the report through these two
  // helpers. Functional stand-ins mirroring runtime.ts — the real classification is pinned by
  // blueprint-hero's own tests; here what is under test is the dispatch pipeline.
  moduleInstallStatusInfo: (m: { status: string; blocked_on?: string[]; error?: string }) =>
    m.status === 'installed' || m.status === 'already_installed'
      ? { kind: m.status, blockedOn: [], purchase: [] }
      : m.status === 'blocked'
        ? { kind: 'blocked', blockedOn: m.blocked_on ?? [], purchase: [] }
        : { kind: 'failed', blockedOn: [], purchase: [], error: m.error },
  sectionStatusInfo: (s: string | Record<string, unknown>) =>
    typeof s === 'string'
      ? { kind: s.toLowerCase() }
      : 'Failed' in s
        ? { kind: 'failed', reason: String(s.Failed) }
        : 'Ignored' in s
          ? { kind: 'ignored', reason: String(s.Ignored) }
          : 'PartiallyApplied' in s
            ? { kind: 'partial', reason: String(s.PartiallyApplied) }
            : { kind: 'applied' },
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

/** What the SaaS blueprint catalogue answers (shape of `CatalogBlueprint`). */
const BLUEPRINTS = [
  {
    slug: 'restaurante-es',
    name: 'Restaurante',
    description: 'Restaurante y bar en España',
    locale: 'es',
    country: 'ES',
    latest_version: '1.0.4',
    latest_sha256: 'abc',
    size_bytes: 1024,
    downloads: 7,
  },
];

const BLUEPRINT_MANIFEST = {
  name: 'Restaurante',
  sections: ['hub_settings', 'media', 'hub_users', 'fiscal'],
  modules: [{ id: 'inventory' }, { id: 'sales' }],
};

beforeEach(() => {
  vi.restoreAllMocks();
  queryMock.mockReset();
  commandMock.mockReset();
  requestInstallMock.mockReset();
  catalogMock.mockReset();
  blueprintCatalogMock.mockReset();
  downloadBlueprintMock.mockReset();
  inspectBlueprintMock.mockReset();
  importBlueprintMock.mockReset();
  catalogMock.mockResolvedValue(CATALOG);
  requestInstallMock.mockResolvedValue({ ok: true, module_id: 'inventory', version: '1.2.19' });
  blueprintCatalogMock.mockResolvedValue(BLUEPRINTS);
  downloadBlueprintMock.mockResolvedValue(new Blob(['zip'], { type: 'application/zip' }));
  inspectBlueprintMock.mockResolvedValue({ ok: true, upload_id: 'up-1', manifest: BLUEPRINT_MANIFEST });
  importBlueprintMock.mockResolvedValue({
    sections: [{ section: 'hub_settings', status: 'Applied' }],
    installed_modules: [{ id: 'inventory', status: 'installed' }, { id: 'sales', status: 'installed' }],
  });
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

// hub#631 steps 2-3: the sector templates. `list` reads the SaaS catalogue; `apply` drives the
// SAME pipeline as the dashboard hero card (download → inspect → import with the one-click
// selection), whose semantics were verified additive before exposing the tool (import_sql.rs is
// INSERT-only + ADR-0304 natural-key guards: existing rows are skipped, never overwritten).
describe('hub.blueprints.list', () => {
  it('lee el catálogo de blueprints, NUNCA el dispatcher de queries, y recorta la ficha', async () => {
    const { bodies } = mockFetchRounds([
      [sseLine({ type: 'function_call', name: 'hub.blueprints.list', call_id: 'b1', arguments: '{}' })],
      [sseLine({ type: 'done' })],
    ]);
    const r = await run();
    expect(r.done).toBe(true);
    expect(blueprintCatalogMock).toHaveBeenCalled();
    expect(queryMock).not.toHaveBeenCalled();
    const toolMsg = bodies[1].messages.find(
      (m) => (m as { role: string }).role === 'tool',
    ) as { content: string };
    expect(toolMsg.content).toContain('restaurante-es');
    expect(toolMsg.content).toContain('1.0.4');
    // Trimmed: the model needs the card, not the checksum plumbing.
    expect(toolMsg.content).not.toContain('latest_sha256');
  });
});

describe('hub.blueprints.apply', () => {
  it('tras CONFIRMAR, aplica por el pipeline del hero: download → inspect → import con la selección one-click', async () => {
    const { bodies } = mockFetchRounds([
      [sseLine({ type: 'function_call', name: 'hub.blueprints.apply', call_id: 'b2', kind: 'command', arguments: '{"slug":"restaurante-es"}' })],
      [sseLine({ type: 'done' })],
    ]);
    const confirm = vi.fn(async () => true);
    const r = await run(confirm);
    expect(r.done).toBe(true);
    expect(confirm).toHaveBeenCalledOnce();
    expect(downloadBlueprintMock).toHaveBeenCalledWith('restaurante-es');
    expect(inspectBlueprintMock).toHaveBeenCalled();
    // The one-click selection (heroSelection, REAL): a template never carries another business's
    // people or fiscal identity, even though the bundle lists those sections.
    expect(importBlueprintMock).toHaveBeenCalledWith(
      'up-1',
      expect.objectContaining({
        users: false,
        fiscal: false,
        settings: true,
        media: true,
        modules: ['inventory', 'sales'],
      }),
    );
    // The model is told the outcome, not handed the raw report.
    const toolMsg = bodies[1].messages.find(
      (m) => (m as { role: string }).role === 'tool',
    ) as { content: string };
    expect(toolMsg.content).toContain('ready');
  });

  it('sin confirmación NO aplica nada — default-deny (ni descarga ni importa)', async () => {
    mockFetchRounds([
      [sseLine({ type: 'function_call', name: 'hub.blueprints.apply', call_id: 'b3', kind: 'command', arguments: '{"slug":"restaurante-es"}' })],
      [sseLine({ type: 'done' })],
    ]);
    const r = await run(async () => false);
    expect(r.done).toBe(true);
    expect(downloadBlueprintMock).not.toHaveBeenCalled();
    expect(importBlueprintMock).not.toHaveBeenCalled();
  });

  it('sin slug → nota de error para el modelo, sin tocar nada', async () => {
    const { bodies } = mockFetchRounds([
      [sseLine({ type: 'function_call', name: 'hub.blueprints.apply', call_id: 'b4', kind: 'command', arguments: '{}' })],
      [sseLine({ type: 'done' })],
    ]);
    const r = await run(async () => true);
    expect(r.done).toBe(true);
    expect(downloadBlueprintMock).not.toHaveBeenCalled();
    expect(importBlueprintMock).not.toHaveBeenCalled();
    const toolMsg = bodies[1].messages.find(
      (m) => (m as { role: string }).role === 'tool',
    ) as { content: string };
    expect(toolMsg.content).toContain('slug');
  });
});
