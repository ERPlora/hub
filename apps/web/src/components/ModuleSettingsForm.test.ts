// @vitest-environment happy-dom
// Generic module settings form (ADR-0082) — hub#959.
//
// The QA of Sales › Settings reported "the receipt/QR fields do not exist" and "the switches have
// no name". Both were the shell's doing, not the module's:
//
//   - A free `string` property rendered as `<ion-input slot="end">` with no placeholder and an
//     empty value: nothing to see, nothing to click on. The field existed; it was invisible.
//   - `<ion-toggle slot="end">` carried no accessible name, while the select and the inputs next to
//     it did. Ten switches read as "switch, switch, switch…" to a screen reader.
//
// These tests pin the renderer's contract: every control the form paints has an accessible name
// equal to the field's label, and a free-text field is visible when empty.
import { describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

vi.mock('../lib/session', async () => {
  const { ref } = await import('vue');
  return { isAdmin: ref(true) };
});
vi.mock('../lib/toast', () => ({ toastSuccess: vi.fn(), toastError: vi.fn() }));
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

const query = vi.fn(async () => [{ receipt_footer: '', print_receipt: 1 }]);
vi.mock('../lib/runtime', () => ({
  getClient: () => ({ query, command: vi.fn() }),
}));

import ModuleSettingsForm from './ModuleSettingsForm.vue';

const SCHEMA = {
  type: 'object',
  properties: {
    print_receipt: { type: 'integer', enum: [0, 1], default: 1, title: 'Imprimir tique' },
    receipt_footer: { type: 'string', default: '', title: 'Pie del recibo' },
  },
};

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: { moduleSettings: { save: 'Save', loading: 'Loading', loadError: 'Error' } } },
});

function mountForm() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({ ok: true, json: async () => SCHEMA })),
  );
  return mount(ModuleSettingsForm, {
    props: { moduleId: 'sales', settings: { schema: 'schemas/settings.json', get: 'sales.settings_get', set: 'sales.settings_update' } },
    global: { plugins: [i18n] },
  });
}

describe('every control has an accessible name', () => {
  it('names the toggle after its field, like the select and the inputs already are', async () => {
    const wrapper = mountForm();
    await flushPromises();

    const toggle = wrapper.findComponent({ name: 'IonToggle' });
    expect(toggle.exists()).toBe(true);
    expect(toggle.attributes('aria-label')).toBe('Imprimir tique');
  });
});

describe('a free-text field is visible when empty', () => {
  it('paints a placeholder so an empty string field is still a field, not blank space', async () => {
    const wrapper = mountForm();
    await flushPromises();

    const inputs = wrapper.findAllComponents({ name: 'IonInput' });
    const footer = inputs.find((i) => i.attributes('aria-label') === 'Pie del recibo');
    expect(footer, 'the string field renders an input').toBeTruthy();
    expect(footer!.props('placeholder')).toBeTruthy();
  });
});
