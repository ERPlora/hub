// #278 — «La navegación inferior recorta pestañas en móvil»: el footer ion-footer > ion-segment
// (tabbar por módulo) no reservaba espacio para la barra de gestos/home-indicator de iOS/Android.
// Las pestañas (min-height 46px, labels de 2 líneas) quedaban bajo ella y se recortaban. El fix es
// añadir padding-bottom: env(safe-area-inset-bottom) al footer, mismo patrón que ok-app-launcher.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const css = readFileSync(new URL('./polish.css', import.meta.url), 'utf8');

describe('el footer del tabbar respeta la safe-area en móvil (#278)', () => {
  it('ion-footer añade padding para la barra de gestos (env(safe-area-inset-bottom))', () => {
    // Busca el bloque de estilos del footer.
    const start = css.indexOf('ion-footer {');
    expect(start, 'no se encontró el bloque ion-footer en polish.css').toBeGreaterThan(-1);
    const block = css.slice(start, css.indexOf('}', start) + 1);
    expect(
      block,
      'sin padding-bottom: env(safe-area-inset-bottom) las pestañas se recortan bajo la home-indicator',
    ).toContain('safe-area-inset-bottom');
  });
});
