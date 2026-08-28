// @vitest-environment happy-dom
// Regression test for ERPlora/hub#1169 — the shell's own load states for a module screen.
//
// What was on screen (seen on `qa-pm149`, shell v1.1.9, at 768×1024 and at 1440): while the
// module's Web Component downloads — half a second on a warm cache, several on a cold first
// visit — the shell painted a bare `ion-spinner` and the words «Cargando módulo…» glued to the
// TOP-LEFT corner of an otherwise blank full-screen card. Around 95 % of the viewport was white.
// A blank screen with a speck in the corner does not read as «this is coming», it reads as «this
// broke», and it is the FIRST thing a person sees on their first visit to every module.
//
// The market settled this a long time ago and we take the settled answer, not a new one: Shopify
// Polaris paints a SkeletonPage (header bar + rows), Square's dashboard a table skeleton, and
// Ionic — the framework this shell is built on — ships `ion-skeleton-text` for exactly this. The
// skeleton occupies the area the content will occupy, so the eye already knows the shape of what
// is loading and nothing looks broken.
//
// These tests hold all THREE sentences the page has to be able to say, because they are three
// different sentences and a screen that says one meaning another is the defect (the rule
// `lib/list-load-state.ts` already writes down for lists, hub#770):
//
//   • loading — the skeleton, full width, announced to screen readers;
//   • error   — the load actually failed: say so and offer the way back (retry);
//   • empty   — the module answered and has NOTHING to paint. Today this said «Could not load
//     the module» with a Retry button that can only fail again, which is «error» said about a
//     fact. It is the same lie hub#770 fixed for lists, one screen up.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { nextTick } from 'vue';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const routeParams = { moduleId: 'sales', navId: 'orders' };

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: routeParams,
    name: 'module',
    path: `/m/${routeParams.moduleId}/${routeParams.navId}`,
    fullPath: `/m/${routeParams.moduleId}/${routeParams.navId}`,
  }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

/** The menu call, under the test's control: each mount takes the next queued answer. */
const menuAnswers: Array<() => Promise<unknown>> = [];
vi.mock('../lib/module-loader', () => ({
  loadMenu: () => (menuAnswers.shift() ?? (() => Promise.resolve([])))(),
  loadManifest: vi.fn(async () => ({})),
  loadComponent: vi.fn(async () => 'erp-sales-orders'),
}));
vi.mock('../lib/runtime', () => ({
  clientInjectionKey: Symbol('runtime-client'),
  getClient: () => ({ forModule: () => ({}), on: () => () => {} }),
}));
vi.mock('../lib/protects', () => ({ resolveProtectsGuard: vi.fn(async () => null) }));
vi.mock('../lib/entitlement', () => ({
  isModuleBlocked: () => false,
  resolveEntitlement: async () => {},
}));
vi.mock('../lib/immersive', () => ({
  chromeControlsFor: () => [],
  installChrome: () => () => {},
}));
vi.mock('@erplora/outfitkit/tabbar', () => ({ scrollActiveTabIntoView: vi.fn() }));

vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /><slot name="footer" /></div>' },
}));
vi.mock('../components/ModulePlanPanel.vue', () => ({
  default: { name: 'ModulePlanPanel', template: '<div />' },
}));
vi.mock('../components/ModuleSettingsForm.vue', () => ({
  default: { name: 'ModuleSettingsForm', template: '<div />' },
}));
vi.mock('../components/HubIcon.vue', () => ({
  default: { name: 'HubIcon', template: '<span />' },
}));

import ModuleView from './ModuleView.vue';
// REAL catalogues: English is the source language and Spanish is NOT optional (binding rule of
// 2026-08-04) — a state whose Spanish is missing is a state that ships half-translated.
import enCatalogue from '../i18n/locales/en';
import esCatalogue from '../i18n/locales/es';

// `import.meta.url` is not a file URL under happy-dom; vitest runs with the package root
// (`apps/web`) as cwd, which is what the whole suite already relies on.
const moduleViewSource = readFileSync(join(process.cwd(), 'src/views/ModuleView.vue'), 'utf8');

const mounted: Array<{ unmount: () => void }> = [];

function mountModuleView(locale: 'en' | 'es' = 'en') {
  const i18n = createI18n({
    legacy: false,
    locale,
    missingWarn: false,
    fallbackWarn: false,
    messages: { en: enCatalogue, es: esCatalogue },
  });
  const wrapper = mount(ModuleView, { global: { plugins: [i18n] } });
  mounted.push(wrapper);
  return wrapper;
}

type Wrapper = ReturnType<typeof mountModuleView>;

async function settle(): Promise<void> {
  await flushPromises();
  await nextTick();
  await flushPromises();
}

/** A menu request that never comes back — the state the person stares at on a cold first visit. */
function queuePendingMenu(): void {
  menuAnswers.push(() => new Promise(() => {}));
}

/** One nav entry, the shape `loadMenu()` hands back. */
const entry = (moduleId: string) => ({
  moduleId,
  moduleName: 'Sales',
  nav: { id: 'orders', label: 'Orders', icon: 'cart' },
});

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount();
});

beforeEach(() => {
  menuAnswers.length = 0;
});

