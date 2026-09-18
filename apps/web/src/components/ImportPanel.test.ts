// @vitest-environment happy-dom
// Contrato del paso «elegir fuente»: el catálogo se carga al entrar y se presenta con el
// ok-data-table reutilizable (tarjetas por defecto + tabla), mientras que el fichero local sigue
// siendo una acción explícita separada.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const fetchBlueprintCatalog = vi.fn();
const downloadBlueprint = vi.fn();
const fetchImportReport = vi.fn();
const retryImport = vi.fn();

vi.mock('../lib/runtime', async () => {
  const actual = await vi.importActual<typeof import('../lib/runtime')>('../lib/runtime');
  return {
    fetchBlueprintCatalog: (...a: unknown[]) => fetchBlueprintCatalog(...a),
    downloadBlueprint: (...a: unknown[]) => downloadBlueprint(...a),
    fetchImportReport: (...a: unknown[]) => fetchImportReport(...a),
    // hub#845: the retry transport is stubbed; whether the button CAN act is real logic
    // (`retryAvailability` reads the report through the real status normalisers below).
    retryImport: (...a: unknown[]) => retryImport(...a),
    RetryRefusedError: actual.RetryRefusedError,
    inspectBlueprint: vi.fn(),
    importBlueprint: vi.fn(),
    // hub#763: estas NO se stubean — `reportWarrantsAttention` (decide si el informe recuperado se
    // muestra al montar) y `reportReason` (pinta el motivo de cada fila) dependen de su lógica real.
    sectionStatusInfo: actual.sectionStatusInfo,
    sectionDiscardCode: actual.sectionDiscardCode,
    // hub#409: esta NO se stubea — es la que decide si la fila de un módulo se pinta bloqueada o
    // roja, justo el contrato bajo prueba.
    moduleInstallStatusInfo: actual.moduleInstallStatusInfo,
  };
});

// hub#488 — los nombres humanos de las apps. Mutable por test: la mayoría no pone ninguno, que es
// el caso «no hay nombre» y debe seguir pintando el id.
const appNames = vi.hoisted(() => new Map<string, string>());
vi.mock('../lib/app-names', async () => {
  const actual = await vi.importActual<typeof import('../lib/app-names')>('../lib/app-names');
  // `appLabel` NO se stubea: la regla de «nombre o id, nunca un invento» es el contrato bajo prueba.
  return { appLabel: actual.appLabel, loadAppNames: async () => appNames };
});
// La sesión NO se stubea (hub#1120): quién puede importar es justo el contrato bajo prueba, y una
// puerta que se prueba con su propio interruptor no prueba nada. Los tests mueven la sesión REAL
// con `setUser`, la misma que escribe el login.
vi.mock('../lib/nav', () => ({ refreshModuleNav: vi.fn() }));
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }));
// HubIcon hornea todos los SVG del shell vía `~icons/…?raw`, que el entorno de test deniega.
// Aquí probamos el contrato del paso pick, no los iconos: lo stubeamos.
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import ImportPanel from './ImportPanel.vue';
import ImportPermissionsConsent from './ImportPermissionsConsent.vue';
import { importBlueprint } from '../lib/runtime';
import { setUser, type SessionUser } from '../lib/session';
// Real English catalogue: the blocked row is tested through the sentence the user reads.
import en from '../i18n/locales/en';

/** La sesión que el runtime escribe para un owner: rol + comodín (`identity::session_permissions`). */
function signInAsOwner(overrides: Partial<SessionUser> = {}): void {
  setUser({ id: 'u-1', name: 'Owner', email: 'owner@example.com', role: 'owner', permissions: ['*'], ...overrides });
}

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
  fetchImportReport.mockReset();
  retryImport.mockReset();
  appNames.clear();
  signInAsOwner();
});

