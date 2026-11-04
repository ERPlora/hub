// hub#687: the business's clock on a screen, as `base.business.get` says it (the hub's zone): followed live, one
// subscription for the whole tab however many pieces ask, and unknown until the business answers: never a zone written
// by hand.
import { afterEach, describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import { business, flush, mountBase } from '../__tests__/mount-base';
import { useBusinessZone } from './zone';

const Probe = defineComponent({
  setup() {
    const zone = useBusinessZone();
    return () => h('span', { 'data-testid': 'zone' }, zone.value ?? 'unknown');
  },
});

afterEach(() => {
  document.body.innerHTML = '';
});

describe('useBusinessZone', () => {
  it("is the business's zone, unknown until it answers, and follows each change live", async () => {
    const m = await mountBase(Probe);
    const call = await m.live();
    const shown = () => m.wrapper.find('[data-testid="zone"]').text();
    expect(shown()).toBe('unknown');
    await m.result(call, 'base.business.get', business({ timezone: 'Atlantic/Canary' }));
    expect(shown()).toBe('Atlantic/Canary');
    await m.result(call, 'base.business.get', business({ timezone: 'Asia/Tokyo' }), 2);
    await flush();
    expect(shown()).toBe('Asia/Tokyo');
  });
});
