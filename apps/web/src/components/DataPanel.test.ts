// @vitest-environment happy-dom
// Contrato de la pestaña Ajustes › Datos (decisión humano 2026-07-17): un sub-segment
// Importar/Exportar (en vez de apilar los dos paneles). Importar es la vista por defecto —
// es lo que necesita el 99% de las veces; exportar se descubre aquí, detrás del segment.
import { describe, it, expect, vi } from 'vitest';
import { mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

// Los paneles hijos arrastran HubIcon → `~icons/…?raw` (denegado en test). Aquí solo probamos el
// toggle del segment, así que los stubeamos; findComponent los resuelve por identidad del módulo.
vi.mock('./ImportPanel.vue', () => ({ default: { name: 'ImportPanel', template: '<div />' } }));
vi.mock('./ExportPanel.vue', () => ({ default: { name: 'ExportPanel', template: '<div />' } }));

import DataPanel from './DataPanel.vue';
import ImportPanel from './ImportPanel.vue';
import ExportPanel from './ExportPanel.vue';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: { settings: { dataImport: 'Import', dataExport: 'Export' } } },
});

function mountPanel(initial?: 'import' | 'export') {
  // shallow: los ion-* y los paneles hijos se stubean; aquí se prueba el toggle, no su interior.
  return mount(DataPanel, {
    props: { initial },
    shallow: true,
    global: { plugins: [i18n], renderStubDefaultSlot: true },
  });
}

describe('DataPanel', () => {
  it('pinta el segment y por defecto muestra Importar (no Exportar)', () => {
    const w = mountPanel();
    expect(w.find('[data-testid="data-view-segment"]').exists()).toBe(true);
    expect(w.findComponent(ImportPanel).exists()).toBe(true);
    expect(w.findComponent(ExportPanel).exists()).toBe(false);
  });

  it('cambiar el segment a Exportar muestra ExportPanel y oculta ImportPanel', async () => {
    const w = mountPanel();
    (w.getComponent('[data-testid="data-view-segment"]') as VueWrapper).vm.$emit(
      'ionChange',
      new CustomEvent('ionChange', { detail: { value: 'export' } }),
    );
    await w.vm.$nextTick();
    expect(w.findComponent(ExportPanel).exists()).toBe(true);
    expect(w.findComponent(ImportPanel).exists()).toBe(false);
  });

  it('respeta la vista inicial pasada por prop', () => {
    const w = mountPanel('export');
    expect(w.findComponent(ExportPanel).exists()).toBe(true);
    expect(w.findComponent(ImportPanel).exists()).toBe(false);
  });
});
