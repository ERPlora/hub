// «Upgrade plan» of the WhatsApp inbox (WHATSAPP_INBOX-F13; BASE-F11): one link for the inbox's notices, the box under
// the thread and Settings. It keeps erplora.com's plans as its address, and its click goes with the pass, so the person
// arrives already signed in. When the pass cannot be signed, the usual address opens.
import { describe, expect, it, vi } from 'vitest';

import { followUpgrade, mountInbox, SIGNED } from '../__tests__/mount-inbox';
import PlanUpgradeLink from './PlanUpgradeLink.vue';

const PLANS = 'http://localhost:8001/dashboard/store/plans';

describe('PlanUpgradeLink', () => {
  it('is a link to the address it is given, in a new tab, that says «Upgrade plan» in the screen’s language', async () => {
    const en = await mountInbox(PlanUpgradeLink, { props: { url: PLANS } });
    expect(en.wrapper.element.tagName).toBe('A');
    expect(en.wrapper.attributes()).toMatchObject({ href: PLANS, target: '_blank', rel: 'noopener' });
    expect(en.wrapper.text()).toBe('Upgrade plan');
    const es = await mountInbox(PlanUpgradeLink, { props: { url: PLANS }, locale: 'es' });
    expect(es.wrapper.text()).toBe('Mejorar el plan');
  });

  it('whoever places it names and styles it: its class and its testid land on the link', async () => {
    const m = await mountInbox(PlanUpgradeLink, {
      props: { url: PLANS, class: 'wa-settings__upgrade', 'data-testid': 'whatsapp-inbox-settings-upgrade' },
    });
    expect(m.wrapper.classes()).toContain('wa-settings__upgrade');
    expect(m.wrapper.attributes('data-testid')).toBe('whatsapp-inbox-settings-upgrade');
  });

  it('its click asks for a pass to the plan and opens it', async () => {
    const m = await mountInbox(PlanUpgradeLink, { props: { url: PLANS } });
    m.answer(200, { url: SIGNED });
    expect(await followUpgrade(m.wrapper.element)).toBe(SIGNED);
    expect(m.sent()).toEqual([{ method: 'POST', path: '/api/saas-pass', query: {}, body: { next: 'plan' } }]);
  });

  it('when the pass cannot be signed, the address it was given opens', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const m = await mountInbox(PlanUpgradeLink, { props: { url: PLANS } });
    m.answer(403, { error: { code: 'base.saas_pass_needs_account', message: 'No.' } });
    expect(await followUpgrade(m.wrapper.element)).toBe(PLANS);
    expect(error).toHaveBeenCalled();
    error.mockRestore();
  });
});