describe('ImportPanel · paso pick', () => {
  it('carga el catálogo de la nube al montar y lo entrega al data-table reutilizable', async () => {
    fetchBlueprintCatalog.mockResolvedValue([
      { slug: 'rest', name: 'Restaurante', description: 'TPV', locale: 'es', latest_version: '1.0.0' },
      { slug: 'beauty', name: 'Peluquería', description: '', locale: 'es', latest_version: '2.1.0' },
    ]);
    const w = mountPanel();
    await flushPromises();
    expect(fetchBlueprintCatalog).toHaveBeenCalledTimes(1);
    const table = w.get('[data-testid="import-blueprint-table"]');
    expect(table.attributes('default-view')).toBe('cards');
    expect(table.attributes('row-key-field')).toBe('slug');
  });

  // 🔴 hub#1120 — quién puede importar lo decide el PERMISO, no la cadena `role`.
  //
  // El panel preguntaba por `isAdmin`, que compara `user.role` con «owner»/«admin». Ese campo es
  // OPCIONAL por contrato (`SessionUser.role`: «las sesiones legacy / el fallback demo no lo
  // traen»), mientras que el permiso `hub.administer` lo concede el runtime a esos MISMOS roles
  // (`identity::session_permissions`) y es la puerta que usa el resto de la administración desde
  // ADR-0248 (hub#506: una sola definición del símbolo). Cuando las dos discrepan sale exactamente
  // lo que se vio en producción: el hero del dashboard —que sí mira el permiso— ofrece las cuatro
  // plantillas, y esta tabla se queda vacía SIN pedir siquiera el catálogo. Ni error, ni petición,
  // ni filas: el onboarding de un clic deja de tener puerta.
  it('pide el catálogo a quien puede ADMINISTRAR el hub, aunque su sesión no traiga `role`', async () => {
    signInAsOwner({ role: undefined, permissions: ['hub.administer'] });
    fetchBlueprintCatalog.mockResolvedValue([
      { slug: 'rest', name: 'Restaurante', description: 'TPV', locale: 'es', latest_version: '1.0.0' },
    ]);
    const w = mountPanel();
    await flushPromises();

    expect(fetchBlueprintCatalog).toHaveBeenCalledTimes(1);
    expect(w.get('[data-testid="import-blueprint-table"]').attributes('empty-message')).not.toBe(
      'importPage.catalogForbidden',
    );
  });

  it('SIEMPRE ofrece «subir desde archivo», haya o no blueprints', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    const w = mountPanel();
    await flushPromises();
    expect(w.find('[data-testid="import-upload-local"]').exists()).toBe(true);
    // Sin blueprints en la nube: el data-table conserva su empty-state y la subida sigue visible.
    expect(w.find('[data-testid="import-blueprint-table"]').exists()).toBe(true);
  });

  it('si el catálogo falla (hub sin credencial cloud) DEGRADA en silencio, sin banner de error', async () => {
    // Regresión: la auto-carga del catálogo volcaba el fallo en el banner de error del inspector
    // de ficheros → un hub Local/dev sin credencial veía «No se pudo leer el fichero…» al entrar.
    fetchBlueprintCatalog.mockRejectedValue(new Error('hub sin credencial'));
    const w = mountPanel();
    await flushPromises();
    // NO hay banner de error (ese se reserva a fallos de inspección de un fichero elegido).
    expect(w.find('[data-testid="import-error"]').exists()).toBe(false);
    // La subida sigue disponible: es el fallback cuando no hay nube.
    expect(w.find('[data-testid="import-upload-local"]').exists()).toBe(true);
  });
});

