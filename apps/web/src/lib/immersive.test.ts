// @vitest-environment happy-dom
// Modo INMERSIVO del shell: vender ocupa toda la pantalla.
//
// El TPV es la única pantalla del Hub que se usa de pie y con prisa, y es la que peor lleva el
// chrome: barra lateral, topbar y tabbar del módulo se comen el alto que necesita la rejilla en una
// tablet de mostrador. Odoo POS, Square y Lightspeed abren la caja sin nada alrededor; aquí es un
// modo, porque el mismo hub es también el back-office.
//
// El reparto es el de ADR-0048 y no se mueve: el chrome es del SHELL. El módulo no oculta nada ni
// llama a la Fullscreen API — solo PIDE (`erp:chrome-request`), y solo se le atiende si su entrada
// de `navigation[]` declaró el control en `chrome`. Esa lista es una enum cerrada que crece aquí,
// no en el manifest.
//
// Dos mitades que tienen que ir juntas o el modo miente:
//   - la marca en el documento (`html.immersive`), que es lo que esconde el chrome por CSS;
//   - la Fullscreen API del navegador, que quita ADEMÁS la barra del navegador.
// La segunda es BEST-EFFORT: iOS no la da en el iPhone y la app instalada ya viene sin chrome. Que
// falle no puede llevarse por delante la primera, que es la que de verdad pedía el mostrador.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { nextTick, ref } from 'vue';
import {
  IMMERSIVE_CLASS,
  CHROME_REQUEST_EVENT,
  immersive,
  setImmersive,
  toggleImmersive,
  chromeControlsFor,
  installChrome,
} from './immersive';

/** Deja el documento con (o sin) Fullscreen API, y devuelve los espías. */
function conFullscreenAPI(soportada: boolean) {
  const request = vi.fn(async () => {
    fullscreenElement = document.documentElement;
    document.dispatchEvent(new Event('fullscreenchange'));
  });
  const exit = vi.fn(async () => {
    fullscreenElement = null;
    document.dispatchEvent(new Event('fullscreenchange'));
  });
  Object.defineProperty(document.documentElement, 'requestFullscreen', {
    value: soportada ? request : undefined, configurable: true, writable: true,
  });
  Object.defineProperty(document, 'exitFullscreen', {
    value: soportada ? exit : undefined, configurable: true, writable: true,
  });
  return { request, exit };
}

let fullscreenElement: Element | null = null;

beforeEach(() => {
  fullscreenElement = null;
  Object.defineProperty(document, 'fullscreenElement', {
    get: () => fullscreenElement, configurable: true,
  });
  conFullscreenAPI(true);
});

afterEach(() => {
  setImmersive(false);
  document.documentElement.className = '';
});

describe('modo inmersivo', () => {
  it('esconde el chrome y pide la pantalla completa al navegador', async () => {
    const { request } = conFullscreenAPI(true);

    setImmersive(true);

    expect(immersive.value).toBe(true);
    expect(document.documentElement.classList.contains(IMMERSIVE_CLASS)).toBe(true);
    await Promise.resolve();
    expect(request).toHaveBeenCalledOnce();
  });

  it('al salir devuelve el chrome y suelta la pantalla completa', async () => {
    const { exit } = conFullscreenAPI(true);
    setImmersive(true);
    await Promise.resolve();

    setImmersive(false);

    expect(document.documentElement.classList.contains(IMMERSIVE_CLASS)).toBe(false);
    await Promise.resolve();
    expect(exit).toHaveBeenCalledOnce();
  });

  it('se aplica igual donde NO hay Fullscreen API', async () => {
    // El iPhone no la da y la app instalada ya viene sin chrome del navegador. Atar el modo a la
    // API dejaría el botón muerto justo en el dispositivo por el que se pidió que fuese visible.
    conFullscreenAPI(false);

    expect(() => setImmersive(true)).not.toThrow();

    expect(immersive.value).toBe(true);
    expect(document.documentElement.classList.contains(IMMERSIVE_CLASS)).toBe(true);
  });

  it('devuelve el chrome cuando el usuario sale con Esc', async () => {
    setImmersive(true);
    await Promise.resolve();
    expect(immersive.value).toBe(true);

    // Esc y F11 salen del fullscreen sin pasar por nuestro botón. Sin escuchar esto, el cajero se
    // queda con la ventana normal Y sin barra lateral, sin nada visible que se lo devuelva.
    fullscreenElement = null;
    document.dispatchEvent(new Event('fullscreenchange'));

    expect(immersive.value).toBe(false);
    expect(document.documentElement.classList.contains(IMMERSIVE_CLASS)).toBe(false);
  });

  it('alterna', () => {
    toggleImmersive();
    expect(immersive.value).toBe(true);
    toggleImmersive();
    expect(immersive.value).toBe(false);
  });
});

