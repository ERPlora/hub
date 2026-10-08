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
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

vi.mock('../lib/session', async () => {
  const { ref } = await import('vue');
  return { isAdmin: ref(true), hasPermission: () => false };
});
vi.mock('../lib/toast', () => ({ toastSuccess: vi.fn(), toastError: vi.fn() }));
vi.mock('./HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
// `module-loader` (whence `loadModuleLocale` comes) pulls the icon sidecar registry, and the
// `~icons/*` virtual ids are a build-time plugin the test env has no business resolving. Same
// three stubs `module-loader.test.ts` already uses.
vi.mock('../lib/icons', () => ({ moduleIconRegistry: (i: Record<string, string>) => i }));
vi.mock('ionicons', () => ({ addIcons: () => {} }));
vi.mock('../lib/entitlement', () => ({ isModuleEntitled: () => true }));

// hub#1426 — the two doors the form uses to mount a module-provided preview element. `vi.hoisted`
// because `vi.mock` runs before every other statement in the file: a plain `const` would still be
// in its temporal dead zone when the factory below is evaluated.
const { loadInstalledManifests, loadModuleComponent } = vi.hoisted(() => ({
  loadInstalledManifests: vi.fn(async () => [
    { moduleId: 'kitchen-1426', manifest: {}, entryUrl: '/modules/kitchen-1426/dist/x.esm.js' },
  ]),
  loadModuleComponent: vi.fn(async (_mod: unknown, tag: string) => tag),
}));
vi.mock('../lib/module-loader', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../lib/module-loader')>()),
  loadInstalledManifests,
  loadModuleComponent,
}));

const query = vi.fn(async (): Promise<Record<string, unknown>[]> => [{ receipt_footer: '', print_receipt: 1 }]);
const command = vi.fn(async () => undefined);
// `forModule` is what the real client hands a module-owned Web Component (the same scoped client
// the `settings.component` escape-hatch gets); a preview element receives it too.
const forModule = vi.fn((id: string) => ({ id, query, command }));
vi.mock('../lib/runtime', () => ({
  getClient: () => ({ query, command, forModule }),
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
      // The re-labelling test switches the SAME instance to `en`: without an `en` bundle the
      // locale type is inferred as the literal `'es'` and `vue-tsc` refuses the switch.
      en: {
        moduleSettings: {
          save: 'Save',
          loading: 'Loading',
          loadError: 'Error',
          saveError: 'Could not save settings.',
          invalidFields: 'Check the fields marked below.',
          fieldInvalid: 'This value is not accepted.',
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

  it('re-labels the mounted screen when the hub language changes (ADR-0055, hub#781)', async () => {
    const KITCHEN_EN = {
      settings: { fields: { warning_time_minutes: { label: 'Amber warning (minutes)' } } },
    };
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).endsWith('/locales/es.json')) return { ok: true, json: async () => KITCHEN_ES };
        if (String(url).endsWith('/locales/en.json')) return { ok: true, json: async () => KITCHEN_EN };
        return { ok: true, json: async () => KITCHEN_SCHEMA };
      }),
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
      },
      global: { plugins: [es] },
    });
    await flushPromises();
    expect(wrapper.html()).toContain('Aviso ámbar (minutos)');

    // Same screen, still open: the person switches the hub to English from the profile.
    es.global.locale.value = 'en';
    await flushPromises();

    expect(wrapper.html()).toContain('Amber warning (minutes)');
    expect(wrapper.html()).not.toContain('Aviso ámbar (minutos)');
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

