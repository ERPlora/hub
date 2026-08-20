// hub#1041 — aplicar una plantilla NO configura lo fiscal, y el asistente decía que sí.
//
// Tras `hub.blueprints.apply` contestó: «✅ Serie de facturación F1 activa y por defecto · ✅
// VeriFactu configurado para cumplimiento AEAT · ya puedes emitir facturas con QR válido y cumplir
// con la normativa española». El hub tenía **0 series** y el runtime bloqueaba toda emisión — con
// el banner rojo «Todavía no puedes facturar» visible en la MISMA captura, a la izquierda.
//
// No lo leyó de ningún sitio: describió el resultado desde la descripción comercial de la
// plantilla. La propia tool ya avisa en su texto que «it never imports people, fiscal identity or
// another business's invoice numbering» — afirmó justo lo que su tool declara que NO hace.
//
// El arreglo no es pedirle que se porte bien: es que el resultado de aplicar la plantilla traiga
// el ESTADO REAL del hub. Así no hay hueco que rellenar — igual que hub#1044, donde la pregunta
// sin camino se arregló dándole el dato.

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { queryMock, commandMock } = vi.hoisted(() => ({ queryMock: vi.fn(), commandMock: vi.fn() }));
const { downloadMock, inspectMock, importMock } = vi.hoisted(() => ({
  downloadMock: vi.fn(),
  inspectMock: vi.fn(),
  importMock: vi.fn(),
}));

// Mock PARCIAL: solo la puerta de red y el cliente. Lo demás que exporta `runtime` (helpers que
// `blueprint-hero` usa por su cuenta) se deja tal cual — enumerarlo a mano convierte el test en
// una lista que hay que mantener, y el primer olvido sale como un error de mock disfrazado de
// fallo de producto (me pasó: el resultado llegaba como `{error: "No moduleInstallStatusInfo…"}`).
vi.mock('./runtime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  RUNTIME_URL: '',
  getClient: () => ({ query: queryMock, command: commandMock }),
  runtimeHeaders: () => ({ 'X-Hub-Id': 'h1', 'X-Hub-Session': 'sesion' }),
  downloadBlueprint: downloadMock,
  inspectBlueprint: inspectMock,
  importBlueprint: importMock,
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
    start(c) {
      for (const l of lines) c.enqueue(enc.encode(l));
      c.close();
    },
  });
}

/** Corre un turno donde el modelo aplica la plantilla, y devuelve el mensaje `tool` que el
 *  runtime manda de vuelta al Cloud — que es lo único que el modelo llega a leer. */
async function applyBlueprintAndCaptureToolResult(): Promise<Record<string, unknown>> {
  const bodies: { messages: { role: string; content: string }[] }[] = [];
  let round = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_u: string, opts: { body: string }) => {
      bodies.push(JSON.parse(opts.body));
      const lines =
        round++ === 0
          ? [
              sseLine({
                type: 'function_call',
                name: 'hub.blueprints.apply',
                call_id: 'c1',
                arguments: '{"slug":"peluqueria"}',
                kind: 'command',
              }),
              sseLine({ type: 'done' }),
            ]
          : [sseLine({ type: 'token', text: 'listo' }), sseLine({ type: 'done' })];
      return { ok: true, body: sseStream(lines) } as unknown as Response;
    }),
  );

  await new Promise<void>((resolve) => {
    streamAssistant([{ role: 'user', content: 'Monta el hub para una peluquería' }] as never, {
      onToken: () => {},
      onDone: () => resolve(),
      onError: () => resolve(),
      onConfirm: async () => true,
    });
  });

  const last = bodies[bodies.length - 1];
  const toolMsg = last.messages.find((m) => m.role === 'tool');
  return JSON.parse(toolMsg?.content ?? '{}') as Record<string, unknown>;
}

describe('aplicar una plantilla devuelve lo que SIGUE bloqueado', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    downloadMock.mockResolvedValue(new Blob());
    inspectMock.mockResolvedValue({ upload_id: 'u1', manifest: {} });
    importMock.mockResolvedValue({ installed_modules: [{ id: 'invoice', status: 'installed' }] });
    // El hub REAL tras la plantilla: lo fiscal sigue sin configurar y el runtime bloquea.
    queryMock.mockResolvedValue([
      {
        items: [
          { key: 'business_identity', state: 'pending', level: 'legal', title: 'Your business details', route: '/settings' },
          { key: 'verifactu.setup', state: 'pending', level: 'legal', title: 'Configure VeriFactu', route: '/m/verifactu/settings' },
          { key: 'apps', state: 'done', level: 'recommended', title: 'Apps', route: '/apps' },
        ],
      },
    ]);
  });

  it('el resultado nombra lo que sigue BLOQUEANDO, no solo lo instalado', async () => {
    const result = await applyBlueprintAndCaptureToolResult();

    expect(result.installed_modules).toBeTruthy();
    const blocking = result.still_blocking as { key: string }[] | undefined;
    expect(blocking, 'sin esto el modelo rellena el hueco con el folleto de la plantilla').toBeTruthy();
    expect(blocking!.map((i) => i.key)).toEqual(['business_identity', 'verifactu.setup']);
  });

  it('lo que ya está hecho NO viaja: el hueco que se tapa es el de lo que falta', async () => {
    const result = await applyBlueprintAndCaptureToolResult();

    const blocking = (result.still_blocking ?? []) as { key: string }[];
    expect(blocking.some((i) => i.key === 'apps')).toBe(false);
  });

  it('si el estado de setup no se puede leer, se dice — no se calla', async () => {
    queryMock.mockRejectedValue(new Error('runtime caído'));

    const result = await applyBlueprintAndCaptureToolResult();

    // Callar sería peor que fallar: el modelo leería «no hay nada bloqueando».
    expect(result.still_blocking).toBeUndefined();
    expect(result.setup_status_unavailable).toBe(true);
  });
});