describe('ImportPanel · el empty-state no puede mentir', () => {
  // 🔴 Defecto de producción (2026-08-03): con una cuenta admin-de-org la pantalla afirmaba
  // «Todavía no hay plantillas publicadas para tu hub». Con el owner listaba CUATRO. No es que no
  // hubiera: es que ni se pedía el catálogo (`onMounted` solo lo carga `if (isAdmin)`), y el
  // empty-state genérico afirmaba lo contrario.
  it('sin permiso NO afirma que no haya plantillas', async () => {
    signInAsOwner({ role: 'cashier', permissions: ['sales.sell'] });
    const w = mountPanel();
    await flushPromises();

    // Ni siquiera se pide el catálogo: no hay base para afirmar nada sobre su contenido.
    expect(fetchBlueprintCatalog).not.toHaveBeenCalled();
    expect(w.get('[data-testid="import-blueprint-table"]').attributes('empty-message')).toBe(
      'importPage.catalogForbidden',
    );
  });

  // 🔴 Revisión de hub#1120 — un fallo del catálogo tiene que poder DESHACERSE desde la pantalla.
  //
  // Reproducido el 2026-08-25 en un hub real (`qa-pm149-20260822-1435`): el SaaS estranguló
  // `GET /api/blueprints/catalog` con un **429** («Request was throttled. Expected available in
  // 1127 seconds») y el panel degradó en silencio a lista vacía. La degradación es correcta —el
  // fichero local sigue siendo el fallback—, pero era **definitiva**: el catálogo se pide una vez
  // al montar y la pestaña Datos vive entre navegaciones, así que un negocio nuevo se quedaba sin
  // plantillas hasta recargar la página entera. Un estrangulamiento dura minutos; la pantalla no
  // puede durar más que él.
  it('tras un fallo del catálogo ofrece reintentarlo, y el reintento lo trae', async () => {
    fetchBlueprintCatalog.mockRejectedValueOnce(new Error('429'));
    const w = mountPanel();
    await flushPromises();
    expect(w.get('[data-testid="import-blueprint-table"]').attributes('empty-message')).toBe(
      'importPage.catalogUnavailable',
    );

    fetchBlueprintCatalog.mockResolvedValueOnce([
      { slug: 'rest', name: 'Restaurante', description: 'TPV', locale: 'es', latest_version: '1.0.0' },
    ]);
    await w.get('[data-testid="import-catalog-retry"]').trigger('click');
    await flushPromises();

    expect(fetchBlueprintCatalog).toHaveBeenCalledTimes(2);
    expect(w.get('[data-testid="import-blueprint-table"]').attributes('empty-message')).toBe(
      'importPage.catalogEmpty',
    );
  });

  it('el reintento SOLO se ofrece cuando el catálogo falló: no cuando está vacío de verdad', async () => {
    // «Vacío» es una afirmación sobre el catálogo, no sobre nosotros: ahí no hay nada que reintentar.
    fetchBlueprintCatalog.mockResolvedValue([]);
    const w = mountPanel();
    await flushPromises();
    expect(w.find('[data-testid="import-catalog-retry"]').exists()).toBe(false);
  });

  it('si el catálogo FALLA tampoco afirma que no haya (dice que no se pudo cargar)', async () => {
    fetchBlueprintCatalog.mockRejectedValue(new Error('hub sin credencial'));
    const w = mountPanel();
    await flushPromises();
    expect(w.get('[data-testid="import-blueprint-table"]').attributes('empty-message')).toBe(
      'importPage.catalogUnavailable',
    );
  });

  it('cargado y realmente vacío SÍ dice que no hay plantillas', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    const w = mountPanel();
    await flushPromises();
    expect(w.get('[data-testid="import-blueprint-table"]').attributes('empty-message')).toBe(
      'importPage.catalogEmpty',
    );
  });
});

describe('ImportPanel · informe: instalación de módulos', () => {
  // 🔴 El import instala los módulos que faltan y anota el resultado en `report.installed_modules`,
  // pero el panel SOLO pintaba `report.sections`. Con los 13 módulos fallando, el usuario veía el
  // informe y «Ir al inicio» dejaba el panel igual de vacío, SIN señal de que algo había fallado.
  function reportWith(installed_modules: unknown[]) {
    // `sections` vacío a propósito: aquí se prueba SOLO la mitad de módulos del informe.
    return { sections: [], installed_modules };
  }

  async function panelConInforme(installed_modules: unknown[]) {
    fetchBlueprintCatalog.mockResolvedValue([]);
    const w = mountPanel();
    await flushPromises();
    const vm = w.vm as unknown as Record<string, unknown>;
    vm.report = reportWith(installed_modules);
    vm.step = 'report';
    await flushPromises();
    return w;
  }

  it('pinta una fila por módulo instalado', async () => {
    const w = await panelConInforme([
      { id: 'inventory', version: '1.2.16', status: 'installed' },
      { id: 'sales', version: '2.12.8', status: 'already_installed' },
    ]);
    const texto = w.get('[data-testid="import-report"]').text();
    expect(texto).toContain('inventory');
    expect(texto).toContain('sales');
  });

  it('un módulo que NO se pudo instalar sale con su MOTIVO, no en silencio', async () => {
    const w = await panelConInforme([
      {
        id: 'tables',
        version: '1.4.0',
        status: 'failed',
        error: 'descarga/integridad: módulo sin firma: la política exige firma verificada',
      },
    ]);
    const texto = w.get('[data-testid="import-report"]').text();
    expect(texto).toContain('tables');
    // El motivo REAL del motor, tal cual: sin él el usuario no puede ni reportar el fallo.
    expect(texto).toContain('módulo sin firma');
  });
});

