import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

import { upgradePlanUrl } from './upgrade-plan-link';

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
