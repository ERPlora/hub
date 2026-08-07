// @vitest-environment happy-dom
// Contrato del panel «Restablecer» (Ajustes › Datos, ADR-0170) — la operación más destructiva del
// producto. Lo que estos tests protegen no es el layout, es que NO se pueda borrar por accidente:
//   - las cifras del alert salen del PLAN real (dry-run), no de un texto genérico,
//   - lo bloqueado por el límite fiscal (facturas remitidas a la AEAT) no es ni seleccionable,
//   - confirmar exige ESCRIBIR el nombre del hub (patrón GitHub), no un simple «Aceptar»,
//   - sin selección no se puede disparar nada.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const fetchResetPlan = vi.fn();
const resetHub = vi.fn();
const fetchImportBatches = vi.fn();
const undoImport = vi.fn();
vi.mock('../lib/runtime', () => ({
  fetchResetPlan: (...a: unknown[]) => fetchResetPlan(...a),
  resetHub: (...a: unknown[]) => resetHub(...a),
  fetchImportBatches: (...a: unknown[]) => fetchImportBatches(...a),
  undoImport: (...a: unknown[]) => undoImport(...a),
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
        resetRows: '{n} rows',
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

/** Espera a que el `onMounted` async (carga del plan) haya resuelto. */
async function flush(w: ReturnType<typeof mountPanel>) {
  await Promise.resolve();
  await Promise.resolve();
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
})
