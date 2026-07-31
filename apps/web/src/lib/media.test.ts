// Contrato de `fetchMediaBytes`: la vía por la que el visor de /files consigue el contenido de
// un fichero. Es el runtime del Hub quien lee disco o S3 — el navegador nunca los toca (ADR-0047).
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./runtime', () => ({
  RUNTIME_URL: 'http://127.0.0.1:8787',
  runtimeHeaders: () => ({ 'X-Hub-Session': 'sesion-viva' }),
}));

import { fetchMediaBytes } from './media';

const okResponse = (body = 'contenido') => ({
  ok: true,
  arrayBuffer: () => Promise.resolve(new TextEncoder().encode(body).buffer),
});

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
});

describe('fetchMediaBytes', () => {
  it('pide el fichero al runtime con la sesión del hub', async () => {
    vi.mocked(fetch).mockResolvedValue(okResponse() as unknown as Response);
    const bytes = await fetchMediaBytes({ id: 'f/a.log', name: 'a.log', url: '/api/media/raw?path=f%2Fa.log' });
    expect(fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8787/api/media/raw?path=f%2Fa.log',
      expect.objectContaining({ headers: { 'X-Hub-Session': 'sesion-viva' } }),
    );
    expect(new TextDecoder().decode(bytes!)).toBe('contenido');
  });

  it('no manda la sesión del hub a un tercero cuando la URL es absoluta', async () => {
    // En cloud el listado podía traer una URL firmada de S3; la cabecera de sesión es un secreto
    // del hub y no puede viajar fuera de su origen.
    vi.mocked(fetch).mockResolvedValue(okResponse() as unknown as Response);
    await fetchMediaBytes({ id: 'x', name: 'x.pdf', url: 'https://fsn1.your-objectstorage.com/erplora-hubs/x.pdf?sig=1' });
    expect(fetch).toHaveBeenCalledWith('https://fsn1.your-objectstorage.com/erplora-hubs/x.pdf?sig=1');
  });

  it('devuelve null si el fichero no tiene URL', async () => {
    expect(await fetchMediaBytes({ id: 'x', name: 'x.pdf' })).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('devuelve null en error de red o respuesta no OK (el modal enseña su aviso)', async () => {
    vi.mocked(fetch).mockResolvedValue({ ok: false, status: 404 } as unknown as Response);
    expect(await fetchMediaBytes({ id: 'x', name: 'x.log', url: '/api/media/raw?path=x' })).toBeNull();

    vi.mocked(fetch).mockRejectedValue(new Error('offline'));
    expect(await fetchMediaBytes({ id: 'x', name: 'x.log', url: '/api/media/raw?path=x' })).toBeNull();
  });
});
