// @vitest-environment happy-dom
// Contrato del panel «Restablecer» (Ajustes › Datos, ADR-0170) — la operación más destructiva del
// producto. Lo que estos tests protegen no es el layout, es que NO se pueda borrar por accidente:
//   - las cifras del alert salen del PLAN real (dry-run), no de un texto genérico,
//   - lo bloqueado por el límite fiscal (facturas remitidas a la AEAT) no es ni seleccionable,
//   - confirmar exige ESCRIBIR el nombre del hub (patrón GitHub), no un simple «Aceptar»,
//   - sin selección no se puede disparar nada.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const fetchResetPlan = vi.fn();
const resetHub = vi.fn();
const fetchImportBatches = vi.fn();
const undoImport = vi.fn();
const listInstalledModules = vi.fn();
vi.mock('../lib/runtime', () => ({
  fetchResetPlan: (...a: unknown[]) => fetchResetPlan(...a),
  resetHub: (...a: unknown[]) => resetHub(...a),
  fetchImportBatches: (...a: unknown[]) => fetchImportBatches(...a),
  undoImport: (...a: unknown[]) => undoImport(...a),
  listInstalledModules: (...a: unknown[]) => listInstalledModules(...a),
}));

// El nombre del hub que hay que teclear para confirmar sale de los settings del hub.
vi.mock('../lib/hub-settings', () => ({
  hubSettings: { value: { business_legal_name: 'Bar Manolo' } },
}));

const alertCreate = vi.fn();
vi.mock('@ionic/vue', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('@ionic/vue');
  return { ...actual, alertController: { create: (...a: unknown[]) => alertCreate(...a) } };
});

import ResetPanel from './ResetPanel.vue';

// Mensajes REALES (no un objeto vacío): la cifra del plan llega al usuario a través de la
// interpolación de i18n, así que un i18n mudo escondería justo lo que estos tests protegen.
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      settings: {
        resetIntro: 'Deleting is permanent.',
        resetExportFirst: 'Export a backup first',
        // Pluralización de vue-i18n: `singular | plural`. El `n` de las opciones decide cuál.
        resetRows: '{n} row | {n} rows',
        resetSubmit: 'Reset hub',
        resetDeleted: '{n} rows deleted',
        resetConfirmTitle: 'This cannot be undone',
        resetConfirmBody: '{total} rows will be permanently deleted:',
        resetConfirmPlaceholder: 'business name',
        resetCancel: 'Cancel',
        resetImportsTitle: 'Undo an import',
        resetImportsHint: 'Removes only what that blueprint brought in.',
        resetSectionsTitle: 'Or delete by section',
        resetUndo: 'Undo',
        resetUndoTitle: 'Undo {name}',
        resetUndoBody: '{n} rows brought in by this blueprint will be deleted.',
        resetUndoEdited: 'You changed {areas} after importing: only your changes stay there.',
        resetUndoNotRestored: 'Only your changes were kept in {areas}.',
        resetConfirm: 'Delete permanently',
        reset_hub_settings: 'Hub settings',
        reset_hub_users: 'Employees',
        reset_roles: 'Active roles',
      },
    },
  },
});

const PLAN = {
  sections: [
    // Secciones VACÍAS: un hub con 27 módulos instalados devuelve casi todas a cero (visto en
    // QA real: 25 secciones, 23 a cero). No hay nada que borrar en ellas → no se listan.
    { section: 'modules/vacio_a', rows: 0, blocked_by: null },
    { section: 'modules/vacio_b', rows: 0, blocked_by: null },
    { section: 'modules/inventory', rows: 124, blocked_by: null },
    { section: 'modules/customers', rows: 38, blocked_by: null },
    {
      section: 'modules/verifactu',
      rows: 12,
      blocked_by: '12 facturas remitidas a la AEAT: inalterables por RD 1007/2023, no se pueden borrar',
    },
    { section: 'hub_settings', rows: 7, blocked_by: null },
    // hub#417: the role set of the hub — the roles the installed modules declare that are LIVE
    // here. It is a section like any other, so the owner picks it deliberately.
    { section: 'roles', rows: 4, blocked_by: null },
  ],
};

function mountPanel() {
  return mount(ResetPanel, { global: { plugins: [i18n], renderStubDefaultSlot: true }, shallow: true });
}

