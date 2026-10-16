// `usePhrasing()` is covered with the catalog in useCatalog.test.ts (the editor reads both together);
// this file pins its contract on its own: a computed phrasing that follows the app's language.
import { describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import { mountFlow } from '../__tests__/mount-flow';
import { usePhrasing } from './usePhrasing';

describe('usePhrasing', () => {
  it('follows a change of language', async () => {
    const m = await mountFlow(
      defineComponent({
        setup() {
          const phrasing = usePhrasing();
          return () => h('p', phrasing.value.t('flow.paused'));
        },
      }),
    );
    expect(m.wrapper.text()).toBe('Paused');
    (m.wrapper.vm.$i18n as unknown as { locale: string }).locale = 'es';
    await m.wrapper.vm.$nextTick();
    expect(m.wrapper.text()).toBe('En pausa');
  });
});
