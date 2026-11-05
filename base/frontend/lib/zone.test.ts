// hub#687: the business's clock on a screen, as `base.business.get` says it (the hub's zone): followed live, one
// subscription for the whole tab however many pieces ask, and unknown until the business answers: never a zone written
// by hand.
import { afterEach, describe, expect, it } from 'vitest';
import { defineComponent, h } from 'vue';

import { business, BYE, errorFrame, flush, HELLO, mountBase } from '../__tests__/mount-base';
import { useBusinessClock, useBusinessZone } from './zone';

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

describe('useBusinessClock', () => {
  const Unread = defineComponent({
    setup() {
      const { zone, unread } = useBusinessClock();
      return () => h('span', { 'data-testid': 'clock' }, `${zone.value ?? 'unknown'} ${unread.value}`);
    },
  });

  it('says its zone could not be read only when it failed, and takes it back when the business answers', async () => {
    const m = await mountBase(Unread);
    const call = await m.live();
    const shown = () => m.wrapper.find('[data-testid="clock"]').text();
    expect(shown()).toBe('unknown false');
    call.push(errorFrame(m.client.stream.subscriptions('base.business.get')[0].id, 'base.boom'));
    await flush();
    expect(shown()).toBe('unknown true');
    await m.result(call, 'base.business.get', business({ timezone: 'Atlantic/Canary' }));
    expect(shown()).toBe('Atlantic/Canary false');
    // The zone it knows stays good when a later read fails.
    call.push(errorFrame(m.client.stream.subscriptions('base.business.get')[0].id, 'base.boom'));
    await flush();
    expect(shown()).toBe('Atlantic/Canary false');
  });

  it('says so too while the stream is down and it never answered', async () => {
    const m = await mountBase(Unread);
    const call = await m.live();
    call.push(HELLO);
    call.push(BYE);
    await flush();
    expect(m.wrapper.find('[data-testid="clock"]').text()).toBe('unknown true');
  });
});
