// La nav de módulos se refresca GLOBALMENTE al instalarse un módulo (WS `module.installed`).
//
// El fallo real (2026-08-09, en vivo): el asistente instaló taxes+inventory desde el drawer —
// runtime OK, módulos activos — y la lista de apps/nav no se enteró: el ÚNICO oyente del evento
// vivía en AppsPage, montada solo en /apps. Instalar desde el drawer (o desde OTRO dispositivo)
// con cualquier otra pantalla abierta dejaba el shell ciego hasta recargar.
//
// Contrato (patrón assistant-reads-the-query): App.vue —siempre montado— escucha
// `module.installed` y llama a refreshModuleNav().
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const app = readFileSync(new URL('../App.vue', import.meta.url), 'utf8');

describe('module.installed → nav global', () => {
  it('App.vue escucha module.installed', () => {
    expect(app).toContain("'module.installed'");
  });
  it('y refresca la nav al recibirlo', () => {
    const idx = app.indexOf("'module.installed'");
    const after = app.slice(idx, idx + 400);
    expect(after).toContain('refreshModuleNav');
  });
});
