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

vi.mock('../lib/runtime', () => ({
  exportHub: (...a: unknown[]) => exportHub(...a),
  listInstalledModules: (...a: unknown[]) => listInstalledModules(...a),
}));
vi.mock('../lib/session', () => ({ isAdmin: { value: true } }));
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import ExportPanel from './ExportPanel.vue';

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
