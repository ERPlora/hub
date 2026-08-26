// Regression guard for hub#754: «las acciones Añadir y Editar no abren formularios en varias
// apps de la demo». El clic del botón «Añadir»/«Editar» de cualquier vista CRUD vive DENTRO de
// `ok-data-table` (OutfitKit), que pinta un `<ion-button>` por dentro. Ese `ion-button` solo
// dispara su handler si el SHELL lo registró antes — OutfitKit asume que el host define sus ion-*
// (convención de `lib/ionic-wc.ts`).
//
// Si `ion-button` (o cualquier ion-* que un ok-* renderiza) se cae de
// `registerOutfitkitIonicDeps()`, TODAS las acciones de TODOS los módulos se vuelven inertes a la
// vez: el botón recibe el clic semántico pero su handler no dispara, no abre diálogo, no navega y
// no da error — justo el patrón transversal de #754. Este test ancla la cadena en un sitio para
// que no vuelva a romperse en silencio.
//
// Verificación por texto del fuente (mismo patrón que `module-host.test.ts`): el registro global
// de customElements se filtra entre tests de componente (otros suites montan ion-* vía @ionic/vue),
// así que un check de `customElements.get` en runtime no distinguiría «el shell lo define» de «otro
// test lo definió». El fuente sí.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('./ionic-wc.ts', import.meta.url), 'utf8');

// Los tags de @ionic/core que `registerOutfitkitIonicDeps` debe PASAR AL ARRAY de
// defineCustomElement: son los que ok-data-table y los formularios de módulo renderizan POR
// DENTRO y asumen del host. ion-button = Añadir/Editar/acción de fila (el contrato más cargado de
// #754); ion-input/ion-select = formularios proyectados; ion-checkbox = selección + celdas
// imperativas; ion-modal = diálogos; ion-card* = vista tarjetas; ion-toast/ion-alert/ion-action-sheet
// = feedback; ion-icon = pictogramas; ion-searchbar = buscador.
// ion-spinner = acción de fila en curso (ok-data-table) y celda «instalando…» de AppsPage, que lo
// crea con `document.createElement` (hub#1129).
const REQUIRED_DEPS = [
  'ionButton', 'ionIcon', 'ionInput', 'ionSearchbar', 'ionSelect', 'ionSelectOption',
  'ionModal', 'ionActionSheet', 'ionToast', 'ionAlert',
  'ionCard', 'ionCardHeader', 'ionCardContent', 'ionCheckbox', 'ionSpinner',
];

describe('registerOutfitkitIonicDeps — la cadena que hace clicables los botones de los módulos (#754)', () => {
  it('importa cada ion-* que ok-data-table y los formularios de módulo asumen del host', () => {
    for (const dep of REQUIRED_DEPS) {
      expect(
        source,
        `${dep} debe importarse de @ionic/core — sin él, una superficie transversal de módulos es inerte`,
      ).toContain(`defineCustomElement as ${dep}`);
    }
  });

  it('pasa CADA dependencia al array que la función registra (importar no basta, hay que definir)', () => {
    // El array es lo que `forEach((def) => def())` recorre. Un import sin uso (tree-shaken o
    // olvidado) dejaría el tag sin definir → botones inertes sin error. Este check fuerza a que
    // cada dep importada aparezca TAMBIÉN en el array de registro.
    const arrayStart = source.indexOf('[');
    const arrayEnd = source.indexOf('].forEach');
    expect(arrayStart, 'la función debe tener un array de dependencias').toBeGreaterThan(-1);
    expect(
      arrayEnd,
      'el array debe pasarse a forEach para definir los custom elements',
    ).toBeGreaterThan(arrayStart);
    const arrayBody = source.slice(arrayStart, arrayEnd);
    for (const dep of REQUIRED_DEPS) {
      expect(
        arrayBody,
        `${dep} debe estar en el array de registro, no solo importada — sin definirla el botón es inerte (#754)`,
      ).toContain(dep);
    }
  });

  it('lista `ion-button`: el elemento detrás del «Añadir», «Editar» y cada acción de fila', () => {
    // Si un refactor reordena o pierde ion-button, este check lo caza antes de que llegue a la
    // demo. Sin ion-button registrado por el shell, el clic de Añadir/Editar/acción de fila llega
    // al botón pero su handler @click de Lit no dispara — exactamente «operativo e inerte» de #754.
    expect(source).toContain('ionButton');
    const arrayStart = source.indexOf('[');
    const arrayEnd = source.indexOf('].forEach');
    expect(source.slice(arrayStart, arrayEnd)).toContain('ionButton');
  });
});