// ── hub#1427 ────────────────────────────────────────────────────────────────────────────────
//
// The other half of hub#1094. The LABEL of a field is read from the module locale; the OPTIONS of
// an `enum` were printed raw, so a Spanish cook was offered `dine_in · takeaway · delivery`. The
// module had nowhere to translate them: the JSON Schema is canonical English (ADR-0055) and the
// stored value must not change.
describe('hub#1427 · the options of an enum are painted in the hub language', () => {
  const SCHEMA = {
    type: 'object',
    properties: {
      // Two enums ON PURPOSE: one the module translates, one it does not. That is the positive
      // control — it proves the fallback is a fallback and not "nothing is translated".
      default_order_type: { type: 'string', enum: ['dine_in', 'takeaway'], default: 'dine_in' },
      sound_tone: { type: 'string', enum: ['chime', 'buzzer'], default: 'chime' },
    },
  };
  const ES = {
    settings: {
      fields: {
        default_order_type: {
          label: 'Tipo de comanda por defecto',
          options: { dine_in: 'En sala', takeaway: 'Para llevar' },
        },
        sound_tone: { label: 'Tono del sonido' },
      },
    },
  };

  const es = createI18n({
    legacy: false,
    locale: 'es',
    missingWarn: false,
    fallbackWarn: false,
    messages: { es: { moduleSettings: { save: 'Guardar', loading: 'Cargando', loadError: 'Error' } } },
  });

  function mountKitchen() {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        String(url).endsWith('/locales/es.json')
          ? { ok: true, json: async () => ES }
          : { ok: true, json: async () => SCHEMA },
      ),
    );
    // A module id of its OWN: `loadModuleLocale` memoizes per URL (`readOnce`), so reusing
    // `kitchen` here would read the locale the hub#1094 block above already cached — and this
    // block would silently assert against somebody else's fixture.
    return mount(ModuleSettingsForm, {
      props: {
        moduleId: 'kitchen-1427',
        settings: { schema: 'schemas/settings.json', get: 'kitchen.settings.get', set: 'kitchen.settings.update' },
      },
      global: { plugins: [es] },
    });
  }

  it('paints a translated option translated, and one without translation raw — both on the same screen', async () => {
    const wrapper = mountKitchen();
    await flushPromises();

    const html = wrapper.html();
    expect(html, 'the translated option shows its translation').toContain('En sala');
    expect(html, 'and its sibling too').toContain('Para llevar');
    expect(html, 'the raw value must not survive a translated enum').not.toContain('dine_in');
    // Positive control: the enum the module did NOT translate still paints, with its raw value.
    expect(html, 'an untranslated option falls back to the raw value').toContain('chime');
  });

  it('keeps the stored value on the enum, not the label', async () => {
    const wrapper = mountKitchen();
    await flushPromises();

    const option = wrapper
      .findAllComponents({ name: 'IonSelectOption' })
      .find((o) => o.text().includes('En sala'));
    expect(option, 'the translated option renders').toBeTruthy();
    expect(option!.props('value')).toBe('dine_in');
  });
});

