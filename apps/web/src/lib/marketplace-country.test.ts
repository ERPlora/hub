// Guard estructural de ADR-0062: el E2E real cubre el Hub registrado; aquí fijamos la excepción
// deliberada del demo (catálogo público sin filtro) y los ISO añadidos al selector de ajustes.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

function view(name: string): string {
  return readFileSync(fileURLToPath(new URL(`../views/${name}`, import.meta.url)), 'utf8');
}

describe('selector de país del marketplace', () => {
  it('no muestra un filtro engañoso en demo', () => {
    expect(view('AppsPage.vue')).toContain(`v-if="tab !== 'mine' && !config.demo"`);
  });

  it('ofrece Alemania e Italia en el ajuste fiscal del Hub', () => {
    const settings = view('SettingsPage.vue');
    expect(settings).toContain('<ion-select-option value="DE">');
    expect(settings).toContain('<ion-select-option value="IT">');
  });
});
