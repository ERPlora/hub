/**
 * El catálogo se pide EN EL IDIOMA que el usuario está mirando (hub#1003, saas#1457).
 *
 * «Añadir apps» salía en inglés dentro de una interfaz traducida entera. El dato ya viaja
 * traducido —el Cloud sirve el catálogo por idioma desde ADR-0364— pero solo para quien dice en
 * cuál lo quiere: callarse significa inglés, que es justo el fallo.
 *
 * El idioma sale de `getLocale()` y no de una preferencia guardada, por lo mismo que ya hace
 * `/api/navigation?locale=` (ADR-0055): es un hecho sobre **la persona que está leyendo ahora**,
 * y eso solo lo sabe la página. El ajuste del hub es el respaldo del runtime, no la fuente.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../i18n', () => ({
  getLocale: () => 'es',
  bootHubLanguage: () => {},
  t: (k: string) => k,
}));

const pedidas: string[] = [];
const fetchOriginal = globalThis.fetch;

beforeEach(() => {
  pedidas.length = 0;
  globalThis.fetch = vi.fn(async (url: RequestInfo | URL) => {
    pedidas.push(String(url));
    return new Response('[]', { status: 200, headers: { 'content-type': 'application/json' } });
  }) as typeof fetch;
});

afterEach(() => {
  globalThis.fetch = fetchOriginal;
});

describe('el catálogo se pide en el idioma del usuario', () => {
  it('manda ?locale= con el idioma activo', async () => {
    const { cloudMarketplaceModules } = await import('./cloud');

    await cloudMarketplaceModules();

    expect(pedidas).toHaveLength(1);
    expect(pedidas[0]).toContain('/api/marketplace/catalog?locale=es');
  });
});
