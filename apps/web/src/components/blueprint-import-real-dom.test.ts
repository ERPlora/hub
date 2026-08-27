// @vitest-environment happy-dom
//
// 🔴 hub#1120 — las dos puertas de «empieza con una plantilla», probadas SOBRE LOS COMPONENTES DE
// VERDAD.
//
// Los tests de `ImportPanel.test.ts` y `BlueprintHeroCard.test.ts` montan con `shallow: true`, así
// que `ok-data-table` y `ion-button` son SELLOS: el primero acepta cualquier prop y no pinta nada,
// el segundo reemite el clic sin pasar por Ionic. Eso les deja comprobar el cableado —y lo hacen
// bien—, pero significa que los dos síntomas que se reportaron desde producción («la tabla está en
// el DOM y no pinta ni una fila», «pulsar no dispara nada») **no pueden ponerlos en rojo**: no hay
// tabla que pintar ni botón que pulsar.
//
// Este fichero cierra ese hueco y solo eso: registra el `ok-data-table` real de OutfitKit, monta
// sin sellos y mira lo que acaba EN PANTALLA (el shadow root del componente) y lo que sale por la
// red al pulsar de verdad. Es deliberadamente corto — son los dos hechos que el usuario vive.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

// El Web Component REAL, el mismo que `main.ts` registra en el arranque del shell.
import '@erplora/outfitkit/ok-data-table';

const fetchBlueprintCatalog = vi.fn();
const downloadBlueprint = vi.fn();
const inspectBlueprint = vi.fn();
const importBlueprint = vi.fn();
const fetchImportReport = vi.fn();

vi.mock('../lib/runtime', async () => {
  const actual = await vi.importActual<typeof import('../lib/runtime')>('../lib/runtime');
  return {
    ...actual,
    fetchBlueprintCatalog: (...a: unknown[]) => fetchBlueprintCatalog(...a),
    downloadBlueprint: (...a: unknown[]) => downloadBlueprint(...a),
    inspectBlueprint: (...a: unknown[]) => inspectBlueprint(...a),
    importBlueprint: (...a: unknown[]) => importBlueprint(...a),
    fetchImportReport: (...a: unknown[]) => fetchImportReport(...a),
  };
});
vi.mock('../lib/nav', () => ({ refreshModuleNav: vi.fn() }));
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }));
// HubIcon hornea los SVG vía `~icons/…?raw`, que el entorno de test deniega. Aquí se mira la tabla
// y el botón, no los iconos.
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import ImportPanel from './ImportPanel.vue';
import BlueprintHeroCard from './BlueprintHeroCard.vue';
import { setUser } from '../lib/session';
import es from '../i18n/locales/es';
import type { CatalogBlueprint } from '../lib/runtime';
import type { SetupItem, SetupStatus } from '../lib/setup-status';

const i18n = createI18n({
  legacy: false,
  locale: 'es',
  missingWarn: false,
  fallbackWarn: false,
  messages: { es },
});

function blueprint(over: Partial<CatalogBlueprint> = {}): CatalogBlueprint {
  return {
    slug: 'restaurante',
    name: 'Restaurante',
    description: 'Bar y restaurante',
    locale: 'es',
    country: 'ES',
    latest_version: '1.0.0',
    latest_sha256: 'abc',
    size_bytes: 2048,
    downloads: 7,
    ...over,
  };
}

const CATALOGUE = [
  blueprint(),
  blueprint({ slug: 'peluqueria', name: 'Peluquería', description: 'Salón' }),
  blueprint({ slug: 'barberia', name: 'Barbería', description: 'Barbería' }),
  blueprint({ slug: 'pizzeria', name: 'Pizzería', description: 'Pizzería' }),
];