describe('the shell paints the three load states of a module screen (hub#1169)', () => {
  it('hub1169_the_module_loading_state_is_a_centered_skeleton_not_a_corner_spinner', async () => {
    queuePendingMenu();
    const wrapper = mountModuleView();
    await settle();

    const skeleton = wrapper.find('[data-testid="module-skeleton"]');
    expect(skeleton.exists(), 'the loading state paints no skeleton at all').toBe(true);

    // A header bar + rows: the SHAPE of the screen that is coming, not a speck in the corner.
    const bars = wrapper.findAll('ion-skeleton-text');
    expect(bars.length, 'too few skeleton bars to read as a page').toBeGreaterThanOrEqual(7);
    // `animated` is a Stencil prop that does NOT reflect to an attribute: Ionic sets it as a
    // PROPERTY on the element, and it reads back `false` when the template omits it — which is
    // what makes this assertion discriminate instead of always passing.
    for (const bar of bars) {
      const el = bar.element as unknown as { animated?: boolean };
      expect(el.animated, 'a still skeleton reads as broken, not as loading').toBe(true);
    }

    // The lone spinner is the defect. It must be gone, not merely moved.
    expect(wrapper.find('ion-spinner').exists(), 'the corner spinner is still there').toBe(false);
  });

  it('announces the wait to screen readers even though the skeleton is decorative', async () => {
    queuePendingMenu();
    const wrapper = mountModuleView();
    await settle();

    const skeleton = wrapper.find('[data-testid="module-skeleton"]');
    expect(skeleton.attributes('role')).toBe('status');
    expect(skeleton.attributes('aria-busy')).toBe('true');
    // Grey bars say nothing out loud: the sentence has to be there for anyone not looking.
    expect(skeleton.attributes('aria-label')).toBe(enCatalogue.moduleView.loading);
  });

  it('fills the content area instead of hugging the top-left corner', async () => {
    // The whole report is about WHERE it sits. The bars are laid out by this rule and nothing
    // else, so the rule is part of the contract: full width, and no `align-items: center` flex
    // row that collapses the block onto one short line in the corner.
    const rule = moduleViewSource.match(/\.module-skeleton\s*\{([\s\S]*?)\}/)?.[1] ?? '';
    expect(rule, '.module-skeleton has no rule of its own').not.toBe('');
    expect(rule).toMatch(/width:\s*100%/);
    expect(rule).not.toMatch(/align-items:\s*center/);
    // The state it replaces must not survive alongside it.
    expect(moduleViewSource).not.toContain('.state-loading');
  });

  it('says a FAILED load failed, and offers the way back', async () => {
    menuAnswers.push(() => Promise.reject(new Error('offline')));
    const wrapper = mountModuleView();
    await settle();

    const feedback = wrapper.find('ok-inline-feedback');
    expect(feedback.exists(), 'a failed load paints no error at all').toBe(true);
    expect(feedback.attributes('tone')).toBe('danger');
    expect(feedback.attributes('heading')).toBe(enCatalogue.moduleView.loadError);
    expect(wrapper.text()).toContain(enCatalogue.moduleView.retry);
    // A failure is not an empty screen and not a skeleton.
    expect(wrapper.find('[data-testid="module-skeleton"]').exists()).toBe(false);
    expect(wrapper.find('ok-empty-state').exists()).toBe(false);
  });

  it('🔴 says a module with NOTHING to paint is empty — not that it failed', async () => {
    // The menu came back. It just has no entry for this module (deactivated, or a module that
    // declares no `navigation[]`). Nothing failed, so «Could not load the module» + Retry is a
    // lie that loops: the retry can only ever produce the same answer.
    menuAnswers.push(async () => [entry('inventory')]);
    const wrapper = mountModuleView();
    await settle();

    const empty = wrapper.find('ok-empty-state');
    expect(empty.exists(), 'an empty module still reports itself as a failure').toBe(true);
    expect(empty.attributes('heading')).toBe(enCatalogue.moduleView.emptyTitle);
    expect(empty.attributes('message')).toBe(enCatalogue.moduleView.emptyHint);
    // The icon has to be one OutfitKit BAKES (`BY_NAME` in its `src/base/icons.ts`). An
    // unbaked name is not an error: `okIcon()` hands the raw string to `ion-icon`, which
    // tries to FETCH it, and the Hub is offline — the icon comes out empty and silent. That
    // is how 19 icons sat broken in the Hub before OutfitKit started shipping its own.
    expect(empty.attributes('icon')).toBe('apps-outline');
    expect(wrapper.find('ok-inline-feedback').exists(), 'the error state is shown too').toBe(false);
    expect(wrapper.find('[data-testid="module-skeleton"]').exists()).toBe(false);
  });

  it('says the empty state in Spanish too', async () => {
    menuAnswers.push(async () => [entry('inventory')]);
    const wrapper = mountModuleView('es');
    await settle();

    expect(wrapper.find('ok-empty-state').attributes('heading')).toBe(
      esCatalogue.moduleView.emptyTitle,
    );
  });

  it('mounts the module and paints none of the three once it is ready', async () => {
    menuAnswers.push(async () => [entry('sales')]);
    const wrapper: Wrapper = mountModuleView();
    await settle();

    expect(wrapper.find('[data-testid="module-skeleton"]').exists()).toBe(false);
    expect(wrapper.find('ok-inline-feedback').exists()).toBe(false);
    expect(wrapper.find('ok-empty-state').exists()).toBe(false);
  });
});
