// @vitest-environment happy-dom
// Tests de `scrollActiveTabIntoView`: cuando el tabbar de footer (ADR-0022) tiene más pestañas de
// las que caben, la barra scrollea (polish.css, hub#165). Si la pestaña activa viene de la URL
// —ModuleView deep-linkea `/m/<moduleId>/<navId>`— puede quedar FUERA de vista al montar: el
// usuario no ve cuál está activa. Ionic NO lo resuelve (ion-segment no hace scrollIntoView; su
// prop `scrollable` solo afecta a layout y gestos), así que lo hace el shell.
//
// jsdom no calcula layout: offsetLeft/offsetWidth/clientWidth/scrollWidth son 0 y son getters de
// solo lectura, así que se fijan por instancia con defineProperty. Por eso la función trabaja con
// scrollLeft (medible) y no con scrollIntoView (no implementado en jsdom).
import { describe, expect, it } from 'vitest';

import { scrollActiveTabIntoView } from './tabbar-scroll';

/** Fija las métricas de layout que jsdom no calcula. */
function metricas(el: HTMLElement, m: Partial<Record<'offsetLeft' | 'offsetWidth' | 'clientWidth' | 'scrollWidth', number>>): void {
  for (const [k, v] of Object.entries(m)) {
    Object.defineProperty(el, k, { configurable: true, value: v });
  }
}

/**
 * Monta un segment de `n` pestañas de 84px (el mínimo táctil de polish.css) dentro de una barra
 * visible de `clientWidth`, con la pestaña `activa` marcada como la marca Ionic.
 */
function segmentCon(n: number, activa: number, clientWidth: number): HTMLElement {
  const seg = document.createElement('ion-segment');
  metricas(seg, { clientWidth, scrollWidth: n * 84 });
  for (let i = 0; i < n; i++) {
    const b = document.createElement('ion-segment-button');
    if (i === activa) b.classList.add('segment-button-checked');
    metricas(b, { offsetLeft: i * 84, offsetWidth: 84 });
    seg.appendChild(b);
  }
  seg.scrollLeft = 0;
  return seg;
}

describe('scrollActiveTabIntoView', () => {
  it('trae a la vista la pestaña activa cuando queda fuera POR LA DERECHA', () => {
    // El caso real: 5 pestañas de 84px (420) en 382px de barra —`tables` o `verifactu` en un móvil
    // de 390px— entrando por URL a la última. Sin esto, el usuario no ve cuál está activa.
    const seg = segmentCon(5, 4, 382);

    scrollActiveTabIntoView(seg);

    // La activa ocupa [336, 420]; para que su borde derecho entre en 382px de ancho → 420-382.
    expect(seg.scrollLeft).toBe(38);
  });

  it('trae a la vista la pestaña activa cuando queda fuera POR LA IZQUIERDA', () => {
    const seg = segmentCon(5, 0, 382);
    seg.scrollLeft = 200; // la barra venía scrolleada; la activa quedó detrás

    scrollActiveTabIntoView(seg);

    expect(seg.scrollLeft).toBe(0);
  });

  it('no mueve la barra si la pestaña activa YA se ve', () => {
    const seg = segmentCon(5, 1, 382); // la activa ocupa [84, 168], dentro de [0, 382]

    scrollActiveTabIntoView(seg);

    expect(seg.scrollLeft).toBe(0);
  });

  it('no toca nada si todas las pestañas caben (no hay scroll)', () => {
    const seg = segmentCon(3, 2, 382); // 3*84 = 252 < 382
    metricas(seg, { scrollWidth: 252 });

    scrollActiveTabIntoView(seg);

    expect(seg.scrollLeft).toBe(0);
  });

  it('no revienta si no hay segment o no hay pestaña activa', () => {
    expect(() => scrollActiveTabIntoView(null)).not.toThrow();

    const sinActiva = segmentCon(5, -1, 382);
    expect(() => scrollActiveTabIntoView(sinActiva)).not.toThrow();
    expect(sinActiva.scrollLeft).toBe(0);
  });
});