/**
 * Espera a que el `onMounted` async (plan + lotes + nombres de módulos) haya resuelto.
 *
 * El onMounted encadena tres awaits secuenciales (fetchResetPlan → fetchImportBatches →
 * listInstalledModules, hub#765). `flushPromises` vacía la cola de microtasks, pero los mocks
 * resuelven en el orden en que se esperan, así que hay que darle suficientes vueltas para que la
 * última promesa se asiente antes de que el test lea el DOM.
 */
async function flush(w: ReturnType<typeof mountPanel>) {
  await flushPromises();
  await flushPromises();
  await flushPromises();
  await w.vm.$nextTick();
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchResetPlan.mockResolvedValue(PLAN);
  resetHub.mockResolvedValue({ sections: [{ section: 'modules/inventory', rows_deleted: 124 }] });
  fetchImportBatches.mockResolvedValue([
    { id: 'batch-1', name: 'restaurante_es', rows: 312, created_at: '2026-07-31T10:14:00Z' },
  ]);
  undoImport.mockResolvedValue({ sections: [{ section: 'inventory_product', rows_deleted: 312 }] });
  // El nombre legible de cada módulo instalado (hub#765): el panel de reset lo usa para que una
  // sección `modules/inventory` se lea «Inventario» y no el slug interno crudo.
  listInstalledModules.mockResolvedValue([
    { id: 'inventory', name: 'Inventory', version: '1.0.0' },
    { id: 'customers', name: 'Customers', version: '1.0.0' },
    { id: 'verifactu', name: 'VeriFactu', version: '1.0.0' },
  ]);
  // Por defecto el usuario teclea bien el nombre y confirma.
  alertCreate.mockResolvedValue({
    present: vi.fn(),
    onDidDismiss: vi.fn().mockResolvedValue({ role: 'confirm', data: { values: { name: 'Bar Manolo' } } }),
  });
});