describe('opt-in declarativo del manifest (ADR-0048)', () => {
  const manifest = {
    navigation: [
      { id: 'pos', label: 'Sell', chrome: ['fullscreen'] },
      { id: 'sales', label: 'Sales' },
    ],
  } as never;

  it('solo la pestaña que lo declara ofrece el control', () => {
    expect(chromeControlsFor(manifest, 'pos')).toEqual(['fullscreen']);
    expect(chromeControlsFor(manifest, 'sales')).toEqual([]);
  });

  it('un manifest sin navegación, o una pestaña que no existe, no ofrecen nada', () => {
    expect(chromeControlsFor(null, 'pos')).toEqual([]);
    expect(chromeControlsFor(manifest, 'no-existe')).toEqual([]);
  });
});

describe('canal de chrome con el Web Component montado', () => {
  /** Un outlet como el de ModuleView, con el WC del módulo dentro. */
  function outletConWc() {
    const outlet = document.createElement('div');
    const wc = document.createElement('erp-pos-touch');
    outlet.appendChild(wc);
    document.body.appendChild(outlet);
    return { outlet, wc };
  }

  function pedir(wc: Element, control: string) {
    wc.dispatchEvent(new CustomEvent(CHROME_REQUEST_EVENT, {
      detail: { control, action: 'toggle' }, bubbles: true, composed: true,
    }));
  }

  it('atiende la petición del control que la pestaña declaró', () => {
    const { outlet, wc } = outletConWc();
    const parar = installChrome(outlet, ref(['fullscreen']));

    pedir(wc, 'fullscreen');

    expect(immersive.value).toBe(true);
    parar();
  });

  it('IGNORA un control que la pestaña no declaró', () => {
    // La autoridad es el manifest del shell, no lo que el módulo pida. Sin esta puerta, cualquier
    // módulo instalado podría dejar el hub sin chrome desde su propio Web Component.
    const { outlet, wc } = outletConWc();
    const parar = installChrome(outlet, ref<string[]>([]));

    pedir(wc, 'fullscreen');

    expect(immersive.value).toBe(false);
    parar();
  });

  it('anuncia al WC qué controles honra, y el estado en que está', async () => {
    const { outlet, wc } = outletConWc();
    const parar = installChrome(outlet, ref(['fullscreen']));
    await Promise.resolve();

    // La capacidad: sin ella el módulo no pinta el botón (un `sales` nuevo sobre una imagen vieja).
    expect(wc.getAttribute('chrome')).toBe('fullscreen');
    expect(wc.hasAttribute('fullscreen')).toBe(false);

    pedir(wc, 'fullscreen');
    await Promise.resolve();
    expect(wc.hasAttribute('fullscreen')).toBe(true);

    parar();
  });

  it('anuncia la capacidad también al WC que se monta DESPUÉS', async () => {
    // ModuleView reemplaza el hijo del outlet en cada cambio de pestaña y al reintentar: el
    // anuncio no puede depender de que el WC ya estuviera puesto al cablear.
    const outlet = document.createElement('div');
    document.body.appendChild(outlet);
    const parar = installChrome(outlet, ref(['fullscreen']));

    const wc = document.createElement('erp-pos-touch');
    outlet.appendChild(wc);
    await new Promise((r) => setTimeout(r, 0));

    expect(wc.getAttribute('chrome')).toBe('fullscreen');
    parar();
  });

  it('devuelve el chrome al pasar a una pestaña que no ofrece el control', async () => {
    // Dentro del mismo módulo se cambia de pestaña sin desmontar la vista: de «Vender» (que lo
    // declara) a «Ventas» (que no). Sin esto, la lista de ventas se quedaría sin menú y sin nadie
    // que supiera devolverlo, porque el ⋮ vive en el TPV.
    const { outlet, wc } = outletConWc();
    const controles = ref<string[]>(['fullscreen']);
    const parar = installChrome(outlet, controles);
    pedir(wc, 'fullscreen');
    expect(immersive.value).toBe(true);

    controles.value = [];
    await nextTick();

    expect(immersive.value).toBe(false);
    expect(wc.hasAttribute('chrome')).toBe(false);
    parar();
  });

  it('al salir del módulo devuelve el chrome', () => {
    // Navegar a Ajustes con el modo puesto dejaría al usuario en una pantalla sin menú y sin el
    // botón del TPV, que era lo único que sabía quitarlo.
    const { outlet, wc } = outletConWc();
    const parar = installChrome(outlet, ref(['fullscreen']));
    pedir(wc, 'fullscreen');
    expect(immersive.value).toBe(true);

    parar();

    expect(immersive.value).toBe(false);
    expect(document.documentElement.classList.contains(IMMERSIVE_CLASS)).toBe(false);
  });
});