// ── hub#1426 ────────────────────────────────────────────────────────────────────────────────
//
// The generic form painted one control per property and nothing else, so a setting you can only
// judge by HEARING it (`kitchen`'s KDS volume/tone, ERPlora/kitchen#72) was regulated blind: save,
// walk to the pass, wait for an order, come back. Every till and KDS in the market (Square, Fresh
// KDS, Loyverse…) puts a "Test" next to the volume, because nobody sets a volume without hearing it.
//
// The shell paints the button; the MODULE owns what it does — the shell knows nothing about sound.
describe('hub#1426 · a module can offer a TEST action next to one of its settings', () => {
  const WITH_PREVIEW = {
    type: 'object',
    properties: {
      sound_volume: { type: 'integer', default: 60, 'x-erplora-preview': 'erp-kitchen-sound-preview' },
      warning_time_minutes: { type: 'integer', default: 15 },
    },
  };
  const WITHOUT_PREVIEW = {
    type: 'object',
    properties: {
      sound_volume: { type: 'integer', default: 60 },
      warning_time_minutes: { type: 'integer', default: 15 },
    },
  };

  /** What the module ships: a custom element whose only job is to perform the preview. */
  const previews: { key: string; value: unknown; settings: Record<string, unknown> }[] = [];
  let previewThrows = false;

  class SoundPreview extends HTMLElement {
    preview(detail: { key: string; value: unknown; settings: Record<string, unknown> }): void {
      if (previewThrows) throw new Error('no audio device');
      previews.push(detail);
    }
  }
  if (!customElements.get('erp-kitchen-sound-preview')) {
    customElements.define('erp-kitchen-sound-preview', SoundPreview);
  }

  const en = createI18n({
    legacy: false,
    locale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages: {
      en: {
        moduleSettings: {
          save: 'Save',
          loading: 'Loading',
          loadError: 'Error',
          preview: 'Test',
          previewError: 'Could not run the test.',
        },
      },
    },
  });

  function mountKitchen(schema: unknown) {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, json: async () => schema })),
    );
    return mount(ModuleSettingsForm, {
      props: {
        moduleId: 'kitchen-1426',
        settings: {
          schema: 'schemas/settings.json',
          get: 'kitchen.settings.get',
          set: 'kitchen.settings.update',
        },
      },
      global: { plugins: [en] },
    });
  }

  beforeEach(() => {
    previews.length = 0;
    previewThrows = false;
    loadModuleComponent.mockClear();
    // `command` is shared with the describes above, which do press Save: without clearing it the
    // "a preview never saves" control would count somebody else's calls.
    command.mockClear();
    query.mockResolvedValue([{ sound_volume: 60, warning_time_minutes: 15 }]);
  });

  it('hands the module the value that is IN THE FORM, not the one on the row, and saves nothing', async () => {
    const wrapper = mountKitchen(WITH_PREVIEW);
    await flushPromises();

    // The person drags the volume to 25 and presses Test WITHOUT saving.
    const volume = wrapper
      .findAllComponents({ name: 'IonInput' })
      .find((i) => i.attributes('aria-label') === 'Sound Volume');
    expect(volume, 'the number field renders').toBeTruthy();
    volume!.vm.$emit('ionInput', { detail: { value: '25' } });
    await flushPromises();

    const button = wrapper
      .findAllComponents({ name: 'IonButton' })
      .find((b) => b.text().includes('Test'));
    expect(button, 'the shell paints the test button the module declared').toBeTruthy();
    await button!.trigger('click');
    await flushPromises();

    expect(previews.length, 'the module was asked exactly once').toBe(1);
    expect(previews[0].key).toBe('sound_volume');
    expect(previews[0].value, 'the UNSAVED value, not the stored 60').toBe(25);
    // Positive control: the stored row is still 60 — nothing was persisted to make the test work.
    expect(previews[0].settings.sound_volume).toBe(25);
    expect(command, 'a preview never saves').not.toHaveBeenCalled();
  });

  it('paints exactly the form of today for a module that declares no preview', async () => {
    const wrapper = mountKitchen(WITHOUT_PREVIEW);
    await flushPromises();

    const buttons = wrapper.findAllComponents({ name: 'IonButton' });
    expect(buttons.some((b) => b.text().includes('Test'))).toBe(false);
    expect(buttons.length, 'only Save').toBe(1);
    expect(loadModuleComponent, 'no module bundle is loaded for a form without previews').not.toHaveBeenCalled();
  });

  it('says out loud when the preview fails instead of swallowing it', async () => {
    const { toastError } = await import('../lib/toast');
    previewThrows = true;
    const wrapper = mountKitchen(WITH_PREVIEW);
    await flushPromises();

    await wrapper
      .findAllComponents({ name: 'IonButton' })
      .find((b) => b.text().includes('Test'))!
      .trigger('click');
    await flushPromises();

    expect(toastError).toHaveBeenCalled();
  });

  it('does not paint a test button for a property whose tag the module did not declare', async () => {
    const wrapper = mountKitchen(WITH_PREVIEW);
    await flushPromises();

    // One preview declared ⇒ exactly one Test button, next to that field and not to its neighbour.
    const tests = wrapper.findAllComponents({ name: 'IonButton' }).filter((b) => b.text().includes('Test'));
    expect(tests.length).toBe(1);
  });
});

