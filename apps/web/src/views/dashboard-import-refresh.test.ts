// #267 — «Dashboard incorrecto después de importar el blueprint»: tras un import, ImportPanel
// solo refrescaba el menú (refreshModuleNav) y navegaba a /dashboard. DashboardPage cargaba sus
// widgets + actividad SOLO en onMounted; al reutilizar Vue la instancia ya montada, no refrescaba y
// mostraba los KPIs y el catálogo de widgets PRE-import. El fix: ImportPanel emite un evento global
// tras importar; DashboardPage lo escucha y recarga widgets + actividad + salud del sistema.
//
// Patrón del hub (apps-core.test.ts): lectura del source del SFC + aserción sobre el contrato.
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const importPanel = readFileSync(new URL('../components/ImportPanel.vue', import.meta.url), 'utf8');
const dashboard = readFileSync(new URL('./DashboardPage.vue', import.meta.url), 'utf8');

describe('el dashboard se refresca tras importar un blueprint (#267)', () => {
  it('ImportPanel emite un evento global al terminar el import con éxito', () => {
    // Localiza doImport y verifica que, tras refreshModuleNav, despacha un evento que avise del cambio.
    const start = importPanel.indexOf('async function doImport');
    const end = importPanel.indexOf('\n}', start) + 2;
    const block = importPanel.slice(start, end);
    expect(block, 'no se encontró doImport').toBeTruthy();
    expect(block).toContain('refreshModuleNav');
    // El evento avisa de que el conjunto de módulos/datos cambió (el dashboard lo escucha).
    expect(block, 'doImport no avisa del cambio de módulos → el dashboard no se entera').toMatch(
      /dispatchEvent\(.*[Ee]vent\(['"]erp:modules-changed['"]/,
    );
  });

  it('DashboardPage escucha ese evento y recarga widgets + actividad', () => {
    // Debe añadir un listener para el evento que emite ImportPanel, y en su handler recargar.
    expect(dashboard, 'DashboardPage no escucha el evento de módulos cambiados').toContain('erp:modules-changed');
    // El handler debe recargar los widgets (catálogo + KPIs) y la actividad, no solo una de las dos.
    const listenerBlock = dashboard.slice(
      dashboard.indexOf('erp:modules-changed') - 200,
      dashboard.indexOf('erp:modules-changed') + 400,
    );
    expect(listenerBlock, 'el handler debe recargar los widgets').toMatch(/loadWidgets\(\)/);
    expect(listenerBlock, 'el handler debe recargar la actividad').toMatch(/loadActivity\(\)/);
  });
});
