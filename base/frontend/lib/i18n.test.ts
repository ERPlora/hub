// The shell's i18n from a component's script: `vue-i18n` is a dependency of @erplora/ui, not of the
// Hub, so the app reads the instance the shell injected globally (`$t`, `$i18n`) instead of
// importing `useI18n` (UI-REQUESTS.md asks @erplora/ui to export it).
import { createShellI18n } from '@erplora/ui/shell';
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import { defineComponent, h, nextTick } from 'vue';

import en from '../locale/en.json';
import es from '../locale/es.json';
import { useBaseI18n } from './i18n';

function harness(locale: 'en' | 'es') {
  const i18n = createShellI18n({ locale, messages: { en, es } });
  let api!: ReturnType<typeof useBaseI18n>;
  const Probe = defineComponent({
    setup() {
      api = useBaseI18n();
      return () => h('span', api.locale.value);
    },
  });
  const wrapper = mount(Probe, { global: { plugins: [i18n] } });
  return { i18n, wrapper, api: () => api };
}

describe('useBaseI18n', () => {
  it('translates with the shell catalogue, placeholders included', () => {
    const { api } = harness('es');
    expect(api().t('base.home.title')).toBe('Inicio');
    expect(api().t('base.setup.progress', { done: 1, total: 3 })).toBe('1 de 3 hechos');
  });

  it('follows the language of the shell', async () => {
    const { i18n, wrapper, api } = harness('en');
    expect(api().locale.value).toBe('en');
    (i18n.global.locale as unknown as { value: string }).value = 'es';
    await nextTick();
    expect(api().locale.value).toBe('es');
    expect(wrapper.text()).toBe('es');
    expect(api().t('base.home.title')).toBe('Inicio');
  });

  it('must be called from setup()', () => {
    expect(() => useBaseI18n()).toThrow(/setup/);
  });
});
