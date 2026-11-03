// «Upgrade plan» has one rule wherever it is offered (BASE-F11): this hub's plan page on erplora.com, which `base/spa.py`
// embeds in `hub-home`, only on the web (it sells, and the stores refuse an app that sells), and never a button that does
// nothing when the address is not there.
import { applySurface } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { usePlanLink } from './plan-link';

const PLAN_URL = 'http://localhost:8001/store/plans?business=0199a1b2-0000-7000-8000-000000000001';

function embed(block: object | null) {
  document.head.innerHTML = block
    ? `<script id="hub-home" type="application/json">${JSON.stringify(block)}</script>`
    : '';
}

afterEach(() => {
  applySurface('web');
  document.head.innerHTML = '';
});

describe('usePlanLink', () => {
  it('on the web with the address embedded, offers it', () => {
    embed({ name: 'Bar', plan_url: PLAN_URL });
    const link = usePlanLink();
    expect([link.planUrl, link.offered.value]).toEqual([PLAN_URL, true]);
  });

  it('does not offer it where the address does not come', () => {
    embed(null);
    expect(usePlanLink().offered.value).toBe(false);
    embed({ name: 'Bar', plan_url: '' });
    expect(usePlanLink().offered.value).toBe(false);
  });

  it('does not offer it in the installed app, and follows the surface', () => {
    embed({ name: 'Bar', plan_url: PLAN_URL });
    const link = usePlanLink();
    applySurface('mobile');
    expect(link.offered.value).toBe(false);
    applySurface('web');
    expect(link.offered.value).toBe(true);
  });
});