// hub#409 — the engine already reports `blocked` (ADR-0060): the module was not installed because
// the plan requires subscribing to a dependency. That is a purchase decision, not a breakage, and
// the report was painting it as a mute red failure. Real translations here (the shared i18n above
// returns keys on purpose) because what is under test is the sentence the user actually reads.
describe('ImportPanel · report: a module blocked by entitlement (ADR-0060)', () => {
  const i18nReal = createI18n({
    legacy: false,
    locale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages: { en },
  });

  /** One entry of `installed_modules[]` exactly as `module_install_entry` serializes it. */
  const blockedEntry = {
    id: 'verifactu',
    version: '1.0.0',
    status: 'blocked',
    code: 'install_blocked',
    blocked_on: ['invoice'],
    purchase: [
      {
        module_id: 'invoice',
        module_type: 'premium',
        price: '9.00',
        currency: 'EUR',
        purchase_url: '/marketplace/invoice/',
      },
    ],
  };

  async function reportWithBlockedModule() {
    fetchBlueprintCatalog.mockResolvedValue([]);
    const w = mount(ImportPanel, {
      shallow: true,
      global: { plugins: [i18nReal], renderStubDefaultSlot: true },
    });
    await flushPromises();
    const vm = w.vm as unknown as Record<string, unknown>;
    vm.report = { sections: [], installed_modules: [blockedEntry] };
    vm.step = 'report';
    await flushPromises();
    return w.get('[data-testid="import-report"]');
  }

  it('is NOT painted as a failure', async () => {
    const report = await reportWithBlockedModule();
    expect(report.text()).not.toContain(en.importPage.statusFailed);
    // A discard's warning, not a breakage's red.
    expect(report.html()).not.toContain('danger');
    expect(report.html()).toContain('warning');
  });

  it('says what has to be subscribed to, with the price the engine sent', async () => {
    const report = await reportWithBlockedModule();
    const text = report.text();
    expect(text).toContain(en.importPage.statusBlocked);
    // Naming the blocking module is the whole point: «failed» told the user nothing.
    expect(text).toContain('invoice');
    // Price formatted for the active locale (9,00 € / €9.00), never invented.
    expect(text).toMatch(/9[.,]00/);
  });

  it('without the list of blocking modules it does not print a dangling sentence', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    const w = mount(ImportPanel, {
      shallow: true,
      global: { plugins: [i18nReal], renderStubDefaultSlot: true },
    });
    await flushPromises();
    const vm = w.vm as unknown as Record<string, unknown>;
    vm.report = {
      sections: [],
      installed_modules: [{ id: 'verifactu', version: '1.0.0', status: 'blocked' }],
    };
    vm.step = 'report';
    await flushPromises();
    const text = w.get('[data-testid="import-report"]').text();
    // Still blocked, never a failure — but a sentence naming an EMPTY list names nothing.
    expect(text).toContain(en.importPage.statusBlocked);
    expect(text).not.toContain(en.importPage.statusFailed);
    expect(text).not.toContain('Subscribe to them');
  });

  // hub#488 — the row and the sentence both named the app by our manifest key. The owner is being
  // asked to go and subscribe to it; `invoice` is not what the marketplace calls it.
  it('names the blocked app the way the marketplace does, not by its manifest id', async () => {
    appNames.set('verifactu', 'VeriFactu · AEAT');
    appNames.set('invoice', 'Facturación');
    const report = await reportWithBlockedModule();
    const text = report.text();

    expect(text).toContain('VeriFactu · AEAT');
    expect(text).toContain('Facturación');
    // The price still comes from the engine, next to the name the owner will recognise.
    expect(text).toMatch(/9[.,]00/);
    // And the raw key is gone from the row: leaving both would just be noise.
    expect(text).not.toMatch(/\binvoice\b/);
  });

  it('an app the shell has no name for keeps its id, and the report still paints', async () => {
    const report = await reportWithBlockedModule();

    expect(report.text()).toContain('invoice');
    expect(report.text()).toContain(en.importPage.statusBlocked);
  });

  it('the other three states keep their visual', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    const w = mount(ImportPanel, {
      shallow: true,
      global: { plugins: [i18nReal], renderStubDefaultSlot: true },
    });
    await flushPromises();
    const vm = w.vm as unknown as Record<string, unknown>;
    vm.report = {
      sections: [],
      installed_modules: [
        { id: 'inventory', version: '1.2.16', status: 'installed' },
        { id: 'sales', version: '2.12.8', status: 'already_installed' },
        { id: 'tables', version: '1.4.0', status: 'failed', error: 'unsigned module' },
      ],
    };
    vm.step = 'report';
    await flushPromises();
    const text = w.get('[data-testid="import-report"]').text();
    expect(text).toContain(en.importPage.statusApplied);
    expect(text).toContain(en.importPage.statusSkipped);
    expect(text).toContain(en.importPage.statusFailed);
    expect(text).toContain('unsigned module');
  });
});

