// @vitest-environment happy-dom
// Contrato del PROPÓSITO del bundle (ADR-0195): el panel de export debe dejar elegir entre una
// copia de seguridad y una plantilla publicable, y mandárselo al motor.
//
// 🔴 El agujero que esto cierra: ADR-0195 aterrizó en el motor (`export_hub` excluye identidades
// y fiscal cuando `purpose == Template`) pero **el front nunca enviaba `purpose`**. Con
// `#[serde(default)]` en el server, TODO export de la UI salía como `backup` — es decir, el plano
// productor estaba implementado pero era INALCANZABLE desde el producto: seguía siendo imposible
// generar una plantilla limpia sin llamar a la API a mano.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const exportHub = vi.fn();
const listInstalledModules = vi.fn();
const fetchExportTables = vi.fn();

vi.mock('../lib/runtime', () => ({
  exportHub: (...a: unknown[]) => exportHub(...a),
  listInstalledModules: (...a: unknown[]) => listInstalledModules(...a),
  fetchExportTables: (...a: unknown[]) => fetchExportTables(...a),
}));
vi.mock('../lib/session', () => ({ isAdmin: { value: true } }));
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import ExportPanel from './ExportPanel.vue';
import en from '../i18n/locales/en';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: {} },
});

function mountPanel() {
  return mount(ExportPanel, {
    shallow: true,
    global: { plugins: [i18n], renderStubDefaultSlot: true },
  });
}

/** Dispara el export y devuelve la `selection` que el panel envió al motor. */
async function selectionEnviada(w: ReturnType<typeof mountPanel>) {
  await (w.vm as unknown as { doExport: () => Promise<void> }).doExport();
  await flushPromises();
  expect(exportHub).toHaveBeenCalled();
  return exportHub.mock.calls[0][2] as Record<string, unknown>;
}

beforeEach(() => {
  exportHub.mockReset();
  exportHub.mockResolvedValue({ blob: new Blob(['x']), filename: 'hub_es.blueprint.zip' });
  listInstalledModules.mockReset();
  listInstalledModules.mockResolvedValue([]);
  fetchExportTables.mockReset();
  fetchExportTables.mockResolvedValue({ modules: [], lockedPurpose: null });
});

describe('ExportPanel · propósito del bundle (ADR-0195)', () => {
  it('por defecto exporta una COPIA DE SEGURIDAD (lo conservador: restaurar necesita identidades)', async () => {
    const w = mountPanel();
    await flushPromises();
    expect((await selectionEnviada(w)).purpose).toBe('backup');
  });

  it('al elegir PLANTILLA se lo dice al motor', async () => {
    const w = mountPanel();
    await flushPromises();
    (w.vm as unknown as Record<string, unknown>).purpose = 'template';
    await flushPromises();
    expect((await selectionEnviada(w)).purpose).toBe('template');
  });

  it('en modo PLANTILLA la UI no ofrece marcar identidades ni fiscal (no son negociables)', async () => {
    const w = mountPanel();
    await flushPromises();
    (w.vm as unknown as Record<string, unknown>).purpose = 'template';
    await flushPromises();

    // Una casilla que el motor va a ignorar es una mentira: no se pinta.
    expect(w.find('[data-testid="export-section-users"]').exists()).toBe(false);
    expect(w.find('[data-testid="export-section-fiscal"]').exists()).toBe(false);
  });

  it('en modo COPIA sí se pueden marcar (un backup sin usuarios pierde roles y PINs)', async () => {
    const w = mountPanel();
    await flushPromises();
    expect(w.find('[data-testid="export-section-users"]').exists()).toBe(true);
  });
});