// ── hub#2511 ────────────────────────────────────────────────────────────────────────────────
//
// A failed READ of the stored values (a network blink, the hub restarting, a 5xx) was swallowed:
// `query(get).catch(() => null)` left `current = null`, every field took the schema `default`, and
// the screen looked exactly like the business's settings. An administrator pressing «Save» then
// sent that whole snapshot of factory values and overwrote everything stored — in Caja, «Enable
// the cash drawer» came back on/off at the schema's whim. What the market does (Square, Shopify,
// Odoo): a screen that could not read says so, offers «Retry», and never offers to save.
describe('hub#2511 · a settings screen whose values could not be read never shows nor saves factory values', () => {
  // Stored values that differ from every schema default, so «factory values» is observable.
  const STORED = { print_receipt: 0, receipt_footer: 'Gracias por su visita' };

  beforeEach(() => {
    query.mockReset();
    command.mockClear();
  });

  it('shows «could not read» with Retry instead of the form, and offers no Save', async () => {
    query.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    const wrapper = mountForm();
    await flushPromises();

    expect(wrapper.find('[data-testid="module-settings-error"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="module-settings-retry"]').exists()).toBe(true);
    expect(wrapper.findComponent({ name: 'IonToggle' }).exists(), 'no factory value on screen').toBe(false);
    expect(wrapper.find('[data-testid="module-settings-save"]').exists(), 'nothing to save over').toBe(false);
    expect(command).not.toHaveBeenCalled();
  });

  it('treats a server error on the read the same way (the hub restarting, a 5xx)', async () => {
    const { ErploraError } = await import('@erplora/module-sdk');
    query.mockRejectedValueOnce(new ErploraError('internal', 'boom'));
    const wrapper = mountForm();
    await flushPromises();

    expect(wrapper.find('[data-testid="module-settings-retry"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="module-settings-save"]').exists()).toBe(false);
  });

  it('Retry reads again and, once read, saving keeps the stored values of every untouched field', async () => {
    query.mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce([STORED]);
    const wrapper = mountForm();
    await flushPromises();

    await wrapper.find('[data-testid="module-settings-retry"]').trigger('click');
    await flushPromises();
    expect(query).toHaveBeenCalledTimes(2);

    // The administrator changes ONE field…
    const footer = wrapper
      .findAllComponents({ name: 'IonInput' })
      .find((i) => i.attributes('aria-label') === 'Pie del recibo');
    footer!.vm.$emit('ionInput', { detail: { value: 'Hasta pronto' } });
    await wrapper.find('[data-testid="module-settings-save"]').trigger('click');
    await flushPromises();

    // …and the other one travels with the value that was READ, never with the schema default (1).
    expect(command).toHaveBeenCalledTimes(1);
    expect(command).toHaveBeenCalledWith('sales.settings_update', {
      print_receipt: 0,
      receipt_footer: 'Hasta pronto',
    });
  });

  // `requires_elevation` (hub#360) is also a refusal of the PERSON: retrying will not change it.
  it.each(['permission_denied', 'requires_elevation'])(
    'says the person may not see these settings, without a Retry that cannot help (%s)',
    async (code) => {
    const { ErploraError } = await import('@erplora/module-sdk');
    query.mockRejectedValueOnce(new ErploraError(code, 'requires sales.manage_settings'));
    const wrapper = mountForm();
    await flushPromises();

    expect(wrapper.find('[data-testid="module-settings-no-permission"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="module-settings-retry"]').exists()).toBe(false);
    expect(wrapper.findComponent({ name: 'IonToggle' }).exists()).toBe(false);
    expect(wrapper.find('[data-testid="module-settings-save"]').exists()).toBe(false);
    },
  );

  it('a read that succeeds with NO row yet is a first save: the defaults show and can be saved', async () => {
    query.mockResolvedValueOnce([]);
    const wrapper = mountForm();
    await flushPromises();

    expect(wrapper.find('[data-testid="module-settings-error"]').exists()).toBe(false);
    await wrapper.find('[data-testid="module-settings-save"]').trigger('click');
    await flushPromises();
    expect(command).toHaveBeenCalledWith('sales.settings_update', { print_receipt: 1, receipt_footer: '' });
  });
});
