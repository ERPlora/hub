// @vitest-environment happy-dom
// **Settings → Hub lets the owner see and change the business TIMEZONE** (hub#1154).
//
// The setting existed and worked everywhere except where a human could reach it: the runtime
// resolved it, the flow kernel read it as the clock for a `cron` trigger, and modules got it as
// `context.timezone` — but the screen never showed it, so the only way to fix a wrong one was a
// `PUT /api/settings` by hand. In Spain that is not a corner case: the country has TWO zones, and
// a hub in the Canaries with `country_code = ES` gets deduced into `Europe/Madrid`, one hour off,
// forever.
//
// 🔴 Note for whoever runs this: THIS MACHINE IS IN `Europe/Madrid`. Every case below drives the
// screen with `Atlantic/Canary`, on purpose — an assertion written around Madrid would stay green
// against a screen that ignored the setting entirely, which is exactly the bug being fixed.
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ hash: '#hub', query: {} }),
}));
vi.mock('../lib/nav', () => ({ moduleNav: ref([]) }));

const updateHubSettings = vi.fn().mockResolvedValue({});
const hubSettings = ref<Record<string, unknown>>({});
vi.mock('../lib/hub-settings', () => ({
  hubSettings,
  // Lo que el runtime YA resolvió. Deliberadamente Madrid: es el reloj equivocado para este hub,
  // así la pantalla tiene que llegar a Canarias por el ajuste y no por el entorno.
  hubTimezone: () => 'Europe/Madrid',
  getHubSettings: vi.fn().mockResolvedValue({}),
  updateHubSettings,
}));

// The RESOLVED zone comes back from the runtime, which is the only thing that knows how to deduce
// it. The screen must ask again after saving — otherwise modules and shell keep the old clock
// until the next boot, and the owner who just fixed the Canaries still sees Madrid time.
const refreshHubTimezone = vi.fn().mockResolvedValue('Atlantic/Canary');
// Only this one export is swapped: `SettingsPage` pulls a dozen things from `lib/runtime`, and a
// hand-written mock of the whole module turns any future import into a timeout instead of a
// failed assertion — which is what it did the first time this file ran.
vi.mock('../lib/runtime', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  refreshHubTimezone,
  // El cliente real abre un WebSocket al arrancar; aquí solo se le pasa a `refreshSetupStatus`,
  // que está mockeado. Sin esto el guardado se va por el `catch` y el fallo aparenta ser de la
  // pantalla en vez de del banco de pruebas.
  getClient: () => ({}),
}));

vi.mock('../lib/session', () => ({ isAdmin }));
const isAdmin = ref(true);
vi.mock('../lib/api-docs', () => ({ apiDocsEnabled: ref(false) }));
vi.mock('../lib/device', () => ({ isTauri: () => false }));
vi.mock('../lib/toast', () => ({ toastSuccess: vi.fn(), toastError: vi.fn() }));
vi.mock('../lib/money', () => ({ publishHubCurrency: vi.fn() }));
vi.mock('../lib/setup-status', () => ({ refreshSetupStatus: vi.fn().mockResolvedValue({}) }));

const i18n = createI18n({
  legacy: false,
  locale: 'es',
  missingWarn: false,
  fallbackWarn: false,
  // Las cadenas REALES de la pantalla: con `messages: {}` cada `t()` devuelve su propia clave, así
  // que una fila que no interpolara nada pasaría igual. Aquí la etiqueta tiene que traer la zona.
  messages: {
    es: {
      settings: {
        timezone: 'Zona horaria',
        timezoneDesc: 'Zona horaria para fechas y horarios',
        timezoneAuto: 'Automática (según el país)',
        timezoneAutoNow: 'Automática · {zone}, {time}',
        timezoneOptionNow: '{zone} · {time}',
      },
    },
  },
});

const PASSTHROUGH = { template: '<div><slot /></div>' };

async function mountSettings() {
  const SettingsPage = (await import('./SettingsPage.vue')).default;
  return mount(SettingsPage, {
    shallow: true,
    global: {
      plugins: [i18n],
      stubs: { AppPage: PASSTHROUGH, IonCard: PASSTHROUGH, IonCardContent: PASSTHROUGH },
      // Los stubs de Ionic no pintan su `<slot>`, y la fila vive dentro de `ion-list` > `ion-item`,
      // con sus opciones dentro de `ion-select`. Sin esto el test diría «no hay fila» pasara lo que
      // pasara — verde antes de escribir la pantalla y verde después de borrarla.
      renderStubDefaultSlot: true,
    },
  });
}

