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
// `module-loader` (whence `loadModuleLocale` comes) pulls the icon sidecar registry, and the
// `~icons/*` virtual ids are a build-time plugin the test env has no business resolving. Same
// three stubs `module-loader.test.ts` already uses.
vi.mock('../lib/icons', () => ({ moduleIconRegistry: (i: Record<string, string>) => i }));
vi.mock('ionicons', () => ({ addIcons: () => {} }));
vi.mock('../lib/entitlement', () => ({ isModuleEntitled: () => true }));

const query = vi.fn(async () => [{ receipt_footer: '', print_receipt: 1 }]);
const command = vi.fn(async () => undefined);
vi.mock('../lib/runtime', () => ({
  getClient: () => ({ query, command }),
  RUNTIME_URL: '',
  runtimeHeaders: () => ({}),
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

// ── hub#1094 ────────────────────────────────────────────────────────────────────────────────
//
// The Settings screen the shell generates for ANY module came out entirely in English on a Spanish
// hub, and it swallowed the 422: press «Save», the request comes back `invalid_payload`, and the
// screen stays exactly as it was.
//
// Both halves are the renderer's doing. It read the JSON Schema — a canonical-English artefact
// (ADR-0055) — and never the module's `locales/`, which `kitchen` and `tables` had been shipping
// for weeks under `settings.title` / `settings.fields.<key>.label`. And the save path caught every
// failure into one generic toast, so nothing on screen said which field the runtime refused.
describe('hub#1094 · the generic settings screen speaks the hub language and shows its refusals', () => {
  const KITCHEN_SCHEMA = {
    type: 'object',
    properties: {
      warning_time_minutes: { type: 'integer' },
      auto_accept_orders: { type: 'boolean' },
    },
  };
  const KITCHEN_ES = {
    settings: {
      title: 'Cocina',
      fields: {
        warning_time_minutes: {
          label: 'Aviso ámbar (minutos)',
          description: 'Cuándo la comanda se pone ámbar',
        },
        auto_accept_orders: { label: 'Aceptar comandas automáticamente' },
      },
    },
  };

  const es = createI18n({
    legacy: false,
    locale: 'es',
    missingWarn: false,
    fallbackWarn: false,
    messages: {
      es: {
        moduleSettings: {
          save: 'Guardar',
          loading: 'Cargando',
          loadError: 'Error',
          saveError: 'No se pudieron guardar los ajustes.',
          invalidFields: 'Revisa los campos marcados.',
          fieldInvalid: 'Este valor no vale.',
        },
      },
    },
  });

  function mountKitchen() {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).endsWith('/locales/es.json')) {
          return { ok: true, json: async () => KITCHEN_ES };
        }
        return { ok: true, json: async () => KITCHEN_SCHEMA };
      }),
    );
    return mount(ModuleSettingsForm, {
      props: {
        moduleId: 'kitchen',
        settings: {
          title: 'Kitchen',
          schema: 'schemas/settings_update.json',
          get: 'kitchen.settings.get',
          set: 'kitchen.settings.update',
        },
      },
      global: { plugins: [es] },
    });
  }

  it('labels the fields from the module locale, not from the schema nor from the column name', async () => {
    const wrapper = mountKitchen();
    await flushPromises();

    // `html()` and not `text()`: Ionic's components put the item body behind a shadow root that
    // happy-dom does not flatten, so `textContent` sees only the shell's own nodes.
    const html = wrapper.html();
    expect(html).toContain('Aviso ámbar (minutos)');
    expect(html).toContain('Aceptar comandas automáticamente');
    // The humanized column name is the last resort and must not survive a translated module.
    expect(html).not.toContain('Warning Time Minutes');
    expect(html).not.toContain('Auto Accept Orders');
  });

  it('shows the translated help text of a field', async () => {
    const wrapper = mountKitchen();
    await flushPromises();
    expect(wrapper.html()).toContain('Cuándo la comanda se pone ámbar');
  });

  it('paints the heading of the screen translated (`settings.title` of the locale, not the manifest)', async () => {
    const wrapper = mountKitchen();
    await flushPromises();
    expect(wrapper.get('.settings-heading').text()).toBe('Cocina');
  });

  it('does not repeat the heading when the bar of the screen already says the same', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        String(url).endsWith('/locales/es.json')
          ? { ok: true, json: async () => KITCHEN_ES }
          : { ok: true, json: async () => KITCHEN_SCHEMA },
      ),
    );
    const wrapper = mount(ModuleSettingsForm, {
      props: {
        moduleId: 'kitchen',
        settings: {
          title: 'Kitchen',
          schema: 'schemas/settings_update.json',
          get: 'kitchen.settings.get',
          set: 'kitchen.settings.update',
        },
        // What `ModuleView` shows in the topbar: the module's localised name — the same word.
        pageTitle: 'Cocina',
      },
      global: { plugins: [es] },
    });
    await flushPromises();
    expect(wrapper.find('.settings-heading').exists()).toBe(false);
  });

  it('keeps the 422 on screen and marks the fields the runtime refused', async () => {
    const { ErploraError } = await import('@erplora/module-sdk');
    command.mockRejectedValueOnce(
      new ErploraError('invalid_payload', 'payload inválido para `kitchen.settings.update`: …', undefined, [
        'warning_time_minutes',
      ]),
    );
    const wrapper = mountKitchen();
    await flushPromises();

    await wrapper.findComponent({ name: 'IonButton' }).trigger('click');
    await flushPromises();

    // A banner, not a toast: it is actionable and has to survive long enough to be read.
    const banner = wrapper.find('ok-inline-feedback');
    expect(banner.exists(), 'the refusal stays on screen').toBe(true);
    expect(banner.text()).toContain('Revisa los campos marcados.');

    // And the control the runtime named is marked, so «which field» is answerable.
    const number = wrapper
      .findAllComponents({ name: 'IonInput' })
      .find((i) => i.attributes('aria-label') === 'Aviso ámbar (minutos)');
    expect(number, 'the refused field renders').toBeTruthy();
    expect(number!.attributes('aria-invalid')).toBe('true');
  });

  it('shows what the server said when the refusal names no field, instead of swallowing it', async () => {
    const { ErploraError } = await import('@erplora/module-sdk');
    command.mockRejectedValueOnce(new ErploraError('permission_denied', 'no puedes tocar esto'));
    const wrapper = mountKitchen();
    await flushPromises();

    await wrapper.findComponent({ name: 'IonButton' }).trigger('click');
    await flushPromises();

    expect(wrapper.find('ok-inline-feedback').text()).toContain('no puedes tocar esto');
  });

  it('clears the previous refusal when the next save succeeds', async () => {
    const { ErploraError } = await import('@erplora/module-sdk');
    command.mockRejectedValueOnce(new ErploraError('invalid_payload', 'malo', undefined, ['warning_time_minutes']));
    const wrapper = mountKitchen();
    await flushPromises();

    const button = wrapper.findComponent({ name: 'IonButton' });
    await button.trigger('click');
    await flushPromises();
    expect(wrapper.find('ok-inline-feedback').exists()).toBe(true);

    await button.trigger('click');
    await flushPromises();
    expect(wrapper.find('ok-inline-feedback').exists()).toBe(false);
  });
});
