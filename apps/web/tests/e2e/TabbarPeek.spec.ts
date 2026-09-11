// Regression test for ERPlora/hub#1830 — the footer tab strip has to SHOW that it continues.
//
// This one runs in a real browser on purpose: the defect is geometry, and the only engine that
// knows where a centred icon lands inside a grid column is the one that laid it out. happy-dom
// reports every offset as zero, so the unit tests next to `tabbar-peek.ts` can only check the
// arithmetic — this check is what ties that arithmetic to what is on screen.
//
// `/settings` and not a module screen because the e2e bench runs with an EMPTY modules directory
// (see `playwright.config.ts`), so there is no module tab bar to photograph here. It is the same
// strip either way: same component, same wiring in `AppPage`, and it reproduces the defect at the
// stock 88px floor — a module screen only makes it worse by raising the floor to 116px.
import { test, expect } from '../bench-boot';
import { hidesTabsSilently, type TabbarGeometry } from '../../src/lib/tabbar-peek';
import { loggedInSession } from './shell-visual-helpers';

/** Geometry of the strip on the VISIBLE page, plus what the model assumes about it. */
type MeasuredTabbar = TabbarGeometry & { strips: number; widths: number[]; scrollLeft: number };

async function measureTabbar(page: import('@playwright/test').Page): Promise<MeasuredTabbar> {
  return page.evaluate(() => {
    // The shell keeps several `.ion-page` in the DOM at once (hub#1734): a plain `querySelector`
    // hands back the dashboard's strip, not the one on screen. Only the visible one has a layout.
    const strips = Array.from(document.querySelectorAll<HTMLElement>('ion-footer ion-segment')).filter(
      (strip) => strip.offsetParent !== null,
    );
    const strip = strips[0];
    if (!strip) throw new Error('no visible footer tab strip');
    const tabs = Array.from(strip.querySelectorAll<HTMLElement>('ion-segment-button'));
    return {
      strips: strips.length,
      widths: tabs.map((tab) => tab.offsetWidth),
      scrollLeft: strip.scrollLeft,
      visibleWidth: strip.clientWidth,
      contentWidth: strip.scrollWidth,
      firstTabLeft: tabs[0]?.offsetLeft ?? 0,
      tabWidth: tabs[0]?.offsetWidth ?? 0,
      tabPitch: (tabs[1]?.offsetLeft ?? 0) - (tabs[0]?.offsetLeft ?? 0),
      tabCount: tabs.length,
    };
  });
}

test.describe('la barra de pestañas del footer avisa de que hay más (hub#1830)', () => {
  test('a 390px la primera pestaña oculta queda asomada, no un hueco', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await loggedInSession(page);
    await page.goto('/settings');
    await expect(page.locator('.ok-tabbar')).toBeVisible();

    // hub#1829 asoma la tira sola al entrar (0 → 28 → 0 en ~400 ms, empezando a los 450 ms). Lo que
    // se mide aquí es el REPOSO, que es lo que la persona tiene delante el resto del tiempo — y un
    // `scrollLeft` a cero NO basta para saber que ya está quieta: al entrar vale cero porque la
    // pista todavía no ha empezado. Se exige quieta dos veces seguidas, como el banco visual
    // (hub#1823), y después de que la pista haya tenido tiempo de ir y volver.
    await page.waitForTimeout(1_200);
    await expect
      .poll(
        async () => {
          const antes = (await measureTabbar(page)).scrollLeft;
          await page.waitForTimeout(400);
          const despues = (await measureTabbar(page)).scrollLeft;
          return antes === 0 && despues === 0;
        },
        { timeout: 10_000 },
      )
      .toBe(true);

    const geometry = await measureTabbar(page);

    // El banco tiene que reproducir el desbordamiento, o este test no prueba nada.
    expect(geometry.strips).toBe(1);
    expect(geometry.scrollLeft).toBe(0);
    expect(geometry.tabCount).toBeGreaterThan(1);
    expect(geometry.contentWidth).toBeGreaterThan(geometry.visibleWidth);
    // El modelo da por hecho que todas las pestañas son una columna del mismo ancho.
    expect(new Set(geometry.widths.map((width) => Math.round(width))).size).toBe(1);

    expect(
      hidesTabsSilently(geometry),
      `la tira esconde pestañas sin decirlo: ${JSON.stringify(geometry)}`,
    ).toBe(false);
  });

  test('a 390px con el suelo de 116px de un módulo, que es el caso de la issue', async ({ page }) => {
    // El banco arranca con el directorio de módulos VACÍO, así que aquí no hay pantalla de módulo
    // que fotografiar. Lo que la separa de `/settings` es UNA declaración: `ModuleView` sube el
    // suelo de pestaña a 116px para que quepan «Configuración» o «Etiquetas» sin partirse. Se
    // inyecta esa misma declaración —desde una HOJA DE ESTILOS, que es de donde viene en la app;
    // el `style` en línea es justo el que el arreglo se reserva para sí— y se mide lo mismo.
    await page.addInitScript(() => {
      const hoja = document.createElement('style');
      hoja.textContent = 'ion-footer ion-segment { --ok-tabbar-min: 116px; }';
      document.addEventListener('DOMContentLoaded', () => document.head.appendChild(hoja));
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await loggedInSession(page);
    await page.goto('/settings');
    await expect(page.locator('.ok-tabbar')).toBeVisible();
    await page.waitForTimeout(1_600);

    const geometry = await measureTabbar(page);
    expect(geometry.scrollLeft).toBe(0);
    expect(geometry.contentWidth).toBeGreaterThan(geometry.visibleWidth);
    // El suelo se respeta: ensanchar la pestaña es lo que deja sitio al asomo, nunca estrecharla.
    expect(geometry.tabWidth).toBeGreaterThanOrEqual(116);
    expect(
      hidesTabsSilently(geometry),
      `la tira de módulo esconde pestañas sin decirlo: ${JSON.stringify(geometry)}`,
    ).toBe(false);
  });

  test('a 1440px caben todas y las pestañas no se tocan', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loggedInSession(page);
    await page.goto('/settings');
    await expect(page.locator('.ok-tabbar')).toBeVisible();
    await page.waitForTimeout(700);

    const geometry = await measureTabbar(page);
    expect(geometry.contentWidth).toBeLessThanOrEqual(geometry.visibleWidth + 1);
    // Sin desbordamiento no hay nada que señalar: el ancho de pestaña se queda como estaba.
    expect(await page.locator('ion-footer ion-segment').first().getAttribute('style')).toBeNull();
  });
});
