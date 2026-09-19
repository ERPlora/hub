// @vitest-environment happy-dom
// Quién reserva la barra de gestos de Android/iOS bajo el pie de página — y cuántas veces.
//
// #278 la puso: `ion-footer > ion-toolbar > ion-segment` es el tabbar por módulo, y sin reservar
// nada las pestañas (min-height 46px, labels de 2 líneas) quedaban cortadas bajo la barra de
// gestos. El arreglo de entonces fue un `padding-bottom: env(safe-area-inset-bottom)` sobre TODO
// `ion-footer` — sin ver que Ionic ya lo pone él, en el último toolbar del pie
// (`ion-footer.footer-toolbar-padding ion-toolbar:last-of-type`). La misma barra, reservada dos
// veces: ~50 dp muertos sobre el gesto de navegación en el emulador (hub#1895, medido por el QA
// de Android el 16/09 sobre el APK de `fb3b48a`).
//
// Esto NO es una comprobación de texto sobre el CSS: se monta el árbol REAL del pie (el del
// tabbar, como lo pinta `ModuleView.vue`, y el del menú lateral, como lo pinta `App.vue`), se le
// cargan las DOS hojas que compiten — `polish.css` y la regla de verdad de `@ionic/core` — y se le
// pregunta al motor de estilos cuánto acaba reservando cada uno. Lo único sustituido es `env()`,
// que happy-dom no resuelve: entra por una variable de prueba, igual que `core.css` de Ionic
// deriva `--ion-safe-area-bottom` de `env(safe-area-inset-bottom)`.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/** Lo que mide la barra de gestos. El número da igual; que se reserve UNA vez, no. */
const GESTURE_BAR = 34;

// Ruta desde el cwd (apps/web) y no desde `import.meta.url`: bajo happy-dom la URL del módulo no
// es `file:` y `readFileSync` la rechaza.
const polish = readFileSync(join(process.cwd(), 'src/theme/polish.css'), 'utf8');

/**
 * La regla con la que Ionic reserva la barra de gestos, leída del paquete INSTALADO.
 *
 * Copiarla aquí a mano dejaría el test verde el día que Ionic la cambie o la suelte — y ese es
 * justo el día en que el shell tendría que volver a ponerla él.
 */
function reglaDeIonic(): string {
  const bundle = readFileSync(
    join(process.cwd(), 'node_modules/@ionic/core/components/ion-footer.js'),
    'utf8',
  );
  const regla = /ion-footer\.footer-toolbar-padding ion-toolbar:last-of-type\{[^}]*\}/.exec(bundle);
  expect(
    regla,
    '@ionic/core ya no reserva la barra de gestos en el último toolbar del pie: si Ionic la ha ' +
      'soltado, el shell tiene que volver a ponerla (hub#1895)',
  ).not.toBeNull();
  return regla![0];
}

/**
 * Monta el pie con las dos hojas que compiten por reservar la barra de gestos.
 *
 * `barra` es lo que reporta el dispositivo: 34px en un móvil con gesto de navegación, 0 en uno con
 * tres botones o en un navegador de escritorio.
 */
function montar(markup: string, barra = GESTURE_BAR): void {
  document.head.innerHTML = '';
  document.body.innerHTML = '';

  const style = document.createElement('style');
  style.textContent = [
    // `--ion-safe-area-bottom` es lo que lee la regla de Ionic; `core.css` lo deriva de
    // `env(safe-area-inset-bottom)`, y `--test-gesture-bar` es ese mismo `env()` para polish.css.
    // Los dos se escriben con el valor literal: happy-dom no resuelve una variable cuyo valor es
    // otra `var()` si la regla que la lee lleva fallback — y salía un 0 que parecía un acierto.
    `html { --test-gesture-bar: ${barra}px; --ion-safe-area-bottom: ${barra}px; }`,
    reglaDeIonic(),
    polish.replaceAll('env(safe-area-inset-bottom', 'var(--test-gesture-bar'),
  ].join('\n');
  document.head.appendChild(style);

  document.body.innerHTML = markup;
}

/**
 * Cuánto reserva ese elemento bajo su contenido, en px.
 *
 * Sin regla que le aplique, el motor devuelve la cadena vacía y eso SÍ es cero. Cualquier otra
 * cosa que no sea una longitud —una `var()` que no se resolvió, por ejemplo— es el test mirando
 * hacia otro lado, así que revienta en vez de redondearla a cero.
 */
function reserva(selector: string): number {
  const el = document.querySelector<HTMLElement>(selector);
  expect(el, `no se montó ${selector}`).not.toBeNull();

  const valor = getComputedStyle(el!).paddingBottom.trim();
  if (valor === '') return 0;
  expect(valor, `${selector} no resolvió su padding-bottom a una longitud`).toMatch(/^-?[\d.]+px$/);
  return parseFloat(valor);
}

// `footer-toolbar-padding` no se escribe en la plantilla: se la pone Ionic en cada render mientras
// el teclado esté escondido y no haya un `ion-tab-bar` abajo (`ion-footer.js`, método `render`).
const PIE_DEL_TABBAR = `
  <div class="ion-page">
    <ion-footer id="tabbar" class="ion-no-border footer-toolbar-padding">
      <ion-toolbar>
        <ion-segment class="ok-tabbar module-tabbar"><ion-segment-button></ion-segment-button></ion-segment>
      </ion-toolbar>
    </ion-footer>
  </div>`;

const PIE_DEL_MENU = `
  <ion-menu class="dash-menu">
    <ion-content class="sidebar-content"></ion-content>
    <ion-footer id="menu-foot" class="ion-no-border sidebar-foot footer-toolbar-padding">
      <div class="sidebar-foot-brand"></div>
    </ion-footer>
  </ion-menu>`;

describe('la barra de gestos se reserva una sola vez bajo el pie (hub#1895, #278)', () => {
  it('el tabbar de un módulo la reserva UNA vez, y quien la reserva es el toolbar de Ionic', () => {
    montar(PIE_DEL_TABBAR);

    expect(
      reserva('#tabbar') + reserva('#tabbar ion-toolbar'),
      'entre el pie y su toolbar solo puede haber UNA barra de gestos: dos dejan ~50 dp muertos ' +
        'sobre el gesto de navegación (hub#1895)',
    ).toBe(GESTURE_BAR);
    expect(
      reserva('#tabbar'),
      'el pie no la reserva él: ya lo hace Ionic en el último toolbar, y el shell no lo duplica',
    ).toBe(0);
  });

  it('el pie del menú lateral no tiene toolbar: ahí la reserva el shell (#278)', () => {
    montar(PIE_DEL_MENU);

    expect(
      reserva('#menu-foot'),
      'sin toolbar dentro, la regla de Ionic no llega: si el shell tampoco reserva, el QR y la ' +
        'versión del menú quedan bajo la barra de gestos (#278)',
    ).toBe(GESTURE_BAR);
  });

  it('reserva lo que mide la barra de este dispositivo, nunca un número fijo', () => {
    // Tres botones de navegación, o el navegador de escritorio: no hay nada que reservar. Un
    // `padding-bottom: 34px` escrito a mano dejaría aquí una franja muerta — y en una tablet, que
    // reserva 24 donde un móvil reserva 52, dejaría el hueco mal en uno de los dos.
    montar(PIE_DEL_TABBAR, 0);
    expect(reserva('#tabbar') + reserva('#tabbar ion-toolbar')).toBe(0);

    montar(PIE_DEL_MENU, 0);
    expect(reserva('#menu-foot')).toBe(0);
  });
});
