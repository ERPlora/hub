// @vitest-environment happy-dom
// The approval dialog says WHAT is being approved (hub#579).
//
// It used to print «Hace falta una aprobación» and nothing else: the manager typed their PIN
// without knowing what for, which turns the receipt (`approved_by`) into a rubber stamp. Every POS
// that asks for a manager names the action — Toast, Square and Lightspeed all do.
//
// What it must NOT do is undo hub#363: the permission key and the command name are our vocabulary,
// not the counter's, and they must never reach the screen — not even as a fallback.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

vi.mock('../lib/module-loader', () => ({ loadInstalledManifests: vi.fn(async () => []) }));
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import ElevationDialog from './ElevationDialog.vue';
import { pendingElevation } from '../lib/elevation';
import { loadInstalledManifests } from '../lib/module-loader';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      elevation: {
        title: 'An approval is needed',
        lead: 'Ask a manager to enter their PIN.',
        orSwipeBadge: '…or swipe their badge.',
        chooseApprover: 'Who approves?',
        approverName: 'Their name',
        approverNamePlaceholder: 'Type their name',
        continue: 'Continue',
        cancel: 'Cancel',
        what: 'To approve: {action}',
        whatFromModule: 'To approve: an action in {app}',
        whatUnknown: 'To approve: an action this app cannot name',
      },
    },
  },
});

function ask(command = 'sales.void') {
  return {
    command,
    permission: 'sales.void_sale',
    payload: { sale_id: 's-1' },
    approve: vi.fn(),
    approveWithBadge: vi.fn(),
  } as never;
}

async function mountDialog() {
  const wrapper = mount(ElevationDialog, {
    // shallow + `renderStubDefaultSlot`: igual que `ElevationDialog.test.ts`. Sin ello el contenido
    // del `ion-modal` no llega al DOM en happy-dom y el test mediría el vacío.
    shallow: true,
    global: {
      plugins: [i18n],
      renderStubDefaultSlot: true,
      config: { compilerOptions: { isCustomElement: (tag: string) => tag.startsWith('ok-') } },
    },
  });
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  pendingElevation.value = null;
  vi.mocked(loadInstalledManifests).mockResolvedValue([]);
});

describe('what the manager is approving', () => {
  it('names the action in the words the module translated', async () => {
    vi.mocked(loadInstalledManifests).mockResolvedValue([
      {
        moduleId: 'sales',
        manifest: { name: 'Sales & POS' },
        entryUrl: '',
        locale: { name: 'Ventas / TPV', commands: { 'sales.void': { label: 'Anular una venta' } } },
      },
    ] as never);
    const wrapper = await mountDialog();
    pendingElevation.value = ask();
    await flushPromises();

    expect(wrapper.get('[data-testid="elevation-what"]').text()).toContain('Anular una venta');
  });

  it('falls back to the app name, and never to the command or the permission', async () => {
    vi.mocked(loadInstalledManifests).mockResolvedValue([
      { moduleId: 'sales', manifest: { name: 'Sales & POS' }, entryUrl: '', locale: { name: 'Ventas / TPV' } },
    ] as never);
    const wrapper = await mountDialog();
    pendingElevation.value = ask('sales.discount');
    await flushPromises();

    const shown = wrapper.get('[data-testid="elevation-what"]').text();
    expect(shown).toContain('Ventas / TPV');
    expect(shown).not.toContain('sales.discount');
    expect(shown).not.toContain('void_sale');
  });

  it('with nothing to go on, says so instead of leaking our vocabulary', async () => {
    const wrapper = await mountDialog();
    pendingElevation.value = ask('mystery.act');
    await flushPromises();

    const shown = wrapper.get('[data-testid="elevation-what"]').text();
    expect(shown).toContain('cannot name');
    expect(wrapper.html()).not.toContain('mystery.act');
    expect(wrapper.html()).not.toContain('void_sale');
  });
});
