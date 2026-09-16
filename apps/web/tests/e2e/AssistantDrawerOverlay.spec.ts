// El panel del Asistente se abre ENCIMA de la pantalla, no dentro de ella (hub#1899).
//
// Lo que clava: en la app de Android, sobre la pantalla de Caja, el cajón salía metido en la
// página — su cabecera caía bajo la de «Caja» y el buscador, los botones de vista y la tarjeta de
// la sesión se pintaban por encima del chat, con lo que no se podía usar ni el Asistente ni la
// Caja (QA de Android del 16/09, emulador `Pixel_10_Pro`).
//
// El cajón y su scrim son dos `position: fixed` hermanos bajo `<ion-app>`, así que su contrato
// depende ENTERO de que ningún ancestro se convierta en su bloque contenedor o en un contexto de
// apilamiento por encima de ellos. Basta un `transform`, un `filter`, un `contain: layout`, un
// `perspective` o un `will-change` en `.assistant-host`, en `ion-app` o en el `body` para que el
// cajón se quede encerrado en la página — y ninguna de esas propiedades se pone «para el cajón»:
// se ponen para animar otra cosa, y rompen esto a distancia. Por eso esto NO afirma sobre el CSS
// del cajón: pregunta al navegador QUÉ HAY PINTADO en cada punto de la pantalla.
//
// ⚠️ Chromium NO reproduce el fallo de Android. Medido el 16/09 en este mismo banco a 426 px con
// el Asistente abierto por la topbar: el cajón sale anclado al viewport (`top: 0`, alto completo),
// el scrim cubre la pantalla y los cuatro puntos de abajo caen todos dentro del cajón. Así que
// esto NO es la reproducción de hub#1899 — es la guarda de la mitad que el navegador sí sostiene,
// y la de Android se verifica sobre el APK del tag.
//
// Lo que estas medidas SÍ cazan, comprobado inyectando el positivo: un `transform` en
// `.assistant-host` —el ancestro que la issue señala— manda el cajón a la página y el buscador
// pasa a ganar el punto del chat («toca la página (página:li.setup-strip-item)»).
// Lo que NO cazan, y conviene saberlo antes de fiarse: en Chromium el apilamiento de este cajón
// no se puede romper por z-index. Se probaron `ion-router-outlet { z-index: 60 }` y
// `.assistant-drawer { z-index: 0 }` y los DOS sobrevivieron: con `contain: layout` en `ion-app`
// (le cae por la clase `ion-page` de `core.css`), sus descendientes `fixed` se pintan con él y
// manda el orden del DOM, donde `.assistant-host` va después del `ion-split-pane`. O sea que en
// navegador la superficie de regresión real es el BLOQUE CONTENEDOR, no el z-index.
import { test, expect } from '../bench-boot';
import { loggedInSession } from './shell-visual-helpers';
import type { Page } from '@playwright/test';

/** Abre el Asistente como lo abre una persona: por la topbar (en móvil, desde el desbordamiento). */
async function openAssistant(page: Page): Promise<void> {
  const direct = page.locator('[data-testid="topbar-assistant"]');
  if (await direct.isVisible().catch(() => false)) {
    await direct.click();
  } else {
    await page.locator('[data-testid="topbar-more"]').click();
    await page.locator('[data-testid="topbar-more-assistant"]').click();
  }
  await expect(page.locator('[data-testid="assistant-drawer"]')).toHaveAttribute('data-open', 'true');
  // La transición del panel es de 0,2 s: las medidas se toman con el panel ya quieto.
  await page.waitForTimeout(400);
}

/**
 * Qué hay pintado en cada punto: `drawer`, `scrim` o `página` (con qué elemento de la página).
 *
 * `elementFromPoint` es lo que el dedo toca, así que responde a la vez por el apilamiento y por la
 * geometría: si el cajón se queda encerrado en la página, aquí salen los elementos de la página.
 */
async function whatIsPaintedAt(page: Page, points: Array<{ label: string; x: number; y: number }>) {
  return page.evaluate((pts) => {
    const drawer = document.querySelector<HTMLElement>('[data-testid="assistant-drawer"]')!;
    const scrim = document.querySelector<HTMLElement>('.assistant-scrim')!;
    const out: Record<string, string> = {};
    for (const p of pts) {
      const hit = document.elementFromPoint(p.x, p.y);
      out[p.label] = !hit
        ? 'nada'
        : drawer.contains(hit)
          ? 'drawer'
          : scrim === hit || scrim.contains(hit)
            ? 'scrim'
            : `página:${hit.tagName.toLowerCase()}${hit.className ? '.' + String(hit.className).split(' ')[0] : ''}`;
    }
    return out;
  }, points);
}

