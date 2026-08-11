// @vitest-environment happy-dom
// **La fila «Plantilla de tique» lleva a algún sitio** (hub#761).
//
// El defecto no era de render: la fila se pintaba perfecta, con su icono, su título, su descripción
// y su chevron de `detail`. Se pintaba como un botón y **no tenía `@click`**. Al pulsarla no pasaba
// nada — ni navegación, ni modal, ni un aviso: el árbol de accesibilidad y la URL quedaban idénticos.
//
// Por eso este test **pulsa**, no mira el markup. Un test que comprobara que la fila existe habría
// pasado en verde durante todo el tiempo que el botón estuvo muerto, que es exactamente lo que pasó.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

// El registro de iconos importa ~70 SVG por `~icons/…?raw`, ids VIRTUALES que este entorno deniega
// (`Denied ID ~icons/ion/add-outline?raw`). Montar una VISTA los arrastra aunque sus hijos estén
// stubbeados —el import ocurre igual— así que se sustituye el registro entero, que es de quien
// cuelgan todos. Los iconos tienen su propio test (`lib/icons.test.ts`), que sí los carga de verdad.
vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

const push = vi.fn();
const moduleNav = ref<{ path: string }[]>([]);

vi.mock('vue-router', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  useRoute: () => ({ hash: '#tickets', query: {} }),
}));
vi.mock('../lib/nav', () => ({ moduleNav }));
vi.mock('../lib/hub-settings', () => ({
  hubSettings: ref({}),
  getHubSettings: vi.fn().mockResolvedValue({}),
  updateHubSettings: vi.fn(),
}));
vi.mock('../lib/session', () => ({ isAdmin: ref(true) }));
vi.mock('../lib/api-docs', () => ({ apiDocsEnabled: ref(false) }));
vi.mock('../lib/device', () => ({ isTauri: () => false }));
vi.mock('../lib/toast', () => ({ toastSuccess: vi.fn(), toastError: vi.fn() }));
vi.mock('../lib/money', () => ({ publishHubCurrency: vi.fn() }));

const i18n = createI18n({
  legacy: false,
  locale: 'es',
  missingWarn: false,
  fallbackWarn: false,
  messages: { es: {} },
});

/** Stub que SÍ pinta lo que envuelve. */
const PASSTHROUGH = { template: '<div><slot /></div>' };

async function mountSettings() {
  const SettingsPage = (await import('./SettingsPage.vue')).default;
  return mount(SettingsPage, {
    // `shallow` stubbea a los hijos (Ionic incluido) para que esto pruebe la PANTALLA y no Ionic…
    shallow: true,
    global: {
      plugins: [i18n],
      // …salvo los CONTENEDORES: un stub no pinta su `<slot>`, así que con el layout y la tarjeta
      // stubbeados del todo la fila no llega a existir y el test pasaría a decir «no hay fila» en
      // vez de probarla. Se abren solo esos tres; el resto de Ionic sigue stubbeado.
      stubs: { AppPage: PASSTHROUGH, IonCard: PASSTHROUGH, IonCardContent: PASSTHROUGH },
    },
  });
}

beforeEach(() => {
  push.mockClear();
  moduleNav.value = [];
});

describe('Ajustes → Tiques · «Plantilla de tique»', () => {
  it('con la app de impresión instalada, pulsarla ABRE sus ajustes', async () => {
    moduleNav.value = [{ path: '/m/sales' }, { path: '/m/printing' }];
    const wrapper = await mountSettings();

    const row = wrapper.find('.receipt-template');
    expect(row.exists(), 'la fila se pinta en la pestaña Tiques').toBe(true);

    await row.trigger('click');

    // Esto es lo que NO pasaba: la URL y el árbol quedaban idénticos tras el clic.
    expect(push, 'pulsar la fila tiene que llevar a alguna parte').toHaveBeenCalledTimes(1);
    expect(push).toHaveBeenCalledWith('/m/printing/printing');
  });

  it('sin la app instalada, lleva a instalarla en vez de no hacer nada', async () => {
    moduleNav.value = [{ path: '/m/sales' }];
    const wrapper = await mountSettings();

    await wrapper.find('.receipt-template').trigger('click');

    expect(push).toHaveBeenCalledWith('/apps');
  });

  it('nunca se queda muda: pulsarla SIEMPRE navega', async () => {
    // La garantía de fondo, independiente de qué haya instalado. Si alguien vuelve a quitar el
    // manejador, este test cae con los dos casos de arriba y con este.
    for (const nav of [[], [{ path: '/m/printing' }], [{ path: '/m/printing_labels' }]]) {
      push.mockClear();
      moduleNav.value = nav;
      const wrapper = await mountSettings();
      await wrapper.find('.receipt-template').trigger('click');
      expect(push, `sin destino con moduleNav=${JSON.stringify(nav)}`).toHaveBeenCalledTimes(1);
    }
  });
});