describe('ExportPanel · error accionable ante fallo (hub#765)', () => {
  // El export ahora tiene deadline: si el runtime no responde, el fetch aborta y exportHub rechaza
  // con `export → timeout`. El panel debe traducir ese mensaje interno a una frase que el usuario
  // pueda accionar (reintentar), no dejar el identificador técnico en pantalla.
  it('un timeout del runtime se muestra con la cadena traducida, no con el mensaje crudo', async () => {
    exportHub.mockRejectedValue(new Error('export → timeout'));
    const w = mountPanel();
    await flushPromises();

    await (w.vm as unknown as { doExport: () => Promise<void> }).doExport();
    await flushPromises();

    const err = w.find('[data-testid="export-error"]');
    expect(err.exists()).toBe(true);
    // La cadena traducida (no el identificador `export → timeout`) es lo que llega al usuario.
    expect(err.text()).not.toContain('export → timeout');
    expect(err.text().length).toBeGreaterThan('export → timeout'.length);
  });

  it('un error del servidor conserva su mensaje HONESTO (no se aplana a genérico)', async () => {
    exportHub.mockRejectedValue(new Error('disk full'));
    const w = mountPanel();
    await flushPromises();

    await (w.vm as unknown as { doExport: () => Promise<void> }).doExport();
    await flushPromises();

    expect(w.find('[data-testid="export-error"]').text()).toContain('disk full');
  });
});


describe('ExportPanel · casillas por TABLA (hub#534)', () => {
  const conInventory = () => {
    listInstalledModules.mockResolvedValue([{ id: 'inventory', name: 'Inventory', version: '1.0.0' }]);
    fetchExportTables.mockResolvedValue({
      modules: [
        {
          module_id: 'inventory',
          tables: [
            { table: 'inventory_product', rows: 280 },
            { table: 'inventory_stock_movement', rows: 1240 },
          ],
        },
      ],
      lockedPurpose: null,
    });
  };

  it('sin tocar nada manda `tables: null` — «todas», que es lo que significaba antes', async () => {
    // El campo es una ADICIÓN: un formulario que no lo usa tiene que exportar exactamente igual.
    conInventory();
    const w = mountPanel();
    await flushPromises();

    const selection = await selectionEnviada(w);
    expect((selection.modules as { tables: unknown }[])[0].tables).toBeNull();
  });

  it('desmarcar una tabla la deja fuera y manda SOLO las que quedan', async () => {
    // Es el caso real: las 4 plantillas publicadas llevaban 25-28 citas pasadas y los ajustes de
    // agenda del salón de origen porque no había forma de dejarlos fuera sin tocar código.
    conInventory();
    const w = mountPanel();
    await flushPromises();

    // «datos» es opt-in por fila: sin marcarlo no hay tablas que elegir.
    const vm = w.vm as unknown as {
      toggleTable: (m: string, t: string) => void;
      rows: { id: string; withData: boolean }[];
    };
    vm.rows = vm.rows.map((r) => ({ ...r, withData: true }));
    vm.toggleTable('inventory', 'inventory_stock_movement');
    await flushPromises();
    const selection = await selectionEnviada(w);

    expect((selection.modules as { tables: string[] }[])[0].tables).toEqual(['inventory_product']);
  });

  it('enseña el RECUENTO de filas: sin el número la lista no es una decisión', async () => {
    conInventory();
    const w = mountPanel();
    await flushPromises();

    const vm = w.vm as unknown as { tablesOf: (m: string) => { table: string; rows: number }[] };
    expect(vm.tablesOf('inventory')).toEqual([
      { table: 'inventory_product', rows: 280 },
      { table: 'inventory_stock_movement', rows: 1240 },
    ]);
  });
});


describe('ExportPanel · el hub puede tener el propósito ATADO (hub#1249)', () => {
  // 🔴 Regression test for ERPlora/hub#1249. Un hub de dev sin enrolar o una demo efímera exporta
  // SIEMPRE como plantilla (hub#377): el servidor cambia el `purpose` después de que el formulario
  // se haya pintado. El panel ofrecía «copia de seguridad» con «usuarios» marcado y devolvía un zip
  // sin usuarios, sin un solo aviso — una copia que parece hecha y no lo está.
  const atado = () =>
    fetchExportTables.mockResolvedValue({ modules: [], lockedPurpose: 'template' });

  it('con el propósito atado el panel exporta como PLANTILLA sin que nadie lo toque', async () => {
    atado();
    const w = mountPanel();
    await flushPromises();

    expect((await selectionEnviada(w)).purpose).toBe('template');
  });

  it('con el propósito atado NO se ofrecen identidades ni fiscal (el motor las va a ignorar)', async () => {
    atado();
    const w = mountPanel();
    await flushPromises();

    expect(w.find('[data-testid="export-section-users"]').exists()).toBe(false);
    expect(w.find('[data-testid="export-section-fiscal"]').exists()).toBe(false);
  });

  it('y lo DICE: la nota explica por qué no se puede elegir', async () => {
    atado();
    const w = mountPanel();
    await flushPromises();

    expect(w.find('[data-testid="export-purpose-locked"]').exists()).toBe(true);
  });

  it('un hub normal sigue eligiendo: ni nota ni casillas escondidas', async () => {
    const w = mountPanel();
    await flushPromises();

    expect(w.find('[data-testid="export-purpose-locked"]').exists()).toBe(false);
    expect(w.find('[data-testid="export-section-users"]').exists()).toBe(true);
    expect((await selectionEnviada(w)).purpose).toBe('backup');
  });
});

