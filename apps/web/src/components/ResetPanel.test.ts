// @vitest-environment happy-dom
// Contrato del panel «Restablecer» (Ajustes › Datos, ADR-0166) — la operación más destructiva del
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
vi.mock('../lib/runtime', () => ({
  fetchResetPlan: (...a: unknown[]) => fetchResetPlan(...a),
  resetHub: (...a: unknown[]) => resetHub(...a),
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
        resetConfirm: 'Delete permanently',
        reset_hub_settings: 'Hub settings',
        reset_hub_users: 'Employees',
      },
    },
  },
});

const PLAN = {
  sections: [
    { section: 'modules/inventory', rows: 124, blocked_by: null },
    { section: 'modules/customers', rows: 38, blocked_by: null },
    {
      section: 'modules/verifactu',
      rows: 12,
      blocked_by: '12 facturas remitidas a la AEAT: inalterables por RD 1007/2023, no se pueden borrar',
    },
    { section: 'hub_settings', rows: 7, blocked_by: null },
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

  it('ofrece exportar antes de borrar (red de seguridad de un clic)', async () => {
    const w = mountPanel();
    await flush(w);

    const backup = w.find('[data-testid="reset-export-first"]');
    expect(backup.exists()).toBe(true);
    await backup.trigger('click');
    expect(w.emitted('go-export')).toBeTruthy();
  });
});
