// #266 — «Citas: Añadir no abre el formulario»: el source y el bundle están correctos, pero el SW
// cachea los bundles de módulos con stale-while-revalidate (sw.js:66-79). Los assets de
// `/public/modules/` NO llevan hash en su nombre (se reescriben in-place al reconstruir), así que
// el SW puede servir un bundle VIEJO en la primera carga aunque el servidor tenga uno nuevo — y si
// el viejo tenía el bug del «+», este se reproduce. Lo correcto: los módulos van SIEMPRE a la red
// (no se cachean), como ya pasa con /api. Este test fija ese contrato.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const sw = readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8');

describe('el SW no cachea los bundles de módulos (sin hash, swr serviría versión vieja) (#266)', () => {
  it('el fetch handler hace passthrough (sin caché) para /modules/', () => {
    // /modules/ debe caer en la misma exclusión que /api (passthrough, nunca cacheado).
    expect(
      sw,
      '/modules/ no debe caer en el cacheo SWR: sus assets no llevan hash y swr serviría uno viejo',
    ).toContain("pathname.startsWith('/modules/");
  });
});