/** Un negocio recién creado: el ítem `apps` del core todavía sin marcar. */
function emptyBusiness(): SetupStatus {
  const apps: SetupItem = {
    key: 'apps',
    source: 'core',
    moduleId: null,
    state: 'pending',
    required: true,
    level: 'functional',
    title: 'Tus apps',
    description: '',
    icon: 'grid-outline',
    route: '/apps',
    order: 10,
    actions: ['template', 'catalog'],
    actionable: true,
    origin: 'user',
  };
  return { items: [apps], total: 1, pending: 1, unavailable: 0, blockingPending: 0, done: 0 };
}

beforeEach(() => {
  fetchBlueprintCatalog.mockReset().mockResolvedValue(CATALOGUE);
  downloadBlueprint.mockReset().mockResolvedValue(new Blob(['zip']));
  inspectBlueprint
    .mockReset()
    .mockResolvedValue({ ok: true, upload_id: 'up-1', manifest: { modules: [], sections: [] } });
  importBlueprint.mockReset().mockResolvedValue({ sections: [], installed_modules: [] });
  fetchImportReport.mockReset().mockResolvedValue(null);
  setUser({
    id: 'u-1',
    name: 'Owner',
    email: 'owner@example.com',
    role: 'owner',
    permissions: ['*'],
  });
  document.body.innerHTML = '';
});

describe('Ajustes › Datos › Importar — la tabla de plantillas PINTA', () => {
  it('pone en pantalla una tarjeta por plantilla publicada, con su acción', async () => {
    // El síntoma reportado era este y no otro: `ok-data-table` presente en el DOM y ni una fila
    // dentro. Con el sello de `shallow` nadie podía verlo, porque no había nada que pintar.
    mount(ImportPanel, { attachTo: document.body, global: { plugins: [i18n] } });
    await flushPromises();
    await flushPromises();

    const table = document.querySelector('ok-data-table');
    expect(table, 'la tabla del catálogo no llegó al DOM').toBeTruthy();

    const painted = table!.shadowRoot;
    expect(painted, 'el Web Component no se materializó: shadow root vacío').toBeTruthy();
    // Una tarjeta por plantilla: el catálogo entero, no un subconjunto.
    expect(painted!.querySelectorAll('ion-card').length).toBe(CATALOGUE.length);
    // Y con su nombre dentro, que es lo que el dueño reconoce.
    expect(painted!.textContent).toContain('Restaurante');
    expect(painted!.textContent).toContain('Peluquería');
    // El buscador del catálogo también es del componente: sin él la lista no se puede filtrar.
    expect(painted!.querySelector('ion-searchbar')).toBeTruthy();
  });

  it('sin plantillas publicadas pinta el estado vacío, nunca una tabla muda', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    mount(ImportPanel, { attachTo: document.body, global: { plugins: [i18n] } });
    await flushPromises();
    await flushPromises();

    const painted = document.querySelector('ok-data-table')!.shadowRoot!;
    expect(painted.querySelectorAll('ion-card').length).toBe(0);
    expect(painted.textContent).toContain(es.importPage.catalogEmpty);
  });
});

describe('El hero del dashboard — «Usar esta» DISPARA', () => {
  it('un clic real sobre el ion-button de Ionic arranca descarga → inspección → import', async () => {
    // El botón es un `ion-button` de verdad: el clic entra por el host y tiene que llegar al
    // handler. Con el sello de `shallow` esto no se probaba — se probaba el sello.
    mount(BlueprintHeroCard, {
      props: { status: emptyBusiness() },
      attachTo: document.body,
      global: { plugins: [i18n] },
    });
    await flushPromises();

    const cta = document.querySelector<HTMLElement>('[data-testid="hero-use"]');
    expect(cta, 'el CTA del hero no llegó al DOM').toBeTruthy();
    expect(cta!.tagName).toBe('ION-BUTTON');
    expect(cta!.hasAttribute('disabled')).toBe(false);

    cta!.dispatchEvent(new Event('click', { bubbles: true, composed: true }));
    await flushPromises();

    expect(downloadBlueprint).toHaveBeenCalledWith('restaurante');
    expect(inspectBlueprint).toHaveBeenCalledTimes(1);
    expect(importBlueprint).toHaveBeenCalledTimes(1);
  });
});