describe('ImportPanel · hub#763 — el informe no se pierde al navegar', () => {
  // 🔴 Defecto (hub#763): el Dashboard anunciaba «ver el detalle en Ajustes › Datos» tras un
  // import parcial, pero al montarse la pestaña Datos empezaba SIEMPRE en el catálogo. El informe
  // vivía solo en un `ref` del componente que el admin acaba de dejar atrás. Ahora se recupera del
  // runtime al montar, y si quedó algo sin aplicar, se muestra en el paso `report`.
  function partialReport() {
    return {
      sections: [{ section: 'modules/inventory', status: { Failed: 'módulo no instalado' }, discarded_rows: 0 }],
      installed_modules: [],
    };
  }

  it('recupera el último informe parcial al montar y lo muestra en el paso report', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    fetchImportReport.mockResolvedValue({
      batch_id: 'b1',
      name: 'pizzeria',
      created_at: '2026-08-10T19:09:00Z',
      report: partialReport(),
    });
    const w = mountPanel();
    await flushPromises();

    // El informe recuperado reemplaza al catálogo: es lo que el Dashboard prometió mostrar.
    expect(w.find('[data-testid="import-blueprint-table"]').exists()).toBe(false);
    const report = w.get('[data-testid="import-report"]');
    expect(report.text()).toContain(en.importPage.statusFailed);
    expect(report.text()).toContain('módulo no instalado');
    // El banner dice de QUÉ import es el informe (no aparece de la nada).
    expect(w.find('[data-testid="import-report-recovered"]').exists()).toBe(true);
  });

  it('un informe totalmente aplicado NO se muestra: el catálogo es lo siguiente', async () => {
    fetchBlueprintCatalog.mockResolvedValue([
      { slug: 'rest', name: 'Restaurante', locale: 'es', latest_version: '1.0.0' },
    ]);
    fetchImportReport.mockResolvedValue({
      batch_id: 'b2',
      name: 'pizzeria',
      created_at: '2026-08-10T19:09:00Z',
      report: {
        sections: [{ section: 'modules/inventory', status: 'Applied', discarded_rows: 0 }],
        installed_modules: [],
      },
    });
    const w = mountPanel();
    await flushPromises();

    // Todo aplicado = nada que decir: el catálogo manda.
    expect(w.find('[data-testid="import-report"]').exists()).toBe(false);
    expect(w.find('[data-testid="import-blueprint-table"]').exists()).toBe(true);
  });

  it('98 copiadas y 182 fallidas recupera el informe y pinta Media como fallo', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    fetchImportReport.mockResolvedValue({
      batch_id: 'b-media',
      name: 'restaurante',
      created_at: '2026-08-17T00:00:00Z',
      report: {
        sections: [{ section: 'media', status: 'Skipped', discarded_rows: 0 }],
        installed_modules: [],
        media: { selected: true, copied: 98, failed: 182 },
      },
    });
    const i18nReal = createI18n({
      legacy: false,
      locale: 'en',
      missingWarn: false,
      fallbackWarn: false,
      messages: { en },
    });
    const w = mount(ImportPanel, {
      shallow: true,
      global: { plugins: [i18nReal], renderStubDefaultSlot: true },
    });
    await flushPromises();

    expect(w.find('[data-testid="import-report-recovered"]').exists()).toBe(true);
    const report = w.get('[data-testid="import-report"]');
    expect(report.text()).toContain(en.importPage.statusFailed);
    expect(report.text()).toContain('182 not copied');
    expect(report.html()).toContain('danger');
  });

  it('«ver las plantillas» descarta el informe recuperado y vuelve al catálogo', async () => {
    fetchBlueprintCatalog.mockResolvedValue([
      { slug: 'rest', name: 'Restaurante', locale: 'es', latest_version: '1.0.0' },
    ]);
    fetchImportReport.mockResolvedValue({
      batch_id: 'b1',
      name: 'pizzeria',
      created_at: '2026-08-10T19:09:00Z',
      report: partialReport(),
    });
    const w = mountPanel();
    await flushPromises();
    expect(w.find('[data-testid="import-blueprint-table"]').exists()).toBe(false);

    await w.get('[data-testid="import-report-dismiss"]').trigger('click');
    await flushPromises();
    expect(w.find('[data-testid="import-blueprint-table"]').exists()).toBe(true);
    expect(w.find('[data-testid="import-report"]').exists()).toBe(false);
  });

  it('sin informe persistido (hub nuevo) muestra el catálogo, como antes', async () => {
    fetchBlueprintCatalog.mockResolvedValue([
      { slug: 'rest', name: 'Restaurante', locale: 'es', latest_version: '1.0.0' },
    ]);
    fetchImportReport.mockResolvedValue(null);
    const w = mountPanel();
    await flushPromises();
    expect(w.find('[data-testid="import-blueprint-table"]').exists()).toBe(true);
    expect(w.find('[data-testid="import-report"]').exists()).toBe(false);
  });
});