test.describe('el panel del Asistente se abre encima de la pantalla (hub#1899)', () => {
  test('en móvil cubre la pantalla y nada de la página se pinta por encima', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await loggedInSession(page);
    await page.goto('/settings');
    await expect(page.locator('.ok-tabbar').filter({ visible: true }).first()).toBeVisible();
    await openAssistant(page);

    // Los cuatro sitios donde la pantalla de debajo se colaba en la captura del QA: la franja de
    // la cabecera de la página, el buscador, la zona de la tarjeta y la barra de pestañas.
    const painted = await whatIsPaintedAt(page, [
      { label: 'franjaDeLaCabecera', x: 195, y: 30 },
      { label: 'zonaDelBuscador', x: 195, y: 180 },
      { label: 'zonaDeLaTarjeta', x: 195, y: 420 },
      { label: 'barraDePestañas', x: 195, y: 800 },
    ]);
    for (const [where, what] of Object.entries(painted)) {
      expect(
        what,
        `en «${where}» toca la página (${what}) en vez del Asistente: eso es la pantalla ` +
          'pintándose por encima del chat (hub#1899)',
      ).toMatch(/^(drawer|scrim)$/);
    }

    const geometry = await page.evaluate(() => {
      const drawer = document.querySelector<HTMLElement>('[data-testid="assistant-drawer"]')!;
      const head = drawer.querySelector<HTMLElement>('.assistant-head')!;
      const scrim = document.querySelector<HTMLElement>('.assistant-scrim')!;
      const d = drawer.getBoundingClientRect();
      const s = scrim.getBoundingClientRect();
      return {
        drawerTop: d.top,
        drawerBottom: d.bottom,
        headTop: head.getBoundingClientRect().top,
        drawerPaddingTop: parseFloat(getComputedStyle(drawer).paddingTop) || 0,
        scrim: { top: s.top, left: s.left, width: s.width, height: s.height },
        viewport: { width: window.innerWidth, height: window.innerHeight },
      };
    });

    expect(
      geometry.drawerTop,
      'el cajón tiene que empezar en el borde de la pantalla: si empieza más abajo es que un ' +
        'ancestro se ha convertido en su bloque contenedor y quedó encerrado en la página (hub#1899)',
    ).toBe(0);
    expect(
      geometry.drawerBottom,
      'y llegar hasta abajo del todo: media pantalla de cajón deja la página usable por debajo',
    ).toBe(geometry.viewport.height);
    expect(
      geometry.headTop,
      'su cabecera va ARRIBA DEL TODO, solo por debajo de lo que reserve la barra de estado',
    ).toBe(geometry.drawerTop + geometry.drawerPaddingTop);
    expect(
      geometry.scrim,
      'el scrim cubre la pantalla entera: es lo que oscurece la página y se traga sus toques',
    ).toMatchObject({ top: 0, left: 0, ...geometry.viewport });

  });

  test('en tablet el cajón sigue anclado a la pantalla, no a la página', async ({ page }) => {
    // Desde 768px el panel EMPUJA el shell en vez de taparlo (no hay scrim), pero el anclaje al
    // viewport es el mismo contrato — y es el que se rompe con un ancestro transformado.
    await page.setViewportSize({ width: 834, height: 1112 });
    await loggedInSession(page);
    await page.goto('/settings');
    await expect(page.locator('.ok-tabbar').filter({ visible: true }).first()).toBeVisible();
    await openAssistant(page);

    const g = await page.evaluate(() => {
      const drawer = document.querySelector<HTMLElement>('[data-testid="assistant-drawer"]')!;
      const r = drawer.getBoundingClientRect();
      return { top: r.top, right: r.right, bottom: r.bottom, viewport: { w: window.innerWidth, h: window.innerHeight } };
    });

    expect(g.top, 'el cajón arranca en el borde superior de la pantalla también en tablet').toBe(0);
    expect(g.bottom, 'y llega hasta abajo').toBe(g.viewport.h);
    expect(g.right, 'pegado al borde derecho, que es el hueco que le reserva el shell').toBe(g.viewport.w);
  });
});
