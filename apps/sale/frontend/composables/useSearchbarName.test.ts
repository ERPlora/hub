// `useSearchbarName`: Ionic 8 names the inner input of an `ion-searchbar` «search text», in English, whatever
// its hint says (outfitkit#182), so a screen reader never reads «Buscar producto…». Every searchbar of the
// app is named by its hint, in the person's language, through `@erplora/ui/components`'
// `syncSearchbarInputName`: once it is on screen, again when its hint changes (the language, the
// territory's tax) and when the searchbar is created again.
import { createShellI18n } from '@erplora/ui/shell';
import { IonSearchbar } from '@ionic/vue';
import { mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';
import { defineComponent, h, ref, useTemplateRef } from 'vue';

import { namesGiven } from '../__tests__/searchbar-name';
import { useSearchbarName } from './useSearchbarName';
import { useT } from './useT';

vi.mock('@erplora/ui/components', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/components')>()),
  syncSearchbarInputName: (await import('../__tests__/searchbar-name')).recordSearchbarName,
}));

const messages = { en: { hint: 'Search a {what}…' }, es: { hint: 'Buscar un {what}…' } };

function host(options: { shown?: () => boolean; what?: () => string } = {}) {
  const i18n = createShellI18n({ locale: 'es', messages });
  const wrapper = mount(
    defineComponent({
      setup() {
        const t = useT();
        const bar = useTemplateRef<{ $el: Element }>('bar');
        useSearchbarName(bar, () => t('hint', { what: options.what?.() ?? 'producto' }));
        return () => h('div', [h('p', 'before'), (options.shown?.() ?? true) ? h(IonSearchbar, { ref: 'bar' }) : null]);
      },
    }),
    { global: { plugins: [i18n] } },
  );
  const bar = () => wrapper.find('ion-searchbar').element;
  return { i18n, wrapper, bar };
}

describe('useSearchbarName', () => {
  it('names the searchbar by its hint, in the app’s language, once it is on screen', async () => {
    const { wrapper, bar } = host();
    await wrapper.vm.$nextTick();
    expect(namesGiven(bar())).toEqual(['Buscar un producto…']);
  });

  it('names it again when the language changes', async () => {
    const { i18n, wrapper, bar } = host();
    await wrapper.vm.$nextTick();
    i18n.global.locale.value = 'en';
    await wrapper.vm.$nextTick();
    expect(namesGiven(bar())).toEqual(['Buscar un producto…', 'Search a producto…']);
  });

  it('names it again when what its hint says changes', async () => {
    const what = ref('producto');
    const { wrapper, bar } = host({ what: () => what.value });
    await wrapper.vm.$nextTick();
    what.value = 'servicio';
    await wrapper.vm.$nextTick();
    expect(namesGiven(bar())).toEqual(['Buscar un producto…', 'Buscar un servicio…']);
  });

  it('names a searchbar created again', async () => {
    const shown = ref(true);
    const { wrapper, bar } = host({ shown: () => shown.value });
    await wrapper.vm.$nextTick();
    const first = bar();
    shown.value = false;
    await wrapper.vm.$nextTick();
    shown.value = true;
    await wrapper.vm.$nextTick();
    expect(bar()).not.toBe(first);
    expect(namesGiven(bar())).toEqual(['Buscar un producto…']);
  });
});