describe('ResetPanel', () => {
  it('carga el plan al entrar y pinta cada sección con su número REAL de filas', async () => {
    const w = mountPanel();
    await flush(w);

    expect(fetchResetPlan).toHaveBeenCalledTimes(1);
    const html = w.html();
    // Las cifras del dry-run, no adjetivos: es lo que hace honesto el aviso.
    expect(html).toContain('124');
    expect(html).toContain('38');
  });

  it('una sección bloqueada por la AEAT NO es seleccionable y muestra el motivo', async () => {
    const w = mountPanel();
    await flush(w);

    const blocked = w.find('[data-testid="reset-section-modules/verifactu"]');
    expect(blocked.exists()).toBe(true);
    expect(blocked.attributes('disabled')).toBeDefined();
    // El motivo se lee en pantalla: un bloqueo mudo se interpreta como un fallo del producto.
    expect(w.html()).toContain('AEAT');
  });

  it('no lista las secciones vacías: no hay nada que borrar en ellas', async () => {
    const w = mountPanel();
    await flush(w);

    expect(w.find('[data-testid="reset-section-modules/vacio_a"]').exists()).toBe(false);
    expect(w.find('[data-testid="reset-section-modules/inventory"]').exists()).toBe(true);
  });

  it('una sección vacía PERO bloqueada sí se muestra: explica por qué no se puede', async () => {
    fetchResetPlan.mockResolvedValue({
      sections: [{ section: 'modules/verifactu', rows: 0, blocked_by: '3 facturas remitidas a la AEAT' }],
    });
    const w = mountPanel();
    await flush(w);

    expect(w.find('[data-testid="reset-section-modules/verifactu"]').exists()).toBe(true);
  });

  it('sin nada seleccionado, el botón de restablecer está deshabilitado', async () => {
    const w = mountPanel();
    await flush(w);

    const btn = w.find('[data-testid="reset-submit"]');
    expect(btn.exists()).toBe(true);
    expect(btn.attributes('disabled')).toBeDefined();
  });

  it('el alert lleva las cifras del plan y EXIGE escribir el nombre del hub', async () => {
    const w = mountPanel();
    await flush(w);

    await w.vm.toggle('modules/inventory');
    await w.vm.submit();

    expect(alertCreate).toHaveBeenCalledTimes(1);
    const opts = alertCreate.mock.calls[0][0] as {
      message?: string;
      inputs?: { placeholder?: string }[];
    };
    expect(opts.message).toContain('124');
    // Confirmación fuerte (patrón GitHub): hay un input donde teclear el nombre del hub.
    expect(opts.inputs?.length).toBeGreaterThan(0);
    expect(JSON.stringify(opts.inputs)).toContain('Bar Manolo');
    expect(resetHub).toHaveBeenCalledTimes(1);
  });

  it('si el nombre tecleado NO coincide, no se borra nada', async () => {
    alertCreate.mockResolvedValue({
      present: vi.fn(),
      onDidDismiss: vi
        .fn()
        .mockResolvedValue({ role: 'confirm', data: { values: { name: 'bar equivocado' } } }),
    });
    const w = mountPanel();
    await flush(w);

    await w.vm.toggle('modules/inventory');
    await w.vm.submit();

    expect(resetHub).not.toHaveBeenCalled();
  });

  it('cancelar el alert no borra nada', async () => {
    alertCreate.mockResolvedValue({
      present: vi.fn(),
      onDidDismiss: vi.fn().mockResolvedValue({ role: 'cancel' }),
    });
    const w = mountPanel();
    await flush(w);

    await w.vm.toggle('modules/inventory');
    await w.vm.submit();

    expect(resetHub).not.toHaveBeenCalled();
  });

  it('nunca envía al servidor una sección bloqueada, aunque se intente forzar', async () => {
    const w = mountPanel();
    await flush(w);

    await w.vm.toggle('modules/verifactu'); // el usuario intenta marcarla
    await w.vm.submit();

    // Ni se abre el alert: no hay nada seleccionable que borrar.
    expect(resetHub).not.toHaveBeenCalled();
  });

  // hub#417 — el juego de roles del hub es una sección propia, no un efecto colateral de otra.
  // Encenderlo hace el rol asignable a una persona, así que apagarlo tiene que ser una decisión
  // que el dueño toma a la vista de su cifra, no algo que se lleva por delante «Ajustes del hub».
  it('el juego de roles se marca aparte y viaja como `roles` al runtime', async () => {
    const w = mountPanel();
    await flush(w);

    const roles = w.find('[data-testid="reset-section-roles"]');
    expect(roles.exists()).toBe(true);
    expect(w.html()).toContain('4');

    await w.vm.toggle('roles');
    await w.vm.submit();

    expect(resetHub).toHaveBeenCalledTimes(1);
    const sent = resetHub.mock.calls[0][0] as Record<string, unknown>;
    expect(sent.roles).toBe(true);
    // Y NADA más: marcar los roles no puede arrastrar los ajustes ni a los empleados.
    expect(sent.settings).toBe(false);
    expect(sent.users).toBe(false);
  });

  it('no marcar los roles los deja intactos: el reset nunca hace de más', async () => {
    const w = mountPanel();
    await flush(w);

    await w.vm.toggle('hub_settings');
    await w.vm.submit();

    const sent = resetHub.mock.calls[0][0] as Record<string, unknown>;
    expect(sent.roles).toBe(false);
  });

  // La sección se pinta con `t('settings.reset_<section>')`: sin la cadena, el panel enseña la
  // clave en crudo. El inglés es la fuente y el español SIEMPRE se traduce (ADR-0055/0199), así
  // que las dos tienen que existir — no basta con la que use el test.
  it('la sección de roles tiene su cadena en inglés Y en español', async () => {
    const [en, es] = await Promise.all([
      import('../i18n/locales/en'),
      import('../i18n/locales/es'),
    ]);
    for (const [lang, mod] of [['en', en], ['es', es]] as const) {
      // Los locales son objetos `as const` profundamente anidados; se leen aquí como un mapa
      // genérico para poder preguntar por la clave SIN que el tipo la dé por hecha (que es
      // justo lo que este test tiene que comprobar).
      const messages = mod.default as unknown as Record<string, Record<string, string>>;
      expect(messages.settings?.reset_roles, `falta settings.reset_roles en ${lang}`).toBeTruthy();
    }
  });

  it('ofrece exportar antes de borrar (red de seguridad de un clic)', async () => {
    const w = mountPanel();
    await flush(w);

    const backup = w.find('[data-testid="reset-export-first"]');
    expect(backup.exists()).toBe(true);
    await backup.trigger('click');
    expect(w.emitted('go-export')).toBeTruthy();
  });

  // hub#765: una sección de módulo (`modules/inventory`) se mostraba con el SLUG crudo —
  // «inventory», «tables», «invoice_series» — porque `label()` solo recortaba el prefijo. El
  // nombre legible ya vive en `listInstalledModules`; usarlo convierte la lista de borrar en algo
  // que el dueño reconoce, no un manojo de identificadores internos.
  it('una sección de módulo se muestra con su NOMBRE legible, no con el slug interno', async () => {
    const w = mountPanel();
    await flush(w);

    const html = w.html();
    expect(html).toContain('Inventory');
    expect(html).toContain('Customers');
    // El slug NO puede ser lo que ve el usuario: es un identificador de desarrollador.
    expect(html).not.toContain('>inventory<');
    expect(html).not.toContain('>customers<');
  });

  // Y si un módulo no está en la lista de instalados (p. ej. sus datos quedaron tras desinstalar),
  // el slug sigue siendo legible: cae al identificador en vez de quedar en blanco.
  it('un módulo desconocido cae al slug en vez de quedar sin etiqueta', async () => {
    fetchResetPlan.mockResolvedValue({
      sections: [{ section: 'modules/orphan_module', rows: 5, blocked_by: null }],
    });
    const w = mountPanel();
    await flush(w);

    expect(w.html()).toContain('orphan_module');
  });

  // hub#765: la gramática concordaba con el número. «1 filas» se leía en cada sección con un
  // solo elemento — feo, pero sobre todo señal de que el recuento no se había pensado para el
  // singular. La pluralización de vue-i18n (pipe `|`) lo resuelve sin tocar la llamada.
  it('una sección con UNA fila dice «1 row», no «1 rows»', async () => {
    fetchResetPlan.mockResolvedValue({
      sections: [{ section: 'modules/lonely', rows: 1, blocked_by: null }],
    });
    const w = mountPanel();
    await flush(w);

    expect(w.html()).toContain('1 row');
    expect(w.html()).not.toContain('1 rows');
  });
});

