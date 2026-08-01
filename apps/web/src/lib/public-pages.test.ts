// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { getPublicPage, listPublicPages, normalizePublicPagePath, putPublicPage } from './public-pages';

vi.mock('./runtime', () => ({
  RUNTIME_URL: 'http://hub.test',
  runtimeHeaders: () => ({ Authorization: 'Bearer session' }),
}));

afterEach(() => vi.unstubAllGlobals());

describe('public pages client', () => {
  it('normaliza rutas legibles y rechaza escapes o caracteres de URL', () => {
    expect(normalizePublicPagePath(' /Carta/Verano/ ')).toBe('carta/verano');
    for (const path of ['', '../secret', 'carta?admin=1', 'con espacio']) {
      expect(() => normalizePublicPagePath(path)).toThrow('invalid public page path');
    }
  });

  it('carga el JSON de bloques por la ruta autenticada', async () => {
    const document = { blocks: [{ type: 'paragraph', data: { text: 'Carta' } }] };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true, data: document }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(getPublicPage('/Carta/Verano')).resolves.toEqual(document);
    expect(fetchMock).toHaveBeenCalledWith(
      'http://hub.test/api/public-pages/carta/verano',
      { headers: { Authorization: 'Bearer session' } },
    );
  });

  it('lista únicamente las definiciones públicas que entrega el runtime', async () => {
    const definitions = [{
      module_id: 'menu', path: 'menu', title: 'Menú', reads: ['menu.items.list'],
      slot: 'public.home.sections',
    }];
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ok: true, data: definitions,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(listPublicPages()).resolves.toEqual(definitions);
    expect(fetchMock).toHaveBeenCalledWith(
      'http://hub.test/api/public-pages',
      { headers: { Authorization: 'Bearer session' } },
    );
  });

  it('guarda únicamente JSON por PUT y mantiene la cabecera de sesión', async () => {
    const document = { blocks: [{ type: 'header', data: { text: 'Carta', level: 2 } }] };
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    vi.stubGlobal('fetch', fetchMock);

    await putPublicPage('carta', document);
    expect(fetchMock).toHaveBeenCalledWith('http://hub.test/api/public-pages/carta', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer session' },
      body: JSON.stringify(document),
    });
  });
});
