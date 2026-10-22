// `useT()`: the shell's translator from a component's script (a confirmation's texts, a label built in code), the
// same `$t` its template uses, so a text built in script follows the language too.
import { createShellI18n } from '@erplora/ui/shell';
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import { computed, defineComponent, h } from 'vue';

import en from '../locale/en.json';
import es from '../locale/es.json';
import { useT } from './useT';

describe('useT', () => {
  it('translates in the app language, with named values, and follows a change of language', async () => {
    const i18n = createShellI18n({ locale: 'en', messages: { en, es } });
    const wrapper = mount(
      defineComponent({
        setup() {
          const t = useT();
          const text = computed(() => `${t('website.title')} · ${t('website.status.live', { url: 'https://a.erplora.com/' })}`);
          return () => h('p', text.value);
        },
      }),
      { global: { plugins: [i18n] } },
    );
    expect(wrapper.text()).toBe('Website · Your website is online at https://a.erplora.com/');
    i18n.global.locale.value = 'es';
    await wrapper.vm.$nextTick();
    expect(wrapper.text()).toBe('Página web · Tu página web está en línea en https://a.erplora.com/');
  });

  it('only works inside a component, which is where the app’s translator lives', () => {
    expect(() => useT()).toThrow(/setup/);
  });
});
