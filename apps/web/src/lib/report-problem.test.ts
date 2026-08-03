// @vitest-environment happy-dom
// Contrato del reporte MANUAL de problemas (botón «Reportar un problema» del menú de usuario).
// Reutiliza el MISMO embudo que el reporte automático (lib/error-report):
//   POST /api/error-report  { type:'user_report', message, url }
// El runtime local lo normaliza a un ErrorEvent{source:'frontend', error_code:'user_report'} y lo
// reenvía al Cloud, donde (error_code accionable, severity 'unexpected') abre un issue de GitHub.
// A diferencia del automático: lo dispara el usuario, lleva su texto, NO se throttlea, y devolvemos
// el resultado (true/false) para dar feedback (toast) en la UI. Best-effort: nunca lanza.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import {
  reportUserProblem,
  openReportProblem,
  closeReportProblem,
  reportProblemOpen,
} from './report-problem';

function mockFetchOk() {
  const fn = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
  vi.stubGlobal('fetch', fn);
  return fn;
}

beforeEach(() => {
  reportProblemOpen.value = false;
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('report-problem', () => {
  it('open/close alternan el estado del modal', () => {
    expect(reportProblemOpen.value).toBe(false);
    openReportProblem();
    expect(reportProblemOpen.value).toBe(true);
    closeReportProblem();
    expect(reportProblemOpen.value).toBe(false);
  });

  it('POSTea a /api/error-report con type=user_report, el mensaje y la url', async () => {
    const fetchMock = mockFetchOk();
    const ok = await reportUserProblem('la impresora no imprime');
    expect(ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toMatch(/\/api\/error-report$/);
    expect(init.method).toBe('POST');
    const body = JSON.parse(init.body as string);
    expect(body.type).toBe('user_report');
    expect(body.message).toBe('la impresora no imprime');
    expect(typeof body.url).toBe('string');
  });

  it('recorta el mensaje antes de enviarlo', async () => {
    const fetchMock = mockFetchOk();
    await reportUserProblem('  con espacios  ');
    const body = JSON.parse((fetchMock.mock.calls[0] as [string, RequestInit])[1].body as string);
    expect(body.message).toBe('con espacios');
  });

  it('devuelve false si el runtime responde !ok (no lanza)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) }));
    await expect(reportUserProblem('x')).resolves.toBe(false);
  });

  it('devuelve false si el fetch rechaza (offline), sin lanzar', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    await expect(reportUserProblem('x')).resolves.toBe(false);
  });

  it('NO throttlea: dos envíos idénticos POSTean dos veces', async () => {
    const fetchMock = mockFetchOk();
    await reportUserProblem('mismo mensaje');
    await reportUserProblem('mismo mensaje');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('mensaje vacío o solo espacios: no POSTea y devuelve false', async () => {
    const fetchMock = mockFetchOk();
    expect(await reportUserProblem('   ')).toBe(false);
    expect(await reportUserProblem('')).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
