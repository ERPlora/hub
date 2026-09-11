// @vitest-environment happy-dom
//
// hub#1723 — the screen a wrong address gets instead of Inicio.
//
// The route table is what stops the silent redirect (`router/not-found-route.hub1723.test.ts`);
// this is the other half: what the person actually READS when they land here. A 404 that says
// nothing useful is the same defect with an extra click, so the three things it owes are held
// here — it says the address does not exist, it says it in the person's own language, and it
// offers ONE way out that works.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { IonButton } from '@ionic/vue';

vi.mock('../components/AppPage.vue', () => ({
  default: {
    name: 'AppPage',
    props: ['title', 'contentLayout'],
    template: '<div data-testid="app-page" :data-title="title"><slot /></div>',
  },
}));

import NotFoundPage from './NotFoundPage.vue';
// The REAL catalogues: English is the source language and Spanish is NOT optional (binding rule
// of 2026-08-04). A screen whose Spanish is missing is a screen that ships half-translated.
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

const mounted: Array<{ unmount: () => void }> = [];

function mountNotFound(locale: 'en' | 'es' = 'en') {
  const i18n = createI18n({
    legacy: false,
    locale,
    missingWarn: false,
    fallbackWarn: false,
    messages: { en: enCatalogue, es: esCatalogue },
  });
  const wrapper = mount(NotFoundPage, { global: { plugins: [i18n] } });
  mounted.push(wrapper);
  return wrapper;
}

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});

describe('the screen a wrong address lands on (hub#1723)', () => {
  it('says the page does not exist, in words and not in a key', () => {
    const wrapper = mountNotFound();

    const state = wrapper.find('ok-empty-state');
    expect(state.exists(), 'the 404 paints no empty state at all').toBe(true);
    expect(state.attributes('heading')).toBe(enCatalogue.notFound.title);
    expect(state.attributes('message')).toBe(enCatalogue.notFound.body);
    // A raw key on screen is the same as saying nothing (ADR-0055).
    expect(wrapper.html()).not.toContain('notFound.');
  });

  it('says it in Spanish too, because the shop floor reads Spanish', () => {
    const wrapper = mountNotFound('es');

    const state = wrapper.find('ok-empty-state');
    expect(state.attributes('heading')).toBe(esCatalogue.notFound.title);
    expect(state.attributes('message')).toBe(esCatalogue.notFound.body);
    // The control: Spanish that is merely the English string copied over is not a translation.
    expect(esCatalogue.notFound.title).not.toBe(enCatalogue.notFound.title);
    expect(esCatalogue.notFound.body).not.toBe(enCatalogue.notFound.body);
    expect(esCatalogue.notFound.action).not.toBe(enCatalogue.notFound.action);
  });

  it('offers exactly one way out, and it goes to Inicio', () => {
    const wrapper = mountNotFound();

    const home = wrapper.find('[data-testid="not-found-home"]');
    expect(home.exists(), 'a dead end is not a screen, it is a trap').toBe(true);
    expect(home.text()).toBe(enCatalogue.notFound.action);
    // Through Ionic's own prop and not the rendered attribute: `router-link` is what the rest of
    // the shell uses to navigate (App.vue, MyAppsCard, SetupChecklistCard), so this asserts the
    // same contract they do instead of how Ionic happens to reflect it into the DOM today.
    expect(wrapper.findComponent(IonButton).props('routerLink')).toBe('/dashboard');
    // ONE way out: a 404 with a menu of guesses is the complexity this product does not add.
    expect(wrapper.findAll('ion-button')).toHaveLength(1);
  });

  it('keeps the shell around it, so the menu is still there to navigate with', () => {
    const wrapper = mountNotFound();

    // AppPage is the shell's single layout (topbar + sidebar). A full-screen 404 like the login
    // page would strand the person: their way out would be the browser's Back button.
    expect(wrapper.find('[data-testid="app-page"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="app-page"]').attributes('data-title')).toBe(
      enCatalogue.notFound.title,
    );
  });
});
