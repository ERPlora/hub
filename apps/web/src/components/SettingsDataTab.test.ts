// @vitest-environment happy-dom
import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

// Los dos paneles se mockean: aquí solo se prueba QUÉ enseña el segmento. Además, importarlos de
// verdad arrastraría lib/icons.ts (`~icons/<set>/<name>?raw`, virtual de unplugin-icons), que no
// resuelve en el pipeline web de vitest.
vi.mock('./ImportPanel.vue', () => ({
  default: { name: 'ImportPanel', template: '<div />' },
}));
vi.mock('./ExportPanel.vue', () => ({
  default: { name: 'ExportPanel', template: '<div />' },
}));

import SettingsDataTab from './SettingsDataTab.vue';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      settings: { dataImport: 'Import', dataExport: 'Export' },
    },
  },
});

function mountTab() {
  // shallow: los hijos (ion-*, ImportPanel, ExportPanel) se stubean; aquí solo se prueba
  // QUÉ panel muestra el segmento, no lo que hace cada panel por dentro.
  // renderStubDefaultSlot: sin él, el stub de <ion-segment> no pinta su slot y los botones del
  // segmento no llegarían al DOM del test.
  return mount(SettingsDataTab, {
    shallow: true,
    global: { plugins: [i18n], renderStubDefaultSlot: true },
  });
}

const importPanel = (w: ReturnType<typeof mountTab>) => w.find('import-panel-stub');
const exportPanel = (w: ReturnType<typeof mountTab>) => w.find('export-panel-stub');

describe('SettingsDataTab', () => {
  it('arranca en «importar»: muestra el panel de import y NO el de export', () => {
    const w = mountTab();
    expect(w.find('ion-segment-stub').attributes('value')).toBe('import');
    expect(importPanel(w).exists()).toBe(true);
    expect(exportPanel(w).exists()).toBe(false);
  });

  it('ofrece un segmento con exactamente dos opciones: import y export', () => {
    const w = mountTab();
    const values = w.findAll('ion-segment-button-stub').map((b) => b.attributes('value'));
    expect(values).toEqual(['import', 'export']);
  });

  it('al elegir «exportar» muestra el panel de export y oculta el de import', async () => {
    const w = mountTab();
    await w.findComponent({ name: 'IonSegment' }).vm.$emit('ionChange', {
      detail: { value: 'export' },
    });
    expect(exportPanel(w).exists()).toBe(true);
    expect(importPanel(w).exists()).toBe(false);
  });

  it('vuelve a «importar» al elegirlo de nuevo', async () => {
    const w = mountTab();
    const seg = w.findComponent({ name: 'IonSegment' });
    await seg.vm.$emit('ionChange', { detail: { value: 'export' } });
    await seg.vm.$emit('ionChange', { detail: { value: 'import' } });
    expect(importPanel(w).exists()).toBe(true);
    expect(exportPanel(w).exists()).toBe(false);
  });
});