describe('ResetPanel · deshacer una importación', () => {
  it('lista las importaciones con su nombre y sus filas', async () => {
    const w = mountPanel();
    await flush(w);

    expect(fetchImportBatches).toHaveBeenCalledTimes(1);
    const html = w.html();
    expect(html).toContain('restaurante_es');
    expect(html).toContain('312');
  });

  it('deshacer pide confirmación y solo entonces llama al runtime', async () => {
    const w = mountPanel();
    await flush(w);

    await w.vm.undo('batch-1');

    expect(alertCreate).toHaveBeenCalledTimes(1);
    const opts = alertCreate.mock.calls[0][0] as { message?: string };
    // El aviso dice QUÉ se deshace y cuánto: sin cifras no informa.
    expect(opts.message).toContain('312');
    expect(undoImport).toHaveBeenCalledWith('batch-1');
  });

  it('cancelar deja la importación intacta', async () => {
    alertCreate.mockResolvedValue({
      present: vi.fn(),
      onDidDismiss: vi.fn().mockResolvedValue({ role: 'cancel' }),
    });
    const w = mountPanel();
    await flush(w);

    await w.vm.undo('batch-1');

    expect(undoImport).not.toHaveBeenCalled();
  });

  it('deshacer NO exige teclear el nombre del hub: es reversible por diseño', async () => {
    // A diferencia del reset por secciones, deshacer solo quita lo que trajo ese blueprint —
    // se puede volver a importar. La fricción debe ser proporcional al daño.
    const w = mountPanel();
    await flush(w);

    await w.vm.undo('batch-1');

    const opts = alertCreate.mock.calls[0][0] as { inputs?: unknown[] };
    expect(opts.inputs ?? []).toHaveLength(0);
    expect(undoImport).toHaveBeenCalled();
  });

  // hub#1556: the business adjusted ONE day of the imported week and then undid the import. The
  // seeded week cannot come back on top of its own row, so it is left with only that day — and
  // nothing said so. The runtime now flags the tables it edited; the dialog has to warn.
  it('warns in the confirmation when the business edited the imported data afterwards', async () => {
    fetchImportBatches.mockResolvedValue([
      {
        id: 'batch-1',
        name: 'peluqueria_es',
        rows: 7,
        created_at: '2026-07-31T10:14:00Z',
        edited_after_import: ['schedules_business_hours'],
      },
    ]);
    listInstalledModules.mockResolvedValue([{ id: 'schedules', name: 'Opening hours', version: '1.0.0' }]);
    const w = mountPanel();
    await flush(w);

    await w.vm.undo('batch-1');

    const opts = alertCreate.mock.calls[0][0] as { message?: string };
    expect(opts.message).toContain('You changed Opening hours after importing');
  });

  it('does not warn when nothing imported was edited', async () => {
    const w = mountPanel();
    await flush(w);

    await w.vm.undo('batch-1');

    const opts = alertCreate.mock.calls[0][0] as { message?: string };
    expect(opts.message).not.toContain('You changed');
  });

  it('says after undoing which data kept only the business changes', async () => {
    undoImport.mockResolvedValue({
      sections: [{ section: 'schedules_business_hours', rows_deleted: 7 }],
      not_restored: ['schedules_business_hours'],
    });
    listInstalledModules.mockResolvedValue([{ id: 'schedules', name: 'Opening hours', version: '1.0.0' }]);
    const w = mountPanel();
    await flush(w);

    await w.vm.undo('batch-1');
    await flush(w);

    const note = w.find('[data-testid="reset-undo-not-restored"]');
    expect(note.exists()).toBe(true);
    expect(note.text()).toContain('Only your changes were kept in Opening hours');
  });

  // hub#2055: the undo report comes back per TABLE (`schedules_business_hours`), not per reset
  // section. Without a table→module lookup the list painted the raw i18n key
  // `settings.reset_schedules_business_hours` instead of a name the business understands.
  it('names each undone table by the app it belongs to, never by an internal key', async () => {
    undoImport.mockResolvedValue({
      sections: [{ section: 'schedules_business_hours', rows_deleted: 7 }],
    });
    listInstalledModules.mockResolvedValue([{ id: 'schedules', name: 'Opening hours', version: '1.0.0' }]);
    const w = mountPanel();
    await flush(w);

    await w.vm.undo('batch-1');
    await flush(w);

    const report = w.find('[data-testid="reset-report"]');
    expect(report.text()).toContain('Opening hours — 7 rows deleted');
    expect(report.text()).not.toContain('settings.reset_');
    expect(report.text()).not.toContain('schedules_business_hours');
  });

  it('adds up the tables of the same app into a single line', async () => {
    undoImport.mockResolvedValue({
      sections: [
        { section: 'inventory_product', rows_deleted: 300 },
        { section: 'inventory_category', rows_deleted: 12 },
        { section: 'customers_customer', rows_deleted: 5 },
      ],
    });
    const w = mountPanel();
    await flush(w);

    await w.vm.undo('batch-1');
    await flush(w);

    const lines = w.findAll('[data-testid="reset-report-line"]').map((l) => l.text());
    expect(lines).toEqual(['Inventory — 312 rows deleted', 'Customers — 5 rows deleted']);
  });

  it('a table no installed app claims falls back to its own name, not to a raw i18n key', async () => {
    undoImport.mockResolvedValue({ sections: [{ section: 'orphan_table', rows_deleted: 2 }] });
    const w = mountPanel();
    await flush(w);

    await w.vm.undo('batch-1');
    await flush(w);

    const report = w.find('[data-testid="reset-report"]');
    expect(report.text()).toContain('orphan_table — 2 rows deleted');
    expect(report.text()).not.toContain('settings.reset_');
  });

  it('a full reset report still names core sections by their translated name', async () => {
    resetHub.mockResolvedValue({
      sections: [
        { section: 'hub_settings', rows_deleted: 1 },
        { section: 'modules/inventory', rows_deleted: 124 },
      ],
    });
    const w = mountPanel();
    await flush(w);
    await w.vm.toggle('modules/inventory');
    await w.vm.submit();
    await flush(w);

    const lines = w.findAll('[data-testid="reset-report-line"]').map((l) => l.text());
    expect(lines).toEqual(['Hub settings — 1 rows deleted', 'Inventory — 124 rows deleted']);
  });
})