describe('ExportPanel · el propósito atado se queda atado tras un clic (hub#1249, revisión)', () => {
  // 🔴 Regression test for ERPlora/hub#1249 (review). `ion-radio-group` has NO `disabled` prop in
  // Ionic 8 (only `ion-radio` does), so a `:disabled` on the group is a no-op: one click on «backup»
  // flipped `purpose`, the users/fiscal boxes came back and the server silently forced `template`
  // again — the exact lie this fix removes. The lock has to live on each radio.
  const atado = () =>
    fetchExportTables.mockResolvedValue({ modules: [], lockedPurpose: 'template' });

  it('con el propósito atado CADA radio está desactivado', async () => {
    atado();
    const w = mountPanel();
    await flushPromises();

    const radios = w.findAll('[data-testid="export-purpose"] ion-radio-stub');
    expect(radios.length).toBe(2);
    for (const r of radios) expect(r.attributes('disabled')).toBe('true');
  });

  it('un hub normal no tiene ningún radio desactivado', async () => {
    const w = mountPanel();
    await flushPromises();

    const radios = w.findAll('[data-testid="export-purpose"] ion-radio-stub');
    expect(radios.length).toBe(2);
    for (const r of radios) expect(r.attributes('disabled')).not.toBe('true');
  });
});

// ── hub#1693 · el código del runtime NUNCA llega a la pantalla ───────────────────────────────
//
// El export habla con el runtime local, pero su cuerpo de error atraviesa el mismo lector
// (`readErrorMessage`) que las puertas proxy: si lo que vuelve es un código estable
// (`cloud_unreachable` desde hub#1689), el panel lo pintaba tal cual.
describe('ExportPanel · el aviso de error es una frase, nunca un código', () => {
  const i18nReal = createI18n({
    legacy: false,
    locale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages: { en },
  });

  function mountReal() {
    return mount(ExportPanel, {
      shallow: true,
      global: { plugins: [i18nReal], renderStubDefaultSlot: true },
    });
  }

  it('traduce el código estable que devolvió el runtime', async () => {
    exportHub.mockRejectedValue(new Error('cloud_unreachable'));
    const w = mountReal();
    await flushPromises();
    await (w.vm as unknown as { doExport: () => Promise<void> }).doExport();
    await flushPromises();

    const shown = w.get('[data-testid="export-error"]').text();
    expect(shown).toContain(en.runtimeErrors.cloud_unreachable);
    expect(shown).not.toContain('cloud_unreachable');
  });

  it('conserva la frase del server cuando el server dijo una frase', async () => {
    exportHub.mockRejectedValue(new Error('no hay espacio en disco para empaquetar el hub'));
    const w = mountReal();
    await flushPromises();
    await (w.vm as unknown as { doExport: () => Promise<void> }).doExport();
    await flushPromises();

    expect(w.get('[data-testid="export-error"]').text()).toContain(
      'no hay espacio en disco para empaquetar el hub',
    );
  });

  it('el timeout sigue teniendo su propia frase (hub#765)', async () => {
    // Guardia de no-regresión: el deadline del export ya se traducía, y pasar por el traductor
    // de códigos no puede robarle su sentencia — `export → timeout` no es un código.
    exportHub.mockRejectedValue(new Error('export → timeout'));
    const w = mountReal();
    await flushPromises();
    await (w.vm as unknown as { doExport: () => Promise<void> }).doExport();
    await flushPromises();

    expect(w.get('[data-testid="export-error"]').text()).toContain(en.exportPage.timeout);
  });
});