describe('ImportPanel · hub#845 — «Reintentar lo que falta» en el informe recuperado', () => {
  // Real English catalogue (like the ADR-0060 block): the reason for a disabled retry and the
  // translated refusal are tested through the sentence the user actually reads.
  const i18nReal = createI18n({
    legacy: false,
    locale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages: { en },
  });

  function mountPanelReal() {
    return mount(ImportPanel, {
      shallow: true,
      global: { plugins: [i18nReal], renderStubDefaultSlot: true },
    });
  }

  function partialCatalogReport() {
    return {
      sections: [
        { section: 'hub_settings', status: 'Applied', discarded_rows: 0 },
        { section: 'modules/inventory', status: { Failed: 'módulo no instalado' }, discarded_rows: 0 },
      ],
      installed_modules: [],
      origin: { source: 'catalog', slug: 'pizzeria', version: '1.0.2', locale: 'es' },
    };
  }

  function storedReport(report: unknown, batchId = 'b1') {
    return { batch_id: batchId, name: 'pizzeria', created_at: '2026-08-10T19:09:00Z', report };
  }

  it('un informe parcial venido del catálogo ofrece el reintento HABILITADO', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    fetchImportReport.mockResolvedValue(storedReport(partialCatalogReport()));
    const w = mountPanelReal();
    await flushPromises();

    const retry = w.get('[data-testid="import-report-retry"]');
    expect(retry.attributes('disabled')).toBe('false');
    // Enabled ⇒ no reason to show: the reason exists only to explain a disabled button.
    expect(w.find('[data-testid="import-retry-reason"]').exists()).toBe(false);
  });

  it('pulsarlo reintenta ESE lote y pinta el informe fresco del reintento', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    // On mount: the partial report. After the retry: the fresh persisted one (new batch).
    const freshReport = {
      sections: [{ section: 'modules/inventory', status: 'Applied', discarded_rows: 0 }],
      installed_modules: [{ id: 'inventory', version: '1.0.0', status: 'installed' }],
      origin: { source: 'catalog', slug: 'pizzeria', version: '1.0.2', locale: 'es' },
    };
    fetchImportReport
      .mockResolvedValueOnce(storedReport(partialCatalogReport()))
      .mockResolvedValueOnce(storedReport(freshReport, 'b2'));
    retryImport.mockResolvedValue({ retried: true, code: undefined, report: freshReport });

    const w = mountPanelReal();
    await flushPromises();
    await w.get('[data-testid="import-report-retry"]').trigger('click');
    await flushPromises();

    expect(retryImport).toHaveBeenCalledWith('b1');
    const report = w.get('[data-testid="import-report"]');
    expect(report.text()).toContain(en.importPage.statusApplied);
    expect(report.text()).not.toContain('módulo no instalado');
  });

  it('un import de FICHERO LOCAL no se puede reintentar: botón deshabilitado y el MOTIVO legible', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    const report = partialCatalogReport();
    (report as { origin: unknown }).origin = { source: 'local' };
    fetchImportReport.mockResolvedValue(storedReport(report));
    const w = mountPanelReal();
    await flushPromises();

    const retry = w.get('[data-testid="import-report-retry"]');
    expect(retry.attributes('disabled')).toBe('true');
    expect(w.get('[data-testid="import-retry-reason"]').text()).toContain(
      en.importPage.retryNotRetryable,
    );
  });

  it('un informe ANTERIOR al campo origin tampoco es reintentable (sin origen no hay garantía)', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    const report = partialCatalogReport();
    delete (report as { origin?: unknown }).origin;
    fetchImportReport.mockResolvedValue(storedReport(report));
    const w = mountPanelReal();
    await flushPromises();

    expect(w.get('[data-testid="import-report-retry"]').attributes('disabled')).toBe('true');
    expect(w.find('[data-testid="import-retry-reason"]').exists()).toBe(true);
  });

  it('un rechazo del server con código estable se enseña TRADUCIDO, no como prosa técnica', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    fetchImportReport.mockResolvedValue(storedReport(partialCatalogReport()));
    const { RetryRefusedError } = await vi.importActual<typeof import('../lib/runtime')>('../lib/runtime');
    retryImport.mockRejectedValue(
      new RetryRefusedError('the catalogue now serves 1.0.5', 'import_retry_version_unavailable'),
    );

    const w = mountPanelReal();
    await flushPromises();
    await w.get('[data-testid="import-report-retry"]').trigger('click');
    await flushPromises();

    expect(w.get('[data-testid="import-retry-error"]').text()).toContain(
      en.importPage.retryVersionUnavailable,
    );
  });
  // ── hub#1693 · el código del runtime NUNCA llega a la pantalla ─────────────────────────────
  //
  // Desde hub#1689 los proxies del runtime contestan un código estable (`cloud_unreachable`) en vez
  // del Display de `reqwest`, que arrastraba la dirección del plano de control. El cuerpo dejó de
  // publicar una dirección interna —y pasó a publicar una palabra en inglés con guion bajo delante
  // de quien lleva el negocio. Se traduce por código; la prosa honesta del server se conserva.

  it('la nube que no contesta se lee como una FRASE, no como `cloud_unreachable`', async () => {
    fetchBlueprintCatalog.mockResolvedValue([
      { slug: 'rest', name: 'Restaurante', description: 'TPV', locale: 'es', latest_version: '1.0.0' },
    ]);
    fetchImportReport.mockResolvedValue(null);
    downloadBlueprint.mockRejectedValue(new Error('cloud_unreachable'));

    const w = mountPanelReal();
    await flushPromises();
    w.get('[data-testid="import-blueprint-table"]').element.dispatchEvent(
      new CustomEvent('rowAction', {
        detail: { actionId: 'use', row: { slug: 'rest', latest_version: '1.0.0' } },
      }),
    );
    await flushPromises();

    const shown = w.get('[data-testid="import-error"]').text();
    expect(shown).toContain(en.runtimeErrors.cloud_unreachable);
    expect(shown).not.toContain('cloud_unreachable');
  });

  it('la prosa HONESTA del server se conserva: solo se traduce lo que es un código', async () => {
    fetchBlueprintCatalog.mockResolvedValue([
      { slug: 'rest', name: 'Restaurante', description: 'TPV', locale: 'es', latest_version: '1.0.0' },
    ]);
    fetchImportReport.mockResolvedValue(null);
    // Integridad rota: dice QUÉ se rompió, y ninguna frase genérica nuestra dice más.
    downloadBlueprint.mockRejectedValue(new Error('el SaaS contestó 404 al resolver el blueprint'));

    const w = mountPanelReal();
    await flushPromises();
    w.get('[data-testid="import-blueprint-table"]').element.dispatchEvent(
      new CustomEvent('rowAction', {
        detail: { actionId: 'use', row: { slug: 'rest', latest_version: '1.0.0' } },
      }),
    );
    await flushPromises();

    expect(w.get('[data-testid="import-error"]').text()).toContain(
      'el SaaS contestó 404 al resolver el blueprint',
    );
  });

  it('el reintento que se cae por la nube tampoco enseña el código', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    fetchImportReport.mockResolvedValue(storedReport(partialCatalogReport()));
    // No es un `RetryRefusedError` (eso ya se traducía): es la puerta del catálogo caída.
    retryImport.mockRejectedValue(new Error('cloud_unreachable'));

    const w = mountPanelReal();
    await flushPromises();
    await w.get('[data-testid="import-report-retry"]').trigger('click');
    await flushPromises();

    const shown = w.get('[data-testid="import-retry-error"]').text();
    expect(shown).toContain(en.runtimeErrors.cloud_unreachable);
    expect(shown).not.toContain('cloud_unreachable');
  });
});

