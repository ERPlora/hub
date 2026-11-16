// «Upgrade plan» with the pass (BASE-F11): the Hub's one link to erplora.com's plans. The menu's foot, People, System ›
// «Usage and plan», the Apps store and the WhatsApp inbox place it; each decides where it shows (it sells: only on the
// web) and how it looks, and none keeps a copy of its click. It keeps the address it is given, so when the pass cannot
// be signed, or the browser blocks the new tab, that address still opens.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it, vi } from 'vitest';
import { h } from 'vue';

import { flush, followPass, mountBase, passRefused, SIGNED, tap } from '../__tests__/mount-base';
import PlanUpgradeLink from './PlanUpgradeLink.vue';

const PLANS = 'http://localhost:8001/store/plans?business=0199a1b2-0000-7000-8000-000000000001';
const HUB = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const THE_PIECE = 'base/frontend/components/PlanUpgradeLink.vue';

/** The piece as its placer puts it: `url`, the attributes for the link and, when given, what it says. */
function placed(attrs: Record<string, unknown>, says?: () => unknown) {
  return { render: () => h(PlanUpgradeLink, { url: PLANS, ...attrs }, says ? { default: says } : undefined) };
}

/** A click on the plan with the pass, written by hand in a template (the copy this piece replaces). */
const HAND_WRITTEN = /\bopenSaasPass\(\s*['"]plan['"]/;

/** The `.vue` files the SPA paints: base's frontend and every app's, tests left out. */
function screens(): string[] {
  const roots = [join(HUB, 'base', 'frontend')];
  for (const app of readdirSync(join(HUB, 'apps'), { withFileTypes: true })) {
    if (app.isDirectory()) roots.push(join(HUB, 'apps', app.name, 'frontend'));
  }
  return roots.flatMap((root) => {
    try {
      return readdirSync(root, { recursive: true, encoding: 'utf8' })
        .filter((file) => file.endsWith('.vue') && !file.split('/').includes('node_modules'))
        .map((file) => relative(HUB, join(root, file)));
    } catch {
      return [];
    }
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

describe('PlanUpgradeLink', () => {
  it('is a link to the address it is given, in a new tab, that says the platform’s «Upgrade plan» in the screen’s language', async () => {
    const en = await mountBase(PlanUpgradeLink, { props: { url: PLANS } });
    expect(en.wrapper.element.tagName).toBe('A');
    expect(en.wrapper.attributes()).toMatchObject({ href: PLANS, target: '_blank', rel: 'noopener' });
    expect(en.wrapper.text()).toBe('Upgrade plan');
    const es = await mountBase(PlanUpgradeLink, { props: { url: PLANS }, locale: 'es' });
    expect(es.wrapper.text()).toBe('Mejorar plan');
  });

  it('says what its placer puts inside instead: the inbox’s own words, the menu’s icon and label', async () => {
    const m = await mountBase(placed({}, () => 'Mejorar el plan'), { locale: 'es' });
    expect(m.wrapper.get('a').text()).toBe('Mejorar el plan');
  });

  it('whoever places it names and styles it: its class, testid, title and label land on the link', async () => {
    const m = await mountBase(
      placed({ class: 'people-upgrade', 'data-testid': 'people-upgrade', title: 'Upgrade plan', 'aria-label': 'Upgrade plan' }),
    );
    const link = m.wrapper.get('a');
    expect(link.classes()).toContain('people-upgrade');
    expect(link.attributes()).toMatchObject({ 'data-testid': 'people-upgrade', title: 'Upgrade plan', 'aria-label': 'Upgrade plan' });
  });

  it('its click asks for a pass to the plan and opens it, already signed in on erplora.com', async () => {
    const m = await mountBase(PlanUpgradeLink, { props: { url: PLANS }, onApi: () => Response.json({ url: SIGNED }) });

    expect(await followPass(m, m.wrapper.element)).toEqual({ next: 'plan', to: SIGNED });
  });

  it('when the pass cannot be signed, the address it was given opens', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const m = await mountBase(PlanUpgradeLink, { props: { url: PLANS }, onApi: passRefused });

    expect(await followPass(m, m.wrapper.element)).toEqual({ next: 'plan', to: PLANS });
    expect(error).toHaveBeenCalled();
  });

  it('when the browser blocks the new tab, the link itself opens the address it was given, and nothing is signed', async () => {
    vi.spyOn(window, 'open').mockReturnValue(null);
    const m = await mountBase(PlanUpgradeLink, { props: { url: PLANS } });

    expect(tap(m.wrapper.element).defaultPrevented).toBe(false);
    await flush();

    expect(m.wrapper.attributes('href')).toBe(PLANS);
    expect(m.net.api).toEqual([]);
  });
});

describe('guardrail: the Hub opens the plan with the pass in one piece', () => {
  it('reads a click on the plan written by hand, and leaves the business’s and the piece’s use alone', () => {
    expect(HAND_WRITTEN.test(`<a :href="planUrl" target="_blank" @click="openSaasPass('plan', planUrl, $event)">`)).toBe(true);
    expect(HAND_WRITTEN.test(`@click="openSaasPass( "plan", url, $event)"`)).toBe(true);
    expect(HAND_WRITTEN.test(`@click="openSaasPass('business', manageUrl, $event)"`)).toBe(false);
    expect(HAND_WRITTEN.test('<PlanUpgradeLink :url="planUrl" data-testid="people-upgrade" />')).toBe(false);
  });

  it('no screen keeps its own copy of the click: they place PlanUpgradeLink', () => {
    const copies = screens().filter((file) => HAND_WRITTEN.test(readFileSync(join(HUB, file), 'utf8')));
    expect(copies).toEqual([THE_PIECE]);
  });
});