/** The zone select, found by its own hook so a reshuffle of the Hub tab does not silently pass. */
function zoneSelect(wrapper: Awaited<ReturnType<typeof mountSettings>>) {
  return wrapper.find('.hub-timezone');
}

/** Elige una opción como lo hace Ionic de verdad: `ionChange` con su `CustomEvent`. */
async function pickZone(wrapper: Awaited<ReturnType<typeof mountSettings>>, value: string) {
  (wrapper.getComponent('.hub-timezone') as VueWrapper).vm.$emit(
    'ionChange',
    new CustomEvent('ionChange', { detail: { value } }),
  );
  // `persistHubSettings` encadena PUT → refresco de setup → toast antes de republicar la zona:
  // contar ticks a mano se queda corto y el fallo parece de la pantalla, no del test.
  await flushPromises();
}

// Compilar `SettingsPage.vue` (1.100 líneas y su árbol de imports) tarda más que el timeout por
// defecto de un test. Se paga aquí, una vez, para que el primer caso no falle por el reloj.
beforeAll(async () => {
  await import('./SettingsPage.vue');
}, 60_000);

beforeEach(() => {
  updateHubSettings.mockClear();
  refreshHubTimezone.mockClear();
  isAdmin.value = true;
  hubSettings.value = { country_code: 'ES', timezone: null };
});

describe('Ajustes → Hub · zona horaria', () => {
  it('pinta la fila con las zonas del país, no una lista de todo el mundo', async () => {
    const wrapper = await mountSettings();
    const select = zoneSelect(wrapper);
    expect(select.exists(), 'la fila de zona horaria se pinta en la pestaña Hub').toBe(true);

    const values = select.findAll('ion-select-option-stub').map((o) => o.attributes('value'));
    // `auto` es el default y tiene que poder recuperarse; las dos zonas de España son las que
    // hacen falta para decidir, y no hay 400 opciones que buscar.
    expect(values).toEqual(['auto', 'Europe/Madrid', 'Atlantic/Canary']);
  });

  it('con el ajuste sin declarar, la fila dice AUTOMÁTICA (es el default y hay que poder volver)', async () => {
    const wrapper = await mountSettings();
    expect(zoneSelect(wrapper).attributes('modelvalue')).toBe('auto');
  });

  it('con una zona declarada, la fila la muestra — aunque no sea la del país deducido', async () => {
    hubSettings.value = { country_code: 'ES', timezone: 'Atlantic/Canary' };
    const wrapper = await mountSettings();
    expect(zoneSelect(wrapper).attributes('modelvalue')).toBe('Atlantic/Canary');
  });

  it('elegir una zona la GUARDA y vuelve a preguntar el reloj resuelto al runtime', async () => {
    const wrapper = await mountSettings();
    await pickZone(wrapper, 'Atlantic/Canary');

    expect(updateHubSettings).toHaveBeenCalledWith({ timezone: 'Atlantic/Canary' });
    // Sin esto, `globalThis.__erploraTimezone` se queda en Madrid hasta el siguiente arranque y
    // los módulos siguen agendando con el reloj viejo justo después de corregirlo.
    expect(refreshHubTimezone, 'hay que republicar la zona resuelta tras guardar').toHaveBeenCalled();
  });

  it('volver a AUTOMÁTICA guarda null, no la cadena «auto»', async () => {
    hubSettings.value = { country_code: 'ES', timezone: 'Atlantic/Canary' };
    const wrapper = await mountSettings();
    await pickZone(wrapper, 'auto');

    // `null` es lo que el runtime entiende por «dedúcela del país». Mandar `"auto"` sería una zona
    // IANA inválida y el PUT lo rechazaría con un 422.
    expect(updateHubSettings).toHaveBeenCalledWith({ timezone: null });
  });

  it('nunca pierde la zona que el hub ya tenía por API, aunque el país no la liste', async () => {
    hubSettings.value = { country_code: 'ES', timezone: 'America/New_York' };
    const wrapper = await mountSettings();
    const values = zoneSelect(wrapper)
      .findAll('ion-select-option-stub')
      .map((o) => o.attributes('value'));
    expect(values).toContain('America/New_York');
    expect(zoneSelect(wrapper).attributes('modelvalue')).toBe('America/New_York');
  });

  it('a quien no es admin le enseña la zona, pero no un selector', async () => {
    isAdmin.value = false;
    hubSettings.value = { country_code: 'ES', timezone: 'Atlantic/Canary' };
    const wrapper = await mountSettings();
    expect(zoneSelect(wrapper).exists(), 'sin selector para no-admin').toBe(false);
    expect(wrapper.html()).toContain('Atlantic/Canary');
  });
});
