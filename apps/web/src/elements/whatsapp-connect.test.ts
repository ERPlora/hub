// @vitest-environment happy-dom
// The element a module embeds (hub#1600): defined under its tag, once, without a shadow root — a
// second boot must not throw, and the module's screen must be able to style what is inside.
//
// hub#1614 — and it must LOOK right where it actually lands. The module's settings screen is a
// LitElement with its own shadow root, and a stylesheet of the shell's does not cross that
// boundary, so the block's own rules have to travel inside the element instead of living in the
// shell's global sheet. That is what the styling tests below pin: the rules apply in a foreign
// shadow root, they apply in the plain document too, and they do not paint anything outside the
// tag — the module's screen is right there in the same tree.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import { nextTick } from 'vue';

vi.mock('../lib/whatsapp-connect', () => ({
  BUSINESS_APP_FEATURE: 'whatsapp_business_app_onboarding',
  WhatsAppConnectError: class WhatsAppConnectError extends Error {
    readonly code: string;
    readonly status: number;
    constructor(code: string, status: number) {
      super(code);
      this.code = code;
      this.status = status;
    }
  },
  fetchWhatsAppConfig: vi.fn(),
  fetchWhatsAppNumbers: vi.fn(),
  connectWhatsApp: vi.fn(),
  disconnectWhatsApp: vi.fn(),
  loadMetaSdk: vi.fn(),
  openEmbeddedSignup: vi.fn(),
}));
vi.mock('../lib/session', async () => {
  const { ref } = await import('vue');
  return { isAdmin: ref(true) };
});

import { WHATSAPP_CONNECT_TAG, registerWhatsAppConnectElement } from './whatsapp-connect';
import { WhatsAppConnectError, fetchWhatsAppConfig, fetchWhatsAppNumbers } from '../lib/whatsapp-connect';
import es from '../i18n/locales/es';

const CONFIG = { configured: true, app_id: '1534856651538860', config_id: 'cfg_987', graph_version: 'v25.0' };
const NUMBER = { phone_number_id: 'phone_123', display_phone: '+34 612 345 678', is_active: true, is_on_biz_app: true };

/** The colours the block's own rules resolve to when no `--ion-*` token is in scope. */
const MEDIUM = '#6b7280';
const DANGER = '#b91c1c';

/** A module's settings screen: a shadow root the shell's global stylesheet cannot reach into. */
function moduleScreen(): ShadowRoot {
  const host = document.createElement('div');
  document.body.appendChild(host);
  return host.attachShadow({ mode: 'open' });
}

/** Mounts the real element in `parent` and waits for its first load to settle. */
async function embed(parent: ParentNode): Promise<HTMLElement> {
  registerWhatsAppConnectElement();
  const el = document.createElement(WHATSAPP_CONNECT_TAG);
  parent.appendChild(el);
  await flushPromises();
  await nextTick();
  return el;
}

beforeEach(() => {
  document.body.innerHTML = '';
  document.head.innerHTML = '';
  vi.mocked(fetchWhatsAppConfig).mockReset().mockResolvedValue(CONFIG);
  vi.mocked(fetchWhatsAppNumbers).mockReset().mockResolvedValue([]);
});

describe('erp-whatsapp-connect', () => {
  it('is defined once under its tag and survives a second registration', () => {
    registerWhatsAppConnectElement();
    const first = customElements.get(WHATSAPP_CONNECT_TAG);
    expect(first).toBeDefined();
    expect(() => registerWhatsAppConnectElement()).not.toThrow();
    expect(customElements.get(WHATSAPP_CONNECT_TAG)).toBe(first);
  });

  it('renders in the light DOM so the module screen can see and style it', async () => {
    const el = await embed(document.body);
    expect(el.shadowRoot).toBeNull();
  });

  it('writes its sentences in the language of the till', async () => {
    // A custom element is its own Vue app: the shell's i18n has to be handed to it under the key
    // `useI18n()` looks up in a web component, or every sentence in the block throws in setup and
    // the owner is left staring at an empty box where the «Connect» button should be.
    const el = await embed(moduleScreen());
    expect(el.textContent).toContain(es.whatsappConnect.intro);
    expect(el.querySelector('[data-test="whatsapp-connect-button"]')).not.toBeNull();
  });

  it('reads the failure sentence in red inside a module shadow root', async () => {
    vi.mocked(fetchWhatsAppConfig).mockRejectedValue(new WhatsAppConnectError('unreachable', 0));
    const el = await embed(moduleScreen());
    const alert = el.querySelector('.whatsapp-connect__status--error');
    expect(alert, 'the block did not render its failure sentence').not.toBeNull();
    expect(getComputedStyle(alert as Element).color).toBe(DANGER);
  });

  it('lays the number row out in line inside a module shadow root', async () => {
    vi.mocked(fetchWhatsAppNumbers).mockResolvedValue([NUMBER]);
    const el = await embed(moduleScreen());
    const row = el.querySelector('.whatsapp-connect__number');
    expect(row, 'the block did not render the connected number').not.toBeNull();
    const style = getComputedStyle(row as Element);
    expect(style.display).toBe('flex');
    expect(style.justifyContent).toBe('space-between');
    expect(getComputedStyle(el).display).toBe('block');
  });

  it('greys the help sentence in the plain document too', async () => {
    vi.mocked(fetchWhatsAppNumbers).mockResolvedValue([NUMBER]);
    const el = await embed(document.body);
    const help = el.querySelector('.whatsapp-connect__help');
    expect(help, 'the block did not render its help sentence').not.toBeNull();
    expect(getComputedStyle(help as Element).color).toBe(MEDIUM);
  });

  it('paints nothing outside its own tag', async () => {
    vi.mocked(fetchWhatsAppConfig).mockRejectedValue(new WhatsAppConnectError('unreachable', 0));
    const screen = moduleScreen();
    await embed(screen);
    // The module's own screen sits in the same tree: its markup must come out untouched even when
    // it happens to use the same class names.
    const foreign = document.createElement('p');
    foreign.className = 'whatsapp-connect__status whatsapp-connect__status--error';
    screen.appendChild(foreign);
    expect(getComputedStyle(foreign).color).not.toBe(DANGER);
  });

  it('does not stack a second copy of its rules when it is re-connected', async () => {
    const screen = moduleScreen();
    const el = await embed(screen);
    const count = () => el.querySelectorAll('style').length;
    expect(count()).toBe(1);
    el.remove();
    screen.appendChild(el);
    await flushPromises();
    await nextTick();
    expect(count()).toBe(1);
  });

  it('cannot be styled from the shell global sheet: that is why it carries its own', async () => {
    // The control for the two tests above: with the same rules in the shell's stylesheet — where
    // they used to live — the block inside a module's shadow root stays unstyled. If this ever
    // starts passing, the check has stopped proving anything.
    const sheet = document.createElement('style');
    sheet.textContent = '.whatsapp-connect__probe { color: rgb(1, 2, 3); }';
    document.head.appendChild(sheet);
    const el = await embed(moduleScreen());
    const probe = document.createElement('p');
    probe.className = 'whatsapp-connect__probe';
    el.appendChild(probe);
    expect(getComputedStyle(probe).color).not.toBe('rgb(1, 2, 3)');

    const inDocument = await embed(document.body);
    const reachable = document.createElement('p');
    reachable.className = 'whatsapp-connect__probe';
    inDocument.appendChild(reachable);
    expect(getComputedStyle(reachable).color).toBe('rgb(1, 2, 3)');
  });
});
