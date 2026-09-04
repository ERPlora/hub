import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

import { planUpgradeIsOfferable, upgradePlanPath, upgradePlanUrl } from './upgrade-plan-link';

const appSource = readFileSync(new URL('../App.vue', import.meta.url), 'utf8');

// «Actualizar plan» en el menú izquierdo — la salida a la gestión del plan de ESTE hub.
//
// Convive con el anti-steering de hub#479, y la línea es fina pero clara: lo que las tiendas miran
// no es «¿hay un enlace?» sino si la app es un ESCAPARATE. Gestionar la cuenta es lo que hace
// cualquier SaaS B2B (Slack, QuickBooks, Shopify) y está en las dos tiendas; enseñar precios y
// «mejora y ahorra un 20 %» dentro de la ventana es otra cosa.
//
// Por eso esto aterriza en `/dashboard/hubs/<id>/change-plan/` —la página de plan de ESE hub, o sea
// la cuenta del cliente— y NO en el marketplace de planes, que sí es escaparate. Y por eso los
// controles que se retiraron en hub#479 (botón «Comprar» con icono de carrito y la parrilla de
// precios al lado) siguen retirados: no es lo mismo.
describe('el enlace de actualizar plan', () => {
  it('apunta al plan de ESTE hub, no al escaparate del marketplace', () => {
    const url = upgradePlanUrl();
    expect(url).toContain('/dashboard/hubs/');
    expect(url).toContain('/change-plan/');
    // El marketplace de planes es la superficie promocional: si esto aterrizara ahí, la app
    // volvería a ser un escaparate y hub#479 habría que reabrirla.
    expect(url).not.toContain('/marketplace/plans');
  });

  it('lleva el hub, para que el SaaS sepa de cuál se habla', () => {
    // El id se interpola a la carta: `config.hubId` lo resuelve el boot, así que en un test sin
    // arrancar está vacío. Lo que se fija aquí es que la dirección lo LLEVA — que es el contrato con
    // el SaaS, cuya ruta es `<uuid:hub_id>` y sin id da 404.
    const source = readFileSync(new URL('./upgrade-plan-link.ts', import.meta.url), 'utf8');
    expect(source).toContain('config.hubId');
    expect(source).toContain('encodeURIComponent');
    expect(upgradePlanUrl()).toMatch(/\/change-plan\/\?utm_source=hub$/);
  });

  it('está en el menú izquierdo y disponible para todos', () => {
    expect(appSource).toContain('upgradePlanUrl');
    // Sin gate de permiso: decisión de Ioan (2026-08-09). `canOpenManagement` filtra la salida a
    // gestión del topbar por `hub.administer`; esta NO se filtra — el dueño entra muchas veces con
    // la sesión de caja, y esconderle su propio plan es peor que enseñárselo a un cajero que al
    // llegar al SaaS no podrá tocarlo (allí manda `IsHubAdmin`, que es la autoridad de verdad).
    expect(appSource).not.toMatch(/canOpenManagement[^\n]*upgradePlan/);
  });

  it('sale por la puerta de salir, que es la que funciona dentro de la app', () => {
    // `window.open` no abre NADA en la webview de la app instalada (hub#475): sin `openExternal`
    // esto sería un botón muerto justo en la pantalla donde el dueño va a pagar.
    expect(appSource).toContain('openExternal');
  });
});

// ── hub#756: la copia que reparte Google Play no ofrece este control ────────────────────────────
//
// El razonamiento de arriba sigue siendo bueno, y para la web y para Windows se mantiene: gestionar
// la cuenta no es un escaparate, y Microsoft lo permite por escrito (política 10.8.2 — un producto
// que no es juego puede usar su propia caja y mandar al navegador a completarla).
//
// Pero la QA sobre un Pixel real (hub#756) demostró lo que un argumento no puede: el revisor de
// Play pulsa el botón, ve abrirse Chrome en `…/change-plan/`, y eso es steering para él. Cuando lo
// que está en juego es que te tumben el envío, la lectura que importa no es la nuestra.
//
// Por eso el corte NO es «Android» sino la DISTRIBUCIÓN: el que pone la regla es quien reparte el
// binario. Un APK instalado de lado no lo gobierna Google, y a ese usuario esconderle su propio
// plan sería quitarle algo por un motivo que no le aplica.
describe('en la copia que reparte una tienda', () => {
  it('Google Play NO recibe el control: es quien lo trata como steering', () => {
    expect(planUpgradeIsOfferable('play')).toBe(false);
  });

  it('Microsoft SÍ lo recibe: su política 10.8.2 lo permite por escrito', () => {
    expect(planUpgradeIsOfferable('msstore')).toBe(true);
  });

  it('una instalación directa lo conserva: ninguna tienda la gobierna', () => {
    expect(planUpgradeIsOfferable('direct')).toBe(true);
  });

  it('sin señal se OFRECE, que es el lado seguro para el cliente', () => {
    // Un shell anterior a hub#757 no manda `distribution`, y el navegador tampoco. Quitar el
    // control ahí dejaría sin acceso a su plan a todo el que abre el hub en Chrome, que es la
    // mayoría — y por un riesgo que en el navegador no existe.
    expect(planUpgradeIsOfferable(undefined)).toBe(true);
  });

  it('App.vue esconde el botón con esa regla, no lo pinta siempre', () => {
    // El fallo de hub#756 era exactamente esto: el botón se pintaba sin mirar de dónde venía la app.
    expect(appSource).toContain('planUpgradeIsOfferable');
  });
});

// pm#196 — este es uno de los enlaces que la issue nombra por su nombre: «billing pide login y 2FA
// otra vez». Dentro de la app instalada el navegador del sistema no comparte cookies con el
// webview, así que la dueña aterrizaba en un login justo cuando iba a cambiar de plan. El pase de
// un solo uso lo cruza logueada; para pedirlo hace falta la RUTA, porque la dirección la arma el
// runtime (una página que eligiera el host elegiría dónde se gasta el pase).
describe('la ruta del plan, para el pase de un solo uso', () => {
  it('es una ruta PROPIA del SaaS, sin host', () => {
    const path = upgradePlanPath();
    expect(path.startsWith('/')).toBe(true);
    expect(path).not.toContain('://');
    // `//host` es una URL protocol-relative: el runtime la rechaza, y aquí no se genera jamás.
    expect(path.startsWith('//')).toBe(false);
  });

  it('es exactamente la cola del enlace de siempre, para que el destino no se bifurque', () => {
    expect(upgradePlanUrl()).toBe(`https://erplora.com${upgradePlanPath()}`);
  });

  it('App.vue cruza por la puerta compartida, no con el enlace pelado', () => {
    // El fallo que arregla pm#196: el mecanismo existía y este enlace no lo usaba.
    //
    // 🪤 Se afirma sobre la LLAMADA, no sobre los nombres sueltos: `toContain('saasDoor')` a secas
    // lo satisface la línea del `import`, así que devolver la llamada al enlace pelado dejaba el
    // test en verde. Comprobado mutando el fichero — con la aserción floja el mutante sobrevivía.
    expect(appSource).toContain(
      "openExternal(await saasDoor(upgradePlanPath(), upgradePlanUrl(), 'upgrade-plan'))",
    );
    // Y la forma vieja no puede quedarse de vuelta por otro camino.
    expect(appSource).not.toContain('openExternal(upgradePlanUrl())');
  });
});
