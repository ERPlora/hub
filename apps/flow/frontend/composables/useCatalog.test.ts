/* eslint-disable vue/one-component-per-file -- one throwaway host component per case */
// `useCatalog()`: what an automation can start on and do in this business (`flow.catalog.read`), read
// once when the editor or the gallery opens, with its loading and its failure, and read again on demand.
import { describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import { mountFlow, settle } from '../__tests__/mount-flow';
import { useCatalog } from './useCatalog';
import { usePhrasing } from './usePhrasing';

const CATALOG = { events: [{ name: 'sale.sale.completed', app: 'sale', app_name: 'Sales' }], actions: [] };

function host(exposed: Record<string, unknown>) {
  return defineComponent({
    setup() {
      const catalog = useCatalog();
      Object.assign(exposed, catalog);
      return () => h('p', catalog.loading.value ? 'loading' : catalog.error.value ? catalog.error.value.code : String(catalog.catalog.value?.events.length));
    },
  });
}

describe('useCatalog', () => {
  it('reads the catalog once and paints what it got', async () => {
    const exposed: Record<string, unknown> = {};
    const m = await mountFlow(host(exposed), { answers: { '/api/flow/catalog': [200, CATALOG] } });
    expect(m.wrapper.text()).toBe('loading');
    await settle();
    expect(m.wrapper.text()).toBe('1');
    expect(m.sent().map((call) => `${call.method} ${call.path}`)).toEqual(['GET /api/flow/catalog']);
  });

  it('says why it could not, and reads again', async () => {
    const exposed: { reload?: () => Promise<void> } = {};
    const m = await mountFlow(host(exposed), { answers: { '/api/flow/catalog': [403, { error: { code: 'permission_denied', message: 'No' } }] } });
    await settle();
    expect(m.wrapper.text()).toBe('permission_denied');
    m.answerBy({ '/api/flow/catalog': [200, CATALOG] });
    await exposed.reload!();
    await settle();
    expect(m.wrapper.text()).toBe('1');
  });
});

describe('usePhrasing', () => {
  it('gives the phrasing the app translator, its key check and its language, live', async () => {
    const m = await mountFlow(
      defineComponent({
        setup() {
          const phrasing = usePhrasing();
          return () => h('p', `${phrasing.value.locale}|${phrasing.value.t('flow.title')}|${phrasing.value.te('flow.nothing')}`);
        },
      }),
      { locale: 'es' },
    );
    expect(m.wrapper.text()).toBe('es|Automatizaciones|false');
  });
});
