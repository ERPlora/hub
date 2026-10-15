/* eslint-disable vue/one-component-per-file -- one throwaway host component per case */
// `useT()`: the shell's translator from a component's script, the same `$t` its template uses, so a text
// built in script follows the language too; `useLocale()`: the app language, live.
import { createShellI18n } from '@erplora/ui/shell';
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import { computed, defineComponent, h } from 'vue';

import en from '../locale/en.json';
import es from '../locale/es.json';
import { useLocale, useT } from './useT';

describe('useT', () => {
  it('translates in the app language, with named values, and follows a change of language', async () => {
    const i18n = createShellI18n({ locale: 'en', messages: { en, es } });
    const wrapper = mount(
      defineComponent({
        setup() {
          const t = useT();
          const text = computed(() => `${t('printing.title')} · ${t('printing.printers.tested', { name: 'Kitchen' })}`);
          return () => h('p', text.value);
        },
      }),
      { global: { plugins: [i18n] } },
    );
    expect(wrapper.text()).toBe('Printing · Test page sent to the queue of Kitchen.');
    i18n.global.locale.value = 'es';
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toBe('Impresión · Hoja de prueba enviada a la cola de Kitchen.');
  });

  it('only works inside a component, which is where the app’s translator lives', () => {
    expect(() => useT()).toThrow(/setup/);
    expect(() => useLocale()).toThrow(/setup/);
  });

  it('useLocale: the app language, live', async () => {
    const i18n = createShellI18n({ locale: 'en', messages: { en, es } });
    const wrapper = mount(
      defineComponent({
        setup() {
          const locale = useLocale();
          return () => h('p', locale.value);
        },
      }),
      { global: { plugins: [i18n] } },
    );
    expect(wrapper.text()).toBe('en');
    i18n.global.locale.value = 'es';
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toBe('es');
  });
});
