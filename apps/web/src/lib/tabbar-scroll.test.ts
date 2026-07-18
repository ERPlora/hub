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
import { describe, expect, it, vi } from 'vitest';

import {
  hintScroll,
  scrollActiveTabIntoView,
  shouldHintScroll,
  syncTabbarOverflow,
  tabbarOverflow,
} from './tabbar-scroll';

/** Fija las métricas de layout que jsdom no calcula. */
function metricas(el: HTMLElement, m: Partial<Record<'offsetLeft' | 'offsetWidth' | 'clientWidth' | 'scrollWidth', number>>): void {
  for (const [k, v] of Object.entries(m)) {
    Object.defineProperty(el, k, { configurable: true, value: v });
  }
}

/**
 * Monta un segment de `n` pestañas de 84px dentro de una barra visible de `clientWidth`, con la
 * pestaña `activa` marcada como la marca Ionic. El 84 es solo el ancho del fixture (números
 * redondos para las cuentas de abajo); el mínimo real vive en polish.css y se mide aparte.
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

// El degradado de borde señala que hay más pestañas fuera de vista. Tiene que ser DINÁMICO: un
// degradado fijo a la derecha seguiría oscureciendo la última pestaña una vez llegas al final, y
// eso se lee como un fallo, no como "hay más". De ahí los cuatro estados.
describe('tabbarOverflow', () => {
  it('sin desbordamiento no marca ningún borde', () => {
    const seg = segmentCon(3, 0, 382);
    metricas(seg, { scrollWidth: 252 }); // 3*84 = 252 < 382

    expect(tabbarOverflow(seg)).toBe('none');
  });

  it('al principio de una barra que desborda solo marca el borde derecho', () => {
    const seg = segmentCon(6, 0, 382); // 6*84 = 504 > 382
    seg.scrollLeft = 0;

    expect(tabbarOverflow(seg)).toBe('end');
  });

  it('a mitad de scroll marca los dos bordes', () => {
    const seg = segmentCon(6, 0, 382);
    seg.scrollLeft = 60;

    expect(tabbarOverflow(seg)).toBe('both');
  });

  it('al final solo marca el borde izquierdo (no deja el degradado colgando)', () => {
    const seg = segmentCon(6, 0, 382);
    seg.scrollLeft = 504 - 382; // tope

    expect(tabbarOverflow(seg)).toBe('start');
  });

  it('tolera el subpíxel: a 0.5px del tope cuenta como final', () => {
    const seg = segmentCon(6, 0, 382);
    seg.scrollLeft = 504 - 382 - 0.5;

    expect(tabbarOverflow(seg)).toBe('start');
  });

  it('sin segment devuelve none', () => {
    expect(tabbarOverflow(null)).toBe('none');
  });
});

describe('syncTabbarOverflow', () => {
  it('escribe el estado en data-overflow para que lo lea el CSS', () => {
    const seg = segmentCon(6, 0, 382);
    seg.scrollLeft = 0;

    syncTabbarOverflow(seg);

    expect(seg.dataset.overflow).toBe('end');
  });

  it('no revienta sin segment', () => {
    expect(() => syncTabbarOverflow(null)).not.toThrow();
  });
});

// El degradado dice "hay más"; el movimiento enseña el GESTO. Al entrar, la barra se asoma un poco
// y vuelve. Es una pista, no una animación decorativa, así que se gobierna con guardarraíles.
describe('shouldHintScroll', () => {
  it('da la pista cuando quedan pestañas a la derecha', () => {
    expect(shouldHintScroll({ overflow: 'end', reducedMotion: false, yaScrolleado: false })).toBe(true);
    expect(shouldHintScroll({ overflow: 'both', reducedMotion: false, yaScrolleado: false })).toBe(true);
  });

  it('NO da la pista si caben todas: no hay nada que descubrir', () => {
    expect(shouldHintScroll({ overflow: 'none', reducedMotion: false, yaScrolleado: false })).toBe(false);
  });

  it('NO da la pista si ya estás al final: no queda nada a la derecha', () => {
    expect(shouldHintScroll({ overflow: 'start', reducedMotion: false, yaScrolleado: false })).toBe(false);
  });

  it('NO da la pista con prefers-reduced-motion: movimiento no pedido', () => {
    expect(shouldHintScroll({ overflow: 'end', reducedMotion: true, yaScrolleado: false })).toBe(false);
  });

  it('NO da la pista si la barra YA se movió sola para revelar la pestaña activa', () => {
    // scrollActiveTabIntoView ya produjo movimiento: repetirlo sería un tirón raro, y además el
    // usuario ya ha visto que la barra se mueve.
    expect(shouldHintScroll({ overflow: 'both', reducedMotion: false, yaScrolleado: true })).toBe(false);
  });
});

describe('hintScroll', () => {
  it('se asoma y vuelve al origen', () => {
    vi.useFakeTimers();
    const seg = segmentCon(6, 0, 382);
    const movimientos: number[] = [];
    seg.scrollTo = ((opts: { left: number }) => movimientos.push(opts.left)) as unknown as typeof seg.scrollTo;

    hintScroll(seg);
    expect(movimientos).toEqual([28]); // se asoma

    vi.runAllTimers();
    expect(movimientos).toEqual([28, 0]); // y vuelve
    vi.useRealTimers();
  });

  it('no revienta sin segment', () => {
    expect(() => hintScroll(null)).not.toThrow();
  });
});
