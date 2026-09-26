// @vitest-environment happy-dom
//
// hub#2205 — the «This page does not exist» block is ONE component, shared by the root 404
// (NotFoundPage) and an app that does not have the screen the address names (ModuleView). Two
// wrong addresses answered two different ways was the defect; the way to keep them the same is
// that neither of them can say it on its own.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

import NotFoundState from './NotFoundState.vue';
import enCatalogue from '../i18n/locales/en';

function mountState() {
  const i18n = createI18n({
    legacy: false,
    locale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages: { en: enCatalogue },
  });
  return mount(NotFoundState, { global: { plugins: [i18n] } });
}

describe('the shared «This page does not exist» block (hub#2205)', () => {
  it('says the page does not exist and offers the way to Home', () => {
    const wrapper = mountState();

    const state = wrapper.find('[data-testid="not-found"]');
    expect(state.exists()).toBe(true);
    expect(state.attributes('heading')).toBe(enCatalogue.notFound.title);
    expect(state.attributes('message')).toBe(enCatalogue.notFound.body);
    expect(wrapper.find('[data-testid="not-found-home"]').text()).toBe(enCatalogue.notFound.action);
  });

  it.each(['../views/NotFoundPage.vue', '../views/ModuleView.vue'])(
    '%s paints the shared block instead of its own copy',
    (file) => {
      const source = readFileSync(resolve(__dirname, file), 'utf8');

      expect(source).toContain('<NotFoundState');
      // A second copy of the sentence is how the two answers drift apart again.
      expect(source).not.toContain(":heading=\"t('notFound.title')");
      expect(source).not.toContain('data-testid="not-found-home"');
    },
  );
});
