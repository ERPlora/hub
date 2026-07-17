// @vitest-environment happy-dom
// Contrato del paso «elegir fuente» del ImportPanel tras la simplificación (decisión humano
// 2026-07-17): el «descargar de la nube» dejaba de ser un botón que despliega una lista. Ahora
// el catálogo de la nube se carga solo al entrar y se pinta como UNA CARD por blueprint, más una
// card secundaria «subir desde archivo». Así el usuario SIEMPRE ve qué puede cargar.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const fetchBlueprintCatalog = vi.fn();
const downloadBlueprint = vi.fn();

vi.mock('../lib/runtime', () => ({
  fetchBlueprintCatalog: (...a: unknown[]) => fetchBlueprintCatalog(...a),
  downloadBlueprint: (...a: unknown[]) => downloadBlueprint(...a),
  inspectBlueprint: vi.fn(),
  importBlueprint: vi.fn(),
  sectionStatusInfo: vi.fn(() => ({ color: '', label: '' })),
}));
vi.mock('../lib/session', () => ({ isAdmin: ref(true) }));
vi.mock('../lib/nav', () => ({ refreshModuleNav: vi.fn() }));
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }));
// HubIcon hornea todos los SVG del shell vía `~icons/…?raw`, que el entorno de test deniega.
// Aquí probamos el contrato del paso pick, no los iconos: lo stubeamos.
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import ImportPanel from './ImportPanel.vue';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: {} },
});

function mountPanel() {
  return mount(ImportPanel, { shallow: true, global: { plugins: [i18n], renderStubDefaultSlot: true } });
}

beforeEach(() => {
  fetchBlueprintCatalog.mockReset();
  downloadBlueprint.mockReset();
});

describe('ImportPanel · paso pick', () => {
  it('carga el catálogo de la nube al montar y pinta una card por blueprint', async () => {
    fetchBlueprintCatalog.mockResolvedValue([
      { slug: 'rest', name: 'Restaurante', description: 'TPV', locale: 'es', latest_version: '1.0.0' },
      { slug: 'beauty', name: 'Peluquería', description: '', locale: 'es', latest_version: '2.1.0' },
    ]);
    const w = mountPanel();
    await flushPromises();
    expect(fetchBlueprintCatalog).toHaveBeenCalledTimes(1);
    expect(w.find('[data-testid="import-cloud-item-rest"]').exists()).toBe(true);
    expect(w.find('[data-testid="import-cloud-item-beauty"]').exists()).toBe(true);
  });

  it('SIEMPRE ofrece la card «subir desde archivo», haya o no blueprints', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    const w = mountPanel();
    await flushPromises();
    expect(w.find('[data-testid="import-upload-local"]').exists()).toBe(true);
    // Sin blueprints en la nube: nota de catálogo vacío, pero la card de subir sigue ahí.
    expect(w.find('[data-testid="import-cloud-empty"]').exists()).toBe(true);
  });

  it('si el catálogo falla (hub sin credencial cloud) DEGRADA en silencio, sin banner de error', async () => {
    // Regresión: la auto-carga del catálogo volcaba el fallo en el banner de error del inspector
    // de ficheros → un hub Local/dev sin credencial veía «No se pudo leer el fichero…» al entrar.
    fetchBlueprintCatalog.mockRejectedValue(new Error('hub sin credencial'));
    const w = mountPanel();
    await flushPromises();
    // NO hay banner de error (ese se reserva a fallos de inspección de un fichero elegido).
    expect(w.find('[data-testid="import-error"]').exists()).toBe(false);
    // La card de subir sigue disponible: es el fallback cuando no hay nube.
    expect(w.find('[data-testid="import-upload-local"]').exists()).toBe(true);
  });
});
