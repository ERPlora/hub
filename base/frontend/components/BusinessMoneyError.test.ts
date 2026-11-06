// The notice of a window whose amounts wait for the business's money (hub#938): when `base.business.get` fails before the
// money is known, the window says it could not be read — the server's reason and «Retry» — instead of waiting in grey
// without a word. «Retry» asks the server again (the tab's stream reopens) and the notice goes while it asks; a new
// failure brings it back and the answer takes it away. Once the money is known a later failure says nothing: no window
// waits for it any longer. A window opened after the read had already failed (the page read the money on loading) says
// it as well. It is the one place that says it: every window that waits places it (CheckoutPanel aside, which says every
// read of its own).
import { afterEach, describe, expect, it } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { business, errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import { useBusinessMoney } from '../lib/money';
import BusinessMoneyError from './BusinessMoneyError.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountBase(BusinessMoneyError, { locale });
  const call = await m.live();
  const notice = () => m.wrapper.find('[data-testid="base-money-error"]');
  const fail = async (code = 'base.hub_busy') => {
    m.net.lastStream().push(errorFrame(subId(m.client, 'base.business.get'), code));
    await flush();
  };
  const answer = async () => {
    m.net.lastStream().push(`event: result\ndata: ${JSON.stringify({ id: subId(m.client, 'base.business.get'), data: business(), rev: 1 })}\n\n`);
    await flush();
  };
  return { ...m, call, notice, fail, answer };
}

describe('BusinessMoneyError', () => {
  it('says nothing while the business has not answered its money, nor once it has', async () => {
    const s = await setup();
    expect(s.client.stream.subscriptions('base.business.get').map((sub) => sub.params)).toEqual([{}]);
    expect(s.notice().exists()).toBe(false);
    await s.result(s.call, 'base.business.get', business());
    expect(s.notice().exists()).toBe(false);
  });

  it('a money that cannot be read: an alert with the reason and «Retry»', async () => {
    const s = await setup();
    await s.fail();
    expect(s.notice().attributes('role')).toBe('alert');
    expect(s.notice().text()).toContain("The business's currency could not be read");
    expect(s.notice().text()).toContain('msg base.hub_busy');
    expect(s.wrapper.find('[data-testid="base-money-error-retry"]').text()).toBe('Retry');
  });

  it('«Retry» asks the server again and the notice goes while it asks; a new failure brings it back, the answer takes it away', async () => {
    const s = await setup();
    await s.fail();
    const asked = s.net.streams.length;
    await s.wrapper.find('[data-testid="base-money-error-retry"]').trigger('click');
    await flush();
    expect([s.net.streams.length, s.notice().exists()]).toEqual([asked + 1, false]);
    await s.fail();
    expect(s.notice().exists()).toBe(true);
    await s.wrapper.find('[data-testid="base-money-error-retry"]').trigger('click');
    await flush();
    await s.answer();
    expect(s.notice().exists()).toBe(false);
  });

  it('a failure once the money is known says nothing: nothing waits for it', async () => {
    const s = await setup();
    await s.result(s.call, 'base.business.get', business());
    await s.fail();
    expect(s.notice().exists()).toBe(false);
  });

  it('a window opened after the read had already failed says so too, and «Retry» asks again', async () => {
    const open = ref(false);
    // The page follows the money from its load; its window (and the notice in it) mounts later, on a tap.
    const Page = defineComponent({
      setup() {
        useBusinessMoney();
        return () => h('div', open.value ? [h(BusinessMoneyError)] : []);
      },
    });
    const m = await mountBase(Page);
    await m.live();
    m.net.lastStream().push(errorFrame(subId(m.client, 'base.business.get'), 'base.hub_busy'));
    await flush();
    open.value = true;
    await flush();
    const notice = () => m.wrapper.find('[data-testid="base-money-error"]');
    expect(notice().exists() && notice().text()).toContain('msg base.hub_busy');
    const asked = m.net.streams.length;
    await m.wrapper.find('[data-testid="base-money-error-retry"]').trigger('click');
    await flush();
    expect([m.net.streams.length - asked, notice().exists()]).toEqual([1, false]);
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    await s.fail();
    expect(s.notice().text()).toContain('No se ha podido leer la moneda del negocio');
    expect(s.wrapper.find('[data-testid="base-money-error-retry"]').text()).toBe('Reintentar');
  });
});
