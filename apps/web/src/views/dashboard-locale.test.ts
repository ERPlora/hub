// #273 — «La fecha mezcla español e inglés»: el label «Hoy» del dashboard usaba
// `toLocaleDateString(undefined, …)`, que cae al locale del NAVEGADOR/SO, no al de la app. Con la
// app en `es` y el navegador en `en-US` salía «lunes, July 2026».
//
// hub#1212 movió el mapeo `en → en-GB` / resto `→ es-ES` de cada pantalla a `formatLocale()`
// (`lib/format-datetime.ts`), así que la regla de #273 ya no se comprueba buscando el ternario en
// el SFC —ya no existe en ninguno— sino en dos mitades: aquí, que la pantalla SIGUE pasando el
// locale de la app (y no `undefined`); y en `lib/format-datetime.test.ts`, que ese locale acaba
// siendo `en-GB`/`es-ES`. Lo que #273 protege no cambia: el idioma lo decide la app.
//
// Patrón del hub (apps-core.test.ts): se lee el source del SFC y se aserta sobre él, sin montar
// (montar requeriría mockear Ionic + vue-i18n + router para un cambio de una línea).
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const dashboard = readFileSync(new URL('./DashboardPage.vue', import.meta.url), 'utf8');
const modulePlan = readFileSync(new URL('../components/ModulePlanPanel.vue', import.meta.url), 'utf8');

describe('el formato de fecha sigue el locale de la app, no el del navegador (#273)', () => {
  it('todayLabel no usa `undefined` como locale (cae al navegador → mezcla idiomas)', () => {
    // Localiza el bloque todayLabel y verifica que no pase `undefined` a toLocaleDateString.
    const start = dashboard.indexOf('const todayLabel');
    const end = dashboard.indexOf('});', start) + '});'.length;
    const block = dashboard.slice(start, end);
    expect(block, 'no se encontró el bloque todayLabel').toBeTruthy();
    expect(block, 'toLocaleDateString(undefined) cae al locale del navegador (el bug)').not.toContain('toLocaleDateString(undefined');
  });

  it('todayLabel usa el locale de la app (en-GB / es-ES), como el resto del dashboard', () => {
    const start = dashboard.indexOf('const todayLabel');
    const end = dashboard.indexOf('});', start) + '});'.length;
    const block = dashboard.slice(start, end);
    // El ternario vive ahora en `formatLocale()`; lo que la pantalla tiene que seguir haciendo es
    // ENTREGARLE el locale de la app. Un `formatDate(...)` sin `locale:` volvería a #273 en cuanto
    // el usuario cambiase de idioma: el `computed` dejaría de depender de él y no se repintaría.
    expect(block, 'todayLabel ya no pasa el locale de la app al formateador').toContain(
      'locale: locale.value',
    );
  });

  it('ModulePlanPanel no usa `undefined` como locale (mismo bug en fmtDate)', () => {
    const start = modulePlan.indexOf('function fmtDate');
    const end = modulePlan.indexOf('}', start) + 1;
    const block = modulePlan.slice(start, end);
    expect(block, 'no se encontró fmtDate').toBeTruthy();
    expect(block, 'fmtDate(undefined) mezcla idiomas igual que todayLabel').not.toContain('toLocaleDateString(undefined');
  });
});
