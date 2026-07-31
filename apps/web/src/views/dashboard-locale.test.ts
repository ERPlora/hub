// #273 — «La fecha mezcla español e inglés»: el label «Hoy» del dashboard usaba
// `toLocaleDateString(undefined, …)`, que cae al locale del NAVEGADOR/SO, no al de la app. Con la
// app en `es` y el navegador en `en-US` salía «lunes, July 2026». El resto del dashboard ya usa
// `locale.value === 'en' ? 'en-GB' : 'es-ES'`; este test fija que el label de hoy haga lo mismo.
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
    expect(block).toContain("locale.value === 'en' ? 'en-GB' : 'es-ES'");
  });

  it('ModulePlanPanel no usa `undefined` como locale (mismo bug en fmtDate)', () => {
    const start = modulePlan.indexOf('function fmtDate');
    const end = modulePlan.indexOf('}', start) + 1;
    const block = modulePlan.slice(start, end);
    expect(block, 'no se encontró fmtDate').toBeTruthy();
    expect(block, 'fmtDate(undefined) mezcla idiomas igual que todayLabel').not.toContain('toLocaleDateString(undefined');
  });
});