// hub#1905 — the end of an import asks for the permissions of the apps it brought. The question
// itself lives in `ImportPermissionsConsent` (tested there); what this panel owes it is the RIGHT
// report: the one of the import that just ran here — never the one recovered from an earlier import
// when the owner merely opens Settings › Data.
describe('hub#1905 · al terminar de importar se piden los permisos de sus apps', () => {
  const consentReport = (w: ReturnType<typeof mountPanel>): unknown =>
    w.getComponent(ImportPermissionsConsent).props('report');

  const salon = {
    sections: [{ section: 'modules/verifactu', status: 'Applied', discarded_rows: 0 }],
    installed_modules: [
      { id: 'verifactu', version: '1.5.40', status: 'installed' },
      { id: 'printing', version: '0.1.22', status: 'installed' },
    ],
    origin: { source: 'catalog', slug: 'peluqueria', version: '1.0.0', locale: 'es' },
  };

  it('el modal de permisos recibe el informe del import que acaba de terminar', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    fetchImportReport.mockResolvedValue(null);
    vi.mocked(importBlueprint).mockResolvedValue(salon as never);
    const w = mountPanel();
    await flushPromises();
    expect(consentReport(w)).toBeNull();

    await (w.vm as unknown as { doImport: () => Promise<void> }).doImport();
    await flushPromises();

    expect(consentReport(w)).toEqual(salon);
  });

  it('y el del reintento, que también puede instalar apps', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    const partial = {
      sections: [{ section: 'modules/verifactu', status: { Failed: 'módulo no instalado' }, discarded_rows: 0 }],
      installed_modules: [],
      origin: salon.origin,
    };
    fetchImportReport
      .mockResolvedValueOnce({ batch_id: 'b1', name: 'peluqueria', created_at: '2026-09-18T10:00:00Z', report: partial })
      .mockResolvedValueOnce({ batch_id: 'b2', name: 'peluqueria', created_at: '2026-09-18T10:05:00Z', report: salon });
    retryImport.mockResolvedValue({ retried: true, code: undefined, report: salon });
    const w = mountPanel();
    await flushPromises();

    await w.get('[data-testid="import-report-retry"]').trigger('click');
    await flushPromises();

    expect(consentReport(w)).toEqual(salon);
  });

  it('un informe RECUPERADO de un import anterior no pregunta nada al abrir Datos', async () => {
    fetchBlueprintCatalog.mockResolvedValue([]);
    fetchImportReport.mockResolvedValue({
      batch_id: 'b1',
      name: 'peluqueria',
      created_at: '2026-09-17T10:00:00Z',
      report: {
        ...salon,
        sections: [{ section: 'modules/tables', status: { Failed: 'módulo no instalado' }, discarded_rows: 0 }],
      },
    });
    const w = mountPanel();
    await flushPromises();
    // The recovered report IS on screen — the question is about the import that is not running.
    expect(w.find('[data-testid="import-report"]').exists()).toBe(true);

    expect(consentReport(w)).toBeNull();
  });
});
